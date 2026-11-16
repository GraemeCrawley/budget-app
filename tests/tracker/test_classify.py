import pytest
from connectors.batch import AccountRef, StatementBatch, Txn, FORMAT_VERSION, make_uids
from tracker.store import open_db, accept_batch
from tracker.rules import seed_rules
from tracker.classify import classify

CHQ = AccountRef("chq", "Chequing", "chequing", "Bank")
CARD = AccountRef("card", "Card", "card", "Bank")

def put(conn, acct, rows, tag):
    uids = make_uids(acct.key, rows)
    txns = tuple(Txn(d, a, s, u) for (d, a, s), u in zip(rows, uids))
    accept_batch(conn, 1, StatementBatch(FORMAT_VERSION, "t", 1, acct, "activity", "2026-01-01", "2026-01-31",
                                         None, None, txns), tag.encode(), tag)

def put_feb(conn, acct, rows, tag):
    uids = make_uids(acct.key, rows)
    txns = tuple(Txn(d, a, s, u) for (d, a, s), u in zip(rows, uids))
    accept_batch(conn, 1, StatementBatch(FORMAT_VERSION, "t", 1, acct, "activity", "2026-02-01", "2026-02-28",
                                         None, None, txns), tag.encode(), tag)

SEED = [
    dict(priority=10, pattern="PAYMENT RECEIVED", account_key="card", sign=1, kind="transfer", category="", label="card payment"),
    dict(priority=20, pattern="EMPLOYER", sign=1, kind="income", category="", label="pay"),
    dict(priority=30, pattern="HOUSEMATE", sign=1, kind="offset", category="Rent", label="share of rent"),
    dict(priority=40, pattern="LANDLORD", sign=-1, kind="spending", category="Rent", label="rent"),
    dict(priority=50, pattern="INVEST CO", sign=-1, kind="saving", category="", label="investing"),
    dict(priority=60, pattern="GROCER", kind="spending", category="Groceries", label="grocery stores"),
    dict(priority=70, pattern="", sign=-1, min_cents=100000, date_from="2026-01-10", date_to="2026-01-12",
         kind="spending", category="Travel", one_off=1, label="trip"),
]

@pytest.fixture
def rows(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    seed_rules(conn, 1, SEED)
    put(conn, CHQ, [("2026-01-02", -200000, "LANDLORD"), ("2026-01-03", 80000, "E-TRANSFER HOUSEMATE"),
                    ("2026-01-15", 300000, "EMPLOYER PAY"), ("2026-01-16", -50000, "INVEST CO"),
                    ("2026-01-18", -30000, "CARD PYMT 000"), ("2026-01-19", -30000, "SOMETHING ELSE"),
                    ("2026-01-20", 1234, "MYSTERY DEPOSIT")], "chq")
    put(conn, CARD, [("2026-01-05", -4500, "INVENTED GROCER 12"), ("2026-01-07", 500, "INVENTED GROCER 12"),
                     ("2026-01-11", -150000, "AIRLINE"), ("2026-01-17", 30000, "PAYMENT RECEIVED"),
                     ("2026-01-22", -999, "UNKNOWN PLACE")], "card")
    return conn, {c.description: c for c in classify(conn, 1)}

def test_rules_assign_kind_category_and_reason(rows):
    _, c = rows
    assert (c["LANDLORD"].kind, c["LANDLORD"].category, c["LANDLORD"].why) == ("spending", "Rent", "rule: rent")
    assert (c["E-TRANSFER HOUSEMATE"].kind, c["E-TRANSFER HOUSEMATE"].category) == ("offset", "Rent")
    assert c["EMPLOYER PAY"].kind == "income"
    assert c["INVEST CO"].kind == "saving"
    assert (c["AIRLINE"].category, c["AIRLINE"].one_off) == ("Travel", True)

def test_card_payment_is_paired_once(rows):
    _, c = rows
    assert c["PAYMENT RECEIVED"].kind == "transfer"
    assert (c["CARD PYMT 000"].kind, c["CARD PYMT 000"].why) == ("transfer", "paid the card")
    assert c["SOMETHING ELSE"].kind == "spending"

def test_unmatched_rows_are_shown_not_hidden(rows):
    _, c = rows
    assert (c["UNKNOWN PLACE"].kind, c["UNKNOWN PLACE"].category, c["UNKNOWN PLACE"].why) == \
           ("spending", "Uncategorised", "no rule matched")
    assert c["MYSTERY DEPOSIT"].kind == "income"

def test_a_refund_is_spending_with_a_positive_amount(rows):
    conn, _ = rows
    refund = [x for x in classify(conn, 1) if x.amount_cents == 500][0]
    assert (refund.kind, refund.category) == ("spending", "Groceries")

def test_an_override_wins(rows):
    conn, c = rows
    conn.execute("INSERT INTO overrides(transaction_id, user_id, set_at, kind, category, one_off)"
                 " VALUES (?, 1, 'now', NULL, 'Eating out', NULL)",
                 (c["UNKNOWN PLACE"].id,))
    again = {x.description: x for x in classify(conn, 1)}
    assert (again["UNKNOWN PLACE"].category, again["UNKNOWN PLACE"].kind, again["UNKNOWN PLACE"].why) == \
           ("Eating out", "spending", "you set this")


def test_equal_distance_chequing_rows_pair_the_earlier_one(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    seed_rules(conn, 1, SEED)
    put(conn, CHQ, [("2026-01-14", -7000, "FIRST PYMT"), ("2026-01-18", -7000, "SECOND PYMT")], "chq")
    put(conn, CARD, [("2026-01-16", 7000, "PAYMENT RECEIVED")], "card")
    c = {x.description: x for x in classify(conn, 1)}
    assert (c["FIRST PYMT"].kind, c["FIRST PYMT"].why) == ("transfer", "paid the card")
    assert (c["SECOND PYMT"].kind, c["SECOND PYMT"].why) == ("spending", "no rule matched")


def _override(conn, txn_id, kind=None, category=None, one_off=None):
    conn.execute("INSERT INTO overrides(transaction_id, user_id, set_at, kind, category, one_off)"
                 " VALUES (?, 1, 'now', ?, ?, ?)",
                 (txn_id, kind, category, one_off))


def test_one_off_only_override_keeps_the_rule_result(rows):
    conn, c = rows
    _override(conn, c["LANDLORD"].id, one_off=1)
    x = {r.description: r for r in classify(conn, 1)}["LANDLORD"]
    assert (x.kind, x.category, x.one_off, x.why) == ("spending", "Rent", True, "you set this")


def test_category_only_override_keeps_a_saving_kind(rows):
    conn, c = rows
    _override(conn, c["INVEST CO"].id, category="Retirement")
    x = {r.description: r for r in classify(conn, 1)}["INVEST CO"]
    assert (x.kind, x.category, x.why) == ("saving", "Retirement", "you set this")


def test_category_only_override_keeps_an_offset_kind(rows):
    conn, c = rows
    _override(conn, c["E-TRANSFER HOUSEMATE"].id, category="Utilities")
    x = {r.description: r for r in classify(conn, 1)}["E-TRANSFER HOUSEMATE"]
    assert (x.kind, x.category) == ("offset", "Utilities")


def test_owner_marking_a_card_credit_as_transfer_pairs_the_chequing_side(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    seed_rules(conn, 1, SEED)
    put(conn, CHQ, [("2026-01-14", -12000, "ODD OUTFLOW")], "chq")
    put(conn, CARD, [("2026-01-16", 12000, "ODD CREDIT")], "card")
    credit = {x.description: x for x in classify(conn, 1)}["ODD CREDIT"]
    _override(conn, credit.id, kind="transfer")
    c = {x.description: x for x in classify(conn, 1)}
    assert c["ODD CREDIT"].kind == "transfer"
    assert (c["ODD OUTFLOW"].kind, c["ODD OUTFLOW"].why) == ("transfer", "paid the card")


def test_owner_turning_a_payment_into_spending_stops_the_pairing(rows):
    conn, c = rows
    _override(conn, c["PAYMENT RECEIVED"].id, kind="spending")
    again = {x.description: x for x in classify(conn, 1)}
    assert again["PAYMENT RECEIVED"].kind == "spending"
    assert (again["CARD PYMT 000"].kind, again["CARD PYMT 000"].why) == ("spending", "no rule matched")


def test_pairing_window_is_five_days_inclusive(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    seed_rules(conn, 1, SEED)
    put(conn, CHQ, [("2026-01-15", -7000, "FIVE AWAY"), ("2026-01-14", -8000, "SIX AWAY")], "chq")
    put(conn, CARD, [("2026-01-20", 7000, "PAYMENT RECEIVED"), ("2026-01-20", 8000, "PAYMENT RECEIVED")], "card")
    c = {x.description: x for x in classify(conn, 1)}
    assert c["FIVE AWAY"].kind == "transfer"
    assert c["SIX AWAY"].kind == "spending"


def test_only_rows_no_rule_override_or_pairing_decided_are_guessed(rows):
    conn, c = rows
    assert c["MYSTERY DEPOSIT"].guessed is True and c["UNKNOWN PLACE"].guessed is True
    assert c["SOMETHING ELSE"].guessed is True
    assert c["LANDLORD"].guessed is False and c["EMPLOYER PAY"].guessed is False
    assert c["CARD PYMT 000"].guessed is False      # the pairing step decided it
    _override(conn, c["MYSTERY DEPOSIT"].id, kind="income")
    assert {x.description: x for x in classify(conn, 1)}["MYSTERY DEPOSIT"].guessed is False


def test_a_merchant_rule_beats_a_built_in_rule_and_spares_other_merchants(rows):
    from tracker.rules import set_merchant_rule
    conn = rows[0]
    put(conn, CARD, [("2026-01-08", -700, "RETAIL PURCHASE 000111222 INVENTED GROCER"),
                     ("2026-01-09", -800, "RETAIL PURCHASE 000111223 BOOK BARN")], "more")
    set_merchant_rule(conn, 1, "INVENTED GROCER", -1, "spending", "Dining & delivery")
    got = {c.description: (c.category, c.why) for c in classify(conn, 1)}
    assert got["RETAIL PURCHASE 000111222 INVENTED GROCER"] == ("Dining & delivery", "rule: you said INVENTED GROCER")
    assert got["RETAIL PURCHASE 000111223 BOOK BARN"][0] == "Uncategorised"


def test_setting_a_merchant_rule_twice_updates_it(rows):
    from tracker.rules import set_merchant_rule, load_rules
    conn = rows[0]
    a = set_merchant_rule(conn, 1, "BOOK BARN", -1, "spending", "Shopping")
    b = set_merchant_rule(conn, 1, "BOOK BARN", -1, "spending", "Gifts")
    assert a == b
    assert [r.category for r in load_rules(conn, 1) if r.merchant_key == "BOOK BARN"] == ["Gifts"]


def test_every_classified_row_carries_its_merchant_key(rows):
    from tracker.merchant import merchant_key
    assert all(c.merchant_key == merchant_key(c.description) for c in classify(rows[0], 1))


def test_set_merchant_rule_validates_and_joins_a_callers_transaction(rows):
    from tracker.rules import set_merchant_rule
    from tracker.store import write_tx
    conn = rows[0]
    with pytest.raises(ValueError):
        set_merchant_rule(conn, 1, "", -1, "spending", "X")
    with pytest.raises(ValueError):
        set_merchant_rule(conn, 1, "BOOK BARN", -1, "bogus", "X")
    with pytest.raises(RuntimeError):
        with write_tx(conn):
            set_merchant_rule(conn, 1, "BOOK BARN", -1, "spending", "Shopping")
            assert conn.in_transaction
            raise RuntimeError
    assert conn.execute("SELECT COUNT(*) FROM rules WHERE merchant_key = 'BOOK BARN'").fetchone()[0] == 0


def test_unmatched_money_into_a_savings_account_is_a_transfer_and_money_out_is_shown(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    put(conn, AccountRef("trip", "Trip", "savings", "Bank"),
        [("2026-01-05", 20000, "INVENTED DEPOSIT"), ("2026-01-09", -3000, "INVENTED HOSTEL")], "trip")
    c = {x.description: x for x in classify(conn, 1)}
    assert (c["INVENTED DEPOSIT"].kind, c["INVENTED DEPOSIT"].why) == ("transfer", "moved into savings")
    assert (c["INVENTED HOSTEL"].kind, c["INVENTED HOSTEL"].category) == ("spending", "Uncategorised")
