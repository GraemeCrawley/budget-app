"""Generic activity CSV: any bank's "download transactions" file with a header row.

Column detection is adapted from the retired upload page; amounts are integer cents.
"""
import csv
import io
from datetime import datetime

from connectors import wealthsimple_cash
from connectors.batch import FORMAT_VERSION, AccountRef, StatementBatch, Txn, make_uids
from connectors.parsing import ReadableError, cents

NAME = "generic_csv"
VERSION = 1
NO_DESCRIPTION = "(no description)"  # the contract needs non-empty text
NEEDS_ACCOUNT = True  # the file does not say which account it is; the caller must

_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y", "%Y/%m/%d", "%d-%b-%Y"]
_DATE_KEYS = ("date", "posted", "transaction date")
_DESC_KEYS = ("description", "details", "memo", "payee", "narrative")
_AMT_KEYS = ("amount", "value")
_DEBIT_KEYS = ("debit", "withdrawal", "out")
_CREDIT_KEYS = ("credit", "deposit", "in")


def _find(header, keys):
    # short keys such as "in" and "out" must match a whole heading, not part of a word
    for i, h in enumerate(header):
        hl = h.strip().lower()
        if any(hl == k or (len(k) > 3 and k in hl) for k in keys):
            return i
    return None


def _detect(header):
    """Column indices for a header row; None where a column is absent."""
    date_c = _find(header, _DATE_KEYS)
    amt_c = _find(header, _AMT_KEYS)
    deb_c = _find(header, _DEBIT_KEYS)
    cred_c = _find(header, _CREDIT_KEYS)
    if amt_c is not None and amt_c in (deb_c, cred_c):
        deb_c = cred_c = None
    if deb_c is not None and cred_c is not None:
        amt_c = None
    return {"date": date_c, "desc": _find(header, _DESC_KEYS),
            "amount": amt_c, "debit": deb_c, "credit": cred_c}


def _usable(cols) -> bool:
    if cols["date"] is None:
        return False
    if cols["amount"] is not None:
        return cols["amount"] != cols["date"]
    return None not in (cols["debit"], cols["credit"]) and cols["debit"] != cols["credit"]


def _read(text: str):
    """(header, data rows) with blank rows dropped; raises csv.Error on text that is not CSV."""
    rows = [r for r in csv.reader(io.StringIO(text.lstrip("﻿"))) if any(c.strip() for c in r)]
    return (rows[0], rows[1:]) if rows else ([], [])


def sniff(filename: str, text: str) -> bool:
    if wealthsimple_cash.sniff(filename, text):
        return False
    try:
        header, rows = _read(text)
    except csv.Error:
        return False
    return len(header) >= 2 and bool(rows) and _usable(_detect(header))


def _money(value: str) -> int:
    value = value.strip()
    if value.startswith("+"):
        value = value[1:]
    try:
        return cents(value)
    except ValueError:
        raise ReadableError("a row has an amount that could not be read") from None


def _dates(raw: list[str]) -> list[str]:
    """ISO dates for every row, in the one format that reads them all."""
    readings = []
    for fmt in _DATE_FORMATS:
        try:
            readings.append([datetime.strptime(v.strip(), fmt).date().isoformat() for v in raw])
        except ValueError:
            continue
    if not readings:
        raise ReadableError("the dates in this file could not be read")
    if any(r != readings[0] for r in readings[1:]):
        raise ReadableError("the dates in this file could be day-first or month-first; "
                            "re-export them in a form that is not ambiguous")
    return readings[0]


def _amount(r, cols) -> int:
    if cols["amount"] is not None:
        if not r[cols["amount"]].strip():
            raise ReadableError("a row has no amount")
        return _money(r[cols["amount"]])
    debit, credit = r[cols["debit"]].strip(), r[cols["credit"]].strip()
    if not debit and not credit:
        raise ReadableError("a row has no amount")
    return (_money(credit) if credit else 0) - (_money(debit) if debit else 0)


def parse(filename: str, text: str, account_key: str | None = None,
          account_kind: str | None = None) -> list[StatementBatch]:
    if account_key is None:
        raise ReadableError("choose an account for this file")
    if account_kind is None:
        raise ReadableError("choose the kind of account for this file")
    try:
        header, rows = _read(text)
    except csv.Error:
        raise ReadableError("the file could not be read as CSV") from None
    cols = _detect(header)
    if not rows:
        return []
    width = max(i for i in cols.values() if i is not None) + 1
    if any(len(r) < width for r in rows):
        raise ReadableError("a row has too few columns")
    days = _dates([r[cols["date"]] for r in rows])
    parsed = [(day, _amount(r, cols), (r[cols["desc"]].strip() if cols["desc"] is not None else "") or NO_DESCRIPTION)
              for day, r in zip(days, rows)]
    uids = make_uids(account_key, parsed)
    return [StatementBatch(
        format_version=FORMAT_VERSION,
        connector=NAME,
        connector_version=VERSION,
        account=AccountRef(key=account_key, name=account_key, kind=account_kind, institution=""),
        kind="activity",
        period_start=min(days),
        period_end=max(days),
        opening_cents=None,
        closing_cents=None,
        transactions=tuple(Txn(d, a, desc, u) for (d, a, desc), u in zip(parsed, uids)),
    )]
