"""The monthly review: what still needs a decision, and what was recognised."""
import sqlite3
from datetime import datetime, timezone

from tracker.blocks import CATEGORY_BLOCK, block_of
from tracker.classify import Classified, classify
from tracker.corrections import _tx
from tracker.months import month_facts

SPENDING_LIKE = ("spending", "bucket", "offset")


def transaction_dict(c: Classified) -> dict:
    return {"id": c.id, "date": c.date, "amount_cents": c.amount_cents, "description": c.description,
            "account": c.account_key, "account_name": c.account_name, "kind": c.kind, "category": c.category,
            "block": block_of(c) if c.kind in SPENDING_LIKE else None, "one_off": c.one_off,
            "provisional": c.provisional, "why": c.why, "guessed": c.guessed, "merchant": c.merchant_key}


def _newest_first(charges: list[Classified]) -> list[Classified]:
    return sorted(charges, key=lambda c: (c.date, c.id), reverse=True)


def review(conn: sqlite3.Connection, user_id: int, month: str | None) -> dict:
    """One month's review, or with no month, what still needs a decision across every month."""
    classified = classify(conn, user_id)
    first_month: dict[str, str] = {}
    for c in classified:
        if c.merchant_key and (c.merchant_key not in first_month or c.date[:7] < first_month[c.merchant_key]):
            first_month[c.merchant_key] = c.date[:7]

    here = [c for c in classified if month is None or c.date[:7] == month]
    spending = [c for c in here if c.kind in SPENDING_LIKE]

    # unplaced groups are by merchant key and sign, so a group's charges are all money out or all money in
    # (the client makes a merchant rule from a group's first charge, and a rule is for one sign)
    unplaced: dict[tuple[str, bool], list[Classified]] = {}
    recognised: dict[str, list[Classified]] = {}
    for c in spending:
        if c.category == "Uncategorised":
            unplaced.setdefault((c.merchant_key, c.amount_cents > 0), []).append(c)
        elif month is not None:
            recognised.setdefault(c.category, []).append(c)

    unplaced_out = [{"merchant": key, "count": len(cs), "cents": -sum(c.amount_cents for c in cs),
                     "charges": [transaction_dict(c) for c in _newest_first(cs)]}
                    for (key, _), cs in unplaced.items()]
    unplaced_out.sort(key=lambda g: (-g["cents"], g["merchant"]))

    recognised_out = []
    for category, cs in recognised.items():
        def first_time(c):
            return bool(c.merchant_key) and first_month[c.merchant_key] == month
        ordered = sorted(cs, key=lambda c: (not first_time(c), c.amount_cents, c.id))
        recognised_out.append({
            "category": category, "block": CATEGORY_BLOCK.get(category, "Everything else"),
            "cents": -sum(c.amount_cents for c in cs),
            "charges": [{**transaction_dict(c), "first_time": first_time(c)} for c in ordered]})
    recognised_out.sort(key=lambda g: (-g["cents"], g["category"]))

    reviewed = conn.execute("SELECT 1 FROM month_reviews WHERE user_id = ? AND month = ?",
                            (user_id, month)).fetchone() is not None
    return {"month": month, "unplaced": unplaced_out,
            "unconfirmed_income": [transaction_dict(c) for c in _newest_first(
                [c for c in here if c.kind == "income" and c.guessed])],
            "recognised": recognised_out, "reviewed": reviewed}


def mark_reviewed(conn: sqlite3.Connection, user_id: int, month: str) -> None:
    """Record that the month was reviewed, with the totals as they stand now."""
    facts = next((m for m in month_facts(conn, user_id) if m.month == month), None)
    income, spending = (facts.income_cents, facts.spending_cents) if facts else (0, 0)
    with _tx(conn):
        conn.execute("INSERT OR REPLACE INTO month_reviews (user_id, month, reviewed_at, income_cents, spending_cents)"
                     " VALUES (?, ?, ?, ?, ?)",
                     (user_id, month, datetime.now(timezone.utc).isoformat(timespec="seconds"), income, spending))
