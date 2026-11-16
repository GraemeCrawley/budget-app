"""Amex card statement, as text from `pdftotext -layout`."""
import re
from datetime import date, timedelta

from connectors.batch import FORMAT_VERSION, AccountRef, StatementBatch, Txn, make_uids
from connectors.parsing import MONTHS, cents

NAME = "amex"
VERSION = 1

_TXN = re.compile(r"^\s*([A-Z][a-z]{2})\s+(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+(.+?)\s+(-?[\d,]+\.\d{2})\s*$")
_DATE = r"([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})"
_PERIOD = re.compile(r"Opening Date\s+Closing Date[^\n]*\n[^\n]*?" + _DATE + r"\s+" + _DATE)
_PREVIOUS = re.compile(r"Previous Balance\s+\$?(-?[\d,]+\.\d{2})")
_NEW = re.compile(r"New Balance\s+\$?(-?[\d,]+\.\d{2})")
_END_MARKERS = ("About Your Credit Limit", "Total of Account Activity",
                "Interest Charge Calculation", "Calculating Your Balance")


def sniff(filename: str, text: str) -> bool:
    return "Your Transactions" in text and "Closing Date" in text


def _period(text: str) -> tuple[str, str, int, int, int]:
    m = _PERIOD.search(text)
    if not m:
        raise ValueError("no opening and closing date found")
    om, od, oy, cm, cd, cy = m.groups()
    if om not in MONTHS or cm not in MONTHS:
        raise ValueError("unreadable opening or closing date")
    start = f"{int(oy):04d}-{MONTHS[om]:02d}-{int(od):02d}"
    end = f"{int(cy):04d}-{MONTHS[cm]:02d}-{int(cd):02d}"
    return start, end, int(oy), int(cy), MONTHS[cm]


def parse(filename: str, text: str) -> list[StatementBatch]:
    key = "amex-cobalt"
    start, end, open_year, close_year, close_month = _period(text)

    start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
    prev = _PREVIOUS.search(text)
    if not prev:
        raise ValueError("no previous balance found")
    new = _NEW.search(text)
    if not new:
        raise ValueError("no new balance found")

    lines = text.splitlines()
    first = next((i for i, ln in enumerate(lines) if ln.strip() == "Your Transactions"), None)
    if first is None:
        raise ValueError("no transactions section found")
    last = next((i for i in range(first + 1, len(lines)) if any(mk in lines[i] for mk in _END_MARKERS)),
                len(lines))

    rows = []
    for ln in lines[first:last]:
        m = _TXN.match(ln)
        if not m or m.group(1) not in MONTHS:
            continue
        month, day = MONTHS[m.group(1)], int(m.group(2))
        year = close_year if month == close_month else open_year
        try:
            when = date(year, month, day)
            if when > end_date:
                when = date(year - 1, month, day)  # a December charge on a statement that opens in January
        except ValueError:
            raise ValueError("a transaction has an impossible date") from None
        if not start_date - timedelta(days=31) <= when <= end_date:
            raise ValueError("a transaction is dated outside the statement period")
        rows.append((when.isoformat(), -cents(m.group(6)), " ".join(m.group(5).split())))

    # A charge can be dated a day or two before the statement opens (it posts after); widen the period to cover it.
    start = min([start] + [d for d, _, _ in rows])
    uids = make_uids(key, rows)
    return [StatementBatch(
        format_version=FORMAT_VERSION,
        connector=NAME,
        connector_version=VERSION,
        account=AccountRef(key, "Amex Cobalt", "card", "American Express"),
        kind="statement",
        period_start=start,
        period_end=end,
        opening_cents=-cents(prev.group(1)),
        closing_cents=-cents(new.group(1)),
        transactions=tuple(Txn(d, a, desc, u) for (d, a, desc), u in zip(rows, uids)),
    )]
