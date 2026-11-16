from tests.tracker.test_classify import put, CHQ, CARD
from tracker.store import open_db
from tracker.coverage import coverage, data_through, month_is_complete

def test_ranges_merge_and_completeness(tmp_path):
    conn = open_db(str(tmp_path / "t.db"))
    put(conn, CHQ, [("2026-01-05", -100, "A")], "one")       # helper batches cover 2026-01-01..2026-01-31
    put(conn, CARD, [("2026-01-06", -100, "B")], "two")
    cov = coverage(conn, 1)
    assert cov == {"chq": [("2026-01-01", "2026-01-31")], "card": [("2026-01-01", "2026-01-31")]}
    assert data_through(conn, 1) == {"chq": "2026-01-31", "card": "2026-01-31"}
    assert month_is_complete(cov, "2026-01") and not month_is_complete(cov, "2026-02")

def test_a_gap_makes_a_month_incomplete():
    cov = {"a": [("2026-01-01", "2026-01-20"), ("2026-01-25", "2026-02-28")]}
    assert not month_is_complete(cov, "2026-01") and month_is_complete(cov, "2026-02")

def test_touching_ranges_merge():
    from tracker.coverage import merge_ranges
    assert merge_ranges([("2026-01-16", "2026-02-15"), ("2026-01-01", "2026-01-15")]) == [("2026-01-01", "2026-02-15")]

def test_overlapping_ranges_merge():
    from tracker.coverage import merge_ranges
    assert merge_ranges([("2026-01-01", "2026-01-20"), ("2026-01-18", "2026-01-31"),
                         ("2026-01-05", "2026-01-06")]) == [("2026-01-01", "2026-01-31")]

def test_an_account_added_later_is_ignored_for_earlier_months():
    cov = {"old": [("2026-01-01", "2026-03-31")], "new": [("2026-03-01", "2026-03-31")]}
    assert month_is_complete(cov, "2026-01") and month_is_complete(cov, "2026-02")
    assert month_is_complete(cov, "2026-03")

def test_the_days_before_an_accounts_first_file_do_not_block_its_first_month():
    cov = {"old": [("2026-01-01", "2026-03-31")], "new": [("2026-03-10", "2026-03-31")]}
    assert month_is_complete(cov, "2026-03")


def test_an_account_that_stops_short_or_has_a_gap_blocks_the_month():
    assert not month_is_complete({"new": [("2026-03-10", "2026-03-20")]}, "2026-03")
    assert not month_is_complete({"new": [("2026-03-10", "2026-03-15"), ("2026-03-20", "2026-04-30")]}, "2026-03")

def test_no_accounts_or_all_ignored_is_not_complete():
    assert not month_is_complete({}, "2026-01")
    assert not month_is_complete({"a": [("2026-03-01", "2026-03-31")]}, "2026-01")
