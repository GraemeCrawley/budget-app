"""Wealthsimple cash account monthly statement CSV."""
import calendar
import csv
import io
import re
from datetime import date

from connectors.batch import FORMAT_VERSION, AccountRef, StatementBatch, Txn, make_uids
from connectors.parsing import NotTaken, cents

NAME = "wealthsimple_cash"
VERSION = 1

_HEADER = ["date", "transaction", "description", "amount", "balance", "currency"]
_UPLOAD_PREFIX = re.compile(r"^[A-Za-z0-9]+-")
# the newer file names: <account name>-monthly-statement-transactions-<account number>-<date>.csv, and from
# a download of everything at once, <account name>-<date>-monthly-statement-transactions-<account number>.csv
_HYPHENATED = re.compile(r"^(.+?)(?:-\d{4}-\d{2}-\d{2})?-monthly-statement-transactions-", re.IGNORECASE)
# Rows only an investment account has. Its trades are neither spending nor income, so it is not taken as cash.
_INVESTMENT_TYPES = {"BUY", "SELL", "DIV", "STKDIV", "NRT", "CRYPTORWD"}


def sniff(filename: str, text: str) -> bool:
    first = text.lstrip("﻿").split("\n", 1)[0]
    try:
        fields = next(csv.reader([first]), [])
    except csv.Error:
        return False
    return [f.strip().lower() for f in fields] == _HEADER


def _account_name(filename: str) -> str:
    base = filename.rsplit("/", 1)[-1]
    m = _HYPHENATED.match(base)
    if m:  # the name is everything before the marker; no upload prefix is cut, the name may be one word
        return m.group(1).replace("_", " ").strip()
    head = base.lower().split("monthlystatement", 1)
    if len(head) < 2:
        raise ValueError(f"cannot find the account name in filename {filename!r}")
    return _UPLOAD_PREFIX.sub("", base[: len(head[0])], count=1).replace("_", " ").strip()


def parse(filename: str, text: str) -> list[StatementBatch]:
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if not rows:
        return []
    if any(r["currency"].strip().upper() != "CAD" or r["transaction"].strip().upper() in _INVESTMENT_TYPES
           for r in rows):
        raise NotTaken("an investment account, or one in another currency")
    name = _account_name(filename)
    key = "wealthsimple-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    parsed = [(date.fromisoformat(r["date"].strip()).isoformat(), cents(r["amount"]), r["description"].strip(), cents(r["balance"]))
              for r in rows]
    uids = make_uids(key, [(d, a, desc) for d, a, desc, _ in parsed])
    first = parsed[0][0]
    year, month = int(first[:4]), int(first[5:7])
    last_day = calendar.monthrange(year, month)[1]
    return [StatementBatch(
        format_version=FORMAT_VERSION,
        connector=NAME,
        connector_version=VERSION,
        account=AccountRef(key=key, name=name, kind="savings", institution="Wealthsimple"),
        kind="statement",
        period_start=f"{year:04d}-{month:02d}-01",
        period_end=f"{year:04d}-{month:02d}-{last_day:02d}",
        opening_cents=parsed[0][3] - parsed[0][1],
        closing_cents=parsed[-1][3],
        transactions=tuple(Txn(d, a, desc, u) for (d, a, desc, _), u in zip(parsed, uids)),
    )]
