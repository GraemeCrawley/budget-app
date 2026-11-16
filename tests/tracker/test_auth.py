import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization

from tests.tracker.helpers import AUD, TEAM
from tracker import auth
from tracker.auth import AccessConfig, Denied, load_config, verify

CONFIG = AccessConfig(team_domain=TEAM, aud=AUD, users={"me@example.test": "owner"}, mode="enforce")


def reason(tok, key_for):
    with pytest.raises(Denied) as e:
        verify(tok, CONFIG, key_for)
    return e.value.reason


def test_valid_token(token, key_for):
    assert verify(token(), CONFIG, key_for) == "me@example.test"

def test_email_is_lower_cased(token, key_for):
    assert verify(token(email="Me@Example.TEST"), CONFIG, key_for) == "me@example.test"

def test_no_token(key_for):
    assert reason("", key_for) == "no_token"

def test_garbage(key_for):
    assert reason("not.a.token", key_for) == "bad_token"
    assert reason("garbage", key_for) == "bad_token"

def test_expired(token, key_for):
    assert reason(token(exp_past=True), key_for) == "expired"

def test_wrong_audience(token, key_for):
    assert reason(token(aud=["other-app"]), key_for) == "wrong_audience"

def test_string_audience_equal_to_configured_is_accepted(token, key_for):
    assert verify(token(aud=AUD), CONFIG, key_for) == "me@example.test"

def test_wrong_issuer(token, key_for):
    assert reason(token(iss="https://evil.example"), key_for) == "wrong_issuer"

def test_unknown_kid(token, key_for):
    assert reason(token(kid="k2"), key_for) == "unknown_key"

def test_hs256_signed_with_the_public_key_bytes(private_key, key_for):
    pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "k1"}).encode())
    body = b64(json.dumps({"email": "me@example.test", "aud": [AUD], "iss": f"https://{TEAM}",
                        "exp": int(time.time()) + 3600}).encode())
    sig = b64(hmac.new(pem, f"{head}.{body}".encode(), hashlib.sha256).digest())
    assert reason(f"{head}.{body}.{sig}", key_for) == "bad_token"

def test_alg_none(key_for):
    tok = jwt.encode({"email": "me@example.test", "aud": [AUD], "iss": f"https://{TEAM}",
                      "exp": int(time.time()) + 3600}, None, algorithm="none", headers={"kid": "k1"})
    assert reason(tok, key_for) == "bad_token"

def test_missing_email_claim(token, key_for):
    assert reason(token(email=None), key_for) == "bad_token"

def test_non_string_email_claim(token, key_for):
    assert reason(token(email=["me@example.test"]), key_for) == "bad_token"

def test_key_fetch_failing_is_unknown_key(token):
    def broken(kid):
        raise OSError("network down")
    assert reason(token(), broken) == "unknown_key"

class FakeCerts:
    """Stands in for auth._open and for the clock; counts fetches."""
    def __init__(self, monkeypatch, public_key):
        self.now = 1000.0
        self.fetches = 0
        self.fail = False
        self.keys = [self.jwk(public_key, "k1")]
        monkeypatch.setattr(auth, "_open", self.open)
        monkeypatch.setattr(auth, "time", SimpleNamespace(monotonic=lambda: self.now))

    @staticmethod
    def jwk(public_key, kid):
        return {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key)), "kid": kid}

    def open(self, url):
        self.fetches += 1
        assert url == f"https://{TEAM}/cdn-cgi/access/certs"
        if self.fail:
            raise OSError("down")
        return json.dumps({"keys": self.keys}).encode()


@pytest.fixture
def certs(monkeypatch, private_key):
    return FakeCerts(monkeypatch, private_key.public_key())


def test_keys_fetch_and_lookup(certs, token):
    keys = auth.Keys(TEAM)
    assert verify(token(), CONFIG, keys) == "me@example.test"
    assert certs.fetches == 1

def test_keys_cache_hit_does_not_fetch_again(certs):
    keys = auth.Keys(TEAM)
    keys("k1"); keys("k1"); keys("k1")
    assert certs.fetches == 1

def test_keys_unknown_kid_refetches_at_most_once_a_minute(certs):
    keys = auth.Keys(TEAM)
    keys("k1")
    for _ in range(3):
        with pytest.raises(Denied) as e:
            keys("nope")
        assert e.value.reason == "unknown_key"
    assert certs.fetches == 1  # the unknown kid fell inside the minute after the first fetch
    certs.now += 61
    with pytest.raises(Denied):
        keys("nope")
    assert certs.fetches == 2
    keys("k1")
    assert certs.fetches == 2

def test_keys_empty_set_is_not_refetched_on_every_request(certs):
    certs.keys = []
    keys = auth.Keys(TEAM)
    for _ in range(5):
        with pytest.raises(Denied) as e:
            keys("k1")
        assert e.value.reason == "unknown_key"
    assert certs.fetches == 1
    certs.now += 61
    with pytest.raises(Denied):
        keys("k1")
    assert certs.fetches == 2

def test_keys_fetch_failure_is_not_retried_on_every_request(certs):
    certs.fail = True
    keys = auth.Keys(TEAM)
    for _ in range(5):
        with pytest.raises(Denied):
            keys("k1")
    assert certs.fetches == 1

def test_keys_failed_refetch_after_the_hour_still_serves_the_cached_key(certs):
    keys = auth.Keys(TEAM)
    good = keys("k1")
    certs.now += 3601
    certs.fail = True
    assert keys("k1") is good
    assert certs.fetches == 2
    assert keys("k1") is good  # and it does not hammer the endpoint
    assert certs.fetches == 2
    certs.now += 61
    certs.fail = False
    keys("k1")
    assert certs.fetches == 3

def test_keys_empty_refetch_after_the_hour_keeps_the_cached_key(certs):
    keys = auth.Keys(TEAM)
    good = keys("k1")
    certs.now += 3601
    certs.keys = []
    assert keys("k1") is good

def test_keys_fetch_refuses_redirects(monkeypatch):
    import urllib.error
    import urllib.request
    handler = auth._NoRedirect()
    req = urllib.request.Request("https://team.example.test/x")
    assert handler.redirect_request(req, None, 302, "Found", {}, "https://evil.example/") is None


def write(tmp_path, data):
    (tmp_path / "access.json").write_text(json.dumps(data))

def test_load_config_valid(tmp_path):
    write(tmp_path, {"team_domain": TEAM, "aud": AUD, "users": {"Me@Example.test": "owner"}, "mode": "report"})
    assert load_config(str(tmp_path)) == AccessConfig(TEAM, AUD, {"me@example.test": "owner"}, "report")

def test_load_config_missing_file(tmp_path):
    assert load_config(str(tmp_path)) is None

def test_load_config_without_aud(tmp_path):
    write(tmp_path, {"team_domain": TEAM, "users": {}})
    assert load_config(str(tmp_path)) is None

def test_load_config_mode_defaults_to_enforce(tmp_path):
    write(tmp_path, {"team_domain": TEAM, "aud": AUD, "users": {}})
    assert load_config(str(tmp_path)).mode == "enforce"

def test_load_config_malformed(tmp_path):
    (tmp_path / "access.json").write_text("{not json")
    assert load_config(str(tmp_path)) is None

def test_load_config_unknown_mode_is_none(tmp_path):
    write(tmp_path, {"team_domain": TEAM, "aud": AUD, "users": {}, "mode": "off"})
    assert load_config(str(tmp_path)) is None

def test_load_config_reads_report_until(tmp_path):
    from datetime import date
    write(tmp_path, {"team_domain": TEAM, "aud": AUD, "users": {}, "mode": "report", "report_until": "2026-12-01"})
    assert load_config(str(tmp_path)).report_until == date(2026, 12, 1)
    write(tmp_path, {"team_domain": TEAM, "aud": AUD, "users": {}, "mode": "report"})
    assert load_config(str(tmp_path)).report_until is None

@pytest.mark.parametrize("bad", ["2026-13-01", "20261201", "2026-12-1", "", "soon", 20261201, None, ["2026-12-01"]])
def test_load_config_with_a_malformed_report_until_is_none(tmp_path, bad):
    write(tmp_path, {"team_domain": TEAM, "aud": AUD, "users": {}, "mode": "report", "report_until": bad})
    assert load_config(str(tmp_path)) is None

def test_report_mode_turns_to_enforce_after_report_until():
    from dataclasses import replace
    from datetime import date
    from tracker.auth import effective_mode
    until = replace(CONFIG, mode="report", report_until=date(2026, 12, 1))
    assert effective_mode(until, date(2026, 12, 1)) == "report"  # through the day itself
    assert effective_mode(until, date(2026, 12, 2)) == "enforce"
    assert effective_mode(replace(until, report_until=None), date(2999, 1, 1)) == "report"
    assert effective_mode(replace(until, mode="enforce"), date(2000, 1, 1)) == "enforce"
