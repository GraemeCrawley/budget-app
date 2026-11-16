"""Verifying the Cloudflare Access login token ourselves, so the app does not trust the network blindly.

Nothing here logs. A failure is a `Denied` carrying only a short reason code; the caller decides what to say.
"""
import json
import os
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

import jwt

MODES = ("enforce", "report")
KEY_TTL = 3600  # seconds a fetched key set is trusted
REFETCH_GAP = 60  # an unknown kid triggers at most one fetch per this many seconds


class Denied(Exception):
    """The login token was not accepted; `reason` is one of a fixed set of codes."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class AccessConfig:
    team_domain: str
    aud: str
    users: dict  # lower-cased email -> user key
    mode: str  # "enforce" or "report"
    report_until: date | None = None  # report mode is enforce after this day (in the app's local zone)


def _day(value) -> date:
    """A YYYY-MM-DD date, exactly; anything else is a ValueError."""
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError("not a YYYY-MM-DD date")
    return date.fromisoformat(value)


def effective_mode(config: AccessConfig, today: date) -> str:
    """The mode in force today: report mode past its report_until is enforce."""
    if config.mode == "report" and config.report_until is not None and today > config.report_until:
        return "enforce"
    return config.mode


def load_config(data_dir: str) -> AccessConfig | None:
    """Read <data_dir>/access.json; a missing, malformed or incomplete file is None (callers fail closed).
    A report_until that is present but not a YYYY-MM-DD date is malformed."""
    try:
        with open(os.path.join(data_dir, "access.json"), encoding="utf-8") as f:
            raw = json.load(f)
        team, aud, users = raw["team_domain"], raw["aud"], raw["users"]
        mode = raw.get("mode", "enforce")
        if (not isinstance(team, str) or not team or not isinstance(aud, str) or not aud
                or not isinstance(users, dict) or mode not in MODES
                or not all(isinstance(k, str) and isinstance(v, str) for k, v in users.items())):
            return None
        until = _day(raw["report_until"]) if "report_until" in raw else None
        return AccessConfig(team, aud, {k.lower(): v for k, v in users.items()}, mode, until)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def verify(token: str, config: AccessConfig, key_for: Callable[[str], Any]) -> str:
    """Return the verified, lower-cased email in `token`, or raise Denied(reason)."""
    if not token:
        raise Denied("no_token")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise Denied("bad_token") from None
    kid = header.get("kid")
    if header.get("alg") != "RS256" or not isinstance(kid, str):
        raise Denied("bad_token")
    try:
        key = key_for(kid)
    except Denied:
        raise
    except Exception:
        raise Denied("unknown_key") from None
    try:
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=config.aud, leeway=30,
                            issuer=f"https://{config.team_domain}", options={"require": ["exp", "iss", "aud"]})
    except jwt.ExpiredSignatureError:
        raise Denied("expired") from None
    except jwt.InvalidAudienceError:
        raise Denied("wrong_audience") from None
    except jwt.InvalidIssuerError:
        raise Denied("wrong_issuer") from None
    except jwt.MissingRequiredClaimError as e:
        raise Denied({"aud": "wrong_audience", "iss": "wrong_issuer"}.get(e.claim, "bad_token")) from None
    except Exception:  # any other PyJWT or key-type failure: the token is simply not valid
        raise Denied("bad_token") from None
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise Denied("bad_token")
    return email.strip().lower()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # a redirect surfaces as an HTTPError, i.e. a failed fetch


def _open(url: str) -> bytes:
    """GET `url` (no redirects, 5 s timeout, 1 MB cap). Tests replace this; nothing else touches the network."""
    with urllib.request.build_opener(_NoRedirect).open(url, timeout=5) as resp:
        return resp.read(1_000_000)


class Keys:
    """Cloudflare Access's public signing keys, by kid. Cached for an hour. Whatever the reason for a refetch
    (hour up, unknown kid, empty cache), no more than one attempt a minute is made, failed ones included. A failed
    or empty refetch keeps the keys already held. Any fetch failure with nothing usable cached is Denied("unknown_key")."""

    def __init__(self, team_domain: str):
        self.url = f"https://{team_domain}/cdn-cgi/access/certs"
        self._keys: dict = {}
        self._fetched = 0.0  # monotonic time of the last successful fetch
        self._attempted: float | None = None  # monotonic time of the last attempt, successful or not
        self._lock = threading.Lock()

    def _fetch(self) -> None:
        self._attempted = time.monotonic()
        try:
            jwks = json.loads(_open(self.url))
            keys = {k["kid"]: jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(k))
                    for k in jwks["keys"] if k.get("kty") == "RSA" and "kid" in k}
        except Exception:
            return  # keep what we hold
        if keys:  # an empty set is treated as a failed fetch
            self._keys, self._fetched = keys, time.monotonic()

    def __call__(self, kid: str):
        with self._lock:
            now = time.monotonic()
            fresh = now - self._fetched <= KEY_TTL
            if not (self._keys and fresh and kid in self._keys):
                if self._attempted is None or now - self._attempted >= REFETCH_GAP:
                    self._fetch()
            try:
                return self._keys[kid]
            except KeyError:
                raise Denied("unknown_key") from None
