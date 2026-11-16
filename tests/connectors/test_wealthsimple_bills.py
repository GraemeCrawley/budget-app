import pytest
from pathlib import Path

from connectors import registry, wealthsimple_bills as wb
from connectors.contract import check_batch

FX = Path(__file__).parent.parent / "fixtures" / "connectors"


def _text():
    return (FX / "ws_bills_statement.txt").read_text(encoding="utf-8")


def test_parses_a_statement_that_reconciles():
    text = _text()
    assert wb.sniff("WS-Bills-March.txt", text)
    (b,) = wb.parse("WS-Bills-March.txt", text)
    assert check_batch(b) == []
    assert (b.opening_cents, b.closing_cents) == (5000, 17015)
    assert [t.amount_cents for t in b.transactions] == [20000, -8000, 15]
    assert (b.period_start, b.period_end) == ("2026-03-01", "2026-03-31")


def test_registry_picks_it_up():
    (b,) = registry.parse_file("WS-Bills-March.txt", _text().encode("utf-8"))
    assert b.connector == "wealthsimple_bills"


def test_running_balance_mismatch_is_unrecognised():
    bad = _text().replace("$170.00", "$171.00")
    with pytest.raises(ValueError):
        wb.parse("x.txt", bad)
    with pytest.raises(registry.UnrecognisedFile):
        registry.parse_file("x.txt", bad.encode("utf-8"))


def test_impossible_date_is_unrecognised():
    bad = _text().replace("2026-03-10             2026-03-10", "2026-02-30             2026-03-10")
    with pytest.raises(registry.UnrecognisedFile):
        registry.parse_file("x.txt", bad.encode("utf-8"))


def test_no_transactions_is_not_sniffed():
    assert not wb.sniff("x.txt", "Wealthsimple\nnothing here\n")


def test_december_period_ends_on_the_31st():
    text = _text().replace("2026-03-01", "2026-12-01").replace("2026-03-10", "2026-12-10").replace("2026-03-31", "2026-12-31")
    (b,) = wb.parse("x.txt", text)
    assert (b.period_start, b.period_end) == ("2026-12-01", "2026-12-31")
