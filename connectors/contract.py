"""Checks that a StatementBatch honours the connector format."""
from datetime import date

from connectors.batch import FORMAT_VERSION, StatementBatch

BATCH_KINDS = ("statement", "activity")
ACCOUNT_KINDS = ("chequing", "card", "savings", "investment")


def _parse(value):
    """The date, only for a canonical ISO YYYY-MM-DD string (the tracker compares dates as text)."""
    if type(value) is not str:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _text(value) -> bool:
    return type(value) is str and value != ""


def _violations(batch: StatementBatch) -> list[tuple[str, str]]:
    """(code, human-readable message) for every violation, in a fixed order; empty when the batch is valid."""
    problems: list[tuple[str, str]] = []
    if batch.format_version != FORMAT_VERSION:
        problems.append(("format_version",
                         f"unsupported format version {batch.format_version}, expected {FORMAT_VERSION}"))
    if batch.kind not in BATCH_KINDS:
        problems.append(("batch_kind", f"batch kind {batch.kind!r} must be one of {BATCH_KINDS}"))
    if batch.account.kind not in ACCOUNT_KINDS:
        problems.append(("account_kind", f"account kind {batch.account.kind!r} must be one of {ACCOUNT_KINDS}"))

    start, end = _parse(batch.period_start), _parse(batch.period_end)
    if start is None:
        problems.append(("bad_period", f"period_start {batch.period_start!r} is not an ISO date"))
    if end is None:
        problems.append(("bad_period", f"period_end {batch.period_end!r} is not an ISO date"))
    if start and end and start > end:
        problems.append(("bad_period", "period starts after it ends"))
    for name in ("opening_cents", "closing_cents"):
        value = getattr(batch, name)
        if value is not None and type(value) is not int:
            problems.append(("bad_amount", f"{name} must be whole cents (an int) or absent"))
    for t in batch.transactions:
        if type(t.amount_cents) is not int:
            problems.append(("bad_amount", f"transaction {t.uid} amount must be whole cents (an int)"))
        if not _text(t.description):
            problems.append(("bad_description", f"transaction {t.uid} description must be non-empty text"))
        if not _text(t.uid):
            problems.append(("bad_uid", "a transaction uid must be non-empty text"))
        d = _parse(t.date)
        if d is None:
            problems.append(("bad_date", f"transaction {t.uid} has a bad date {t.date!r}"))
        elif start and end and not (start <= d <= end):
            problems.append(("outside_period", f"transaction {t.uid} on {t.date} is outside the period"))

    uids = [t.uid for t in batch.transactions]
    if len(set(uids)) != len(uids):
        problems.append(("duplicate_uid", "duplicate uid among transactions"))

    if batch.kind == "statement" and (batch.opening_cents is None or batch.closing_cents is None):
        problems.append(("missing_balance", "a statement must carry both opening and closing balance"))
    amounts_are_cents = all(type(t.amount_cents) is int for t in batch.transactions)
    if type(batch.opening_cents) is int and type(batch.closing_cents) is int and amounts_are_cents:
        total = sum(t.amount_cents for t in batch.transactions)
        if batch.opening_cents + total != batch.closing_cents:
            problems.append(("balance_mismatch",
                             f"balance mismatch: opening {batch.opening_cents} + transactions {total} "
                             f"!= closing {batch.closing_cents}"))
    return problems


def check_batch(batch: StatementBatch) -> list[str]:
    """Return human-readable violations; empty when the batch is valid."""
    return [message for _, message in _violations(batch)]


def check_batch_codes(batch: StatementBatch) -> list[str]:
    """The same violations as check_batch, in the same order, as fixed codes that quote nothing from the batch."""
    return [code for code, _ in _violations(batch)]
