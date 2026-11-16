import json
import logging

from tests.tracker.helpers import write_config


def test_no_config_fails_closed(client_without_config):
    assert client_without_config.get("/api/v1/months").status_code == 503
    assert client_without_config.get("/api/v1/months").json() == {"detail": "login check not configured"}
    assert client_without_config.get("/").status_code == 503
    assert client_without_config.get("/health").status_code == 200

def test_enforce_mode(make_client, token):
    c = make_client(mode="enforce")
    assert c.get("/api/v1/months").json() == {"detail": "not signed in", "reason": "no_token"}
    assert c.get("/api/v1/months", headers={"Cf-Access-Jwt-Assertion": token(exp_past=True)}).status_code == 401
    assert c.get("/api/v1/months", headers={"Cf-Access-Jwt-Assertion": token(email="stranger@example.test")}).status_code == 403
    ok = c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token()})
    assert ok.json() == {"user": "owner", "login_check": "enforce"}
    c.cookies.set("CF_Authorization", token())
    assert c.get("/api/v1/me").status_code == 200

def test_forbidden_body(make_client, token):
    c = make_client(mode="enforce")
    r = c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token(email="stranger@example.test")})
    assert (r.status_code, r.json()) == (403, {"detail": "not a known user", "reason": "unknown_email"})

def test_verified_user_key_without_a_ledger_row_is_403(make_client, token):
    c = make_client(mode="enforce")
    r = c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token(email="ghost@example.test")})
    assert (r.status_code, r.json()) == (403, {"detail": "not a known user", "reason": "unknown_user"})

def test_email_case_does_not_matter(make_client, token):
    c = make_client(mode="enforce")
    assert c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token(email="ME@Example.Test")}).status_code == 200

def test_bad_token_is_401_with_reason(make_client):
    c = make_client(mode="enforce")
    r = c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": "garbage"})
    assert (r.status_code, r.json()) == (401, {"detail": "not signed in", "reason": "bad_token"})

def test_every_path_is_gated_in_enforce_mode(make_client):
    c = make_client(mode="enforce")
    for p in ("/", "/api/v1/months", "/api/v1/me", "/anything", "/docs", "/openapi.json", "/metrics/", "/health/x",
              "//health", "/robots.txt/", "/api/v1/transactions?month=2026-01"):
        assert c.get(p).status_code == 401, p
    assert c.post("/api/v1/months").status_code == 401

def test_report_mode_lets_the_request_through_and_logs_no_identity(make_client, token, caplog):
    c = make_client(mode="report")  # no caplog.set_level: the app must make its own line visible
    assert c.get("/api/v1/me").json() == {"user": "owner", "login_check": "report"}
    c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token()})
    text = caplog.text
    assert "login check (report): no_token" in text and "login check (report): ok" in text
    assert "example.test" not in text and "eyJ" not in text

def test_report_mode_runs_as_owner_whatever_the_token_says(make_client, token):
    c = make_client(mode="report")
    r = c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token(email="ghost@example.test")})
    assert r.json() == {"user": "owner", "login_check": "report"}

def test_enforce_mode_logs_nothing_about_identity(make_client, token, caplog):
    caplog.set_level(logging.DEBUG)
    c = make_client(mode="enforce")
    t = token()
    c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": t})
    assert "example.test" not in caplog.text and t not in caplog.text

def test_probes_need_no_login_and_everything_else_does(make_client):
    c = make_client(mode="enforce")
    assert [c.get(p).status_code for p in ("/health", "/healthz", "/robots.txt", "/metrics")] == [200] * 4
    assert c.get("/").status_code == 401

def test_probes_return_no_data(make_client):
    c = make_client(mode="enforce")
    assert set(c.get("/healthz").json()) == {"status", "data_dir_mounted", "now"}
    assert c.get("/robots.txt").text == "User-agent: *\nDisallow: /\n"

def test_config_is_re_read_on_each_request(make_client, token, tmp_path):
    c = make_client(mode="report")
    assert c.get("/api/v1/me").status_code == 200
    write_config(tmp_path, "enforce")
    assert c.get("/api/v1/me").status_code == 401
    (tmp_path / "access.json").unlink()
    assert c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token()}).status_code == 503

def test_startup_opens_the_ledger_so_the_schema_is_current(tmp_path, monkeypatch, key_for):
    import sqlite3
    from fastapi.testclient import TestClient
    from tracker.server import create_app
    from tracker.store import SCHEMA, SCHEMA_VERSION
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    write_config(tmp_path, "report")
    db = tmp_path / "tracker.db"
    c = sqlite3.connect(db)
    c.executescript(SCHEMA.read_text() + "PRAGMA user_version = 1;")
    c.close()
    with TestClient(create_app(key_for=key_for)):  # entering runs the lifespan
        pass
    c = sqlite3.connect(db)
    assert c.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    c.close()

def test_startup_without_a_ledger_creates_nothing(tmp_path, monkeypatch, key_for):
    from fastapi.testclient import TestClient
    from tracker.server import create_app
    monkeypatch.setenv("GB_DATA_DIR", str(tmp_path))
    with TestClient(create_app(key_for=key_for)):
        pass
    assert list(tmp_path.iterdir()) == []


def test_report_line_is_visible_without_anyone_configuring_logging(make_client):
    lg = logging.getLogger("tracker.auth")
    lg.setLevel(logging.NOTSET)
    for h in [h for h in lg.handlers if getattr(h, "_tracker_auth", False)]:
        lg.removeHandler(h)
    make_client(mode="report")
    make_client(mode="report")
    assert lg.isEnabledFor(logging.INFO)
    assert [getattr(h, "_tracker_auth", False) for h in lg.handlers].count(True) == 1


def _with_post_route(c):
    @c.app.post("/api/v1/throwaway")
    def throwaway():
        return {"ok": True}
    c.app.router.routes.insert(0, c.app.router.routes.pop())  # ahead of the client mount, which takes the rest
    return c


def test_writes_need_the_client_header_in_both_modes(make_client, token):
    for mode in ("enforce", "report"):
        c = _with_post_route(make_client(mode=mode))
        auth_h = {"Cf-Access-Jwt-Assertion": token()}
        bare = {"headers": auth_h}
        # drop the default client header for this request
        c.headers.pop("X-Budget-Client")
        r = c.post("/api/v1/throwaway", **bare)
        assert (r.status_code, r.json()) == (403, {"detail": "missing client header"}), mode
        assert c.post("/api/v1/throwaway", headers={**auth_h, "X-Budget-Client": "0"}).status_code == 403
        assert c.post("/api/v1/throwaway", headers={**auth_h, "X-Budget-Client": "1"}).status_code == 200
        assert c.get("/api/v1/me", **bare).status_code == 200  # reads need no such header


def test_the_client_header_check_comes_after_the_login_check(make_client):
    c = _with_post_route(make_client(mode="enforce"))
    c.headers.pop("X-Budget-Client")
    assert c.post("/api/v1/throwaway").status_code == 401


def test_no_cors_is_offered(make_client, token):
    c = make_client(mode="enforce")
    r = c.options("/api/v1/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers


def test_the_built_client_is_served_behind_the_login(make_client, token, tmp_path, monkeypatch):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<title>client</title>")
    monkeypatch.setenv("GB_WEB_DIR", str(tmp_path / "web"))
    c = make_client(mode="enforce")
    assert c.get("/").status_code == 401
    assert "client" in c.get("/", headers={"Cf-Access-Jwt-Assertion": token()}).text
    assert c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token()}).json()["user"] == "owner"


def test_the_page_is_always_rechecked_so_a_phone_never_keeps_an_old_build(make_client, tmp_path, monkeypatch):
    (tmp_path / "web" / "assets").mkdir(parents=True)
    (tmp_path / "web" / "index.html").write_text("<title>client</title>")
    (tmp_path / "web" / "assets" / "index-abc123.js").write_text("1")
    monkeypatch.setenv("GB_WEB_DIR", str(tmp_path / "web"))
    c = make_client(mode="report")
    assert c.get("/").headers["cache-control"] == "no-cache"
    assert c.get("/assets/index-abc123.js").headers["cache-control"] == "private, max-age=31536000, immutable"


def test_a_missing_client_build_is_a_plain_503(make_client, monkeypatch, tmp_path):
    monkeypatch.setenv("GB_WEB_DIR", str(tmp_path / "nope"))
    r = make_client(mode="report").get("/")
    assert r.status_code == 503
    assert r.text == "client not built"


def test_an_unknown_api_path_is_a_json_404_not_the_client(make_client, monkeypatch, tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<title>client</title>")
    monkeypatch.setenv("GB_WEB_DIR", str(tmp_path / "web"))
    r = make_client(mode="report").get("/api/v1/nonsense")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "client" not in r.text


def test_report_mode_past_its_report_until_is_enforced(make_client, token, tmp_path):
    c = make_client(mode="report")
    write_config(tmp_path, "report", report_until="2000-01-01")
    assert c.get("/api/v1/me").status_code == 401
    r = c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token()})
    assert r.json() == {"user": "owner", "login_check": "enforce"}
    write_config(tmp_path, "report", report_until="2999-12-31")
    assert c.get("/api/v1/me").json() == {"user": "owner", "login_check": "report"}
    write_config(tmp_path, "report", report_until="next week")
    assert c.get("/api/v1/me").status_code == 503  # a malformed date fails closed


def test_report_mode_today_is_the_apps_local_day(make_client, tmp_path, monkeypatch):
    from datetime import datetime
    import tracker.server
    c = make_client(mode="report")
    write_config(tmp_path, "report", report_until="2026-12-01")

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):  # 02:30 on the 2nd in UTC is still the 1st in the app's zone
            return datetime(2026, 12, 2, 2, 30, tzinfo=tracker.server.ZoneInfo("UTC")).astimezone(tz)
    monkeypatch.setattr(tracker.server, "datetime", Clock)
    monkeypatch.setattr(tracker.server, "LOCAL_TZ", tracker.server.ZoneInfo("America/Toronto"))
    assert c.get("/api/v1/me").json()["login_check"] == "report"


def test_report_mode_warns_once_after_start_up(make_client, token, caplog):
    c = make_client(mode="report")
    c.get("/api/v1/me")
    c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token()})
    warnings = [r for r in caplog.records if r.name == "tracker.auth" and r.levelno == logging.WARNING]
    assert [r.getMessage() for r in warnings] == ["login check is in report mode"]
    make_client(mode="report").get("/api/v1/me")  # a fresh start-up warns again
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING].count(
        "login check is in report mode") == 2


def test_enforce_mode_never_warns_about_report_mode(make_client, token, caplog):
    c = make_client(mode="enforce")
    c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token()})
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# --- report mode tells what enforce would answer; refusals are logged and readable ---

def _report_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("login check (report)")]


def test_report_mode_says_which_answer_enforce_would_give(make_client, token, caplog):
    c = make_client(mode="report")
    cases = [(None, "no_token"), (token(), "ok"), (token(email="stranger@example.test"), "unknown_email"),
             (token(email="ghost@example.test"), "unknown_user")]
    for t, expected in cases:
        caplog.clear()
        r = c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": t} if t else {})
        assert r.json() == {"user": "owner", "login_check": "report"}
        assert _report_lines(caplog) == [f"login check (report): {expected}"]
        assert "example.test" not in caplog.text and "eyJ" not in caplog.text and "/api" not in caplog.text


def test_enforce_403_body_names_the_reason(make_client, token):
    c = make_client(mode="enforce")
    r = c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token(email="stranger@example.test")})
    assert (r.status_code, r.json()) == (403, {"detail": "not a known user", "reason": "unknown_email"})
    r = c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token(email="ghost@example.test")})
    assert (r.status_code, r.json()) == (403, {"detail": "not a known user", "reason": "unknown_user"})


def test_enforce_logs_each_refusal_reason_at_most_once_a_minute(make_client, token, caplog, monkeypatch):
    from tracker import server
    now = [1000.0]
    monkeypatch.setattr(server, "_clock", lambda: now[0])
    c = make_client(mode="enforce")
    stranger = {"Cf-Access-Jwt-Assertion": token(email="stranger@example.test")}

    def lines():
        return [r.getMessage() for r in caplog.records if r.getMessage().startswith("login check: refused")]
    for _ in range(3):
        c.get("/api/v1/me", headers=stranger)
    c.get("/api/v1/me")
    c.get("/api/v1/me")
    assert lines() == ["login check: refused unknown_email", "login check: refused no_token"]
    now[0] += 61
    c.get("/api/v1/me", headers=stranger)
    assert lines()[2:] == ["login check: refused unknown_email"]
    assert "example.test" not in caplog.text


HTML = {"Accept": "text/html,application/xhtml+xml"}


def _page_checks(r, status, heading):
    assert r.status_code == status
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "no-store"
    assert heading in r.text
    assert "example.test" not in r.text and "eyJ" not in r.text


def test_401_is_a_page_for_a_browser(make_client):
    r = make_client(mode="enforce").get("/", headers=HTML)
    _page_checks(r, 401, "You're not signed in.")
    assert '<a href="">Reload</a>' in r.text and "prefers-color-scheme" in r.text


def test_403_is_a_page_for_a_browser(make_client, token):
    c = make_client(mode="enforce")
    r = c.get("/", headers={**HTML, "Cf-Access-Jwt-Assertion": token(email="stranger@example.test")})
    _page_checks(r, 403, "This login isn't set up for this app.")
    assert "unknown_email" in r.text and "Nothing is wrong with your data." in r.text
    r = c.get("/", headers={**HTML, "Cf-Access-Jwt-Assertion": token(email="ghost@example.test")})
    assert r.status_code == 403 and "unknown_user" in r.text


def test_503_is_a_page_for_a_browser(client_without_config, make_client, tmp_path):
    r = client_without_config.get("/", headers=HTML)
    _page_checks(r, 503, "The app isn't ready.")
    assert "login check not configured" in r.text
    c = make_client(mode="report")
    (tmp_path / "tracker.db").unlink()
    r = c.get("/", headers=HTML)
    _page_checks(r, 503, "The app isn't ready.")
    assert "no ledger yet" in r.text


def test_api_paths_and_other_clients_still_get_json(make_client, token):
    c = make_client(mode="enforce")
    r = c.get("/api/v1/me", headers=HTML)
    assert (r.status_code, r.json()) == (401, {"detail": "not signed in", "reason": "no_token"})
    r = c.get("/", headers={"Accept": "application/json"})
    assert (r.status_code, r.json()) == (401, {"detail": "not signed in", "reason": "no_token"})


def test_missing_client_header_stays_json_for_a_browser(make_client, token):
    c = make_client(mode="enforce")
    c.headers.pop("X-Budget-Client")
    r = c.post("/api/v1/months", headers={**HTML, "Cf-Access-Jwt-Assertion": token()})
    assert (r.status_code, r.json()) == (403, {"detail": "missing client header"})
