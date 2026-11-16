"""Taking an uploaded file into the ledger, and the fixed sentences for every way it can be refused.

Nothing here logs, and no sentence or outcome carries anything from the file, its name or a connector's
message: a refusal is a code from REASONS plus, at most, the name of an account the owner already holds.
"""
import calendar
import os
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from connectors.batch import StatementBatch, Txn, make_uids
from connectors.contract import check_batch_codes
from connectors.registry import RefusedFile, UnrecognisedFile, parse_file
from tracker.store import accept_batch, as_held_cash_kind, held_account_kind, write_tx

LOCAL_TZ = ZoneInfo(os.getenv("TZ", "America/Toronto"))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
WIDEN_LIMIT_DAYS = 45

REASONS = {
    "no_format": "This file is not in a format the tracker knows.",
    "unreadable_pdf": "This PDF could not be read.",
    "unreadable_row": "The file looks like a known format, but a row or the file name could not be read.",
    "no_transactions": "This file has no transactions in it.",
    "account_needed": "This file does not say which account it is for. Choose the account.",
    "failed_checks": "The file was read, but it failed the tracker's checks, so nothing was stored.",
    "format_version": "The file was read, but it uses a statement format version the tracker does not support.",
    "batch_kind": "The file was read, but it is neither a statement nor a list of activity.",
    "account_kind": "The file was read, but the kind of account it names is not one the tracker holds.",
    "bad_period": "The period the file covers is missing, malformed or ends before it starts.",
    "bad_amount": "An amount in the file is not a whole number of cents.",
    "bad_description": "A row in the file has no description.",
    "bad_uid": "A row in the file could not be given a stable identity.",
    "bad_date": "A row in the file has a date that could not be read.",
    "outside_period": "A row in the file is dated outside the period the file says it covers.",
    "duplicate_uid": "The file lists the same row twice with the same identity.",
    "missing_balance": "A statement must state its opening and closing balances, and this one does not.",
    "balance_mismatch": "The statement does not balance: its opening balance plus its transactions is not its closing balance.",
    "wrong_account": "This file is for a different account than the one chosen.",
    "signs_look_reversed": "Most rows in this card export are money in. Charges may be shown as positive numbers. Say whether to flip the signs.",
    "too_large": "This file is larger than 10 MB, the most the tracker takes.",
    "not_taken": "This is an investment account or one in another currency. The tracker does not take those yet.",
    "kind_mismatch": "This file is for a kind of account different from the kind already held under that account.",
    "statement_exists": "This account already has a different statement for this period.",
}


@dataclass
class UploadOutcome:
    ok: bool
    code: str  # "ok", or a key of REASONS
    batches: list = field(default_factory=list)
    needs: dict | None = None
    reason: str = ""


class _Abort(Exception):
    def __init__(self, outcome: UploadOutcome):
        self.outcome = outcome


def _refusal(code: str, needs: dict | None = None, reason_code: str | None = None) -> UploadOutcome:
    return UploadOutcome(False, code, [], needs, REASONS[reason_code or code])


def _last_day(day: str) -> str:
    return f"{day[:7]}-{calendar.monthrange(int(day[:4]), int(day[5:7]))[1]:02d}"


def _summary(conn: sqlite3.Connection, user_id: int, batch_id: int, **over) -> dict:
    row = conn.execute(
        "SELECT b.id, a.key, a.name, b.kind, b.period_start, b.period_end FROM batches b"
        " JOIN accounts a ON a.id = b.account_id AND a.user_id = b.user_id WHERE b.user_id = ? AND b.id = ?",
        (user_id, batch_id)).fetchone()
    if row is None:
        raise LookupError("no such batch")
    live = conn.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ? AND batch_id = ? AND superseded_by IS NULL",
                        (user_id, batch_id)).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ? AND batch_id = ?",
                         (user_id, batch_id)).fetchone()[0]
    out = {"id": row["id"], "account": row["key"], "account_name": row["name"], "kind": row["kind"],
           "period_start": row["period_start"], "period_end": row["period_end"], "status": "accepted",
           "added": live, "already_held": total - live, "confirmed": 0, "differences": [], "message": "",
           "can_widen": row["kind"] == "activity" and (row["period_start"][8:] != "01"
                                                       or row["period_end"] != _last_day(row["period_end"]))}
    out.update(over)
    return out


def _flipped(batch: StatementBatch) -> StatementBatch:
    rows = [(t.date, -t.amount_cents, t.description) for t in batch.transactions]
    uids = make_uids(batch.account.key, rows)
    return replace(batch, transactions=tuple(Txn(d, a, s, u) for (d, a, s), u in zip(rows, uids)))


def _looks_reversed(batch: StatementBatch) -> bool:
    money_in = sum(1 for t in batch.transactions if t.amount_cents > 0)
    return money_in * 2 > len(batch.transactions)


def take_upload(conn: sqlite3.Connection, user_id: int, filename: str, data: bytes, *,
                account_key: str | None = None, signs: str | None = None) -> UploadOutcome:
    if signs not in (None, "as_is", "flip"):
        raise ValueError("signs must be as_is or flip")
    held_kind = held_account_kind(conn, user_id, account_key) if account_key else None
    try:
        batches = parse_file(filename, data, account_key, held_kind)
    except RefusedFile as exc:
        return _refusal("failed_checks", reason_code=(exc.problem_codes or ["failed_checks"])[0])
    except UnrecognisedFile as exc:
        code = exc.code if exc.code in REASONS else "no_format"
        return _refusal(code, {"choose_account": True} if code == "account_needed" else None)

    batches = [as_held_cash_kind(conn, user_id, batch) for batch in batches]
    if account_key is not None:
        for batch in batches:
            if batch.account.key != account_key:  # a connector that names its own account named another
                held = conn.execute("SELECT name FROM accounts WHERE user_id = ? AND key = ?",
                                    (user_id, batch.account.key)).fetchone()
                # an account not held is named by its connector, never by a name derived from the file
                return _refusal("wrong_account", {"file_is_for": held["name"] if held else batch.connector})

    try:
        with write_tx(conn):  # all the file's batches are stored, or none
            summaries = []
            for batch in batches:
                summaries.append(_take_batch(conn, user_id, batch, data, filename, signs))
    except _Abort as stop:
        return stop.outcome
    return UploadOutcome(True, "ok", summaries)


def _take_batch(conn, user_id: int, batch: StatementBatch, raw: bytes, filename: str, signs: str | None) -> dict:
    key = batch.account.key
    held = conn.execute("SELECT kind, flip_sign FROM accounts WHERE user_id = ? AND key = ?", (user_id, key)).fetchone()
    if held is not None and held["kind"] != batch.account.kind:
        raise _Abort(_refusal("kind_mismatch"))
    flip_now = unflip_now = False
    if batch.kind == "activity" and batch.account.kind == "card":  # signs are only ever a card question
        flipped_before = bool(held is not None and held["flip_sign"])
        if signs == "as_is":
            unflip_now = flipped_before  # the owner's way to undo a wrong answer
        elif signs == "flip" or flipped_before:
            batch, flip_now = _flipped(batch), signs == "flip" and not flipped_before
        elif _looks_reversed(batch):
            raise _Abort(_refusal("signs_look_reversed", {"choose_signs": True}))
    result = accept_batch(conn, user_id, batch, raw, filename, in_transaction=True)
    if result.status == "refused":
        if result.code in ("statement_exists", "kind_mismatch"):
            raise _Abort(_refusal(result.code))
        codes = check_batch_codes(batch)  # the only other refusal is check_batch's
        raise _Abort(_refusal("failed_checks", reason_code=codes[0] if codes else "failed_checks"))
    if result.status == "accepted" and (flip_now or unflip_now):  # a duplicate changes nothing
        conn.execute("UPDATE accounts SET flip_sign = ? WHERE user_id = ? AND key = ?",
                     (1 if flip_now else 0, user_id, key))
    return _summary(conn, user_id, result.batch_id, status=result.status, added=result.added,
                    already_held=result.already_held, confirmed=result.confirmed,
                    differences=list(result.differences), message=result.message)


class PeriodRefused(Exception):
    """The period change is not allowed; the message is a fixed sentence."""


def _valid_day(value) -> date:
    try:
        parsed = date.fromisoformat(value) if type(value) is str else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise PeriodRefused("The period must be two dates written like 2026-03-31.")
    return parsed


def widen_period(conn: sqlite3.Connection, user_id: int, batch_id: int, period_start, period_end) -> dict:
    """State that an activity export covers a wider period. LookupError when the batch is not this user's."""
    new_start, new_end = _valid_day(period_start), _valid_day(period_end)
    with write_tx(conn):
        row = conn.execute("SELECT kind, period_start, period_end, received_at FROM batches"
                           " WHERE user_id = ? AND id = ?", (user_id, batch_id)).fetchone()
        if row is None:
            raise LookupError("no such batch")
        if row["kind"] != "activity":
            raise PeriodRefused("Only the period of an export of activity can be changed, not a statement's.")
        if new_start > new_end:
            raise PeriodRefused("The period ends before it starts.")
        if period_start > row["period_start"] or period_end < row["period_end"]:
            raise PeriodRefused("The period can only be widened, not made shorter.")
        received = datetime.fromisoformat(row["received_at"]).astimezone(LOCAL_TZ).date()
        if new_end > received:
            raise PeriodRefused("The period cannot end after the day this file was uploaded.")
        span = conn.execute("SELECT MIN(date), MAX(date) FROM transactions WHERE user_id = ? AND batch_id = ?",
                            (user_id, batch_id)).fetchone()
        if span[0] is None:  # every row was already held, so none is stored: the bound is from the batch's period
            span = (row["period_start"], row["period_end"])
        if (new_start < date.fromisoformat(span[0]) - timedelta(days=WIDEN_LIMIT_DAYS)
                or new_end > date.fromisoformat(span[1]) + timedelta(days=WIDEN_LIMIT_DAYS)):
            raise PeriodRefused("The period cannot reach more than forty-five days beyond the rows in the file.")
        conn.execute("UPDATE batches SET period_start = ?, period_end = ? WHERE user_id = ? AND id = ?",
                     (period_start, period_end, user_id, batch_id))
        return _summary(conn, user_id, batch_id)
