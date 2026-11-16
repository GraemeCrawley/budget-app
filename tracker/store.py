"""The ledger store: every uploaded batch is kept exactly as received."""
import hashlib
import os
import re
import sqlite3
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from connectors.batch import AccountRef, StatementBatch
from connectors.contract import check_batch
from tracker.matching import rule_matches
from tracker.merchant import merchant_key

SCHEMA = Path(__file__).with_name("schema.sql")
SCHEMA_V2 = Path(__file__).with_name("schema_v2.sql")
SCHEMA_V3 = Path(__file__).with_name("schema_v3.sql")
SCHEMA_V4 = Path(__file__).with_name("schema_v4.sql")
SCHEMA_V5 = Path(__file__).with_name("schema_v5.sql")

# The ledger's schema version, kept in PRAGMA user_version. MIGRATIONS[i] returns the SQL that takes a
# ledger from version i to i + 1; add one (and raise SCHEMA_VERSION) for every schema change.
SCHEMA_VERSION = 5
MIGRATIONS = [
    lambda: SCHEMA.read_text(),  # 0 -> 1: the first schema (its tables may already exist, unversioned)
    lambda: SCHEMA_V2.read_text(),  # 1 -> 2: corrections
    lambda: SCHEMA_V3.read_text(),  # 2 -> 3: carried overrides remember their merchant
    lambda: SCHEMA_V4.read_text(),  # 3 -> 4: phone notifications
    lambda: SCHEMA_V5.read_text(),  # 4 -> 5: the plan (target and budgets)
]


class LedgerNeedsUpgrade(Exception):
    """The ledger's schema version is not the one this code reads; a writer must open it first."""


def _version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _migrate(conn: sqlite3.Connection) -> None:
    current = _version(conn)
    if current > SCHEMA_VERSION:
        raise RuntimeError(f"the ledger is at schema version {current}, newer than this code's {SCHEMA_VERSION};"
                           " refusing to open it")
    for version in range(current, SCHEMA_VERSION):
        try:  # one transaction per step: a failing step leaves the ledger at the version before it
            conn.executescript(f"BEGIN;\n{MIGRATIONS[version]()}\nPRAGMA user_version = {version + 1};\nCOMMIT;")
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise


def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _migrate(conn)
        with conn:
            conn.execute("INSERT OR IGNORE INTO users (id, key) VALUES (1, 'owner')")
    except BaseException:
        conn.close()
        raise
    return conn


@contextmanager
def write_tx(conn: sqlite3.Connection):
    """One write transaction that takes the write lock first: commits on exit, rolls back and re-raises on error.

    It must not be entered while the connection already has an open transaction (BEGIN would fail).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def open_readonly(path: str) -> sqlite3.Connection:
    """Open an existing ledger for reading only: creates nothing, runs no schema script, cannot write.

    Raises LedgerNeedsUpgrade when the ledger's schema version is not SCHEMA_VERSION.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    if _version(conn) != SCHEMA_VERSION:
        conn.close()
        raise LedgerNeedsUpgrade(path)
    return conn


def held_account_kind(conn: sqlite3.Connection, user_id: int, key: str) -> Optional[str]:
    """The kind of the account held under this key, or None when there is none."""
    row = conn.execute("SELECT kind FROM accounts WHERE user_id = ? AND key = ?", (user_id, key)).fetchone()
    return row["kind"] if row else None


CASH_KINDS = ("chequing", "savings")


def as_held_cash_kind(conn: sqlite3.Connection, user_id: int, batch: StatementBatch) -> StatementBatch:
    """The batch, with its account's kind set to the kind already held when both are cash kinds.

    A cash statement cannot tell a chequing account from a savings one, so the kind the ledger holds wins."""
    held = held_account_kind(conn, user_id, batch.account.key)
    if held in CASH_KINDS and batch.account.kind in CASH_KINDS and held != batch.account.kind:
        return replace(batch, account=replace(batch.account, kind=held))
    return batch


def ensure_account(conn: sqlite3.Connection, user_id: int, ref: AccountRef) -> int:
    """Return the account id, creating the row on first sight.

    Never overwrites an existing name. Does not commit; the caller owns the transaction.
    """
    conn.execute(
        "INSERT OR IGNORE INTO accounts (user_id, key, name, kind, institution) VALUES (?, ?, ?, ?, ?)",
        (user_id, ref.key, ref.name, ref.kind, ref.institution),
    )
    row = conn.execute(
        "SELECT id FROM accounts WHERE user_id = ? AND key = ?", (user_id, ref.key)
    ).fetchone()
    return row["id"]


@dataclass
class AcceptResult:
    status: str  # "accepted" | "duplicate" | "refused"
    batch_id: Optional[int]
    added: int
    already_held: int
    message: str
    confirmed: int = 0
    differences: list[str] = field(default_factory=list)
    code: str = ""  # for a refusal: failed_checks | kind_mismatch | statement_exists


MATCH_WINDOW_DAYS = 3
# An unmatched charge dated after a statement's period_end - GRACE_DAYS may still post on the next one: it stays live.
GRACE_DAYS = MATCH_WINDOW_DAYS


def _insert_batch(conn, user_id: int, account_id: int, batch: StatementBatch,
                  raw: bytes, sha256: str, source_name: str) -> int:
    cur = conn.execute(
        "INSERT INTO batches (user_id, account_id, connector, connector_version, format_version, kind,"
        " period_start, period_end, opening_cents, closing_cents, source_name, sha256, raw, received_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, account_id, batch.connector, batch.connector_version, batch.format_version, batch.kind,
         batch.period_start, batch.period_end, batch.opening_cents, batch.closing_cents,
         source_name, sha256, raw, datetime.now(timezone.utc).isoformat()),
    )
    return cur.lastrowid


def _gap(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def _shift(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def _pair_most(rows, targets, allowed) -> dict:
    """Pair rows with targets of the same amount at most MATCH_WINDOW_DAYS apart, where allowed(row, target).

    rows and targets are tuples starting (key, date, amount_cents, order). Within each amount the pairing
    has the most pairs; among those, the smallest total date gap; remaining ties go to earlier dates (the
    earliest row pairs with the earliest target it can). With one window for every pair an order-preserving
    pairing is optimal, so a dynamic programme over the two date-sorted lists finds it.
    Returns {row key: target tuple}.
    """
    by_amount = {}
    for t in targets:
        by_amount.setdefault(t[2], ([], []))[1].append(t)
    for r in rows:
        if r[2] in by_amount:
            by_amount[r[2]][0].append(r)
    paired = {}
    for rs, ts in by_amount.values():
        rs.sort(key=lambda x: (x[1], x[3]))
        ts.sort(key=lambda x: (x[1], x[3]))
        n, m = len(rs), len(ts)
        # best[i][j]: (pairs, -total gap) over rs[i:] and ts[j:]; step[i][j]: the choice made there
        best = [[(0, 0)] * (m + 1) for _ in range(n + 1)]
        step = [[None] * (m + 1) for _ in range(n + 1)]
        for i in range(n - 1, -1, -1):
            for j in range(m - 1, -1, -1):
                options = []  # in tie-break order: pair, then skip the target, then skip the row
                gap = _gap(rs[i][1], ts[j][1])
                if gap <= MATCH_WINDOW_DAYS and allowed(rs[i], ts[j]):
                    after = best[i + 1][j + 1]
                    options.append(((after[0] + 1, after[1] - gap), "pair"))
                options.append((best[i][j + 1], "skip target"))
                options.append((best[i + 1][j], "skip row"))
                best[i][j], step[i][j] = max(options, key=lambda o: o[0])  # max keeps the first of equals
        i = j = 0
        while i < n and j < m:
            if step[i][j] == "pair":
                paired[rs[i][0]] = ts[j]
                i, j = i + 1, j + 1
            elif step[i][j] == "skip target":
                j += 1
            else:
                i += 1
    return paired


def _covers(start: str, end: str, day: str) -> bool:
    return start <= day <= end


def _held_statements(conn, user_id: int, account_id: int) -> list:
    return conn.execute(
        "SELECT id, period_start, period_end FROM batches"
        " WHERE user_id = ? AND account_id = ? AND kind = 'statement' ORDER BY period_start DESC, id DESC",
        (user_id, account_id)).fetchall()


def _kept_live(day: str, period_end: str, statements) -> bool:
    """Statement rule 3: an unmatched charge dated after period_end - GRACE_DAYS (the end day and the
    GRACE_DAYS - 1 days before it) may post on the next statement, unless a held statement starts after it."""
    return (_shift(period_end, -GRACE_DAYS) < day <= period_end
            and not any(s["period_start"] > day for s in statements))


def _insert_transactions(conn, user_id: int, account_id: int, batch_id: int,
                         batch: StatementBatch) -> tuple[int, int, list[str]]:
    """Store the batch's transactions. Returns (added, already_held, differences)."""
    if batch.kind == "statement":
        return _insert_statement_rows(conn, user_id, account_id, batch_id, batch)
    return _insert_activity_rows(conn, user_id, account_id, batch_id, batch)


def _insert_statement_rows(conn, user_id: int, account_id: int, batch_id: int,
                           batch: StatementBatch) -> tuple[int, int, list[str]]:
    added = 0
    for t in batch.transactions:
        # A provisional row with the same uid is the earlier export's copy of this purchase.
        # Move its uid aside so the statement's row can be stored; it is superseded next.
        conn.execute(
            "UPDATE transactions SET uid = uid || '~' || id"
            " WHERE user_id = ? AND account_id = ? AND uid = ? AND provisional = 1",
            (user_id, account_id, t.uid))
        uid = t.uid
        if conn.execute("SELECT 1 FROM transactions WHERE user_id = ? AND account_id = ? AND uid = ?",
                        (user_id, account_id, uid)).fetchone():
            # Same uid on another statement: a different charge (periods can share a day). Keep both.
            uid = f"{uid}~s{batch_id}"
        cur = conn.execute(
            "INSERT INTO transactions (user_id, account_id, batch_id, uid, date, amount_cents,"
            " description, provisional) VALUES (?, ?, ?, ?, ?, ?, ?, 0)"
            " ON CONFLICT(account_id, uid) DO NOTHING",  # only a held uid is skipped; any other failure raises
            (user_id, account_id, batch_id, uid, t.date, t.amount_cents, t.description),
        )
        added += cur.rowcount
    if added != len(batch.transactions):
        raise RuntimeError("a statement row was not stored; the statement is refused whole")
    return added, 0, []


def _insert_activity_rows(conn, user_id: int, account_id: int, batch_id: int,
                          batch: StatementBatch) -> tuple[int, int, list[str]]:
    """Activity rules 1-4: a held uid is skipped; a row a held statement already records is stored
    superseded (matched to the statement row it copies, or reported when that statement lacks it)."""
    added = already_held = 0
    pending = []  # (position, txn) for every row whose uid is not held (rule 1)
    for position, t in enumerate(batch.transactions):
        if conn.execute("SELECT 1 FROM transactions WHERE user_id = ? AND account_id = ? AND uid = ?",
                        (user_id, account_id, t.uid)).fetchone():
            already_held += 1
        else:
            pending.append((position, t))
    if not pending:
        return added, already_held, []

    statements = _held_statements(conn, user_id, account_id)
    first, last = min(t.date for _, t in pending), max(t.date for _, t in pending)
    unclaimed = [(r["id"], r["date"], r["amount_cents"], r["id"], r["batch_id"], r["period_end"])
                 for r in conn.execute(
        "SELECT s.id, s.date, s.amount_cents, s.batch_id, b.period_end FROM transactions s"
        " JOIN batches b ON b.id = s.batch_id AND b.user_id = s.user_id AND b.account_id = s.account_id"
        " WHERE s.user_id = ? AND s.account_id = ? AND s.provisional = 0 AND s.date BETWEEN ? AND ?"
        " AND NOT EXISTS (SELECT 1 FROM transactions m"
        "                 WHERE m.user_id = ? AND m.account_id = ? AND m.matched_id = s.id)",
        (user_id, account_id, _shift(first, -MATCH_WINDOW_DAYS), _shift(last, MATCH_WINDOW_DAYS),
         user_id, account_id))]

    def allowed(row, target):  # ruling C: across the statement's period_end only if this export covers it
        end = target[5]
        return (row[1] > end) == (target[1] > end) or _covers(batch.period_start, batch.period_end, target[1])
    matched = _pair_most([(pos, t.date, t.amount_cents, pos) for pos, t in pending], unclaimed, allowed)

    differences = []
    for position, t in pending:
        superseded_by = matched_id = None
        if position in matched:  # rule 2: a copy of a statement row
            matched_id, superseded_by = matched[position][0], matched[position][4]
        else:  # rule 3: inside a held statement that lacks it, and not in that statement's last days.
            # When several covering statements lack it, the one starting latest supersedes it (then latest id).
            lacking = next((s["id"] for s in statements if s["period_start"] <= t.date <= s["period_end"]
                            and not _kept_live(t.date, s["period_end"], statements)), None)
            if lacking is not None:
                superseded_by = lacking
                differences.append(f"only in this export: {t.date}")
        conn.execute(
            "INSERT INTO transactions (user_id, account_id, batch_id, uid, date, amount_cents,"
            " description, provisional, superseded_by, matched_id) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (user_id, account_id, batch_id, t.uid, t.date, t.amount_cents, t.description,
             superseded_by, matched_id),
        )
        if superseded_by is None:  # rule 4
            added += 1
        else:
            already_held += 1
    return added, already_held, differences


def _deciding_owner_rule(rules, row):
    """The owner merchant rule (origin 'owner', merchant_key set) that decides `row`, or None: the first of the
    user's rules (by priority, then id) to match it must be such a rule. `rules` is [(rule, compiled pattern)]."""
    key = merchant_key(row["description"])
    first = next((r for r, p in rules if rule_matches(r, p, row, key)), None)
    return first if first is not None and first.origin == "owner" and first.merchant_key else None


def _carry_owner_rule(conn, user_id: int, rules, account_key: str, candidate, statement_row) -> None:
    """Statement rule 2, continued: when the owner merchant rule that decided the export's copy does not match the
    statement's wording, keep that decision on the statement row as an override that remembers the rule's merchant.

    Nothing is carried onto a row the owner already decided by hand, or one an owner merchant rule of its own
    decides (a mispaired match would otherwise put one merchant's category on another's row). An override that
    holds only a one-off mark is filled in and keeps its mark."""
    held = conn.execute("SELECT kind, category FROM overrides WHERE user_id = ? AND transaction_id = ?",
                        (user_id, statement_row["id"])).fetchone()
    if held and (held["kind"] is not None or held["category"] is not None):
        return
    target = {**dict(statement_row), "account_key": account_key}
    if _deciding_owner_rule(rules, target) is not None:
        return
    rule = _deciding_owner_rule(rules, {**dict(candidate), "account_key": account_key})
    if rule is None:
        return
    pattern = re.compile(rule.pattern, re.IGNORECASE)
    if rule_matches(rule, pattern, target, merchant_key(statement_row["description"])):
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if held:
        conn.execute("UPDATE overrides SET kind = ?, category = ?, carried_key = ? WHERE user_id = ?"
                     " AND transaction_id = ?", (rule.kind, rule.category, rule.merchant_key, user_id,
                                                 statement_row["id"]))
    else:
        conn.execute("INSERT INTO overrides (transaction_id, user_id, kind, category, one_off, set_at, carried_key)"
                     " VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (statement_row["id"], user_id, rule.kind, rule.category, rule.one_off, now, rule.merchant_key))


def _supersede_provisional(conn, user_id: int, account_id: int,
                           batch_id: int, batch: StatementBatch) -> tuple[int, list[str]]:
    """Statement rules 1-5: let a statement confirm and replace provisional rows at and near its period.

    Candidates are the account's live provisional rows dated period_start - W to period_end + W
    (W = MATCH_WINDOW_DAYS). They are paired with this statement's rows by _pair_most: same amount, at
    most W days apart, the most pairs, then the smallest total gap, then earlier dates. A candidate dated
    after period_end pairs only with a row its own export's period covers. A paired candidate is
    superseded, gets matched_id, and its override moves to the statement row unless that row has one;
    when the statement row is then still without one, _carry_owner_rule may give it one.
    An unpaired candidate inside the period stays live when _kept_live, else it is superseded and
    reported; one before period_start is superseded and reported only when another held statement
    covers it; any other is untouched. Unpaired statement rows are reported only where a held export's
    period covers their date. Returns (confirmed, differences). Only provisional rows are superseded.
    """
    candidates = conn.execute(
        "SELECT t.id, t.date, t.amount_cents, t.description, b.period_start, b.period_end FROM transactions t"
        " JOIN batches b ON b.id = t.batch_id AND b.user_id = t.user_id AND b.account_id = t.account_id"
        " WHERE t.user_id = ? AND t.account_id = ?"
        " AND t.provisional = 1 AND t.superseded_by IS NULL AND t.date BETWEEN ? AND ?"
        " ORDER BY t.date, t.id",
        (user_id, account_id, _shift(batch.period_start, -MATCH_WINDOW_DAYS),
         _shift(batch.period_end, MATCH_WINDOW_DAYS))).fetchall()
    statement_rows = {r["id"]: r for r in conn.execute(
        "SELECT id, date, amount_cents, description FROM transactions"
        " WHERE user_id = ? AND account_id = ? AND batch_id = ? ORDER BY date, id", (user_id, account_id, batch_id))}
    rows = [(r["id"], r["date"], r["amount_cents"], r["id"]) for r in statement_rows.values()]
    rules = [(SimpleNamespace(**dict(r)), re.compile(r["pattern"], re.IGNORECASE)) for r in conn.execute(
        "SELECT * FROM rules WHERE user_id = ? ORDER BY priority, id", (user_id,))]
    end = batch.period_end

    def allowed(cand, row):  # ruling C: across period_end only if the candidate's export covers the row
        return (cand[1] > end) == (row[1] > end) or _covers(cand[4], cand[5], row[1])
    matched = _pair_most([(c["id"], c["date"], c["amount_cents"], c["id"], c["period_start"], c["period_end"])
                          for c in candidates], rows, allowed)
    statements = _held_statements(conn, user_id, account_id)

    confirmed = 0
    differences = []
    for c in candidates:
        day = c["date"]
        if c["id"] in matched:  # rule 2
            statement_row = matched[c["id"]][0]
            conn.execute("UPDATE transactions SET superseded_by = ?, matched_id = ?"
                         " WHERE user_id = ? AND account_id = ? AND id = ?",
                         (batch_id, statement_row, user_id, account_id, c["id"]))
            conn.execute(
                "UPDATE overrides SET transaction_id = ? WHERE user_id = ? AND transaction_id = ?"
                " AND NOT EXISTS (SELECT 1 FROM overrides o WHERE o.user_id = ? AND o.transaction_id = ?)",
                (statement_row, user_id, c["id"], user_id, statement_row))
            _carry_owner_rule(conn, user_id, rules, batch.account.key, c, statement_rows[statement_row])
            confirmed += 1
            continue
        if batch.period_start <= day <= batch.period_end:  # rule 3
            lacking = not _kept_live(day, batch.period_end, statements)
        else:  # rule 4
            lacking = day < batch.period_start and any(
                s["id"] != batch_id and s["period_start"] <= day <= s["period_end"] for s in statements)
        if lacking:
            conn.execute("UPDATE transactions SET superseded_by = ? WHERE user_id = ? AND account_id = ? AND id = ?",
                         (batch_id, user_id, account_id, c["id"]))
            differences.append(f"only in the earlier export: {day}")

    claimed = {t[0] for t in matched.values()}
    activity = conn.execute(
        "SELECT period_start, period_end FROM batches WHERE user_id = ? AND account_id = ? AND kind = 'activity'",
        (user_id, account_id)).fetchall()
    differences.extend(  # rule 5
        f"only in the statement: {r[1]}" for r in rows
        if r[0] not in claimed and any(a["period_start"] <= r[1] <= a["period_end"] for a in activity))
    return confirmed, differences


def _held_statement_with_same_content(conn, user_id: int, account_id: int, batch: StatementBatch):
    """Id of a held statement with the same period, balances and (date, amount) multiset, else None."""
    wanted = sorted((t.date, t.amount_cents) for t in batch.transactions)
    for b in conn.execute(
            "SELECT id FROM batches WHERE user_id = ? AND account_id = ? AND kind = 'statement'"
            " AND period_start = ? AND period_end = ? AND opening_cents IS ? AND closing_cents IS ?",
            (user_id, account_id, batch.period_start, batch.period_end,
             batch.opening_cents, batch.closing_cents)).fetchall():
        held = sorted(tuple(r) for r in conn.execute(
            "SELECT date, amount_cents FROM transactions WHERE user_id = ? AND account_id = ? AND batch_id = ?",
            (user_id, account_id, b["id"])))
        if held == wanted:
            return b["id"]
    return None


def accept_batch(conn: sqlite3.Connection, user_id: int, batch: StatementBatch,
                 raw: bytes, source_name: str, *, in_transaction: bool = False) -> AcceptResult:
    """Accept one batch. With in_transaction the caller has opened (and will commit or roll back) the
    write transaction, so several batches can be stored all together or not at all."""
    problems = check_batch(batch)
    if problems:
        return AcceptResult("refused", None, 0, 0, problems[0], code="failed_checks")
    held_kind = held_account_kind(conn, user_id, batch.account.key)
    if held_kind is not None and held_kind != batch.account.kind:
        return AcceptResult("refused", None, 0, 0,
                            f"this file is for a {batch.account.kind} account, but {batch.account.key}"
                            f" is held as a {held_kind} account", code="kind_mismatch")

    sha256 = hashlib.sha256(raw).hexdigest()
    with nullcontext() if in_transaction else write_tx(conn):  # one transaction: any failure below rolls it back
        account_id = ensure_account(conn, user_id, batch.account)
        held = conn.execute(
            "SELECT id FROM batches WHERE user_id = ? AND account_id = ? AND sha256 = ?",
            (user_id, account_id, sha256),
        ).fetchone()
        if held:
            return AcceptResult("duplicate", held["id"], 0, 0, "this file was already uploaded")
        if batch.kind == "statement":
            same = _held_statement_with_same_content(conn, user_id, account_id, batch)
            if same:
                return AcceptResult("duplicate", same, 0, 0, "this statement was already uploaded")
            if conn.execute(  # statement rule 6 (ruling D): a different statement for a held period is refused
                    "SELECT 1 FROM batches WHERE user_id = ? AND account_id = ? AND kind = 'statement'"
                    " AND period_start = ? AND period_end = ?",
                    (user_id, account_id, batch.period_start, batch.period_end)).fetchone():
                return AcceptResult("refused", None, 0, 0,
                                    "this account already has a different statement for this period",
                                    code="statement_exists")
        batch_id = _insert_batch(conn, user_id, account_id, batch, raw, sha256, source_name)
        added, already_held, differences = _insert_transactions(conn, user_id, account_id, batch_id, batch)
        confirmed = 0
        if batch.kind == "statement":
            confirmed, differences = _supersede_provisional(conn, user_id, account_id, batch_id, batch)
    return AcceptResult("accepted", batch_id, added, already_held, "", confirmed, differences)
