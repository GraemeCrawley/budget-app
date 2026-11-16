"""The accounts and upload endpoints, through the HTTP client, signed in."""
import logging
from pathlib import Path

import pytest

from tests.tracker.conftest import OWNER_EMAIL
from tracker.store import open_db

FX = Path(__file__).parent.parent / "fixtures" / "connectors"
API = "/api/v1"
MARCH = (b"Date,Description,Amount\n2026-03-03,INVENTED SHOP,-12.50\n2026-03-15,INVENTED CAFE,-8.00\n"
         b"2026-03-29,INVENTED PAYROLL,300.00\n")


@pytest.fixture
def client(make_client, tmp_path, token):
    c = make_client()
    c.headers["Cf-Access-Jwt-Assertion"] = token(OWNER_EMAIL)
    c.db_path = str(tmp_path / "tracker.db")
    return c


def upload(client, name, data, **form):
    return client.post(f"{API}/uploads", files={"file": (name, data, "application/octet-stream")}, data=form)


def make_account(client, name="Invented Chequing", kind="chequing"):
    r = client.post(f"{API}/accounts", json={"name": name, "kind": kind})
    assert r.status_code == 201, r.text
    return r.json()


def accounts(client):
    return {a["key"]: a for a in client.get(f"{API}/accounts").json()["accounts"]}


def test_upload_then_accounts_show_data_through(client):
    acct = make_account(client)
    assert acct == {"key": "invented-chequing", "name": "Invented Chequing", "kind": "chequing", "institution": "",
                    "export_note": "", "data_through": None, "ranges": [], "flip_sign": 0}
    assert accounts(client)["invented-chequing"] == acct  # an account with no batches is listed
    r = upload(client, "march.csv", MARCH, account_key="invented-chequing")
    assert r.status_code == 200
    body = r.json()
    (b,) = body["batches"]
    assert body == {"ok": True, "batches": [{
        "id": b["id"], "account": "invented-chequing", "account_name": "Invented Chequing", "kind": "activity",
        "period_start": "2026-03-03", "period_end": "2026-03-29", "status": "accepted", "added": 3,
        "already_held": 0, "confirmed": 0, "differences": [], "message": "", "can_widen": True}]}
    a = accounts(client)["invented-chequing"]
    assert (a["data_through"], a["ranges"]) == ("2026-03-29", [["2026-03-03", "2026-03-29"]])
    again = upload(client, "march-again.csv", MARCH, account_key="invented-chequing")
    assert again.status_code == 200 and again.json()["batches"][0]["status"] == "duplicate"
    assert client.get(f"{API}/coverage").json()["accounts"][0]["data_through"] == "2026-03-29"


def test_refusals_are_422_with_exactly_four_keys(client):
    from tracker.uploads import REASONS
    r = upload(client, "export.csv", MARCH)
    assert r.status_code == 422
    assert r.json() == {"ok": False, "code": "account_needed", "reason": REASONS["account_needed"],
                        "needs": {"choose_account": True}}
    r = upload(client, "x.bin", b"hello\n")
    assert r.json() == {"ok": False, "code": "no_format", "reason": REASONS["no_format"], "needs": None}
    make_account(client, "Invented Card", "card")
    r = upload(client, "c.csv", b"Date,Description,Amount\n2026-03-03,INVENTED SHOP,5.00\n", account_key="invented-card")
    assert r.status_code == 422 and r.json()["needs"] == {"choose_signs": True}
    r = upload(client, "c.csv", b"Date,Description,Amount\n2026-03-03,INVENTED SHOP,5.00\n",
               account_key="invented-card", signs="flip")
    assert r.status_code == 200 and accounts(client)["invented-card"]["flip_sign"] == 1
    r = upload(client, "c.csv", MARCH, account_key="invented-card", signs="sideways")
    assert r.status_code == 422


def test_upload_over_10_mb_is_413(client):
    from tracker.uploads import REASONS
    r = upload(client, "big.csv", b"x" * (10 * 1024 * 1024 + 1))
    assert r.status_code == 413
    assert r.json() == {"ok": False, "code": "too_large", "reason": REASONS["too_large"]}
    exactly = upload(client, "edge.bin", b"x" * (10 * 1024 * 1024))  # the limit itself is taken, then not recognised
    assert (exactly.status_code, exactly.json()["code"]) == (422, "no_format")


def test_nothing_about_the_file_is_logged(client, caplog):
    caplog.set_level(logging.DEBUG)
    make_account(client)
    secret = (b"Date,Description,Amount\n2026-03-03,ZEBRAQUILL MERCHANT,-7777.77\n"
              b"2026-03-04,ZEBRAQUILL MERCHANT,not-money-7777\n")
    for body in (secret, secret.split(b"\n2026-03-04")[0] + b"\n", b"%PDF-1.4 ZEBRAQUILL",
                 secret.replace(b"Description", b"Memo")):
        upload(client, "zebraquill-secret-name.csv", body, account_key="invented-chequing")
        upload(client, "zebraquill-secret-name.csv", body)
    for leak in ("zebraquill", "ZEBRAQUILL", "7777", "secret-name"):
        assert leak not in caplog.text


def test_create_account_slugs_the_name_and_refuses_a_repeat(client):
    r = client.post(f"{API}/accounts", json={"name": "  My Visa -- Card!  ", "kind": "card", "institution": "Invented Bank"})
    assert r.status_code == 201
    assert r.json() == {"key": "my-visa-card", "name": "My Visa -- Card!", "kind": "card",
                        "institution": "Invented Bank", "export_note": "", "data_through": None, "ranges": [],
                        "flip_sign": 0}
    r = client.post(f"{API}/accounts", json={"name": "my visa card", "kind": "card"})
    assert (r.status_code, r.json()) == (409, {"detail": "an account with that name already exists"})
    assert client.post(f"{API}/accounts", json={"name": "X", "kind": "loan"}).status_code == 422
    assert client.post(f"{API}/accounts", json={"name": "   ", "kind": "card"}).status_code == 422
    assert client.post(f"{API}/accounts", json={"name": "!!!", "kind": "card"}).status_code == 422
    assert list(accounts(client)) == ["my-visa-card"]


def test_patch_account_note(client):
    make_account(client)
    r = client.patch(f"{API}/accounts/invented-chequing", json={"export_note": "Download from the web site, last 90 days"})
    assert r.status_code == 200
    assert r.json()["export_note"] == "Download from the web site, last 90 days"
    r = client.patch(f"{API}/accounts/invented-chequing", json={"name": "Renamed"})
    assert (r.json()["name"], r.json()["key"], r.json()["export_note"]) == \
        ("Renamed", "invented-chequing", "Download from the web site, last 90 days")
    assert accounts(client)["invented-chequing"]["name"] == "Renamed"
    assert client.patch(f"{API}/accounts/nowhere", json={"export_note": "x"}).status_code == 404
    assert client.patch(f"{API}/accounts/invented-chequing", json={"name": " "}).status_code == 422
    assert client.patch(f"{API}/accounts/invented-chequing", json={}).status_code == 422


def month_complete(client, ym):
    return {m["month"]: m["complete"] for m in client.get(f"{API}/months").json()["months"]}[ym]


def test_widening_an_activity_period_completes_the_month(client):
    make_account(client)
    (b,) = upload(client, "march.csv", MARCH, account_key="invented-chequing").json()["batches"]
    assert month_complete(client, "2026-03") is False
    r = client.patch(f"{API}/batches/{b['id']}/period", json={"period_start": "2026-03-01", "period_end": "2026-03-31"})
    assert r.status_code == 200
    assert r.json() == {**b, "period_start": "2026-03-01", "period_end": "2026-03-31", "can_widen": False,
                        "status": "accepted", "added": 3, "already_held": 0, "confirmed": 0, "differences": [],
                        "message": ""}
    assert month_complete(client, "2026-03") is True
    assert accounts(client)["invented-chequing"]["ranges"] == [["2026-03-01", "2026-03-31"]]


def test_period_cannot_shrink_reach_the_future_or_touch_a_statement(client):
    make_account(client)
    (b,) = upload(client, "march.csv", MARCH, account_key="invented-chequing").json()["batches"]
    url = f"{API}/batches/{b['id']}/period"
    assert client.patch(url, json={"period_start": "2026-03-05", "period_end": "2026-03-29"}).status_code == 422  # shrink
    conn = open_db(client.db_path)
    with conn:
        conn.execute("UPDATE batches SET received_at = '2026-03-30T12:00:00+00:00'")
    conn.close()
    assert client.patch(url, json={"period_start": "2026-03-03", "period_end": "2026-03-31"}).status_code == 422  # future
    (s,) = upload(client, "x.txt", (FX / "cibc_statement.txt").read_bytes()).json()["batches"]
    r = client.patch(f"{API}/batches/{s['id']}/period", json={"period_start": "2026-01-25", "period_end": "2026-02-28"})
    assert r.status_code == 422
    assert client.patch(f"{API}/batches/9999/period", json={"period_start": "2026-03-01", "period_end": "2026-03-31"}
                        ).status_code == 404
    # nothing changed
    assert accounts(client)["invented-chequing"]["ranges"] == [["2026-03-03", "2026-03-29"]]


def test_the_endpoints_need_the_login(make_client):
    c = make_client()
    for method, url in [("get", "/accounts"), ("post", "/accounts"), ("post", "/uploads"),
                        ("patch", "/accounts/x"), ("patch", "/batches/1/period")]:
        assert getattr(c, method)(API + url).status_code == 401


def test_a_declared_length_over_the_limit_is_refused_before_the_body_is_read(client):
    from tracker.uploads import REASONS
    r = client.post(f"{API}/uploads", content=b"x", headers={"Content-Length": str(10 * 1024 * 1024 + 64 * 1024 + 1),
                                                           "Content-Type": "multipart/form-data; boundary=zz"})
    assert r.status_code == 413
    assert r.json() == {"ok": False, "code": "too_large", "reason": REASONS["too_large"]}


def test_a_missing_file_is_422(client):
    assert client.post(f"{API}/uploads", data={"signs": "flip"}).status_code == 422


def test_names_institutions_and_notes_have_length_limits(client):
    assert client.post(f"{API}/accounts", json={"name": "a" * 81, "kind": "card"}).status_code == 422
    assert client.post(f"{API}/accounts", json={"name": "a" * 80, "kind": "card"}).status_code == 201
    assert client.post(f"{API}/accounts", json={"name": "b", "kind": "card", "institution": "i" * 81}).status_code == 422
    assert client.post(f"{API}/accounts", json={"name": "b", "kind": "card", "institution": "i" * 80}).status_code == 201
    key = "b"
    assert client.patch(f"{API}/accounts/{key}", json={"export_note": "n" * 2001}).status_code == 422
    assert client.patch(f"{API}/accounts/{key}", json={"export_note": "n" * 2000}).status_code == 200
    assert client.patch(f"{API}/accounts/{key}", json={"name": "c" * 81}).status_code == 422
