"""The app's own phone notifications: who is subscribed, what the reminder says, what gets recorded."""
import json
from datetime import date

import pytest

from tests.tracker.conftest import OWNER_EMAIL
from tests.tracker.test_classify import CARD, CHQ, put, put_feb
from tracker import push
from tracker.cli import main
from tracker.store import open_db

PHONE = "https://web.push.apple.com/invented-device-address"
KEYS = {"p256dh": "invented-public-key", "auth": "invented-secret"}


@pytest.fixture
def conn(tmp_path):
    c = open_db(str(tmp_path / "tracker.db"))
    put(c, CHQ, [("2026-01-15", 300000, "EMPLOYER PAY")], "chq")
    put(c, CARD, [("2026-01-05", -4500, "INVENTED GROCER 12")], "card")
    yield c
    c.close()


class Phone:
    """Stands in for the push service: records what it was asked to deliver."""

    def __init__(self, status=None):
        self.got = []
        self.status = status

    def __call__(self, subscription, payload, key_path):
        if self.status:
            raise push.Undelivered(self.status)
        self.got.append((subscription, json.loads(payload)))


def test_a_phone_is_kept_once_however_often_it_subscribes(conn):
    push.save_subscription(conn, 1, PHONE, KEYS["p256dh"], KEYS["auth"])
    push.save_subscription(conn, 1, PHONE, "a-newer-key", KEYS["auth"])
    assert push.count(conn, 1) == 1
    push.remove_subscription(conn, 1, PHONE)
    assert push.count(conn, 1) == 0


@pytest.mark.parametrize("address", ["http://web.push.apple.com/x", "https://example.com/x",
                                     "https://web.push.apple.com.example.com/x", "not an address", ""])
def test_only_a_known_push_service_is_accepted(conn, address):
    with pytest.raises(ValueError):
        push.save_subscription(conn, 1, address, KEYS["p256dh"], KEYS["auth"])


def test_the_reminder_names_the_accounts_still_missing_last_month_and_no_figures(conn):
    put_feb(conn, CARD, [("2026-02-03", -1500, "UNKNOWN PLACE")], "card2")
    title, body = push.reminder(conn, 1, date(2026, 3, 1))
    assert "February" in title
    assert "Chequing" in body and "Card" not in body
    assert "$" not in title + body and not any(ch.isdigit() for ch in body)


def test_no_reminder_when_every_account_has_last_month(conn):
    assert push.reminder(conn, 1, date(2026, 2, 4)) is None


def test_sending_reaches_each_phone_in_the_form_the_phone_opens_itself(conn, tmp_path):
    push.save_subscription(conn, 1, PHONE, KEYS["p256dh"], KEYS["auth"])
    phone = Phone()
    result = push.send(conn, str(tmp_path), 1, "test", "A title", "A body", "#/add", deliver=phone)
    assert (result["sent"], result["failed"]) == (1, 0)
    (subscription, payload), = phone.got
    assert subscription == {"endpoint": PHONE, "keys": KEYS}
    assert payload["web_push"] == 8030
    note = payload["notification"]
    assert (note["title"], note["body"]) == ("A title", "A body")
    assert note["navigate"] == f"{push.SITE}?n={result['id']}#/add"
    row = conn.execute("SELECT kind, sent_at, delivered_at, opened_at FROM notifications").fetchone()
    assert row["kind"] == "test" and row["sent_at"] and row["delivered_at"] is None and row["opened_at"] is None


def test_a_phone_the_push_service_no_longer_knows_is_dropped(conn, tmp_path):
    push.save_subscription(conn, 1, PHONE, KEYS["p256dh"], KEYS["auth"])
    result = push.send(conn, str(tmp_path), 1, "test", "t", "b", "#/", deliver=Phone(status=410))
    assert (result["sent"], result["failed"]) == (0, 1)
    assert push.count(conn, 1) == 0


def test_a_passing_failure_keeps_the_phone(conn, tmp_path):
    push.save_subscription(conn, 1, PHONE, KEYS["p256dh"], KEYS["auth"])
    push.send(conn, str(tmp_path), 1, "test", "t", "b", "#/", deliver=Phone(status=503))
    assert push.count(conn, 1) == 1


def test_delivery_and_opening_are_recorded_once_each(conn, tmp_path):
    push.save_subscription(conn, 1, PHONE, KEYS["p256dh"], KEYS["auth"])
    note = push.send(conn, str(tmp_path), 1, "test", "t", "b", "#/", deliver=Phone())["id"]
    assert push.mark(conn, 1, note, "opened") is True
    first = conn.execute("SELECT opened_at FROM notifications").fetchone()[0]
    assert push.mark(conn, 1, note, "opened") is True
    assert conn.execute("SELECT opened_at FROM notifications").fetchone()[0] == first
    assert push.mark(conn, 1, "no-such-note", "opened") is False
    with pytest.raises(ValueError):
        push.mark(conn, 1, note, "deleted")


def test_the_signing_key_is_made_once_and_kept_private(tmp_path):
    first = push.public_key(str(tmp_path))
    assert push.public_key(str(tmp_path)) == first and len(first) > 80
    assert (tmp_path / "push" / "vapid_private.pem").stat().st_mode & 0o077 == 0


# --- the command the monthly timer runs ---

def test_remind_sends_nothing_when_nothing_is_missing(conn, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(push, "_today", lambda: date(2026, 2, 4))
    assert main(["remind"]) == 0
    assert "nothing missing" in capsys.readouterr().out


def test_remind_says_so_when_no_phone_could_be_reached(conn, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(push, "_today", lambda: date(2026, 3, 1))
    assert main(["remind"]) == push.NOT_DELIVERED  # the caller falls back to its other channel
    out = capsys.readouterr().out
    assert "Chequing" not in out and "$" not in out


def test_remind_reaches_the_phone(conn, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(push, "_today", lambda: date(2026, 3, 1))
    phone = Phone()
    monkeypatch.setattr(push, "_deliver", phone)
    push.save_subscription(conn, 1, PHONE, KEYS["p256dh"], KEYS["auth"])
    assert main(["remind"]) == 0
    assert len(phone.got) == 1 and "sent to 1" in capsys.readouterr().out


# --- through the server ---

@pytest.fixture
def client(make_client, token):
    c = make_client()
    c.headers["Cf-Access-Jwt-Assertion"] = token(OWNER_EMAIL)
    return c


def test_the_app_can_subscribe_test_and_report_back(client, monkeypatch):
    phone = Phone()
    monkeypatch.setattr(push, "_deliver", phone)
    state = client.get("/api/v1/push").json()
    assert state["phones"] == 0 and len(state["key"]) > 80
    assert client.post("/api/v1/push/test").status_code == 409  # no phone yet
    assert client.post("/api/v1/push/subscriptions", json={"endpoint": "https://example.com/x", "keys": KEYS}).status_code == 422
    assert client.post("/api/v1/push/subscriptions", json={"endpoint": PHONE, "keys": KEYS}).json() == {"phones": 1}
    sent = client.post("/api/v1/push/test").json()
    assert sent["sent"] == 1 and len(phone.got) == 1
    assert client.post("/api/v1/push/events", json={"id": sent["id"], "kind": "opened"}).status_code == 204
    assert client.post("/api/v1/push/events", json={"id": sent["id"], "kind": "nonsense"}).status_code == 422
    last = client.get("/api/v1/push").json()["last"]
    assert last["kind"] == "test" and last["opened_at"]
    assert client.request("DELETE", "/api/v1/push/subscriptions", json={"endpoint": PHONE}).json() == {"phones": 0}
