"""Give every live transaction a kind, a category and a plain reason. Derived on read; stores nothing."""
import re
import sqlite3
from dataclasses import dataclass
from datetime import date

from tracker.matching import rule_matches
from tracker.merchant import merchant_key
from tracker.rules import Rule, load_rules

PAIR_WINDOW_DAYS = 5
SPENDING_LIKE = ("spending", "bucket", "offset")


@dataclass
class Classified:
    id: int
    account_key: str
    account_kind: str
    date: str
    amount_cents: int
    description: str
    provisional: bool
    kind: str
    category: str
    one_off: bool
    why: str
    guessed: bool  # true when no rule, override or card-payment pairing decided the row: the fallback did
    merchant_key: str = ""
    account_name: str = ""


def _overridden(row) -> bool:
    return row["o_kind"] is not None or row["o_category"] is not None or row["o_one_off"] is not None


def _pair_card_payments(rows: list, results: list, candidates: set) -> None:
    """Mark chequing money-out rows that paid a card payment.

    A card payment is a card money-in row whose final kind (after any override) is transfer.
    Each takes the nearest-dated unclaimed candidate of the same amount within PAIR_WINDOW_DAYS;
    rows are in date order, so the earlier one wins a tie.
    """
    available = sorted(candidates)
    for p, row in enumerate(rows):
        if row["account_kind"] != "card" or row["amount_cents"] <= 0:
            continue
        kind = row["o_kind"] if row["o_kind"] is not None else (results[p] or {}).get("kind")
        if kind != "transfer":
            continue
        day = date.fromisoformat(row["date"])
        best = None
        for i in available:
            if rows[i]["amount_cents"] != -row["amount_cents"]:
                continue
            gap = abs((date.fromisoformat(rows[i]["date"]) - day).days)
            if gap <= PAIR_WINDOW_DAYS and (best is None or gap < best[0]):
                best = (gap, i)
        if best:
            available.remove(best[1])
            results[best[1]] = dict(kind="transfer", category="", one_off=False, why="paid the card",
                                    guessed=False)


def classify(conn: sqlite3.Connection, user_id: int) -> list[Classified]:
    compiled = [(r, re.compile(r.pattern, re.IGNORECASE)) for r in load_rules(conn, user_id)]
    rows = conn.execute(
        "SELECT t.id, a.key AS account_key, a.kind AS account_kind, a.name AS account_name, t.date, t.amount_cents, t.description,"
        " t.provisional, o.kind AS o_kind, o.category AS o_category, o.one_off AS o_one_off"
        " FROM transactions t JOIN accounts a ON a.id = t.account_id"
        " LEFT JOIN overrides o ON o.transaction_id = t.id"
        " WHERE t.user_id = ? AND t.superseded_by IS NULL ORDER BY t.date, t.id", (user_id,)).fetchall()

    keys = [merchant_key(row["description"]) for row in rows]
    results = [next(({"kind": r.kind, "category": r.category, "one_off": bool(r.one_off),
                      "why": f"rule: {r.label}", "guessed": False}
                     for r, p in compiled if rule_matches(r, p, row, key)), None)
               for row, key in zip(rows, keys)]
    candidates = {i for i, row in enumerate(rows) if results[i] is None and not _overridden(row)
                  and row["account_kind"] == "chequing" and row["amount_cents"] < 0}
    _pair_card_payments(rows, results, candidates)

    out = []
    for row, result, key in zip(rows, results, keys):
        if result is None:
            if row["amount_cents"] > 0 and row["account_kind"] == "chequing":
                result = dict(kind="income", category="", one_off=False, why="no rule matched", guessed=True)
            elif row["amount_cents"] > 0 and row["account_kind"] == "savings":
                # money arriving in a savings account was moved there; it is not a refund of spending
                result = dict(kind="transfer", category="", one_off=False, why="moved into savings", guessed=True)
            else:
                result = dict(kind="spending", category="Uncategorised", one_off=False, why="no rule matched",
                              guessed=True)
        if _overridden(row):
            if row["o_kind"] is not None:
                result["kind"] = row["o_kind"]
            if row["o_category"] is not None:
                result["category"] = row["o_category"]
            if row["o_one_off"] is not None:
                result["one_off"] = bool(row["o_one_off"])
            result["why"] = "you set this"
            result["guessed"] = False
        if result["kind"] in SPENDING_LIKE and result["category"] == "":
            result["category"] = "Uncategorised"  # spending is never shown without a category
        out.append(Classified(row["id"], row["account_key"], row["account_kind"], row["date"],
                              row["amount_cents"], row["description"], bool(row["provisional"]), merchant_key=key, account_name=row["account_name"], **result))
    return out
