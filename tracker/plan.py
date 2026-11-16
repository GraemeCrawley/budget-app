"""The plan: the savings-rate target, and a budget for any category by the month or by the year."""
import sqlite3

from tracker.store import write_tx

DEFAULT_TARGET = 0.15  # the owner's first step, set 2026-11-15
MAX_TARGET = 0.9
PERIODS = ("month", "year")
MAX_BUDGET_CENTS = 100_000_000


def target(conn: sqlite3.Connection, user_id: int) -> float:
    row = conn.execute("SELECT target FROM plan_settings WHERE user_id = ?", (user_id,)).fetchone()
    return row[0] if row else DEFAULT_TARGET


def budgets(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT category, cents, period FROM budgets WHERE user_id = ? ORDER BY category", (user_id,))]


def set_target(conn: sqlite3.Connection, user_id: int, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= MAX_TARGET:
        raise ValueError("the target is a share between 0 and 0.9")
    with write_tx(conn):
        conn.execute("INSERT INTO plan_settings (user_id, target) VALUES (?, ?)"
                     " ON CONFLICT(user_id) DO UPDATE SET target = excluded.target", (user_id, round(value, 4)))


def set_budget(conn: sqlite3.Connection, user_id: int, category: str, cents: int, period: str) -> None:
    category = category.strip()
    if not category or len(category) > 60:
        raise ValueError("a budget needs a category")
    if isinstance(cents, bool) or not isinstance(cents, int) or not 0 < cents <= MAX_BUDGET_CENTS:
        raise ValueError("a budget is an amount above zero")
    if period not in PERIODS:
        raise ValueError("a budget is by the month or by the year")
    with write_tx(conn):
        conn.execute("INSERT INTO budgets (user_id, category, cents, period) VALUES (?, ?, ?, ?)"
                     " ON CONFLICT(user_id, category) DO UPDATE SET cents = excluded.cents, period = excluded.period",
                     (user_id, category, cents, period))


def clear_budget(conn: sqlite3.Connection, user_id: int, category: str) -> None:
    with write_tx(conn):
        conn.execute("DELETE FROM budgets WHERE user_id = ? AND category = ?", (user_id, category.strip()))
