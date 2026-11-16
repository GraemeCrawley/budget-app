"""Shared fixtures for the server tests: a signing key, a token factory and a client factory.

`token(...)` signs a Cloudflare-Access-shaped token with a throwaway RSA key (kid "k1");
`make_client(mode=...)` builds the real server app over a temp data directory with a matching
access.json and a ledger, injecting the key lookup so no test touches the network.
"""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from tests.tracker.helpers import AUD, GHOST_EMAIL, OWNER_EMAIL, TEAM, write_config  # noqa: F401 (re-exported)
from tracker.auth import Denied
from tracker.store import open_db

@pytest.fixture(scope="session")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def key_for(private_key):
    public = private_key.public_key()

    def lookup(kid):
        if kid == "k1":
            return public
        raise Denied("unknown_key")
    return lookup


@pytest.fixture
def token(private_key):
    def make(email=OWNER_EMAIL, exp_past=False, aud=None, iss=None, kid="k1", **claims):
        body = {"email": email, "aud": [AUD] if aud is None else aud,
                "iss": iss or f"https://{TEAM}",
                "exp": int(time.time()) + (-3600 if exp_past else 3600)}
        body.update(claims)
        body = {k: v for k, v in body.items() if v is not None}
        return jwt.encode(body, private_key, algorithm="RS256", headers={"kid": kid})
    return make


@pytest.fixture
def make_client(tmp_path, monkeypatch, key_for):
    from tracker.server import create_app

    def make(mode="enforce"):
        monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
        open_db(str(tmp_path / "tracker.db")).close()
        write_config(tmp_path, mode)
        return TestClient(create_app(key_for=key_for), headers={"X-Budget-Client": "1"})
    return make


@pytest.fixture
def client_without_config(tmp_path, monkeypatch, key_for):
    from tracker.server import create_app
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    return TestClient(create_app(key_for=key_for))
