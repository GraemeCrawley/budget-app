"""The correction and review endpoints, through the HTTP client, signed in."""
import pytest
from tests.tracker.test_classify import put, put_feb, CHQ, CARD, SEED
from tests.tracker.conftest import OWNER_EMAIL
from tracker.rules import seed_rules
from tracker.store import open_db


@pytest.fixture
def client(make_client, tmp_path, token):
    c = make_client()
    conn = open_db(str(tmp_path / "tracker.db"))
    seed_rules(conn, 1, SEED)
    put(conn, CHQ, [("2026-01-15", 300000, "EMPLOYER PAY"), ("2026-01-20", 1234, "MYSTERY DEPOSIT")], "chq")
    put(conn, CARD, [("2026-01-05", -4500, "INVENTED GROCER 12"), ("2026-01-22", -999, "UNKNOWN PLACE 4411"),
                     ("2026-01-25", -700, "UNKNOWN PLACE")], "card")
    put_feb(conn, CARD, [("2026-02-03", -1500, "UNKNOWN PLACE"), ("2026-02-04", -250, "RETAIL PURCHASE 123456")], "card2")
    conn.close()
    c.headers["Cf-Access-Jwt-Assertion"] = token(OWNER_EMAIL)
    c.db_path = str(tmp_path / "tracker.db")
    return c


def find(client, description, month="2026-01"):
    rows = client.get("/api/v1/transactions", params={"month": month}).json()["transactions"]
    return next(t for t in rows if t["description"] == description)


def test_transaction_rows_carry_the_full_object(client):
    t = find(client, "INVENTED GROCER 12")
    assert t == {"id": t["id"], "date": "2026-01-05", "amount_cents": -4500, "description": "INVENTED GROCER 12",
                 "account": "card", "account_name": "Card", "kind": "spending", "category": "Groceries",
                 "block": "Food", "one_off": False, "provisional": t["provisional"],
                 "why": "rule: grocery stores", "guessed": False, "merchant": "INVENTED GROCER 12"}


def test_get_one_transaction_counts_the_merchant_charges(client):
    t = find(client, "UNKNOWN PLACE")
    body = client.get(f"/api/v1/transactions/{t['id']}").json()
    assert body["merchant_charges"] == 3
    assert body["merchant"] == "UNKNOWN PLACE" and body["id"] == t["id"]
    blank = find(client, "RETAIL PURCHASE 123456", "2026-02")
    assert client.get(f"/api/v1/transactions/{blank['id']}").json()["merchant_charges"] == 0


def test_categories_include_picker_and_any_in_use(client):
    body = client.get("/api/v1/categories").json()
    assert body["categories"] == sorted(body["categories"])
    assert {"Groceries", "Rent", "Personal care", "Travel"} <= set(body["categories"])
    assert not {"Shopping/home", "Health", "Other"} & set(body["categories"])
    assert "Coffee" in body["categories"]
    t = find(client, "UNKNOWN PLACE")
    assert client.put(f"/api/v1/transactions/{t['id']}/override", json={"category": "Pottery"}).status_code == 200
    body = client.get("/api/v1/categories").json()
    assert "Pottery" in body["categories"] and body["blocks"]["Pottery"] == "Everything else"
    assert body["blocks"]["Groceries"] == "Food" and set(body["blocks"]) == set(body["categories"])


def test_put_override_then_month_totals_move_at_once(client):
    t = find(client, "INVENTED GROCER 12")
    before = client.get("/api/v1/months/2026-01").json()
    r = client.put(f"/api/v1/transactions/{t['id']}/override", json={"kind": "transfer"})
    assert r.status_code == 200
    body = r.json()
    assert (body["kind"], body["block"], body["why"], body["guessed"]) == ("transfer", None, "you set this", False)
    assert "merchant_charges" not in body
    after = client.get("/api/v1/months/2026-01").json()
    assert after["spending_cents"] == before["spending_cents"] - 4500
    r = client.put(f"/api/v1/transactions/{t['id']}/override", json={"kind": None, "category": "Coffee"})
    assert (r.json()["kind"], r.json()["category"]) == ("spending", "Coffee")
    r = client.delete(f"/api/v1/transactions/{t['id']}/override")
    assert (r.status_code, r.json()["category"], r.json()["why"]) == (200, "Groceries", "rule: grocery stores")
    assert client.get("/api/v1/months/2026-01").json()["spending_cents"] == before["spending_cents"]


def test_an_absent_field_is_left_alone_and_null_clears_it(client):
    t = find(client, "UNKNOWN PLACE")
    url = f"/api/v1/transactions/{t['id']}/override"
    client.put(url, json={"category": "Gifts"})
    r = client.put(url, json={"one_off": True})
    assert (r.json()["category"], r.json()["one_off"]) == ("Gifts", True)
    r = client.put(url, json={"category": None})
    assert (r.json()["category"], r.json()["one_off"]) == ("Uncategorised", True)


def test_put_override_rejects_unknown_kind_and_empty_category(client):
    t = find(client, "UNKNOWN PLACE")
    url = f"/api/v1/transactions/{t['id']}/override"
    assert client.put(url, json={"kind": "nonsense"}).status_code == 422
    assert client.put(url, json={"category": ""}).status_code == 422
    assert find(client, "UNKNOWN PLACE")["why"] == "no rule matched"


def test_confirming_income_clears_the_unconfirmed_flag(client):
    t = find(client, "MYSTERY DEPOSIT")
    assert (t["kind"], t["guessed"]) == ("income", True)
    assert client.get("/api/v1/months/2026-01").json()["unconfirmed_income_count"] == 1
    r = client.put(f"/api/v1/transactions/{t['id']}/override", json={"kind": "income"})
    assert (r.json()["kind"], r.json()["guessed"]) == ("income", False)
    assert client.get("/api/v1/months/2026-01").json()["unconfirmed_income_count"] == 0
    assert client.get("/api/v1/review", params={"month": "2026-01"}).json()["unconfirmed_income"] == []


def test_merchant_rule_endpoint_and_its_no_merchant_case(client):
    t = find(client, "UNKNOWN PLACE")
    r = client.post(f"/api/v1/transactions/{t['id']}/merchant-rule",
                    json={"kind": "spending", "category": "Entertainment"})
    assert (r.status_code, r.json()) == (200, {"merchant": "UNKNOWN PLACE", "charges": 3})
    feb = find(client, "UNKNOWN PLACE", "2026-02")
    assert (feb["category"], feb["why"]) == ("Entertainment", "rule: you said UNKNOWN PLACE")
    assert client.post(f"/api/v1/transactions/{t['id']}/merchant-rule",
                       json={"kind": "nonsense", "category": "Other"}).status_code == 422
    blank = find(client, "RETAIL PURCHASE 123456", "2026-02")
    r = client.post(f"/api/v1/transactions/{blank['id']}/merchant-rule", json={"kind": "spending", "category": "Other"})
    assert (r.status_code, r.json()) == (422, {"detail": "no merchant"})


def test_a_spending_merchant_rule_needs_a_category(client):
    t = find(client, "UNKNOWN PLACE")
    url = f"/api/v1/transactions/{t['id']}/merchant-rule"
    for body in ({"kind": "spending"}, {"kind": "bucket", "category": ""}, {"kind": "offset"}):
        assert client.post(url, json=body).status_code == 422
    assert find(client, "UNKNOWN PLACE")["why"] == "no rule matched"
    r = client.post(url, json={"kind": "transfer"})
    assert (r.status_code, r.json()["charges"]) == (200, 3)
    assert (find(client, "UNKNOWN PLACE")["kind"], find(client, "UNKNOWN PLACE")["category"]) == ("transfer", "")


def test_review_endpoint_shape(client):
    r = client.get("/api/v1/review", params={"month": "2026-01"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"month", "unplaced", "unconfirmed_income", "recognised", "reviewed"}
    assert [(g["merchant"], g["count"], g["cents"]) for g in body["unplaced"]] == [("UNKNOWN PLACE", 2, 1699)]
    assert [(g["category"], g["block"], g["cents"]) for g in body["recognised"]] == [("Groceries", "Food", 4500)]
    assert body["recognised"][0]["charges"][0]["first_time"] is True
    every = client.get("/api/v1/review").json()
    assert every["month"] is None and every["recognised"] == []
    assert client.get("/api/v1/review", params={"month": "2026-13"}).status_code == 422


def test_mark_reviewed_is_visible_in_months_and_review(client):
    r = client.post("/api/v1/months/2026-01/reviewed")
    assert (r.status_code, r.json()) == (200, {"month": "2026-01", "reviewed": True})
    m = {x["month"]: x for x in client.get("/api/v1/months").json()["months"]}
    assert (m["2026-01"]["reviewed"], m["2026-01"]["changed_since_review"]) == (True, False)
    assert client.get("/api/v1/review", params={"month": "2026-01"}).json()["reviewed"] is True
    assert client.post("/api/v1/months/2026-13/reviewed").status_code == 422


def test_unknown_or_superseded_transaction_is_404(client):
    t = find(client, "UNKNOWN PLACE")
    for tid in (999999, t["id"]):
        if tid == t["id"]:
            conn = open_db(client.db_path)
            conn.execute("UPDATE transactions SET superseded_by = batch_id WHERE id = ?", (tid,)); conn.commit()
            conn.close()
        assert client.get(f"/api/v1/transactions/{tid}").status_code == 404
        assert client.put(f"/api/v1/transactions/{tid}/override", json={"category": "Other"}).status_code == 404
        assert client.delete(f"/api/v1/transactions/{tid}/override").status_code == 404
        assert client.post(f"/api/v1/transactions/{tid}/merchant-rule",
                           json={"kind": "spending", "category": "Other"}).status_code == 404


def test_writes_without_a_ledger_are_a_503_and_create_nothing(make_client, tmp_path, token):
    c = make_client()
    (tmp_path / "tracker.db").unlink()
    c.headers["Cf-Access-Jwt-Assertion"] = token(OWNER_EMAIL)
    r = c.put("/api/v1/transactions/1/override", json={"category": "Other"})
    assert (r.status_code, r.json()) == (503, {"detail": "no ledger yet"})
    assert not (tmp_path / "tracker.db").exists()


def test_the_write_routes_need_a_login(client):
    client.headers.pop("Cf-Access-Jwt-Assertion")
    assert client.put("/api/v1/transactions/1/override", json={"category": "Other"}).status_code in (401, 403)


def test_a_category_of_his_own_is_trimmed_stored_and_listed(client):
    t = find(client, "UNKNOWN PLACE")
    r = client.put(f"/api/v1/transactions/{t['id']}/override", json={"category": "  Pottery  "})
    assert (r.status_code, r.json()["category"]) == (200, "Pottery")
    assert "Pottery" in client.get("/api/v1/categories").json()["categories"]


def test_a_category_matching_an_existing_one_ignoring_case_takes_its_spelling(client):
    t = find(client, "UNKNOWN PLACE")
    r = client.put(f"/api/v1/transactions/{t['id']}/override", json={"category": " transport"})
    assert r.json()["category"] == "Transport"
    r = client.post(f"/api/v1/transactions/{t['id']}/merchant-rule", json={"kind": "spending", "category": "GROCERIES"})
    assert r.status_code == 200
    assert find(client, "UNKNOWN PLACE")["category"] == "Groceries"
    assert client.get("/api/v1/categories").json()["categories"].count("Groceries") == 1


def test_a_bad_category_name_is_a_plain_422_on_both_routes(client):
    t = find(client, "UNKNOWN PLACE")
    for bad in ("   ", "x" * 41, "bad\x07name", "line\nbreak", "uncategorised", " UNCATEGORISED "):
        r = client.put(f"/api/v1/transactions/{t['id']}/override", json={"category": bad})
        assert r.status_code == 422 and isinstance(r.json()["detail"], str), bad
        r = client.post(f"/api/v1/transactions/{t['id']}/merchant-rule", json={"kind": "spending", "category": bad})
        assert r.status_code == 422 and isinstance(r.json()["detail"], str), bad
    assert find(client, "UNKNOWN PLACE")["why"] == "no rule matched"
    ok = client.put(f"/api/v1/transactions/{t['id']}/override", json={"category": "x" * 40})
    assert ok.status_code == 200


def test_a_write_while_the_ledger_is_busy_is_a_plain_503_not_a_crash(client, monkeypatch):
    import sqlite3
    import tracker.api as api

    def busy(path):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(api, "open_db", busy)
    r = client.post("/api/v1/months/2026-01/reviewed")
    assert (r.status_code, r.json()["detail"]) == (503, "the ledger is busy; try again in a moment")
