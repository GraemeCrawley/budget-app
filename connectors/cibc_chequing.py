"""CIBC chequing account statement, as text from `pdftotext -layout`."""
import re

from connectors.batch import FORMAT_VERSION, AccountRef, StatementBatch, Txn, make_uids
from connectors.parsing import MONTHS, cents

NAME = "cibc_chequing"
VERSION = 1

_MONEY = re.compile(r"-?\$?[\d,]+\.\d{2}")
_PERIOD = re.compile(r"\bFor\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+to\s+([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})")
_DATE = re.compile(r"\s*([A-Z][a-z]{2})\s+(\d{1,2})\b")
_NOT_CONTINUATION = ("CIBC", "Date", "Page", "Account", "Branch", "Transaction details")


def sniff(filename: str, text: str) -> bool:
    return "Transaction details" in text and "Opening balance" in text


def _period(text: str) -> tuple[str, str, int, int, int]:
    m = _PERIOD.search(text)
    if not m:
        raise ValueError("no statement period line found")
    sm, sd, em, ed, year = m.group(1), int(m.group(2)), m.group(3), int(m.group(4)), int(m.group(5))
    if sm not in MONTHS or em not in MONTHS:
        raise ValueError("unreadable statement period")
    start_year = year - 1 if MONTHS[sm] > MONTHS[em] else year
    start = f"{start_year:04d}-{MONTHS[sm]:02d}-{sd:02d}"
    end = f"{year:04d}-{MONTHS[em]:02d}-{ed:02d}"
    return start, end, start_year, year, MONTHS[em]


def parse(filename: str, text: str) -> list[StatementBatch]:
    key = "cibc-chequing"
    start, end, start_year, end_year, end_month = _period(text)
    lines = text.splitlines()
    first = next((i for i, ln in enumerate(lines) if ln.strip().startswith("Transaction details")), None)
    if first is None:
        raise ValueError("no transaction details heading found")

    opening = None
    for ln in lines:
        if "Opening balance" in ln and _MONEY.findall(ln):
            opening = cents(_MONEY.findall(ln)[-1])
            break
    if opening is None:
        raise ValueError("no opening balance found")

    prev = opening
    closing = None
    month = int(start[5:7])
    day = int(start[8:10])
    rows: list[list] = []  # [date, amount_cents, description]
    for ln in lines[first:]:
        nums = _MONEY.findall(ln)
        if "Opening balance" in ln:
            continue
        if "Closing balance" in ln:
            if nums:
                closing = cents(nums[-1])
                break
            continue
        if len(nums) >= 2:
            dm = _DATE.match(ln)
            if dm and dm.group(1) in MONTHS:
                month, day = MONTHS[dm.group(1)], int(dm.group(2))
            amount, balance = cents(nums[-2]), cents(nums[-1])
            delta = balance - prev
            if abs(abs(delta) - amount) > 1:
                continue
            desc = ln[dm.end():] if dm and dm.group(1) in MONTHS else ln
            desc = " ".join(_MONEY.sub("", desc).split())
            year = end_year if month == end_month else start_year
            rows.append([f"{year:04d}-{month:02d}-{day:02d}", amount if delta > 0 else -amount,
                         desc or "(cibc)"])
            prev = balance
        elif not nums and ln.strip() and rows:
            cont = " ".join(ln.split())
            if not cont.startswith(_NOT_CONTINUATION):
                rows[-1][2] += " " + cont
    if closing is None:
        raise ValueError("no closing balance found")

    uids = make_uids(key, [(d, a, desc) for d, a, desc in rows])
    return [StatementBatch(
        format_version=FORMAT_VERSION,
        connector=NAME,
        connector_version=VERSION,
        account=AccountRef(key, "CIBC chequing", "chequing", "CIBC"),
        kind="statement",
        period_start=start,
        period_end=end,
        opening_cents=opening,
        closing_cents=closing,
        transactions=tuple(Txn(d, a, desc, u) for (d, a, desc), u in zip(rows, uids)),
    )]
