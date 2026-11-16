from tests.tracker.test_classify import rows, put, CHQ, SEED  # noqa: F401
from tracker.store import open_db
from tracker.rules import seed_rules
from tracker.months import month_facts
from tracker.blocks import BLOCKS

def test_january_adds_up(rows):
    conn, _ = rows
    (m,) = month_facts(conn, 1)
    assert m.month == "2026-01"
    assert m.income_cents == 300000 + 1234
    # rent 200000 less the 80000 offset; groceries 4500 less a 500 refund; airline 150000;
    # the unpaired 30000; the unknown 999
    assert m.blocks == {"Food": 4000, "Bills": 120000, "Subscriptions": 0,
                        "Big purchases": 180000, "Buckets": 0, "Everything else": 999}
    assert m.spending_cents == sum(m.blocks.values()) == 304999
    assert m.saving_cents == 50000
    assert m.savings_rate == round((301234 - 304999) / 301234, 4)   # negative: spent more than earned
    assert (m.food_home_cents, m.food_out_cents) == (4000, 0)
    assert m.provisional is True and m.uncategorised_count == 2
    assert list(m.blocks) == BLOCKS

def test_no_income_gives_no_rate(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    seed_rules(conn, 1, SEED)
    put(conn, CHQ, [("2026-01-02", -200000, "LANDLORD")], "only")
    (m,) = month_facts(conn, 1)
    assert m.income_cents == 0 and m.savings_rate is None

def test_blocks_add_up_when_an_offset_exceeds_its_category(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    seed_rules(conn, 1, SEED)
    put(conn, CHQ, [("2026-01-02", -50000, "LANDLORD"), ("2026-01-03", 80000, "E-TRANSFER HOUSEMATE"),
                    ("2026-01-15", 100000, "EMPLOYER PAY")], "chq")
    (m,) = month_facts(conn, 1)
    assert m.blocks["Bills"] == -30000
    assert m.spending_cents == sum(m.blocks.values()) == -30000
    assert m.savings_rate == round((100000 + 30000) / 100000, 4)


FOOD_SEED = [
    dict(priority=10, pattern="PAYROLL", sign=1, kind="income", category="", label="pay"),
    dict(priority=15, pattern="BONUS", sign=1, kind="income", category="", one_off=1, label="bonus"),
    dict(priority=20, pattern="DINER", kind="spending", category="Dining & delivery", label="dining"),
    dict(priority=30, pattern="CAFE", kind="spending", category="Coffee", label="coffee"),
    dict(priority=40, pattern="GROCER", kind="spending", category="Groceries", label="groceries"),
    dict(priority=50, pattern="POT", kind="bucket", category="Coffee", label="bucket"),
]


def test_food_split_and_buckets(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    seed_rules(conn, 1, FOOD_SEED)
    put(conn, CHQ, [("2026-01-02", -3000, "DINER"), ("2026-01-03", -450, "CAFE"),
                    ("2026-01-04", -7000, "GROCER"), ("2026-01-05", -9000, "POT")], "chq")
    (m,) = month_facts(conn, 1)
    assert m.food_out_cents == 3450 and m.food_home_cents == 7000
    assert m.food_out_cents + m.food_home_cents == m.blocks["Food"] == 10450
    assert m.blocks["Buckets"] == 9000
    assert m.spending_cents == 19450


def _batch(conn, kind, start, end, rows, tag):
    from connectors.batch import StatementBatch, Txn, FORMAT_VERSION, make_uids
    from tracker.store import accept_batch
    txns = tuple(Txn(d, a, s, u) for (d, a, s), u in zip(rows, make_uids(CHQ.key, rows)))
    opening, closing = (0, sum(a for _, a, _ in rows)) if kind == "statement" else (None, None)
    result = accept_batch(conn, 1, StatementBatch(FORMAT_VERSION, "t", 1, CHQ, kind, start, end,
                                                  opening, closing, txns), tag.encode(), tag)
    assert result.status == "accepted"


def test_one_off_income_provisional_and_ordering(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    seed_rules(conn, 1, FOOD_SEED)
    _batch(conn, "activity", "2026-02-01", "2026-02-28",
           [("2026-02-02", 5000, "BONUS"), ("2026-02-03", 100000, "PAYROLL")], "feb")
    _batch(conn, "activity", "2026-01-01", "2026-01-31", [("2026-01-02", 100000, "PAYROLL")], "jan")
    jan, feb = month_facts(conn, 1)
    assert (jan.month, feb.month) == ("2026-01", "2026-02")
    assert jan.one_off_income is False and feb.one_off_income is True


def test_a_charge_marked_one_off_flags_its_month(tmp_path):
    from tracker.corrections import set_override
    conn = open_db(str(tmp_path / "t.db"))
    _batch(conn, "activity", "2026-01-01", "2026-01-31",
           [("2026-01-02", 100000, "PAYROLL"), ("2026-01-09", -90000, "INVENTED YEARLY POLICY")], "jan")
    assert month_facts(conn, 1)[0].one_off_spending is False
    charge = conn.execute("SELECT id FROM transactions WHERE amount_cents < 0").fetchone()[0]
    set_override(conn, 1, charge, category="Insurance", one_off=True)
    (jan,) = month_facts(conn, 1)
    assert jan.one_off_spending is True and jan.blocks["Bills"] == 90000


def test_statement_only_month_is_not_provisional(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    seed_rules(conn, 1, FOOD_SEED)
    _batch(conn, "statement", "2026-01-01", "2026-01-31", [("2026-01-02", -3000, "DINER")], "s")
    (m,) = month_facts(conn, 1)
    assert m.provisional is False


def test_income_no_rule_matched_is_counted_as_unconfirmed(rows):
    conn, c = rows
    (m,) = month_facts(conn, 1)
    assert m.unconfirmed_income_count == 1            # the mystery deposit; the employer's pay has a rule
    conn.execute("INSERT INTO overrides(transaction_id, user_id, set_at, kind) VALUES (?, 1, 'now', 'income')", (c["MYSTERY DEPOSIT"].id,))
    (m,) = month_facts(conn, 1)
    assert m.unconfirmed_income_count == 0 and m.income_cents == 301234


def test_uncategorised_count_skips_rows_whose_final_kind_has_no_category(rows):
    conn, c = rows
    for desc, kind in (("UNKNOWN PLACE", "transfer"), ("SOMETHING ELSE", "saving")):
        conn.execute("INSERT INTO overrides(transaction_id, user_id, set_at, kind) VALUES (?, 1, 'now', ?)", (c[desc].id, kind))
    (m,) = month_facts(conn, 1)
    assert m.uncategorised_count == 0
