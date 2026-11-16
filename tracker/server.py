"""The tracker's own web server. Every request except four internal probes must carry a Cloudflare Access
token that this app verifies itself (see tracker/auth.py); without a valid login configuration it serves nothing.

The login configuration (<GB_DATA_DIR>/access.json) is re-read on every request, so switching `mode` from
`report` to `enforce` is a file edit with no restart. An optional `report_until` (YYYY-MM-DD) ends report mode
by itself: after that day, in the app's local zone, the check is enforced.
"""
import html
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from tracker import auth
from tracker.api import router as api_router
from tracker.store import LedgerNeedsUpgrade, open_db, open_readonly

LOCAL_TZ = ZoneInfo(os.getenv("TZ", "America/Toronto"))
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
PROBES = frozenset({"/health", "/healthz", "/metrics", "/robots.txt"})
log = logging.getLogger("tracker.auth")
REFUSAL_LOG_EVERY = 60.0  # seconds: one refusal line per reason per this long
_clock = time.monotonic  # tests replace this


def _data_dir() -> str | None:
    d = os.environ.get("GB_DATA_DIR")
    return d if d and os.path.isdir(d) else None


def _config() -> tuple[str | None, "auth.AccessConfig | None"]:
    d = _data_dir()
    return d, (auth.load_config(d) if d else None)


def _log_to_stderr_once() -> None:
    """Nothing else configures logging for this logger (uvicorn only handles its own), so give the login-check
    line a level and a handler, once however many apps are built."""
    log.setLevel(logging.INFO)
    if not any(getattr(h, "_tracker_auth", False) for h in log.handlers):
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        h._tracker_auth = True
        log.addHandler(h)


class _Unavailable(Exception):
    def __init__(self, detail: str):
        self.detail = detail


def _user_id(data_dir: str, key: str) -> int | None:
    """users.id for a user key, or None when the ledger has no such user. Raises _Unavailable if no usable ledger."""
    try:
        conn = open_readonly(os.path.join(data_dir, "tracker.db"))
    except FileNotFoundError:
        raise _Unavailable("no ledger yet") from None
    except LedgerNeedsUpgrade:
        raise _Unavailable("ledger needs upgrading") from None
    try:
        row = conn.execute("SELECT id FROM users WHERE key = ?", (key,)).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


class _Client(StaticFiles):
    """The built client. An API path that does not exist is a JSON 404, never the client's index.html.
    The page itself is rechecked on every open, so a phone never keeps an old build; the files under
    assets/ carry a hash of their contents in their names and can be kept for good."""

    async def get_response(self, path, scope):
        if path == "api" or path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        response = await super().get_response(path, scope)
        kept = path.startswith("assets/") and response.status_code == 200
        response.headers["Cache-Control"] = "private, max-age=31536000, immutable" if kept else "no-cache"
        return response


_PAGES = {
    401: ("You're not signed in.", "Reload this page to sign in again.", '<p><a href="">Reload</a></p>'),
    403: ("This login isn't set up for this app.",
          "The address on your login isn't on this app's owner list. Nothing is wrong with your data.", ""),
    503: ("The app isn't ready.", "Its login check or its ledger isn't available yet. Try again in a minute.", ""),
}
_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme: light dark; --bg: #fff; --fg: #1b1b1b; --muted: #666; --link: #0b57d0; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #121212; --fg: #eee; --muted: #999; --link: #8ab4f8; }} }}
body {{ margin: 0; padding: 24px 16px; background: var(--bg); color: var(--fg);
  font: 18px/1.5 system-ui, sans-serif; max-width: 32rem; }}
h1 {{ font-size: 1.4rem; margin: 0 0 .5rem; }}
a {{ color: var(--link); }}
small {{ color: var(--muted); font-size: .8rem; }}
</style></head><body>
<h1>{title}</h1>
<p>{text}</p>
{extra}{note}
</body></html>
"""


def _wants_page(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "") and not request.url.path.startswith("/api/")


def _refuse(request: Request, status: int, **body) -> Response:
    """A login-check refusal: JSON, or a small readable page for a browser navigation."""
    if status in _PAGES and _wants_page(request):
        title, text, extra = _PAGES[status]
        muted = body.get("reason") if status == 403 else body.get("detail") if status == 503 else None
        note = f"<p><small>{html.escape(muted)}</small></p>" if muted else ""
        return HTMLResponse(_PAGE.format(title=title, text=text, extra=extra, note=note),
                            status_code=status, headers={"Cache-Control": "no-store"})
    return JSONResponse(body, status_code=status)


def create_app(key_for=None) -> FastAPI:
    """Build the server. `key_for(kid)` supplies token-signing keys; tests inject one so nothing touches the network."""
    _log_to_stderr_once()
    keys: dict = {}  # team domain -> Keys, so one fetch cache lives as long as the app
    last_logged: dict = {}  # refusal reason -> when it was last logged
    warned = []  # set once the report-mode warning has been logged since this app was built

    def lookup(config: auth.AccessConfig):
        if key_for is not None:
            return key_for
        if config.team_domain not in keys:
            keys[config.team_domain] = auth.Keys(config.team_domain)
        return keys[config.team_domain]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        d = _data_dir()
        if d and os.path.isfile(os.path.join(d, "tracker.db")):
            open_db(os.path.join(d, "tracker.db")).close()  # bring the schema current before read-only opens
        yield

    # No interactive docs or schema: nothing beyond the API and the probes is served.
    app = FastAPI(title="budget", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def refused(request: Request, status: int, reason: str) -> Response:
        now = _clock()
        if reason not in last_logged or now - last_logged[reason] >= REFUSAL_LOG_EVERY:
            last_logged[reason] = now
            log.info("login check: refused %s", reason)
        detail = "not signed in" if status == 401 else "not a known user"
        return _refuse(request, status, detail=detail, reason=reason)

    @app.middleware("http")
    async def check_login(request: Request, call_next):
        if request.url.path in PROBES:
            return await call_next(request)
        data_dir, config = await run_in_threadpool(_config)
        if config is None:
            return _refuse(request, 503, detail="login check not configured")
        token = request.headers.get("Cf-Access-Jwt-Assertion") or request.cookies.get("CF_Authorization") or ""
        denial = None
        email = None
        try:
            email = await run_in_threadpool(auth.verify, token, config, lookup(config))
        except auth.Denied as d:
            denial = d.reason
        mode = auth.effective_mode(config, datetime.now(LOCAL_TZ).date())
        mapped = None if denial else config.users.get(email)
        try:
            if denial is None and mapped is None:
                would = "unknown_email"
            elif denial is None and await run_in_threadpool(_user_id, data_dir, mapped) is None:
                would = "unknown_user"
            else:
                would = denial
            if mode == "report":
                log.info("login check (report): %s", would or "ok")
                user_key = "owner"
            else:
                if denial:
                    return refused(request, 401, denial)
                if would:
                    return refused(request, 403, would)
                user_key = mapped
            user_id = await run_in_threadpool(_user_id, data_dir, user_key)
        except _Unavailable as e:
            return _refuse(request, 503, detail=e.detail)
        if user_id is None:
            return refused(request, 403, "unknown_user")
        if request.method not in SAFE_METHODS and request.headers.get("X-Budget-Client") != "1":
            return JSONResponse({"detail": "missing client header"}, status_code=403)  # a cross-site form cannot set this header
        request.state.user_id = user_id
        request.state.user_key = user_key
        request.state.login_check = mode
        if mode == "report" and not warned:  # once per start-up, on the first request served in report mode
            warned.append(True)
            log.warning("login check is in report mode")
        return await call_next(request)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    @app.get("/health")
    async def health() -> dict:
        d = os.environ.get("GB_DATA_DIR")
        return {"status": "ok", "data_dir_mounted": bool(d and os.path.isdir(d)),
                "now": datetime.now(LOCAL_TZ).isoformat()}

    @app.get("/healthz")
    async def healthz() -> dict:
        return await health()

    @app.get("/robots.txt", response_class=PlainTextResponse)
    async def robots() -> str:
        return "User-agent: *\nDisallow: /\n"

    app.include_router(api_router)

    web_dir = os.environ.get("GB_WEB_DIR", "/app/web_dist")
    if os.path.isdir(web_dir):
        app.mount("/", _Client(directory=web_dir, html=True), name="client")  # after the API routes
    else:
        @app.get("/", response_class=PlainTextResponse, include_in_schema=False)
        async def client_not_built():
            return PlainTextResponse("client not built", status_code=503)
    return app


app = create_app()
