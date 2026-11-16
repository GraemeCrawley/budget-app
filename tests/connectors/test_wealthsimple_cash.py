from pathlib import Path
from connectors import wealthsimple_cash as ws
from connectors.contract import check_batch
import pytest

from connectors.parsing import NotTaken, cents, decode

FX = Path(__file__).parent.parent / "fixtures" / "connectors"
NAME = "abc123-Rainy_DaymonthlystatementtransactionsXX0000000CAD20260201.csv"

def test_cents():
    assert [cents(s) for s in ["1,234.56", "$1,234.56", "-12.30", "–12.30", "(12.30)", "0.05"]] == \
           [123456, 123456, -1230, -1230, -1230, 5]

def test_decode_handles_bom_and_latin1():
    assert decode("﻿a,b".encode("utf-8")) == "a,b"
    assert decode("café".encode("latin-1")) == "café"

def test_parses_one_verified_statement_batch():
    text = decode((FX / "ws_cash_monthly.csv").read_bytes())
    assert ws.sniff(NAME, text)
    (b,) = ws.parse(NAME, text)
    assert check_batch(b) == []
    assert (b.kind, b.account.key, b.account.kind) == ("statement", "wealthsimple-rainy-day", "savings")
    assert (b.opening_cents, b.closing_cents) == (10000, 11492)
    assert [t.amount_cents for t in b.transactions] == [2500, -1050, 42]
    assert (b.period_start, b.period_end) == ("2026-01-01", "2026-01-31")
    assert "0000000" not in b.account.key

def test_does_not_claim_other_files():
    assert not ws.sniff("x.csv", "Date,Description,Amount\n")

def test_dates_are_emitted_in_canonical_iso_form():
    text = decode((FX / "ws_cash_monthly.csv").read_bytes()).replace('"2026-01-', '"202601')
    (b,) = ws.parse(NAME, text)
    assert [t.date for t in b.transactions] == ["2026-01-02", "2026-01-15", "2026-01-28"]
    assert check_batch(b) == []


NEW_NAME = "Rainy_Day-monthly-statement-transactions-XX0000000CAD-2026-02-01.csv"
HEADER = '"date","transaction","description","amount","balance","currency"\n'


def test_reads_the_account_name_from_the_hyphenated_file_name():
    text = decode((FX / "ws_cash_monthly.csv").read_bytes())
    (b,) = ws.parse(NEW_NAME, text)
    assert (b.account.key, b.account.name) == ("wealthsimple-rainy-day", "Rainy Day")
    assert "0000000" not in b.account.key
    assert check_batch(b) == []


def test_a_one_word_account_name_is_kept_whole_in_the_hyphenated_form():
    text = decode((FX / "ws_cash_monthly.csv").read_bytes())
    (b,) = ws.parse("Bills-monthly-statement-transactions-XX0000000CAD-2026-02-01.csv", text)
    assert b.account.key == "wealthsimple-bills"


def test_an_investment_account_is_not_taken():
    text = HEADER + '"2026-01-05","BUY","Invented Fund: Bought 1.0000 shares","-10.00","90.00","CAD"\n'
    with pytest.raises(NotTaken):
        ws.parse(NEW_NAME, text)


def test_an_account_in_another_currency_is_not_taken():
    text = HEADER + '"2026-01-05","INT","Interest","1.00","101.00","USD"\n'
    with pytest.raises(NotTaken):
        ws.parse(NEW_NAME, text)


def test_reads_the_account_name_when_the_date_comes_before_the_marker():
    text = decode((FX / "ws_cash_monthly.csv").read_bytes())
    (b,) = ws.parse("Rainy Day 🌧-2026-01-01-monthly-statement-transactions-XX0000000CAD.csv", text)
    assert b.account.key == "wealthsimple-rainy-day"
    assert check_batch(b) == []
