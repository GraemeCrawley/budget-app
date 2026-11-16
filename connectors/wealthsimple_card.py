"""Wealthsimple credit card statement-transactions CSV.

The file lists charges as positive amounts and states no balances, so it is taken as card activity
with the signs turned round: a charge is money out.

The file does not state its period. The card's statement runs from the 15th of one month to the 14th
of the next, and the file is named for the month it ends in, so the period is taken from the name and
stretched to hold every row. A file with no date in its name covers just the span of its rows.
"""
import csv
import io
import re
from datetime import date

from connectors.batch import FORMAT_VERSION, AccountRef, StatementBatch, Txn, make_uids
from connectors.parsing import NotTaken, cents

NAME = "wealthsimple_card"
VERSION = 1
KEY = "wealthsimple-credit-card"

# the date sits after the marker in a single download and before it in a download of everything at once
_NAMED_MONTH = re.compile(r"statement-transactions-(\d{4})-(\d{2})-\d{2}|(\d{4})-(\d{2})-\d{2}-credit-card-statement-transactions")
CYCLE_START_DAY, CYCLE_END_DAY = 15, 14

_HEADER = ["transaction_date", "post_date", "type", "details", "amount", "currency"]


def sniff(filename: str, text: str) -> bool:
    first = text.lstrip("﻿").split("\n", 1)[0]
    try:
        fields = next(csv.reader([first]), [])
    except csv.Error:
        return False
    return [f.strip().lower() for f in fields] == _HEADER


def parse(filename: str, text: str) -> list[StatementBatch]:
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if not rows:
        return []
    if any(r["currency"].strip().upper() != "CAD" for r in rows):
        raise NotTaken("a card in another currency")
    parsed = [(date.fromisoformat(r["transaction_date"].strip()).isoformat(), -cents(r["amount"]),
               r["details"].strip() or r["type"].strip()) for r in rows]
    uids = make_uids(KEY, parsed)
    days = [d for d, _, _ in parsed]
    start, end = min(days), max(days)
    named = _NAMED_MONTH.search(filename)
    if named and 1 <= int(named.group(2) or named.group(4)) <= 12:
        year, month = int(named.group(1) or named.group(3)), int(named.group(2) or named.group(4))
        before = (year - 1, 12) if month == 1 else (year, month - 1)
        start = min(start, f"{before[0]:04d}-{before[1]:02d}-{CYCLE_START_DAY:02d}")
        end = max(end, f"{year:04d}-{month:02d}-{CYCLE_END_DAY:02d}")
    return [StatementBatch(
        format_version=FORMAT_VERSION,
        connector=NAME,
        connector_version=VERSION,
        account=AccountRef(key=KEY, name="Wealthsimple credit card", kind="card", institution="Wealthsimple"),
        kind="activity",
        period_start=start,
        period_end=end,
        opening_cents=None,
        closing_cents=None,
        transactions=tuple(Txn(d, a, desc, u) for (d, a, desc), u in zip(parsed, uids)),
    )]
