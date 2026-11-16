"""The plan: the savings target and budgets, in the ledger and through the server."""
import pytest

from tests.tracker.conftest import OWNER_EMAIL
from tracker import plan
from tracker.store import open_db


@pytest.fixture
def conn(tmp_path):
    c = open_db(str(tmp_path / "tracker.db"))
    yield c
    c.close()


def test_the_target_starts_at_the_first_step_and_can_be_moved(conn):
    assert plan.target(conn, 1) == 0.15
    plan.set_target(conn, 1, 0.2)
    plan.set_target(conn, 1, 0.25)
    assert plan.target(conn, 1) == 0.25


@pytest.mark.parametrize("bad", [-0.1, 0.95, "0.2", None, True])
def test_a_target_outside_its_range_is_refused(conn, bad):
    with pytest.raises(ValueError):
        plan.set_target(conn, 1, bad)


def test_a_category_has_one_budget_which_can_be_changed_and_removed(conn):
    plan.set_budget(conn, 1, "Groceries", 40000, "month")
    plan.set_budget(conn, 1, "Travel", 300000, "year")
    plan.set_budget(conn, 1, " Groceries ", 45000, "month")
    assert plan.budgets(conn, 1) == [{"category": "Groceries", "cents": 45000, "period": "month"},
                                     {"category": "Travel", "cents": 300000, "period": "year"}]
    plan.clear_budget(conn, 1, "Travel")
    assert [b["category"] for b in plan.budgets(conn, 1)] == ["Groceries"]


@pytest.mark.parametrize("category, cents, period", [("", 100, "month"), ("Groceries", 0, "month"),
                                                     ("Groceries", -5, "month"), ("Groceries", 12.5, "month"),
                                                     ("Groceries", 100, "week")])
def test_a_budget_that_makes_no_sense_is_refused(conn, category, cents, period):
    with pytest.raises(ValueError):
        plan.set_budget(conn, 1, category, cents, period)


@pytest.fixture
def client(make_client, token):
    c = make_client()
    c.headers["Cf-Access-Jwt-Assertion"] = token(OWNER_EMAIL)
    return c


def test_the_plan_through_the_server(client):
    assert client.get("/api/v1/plan").json() == {"target": 0.15, "budgets": []}
    assert client.put("/api/v1/plan/target", json={"target": 0.2}).json()["target"] == 0.2
    assert client.put("/api/v1/plan/target", json={"target": 2}).status_code == 422
    body = client.put("/api/v1/plan/budgets", json={"category": "Coffee", "cents": 6000, "period": "month"}).json()
    assert body["budgets"] == [{"category": "Coffee", "cents": 6000, "period": "month"}]
    assert client.put("/api/v1/plan/budgets", json={"category": "Coffee", "cents": 0, "period": "month"}).status_code == 422
    assert client.request("DELETE", "/api/v1/plan/budgets", json={"category": "Coffee"}).json()["budgets"] == []
    assert client.get("/api/v1/months").json()["target"] == 0.2
