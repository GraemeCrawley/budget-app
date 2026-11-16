"""Read-only JSON API over the ledger. Money is integer cents; savings_rate is the one float."""
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tracker import plan, push
from tracker.blocks import BLOCKS, CATEGORY_BLOCK, block_of
from tracker.classify import classify
from tracker.corrections import clear_override, correct_merchant, count_merchant_charges, known_categories, set_override
from tracker.coverage import coverage, data_through
from connectors.contract import ACCOUNT_KINDS
from tracker.months import month_facts
from tracker.review import mark_reviewed, review, transaction_dict
from tracker.store import LedgerNeedsUpgrade, open_db, open_readonly, write_tx
from tracker.uploads import MAX_UPLOAD_BYTES, REASONS, PeriodRefused, take_upload, widen_period

YM_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
SPENDING_LIKE = ("spending", "bucket", "offset")

def current_user(request: Request) -> int:
    """The user id the login middleware verified for this request. No middleware, no user: fail closed."""
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return user_id


router = APIRouter(prefix="/api/v1")


@contextmanager
def _db():
    data_dir = os.environ.get("GB_DATA_DIR")
    if not data_dir or not os.path.isdir(data_dir):
        raise HTTPException(status_code=503, detail="data directory not available")
    try:
        conn = open_readonly(os.path.join(data_dir, "tracker.db"))
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="no ledger yet")
    except LedgerNeedsUpgrade:
        raise HTTPException(status_code=503, detail="ledger needs upgrading")
    try:
        yield conn
    finally:
        conn.close()


_WRITE_LOCK = threading.Lock()


@contextmanager
def _db_write():
    """The ledger opened for writing; same 503s as _db(), and it never creates a missing ledger."""
    data_dir = os.environ.get("GB_DATA_DIR")
    if not data_dir or not os.path.isdir(data_dir):
        raise HTTPException(status_code=503, detail="data directory not available")
    path = os.path.join(data_dir, "tracker.db")
    if not os.path.isfile(path):
        raise HTTPException(status_code=503, detail="no ledger yet")
    # One writer at a time inside this server: a second write waits its turn here, instead of
    # racing the first for the file's lock and failing with "database is locked".
    with _WRITE_LOCK:
        try:
            conn = open_db(path)
        except LedgerNeedsUpgrade:
            raise HTTPException(status_code=503, detail="ledger needs upgrading")
        except sqlite3.OperationalError as e:
            if "locked" not in str(e):
                raise
            raise HTTPException(status_code=503, detail="the ledger is busy; try again in a moment")
        try:
            yield conn
        finally:
            conn.close()


@router.get("/months")
def list_months(user_id: int = Depends(current_user)):
    with _db() as conn:
        return {"months": [asdict(m) for m in month_facts(conn, user_id)],
                "data_through": data_through(conn, user_id), "target": plan.target(conn, user_id)}


@router.get("/months/{ym}")
def one_month(ym: str = Path(pattern=YM_PATTERN), user_id: int = Depends(current_user)):
    with _db() as conn:
        classified = classify(conn, user_id)
        facts = next((m for m in month_facts(conn, user_id, classified) if m.month == ym), None)
        if facts is None:
            raise HTTPException(status_code=404, detail="no data for that month")
        groups: dict[tuple[str, str], list[int]] = {}
        for c in classified:
            if c.date[:7] == ym and c.kind in SPENDING_LIKE:
                entry = groups.setdefault((c.category, block_of(c)), [0, 0])
                entry[0] -= c.amount_cents
                entry[1] += 1
        categories = [{"category": cat, "block": block, "cents": v[0], "count": v[1]}
                      for (cat, block), v in groups.items()]
        categories.sort(key=lambda r: (-r["cents"], r["category"]))
        return {**asdict(facts), "categories": categories}


@router.get("/transactions")
def transactions(month: str | None = Query(default=None, pattern=YM_PATTERN), block: str | None = None,
                 category: str | None = None, user_id: int = Depends(current_user)):
    if block is not None and block not in BLOCKS:
        raise HTTPException(status_code=422, detail="unknown block")
    with _db() as conn:
        out = []
        for c in classify(conn, user_id):
            if month is not None and c.date[:7] != month:
                continue
            row_block = block_of(c) if c.kind in SPENDING_LIKE else None
            if block is not None and row_block != block:
                continue
            if category is not None and c.category != category:
                continue
            out.append(transaction_dict(c))
        out.sort(key=lambda t: (t["date"], t["id"]), reverse=True)
        return {"transactions": out}


def _account_dicts(conn, user_id: int, key: str | None = None) -> list[dict]:
    cov = coverage(conn, user_id)
    rows = conn.execute(
        "SELECT key, name, kind, institution, export_note, flip_sign FROM accounts WHERE user_id = ?"
        " AND (? IS NULL OR key = ?) ORDER BY key", (user_id, key, key)).fetchall()
    return [{"key": a["key"], "name": a["name"], "kind": a["kind"], "institution": a["institution"],
             "export_note": a["export_note"], "data_through": cov[a["key"]][-1][1] if a["key"] in cov else None,
             "ranges": [list(r) for r in cov.get(a["key"], [])], "flip_sign": a["flip_sign"]}
            for a in rows]


@router.get("/accounts")
@router.get("/coverage")
def accounts_view(user_id: int = Depends(current_user)):
    with _db() as conn:
        return {"accounts": _account_dicts(conn, user_id)}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class AccountBody(BaseModel):
    name: str
    kind: str
    institution: str = ""


class AccountPatch(BaseModel):
    name: str | None = None
    export_note: str | None = None


def _clean_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 80:
        raise HTTPException(status_code=422, detail="the name must be 1 to 80 characters")
    return name


@router.post("/accounts", status_code=201)
def create_account(body: AccountBody, user_id: int = Depends(current_user)):
    name = _clean_name(body.name)
    if body.kind not in ACCOUNT_KINDS:
        raise HTTPException(status_code=422, detail="unknown kind of account")
    institution = body.institution.strip()
    if len(institution) > 80:
        raise HTTPException(status_code=422, detail="the institution must be at most 80 characters")
    key = _slug(name)
    if not key:
        raise HTTPException(status_code=422, detail="the name needs a letter or a digit")
    with _db_write() as conn:
        with write_tx(conn):
            if conn.execute("SELECT 1 FROM accounts WHERE user_id = ? AND key = ?", (user_id, key)).fetchone():
                raise HTTPException(status_code=409, detail="an account with that name already exists")
            conn.execute("INSERT INTO accounts (user_id, key, name, kind, institution) VALUES (?, ?, ?, ?, ?)",
                         (user_id, key, name, body.kind, institution))
        return _account_dicts(conn, user_id, key)[0]


@router.patch("/accounts/{key}")
def patch_account(key: str, body: AccountPatch, user_id: int = Depends(current_user)):
    given = {n: getattr(body, n) for n in body.model_fields_set if getattr(body, n) is not None}
    if not given:
        raise HTTPException(status_code=422, detail="give a name or an export note")
    if "name" in given:
        given["name"] = _clean_name(given["name"])
    if len(given.get("export_note", "")) > 2000:
        raise HTTPException(status_code=422, detail="the export note is too long")
    with _db_write() as conn:
        with write_tx(conn):
            if not conn.execute("SELECT 1 FROM accounts WHERE user_id = ? AND key = ?", (user_id, key)).fetchone():
                raise HTTPException(status_code=404, detail="no such account")
            for column, value in given.items():  # column names come from the two fixed fields above
                conn.execute(f"UPDATE accounts SET {column} = ? WHERE user_id = ? AND key = ?", (value, user_id, key))
        return _account_dicts(conn, user_id, key)[0]


FORM_OVERHEAD_BYTES = 64 * 1024


def _too_large() -> JSONResponse:
    return JSONResponse({"ok": False, "code": "too_large", "reason": REASONS["too_large"]}, status_code=413)


@router.post("/uploads")
async def post_upload(request: Request, user_id: int = Depends(current_user)):
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES + FORM_OVERHEAD_BYTES:
        return _too_large()  # refused before the body is read
    form = await request.form()
    file = form.get("file")
    if not hasattr(file, "read"):
        raise HTTPException(status_code=422, detail="send the file as the form field 'file'")
    account_key, signs = form.get("account_key"), form.get("signs") or None
    if not isinstance(account_key, (str, type(None))) or signs not in (None, "as_is", "flip"):
        raise HTTPException(status_code=422, detail="signs must be as_is or flip")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return _too_large()

    def run():
        with _db_write() as conn:
            return take_upload(conn, user_id, file.filename or "", data, account_key=account_key or None, signs=signs)
    outcome = await run_in_threadpool(run)
    if outcome.ok:
        return {"ok": True, "batches": outcome.batches}
    return JSONResponse({"ok": False, "code": outcome.code, "reason": outcome.reason, "needs": outcome.needs},
                        status_code=422)


class PeriodBody(BaseModel):
    period_start: str
    period_end: str


@router.patch("/batches/{batch_id}/period")
def patch_batch_period(batch_id: int, body: PeriodBody, user_id: int = Depends(current_user)):
    with _db_write() as conn:
        try:
            return widen_period(conn, user_id, batch_id, body.period_start, body.period_end)
        except LookupError:
            raise HTTPException(status_code=404, detail="no such batch")
        except PeriodRefused as exc:
            raise HTTPException(status_code=422, detail=str(exc))


@router.get("/me")
def me(request: Request, user_id: int = Depends(current_user)):
    return {"user": request.state.user_key, "login_check": request.state.login_check}


def _one_transaction(conn, user_id: int, transaction_id: int) -> dict:
    """The transaction object for a live charge of this user; 404 for any other."""
    for c in classify(conn, user_id):
        if c.id == transaction_id:
            return transaction_dict(c)
    raise HTTPException(status_code=404, detail="no such transaction")


@router.get("/categories")
def categories(user_id: int = Depends(current_user)):
    with _db() as conn:
        names = known_categories(conn, user_id)
        return {"categories": names, "blocks": {n: CATEGORY_BLOCK.get(n, "Everything else") for n in names}}


@router.get("/transactions/{transaction_id}")
def one_transaction(transaction_id: int, user_id: int = Depends(current_user)):
    with _db() as conn:
        txn = _one_transaction(conn, user_id, transaction_id)
        sign = 1 if txn["amount_cents"] > 0 else -1 if txn["amount_cents"] < 0 else 0
        return {**txn, "merchant_charges": count_merchant_charges(conn, user_id, txn["merchant"], sign)}


class OverrideBody(BaseModel):
    kind: str | None = None
    category: str | None = None
    one_off: bool | None = None


@router.put("/transactions/{transaction_id}/override")
def put_override(transaction_id: int, body: OverrideBody, user_id: int = Depends(current_user)):
    given = {name: getattr(body, name) for name in body.model_fields_set}  # present (even null) vs absent
    if given.get("category") == "":
        raise HTTPException(status_code=422, detail="category must not be empty")
    with _db_write() as conn:
        try:
            set_override(conn, user_id, transaction_id, **given)
        except LookupError:
            raise HTTPException(status_code=404, detail="no such transaction")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return _one_transaction(conn, user_id, transaction_id)


@router.delete("/transactions/{transaction_id}/override")
def delete_override(transaction_id: int, user_id: int = Depends(current_user)):
    with _db_write() as conn:
        try:
            clear_override(conn, user_id, transaction_id)
        except LookupError:
            raise HTTPException(status_code=404, detail="no such transaction")
        return _one_transaction(conn, user_id, transaction_id)


class MerchantRuleBody(BaseModel):
    kind: str
    category: str | None = None  # needed for spending, bucket and offset; not stored for the other kinds
    one_off: bool = False


@router.post("/transactions/{transaction_id}/merchant-rule")
def post_merchant_rule(transaction_id: int, body: MerchantRuleBody, user_id: int = Depends(current_user)):
    if body.kind in SPENDING_LIKE and not body.category:
        raise HTTPException(status_code=422, detail="category must not be empty")
    with _db_write() as conn:
        try:
            charges = correct_merchant(conn, user_id, transaction_id, body.kind, body.category or "",
                                       int(body.one_off))
        except LookupError:
            raise HTTPException(status_code=404, detail="no such transaction")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return {"merchant": _one_transaction(conn, user_id, transaction_id)["merchant"], "charges": charges}


@router.get("/review")
def review_view(month: str | None = Query(default=None, pattern=YM_PATTERN), user_id: int = Depends(current_user)):
    with _db() as conn:
        return review(conn, user_id, month)


@router.post("/months/{ym}/reviewed")
def post_reviewed(ym: str = Path(pattern=YM_PATTERN), user_id: int = Depends(current_user)):
    with _db_write() as conn:
        mark_reviewed(conn, user_id, ym)
        return {"month": ym, "reviewed": True}


# --- the app's own phone notifications ---

class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionBody(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


class EndpointBody(BaseModel):
    endpoint: str


class PushEventBody(BaseModel):
    id: str
    kind: str


def _data_dir() -> str:
    return os.environ["GB_DATA_DIR"]  # _db() and _db_write() have already refused a missing one


@router.get("/push")
def push_state(user_id: int = Depends(current_user)):
    """The key a phone subscribes with, how many phones are subscribed, and the last notification sent."""
    with _db() as conn:
        return {"key": push.public_key(_data_dir()), "phones": push.count(conn, user_id),
                "last": push.last_notification(conn, user_id)}


@router.post("/push/subscriptions")
def push_subscribe(body: SubscriptionBody, user_id: int = Depends(current_user)):
    with _db_write() as conn:
        try:
            push.save_subscription(conn, user_id, body.endpoint, body.keys.p256dh, body.keys.auth)
        except ValueError:
            raise HTTPException(status_code=422, detail="not a push subscription")
        return {"phones": push.count(conn, user_id)}


@router.delete("/push/subscriptions")
def push_unsubscribe(body: EndpointBody, user_id: int = Depends(current_user)):
    with _db_write() as conn:
        push.remove_subscription(conn, user_id, body.endpoint)
        return {"phones": push.count(conn, user_id)}


@router.post("/push/test")
def push_test(user_id: int = Depends(current_user)):
    with _db_write() as conn:
        if push.count(conn, user_id) == 0:
            raise HTTPException(status_code=409, detail="no phone has reminders turned on yet")
        return push.send(conn, _data_dir(), user_id, "test", "Budget: test reminder",
                         "Reminders work on this phone. Tap to open the app.", "#/settings")


@router.post("/push/events", status_code=204)
def push_event(body: PushEventBody, user_id: int = Depends(current_user)):
    with _db_write() as conn:
        try:
            push.mark(conn, user_id, body.id[:32], body.kind)
        except ValueError:
            raise HTTPException(status_code=422, detail="unknown event")


# --- the plan: the savings target and budgets ---

class TargetBody(BaseModel):
    target: float


class BudgetBody(BaseModel):
    category: str
    cents: int
    period: str


class CategoryBody(BaseModel):
    category: str


def _plan(conn, user_id: int) -> dict:
    return {"target": plan.target(conn, user_id), "budgets": plan.budgets(conn, user_id)}


@router.get("/plan")
def plan_view(user_id: int = Depends(current_user)):
    with _db() as conn:
        return _plan(conn, user_id)


@router.put("/plan/target")
def put_target(body: TargetBody, user_id: int = Depends(current_user)):
    with _db_write() as conn:
        try:
            plan.set_target(conn, user_id, body.target)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return _plan(conn, user_id)


@router.put("/plan/budgets")
def put_budget(body: BudgetBody, user_id: int = Depends(current_user)):
    with _db_write() as conn:
        try:
            plan.set_budget(conn, user_id, body.category, body.cents, body.period)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return _plan(conn, user_id)


@router.delete("/plan/budgets")
def delete_budget(body: CategoryBody, user_id: int = Depends(current_user)):
    with _db_write() as conn:
        plan.clear_budget(conn, user_id, body.category)
        return _plan(conn, user_id)
