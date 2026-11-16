import pytest
from tests.tracker.test_classify import put, put_feb, CHQ, CARD, SEED
from tracker.corrections import set_override
from tracker.months import month_facts
from tracker.review import review, mark_reviewed
from tracker.rules import seed_rules
from tracker.store import open_db


@pytest.fixture
def conn(tmp_path):
    c = open_db(str(tmp_path / "t.db"))
    seed_rules(c, 1, SEED)
    put(c, CHQ, [("2026-01-15", 300000, "EMPLOYER PAY"), ("2026-01-20", 1234, "MYSTERY DEPOSIT")], "chq")
    put(c, CARD, [("2026-01-05", -4500, "INVENTED GROCER 12"),
                  ("2026-01-08", -899, "BOOK BARN 4411"), ("2026-01-09", -899, "BOOK BARN 5522"),
                  ("2026-01-22", -999, "UNKNOWN PLACE"), ("2026-01-23", -250, "RETAIL PURCHASE 123456"),
                  ("2026-01-24", -3000, "CORNER GROCER")], "card")
    put_feb(c, CARD, [("2026-02-02", -2000, "INVENTED GROCER 12"), ("2026-02-03", -1100, "NEW GROCER"),
                  ("2026-02-04", -300, "BOOK BARN 6633")], "card2")
    return c


def facts(conn):
    return {m.month: m for m in month_facts(conn, 1)}


def tid(conn, description):
    return conn.execute("SELECT id FROM transactions WHERE description = ?", (description,)).fetchone()["id"]


def test_review_lists_unplaced_by_merchant_then_unconfirmed_income_then_recognised(conn):
    r = review(conn, 1, "2026-01")
    assert r["month"] == "2026-01" and r["reviewed"] is False
    assert [(g["merchant"], g["count"], g["cents"]) for g in r["unplaced"]] == [
        ("BOOK BARN", 2, 1798), ("UNKNOWN PLACE", 1, 999), ("", 1, 250)]
    assert [t["description"] for t in r["unplaced"][0]["charges"]] == ["BOOK BARN 5522", "BOOK BARN 4411"]
    assert [(t["description"], t["kind"], t["guessed"]) for t in r["unconfirmed_income"]] == [
        ("MYSTERY DEPOSIT", "income", True)]
    assert [(g["category"], g["block"], g["cents"]) for g in r["recognised"]] == [("Groceries", "Food", 7500)]


def test_a_first_time_merchant_sorts_before_a_repeat_one(conn):
    (g,) = review(conn, 1, "2026-01")["recognised"]
    assert [(t["description"], t["first_time"]) for t in g["charges"]] == [
        ("INVENTED GROCER 12", True), ("CORNER GROCER", True)]
    (g,) = review(conn, 1, "2026-02")["recognised"]
    assert (g["category"], g["cents"]) == ("Groceries", 3100)
    assert [(t["description"], t["first_time"]) for t in g["charges"]] == [
        ("NEW GROCER", True), ("INVENTED GROCER 12", False)]
    (u,) = review(conn, 1, "2026-02")["unplaced"]
    assert (u["merchant"], u["count"], u["cents"]) == ("BOOK BARN", 1, 300)
    assert "first_time" not in u["charges"][0]


def test_an_empty_merchant_key_is_never_first_time(conn):
    put(conn, CARD, [("2026-01-26", -111, "RETAIL PURCHASE 654321")], "cardx")
    set_override(conn, 1, tid(conn, "RETAIL PURCHASE 654321"), category="Groceries")
    (g,) = review(conn, 1, "2026-01")["recognised"]
    t = next(t for t in g["charges"] if t["description"] == "RETAIL PURCHASE 654321")
    assert (t["merchant"], t["first_time"]) == ("", False)


def test_a_month_with_no_data_reviews_empty(conn):
    assert review(conn, 1, "2030-05") == {"month": "2030-05", "unplaced": [], "unconfirmed_income": [],
                                          "recognised": [], "reviewed": False}


def test_a_reviewed_month_says_when_its_totals_later_change(conn):
    assert not facts(conn)["2026-01"].reviewed
    mark_reviewed(conn, 1, "2026-01")
    assert facts(conn)["2026-01"].reviewed and not facts(conn)["2026-01"].changed_since_review
    assert not facts(conn)["2026-02"].reviewed
    assert review(conn, 1, "2026-01")["reviewed"] is True
    set_override(conn, 1, tid(conn, "INVENTED GROCER 12"), kind="transfer")
    assert facts(conn)["2026-01"].changed_since_review
    mark_reviewed(conn, 1, "2026-01")
    assert not facts(conn)["2026-01"].changed_since_review


def test_a_merchant_with_charges_and_refunds_is_two_groups_of_one_sign_each(conn):
    put(conn, CARD, [("2026-01-26", 400, "BOOK BARN 7744")], "card-refund")
    r = review(conn, 1, "2026-01")
    books = [g for g in r["unplaced"] if g["merchant"] == "BOOK BARN"]
    assert [(g["count"], g["cents"]) for g in books] == [(2, 1798), (1, -400)]
    for g in books:
        assert set(g) == {"merchant", "count", "cents", "charges"}
        assert len({c["amount_cents"] > 0 for c in g["charges"]}) == 1
    assert books[1]["charges"][0]["amount_cents"] == 400


def test_review_without_a_month_lists_what_needs_a_decision_across_every_month(conn):
    r = review(conn, 1, None)
    assert r["month"] is None and r["reviewed"] is False and r["recognised"] == []
    assert [(g["merchant"], g["count"], g["cents"]) for g in r["unplaced"]] == [
        ("BOOK BARN", 3, 2098), ("UNKNOWN PLACE", 1, 999), ("", 1, 250)]
    assert [t["date"][:7] for t in r["unplaced"][0]["charges"]] == ["2026-02", "2026-01", "2026-01"]
    assert [t["description"] for t in r["unconfirmed_income"]] == ["MYSTERY DEPOSIT"]
