from dataclasses import replace
import sqlite3
import pytest
from connectors.batch import AccountRef, StatementBatch, Txn, FORMAT_VERSION, make_uids
from tracker.store import open_db, open_readonly, accept_batch, ensure_account
import tracker.store

ACCT = AccountRef("acct-x", "Test", "chequing", "Testbank")

def batch(rows, kind="statement", opening=0, start="2026-01-01", end="2026-01-31"):
    uids = make_uids(ACCT.key, rows)
    txns = tuple(Txn(d, a, s, u) for (d, a, s), u in zip(rows, uids))
    closing = opening + sum(a for _, a, _ in rows)
    if kind == "activity":
        opening = closing = None
    return StatementBatch(FORMAT_VERSION, "test", 1, ACCT, kind, start, end, opening, closing, txns)

@pytest.fixture
def conn(tmp_path):
    return open_db(str(tmp_path / "t.db"))

def count(conn, table): return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

def test_accepts_and_keeps_the_raw_file(conn):
    r = accept_batch(conn, 1, batch([("2026-01-05", -450, "SHOP")]), b"raw-bytes", "jan.csv")
    assert (r.status, r.added, r.already_held) == ("accepted", 1, 0)
    row = conn.execute("SELECT raw, source_name FROM batches").fetchone()
    assert (bytes(row["raw"]), row["source_name"]) == (b"raw-bytes", "jan.csv")
    assert conn.execute("SELECT provisional FROM transactions").fetchone()[0] == 0

def test_same_file_twice_is_a_duplicate(conn):
    b = batch([("2026-01-05", -450, "SHOP")])
    accept_batch(conn, 1, b, b"same", "a.csv")
    r = accept_batch(conn, 1, b, b"same", "a-again.csv")
    assert r.status == "duplicate" and count(conn, "transactions") == 1 and count(conn, "batches") == 1

def test_overlapping_export_adds_only_what_is_new(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "SHOP"), ("2026-01-06", -100, "CAFE")], kind="activity",
                                start="2026-01-05", end="2026-01-06"), b"one", "a.csv")
    r = accept_batch(conn, 1, batch([("2026-01-06", -100, "CAFE"), ("2026-01-07", -200, "FUEL")], kind="activity",
                                    start="2026-01-06", end="2026-01-07"), b"two", "b.csv")
    assert (r.status, r.added, r.already_held) == ("accepted", 1, 1)
    assert count(conn, "transactions") == 3
    assert {x[0] for x in conn.execute("SELECT provisional FROM transactions")} == {1}

def test_a_statement_that_does_not_balance_is_refused_whole(conn):
    bad = replace(batch([("2026-01-05", -450, "SHOP")]), closing_cents=999)
    r = accept_batch(conn, 1, bad, b"bad", "bad.csv")
    assert r.status == "refused" and "balance" in r.message
    assert count(conn, "transactions") == 0 and count(conn, "batches") == 0

def test_account_name_is_not_overwritten(conn):
    a = ensure_account(conn, 1, ACCT)
    conn.execute("UPDATE accounts SET name = 'My name for it' WHERE id = ?", (a,))
    assert ensure_account(conn, 1, replace(ACCT, name="Other")) == a
    assert conn.execute("SELECT name FROM accounts").fetchone()[0] == "My name for it"

def test_a_failure_part_way_leaves_nothing_behind(conn, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("disk gone")
    monkeypatch.setattr(tracker.store, "_insert_transactions", boom)
    with pytest.raises(RuntimeError):
        accept_batch(conn, 1, batch([("2026-01-05", -450, "SHOP")]), b"raw", "a.csv")
    assert count(conn, "batches") == 0 and count(conn, "transactions") == 0
    assert not conn.in_transaction

def test_open_db_is_safe_to_repeat(tmp_path):
    path = str(tmp_path / "t.db")
    open_db(path).close()
    c = open_db(path)
    assert not c.in_transaction
    assert c.execute("SELECT key FROM users WHERE id = 1").fetchone()[0] == "owner"
    assert count(c, "users") == 1
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_open_readonly_cannot_write_and_never_creates(tmp_path):
    path = str(tmp_path / "t.db")
    with pytest.raises(FileNotFoundError):
        open_readonly(path)
    assert list(tmp_path.iterdir()) == []
    open_db(path).close()
    c = open_readonly(path)
    assert c.execute("SELECT key FROM users WHERE id = 1").fetchone()["key"] == "owner"
    with pytest.raises(sqlite3.OperationalError):
        c.execute("INSERT INTO users (id, key) VALUES (2, 'x')")
    c.close()

def test_a_batch_whose_account_kind_differs_from_the_held_account_is_refused(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "SHOP")]), b"one", "a.txt")
    other = replace(batch([("2026-02-05", -100, "CAFE")], start="2026-02-01", end="2026-02-28"),
                    account=replace(ACCT, kind="card"))
    r = accept_batch(conn, 1, other, b"two", "b.txt")
    assert (r.status, r.batch_id, r.added) == ("refused", None, 0)
    assert "card" in r.message and "chequing" in r.message and ACCT.key in r.message
    assert count(conn, "batches") == 1 and count(conn, "transactions") == 1
    assert [tuple(r) for r in conn.execute("SELECT kind FROM accounts")] == [("chequing",)]
    assert not conn.in_transaction

def test_a_constraint_failure_other_than_the_uid_rolls_the_batch_back(conn, monkeypatch):
    monkeypatch.setattr(tracker.store, "check_batch", lambda b: [])  # let a bad row reach the database
    b = batch([("2026-01-05", -450, "SHOP"), ("2026-01-06", -100, "CAFE")], kind="activity")
    bad = replace(b, transactions=(b.transactions[0], replace(b.transactions[1], description=None)))
    with pytest.raises(sqlite3.IntegrityError):
        accept_batch(conn, 1, bad, b"raw", "a.csv")
    assert count(conn, "batches") == 0 and count(conn, "transactions") == 0
    assert not conn.in_transaction

def test_a_statement_row_that_is_not_stored_rolls_the_statement_back(conn, monkeypatch):
    monkeypatch.setattr(tracker.store, "check_batch", lambda b: [])
    b = batch([("2026-01-05", -450, "SHOP")] * 3)
    same_uid = tuple(replace(t, uid=b.transactions[0].uid) for t in b.transactions)
    with pytest.raises(RuntimeError, match="not stored"):
        accept_batch(conn, 1, replace(b, transactions=same_uid), b"raw", "s.txt")
    assert count(conn, "batches") == 0 and count(conn, "transactions") == 0
    assert not conn.in_transaction


def _version(path):
    c = sqlite3.connect(path)
    try:
        return c.execute("PRAGMA user_version").fetchone()[0]
    finally:
        c.close()

def _stamp(path, version):
    c = sqlite3.connect(path)
    c.execute(f"PRAGMA user_version = {version}")
    c.close()

def test_a_new_ledger_is_stamped_with_the_schema_version(tmp_path):
    path = str(tmp_path / "t.db")
    open_db(path).close()
    assert _version(path) == tracker.store.SCHEMA_VERSION == 5

def test_an_unversioned_ledger_with_the_current_tables_upgrades_and_keeps_its_rows(tmp_path):
    path = str(tmp_path / "t.db")
    c = sqlite3.connect(path)
    c.executescript(tracker.store.SCHEMA.read_text())
    c.execute("INSERT INTO users (id, key) VALUES (1, 'owner')")
    c.execute("INSERT INTO accounts (user_id, key, name, kind, institution) VALUES (1, 'a', 'A', 'chequing', 'B')")
    c.commit()
    c.close()
    assert _version(path) == 0
    conn = open_db(path)
    assert [tuple(r) for r in conn.execute("SELECT key, kind FROM accounts")] == [("a", "chequing")]
    assert count(conn, "users") == 1
    conn.close()
    assert _version(path) == tracker.store.SCHEMA_VERSION

def test_a_ledger_newer_than_the_code_is_refused(tmp_path):
    path = str(tmp_path / "t.db")
    open_db(path).close()
    _stamp(path, tracker.store.SCHEMA_VERSION + 1)
    with pytest.raises(RuntimeError, match="newer"):
        open_db(path)
    assert _version(path) == tracker.store.SCHEMA_VERSION + 1

def test_a_failing_migration_leaves_the_ledger_at_its_version(tmp_path, monkeypatch):
    path = str(tmp_path / "t.db")
    open_db(path).close()
    held = tracker.store.SCHEMA_VERSION
    monkeypatch.setattr(tracker.store, "SCHEMA_VERSION", held + 1)
    monkeypatch.setattr(tracker.store, "MIGRATIONS",
                        [*tracker.store.MIGRATIONS, lambda: "CREATE TABLE extra (x); SELECT nonsense(;"])
    with pytest.raises(sqlite3.Error):
        open_db(path)
    assert _version(path) == held
    c = sqlite3.connect(path)
    assert c.execute("SELECT name FROM sqlite_master WHERE name = 'extra'").fetchall() == []
    c.close()

@pytest.mark.parametrize("version", [0, tracker.store.SCHEMA_VERSION - 1, tracker.store.SCHEMA_VERSION + 1])
def test_open_readonly_refuses_a_ledger_at_another_version(tmp_path, version):
    from tracker.store import LedgerNeedsUpgrade
    path = str(tmp_path / "t.db")
    open_db(path).close()
    _stamp(path, version)
    with pytest.raises(LedgerNeedsUpgrade):
        open_readonly(path)


def test_a_version_1_ledger_upgrades_and_keeps_overrides(tmp_path):
    path = str(tmp_path / "t.db")
    raw = sqlite3.connect(path)
    raw.executescript(tracker.store.SCHEMA.read_text() + "PRAGMA user_version = 1;")
    raw.execute("INSERT INTO users (id, key) VALUES (1, 'owner')")
    raw.execute("INSERT INTO accounts (id, user_id, key, name, kind, institution) VALUES (1, 1, 'a', 'A', 'card', 'B')")
    raw.execute("INSERT INTO batches (id, user_id, account_id, connector, connector_version, format_version, kind,"
                " period_start, period_end, source_name, sha256, raw, received_at)"
                " VALUES (1, 1, 1, 't', 1, 1, 'activity', '2026-01-01', '2026-01-31', 'f', 'h', x'00', 'now')")
    raw.execute("INSERT INTO transactions (id, user_id, account_id, batch_id, uid, date, amount_cents, description,"
                " provisional) VALUES (7, 1, 1, 1, 'u', '2026-01-05', -450, 'SHOP', 1)")
    raw.execute("INSERT INTO overrides (transaction_id, category) VALUES (7, 'Coffee')")
    raw.commit(); raw.close()
    conn = open_db(path)
    try:
        assert _version(path) == tracker.store.SCHEMA_VERSION
        assert tuple(conn.execute("SELECT transaction_id, user_id, kind, category, one_off, set_at, carried_key"
                                  " FROM overrides").fetchone()) == (7, 1, None, "Coffee", None, "", None)
        assert tuple(conn.execute("SELECT flip_sign, export_note FROM accounts").fetchone()) == (0, "")
        conn.execute("SELECT merchant_key FROM rules"); conn.execute("SELECT matched_id FROM transactions")
        conn.execute("SELECT month, reviewed_at, income_cents, spending_cents FROM month_reviews WHERE user_id = 1")
    finally:
        conn.close()


def test_an_override_with_an_unknown_kind_is_rejected(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st", "s.txt")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO overrides (transaction_id, user_id, kind, set_at) VALUES (1, 1, 'gift', 'now')")


def test_write_tx_holds_the_write_lock_and_rolls_back_on_error(tmp_path):
    path = str(tmp_path / "t.db")
    a = open_db(path)
    other = sqlite3.connect(path, timeout=0)
    try:
        with pytest.raises(RuntimeError):
            with tracker.store.write_tx(a):
                a.execute("INSERT INTO users (id, key) VALUES (2, 'x')")
                with pytest.raises(sqlite3.OperationalError):
                    other.execute("BEGIN IMMEDIATE")
                raise RuntimeError("boom")
        assert a.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    finally:
        other.close()
        a.close()
