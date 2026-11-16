import sqlite3
import pytest
from fastapi.testclient import TestClient
from tests.tracker.test_classify import put, CHQ, CARD, SEED
from tracker.store import open_db
from tracker.rules import seed_rules
from tests.tracker.conftest import write_config

@pytest.fixture
def client(tmp_path, monkeypatch, key_for):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    write_config(tmp_path, "report")
    conn = open_db(str(tmp_path / "tracker.db"))
    seed_rules(conn, 1, SEED)
    put(conn, CHQ, [("2026-01-15", 300000, "EMPLOYER PAY"), ("2026-01-02", -200000, "LANDLORD")], "chq")
    put(conn, CARD, [("2026-01-05", -4500, "INVENTED GROCER 12"), ("2026-01-22", -999, "UNKNOWN PLACE")], "card")
    conn.close()
    from tracker.server import create_app
    return TestClient(create_app(key_for=key_for))

def test_months(client):
    body = client.get("/api/v1/months").json()
    (m,) = body["months"]
    assert (m["month"], m["income_cents"], m["spending_cents"]) == ("2026-01", 300000, 205499)
    assert m["savings_rate"] == round((300000 - 205499) / 300000, 4)
    assert body["data_through"] == {"chq": "2026-01-31", "card": "2026-01-31"}

def test_each_month_says_what_its_groups_are_made_of(client):
    (m,) = client.get("/api/v1/months").json()["months"]
    assert m["categories"] == {"Bills": {"Rent": 200000}, "Food": {"Groceries": 4500},
                               "Everything else": {"Uncategorised": 999}}


def test_one_month_with_categories(client):
    body = client.get("/api/v1/months/2026-01").json()
    assert [(c["category"], c["block"], c["cents"]) for c in body["categories"]] == \
           [("Rent", "Bills", 200000), ("Groceries", "Food", 4500), ("Uncategorised", "Everything else", 999)]
    assert client.get("/api/v1/months/2031-01").status_code == 404
    assert client.get("/api/v1/months/january").status_code == 422

def test_transactions_filter(client):
    food = client.get("/api/v1/transactions", params={"month": "2026-01", "block": "Food"}).json()["transactions"]
    assert [(t["amount_cents"], t["category"], t["why"]) for t in food] == [(-4500, "Groceries", "rule: grocery stores")]
    assert len(client.get("/api/v1/transactions", params={"month": "2026-01"}).json()["transactions"]) == 4
    assert client.get("/api/v1/transactions", params={"month": "january"}).status_code == 422

def test_transactions_without_a_month_are_every_charge_newest_first(client):
    rows = client.get("/api/v1/transactions").json()["transactions"]
    assert [t["date"] for t in rows] == ["2026-01-22", "2026-01-15", "2026-01-05", "2026-01-02"]

def test_coverage(client):
    accounts = client.get("/api/v1/coverage").json()["accounts"]
    assert {a["key"]: a["data_through"] for a in accounts} == {"chq": "2026-01-31", "card": "2026-01-31"}
    chq = next(a for a in accounts if a["key"] == "chq")
    assert chq["ranges"] == [["2026-01-01", "2026-01-31"]]

def test_missing_data_directory_is_a_503(client, monkeypatch):
    monkeypatch.delenv("GB_DATA_DIR")  # no data directory means no login config either: the server fails closed
    r = client.get("/api/v1/months")
    assert (r.status_code, r.json()) == (503, {"detail": "login check not configured"})

def test_the_router_alone_serves_nothing_without_the_login_middleware(client):
    from fastapi import FastAPI
    bare = FastAPI()
    import tracker.api as api
    bare.include_router(api.router)
    assert TestClient(bare).get("/api/v1/months").status_code == 401

def test_data_directory_that_is_not_a_directory_is_a_503(client, monkeypatch, tmp_path):
    f = tmp_path / "afile"
    f.write_text("x")
    monkeypatch.setenv("GB_DATA_DIR", str(f))
    for url in ("/api/v1/months", "/api/v1/months/2026-01", "/api/v1/coverage"):
        assert client.get(url).status_code == 503
    assert client.get("/api/v1/transactions", params={"month": "2026-01"}).status_code == 503

def test_month_13_and_malformed_months_are_422(client):
    assert client.get("/api/v1/months/2026-13").status_code == 422
    assert client.get("/api/v1/months/2026-00").status_code == 422
    assert client.get("/api/v1/transactions", params={"month": "2026-13"}).status_code == 422
    assert client.get("/api/v1/transactions", params={"month": "2026-1"}).status_code == 422

def test_unknown_block_is_422_and_unknown_category_is_empty(client):
    assert client.get("/api/v1/transactions", params={"month": "2026-01", "block": "Nope"}).status_code == 422
    r = client.get("/api/v1/transactions", params={"month": "2026-01", "category": "Nope"})
    assert (r.status_code, r.json()) == (200, {"transactions": []})

def test_category_filter(client):
    rows = client.get("/api/v1/transactions", params={"month": "2026-01", "category": "Rent"}).json()["transactions"]
    assert [(t["description"], t["block"]) for t in rows] == [("LANDLORD", "Bills")]

def test_non_spending_rows_have_no_block_and_miss_block_filters(client, tmp_path):
    conn = open_db(str(tmp_path / "tracker.db"))
    put(conn, CHQ, [("2026-01-16", -50000, "INVEST CO"), ("2026-01-18", -30000, "CARD PYMT 000")], "extra")
    put(conn, CARD, [("2026-01-17", 30000, "PAYMENT RECEIVED")], "extra2")
    conn.close()
    rows = client.get("/api/v1/transactions", params={"month": "2026-01"}).json()["transactions"]
    assert {t["kind"] for t in rows} >= {"income", "transfer", "saving"}
    for t in rows:
        if t["kind"] in ("income", "transfer", "saving"):
            assert t["block"] is None
    assert [t["date"] for t in rows] == sorted((t["date"] for t in rows), reverse=True)
    for block in ("Food", "Bills", "Subscriptions", "Big purchases", "Buckets", "Everything else"):
        got = client.get("/api/v1/transactions", params={"month": "2026-01", "block": block}).json()["transactions"]
        assert all(t["kind"] in ("spending", "bucket", "offset") and t["block"] == block for t in got)

def test_categories_add_up_to_block_totals(client, tmp_path):
    conn = open_db(str(tmp_path / "tracker.db"))
    put(conn, CHQ, [("2026-01-03", 80000, "E-TRANSFER HOUSEMATE"), ("2026-01-04", -200000, "LANDLORD"),
                    ("2026-01-05", 300000, "EMPLOYER PAY")], "chq2")
    put(conn, CARD, [("2026-01-06", -4500, "INVENTED GROCER 12"), ("2026-01-08", 500, "INVENTED GROCER 12")], "card2")
    conn.close()
    for ym in ("2026-01",):
        body = client.get(f"/api/v1/months/{ym}").json()
        sums = {}
        for c in body["categories"]:
            sums[c["block"]] = sums.get(c["block"], 0) + c["cents"]
        assert {b: v for b, v in body["blocks"].items() if v} == {b: v for b, v in sums.items() if v}
    feb = client.get("/api/v1/months/2026-01").json()
    rent = next(c for c in feb["categories"] if c["category"] == "Rent")
    assert (rent["cents"], rent["count"]) == (320000, 3)

def test_no_ledger_yet_is_a_503_and_creates_nothing(tmp_path, monkeypatch, key_for):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("GB_DATA_DIR", str(empty))
    write_config(empty, "report")
    from tracker.server import create_app
    c = TestClient(create_app(key_for=key_for))
    urls = [("/api/v1/months", {}), ("/api/v1/months/2026-01", {}), ("/api/v1/coverage", {}),
            ("/api/v1/transactions", {"month": "2026-01"})]
    for url, params in urls:
        r = c.get(url, params=params)
        assert (r.status_code, r.json()) == (503, {"detail": "no ledger yet"})
    assert [p.name for p in empty.iterdir()] == ["access.json"]

class _Spy:
    """Wraps a connection, delegating everything and noting whether close() was called."""
    def __init__(self, conn):
        self._conn = conn
        self.closed = False
    def close(self):
        self.closed = True
        self._conn.close()
    def __getattr__(self, name):
        return getattr(self._conn, name)

@pytest.fixture
def handed_out(client, monkeypatch):
    import tracker.api as api
    conns = []
    real = api.open_readonly
    def spy(path):
        conns.append(_Spy(real(path)))
        return conns[-1]
    monkeypatch.setattr(api, "open_readonly", spy)
    return conns

def _assert_all_closed(conns):
    assert conns
    assert [c.closed for c in conns] == [True] * len(conns)

def test_every_endpoint_closes_its_connection(client, handed_out):
    assert client.get("/api/v1/months").status_code == 200
    assert client.get("/api/v1/months/2026-01").status_code == 200
    assert client.get("/api/v1/months/2031-01").status_code == 404
    assert client.get("/api/v1/months/2026-13").status_code == 422
    assert client.get("/api/v1/transactions", params={"month": "2026-01"}).status_code == 200
    assert client.get("/api/v1/transactions", params={"month": "2026-01", "block": "Nope"}).status_code == 422
    assert client.get("/api/v1/coverage").status_code == 200
    assert len(handed_out) == 5
    _assert_all_closed(handed_out)

def test_a_failing_handler_still_closes_its_connection(client, handed_out, monkeypatch):
    import tracker.api as api
    def boom(*a, **k): raise RuntimeError("boom")
    monkeypatch.setattr(api, "month_facts", boom)
    monkeypatch.setattr(api, "classify", boom)
    monkeypatch.setattr(api, "coverage", boom)
    for url, params in [("/api/v1/months", {}), ("/api/v1/months/2026-01", {}), ("/api/v1/coverage", {}),
                        ("/api/v1/transactions", {"month": "2026-01"})]:
        with pytest.raises(RuntimeError):
            client.get(url, params=params)
    assert len(handed_out) == 4
    _assert_all_closed(handed_out)

def test_a_ledger_that_needs_upgrading_is_a_503(client, tmp_path):
    c = sqlite3.connect(tmp_path / "tracker.db")
    c.execute("PRAGMA user_version = 0")
    c.close()
    for url, params in [("/api/v1/months", {}), ("/api/v1/months/2026-01", {}), ("/api/v1/coverage", {}),
                        ("/api/v1/transactions", {"month": "2026-01"})]:
        r = client.get(url, params=params)
        assert (r.status_code, r.json()) == (503, {"detail": "ledger needs upgrading"})

def test_unconfirmed_income_and_guessed_rows_are_exposed(client, tmp_path):
    conn = open_db(str(tmp_path / "tracker.db"))
    put(conn, CHQ, [("2026-01-20", 1234, "MYSTERY DEPOSIT")], "extra")
    conn.close()
    (m,) = client.get("/api/v1/months").json()["months"]
    assert m["unconfirmed_income_count"] == 1
    assert client.get("/api/v1/months/2026-01").json()["unconfirmed_income_count"] == 1
    rows = client.get("/api/v1/transactions", params={"month": "2026-01"}).json()["transactions"]
    assert {t["description"]: t["guessed"] for t in rows} == {
        "EMPLOYER PAY": False, "LANDLORD": False, "INVENTED GROCER 12": False,
        "UNKNOWN PLACE": True, "MYSTERY DEPOSIT": True}

def test_one_month_classifies_once(client, monkeypatch):
    import tracker.api as api
    import tracker.months as months
    calls = []
    def counting(real):
        def wrapped(*a, **k):
            calls.append(1)
            return real(*a, **k)
        return wrapped
    monkeypatch.setattr(api, "classify", counting(api.classify))
    monkeypatch.setattr(months, "classify", counting(months.classify))
    assert client.get("/api/v1/months/2026-01").status_code == 200
    assert len(calls) == 1
