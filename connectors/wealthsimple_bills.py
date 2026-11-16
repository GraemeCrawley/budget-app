"""Wealthsimple Bills chequing statement, as text from `pdftotext -layout`."""
import re
from datetime import date

from connectors.batch import FORMAT_VERSION, AccountRef, StatementBatch, Txn, make_uids
from connectors.parsing import cents

NAME = "wealthsimple_bills"
VERSION = 1

_TXN = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+\d{4}-\d{2}-\d{2}\s+(.+?)\s+([–−-]?\$[\d,]+\.\d{2})\s+(\$[\d,]+\.\d{2})$")


def _matches(text: str):
    return [m for m in (_TXN.match(ln.strip()) for ln in text.splitlines()) if m]


def sniff(filename: str, text: str) -> bool:
    return "Wealthsimple" in text and bool(_matches(text))


def parse(filename: str, text: str) -> list[StatementBatch]:
    key = "wealthsimple-bills"
    rows = []
    previous = None
    opening = None
    for m in _matches(text):
        when = date.fromisoformat(m.group(1))
        amount, balance = cents(m.group(3)), cents(m.group(4))
        if previous is None:
            opening = balance - amount
        elif previous + amount != balance:
            raise ValueError("a running balance does not follow from the previous balance and amount")
        previous = balance
        rows.append((when.isoformat(), amount, " ".join(m.group(2).split())))
    if not rows:
        raise ValueError("no transactions found")

    first = date.fromisoformat(rows[0][0])
    start = first.replace(day=1)
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    end = date.fromordinal(nxt.toordinal() - 1)
    uids = make_uids(key, rows)
    return [StatementBatch(
        format_version=FORMAT_VERSION,
        connector=NAME,
        connector_version=VERSION,
        account=AccountRef(key, "Wealthsimple Bills", "chequing", "Wealthsimple"),
        kind="statement",
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        opening_cents=opening,
        closing_cents=previous,
        transactions=tuple(Txn(d, a, desc, u) for (d, a, desc), u in zip(rows, uids)),
    )]
