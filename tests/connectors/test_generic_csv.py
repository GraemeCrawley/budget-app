import pytest
from pathlib import Path
from connectors import generic_csv as g
from connectors.contract import check_batch
from connectors.registry import parse_file, UnrecognisedFile

FX = Path(__file__).parent.parent / "fixtures" / "connectors"
TEXT = (FX / "activity_generic.csv").read_text(encoding="utf-8")

def test_parses_activity_without_balances():
    assert g.sniff("export.csv", TEXT)
    (b,) = g.parse("export.csv", TEXT, "some-visa", "card")
    assert check_batch(b) == []
    assert (b.kind, b.opening_cents, b.closing_cents) == ("activity", None, None)
    assert (b.account.key, b.account.kind) == ("some-visa", "card")
    assert [t.amount_cents for t in b.transactions] == [-1250, -1250, 500]
    assert (b.period_start, b.period_end) == ("2026-04-02", "2026-04-09")

def test_needs_an_account():
    with pytest.raises(ValueError, match="choose an account"):
        g.parse("export.csv", TEXT, None, "card")

def test_needs_the_kind_of_account_and_never_guesses_it():
    with pytest.raises(ValueError, match="choose the kind of account"):
        g.parse("export.csv", TEXT, "some-visa")
    (b,) = g.parse("export.csv", TEXT, "some-visa", "savings")
    assert b.account.kind == "savings"

def test_separate_debit_and_credit_columns():
    text = "Date,Details,Debit,Credit\n04/02/2026,INVENTED SHOP,12.50,\n04/25/2026,INVENTED PAY,,100.00\n"
    (b,) = g.parse("e.csv", text, "some-chequing", "chequing")
    assert [t.amount_cents for t in b.transactions] == [-1250, 10000]
    assert (b.account.kind, b.account.institution, b.account.name) == ("chequing", "", "some-chequing")

def test_header_only_file_is_unrecognised():
    with pytest.raises(UnrecognisedFile):
        parse_file("e.csv", b"Date,Description,Amount\n", "some-visa", "card")

def test_registry_needs_an_account_for_a_generic_file():
    with pytest.raises(UnrecognisedFile, match="choose an account"):
        parse_file("export.csv", TEXT.encode(), None)

def test_registry_passes_the_callers_account_kind():
    (b,) = parse_file("export.csv", TEXT.encode(), account_key="some-pot", account_kind="savings")
    assert (b.account.key, b.account.kind) == ("some-pot", "savings")
    with pytest.raises(UnrecognisedFile, match="choose the kind of account"):
        parse_file("export.csv", TEXT.encode(), account_key="some-pot")

def test_day_first_dates_and_bracketed_amounts():
    text = "Date,Description,Amount\n25/04/2026,INVENTED SHOP,(12.50)\n02/05/2026,INVENTED PAY,\"$1,000.00\"\n"
    (b,) = g.parse("e.csv", text, "some-amex", "card")
    assert [t.date for t in b.transactions] == ["2026-04-25", "2026-05-02"]
    assert [t.amount_cents for t in b.transactions] == [-1250, 100000]
    assert b.account.kind == "card"

def test_balance_column_does_not_become_a_credit_column():
    text = "Date,Description,Amount,Running Balance\n2026-04-02,INVENTED SHOP,-12.50,100.00\n"
    (b,) = g.parse("e.csv", text, "some-chequing", "chequing")
    assert [t.amount_cents for t in b.transactions] == [-1250]

def test_does_not_claim_the_wealthsimple_cash_csv():
    text = (FX / "ws_cash_monthly.csv").read_text(encoding="utf-8")
    assert not g.sniff("export.csv", text)
    g.parse("export.csv", text, "some-chequing", "chequing")  # must not crash

@pytest.mark.parametrize("path", sorted(FX.glob("*.txt")), ids=lambda p: p.name)
def test_does_not_claim_statement_text(path):
    assert not g.sniff(path.name, path.read_text(encoding="utf-8"))

@pytest.mark.parametrize("text", ["", "\x00\x01", "hello world\n", "Date\n2026-01-01\n", "Date Amount\n1 2\n"])
def test_sniff_is_false_for_non_csv(text):
    assert g.sniff("x.csv", text) is False

@pytest.mark.parametrize("row,reason", [
    ("not-a-date,INVENTED SHOP,-1.00", "dates in this file could not be read"),
    ("2026-02-30,INVENTED SHOP,-1.00", "dates in this file could not be read"),
    ("2026-04-02,INVENTED SHOP,twelve", "amount that could not be read"),
    ("2026-04-02,INVENTED SHOP,1.234", "amount that could not be read"),
    ("2026-04-02", "too few columns"),
])
def test_bad_rows_raise_plain_value_error_through_the_registry(row, reason):
    data = ("Date,Description,Amount\n2026-04-01,OK,1.00\n" + row + "\n").encode()
    with pytest.raises(UnrecognisedFile) as exc:
        parse_file("e.csv", data, "some-visa", "card")
    assert reason in str(exc.value)
    for secret in ("not-a-date", "02-30", "twelve", "1.234", "INVENTED"):
        assert secret not in str(exc.value)

@pytest.mark.parametrize("text", [
    "Date,Description,Amount\n2026-04-02,X,\n",
    "Date,Description,Debit,Credit\n2026-04-02,X,,\n",
])
def test_blank_amount_is_rejected(text):
    with pytest.raises(UnrecognisedFile, match="no amount"):
        parse_file("e.csv", text.encode(), "some-visa", "card")

def test_one_blank_side_of_a_pair_still_parses():
    text = "Date,Description,Debit,Credit\n2026-04-02,X,5.00,\n2026-04-03,Y,,7.00\n"
    (b,) = parse_file("e.csv", text.encode(), "some-chequing", "chequing")
    assert [t.amount_cents for t in b.transactions] == [-500, 700]

def test_day_first_file_with_small_days_in_the_first_row():
    text = "Date,Description,Amount\n03/04/2026,X,1.00\n25/04/2026,Y,2.00\n"
    (b,) = parse_file("e.csv", text.encode(), "some-visa", "card")
    assert [t.date for t in b.transactions] == ["2026-04-03", "2026-04-25"]

def test_month_first_file_with_a_later_large_day():
    text = "Date,Description,Amount\n03/04/2026,X,1.00\n04/25/2026,Y,2.00\n"
    (b,) = parse_file("e.csv", text.encode(), "some-visa", "card")
    assert [t.date for t in b.transactions] == ["2026-03-04", "2026-04-25"]

def test_all_ambiguous_slash_dates_are_refused():
    text = "Date,Description,Amount\n03/04/2026,X,1.00\n05/06/2026,Y,2.00\n"
    with pytest.raises(UnrecognisedFile, match="day-first or month-first"):
        parse_file("e.csv", text.encode(), "some-visa", "card")

def test_bad_first_date_raises_value_error():
    with pytest.raises(ValueError):
        g.parse("e.csv", "Date,Description,Amount\nnope,X,1.00\n", "some-visa", "card")

def test_a_blank_or_missing_description_still_meets_the_contract():
    for text in ("Date,Amount\n2026-04-02,-1.00\n", "Date,Description,Amount\n2026-04-02, ,-1.00\n"):
        (b,) = parse_file("e.csv", text.encode(), "some-visa", "card")
        assert [t.description for t in b.transactions] == ["(no description)"]
