"""Corrections the owner makes: for one charge (an override row) or for a whole merchant (a rule)."""
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone

from tracker.blocks import CATEGORIES
from tracker.merchant import merchant_key
from tracker.rules import KINDS, set_merchant_rule
from tracker.store import write_tx

UNSET = object()  # a field not passed, as against None, which clears it
SPENDING_LIKE = ("spending", "bucket", "offset")


@contextmanager
def _tx(conn: sqlite3.Connection):
    """Join the caller's open transaction, or run one of our own."""
    if conn.in_transaction:
        yield conn
    else:
        with write_tx(conn):
            yield conn


RESERVED_CATEGORY = "Uncategorised"
MAX_CATEGORY = 40


def known_categories(conn: sqlite3.Connection, user_id: int) -> list[str]:
    """The fixed list plus every category this user's rules and overrides already use, sorted."""
    used = {r[0] for r in conn.execute(
        "SELECT category FROM rules WHERE user_id = ? AND category <> ''"
        " UNION SELECT category FROM overrides WHERE user_id = ? AND category IS NOT NULL AND category <> ''",
        (user_id, user_id))}
    return sorted(set(CATEGORIES) | used)


def clean_category(conn: sqlite3.Connection, user_id: int, name: str) -> str:
    """The category name to store: trimmed, checked, and spelt as an existing category if one matches ignoring case.

    Raises ValueError, with a message fit to show the owner, for a name that is empty, too long, holds a control
    character, or is the reserved name.
    """
    name = name.strip()
    if not name:
        raise ValueError("category must not be empty")
    if len(name) > MAX_CATEGORY:
        raise ValueError(f"category must be {MAX_CATEGORY} characters or fewer")
    if any(unicodedata.category(ch) == "Cc" for ch in name):
        raise ValueError("category must not contain control characters")
    if name.casefold() == RESERVED_CATEGORY.casefold():
        raise ValueError(f"{RESERVED_CATEGORY} is reserved; pick another name")
    return next((c for c in known_categories(conn, user_id) if c.casefold() == name.casefold()), name)


def _live_charge(conn: sqlite3.Connection, user_id: int, transaction_id: int):
    row = conn.execute("SELECT id, description, amount_cents FROM transactions"
                       " WHERE id = ? AND user_id = ? AND superseded_by IS NULL",
                       (transaction_id, user_id)).fetchone()
    if row is None:
        raise LookupError(transaction_id)
    return row


def _sign(amount_cents: int) -> int:
    return 1 if amount_cents > 0 else -1 if amount_cents < 0 else 0


def set_override(conn: sqlite3.Connection, user_id: int, transaction_id: int, *,
                 kind=UNSET, category=UNSET, one_off=UNSET) -> None:
    """Merge the passed fields into the charge's override; None clears a field; an all-NULL override is deleted."""
    if kind is not UNSET and kind is not None and kind not in KINDS:
        raise ValueError(f"kind {kind!r} is not one of {', '.join(KINDS)}")
    if category is not UNSET and category is not None and not isinstance(category, str):
        raise ValueError("category must be text")
    with _tx(conn):
        _live_charge(conn, user_id, transaction_id)
        if category is not UNSET and category is not None:
            category = clean_category(conn, user_id, category)
        held = conn.execute("SELECT kind, category, one_off, carried_key FROM overrides"
                            " WHERE transaction_id = ? AND user_id = ?", (transaction_id, user_id)).fetchone()
        values = dict(held) if held else {"kind": None, "category": None, "one_off": None}
        # a decision carried from a merchant rule stays carried only while the owner leaves it as it is
        carried = values.pop("carried_key", None) if kind is UNSET and category is UNSET else None
        values.pop("carried_key", None)
        if kind is not UNSET:
            values["kind"] = kind
        if category is not UNSET:
            values["category"] = category
        if one_off is not UNSET:
            values["one_off"] = None if one_off is None else int(bool(one_off))
        if all(v is None for v in values.values()):
            conn.execute("DELETE FROM overrides WHERE transaction_id = ? AND user_id = ?", (transaction_id, user_id))
            return
        conn.execute("INSERT OR REPLACE INTO overrides"
                     " (transaction_id, user_id, kind, category, one_off, set_at, carried_key)"
                     " VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (transaction_id, user_id, values["kind"], values["category"], values["one_off"],
                      datetime.now(timezone.utc).isoformat(timespec="seconds"), carried))


def clear_override(conn: sqlite3.Connection, user_id: int, transaction_id: int) -> None:
    with _tx(conn):
        _live_charge(conn, user_id, transaction_id)
        conn.execute("DELETE FROM overrides WHERE transaction_id = ? AND user_id = ?", (transaction_id, user_id))


def count_merchant_charges(conn: sqlite3.Connection, user_id: int, key: str, sign: int) -> int:
    """Live charges of the user with this merchant key and sign. Zero for an empty key."""
    if not key:
        return 0
    rows = conn.execute("SELECT description, amount_cents FROM transactions"
                        " WHERE user_id = ? AND superseded_by IS NULL", (user_id,))
    return sum(1 for r in rows if _sign(r["amount_cents"]) == sign and merchant_key(r["description"]) == key)


def _give_way(conn: sqlite3.Connection, user_id: int, transaction_id: int) -> None:
    """Drop the kind and category of a charge's override so the merchant's rule decides it. A one-off mark the
    owner set stays; a carried override's "not a one-off" came from the old rule and goes with it."""
    held = conn.execute("SELECT one_off, carried_key FROM overrides WHERE transaction_id = ? AND user_id = ?",
                        (transaction_id, user_id)).fetchone()
    if held is None:
        return
    if held["one_off"] is None or (held["carried_key"] is not None and held["one_off"] == 0):
        conn.execute("DELETE FROM overrides WHERE transaction_id = ? AND user_id = ?", (transaction_id, user_id))
    else:
        conn.execute("UPDATE overrides SET kind = NULL, category = NULL, carried_key = NULL"
                     " WHERE transaction_id = ? AND user_id = ?", (transaction_id, user_id))


def correct_merchant(conn: sqlite3.Connection, user_id: int, transaction_id: int, kind: str, category: str,
                     one_off: int = 0) -> int:
    """Make the owner's rule for this charge's merchant and sign; clear the kind and category of this charge's
    override (its one-off mark stays), and of any decision carried onto this merchant's rows; return charges decided.

    Spending, bucket and offset need a category; transfer, income and saving store none.
    """
    with _tx(conn):
        charge = _live_charge(conn, user_id, transaction_id)
        if kind in SPENDING_LIKE:
            category = clean_category(conn, user_id, category or "")
        else:
            category = ""
        key = merchant_key(charge["description"])
        if not key:
            raise ValueError("no merchant")
        sign = _sign(charge["amount_cents"])
        set_merchant_rule(conn, user_id, key, sign, kind, category, int(bool(one_off)))
        _give_way(conn, user_id, transaction_id)
        # decisions carried onto this merchant's other rows from another wording give way to its own rule too
        carried = conn.execute(
            "SELECT o.transaction_id, t.description, t.amount_cents FROM overrides o"
            " JOIN transactions t ON t.id = o.transaction_id"
            " WHERE o.user_id = ? AND o.carried_key IS NOT NULL AND t.superseded_by IS NULL", (user_id,)).fetchall()
        for row in carried:
            if _sign(row["amount_cents"]) == sign and merchant_key(row["description"]) == key:
                _give_way(conn, user_id, row["transaction_id"])
        # and rows this merchant's earlier decision was carried to follow the new one
        conn.execute(
            "UPDATE overrides SET kind = ?, category = ? WHERE user_id = ? AND carried_key = ?"
            " AND transaction_id IN (SELECT id FROM transactions WHERE user_id = ? AND superseded_by IS NULL"
            f" AND amount_cents {'>' if sign > 0 else '<'} 0)", (kind, category, user_id, key, user_id))
        return count_merchant_charges(conn, user_id, key, sign)
