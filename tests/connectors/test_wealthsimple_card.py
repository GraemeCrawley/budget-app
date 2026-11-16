import pytest

from connectors import wealthsimple_card as card
from connectors.contract import check_batch
from connectors.parsing import NotTaken
from connectors.registry import parse_file

HEADER = '"transaction_date","post_date","type","details","amount","currency"\n'
TEXT = (HEADER
        + '"2026-01-30","2026-02-01","Purchase","INVENTED SHOP","12.50","CAD"\n'
        + '"2026-02-03","2026-02-04","Purchase","INVENTED CAFE","8.00","CAD"\n'
        + '"2026-02-09","2026-02-10","Payment","","-20.50","CAD"\n')
NAME = "credit-card-statement-transactions-2026-02-01.csv"


def test_charges_become_money_out_on_the_cards_own_account():
    assert card.sniff(NAME, TEXT)
    (b,) = card.parse(NAME, TEXT)
    assert check_batch(b) == []
    assert (b.kind, b.account.key, b.account.kind) == ("activity", "wealthsimple-credit-card", "card")
    assert [(t.date, t.amount_cents, t.description) for t in b.transactions] == [
        ("2026-01-30", -1250, "INVENTED SHOP"), ("2026-02-03", -800, "INVENTED CAFE"), ("2026-02-09", 2050, "Payment")]
    assert (b.period_start, b.period_end) == ("2026-01-15", "2026-02-14")


def test_the_file_needs_no_account_chosen():
    (b,) = parse_file(NAME, TEXT.encode())
    assert b.connector == "wealthsimple_card"


def test_does_not_claim_another_csv():
    assert not card.sniff("x.csv", "Date,Description,Amount\n")


def test_a_card_in_another_currency_is_not_taken():
    with pytest.raises(NotTaken):
        card.parse(NAME, TEXT.replace('"CAD"', '"USD"', 1))


def test_the_period_is_stretched_to_hold_a_row_outside_the_usual_cycle():
    text = TEXT.replace('"2026-02-09","2026-02-10"', '"2026-02-16","2026-02-17"')
    (b,) = card.parse(NAME, text)
    assert (b.period_start, b.period_end) == ("2026-01-15", "2026-02-16")
    assert check_batch(b) == []


def test_a_january_file_starts_in_december():
    text = HEADER + '"2026-01-02","2026-01-03","Purchase","INVENTED SHOP","5.00","CAD"\n'
    (b,) = card.parse("credit-card-statement-transactions-2026-01-01.csv", text)
    assert (b.period_start, b.period_end) == ("2025-12-15", "2026-01-14")


def test_a_file_with_no_date_in_its_name_covers_the_span_of_its_rows():
    (b,) = card.parse("card.csv", TEXT)
    assert (b.period_start, b.period_end) == ("2026-01-30", "2026-02-09")


def test_the_month_is_read_when_the_date_comes_before_the_marker():
    name = "Wealthy-credit-card-2026-02-01-credit-card-statement-transactions-ca-credit-card-xx.csv"
    (b,) = card.parse(name, TEXT)
    assert (b.period_start, b.period_end) == ("2026-01-15", "2026-02-14")
