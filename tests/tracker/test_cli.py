import json
import sqlite3
from pathlib import Path

from tracker.cli import main
from tracker.rules import Rule, add_rule

FX = Path(__file__).parent.parent / "fixtures" / "connectors"


def test_ingest_seed_check(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    assert main(["ingest", str(FX / "cibc_statement.txt"), str(FX / "amex_statement.txt")]) == 0
    assert main(["ingest", str(FX / "cibc_statement.txt")]) == 0          # duplicate is not a failure
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps([dict(pattern="GROCER", kind="spending", category="Groceries", label="grocery stores")]))
    assert main(["seed", str(rules)]) == 0
    assert main(["check"]) == 0
    out = capsys.readouterr().out
    assert "cibc_statement.txt: accepted added=4" in out and "duplicate" in out and "seeded 1 rules" in out
    assert "2026-02 complete=no" in out
    assert "$" not in out and "INVENTED" not in out


def test_unrecognised_file_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    junk = tmp_path / "junk.bin"; junk.write_bytes(b"\x00\x01")
    assert main(["ingest", str(junk)]) == 1


def test_data_dir_unset_is_a_loud_error(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GB_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["ingest", str(FX / "cibc_statement.txt")]) != 0
    assert main(["check"]) != 0
    assert "GB_DATA_DIR" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_data_dir_not_a_directory_is_a_loud_error(tmp_path, monkeypatch):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path / "missing"))
    assert main(["check"]) != 0
    assert not (tmp_path / "missing").exists()


def test_statement_that_does_not_balance_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    altered = tmp_path / "unbalanced.txt"
    text = (FX / "cibc_statement.txt").read_text()
    altered.write_text(text.replace("$2,420.00", "$2,421.00"))   # the closing balance no longer follows
    assert main(["ingest", str(altered), str(FX / "amex_statement.txt")]) == 1
    out = capsys.readouterr().out
    assert "unbalanced.txt: refused" in out
    assert "amex_statement.txt: accepted" in out
    assert "2,42" not in out and "242" not in out and "INVENTED" not in out


def test_account_option_routes_an_activity_csv(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    assert main(["ingest", str(FX / "activity_generic.csv"), "--account", "test-visa", "--new-account", "card"]) == 0
    assert "activity_generic.csv: accepted added=3" in capsys.readouterr().out
    conn = sqlite3.connect(tmp_path / "tracker.db")
    assert conn.execute("SELECT key, kind FROM accounts").fetchall() == [("test-visa", "card")]


def test_activity_csv_without_account_is_unrecognised(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    assert main(["ingest", str(FX / "activity_generic.csv")]) == 1
    assert "activity_generic.csv: unrecognised" in capsys.readouterr().out


def test_seed_with_an_invalid_pattern_leaves_rules_untouched(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    good = tmp_path / "good.json"
    good.write_text(json.dumps([dict(pattern="GROCER", kind="spending", category="Groceries", label="grocery stores")]))
    assert main(["seed", str(good)]) == 0
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([dict(pattern="SHOP", kind="spending", category="Shopping", label="shops"),
                               dict(pattern="(unclosed", kind="spending", category="Other", label="broken rule")]))
    assert main(["seed", str(bad)]) != 0
    err = capsys.readouterr().err
    assert "broken rule" in err and "(unclosed" not in err
    conn = sqlite3.connect(tmp_path / "tracker.db")
    assert conn.execute("SELECT label FROM rules").fetchall() == [("grocery stores",)]


def test_check_prints_one_line_per_month(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    main(["ingest", str(FX / "activity_generic.csv"), "--account", "test-visa", "--new-account", "card"])
    capsys.readouterr()
    assert main(["check"]) == 0
    assert capsys.readouterr().out == "2026-04 complete=no provisional=yes uncategorised=3 unconfirmed_income=0\n"


def _owner_rules(tmp_path):
    conn = sqlite3.connect(tmp_path / "tracker.db")
    return conn.execute("SELECT merchant_key, sign, kind, category, label, priority, pattern FROM rules"
                        " WHERE origin = 'owner' ORDER BY id").fetchall()


def _write(path, obj):
    path.write_text(json.dumps(obj))
    return str(path)


def test_owner_rules_from_confirmed_merchants(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    merchants = tmp_path / "merchants.json"
    assert main(["owner-rules", _write(merchants, {"CORNER CAFE": "Coffee", "BOOK BARN": "Shopping",
                                                   "   ": "Coffee"})]) == 0
    assert capsys.readouterr().out == "added 2 owner rules, 0 already present, 0 updated, 1 skipped\n"
    assert _owner_rules(tmp_path) == [
        ("CORNER CAFE", -1, "spending", "Coffee", "you said CORNER CAFE", 500, ""),
        ("BOOK BARN", -1, "spending", "Shopping", "you said BOOK BARN", 500, "")]


def test_owner_rules_rerun_adds_new_and_updates_changed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    merchants = tmp_path / "merchants.json"
    main(["owner-rules", _write(merchants, {"CORNER CAFE": "Coffee", "BOOK BARN": "Groceries"})])
    capsys.readouterr()
    assert main(["owner-rules", _write(merchants, {"CORNER CAFE": "Coffee", "BOOK BARN": "Dining & delivery",
                                                   "INVENTED BAR": "Bars & alcohol"})]) == 0
    assert capsys.readouterr().out == "added 1 owner rules, 1 already present, 1 updated, 0 skipped\n"
    assert [(r[0], r[3]) for r in _owner_rules(tmp_path)] == [
        ("CORNER CAFE", "Coffee"), ("BOOK BARN", "Dining & delivery"), ("INVENTED BAR", "Bars & alcohol")]
    before = _owner_rules(tmp_path)
    main(["owner-rules", str(merchants)])
    assert _owner_rules(tmp_path) == before


def test_an_old_anchored_owner_rule_is_replaced_not_doubled(tmp_path, monkeypatch, capsys):
    from tracker.store import open_db
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    conn = open_db(str(tmp_path / "tracker.db"))
    add_rule(conn, 1, Rule(id=None, priority=500, pattern=r"^\s*CORNER\ CAFE", account_key=None, sign=-1,
                           min_cents=None, max_cents=None, date_from=None, date_to=None, kind="spending",
                           category="Coffee", one_off=0, origin="owner", label="you confirmed this merchant"))
    conn.close()
    assert main(["owner-rules", _write(tmp_path / "m.json", {"CORNER CAFE": "Coffee"})]) == 0
    got = _owner_rules(tmp_path)
    assert len(got) == 1 and got[0][0] == "CORNER CAFE" and got[0][6] == ""


def test_owner_merchant_rule_matches_every_charge_from_the_merchant(tmp_path, monkeypatch):
    from tests.tracker.test_classify import CHQ, put
    from tracker.classify import classify
    from tracker.store import open_db
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    conn = open_db(str(tmp_path / "tracker.db"))
    put(conn, CHQ, [("2026-01-02", -100, "RETAIL PURCHASE 000111222 CORNER CAFE"),
                    ("2026-01-03", -200, "Point of Sale  corner cafe #4417"),
                    ("2026-01-04", -300, "BOOK BARN"),
                    ("2026-01-06", 500, "CORNER CAFE REFUND")], "chq")  # money in is never made spending
    main(["owner-rules", _write(tmp_path / "m.json", {"CORNER CAFE": "Coffee"})])
    got = [(c.amount_cents, c.kind, c.category) for c in classify(conn, 1)]
    assert got == [(-100, "spending", "Coffee"), (-200, "spending", "Coffee"),
                   (-300, "spending", "Uncategorised"), (500, "income", "")]


def test_owner_rules_refuse_a_document_that_is_not_a_merchant_mapping(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    for bad in (["INVENTED CAFE", "Coffee"], {"INVENTED CAFE": 3}, "Coffee"):
        assert main(["owner-rules", _write(tmp_path / "bad.json", bad)]) != 0
        assert "merchant" in capsys.readouterr().err
    (tmp_path / "bad.json").write_text("{not json")
    assert main(["owner-rules", str(tmp_path / "bad.json")]) != 0
    assert _owner_rules(tmp_path) == []


def test_owner_rules_survive_reseeding(tmp_path, monkeypatch):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    main(["owner-rules", _write(tmp_path / "m.json", {"CORNER CAFE": "Coffee"})])
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps([dict(pattern="GROCER", kind="spending", category="Groceries", label="grocery stores")]))
    main(["seed", str(rules)])
    assert len(_owner_rules(tmp_path)) == 1


def test_account_option_does_not_refile_a_statement(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    assert main(["ingest", str(FX / "cibc_statement.txt"), str(FX / "activity_generic.csv"),
                 "--account", "test-visa", "--new-account", "card"]) == 0
    conn = sqlite3.connect(tmp_path / "tracker.db")
    held = conn.execute("SELECT a.key, a.kind, COUNT(t.id) FROM accounts a LEFT JOIN transactions t"
                        " ON t.account_id = a.id GROUP BY a.id ORDER BY a.key").fetchall()
    assert held == [("cibc-chequing", "chequing", 4), ("test-visa", "card", 3)]


def test_account_option_on_a_held_key_uses_its_stored_kind(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    assert main(["ingest", str(FX / "activity_generic.csv"), "--account", "test-pot", "--new-account", "savings"]) == 0
    altered = tmp_path / "later.csv"
    altered.write_text((FX / "activity_generic.csv").read_text().replace("2026-04", "2026-05"))
    assert main(["ingest", str(altered), "--account", "test-pot"]) == 0
    assert "later.csv: accepted added=3" in capsys.readouterr().out
    conn = sqlite3.connect(tmp_path / "tracker.db")
    assert conn.execute("SELECT key, kind FROM accounts").fetchall() == [("test-pot", "savings")]


def test_account_option_on_an_unknown_key_is_refused_without_a_kind(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    assert main(["ingest", str(FX / "activity_generic.csv"), str(FX / "cibc_statement.txt"),
                 "--account", "test-vsia"]) == 1
    out = capsys.readouterr().out
    assert "activity_generic.csv: refused" in out and "test-vsia" in out and "--new-account" in out
    assert "cibc_statement.txt: accepted" in out
    conn = sqlite3.connect(tmp_path / "tracker.db")
    assert conn.execute("SELECT key FROM accounts").fetchall() == [("cibc-chequing",)]


def test_new_account_kind_must_be_a_known_kind(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    with pytest.raises(SystemExit):
        main(["ingest", str(FX / "activity_generic.csv"), "--account", "x", "--new-account", "wallet"])


def test_a_file_with_no_transactions_fails_as_unrecognised(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    empty = tmp_path / "abc-Rainy_DaymonthlystatementtransactionsXX0000000CAD20260201.csv"
    empty.write_text('"date","transaction","description","amount","balance","currency"\n')
    assert main(["ingest", str(empty)]) == 1
    assert capsys.readouterr().out == f"{empty.name}: unrecognised\n"


def test_a_file_a_connector_chokes_on_fails_without_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    short = tmp_path / "abc-Rainy_DaymonthlystatementtransactionsXX0000000CAD20260201.csv"
    short.write_text('"date","transaction","description","amount","balance","currency"\n"2026-01-02","DEP"\n')
    assert main(["ingest", str(short), str(FX / "cibc_statement.txt")]) == 1
    out = capsys.readouterr().out
    assert f"{short.name}: unrecognised" in out and "cibc_statement.txt: accepted" in out


def test_a_missing_or_unreadable_path_fails_that_file_and_the_rest_still_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    folder = tmp_path / "a-folder"
    folder.mkdir()
    assert main(["ingest", str(tmp_path / "missing.txt"), str(folder), str(FX / "cibc_statement.txt")]) == 1
    out = capsys.readouterr().out
    assert "missing.txt: could not be read" in out and "a-folder: could not be read" in out
    assert "cibc_statement.txt: accepted" in out


def test_seed_and_owner_rules_with_a_missing_file_fail_plainly(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    assert main(["seed", str(tmp_path / "missing.json")]) == 1
    assert main(["owner-rules", str(tmp_path / "missing.json")]) == 1
    assert main(["seed", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert err.count("could not be read") == 3 and "Traceback" not in err


def test_owner_rules_never_touch_an_in_app_rule_or_a_money_in_rule(tmp_path, monkeypatch, capsys):
    from tracker.rules import OWNER_FIRST, set_merchant_rule
    from tracker.store import open_db
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    conn = open_db(str(tmp_path / "tracker.db"))
    set_merchant_rule(conn, 1, "CORNER CAFE", -1, "spending", "Eating out")  # made in the app
    set_merchant_rule(conn, 1, "BOOK BARN", 1, "income", "")  # a money-in rule
    conn.close()
    before = _owner_rules(tmp_path)
    assert main(["owner-rules", _write(tmp_path / "m.json", {" corner cafe ": "Coffee", "BOOK BARN": "Shopping"})]) == 0
    assert capsys.readouterr().out == "added 2 owner rules, 0 already present, 0 updated, 0 skipped\n"
    got = _owner_rules(tmp_path)
    assert got[:2] == before
    assert before[0][5] == OWNER_FIRST
    assert got[2:] == [("CORNER CAFE", -1, "spending", "Coffee", "you said CORNER CAFE", 500, ""),
                       ("BOOK BARN", -1, "spending", "Shopping", "you said BOOK BARN", 500, "")]
    assert main(["owner-rules", str(tmp_path / "m.json")]) == 0  # a re-run finds its own carried rules
    assert capsys.readouterr().out == "added 0 owner rules, 2 already present, 0 updated, 0 skipped\n"
    assert _owner_rules(tmp_path) == got


def test_owner_rules_refuse_the_apps_own_priority(tmp_path, monkeypatch, capsys):
    from tracker.rules import OWNER_FIRST
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    assert main(["owner-rules", _write(tmp_path / "m.json", {"CORNER CAFE": "Coffee"}),
                 "--priority", str(OWNER_FIRST)]) == 1
    assert "nothing written" in capsys.readouterr().err
    assert _owner_rules(tmp_path) == []


def test_ingest_refuses_activity_for_a_card_whose_signs_are_flipped(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    from tracker.store import open_db
    conn = open_db(str(tmp_path / "tracker.db"))
    with conn:
        conn.execute("INSERT INTO accounts (user_id, key, name, kind, institution, flip_sign)"
                     " VALUES (1, 'test-visa', 'Test card', 'card', 'Bank', 1)")
    conn.close()
    assert main(["ingest", str(FX / "activity_generic.csv"), str(FX / "amex_statement.txt"),
                 "--account", "test-visa"]) == 1
    out = capsys.readouterr().out
    assert "activity_generic.csv: refused: this card's exports are stored with their signs flipped;" \
           " upload this file through the app\n" in out
    assert "amex_statement.txt: accepted" in out
    conn = sqlite3.connect(tmp_path / "tracker.db")
    assert conn.execute("SELECT COUNT(*) FROM batches b JOIN accounts a ON a.id = b.account_id"
                        " WHERE a.key = 'test-visa'").fetchone()[0] == 0


# ---- rekey ----------------------------------------------------------------------------------------

def _rekey_db(tmp_path, monkeypatch, rows):
    """A ledger with one chequing account holding `rows` [(date, cents, description)]."""
    from tests.tracker.test_classify import put, CHQ
    from tracker.store import open_db
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    conn = open_db(str(tmp_path / "tracker.db"))
    put(conn, CHQ, rows, "r")
    return conn


def _rule(conn, key, sign=-1, priority=5, label=None, user=1, category="Transport"):
    from tracker.rules import set_merchant_rule
    rid = set_merchant_rule(conn, user, key, sign, "spending", category, priority=priority)
    if label is not None:
        conn.execute("UPDATE rules SET label = ? WHERE id = ?", (label, rid)); conn.commit()
    return rid


def _keys(conn):
    return [r[0] for r in conn.execute("SELECT merchant_key FROM rules WHERE origin = 'owner' ORDER BY id")]


def test_rekey_moves_a_rule_to_the_new_key_and_is_safe_twice(tmp_path, monkeypatch, capsys):
    conn = _rekey_db(tmp_path, monkeypatch, [("2026-01-02", -100, "FUELCO # 44172 FUELC TORONTO ON"),
                                             ("2026-01-03", -200, "FUELCO # 55283 FUELC TORONTO ON")])
    _rule(conn, "FUELCO # FUELC TORON")
    assert main(["rekey"]) == 0
    assert capsys.readouterr().out.strip() == "rekeyed 1, merged 0, unchanged 0, no charges 0, ambiguous 0, conflicts 0"
    assert _keys(conn) == ["FUELCO FUELC"]
    assert conn.execute("SELECT label FROM rules WHERE origin = 'owner'").fetchone()[0] == "you said FUELCO FUELC"
    assert main(["rekey"]) == 0
    # the rule now holds the new key, which no charge had under the old algorithm: nothing to do
    assert capsys.readouterr().out.strip() == "rekeyed 0, merged 0, unchanged 0, no charges 1, ambiguous 0, conflicts 0"
    assert _keys(conn) == ["FUELCO FUELC"]


def test_rekey_moves_a_rule_keyed_by_the_second_algorithm(tmp_path, monkeypatch, capsys):
    conn = _rekey_db(tmp_path, monkeypatch, [("2026-01-02", -100, "GREEN GROCER TORONTO TORONTO"),
                                             ("2026-01-03", -200, "1100 SIDE ST. WEST TORONTO")])
    _rule(conn, "GREEN GROCER TORONTO")
    _rule(conn, "SIDE ST. WEST TORONT")
    main(["rekey"])
    assert capsys.readouterr().out.strip() == "rekeyed 2, merged 0, unchanged 0, no charges 0, ambiguous 0, conflicts 0"
    assert _keys(conn) == ["GREEN GROCER", "1100 SIDE ST. WEST"]


def test_rekey_counts_a_rule_whose_key_does_not_change(tmp_path, monkeypatch, capsys):
    conn = _rekey_db(tmp_path, monkeypatch, [("2026-01-02", -100, "CORNER CAFE #4417")])
    _rule(conn, "CORNER CAFE")
    main(["rekey"])
    assert capsys.readouterr().out.strip() == "rekeyed 0, merged 0, unchanged 1, no charges 0, ambiguous 0, conflicts 0"


def test_rekey_leaves_a_custom_label_alone(tmp_path, monkeypatch, capsys):
    conn = _rekey_db(tmp_path, monkeypatch, [("2026-01-02", -100, "FUELCO # 44172 FUELC")])
    _rule(conn, "FUELCO # FUELC", label="petrol")
    main(["rekey"])
    assert conn.execute("SELECT merchant_key, label FROM rules WHERE origin = 'owner'").fetchone()[:] == ("FUELCO FUELC", "petrol")


def test_rekey_counts_a_rule_with_no_matching_charges(tmp_path, monkeypatch, capsys):
    conn = _rekey_db(tmp_path, monkeypatch, [("2026-01-02", -100, "CORNER CAFE")])
    _rule(conn, "NOBODY # HERE")
    main(["rekey"])
    assert capsys.readouterr().out.strip() == "rekeyed 0, merged 0, unchanged 0, no charges 1, ambiguous 0, conflicts 0"
    assert _keys(conn) == ["NOBODY # HERE"]


def test_rekey_counts_a_rule_whose_old_key_now_splits_in_two(tmp_path, monkeypatch, capsys):
    # the old key cut at 20 characters; the new key drops the lone "#" first, so the cut falls elsewhere
    conn = _rekey_db(tmp_path, monkeypatch, [("2026-01-02", -100, "LONGMERCHANT # 11111 ABCDE X"),
                                             ("2026-01-03", -200, "LONGMERCHANT # 22222 ABCDE Z")])
    from tracker.merchant import PREVIOUS_KEYS
    first = PREVIOUS_KEYS[0]
    old = first("LONGMERCHANT # 11111 ABCDE X")
    assert old == first("LONGMERCHANT # 22222 ABCDE Z")
    _rule(conn, old)
    main(["rekey"])
    assert capsys.readouterr().out.strip() == "rekeyed 0, merged 0, unchanged 0, no charges 0, ambiguous 1, conflicts 0"
    assert _keys(conn) == [old]


def test_rekey_merges_a_rule_into_one_that_already_says_the_same(tmp_path, monkeypatch, capsys):
    conn = _rekey_db(tmp_path, monkeypatch, [("2026-01-02", -100, "FUELCO # 44172 FUELC")])
    _rule(conn, "FUELCO # FUELC")
    _rule(conn, "FUELCO FUELC")
    main(["rekey"])
    assert capsys.readouterr().out.strip() == "rekeyed 0, merged 1, unchanged 1, no charges 0, ambiguous 0, conflicts 0"
    assert _keys(conn) == ["FUELCO FUELC"]


def test_rekey_leaves_a_rule_alone_when_the_new_key_is_held_with_another_category(tmp_path, monkeypatch, capsys):
    conn = _rekey_db(tmp_path, monkeypatch, [("2026-01-02", -100, "FUELCO # 44172 FUELC")])
    _rule(conn, "FUELCO # FUELC")
    _rule(conn, "FUELCO FUELC", category="Groceries")
    _rule(conn, "FUELCO # FUELC", priority=500)   # another priority: no clash with the held one
    main(["rekey"])
    out = capsys.readouterr().out.strip()
    assert out == "rekeyed 1, merged 0, unchanged 1, no charges 0, ambiguous 0, conflicts 1"
    assert _keys(conn) == ["FUELCO # FUELC", "FUELCO FUELC", "FUELCO FUELC"]


def test_rekey_reads_superseded_rows_and_only_this_users_charges(tmp_path, monkeypatch, capsys):
    conn = _rekey_db(tmp_path, monkeypatch, [("2026-01-02", -100, "FUELCO # 44172 FUELC")])
    conn.execute("UPDATE transactions SET superseded_by = batch_id"); conn.commit()
    _rule(conn, "FUELCO # FUELC")
    main(["rekey"])
    assert _keys(conn) == ["FUELCO FUELC"]
    conn.execute("INSERT INTO users (id, key) VALUES (2, 'other')")
    conn.execute("UPDATE transactions SET user_id = 2")
    conn.execute("UPDATE rules SET merchant_key = 'FUELCO # FUELC'"); conn.commit()
    main(["rekey"])
    assert capsys.readouterr().out.strip().splitlines()[-1] == "rekeyed 0, merged 0, unchanged 0, no charges 1, ambiguous 0, conflicts 0"


def test_rekey_prints_counts_only(tmp_path, monkeypatch, capsys):
    conn = _rekey_db(tmp_path, monkeypatch, [("2026-01-02", -100, "FUELCO # 44172 FUELC")])
    _rule(conn, "FUELCO # FUELC")
    main(["rekey"])
    out = capsys.readouterr().out
    assert "FUELCO" not in out and "$" not in out
