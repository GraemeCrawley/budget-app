"""Classification rules, stored as data in the ledger database."""
import re
import sqlite3
from dataclasses import dataclass, fields
from typing import Optional

from tracker.store import write_tx

OWNER_FIRST = 5       # in-app owner rules run ahead of every built-in rule
OWNER_CARRIED = 500   # merchants carried over by the command line run after the seed's kind rules

KINDS = ("spending", "income", "transfer", "saving", "bucket", "offset")

_SEED_DEFAULTS = dict(priority=100, pattern="", account_key=None, sign=None, min_cents=None, max_cents=None,
                      date_from=None, date_to=None, category="", one_off=0)


@dataclass
class Rule:
    id: Optional[int]
    priority: int
    pattern: str
    account_key: Optional[str]
    sign: Optional[int]
    min_cents: Optional[int]
    max_cents: Optional[int]
    date_from: Optional[str]
    date_to: Optional[str]
    kind: str
    category: str
    one_off: int
    origin: str
    label: str
    merchant_key: Optional[str] = None


_COLUMNS = [f.name for f in fields(Rule) if f.name != "id"]


def _validate(rule: Rule) -> None:
    if rule.kind not in KINDS:
        raise ValueError(f"rule {rule.label!r}: kind {rule.kind!r} is not one of {', '.join(KINDS)}")
    try:
        re.compile(rule.pattern, re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"rule {rule.label!r}: invalid pattern {rule.pattern!r}: {exc}") from exc


def _insert(conn: sqlite3.Connection, user_id: int, rule: Rule) -> int:
    cur = conn.execute(
        f"INSERT INTO rules (user_id, {', '.join(_COLUMNS)}) VALUES (?{', ?' * len(_COLUMNS)})",
        (user_id, *(getattr(rule, c) for c in _COLUMNS)))
    return cur.lastrowid


def load_rules(conn: sqlite3.Connection, user_id: int) -> list[Rule]:
    rows = conn.execute(
        f"SELECT id, {', '.join(_COLUMNS)} FROM rules WHERE user_id = ? ORDER BY priority, id", (user_id,))
    return [Rule(**dict(r)) for r in rows]


def add_rule(conn: sqlite3.Connection, user_id: int, rule: Rule) -> int:
    _validate(rule)
    with conn:
        return _insert(conn, user_id, rule)


def set_category(conn: sqlite3.Connection, user_id: int, rule_id: int, category: str) -> None:
    with conn:
        conn.execute("UPDATE rules SET category = ? WHERE user_id = ? AND id = ?", (category, user_id, rule_id))


def seed_rules(conn: sqlite3.Connection, user_id: int, rules: list[dict]) -> int:
    """Replace the user's seed rules with the given ones. Owner rules are untouched."""
    built = [Rule(id=None, **{**_SEED_DEFAULTS, **r, "origin": "seed"}) for r in rules]
    for rule in built:
        _validate(rule)
    with conn:
        conn.execute("DELETE FROM rules WHERE user_id = ? AND origin = 'seed'", (user_id,))
        for rule in built:
            _insert(conn, user_id, rule)
    return len(built)


def set_merchant_rule(conn: sqlite3.Connection, user_id: int, key: str, sign: int, kind: str, category: str,
                      one_off: int = 0, priority: int = OWNER_FIRST) -> int:
    """The owner's one rule for (merchant_key, sign, priority): insert it, or update the held one. Returns its id.

    Keyed on priority too, so a rule carried over by the command line (OWNER_CARRIED) and one made in the app
    (OWNER_FIRST) for the same merchant are separate rules and neither writer overwrites the other's.
    """
    if not key:
        raise ValueError("a merchant rule needs a merchant key")
    if sign not in (-1, 1) or type(sign) is not int:
        raise ValueError("a merchant rule's sign must be -1 or 1")
    if kind not in KINDS:
        raise ValueError(f"kind {kind!r} is not one of {', '.join(KINDS)}")

    def write() -> int:
        held = conn.execute(
            "SELECT id FROM rules WHERE user_id = ? AND origin = 'owner' AND merchant_key = ? AND sign = ?"
            " AND priority = ? ORDER BY id", (user_id, key, sign, priority)).fetchone()
        if held:
            conn.execute("UPDATE rules SET kind = ?, category = ?, one_off = ?, label = ?"
                         " WHERE id = ? AND user_id = ?", (kind, category, one_off, f"you said {key}", held["id"], user_id))
            return held["id"]
        return _insert(conn, user_id, Rule(
            id=None, priority=priority, pattern="", account_key=None, sign=sign, min_cents=None, max_cents=None,
            date_from=None, date_to=None, kind=kind, category=category, one_off=one_off, origin="owner",
            label=f"you said {key}", merchant_key=key))

    if conn.in_transaction:
        return write()
    with write_tx(conn):
        return write()
