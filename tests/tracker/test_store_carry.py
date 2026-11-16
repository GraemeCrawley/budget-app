"""A statement that words a charge differently keeps the owner's merchant-wide correction (F1)."""
from tests.tracker.test_store import ACCT, batch, conn  # noqa: F401  (conn is a fixture)
from tracker.classify import classify
from tracker.merchant import merchant_key
from tracker.months import month_facts
from tracker.rules import OWNER_CARRIED, seed_rules, set_merchant_rule
from tracker.store import accept_batch

EXPORT = [("2026-01-05", -450, "CORNER CAFE WEB"), ("2026-01-12", -525, "CORNER CAFE WEB")]


def _export(conn):
    accept_batch(conn, 1, batch(EXPORT, kind="activity", start="2026-01-05", end="2026-01-12"), b"act", "a.csv")


def _statement(conn, wording):
    return accept_batch(conn, 1, batch([(d, a, wording) for d, a, _ in EXPORT]), b"st", "s.txt")


def _overrides(conn):
    return [tuple(r) for r in conn.execute("SELECT kind, category, one_off FROM overrides ORDER BY transaction_id")]


def _live(conn):
    return [c for c in classify(conn, 1) if not c.provisional]


def test_a_merchant_rule_survives_a_statement_that_words_the_charge_differently(conn):
    set_merchant_rule(conn, 1, merchant_key("CORNER CAFE WEB"), -1, "spending", "Coffee")
    _export(conn)
    assert merchant_key("CORNER CAFE #4417 TORONTO ON") != merchant_key("CORNER CAFE WEB")
    r = _statement(conn, "CORNER CAFE #4417 TORONTO ON")
    assert r.confirmed == 2
    live = _live(conn)
    assert [(c.kind, c.category) for c in live] == [("spending", "Coffee")] * 2
    assert len(live) == len(classify(conn, 1))  # the export's rows are superseded
    assert next(m for m in month_facts(conn, 1) if m.month == "2026-01").uncategorised_count == 0
    assert _overrides(conn) == [("spending", "Coffee", 0)] * 2
    assert all(r[0] for r in conn.execute("SELECT set_at FROM overrides"))
    assert conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 1  # no rule created or changed


def test_the_rules_one_off_is_carried_too(conn):
    set_merchant_rule(conn, 1, merchant_key("CORNER CAFE WEB"), -1, "bucket", "Gifts", one_off=1)
    _export(conn)
    _statement(conn, "CORNER CAFE #4417 TORONTO ON")
    assert _overrides(conn) == [("bucket", "Gifts", 1)] * 2


def test_no_override_when_the_statement_wording_has_the_same_key(conn):
    set_merchant_rule(conn, 1, merchant_key("CORNER CAFE WEB"), -1, "spending", "Coffee")
    _export(conn)
    _statement(conn, "CORNER CAFE WEB #4417")
    assert _overrides(conn) == []
    assert [c.category for c in _live(conn)] == ["Coffee", "Coffee"]


def test_an_override_already_on_the_statement_row_is_left_alone(conn):
    set_merchant_rule(conn, 1, merchant_key("CORNER CAFE WEB"), -1, "spending", "Coffee")
    _export(conn)
    first = conn.execute("SELECT id FROM transactions ORDER BY date LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO overrides (transaction_id, user_id, kind, category, one_off, set_at)"
                 " VALUES (?, 1, NULL, 'Eating out', NULL, 'then')", (first,))
    conn.commit()
    _statement(conn, "CORNER CAFE #4417 TORONTO ON")
    assert _overrides(conn) == [(None, "Eating out", None), ("spending", "Coffee", 0)]
    assert conn.execute("SELECT set_at FROM overrides ORDER BY transaction_id LIMIT 1").fetchone()[0] == "then"


def test_a_seed_rule_deciding_the_export_row_writes_nothing(conn):
    seed_rules(conn, 1, [dict(pattern="CAFE WEB", kind="spending", category="Coffee", label="cafe")])
    _export(conn)
    _statement(conn, "CORNER CAFE #4417 TORONTO ON")
    assert _overrides(conn) == []


def test_a_carried_rule_that_a_seed_rule_ran_ahead_of_writes_nothing(conn):
    # the seed rule decided the export's rows, so the owner never saw the carried rule's category on them
    seed_rules(conn, 1, [dict(pattern="CAFE WEB", kind="transfer", category="", label="cafe")])
    set_merchant_rule(conn, 1, merchant_key("CORNER CAFE WEB"), -1, "spending", "Coffee", priority=OWNER_CARRIED)
    _export(conn)
    _statement(conn, "CORNER CAFE #4417 TORONTO ON")
    assert _overrides(conn) == []


def test_a_merchant_rule_for_the_other_sign_writes_nothing(conn):
    set_merchant_rule(conn, 1, merchant_key("CORNER CAFE WEB"), 1, "spending", "Coffee")
    _export(conn)
    _statement(conn, "CORNER CAFE #4417 TORONTO ON")
    assert _overrides(conn) == []


def _carried(conn):
    return [r[0] for r in conn.execute("SELECT carried_key FROM overrides ORDER BY transaction_id")]


def test_a_carried_override_remembers_the_merchant_it_came_from(conn):
    set_merchant_rule(conn, 1, merchant_key("CORNER CAFE WEB"), -1, "spending", "Coffee")
    _export(conn)
    _statement(conn, "CORNER CAFE #4417 OAKTOWN")
    assert _carried(conn) == ["CORNER CAFE WEB"] * 2


def test_nothing_is_carried_onto_a_statement_row_its_own_merchant_rule_decides(conn):
    # a mispaired match must not put one merchant's category on a row another merchant's rule already decides
    set_merchant_rule(conn, 1, merchant_key("CORNER CAFE WEB"), -1, "spending", "Coffee")
    set_merchant_rule(conn, 1, merchant_key("BOOK BARN #4417"), -1, "spending", "Gifts")
    _export(conn)
    _statement(conn, "BOOK BARN #4417")
    assert _overrides(conn) == []
    assert [c.category for c in _live(conn)] == ["Gifts", "Gifts"]


def test_a_one_off_only_override_is_filled_from_the_rule_and_keeps_its_mark(conn):
    set_merchant_rule(conn, 1, merchant_key("CORNER CAFE WEB"), -1, "spending", "Coffee")
    _export(conn)
    first = conn.execute("SELECT id FROM transactions ORDER BY date LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO overrides (transaction_id, user_id, kind, category, one_off, set_at)"
                 " VALUES (?, 1, NULL, NULL, 1, 'then')", (first,))
    conn.commit()
    _statement(conn, "CORNER CAFE #4417 OAKTOWN")
    assert _overrides(conn) == [("spending", "Coffee", 1), ("spending", "Coffee", 0)]
    assert _carried(conn) == ["CORNER CAFE WEB"] * 2
    assert [(c.category, c.one_off) for c in _live(conn)] == [("Coffee", True), ("Coffee", False)]


def _carried_statement(conn):
    set_merchant_rule(conn, 1, merchant_key("CORNER CAFE WEB"), -1, "spending", "Coffee")
    _export(conn)
    _statement(conn, "CORNER CAFE #4417 OAKTOWN")
    return [c.id for c in _live(conn)]


def test_a_merchant_wide_correction_on_a_statement_row_clears_what_was_carried_onto_its_merchant(conn):
    from tracker.corrections import correct_merchant
    first, second = _carried_statement(conn)
    assert correct_merchant(conn, 1, first, "spending", "Groceries") == 2
    assert [c.category for c in _live(conn)] == ["Groceries", "Groceries"]
    assert _overrides(conn) == []


def test_a_correction_of_the_original_merchant_reaches_the_rows_its_decision_was_carried_to(conn):
    from tracker.corrections import correct_merchant
    _carried_statement(conn)
    accept_batch(conn, 1, batch([("2026-02-03", -450, "CORNER CAFE WEB")], kind="activity",
                                start="2026-02-03", end="2026-02-03"), b"act2", "a2.csv")
    later = next(c.id for c in classify(conn, 1) if c.date == "2026-02-03")
    correct_merchant(conn, 1, later, "spending", "Groceries")
    assert [c.category for c in _live(conn) if c.date < "2026-02"] == ["Groceries", "Groceries"]
    assert _carried(conn) == ["CORNER CAFE WEB"] * 2


def test_changing_a_carried_override_by_hand_makes_it_the_owners_own(conn):
    from tracker.corrections import correct_merchant, set_override
    first, second = _carried_statement(conn)
    set_override(conn, 1, first, category="Eating out")
    set_override(conn, 1, second, one_off=True)   # a one-off mark alone leaves the carried decision carried
    assert _carried(conn) == [None, "CORNER CAFE WEB"]
    correct_merchant(conn, 1, second, "spending", "Groceries")
    assert [(c.category, c.one_off) for c in _live(conn)] == [("Eating out", False), ("Groceries", True)]
