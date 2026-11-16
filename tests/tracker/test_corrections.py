import pytest
from tests.tracker.test_classify import put, put_feb, CHQ, CARD, SEED
from tracker.classify import classify
from tracker.corrections import set_override, clear_override, correct_merchant
from tracker.rules import seed_rules
from tracker.store import open_db


@pytest.fixture
def conn(tmp_path):
    c = open_db(str(tmp_path / "t.db"))
    seed_rules(c, 1, SEED)
    put(c, CHQ, [("2026-01-15", 300000, "EMPLOYER PAY")], "chq")
    put(c, CARD, [("2026-01-05", -4500, "INVENTED GROCER 12"), ("2026-01-22", -999, "UNKNOWN PLACE 4411"),
                  ("2026-01-25", -700, "UNKNOWN PLACE")], "card")
    put_feb(c, CARD, [("2026-02-03", -1500, "UNKNOWN PLACE"), ("2026-02-04", 300, "UNKNOWN PLACE")], "card2")
    return c


def txn_id(conn, description, date=None):
    sql = "SELECT id FROM transactions WHERE description = ?"
    args = [description]
    if date:
        sql += " AND date = ?"
        args.append(date)
    return conn.execute(sql, args).fetchone()["id"]


@pytest.fixture
def card_txn(conn):
    return txn_id(conn, "INVENTED GROCER 12")


def row(conn, tid):
    r = conn.execute("SELECT kind, category, one_off FROM overrides WHERE transaction_id = ?", (tid,)).fetchone()
    return tuple(r) if r else None


def test_an_override_merges_field_by_field_and_empties_away(conn, card_txn):
    set_override(conn, 1, card_txn, category="Coffee")
    set_override(conn, 1, card_txn, one_off=True)
    assert row(conn, card_txn) == (None, "Coffee", 1)
    set_override(conn, 1, card_txn, category=None); set_override(conn, 1, card_txn, one_off=None)
    assert conn.execute("SELECT COUNT(*) FROM overrides").fetchone()[0] == 0


def test_an_override_changes_the_classification_and_the_reason(conn, card_txn):
    set_override(conn, 1, card_txn, category="Coffee", kind="spending")
    c = next(c for c in classify(conn, 1) if c.id == card_txn)
    assert (c.category, c.why, c.guessed) == ("Coffee", "you set this", False)
    clear_override(conn, 1, card_txn)
    assert row(conn, card_txn) is None
    assert next(c for c in classify(conn, 1) if c.id == card_txn).category == "Groceries"


def test_an_unknown_kind_is_a_value_error_and_writes_nothing(conn, card_txn):
    with pytest.raises(ValueError):
        set_override(conn, 1, card_txn, kind="nonsense")
    assert row(conn, card_txn) is None
    assert not conn.in_transaction


def test_another_users_or_a_superseded_charge_cannot_be_corrected(conn, card_txn):
    with pytest.raises(LookupError): set_override(conn, 2, card_txn, category="Coffee")
    with pytest.raises(LookupError): clear_override(conn, 2, card_txn)
    conn.execute("UPDATE transactions SET superseded_by = batch_id WHERE id = ?", (card_txn,)); conn.commit()
    with pytest.raises(LookupError): set_override(conn, 1, card_txn, category="Coffee")


def test_a_merchant_correction_recategorises_past_and_future_charges(conn):
    first_id = txn_id(conn, "UNKNOWN PLACE 4411")
    set_override(conn, 1, first_id, category="Other")
    n = correct_merchant(conn, 1, first_id, "spending", "Entertainment")
    # the two money-out charges in January and the one in February; the 300 refund has the other sign
    assert n == 3
    assert {c.category for c in classify(conn, 1) if c.merchant_key == "UNKNOWN PLACE" and c.amount_cents < 0} \
        == {"Entertainment"}
    refund = next(c for c in classify(conn, 1) if c.amount_cents == 300)
    assert refund.category == "Uncategorised"
    assert conn.execute("SELECT COUNT(*) FROM overrides WHERE transaction_id = ?", (first_id,)).fetchone()[0] == 0
    assert next(c for c in classify(conn, 1) if c.id == first_id).why == "rule: you said UNKNOWN PLACE"


def test_a_second_merchant_correction_replaces_the_first_rule(conn):
    tid = txn_id(conn, "UNKNOWN PLACE", "2026-01-25")
    correct_merchant(conn, 1, tid, "spending", "Entertainment")
    correct_merchant(conn, 1, tid, "spending", "Gifts", one_off=1)
    assert conn.execute("SELECT COUNT(*) FROM rules WHERE origin = 'owner'").fetchone()[0] == 1
    c = next(c for c in classify(conn, 1) if c.id == tid)
    assert (c.category, c.one_off) == ("Gifts", True)


def test_a_charge_with_no_merchant_cannot_make_a_rule(conn):
    put_feb(conn, CARD, [("2026-02-10", -250, "RETAIL PURCHASE 123456")], "card3")
    tid = txn_id(conn, "RETAIL PURCHASE 123456")
    with pytest.raises(ValueError, match="no merchant"):
        correct_merchant(conn, 1, tid, "spending", "Other")
    assert not conn.in_transaction


def test_a_merchant_correction_on_someone_elses_charge_is_a_lookup_error(conn, card_txn):
    with pytest.raises(LookupError):
        correct_merchant(conn, 2, card_txn, "spending", "Other")


def test_an_empty_category_in_an_override_is_a_value_error(conn, card_txn):
    with pytest.raises(ValueError):
        set_override(conn, 1, card_txn, category="")
    assert row(conn, card_txn) is None and not conn.in_transaction


@pytest.mark.parametrize("kind", ["spending", "bucket", "offset"])
def test_a_spending_like_merchant_correction_needs_a_category(conn, kind):
    tid = txn_id(conn, "UNKNOWN PLACE", "2026-01-25")
    with pytest.raises(ValueError):
        correct_merchant(conn, 1, tid, kind, "")
    assert conn.execute("SELECT COUNT(*) FROM rules WHERE origin = 'owner'").fetchone()[0] == 0
    assert not conn.in_transaction


@pytest.mark.parametrize("kind", ["transfer", "income", "saving"])
def test_a_merchant_correction_that_is_not_spending_stores_no_category(conn, kind):
    tid = txn_id(conn, "UNKNOWN PLACE", "2026-01-25")
    correct_merchant(conn, 1, tid, kind, "Coffee")
    assert [tuple(r) for r in conn.execute("SELECT kind, category FROM rules WHERE origin = 'owner'")] == [(kind, "")]
    assert next(c for c in classify(conn, 1) if c.id == tid).category == ""


def test_spending_with_an_empty_category_is_uncategorised(conn):
    pay = txn_id(conn, "EMPLOYER PAY")  # a rule says income with category ""
    set_override(conn, 1, pay, kind="spending")
    c = next(c for c in classify(conn, 1) if c.id == pay)
    assert (c.kind, c.category) == ("spending", "Uncategorised")
    seed_rules(conn, 1, [dict(pattern="GROCER", kind="bucket", category="", label="empty")])
    grocer = next(c for c in classify(conn, 1) if c.description == "INVENTED GROCER 12")
    assert (grocer.kind, grocer.category) == ("bucket", "Uncategorised")


def test_a_one_off_charge_stays_one_off_after_a_merchant_correction(conn):
    tid = txn_id(conn, "UNKNOWN PLACE", "2026-01-25")
    set_override(conn, 1, tid, category="Other", kind="spending", one_off=True)
    correct_merchant(conn, 1, tid, "spending", "Entertainment")
    assert row(conn, tid) == (None, None, 1)
    c = next(c for c in classify(conn, 1) if c.id == tid)
    assert (c.category, c.one_off) == ("Entertainment", True)


def test_a_category_name_is_validated_and_trimmed_for_both_writers(conn, card_txn):
    for bad in ("  ", "y" * 41, "a\tb", "Uncategorised", "uncategorised"):
        with pytest.raises(ValueError):
            set_override(conn, 1, card_txn, category=bad)
        with pytest.raises(ValueError):
            correct_merchant(conn, 1, card_txn, "spending", bad)
    assert row(conn, card_txn) is None and not conn.in_transaction
    set_override(conn, 1, card_txn, category="  Pottery ")
    assert row(conn, card_txn) == (None, "Pottery", None)
    set_override(conn, 1, card_txn, category="pottery")   # now an existing category: keeps its spelling
    assert row(conn, card_txn) == (None, "Pottery", None)
    correct_merchant(conn, 1, card_txn, "spending", "COFFEE")
    assert conn.execute("SELECT category FROM rules WHERE origin = 'owner'").fetchone()[0] == "Coffee"
