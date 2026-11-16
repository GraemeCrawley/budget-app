import pytest

from tracker.store import open_db
from tracker.rules import Rule, add_rule, load_rules, seed_rules


def rule(**kw):
    base = dict(id=None, priority=100, pattern="", account_key=None, sign=None, min_cents=None, max_cents=None,
                date_from=None, date_to=None, kind="spending", category="Groceries", one_off=0,
                origin="owner", label="test")
    return Rule(**{**base, **kw})


def test_rules_load_in_priority_order(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    add_rule(conn, 1, rule(priority=50, label="second"))
    add_rule(conn, 1, rule(priority=10, label="first"))
    assert [r.label for r in load_rules(conn, 1)] == ["first", "second"]


def test_reseeding_replaces_seed_rules_and_keeps_the_owners(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    add_rule(conn, 1, rule(label="mine"))
    seed = [dict(priority=20, pattern="GROCER", kind="spending", category="Groceries", label="grocery stores")]
    assert seed_rules(conn, 1, seed) == 1
    assert seed_rules(conn, 1, seed) == 1
    assert sorted(r.label for r in load_rules(conn, 1)) == ["grocery stores", "mine"]


def test_add_rule_returns_id_and_leaves_no_open_transaction(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    rid = add_rule(conn, 1, rule(label="mine"))
    assert load_rules(conn, 1)[0].id == rid
    assert not conn.in_transaction


def test_bad_pattern_in_add_rule_names_the_label_and_writes_nothing(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    with pytest.raises(ValueError, match="broken one"):
        add_rule(conn, 1, rule(pattern="(", label="broken one"))
    assert load_rules(conn, 1) == []
    assert not conn.in_transaction


def test_bad_pattern_in_seed_leaves_existing_seed_rules_untouched(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    seed_rules(conn, 1, [dict(pattern="GROCER", kind="spending", category="Groceries", label="good")])
    with pytest.raises(ValueError, match="broken seed"):
        seed_rules(conn, 1, [dict(pattern="ok", kind="spending", label="fine"),
                             dict(pattern="[", kind="spending", label="broken seed")])
    assert [r.label for r in load_rules(conn, 1)] == ["good"]
    assert not conn.in_transaction


def test_unknown_kind_is_a_value_error_naming_the_label(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    with pytest.raises(ValueError, match="odd kind"):
        add_rule(conn, 1, rule(kind="gift", label="odd kind"))
    with pytest.raises(ValueError, match="odd seed"):
        seed_rules(conn, 1, [dict(kind="gift", label="odd seed")])
    assert load_rules(conn, 1) == []


def test_a_merchant_rule_needs_a_sign_of_minus_one_or_one(tmp_path):
    from tracker.rules import set_merchant_rule
    conn = open_db(str(tmp_path / "t.db"))
    for sign in (0, 2, None):
        with pytest.raises(ValueError):
            set_merchant_rule(conn, 1, "CORNER CAFE", sign, "spending", "Coffee")
    assert load_rules(conn, 1) == [] and not conn.in_transaction


def test_updating_a_merchant_rule_is_scoped_to_its_user(tmp_path):
    from tracker.rules import set_merchant_rule
    conn = open_db(str(tmp_path / "t.db"))
    with conn:
        conn.execute("INSERT INTO users (id, key) VALUES (2, 'other')")
    mine = set_merchant_rule(conn, 1, "CORNER CAFE", -1, "spending", "Coffee")
    theirs = set_merchant_rule(conn, 2, "CORNER CAFE", -1, "spending", "Coffee")
    statements = []
    conn.set_trace_callback(statements.append)
    assert set_merchant_rule(conn, 2, "CORNER CAFE", -1, "spending", "Eating out") == theirs
    conn.set_trace_callback(None)
    updates = [s for s in statements if s.lstrip().upper().startswith("UPDATE RULES")]
    assert updates and all("user_id = 2" in u.replace("user_id=", "user_id = ") for u in updates)
    assert [r.category for r in load_rules(conn, 1)] == ["Coffee"] and load_rules(conn, 1)[0].id == mine
    assert [r.category for r in load_rules(conn, 2)] == ["Eating out"]
