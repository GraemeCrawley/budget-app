"""The app's own phone notifications.

A phone that has the app on its home screen subscribes at its push service and hands us the address.
We send in the form the phone opens by itself on a tap (no code of ours has to run on the phone for
the tap to work), and the opened page tells us it was opened.

Notification text never carries a dollar figure. Nothing here logs or prints an address or a key.
"""
import base64
import calendar
import json
import os
import secrets
import sqlite3
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from tracker.coverage import coverage
from tracker.store import write_tx

LOCAL_TZ = ZoneInfo(os.getenv("TZ", "America/Toronto"))
# The address the app is reached at, ending in a slash: a tapped notification opens here.
SITE = os.getenv("GB_SITE_URL", "http://localhost:8000/")
# The push services a browser can hand us an address at. Anything else is refused, so the server
# cannot be told to send requests to an address of someone's choosing.
PUSH_HOSTS = ("web.push.apple.com", "fcm.googleapis.com", "updates.push.services.mozilla.com")
PUSH_HOST_ENDINGS = (".push.apple.com", ".notify.windows.com")
GONE = (404, 410)  # the push service no longer knows this phone
EVENTS = {"delivered": "delivered_at", "opened": "opened_at"}
NOT_DELIVERED = 3  # exit code of the remind command: a reminder was due and reached no phone
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


class Undelivered(Exception):
    """The push service refused a message; `status` is its HTTP status, or 0 when it was not reached."""

    def __init__(self, status: int):
        super().__init__(str(status))
        self.status = status


def _today() -> date:
    return datetime.now(LOCAL_TZ).date()


def _now() -> str:
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


# --- the signing key ---

def _key_path(data_dir: str) -> Path:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    folder = Path(data_dir) / "push"
    folder.mkdir(exist_ok=True)
    path = folder / "vapid_private.pem"
    if not path.exists():
        key = ec.generate_private_key(ec.SECP256R1())
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    return path


def public_key(data_dir: str) -> str:
    """The key a phone subscribes with, made on first use and kept in the data directory."""
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(_key_path(data_dir).read_bytes(), password=None)
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# --- phones ---

def _known_service(endpoint: str) -> bool:
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host in PUSH_HOSTS or host.endswith(PUSH_HOST_ENDINGS))


def save_subscription(conn: sqlite3.Connection, user_id: int, endpoint: str, p256dh: str, auth: str) -> None:
    if not _known_service(endpoint) or not p256dh or not auth:
        raise ValueError("not a push subscription")
    with write_tx(conn):
        conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        conn.execute("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at)"
                     " VALUES (?, ?, ?, ?, ?)", (user_id, endpoint, p256dh, auth, _now()))


def remove_subscription(conn: sqlite3.Connection, user_id: int, endpoint: str) -> None:
    with write_tx(conn):
        conn.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user_id, endpoint))


def count(conn: sqlite3.Connection, user_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?", (user_id,)).fetchone()[0]


def last_notification(conn: sqlite3.Connection, user_id: int) -> dict | None:
    row = conn.execute("SELECT kind, sent_at, phones, delivered_at, opened_at FROM notifications"
                       " WHERE user_id = ? ORDER BY sent_at DESC, rowid DESC LIMIT 1", (user_id,)).fetchone()
    return dict(row) if row else None


# --- what the monthly reminder says ---

def _last_month(today: date) -> str:
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f"{year}-{month:02d}"


def missing_accounts(conn: sqlite3.Connection, user_id: int, today: date) -> list[str]:
    """Names of the accounts whose files do not yet reach the end of last month."""
    ym = _last_month(today)
    last_day = f"{ym}-{calendar.monthrange(int(ym[:4]), int(ym[5:]))[1]:02d}"
    cov = coverage(conn, user_id)
    names = {r["key"]: r["name"] for r in conn.execute("SELECT key, name FROM accounts WHERE user_id = ?", (user_id,))}
    return sorted(names[key] for key, ranges in cov.items() if ranges and ranges[-1][1] < last_day)


def reminder(conn: sqlite3.Connection, user_id: int, today: date) -> tuple[str, str] | None:
    """The reminder's title and body, or None when every account already has last month."""
    missing = missing_accounts(conn, user_id, today)
    if not missing:
        return None
    month = MONTHS[int(_last_month(today)[5:]) - 1]
    return f"Add {month}'s files", "Still needed: " + ", ".join(missing) + "."


# --- sending ---

def _deliver(subscription: dict, payload: str, key_path: str) -> None:
    """Hand one message to the push service. Tests replace this; nothing else touches the network."""
    from pywebpush import WebPushException, webpush

    origin = "{0.scheme}://{0.netloc}".format(urlsplit(SITE))
    try:
        webpush(subscription_info=subscription, data=payload, vapid_private_key=key_path,
                vapid_claims={"sub": origin}, ttl=86400, headers={"Urgency": "high"}, timeout=20)
    except WebPushException as e:
        raise Undelivered(getattr(getattr(e, "response", None), "status_code", 0) or 0) from None
    except Exception:
        raise Undelivered(0) from None


def send(conn: sqlite3.Connection, data_dir: str, user_id: int, kind: str, title: str, body: str, link: str,
         deliver=None) -> dict:
    """Send one notification to every phone of the user. `link` is where in the app a tap lands ("#/add")."""
    deliver = deliver or _deliver
    note_id = secrets.token_hex(8)
    payload = json.dumps({
        "web_push": 8030,  # the form the phone shows and opens by itself
        "mutable": True,   # and still tells the app's own worker, which reports that it arrived
        "notification": {"title": title, "body": body, "navigate": f"{SITE}?n={note_id}{link}",
                         "tag": note_id, "data": {"id": note_id}},
    })
    phones = conn.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = ?",
                          (user_id,)).fetchall()
    key_path = str(_key_path(data_dir)) if phones else ""
    sent, gone = 0, []
    for phone in phones:
        try:
            deliver({"endpoint": phone["endpoint"], "keys": {"p256dh": phone["p256dh"], "auth": phone["auth"]}},
                    payload, key_path)
            sent += 1
        except Undelivered as e:
            if e.status in GONE:
                gone.append(phone["endpoint"])
    with write_tx(conn):
        for endpoint in gone:
            conn.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user_id, endpoint))
        conn.execute("INSERT INTO notifications (id, user_id, kind, sent_at, phones) VALUES (?, ?, ?, ?, ?)",
                     (note_id, user_id, kind, _now(), sent))
    return {"id": note_id, "sent": sent, "failed": len(phones) - sent}


def mark(conn: sqlite3.Connection, user_id: int, note_id: str, kind: str) -> bool:
    """Record that a notification arrived or was opened; the first report of each kind is the one kept."""
    column = EVENTS.get(kind)
    if column is None:
        raise ValueError("unknown event")
    with write_tx(conn):
        row = conn.execute("SELECT 1 FROM notifications WHERE id = ? AND user_id = ?", (note_id, user_id)).fetchone()
        if row is None:
            return False
        conn.execute(f"UPDATE notifications SET {column} = COALESCE({column}, ?) WHERE id = ? AND user_id = ?",
                     (_now(), note_id, user_id))
    return True


def remind(conn: sqlite3.Connection, data_dir: str, user_id: int) -> tuple[int, str]:
    """Send the monthly reminder if anything is missing. Returns an exit code and a figure-free, name-free line."""
    words = reminder(conn, user_id, _today())
    if words is None:
        return 0, "nothing missing; no reminder sent"
    result = send(conn, data_dir, user_id, "reminder", words[0], words[1], "#/add")
    if result["sent"] == 0:
        return NOT_DELIVERED, "a reminder was due and no phone could be reached"
    return 0, f"reminder sent to {result['sent']} phone(s)"
