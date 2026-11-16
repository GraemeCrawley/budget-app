from dataclasses import replace
from connectors.batch import AccountRef, StatementBatch, Txn, FORMAT_VERSION, make_uids
from connectors.contract import check_batch

def good():
    rows = [("2026-01-05", -450, "CORNER SHOP"), ("2026-01-20", 100000, "PAY")]
    uids = make_uids("acct-x", rows)
    txns = tuple(Txn(d, a, s, u) for (d, a, s), u in zip(rows, uids))
    return StatementBatch(FORMAT_VERSION, "test", 1, AccountRef("acct-x", "Test", "chequing", "Testbank"),
                          "statement", "2026-01-01", "2026-01-31", 5000, 104550, txns)

def test_valid_batch_has_no_violations():
    assert check_batch(good()) == []

def test_violations_are_reported():
    b = good()
    assert any("balance" in v for v in check_batch(replace(b, closing_cents=1)))
    assert any("period" in v for v in check_batch(replace(b, period_end="2026-01-10")))
    assert any("kind" in v for v in check_batch(replace(b, kind="other")))
    assert any("uid" in v for v in check_batch(replace(b, transactions=(b.transactions[0], b.transactions[0]))))
    assert any("version" in v for v in check_batch(replace(b, format_version=99)))
    assert any("date" in v for v in check_batch(replace(b, period_start="01/01/2026")))

def test_balance_rule_is_skipped_when_balances_are_absent():
    assert check_batch(replace(good(), opening_cents=None, closing_cents=None, kind="activity")) == []

def test_a_statement_must_carry_balances():
    assert any("balance" in v for v in check_batch(replace(good(), opening_cents=None)))


import pytest


@pytest.mark.parametrize("value", ["20260105", "2026-W02-1", "2026-1-5", None, 20260105])
def test_dates_must_be_canonical_iso_strings(value):
    b = good()
    assert any("period_start" in v for v in check_batch(replace(b, period_start=value)))
    assert any("period_end" in v for v in check_batch(replace(b, period_end=value)))
    t = replace(b.transactions[0], date=value)
    assert any("date" in v for v in check_batch(replace(b, transactions=(t, b.transactions[1]))))


@pytest.mark.parametrize("value", [None, 12.5, True, "450", 450.0])
def test_amounts_must_be_int_cents(value):
    b = good()
    t = replace(b.transactions[0], amount_cents=value)
    problems = check_batch(replace(b, kind="activity", opening_cents=None, closing_cents=None,
                                   transactions=(t, b.transactions[1])))
    assert any("amount" in v for v in problems)


@pytest.mark.parametrize("field", ["opening_cents", "closing_cents"])
@pytest.mark.parametrize("value", [12.5, True, "5000"])
def test_balances_must_be_int_or_none(field, value):
    assert any(field in v for v in check_batch(replace(good(), **{field: value})))


@pytest.mark.parametrize("field", ["description", "uid"])
@pytest.mark.parametrize("value", [None, "", 7])
def test_description_and_uid_must_be_non_empty_text(field, value):
    b = good()
    t = replace(b.transactions[0], **{field: value})
    assert any(field in v for v in check_batch(replace(b, transactions=(t, b.transactions[1]))))


def _violations():
    from connectors.contract import check_batch_codes  # noqa: F401
    b = good()
    t0, t1 = b.transactions
    activity = dict(kind="activity", opening_cents=None, closing_cents=None)
    return {
        "format_version": replace(b, format_version=99),
        "batch_kind": replace(b, kind="other"),
        "account_kind": replace(b, account=replace(b.account, kind="loan")),
        "bad_period": replace(b, period_start="01/01/2026"),
        "period_order": replace(b, period_start="2026-02-01"),
        "bad_amount": replace(b, **activity, transactions=(replace(t0, amount_cents=12.5), t1)),
        "bad_balance_type": replace(b, opening_cents=12.5),
        "bad_description": replace(b, transactions=(replace(t0, description=""), t1)),
        "bad_uid": replace(b, transactions=(replace(t0, uid=""), t1)),
        "bad_date": replace(b, transactions=(replace(t0, date="soon"), t1)),
        "outside_period": replace(b, transactions=(replace(t0, date="2025-12-31"), t1)),
        "duplicate_uid": replace(b, transactions=(t0, t0)),
        "missing_balance": replace(b, opening_cents=None),
        "balance_mismatch": replace(b, closing_cents=1),
    }


def test_codes_line_up_with_messages_for_every_kind_of_violation():
    from connectors.contract import check_batch_codes
    assert check_batch_codes(good()) == []
    for name, b in _violations().items():
        assert len(check_batch(b)) == len(check_batch_codes(b)) >= 1, name
    several = replace(good(), format_version=99, kind="other", closing_cents=1,
                      transactions=(replace(good().transactions[0], description=""), good().transactions[1]))
    assert len(check_batch(several)) == len(check_batch_codes(several))


def test_each_violation_has_its_code():
    from connectors.contract import check_batch_codes
    expected = {"format_version": "format_version", "batch_kind": "batch_kind", "account_kind": "account_kind",
                "bad_period": "bad_period", "period_order": "bad_period", "bad_amount": "bad_amount",
                "bad_balance_type": "bad_amount", "bad_description": "bad_description", "bad_uid": "bad_uid",
                "bad_date": "bad_date", "outside_period": "outside_period", "duplicate_uid": "duplicate_uid",
                "missing_balance": "missing_balance", "balance_mismatch": "balance_mismatch"}
    for name, b in _violations().items():
        assert expected[name] in check_batch_codes(b), name
    assert check_batch_codes(replace(good(), closing_cents=1)) == ["balance_mismatch"]
    # same order as the messages: version, then kind, then the transactions, then the balance
    both = replace(good(), format_version=99, closing_cents=1)
    assert check_batch_codes(both) == ["format_version", "balance_mismatch"]
