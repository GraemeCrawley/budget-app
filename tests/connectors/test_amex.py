from pathlib import Path

import pytest

from connectors import amex, registry
from connectors.contract import check_batch

FX = Path(__file__).parent.parent / "fixtures" / "connectors"


def load(name): return (FX / name).read_text(encoding="utf-8")


def test_parses_a_statement_that_reconciles():
    text = load("amex_statement.txt")
    assert amex.sniff("s.txt", text)
    (b,) = amex.parse("s.txt", text)
    assert check_batch(b) == []
    assert (b.kind, b.account.key, b.account.kind) == ("statement", "amex-cobalt", "card")
    assert (b.period_start, b.period_end) == ("2026-01-04", "2026-02-03")
    assert (b.opening_cents, b.closing_cents) == (-30000, -18050)
    assert [t.amount_cents for t in b.transactions] == [-6025, 30000, -12025]


def test_year_boundary():
    (b,) = amex.parse("s.txt", load("amex_statement_yearend.txt"))
    assert check_batch(b) == []
    assert [t.date for t in b.transactions] == ["2025-12-20", "2026-01-02"]


def test_does_not_claim_other_text():
    assert not amex.sniff("x.txt", "Transaction details\nOpening balance 1.00\n")


@pytest.mark.parametrize("drop", ["Previous Balance", "Equals New Balance", "Opening Date"])
def test_claimed_but_unparseable_text_is_unrecognised(drop):
    text = load("amex_statement.txt").replace(drop, "Removed Label")
    assert amex.sniff("s.txt", text)
    with pytest.raises(registry.UnrecognisedFile):
        registry.parse_file("s.txt", text.encode("utf-8"))


def test_registry_routes_to_amex():
    (b,) = registry.parse_file("s.txt", load("amex_statement.txt").encode("utf-8"))
    assert b.connector == "amex"


def test_charge_dated_before_the_opening_date_widens_the_period():
    text = load("amex_statement.txt").replace("Jan 10        Jan 11", "Jan 2         Jan 5 ")
    (b,) = amex.parse("s.txt", text)
    assert check_batch(b) == []
    assert b.period_start == "2026-01-02"
    assert b.transactions[0].date == "2026-01-02"


def test_late_december_charge_on_a_statement_opening_in_january():
    text = load("amex_statement.txt").replace("Jan 10        Jan 11", "Dec 31        Jan 5 ")
    (b,) = amex.parse("s.txt", text)
    assert check_batch(b) == []
    assert b.transactions[0].date == "2025-12-31"
    assert b.period_start == "2025-12-31"


@pytest.mark.parametrize("bad_row", ["Feb 5         Feb 6 ", "Feb 31        Feb 3 "])
def test_transaction_dates_outside_the_statement_window_are_unrecognised(bad_row):
    text = load("amex_statement.txt").replace("Jan 10        Jan 11", bad_row)
    assert amex.sniff("s.txt", text)
    with pytest.raises(registry.UnrecognisedFile):
        registry.parse_file("s.txt", text.encode("utf-8"))
