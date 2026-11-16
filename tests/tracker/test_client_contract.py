"""The phone client against the real server.

web/ was built against its own mock from the written contract. This builds a small invented ledger through the real
app and checks, endpoint by endpoint, that every field the client reads is there with the type the client expects.
The `*_FIELDS` dicts below are what `web/src` reads (screens and components, not mock.js): when a screen starts
reading another property, add it here. `None` in a type tuple means the client copes with null there.
"""
from pathlib import Path

import pytest

from tests.tracker.conftest import OWNER_EMAIL
from tracker.uploads import REASONS

FX = Path(__file__).parent.parent / "fixtures" / "connectors"
API = "/api/v1"
NONE = type(None)
BLOCKS = ["Food", "Bills", "Subscriptions", "Big purchases", "Buckets", "Everything else"]

ME_FIELDS = {"login_check": str}                                     # App.jsx (the notice in report mode)
MONTHS_FIELDS = {"months": list, "data_through": dict, "target": float}               # Home, Block
MONTH_FIELDS = {                                                     # Home, RateChart, BlockChart, Block
    "month": str, "income_cents": int, "spending_cents": int, "savings_rate": (float, int, NONE),
    "blocks": dict, "categories": dict, "food_out_cents": int, "food_home_cents": int, "complete": bool, "provisional": bool,
    "uncategorised_count": int, "unconfirmed_income_count": int, "changed_since_review": bool,
}
ACCOUNT_FIELDS = {                                                   # Home, Add, AccountCard, UploadRefusal
    "key": str, "name": str, "export_note": (str, NONE), "data_through": (str, NONE), "ranges": list,
}
CHARGE_FIELDS = {                                                    # ChargeRow, Block, Charge, Review, PlaceGroup
    "id": int, "date": str, "amount_cents": int, "description": str, "account_name": str, "kind": str,
    "category": str, "block": (str, NONE), "one_off": bool, "provisional": bool, "why": str, "guessed": bool,
    "merchant": str,
}
ONE_CHARGE_FIELDS = {**CHARGE_FIELDS, "merchant_charges": int}       # Charge (GET one)
CATEGORIES_FIELDS = {"categories": list, "blocks": dict}             # CategoryPicker
REVIEW_FIELDS = {"unplaced": list, "unconfirmed_income": list, "recognised": list}  # Review
GROUP_FIELDS = {"merchant": str, "count": int, "cents": int, "charges": list}       # PlaceGroup
RECOGNISED_FIELDS = {"category": str, "block": (str, NONE), "cents": int, "charges": list}  # Review
FIRST_TIME_FIELDS = {"first_time": bool}                             # ChargeRow, on recognised charges only
BATCH_FIELDS = {                                                     # UploadResult
    "id": int, "account_name": str, "period_start": str, "period_end": str, "status": str, "added": int,
    "already_held": int, "confirmed": int, "differences": list, "message": (str, NONE), "can_widen": bool,
}
REFUSAL_FIELDS = {"reason": str, "needs": (dict, NONE)}              # Add (e.body.reason), UploadRefusal
REVIEWED_FIELDS = {"reviewed": bool}                                 # Review (Done)
RULE_FIELDS = {"merchant": str, "charges": int}


def check(body, fields, where=""):
    assert isinstance(body, dict), f"{where}: not an object: {body!r}"
    for name, kinds in fields.items():
        assert name in body, f"{where}: the client reads `{name}`, which the server does not send"
        kinds = kinds if isinstance(kinds, tuple) else (kinds,)
        ok = isinstance(body[name], kinds) and not (bool not in kinds and isinstance(body[name], bool))
        assert ok, f"{where}: `{name}` is {type(body[name]).__name__} ({body[name]!r}), the client expects {kinds}"


@pytest.fixture
def client(make_client, token):
    c = make_client()
    c.headers["Cf-Access-Jwt-Assertion"] = token(OWNER_EMAIL)
    return c


def upload(client, name, data=None, **form):
    data = (FX / name).read_bytes() if data is None else data
    return client.post(f"{API}/uploads", files={"file": (name, data, "application/octet-stream")}, data=form)


@pytest.fixture
def ledger(client):
    """A February statement (chequing) and a January-February card statement, both through the front door; an
    activity export for April that is then widened; an override, a merchant rule, and February marked reviewed."""
    assert upload(client, "cibc_statement.txt").status_code == 200
    assert upload(client, "amex_statement.txt").status_code == 200
    r = client.post(f"{API}/accounts", json={"name": "Invented Chequing", "kind": "chequing"})
    assert r.status_code == 201
    r = upload(client, "activity_generic.csv", account_key="invented-chequing")
    (batch,) = r.json()["batches"]
    review = client.get(f"{API}/review?month=2026-02").json()
    grocer = next(g for g in review["unplaced"] if g["merchant"] == "INVENTED GROCER")
    assert client.post(f"{API}/transactions/{grocer['charges'][0]['id']}/merchant-rule",
                       json={"kind": "spending", "category": "Groceries"}).status_code == 200
    store = next(g for g in review["unplaced"] if g["merchant"] == "INVENTED STORE")
    assert client.put(f"{API}/transactions/{store['charges'][0]['id']}/override",
                      json={"category": "Gifts", "one_off": True}).status_code == 200
    assert client.post(f"{API}/months/2026-02/reviewed").status_code == 200
    return {"batch": batch, "grocer_id": grocer["charges"][0]["id"], "store_id": store["charges"][0]["id"]}


def test_me(client):
    check(client.get(f"{API}/me").json(), ME_FIELDS, "GET me")


def test_months(client, ledger):
    body = client.get(f"{API}/months").json()
    check(body, MONTHS_FIELDS, "GET months")
    assert all(isinstance(v, str) for v in body["data_through"].values())  # Home sorts them as dates
    months = body["months"]
    assert [m["month"] for m in months] == sorted(m["month"] for m in months)  # prev/next and the chart read in order
    for m in months:
        check(m, MONTH_FIELDS, f"GET months {m['month']}")
        assert list(m["blocks"]) == BLOCKS and all(isinstance(v, int) for v in m["blocks"].values())
    feb = next(m for m in months if m["month"] == "2026-02")
    assert feb["reviewed"] is True and feb["unconfirmed_income_count"] == 1
    assert feb["uncategorised_count"] >= 1


def test_accounts(client, ledger):
    accounts = client.get(f"{API}/accounts").json()["accounts"]
    assert len(accounts) == 3
    for a in accounts:
        check(a, ACCOUNT_FIELDS, "GET accounts")
        assert all(len(r) == 2 and all(isinstance(d, str) for d in r) for r in a["ranges"])
    created = client.post(f"{API}/accounts", json={"name": "Another Invented", "kind": "card"})
    assert created.status_code == 201
    check(created.json(), ACCOUNT_FIELDS, "POST accounts")
    assert created.json()["data_through"] is None
    noted = client.patch(f"{API}/accounts/another-invented", json={"export_note": "Menu, then Export"})
    check(noted.json(), ACCOUNT_FIELDS, "PATCH accounts")
    assert noted.json()["export_note"] == "Menu, then Export"


def test_transactions_for_a_block_and_one_charge(client, ledger):
    rows = client.get(f"{API}/transactions?month=2026-02&block=Everything%20else").json()["transactions"]
    assert rows
    for t in rows:
        check(t, CHARGE_FIELDS, "GET transactions")
        assert t["block"] == "Everything else"
    one = client.get(f"{API}/transactions/{ledger['grocer_id']}").json()
    check(one, ONE_CHARGE_FIELDS, "GET transactions/id")
    assert one["category"] == "Groceries" and one["merchant_charges"] == 2 and one["guessed"] is False


def test_a_charge_that_is_counted_is_not_shown_as_a_guess_about_income(client, ledger):
    """The Charge screen says "This looks like income" for `guessed`; the server also sets `guessed` on spending
    it could not place, so the screen must look at `kind` too (see Charge.jsx)."""
    review = client.get(f"{API}/review?month=2026-02").json()
    spending_guesses = [c for g in review["unplaced"] for c in g["charges"] if c["guessed"] and c["kind"] == "spending"]
    assert spending_guesses, "the server marks unplaced spending as guessed; the client must not call it income"


def test_overrides_and_merchant_rules(client, ledger):
    t = client.put(f"{API}/transactions/{ledger['store_id']}/override", json={"one_off": False}).json()
    check(t, CHARGE_FIELDS, "PUT override")
    assert t["category"] == "Gifts" and t["why"] == "you set this"
    t = client.delete(f"{API}/transactions/{ledger['store_id']}/override").json()
    check(t, CHARGE_FIELDS, "DELETE override")
    assert "merchant_charges" not in t  # the client keeps the one it already had
    check(client.post(f"{API}/transactions/{ledger['store_id']}/merchant-rule",
                      json={"kind": "spending", "category": "Gifts"}).json(), RULE_FIELDS, "POST merchant-rule")


def test_categories(client, ledger):
    body = client.get(f"{API}/categories").json()
    check(body, CATEGORIES_FIELDS, "GET categories")
    assert all(isinstance(c, str) for c in body["categories"])
    assert all(body["blocks"][c] in BLOCKS for c in body["categories"])  # the picker shows blocks[name]


def test_review(client, ledger):
    body = client.get(f"{API}/review?month=2026-02").json()
    check(body, REVIEW_FIELDS, "GET review")
    assert body["unplaced"] and body["unconfirmed_income"] and body["recognised"]
    for g in body["unplaced"]:
        check(g, GROUP_FIELDS, "review.unplaced")
        assert g["count"] == len(g["charges"])
        for c in g["charges"]:
            check(c, CHARGE_FIELDS, "review.unplaced.charges")
    # a group with no merchant is set charge by charge: the client reads merchant "" for it
    assert any(g["merchant"] == "" for g in body["unplaced"])
    for c in body["unconfirmed_income"]:
        check(c, CHARGE_FIELDS, "review.unconfirmed_income")
        assert c["kind"] == "income" and c["guessed"] is True
    for cat in body["recognised"]:
        check(cat, RECOGNISED_FIELDS, "review.recognised")
        for c in cat["charges"]:
            check(c, {**CHARGE_FIELDS, **FIRST_TIME_FIELDS}, "review.recognised.charges")
    # the same call for a month with nothing in it is the empty shape, not an error
    empty = client.get(f"{API}/review?month=2030-01").json()
    check(empty, REVIEW_FIELDS, "GET review (empty)")


def test_mark_reviewed(client, ledger):
    r = client.post(f"{API}/months/2026-04/reviewed")
    assert r.status_code == 200
    check(r.json(), REVIEWED_FIELDS, "POST reviewed")
    after = {m["month"]: m for m in client.get(f"{API}/months").json()["months"]}
    assert after["2026-04"]["reviewed"] is True


def test_upload_success_and_duplicate(client, ledger):
    accounts = {a["key"] for a in client.get(f"{API}/accounts").json()["accounts"]}
    assert "invented-chequing" in accounts
    b = ledger["batch"]
    check(b, BATCH_FIELDS, "POST uploads")
    assert b["status"] == "accepted" and b["can_widen"] is True and b["account_name"] == "Invented Chequing"
    again = upload(client, "activity_generic.csv", account_key="invented-chequing").json()
    (dup,) = again["batches"]
    check(dup, BATCH_FIELDS, "POST uploads (duplicate)")
    assert dup["status"] == "duplicate"  # the only status the client treats specially
    s = upload(client, "cibc_statement.txt").json()  # the same statement again, naming its own account
    assert s["batches"][0]["status"] == "duplicate"


def test_widen_a_period(client, ledger):
    b = ledger["batch"]
    r = client.patch(f"{API}/batches/{b['id']}/period", json={"period_start": "2026-04-01", "period_end": "2026-04-30"})
    assert r.status_code == 200
    check(r.json(), BATCH_FIELDS, "PATCH batches period")
    assert r.json()["can_widen"] is False and r.json()["period_end"] == "2026-04-30"


def test_a_refused_widening_carries_its_sentence_as_detail(client, ledger):
    b = ledger["batch"]
    r = client.patch(f"{API}/batches/{b['id']}/period", json={"period_start": "2026-04-01", "period_end": "2027-12-31"})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str) and r.json()["detail"]  # ApiError.detail, shown as given
    assert "reason" not in r.json()


def test_a_file_that_does_not_say_its_account_needs_one(client, ledger):
    r = upload(client, "activity_generic.csv")
    assert r.status_code == 422
    check(r.json(), REFUSAL_FIELDS, "account_needed")
    assert r.json()["code"] == "account_needed" and r.json()["reason"] == REASONS["account_needed"]
    assert r.json()["needs"] == {"choose_account": True}


def test_a_card_file_that_looks_reversed_asks_about_signs(client, ledger):
    client.post(f"{API}/accounts", json={"name": "Invented Card", "kind": "card"})
    rows = b"Date,Description,Amount\n2026-03-03,INVENTED SHOP,5.00\n2026-03-04,INVENTED CAFE,7.00\n"
    r = upload(client, "card.csv", rows, account_key="invented-card")
    assert r.status_code == 422
    check(r.json(), REFUSAL_FIELDS, "signs_look_reversed")
    assert r.json()["code"] == "signs_look_reversed" and r.json()["needs"] == {"choose_signs": True}
    # the same File is sent again with signs=flip (or as_is) and the account it was already given
    assert upload(client, "card.csv", rows, account_key="invented-card", signs="flip").status_code == 200


def test_a_file_for_another_account_names_the_account_it_is_for(client, ledger):
    r = upload(client, "cibc_statement.txt", account_key="amex-cobalt")
    assert r.status_code == 422
    check(r.json(), REFUSAL_FIELDS, "wrong_account")
    assert r.json()["code"] == "wrong_account"
    owner = r.json()["needs"]["file_is_for"]
    names = {a["name"] for a in client.get(f"{API}/accounts").json()["accounts"]}
    assert owner in names  # the client finds the account by this name to offer "Send it to ..."


def test_a_file_over_the_limit_is_413_with_a_reason_and_no_needs(client, ledger):
    r = upload(client, "big.csv", b"x" * (10 * 1024 * 1024 + 1))
    assert r.status_code == 413
    check({**r.json(), "needs": r.json().get("needs")}, REFUSAL_FIELDS, "too_large")  # the client reads `needs || {}`
    assert r.json()["reason"] == REASONS["too_large"]


def test_every_other_refusal_has_a_reason_the_client_can_show(client, ledger):
    r = upload(client, "x.bin", b"hello\n", account_key="invented-chequing")
    assert r.status_code == 422
    check(r.json(), REFUSAL_FIELDS, "no_format")
    assert r.json()["needs"] is None


def test_an_unknown_api_path_is_json(client, ledger):
    r = client.get(f"{API}/nonsense")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}
