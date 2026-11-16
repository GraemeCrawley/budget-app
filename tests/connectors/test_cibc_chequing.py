from pathlib import Path

import pytest

from connectors import cibc_chequing as cibc
from connectors.contract import check_batch
from connectors.registry import UnrecognisedFile, parse_file

FX = Path(__file__).parent.parent / "fixtures" / "connectors"

def load(name): return (FX / name).read_text(encoding="utf-8")

def test_parses_a_statement_that_reconciles():
    text = load("cibc_statement.txt")
    assert cibc.sniff("anything.txt", text)
    (b,) = cibc.parse("anything.txt", text)
    assert check_batch(b) == []
    assert (b.kind, b.account.key) == ("statement", "cibc-chequing")
    assert (b.period_start, b.period_end) == ("2026-02-01", "2026-02-28")
    assert (b.opening_cents, b.closing_cents) == (100000, 242000)
    assert [t.amount_cents for t in b.transactions] == [-4000, -4000, 200000, -50000]
    assert b.transactions[0].uid != b.transactions[1].uid
    assert "REF 0001" in b.transactions[2].description
    assert "000000000001" in b.transactions[3].description

def test_year_boundary():
    (b,) = cibc.parse("x.txt", load("cibc_statement_yearend.txt"))
    assert check_batch(b) == []
    assert (b.period_start, b.period_end) == ("2025-12-15", "2026-01-14")
    assert [t.date for t in b.transactions] == ["2025-12-30", "2026-01-02"]

def test_does_not_claim_other_text():
    assert not cibc.sniff("x.txt", "Your Transactions\nClosing Date Feb 3, 2026\n")

def test_line_not_matching_balance_movement_is_skipped():
    text = load("cibc_statement.txt").replace("500.00 ", "499.00 ", 1)
    (b,) = cibc.parse("x.txt", text)
    assert [t.amount_cents for t in b.transactions] == [-4000, -4000, 200000]

def test_missing_period_line_raises():
    with pytest.raises(ValueError):
        cibc.parse("x.txt", load("cibc_statement.txt").replace("For Feb 1 to Feb 28, 2026", ""))

def test_phrase_only_mid_line_is_unrecognised_not_a_crash():
    text = "INVENTED CLIENT   For Feb 1 to Feb 28, 2026\nSee Transaction details below\nOpening balance $1.00\n"
    assert cibc.sniff("x.txt", text)
    with pytest.raises(UnrecognisedFile):
        parse_file("x.txt", text.encode("utf-8"))
