"""Which dates each account's held batches cover."""
import calendar
import sqlite3
from datetime import date, timedelta


def merge_ranges(ranges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Merge ranges that overlap or touch (one ends the day before the next starts); sorted."""
    merged: list[tuple[str, str]] = []
    for start, end in sorted(ranges):
        if merged:
            last_start, last_end = merged[-1]
            if date.fromisoformat(start) <= date.fromisoformat(last_end) + timedelta(days=1):
                merged[-1] = (last_start, max(last_end, end))
                continue
        merged.append((start, end))
    return merged


def coverage(conn: sqlite3.Connection, user_id: int) -> dict[str, list[tuple[str, str]]]:
    per_account: dict[str, list[tuple[str, str]]] = {}
    for row in conn.execute(
            "SELECT a.key, b.period_start, b.period_end FROM batches b JOIN accounts a ON a.id = b.account_id"
            " WHERE b.user_id = ? ORDER BY a.key, b.period_start", (user_id,)):
        per_account.setdefault(row[0], []).append((row[1], row[2]))
    return {key: merge_ranges(ranges) for key, ranges in per_account.items()}


def data_through(conn: sqlite3.Connection, user_id: int) -> dict[str, str]:
    return {key: ranges[-1][1] for key, ranges in coverage(conn, user_id).items()}


def month_is_complete(cov: dict, ym: str) -> bool:
    """Every account that existed by the end of the month has one range holding the whole month.

    An account whose coverage starts after the month ends had not been added yet and is ignored.
    An account whose coverage starts inside the month is judged from that day on: the days before its
    first file are not counted as missing. With no accounts to judge, the month is not complete.
    """
    year, month = int(ym[:4]), int(ym[5:7])
    first = f"{ym}-01"
    last = f"{ym}-{calendar.monthrange(year, month)[1]:02d}"
    judged = [ranges for ranges in cov.values() if ranges and ranges[0][0] <= last]
    if not judged:
        return False
    return all(any(start <= max(first, ranges[0][0]) and end >= last for start, end in ranges) for ranges in judged)
