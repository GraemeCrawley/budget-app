import pytest
from tests.tracker.test_store import batch, conn, count  # noqa: F401  (conn is a fixture)
import tracker.store
from tracker.store import accept_batch


def live(conn):
    return [tuple(r) for r in conn.execute(
        "SELECT date, amount_cents, provisional FROM transactions WHERE superseded_by IS NULL ORDER BY date, amount_cents")]


def test_statement_replaces_matching_provisional_rows(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "shop web"), ("2026-01-20", -900, "fuel web")],
                                kind="activity", start="2026-01-05", end="2026-01-20"), b"act", "a.csv")
    r = accept_batch(conn, 1, batch([("2026-01-06", -450, "SHOP 123"), ("2026-01-20", -900, "FUEL 9")]), b"st", "s.txt")
    assert (r.status, r.confirmed, r.differences) == ("accepted", 2, [])
    assert live(conn) == [("2026-01-06", -450, 0), ("2026-01-20", -900, 0)]


def test_differences_are_reported_and_the_statement_wins(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "a"), ("2026-01-09", -777, "b")],
                                kind="activity", start="2026-01-05", end="2026-01-09"), b"act", "a.csv")
    r = accept_batch(conn, 1, batch([("2026-01-05", -450, "A"), ("2026-01-25", -300, "C")]), b"st", "s.txt")
    assert r.confirmed == 1
    # the 25th is outside the export's period, so the statement-only row there is not reported (statement rule 5)
    assert r.differences == ["only in the earlier export: 2026-01-09"]
    assert live(conn) == [("2026-01-05", -450, 0), ("2026-01-25", -300, 0)]


def test_provisional_rows_outside_the_period_are_left_alone(conn):
    accept_batch(conn, 1, batch([("2026-02-02", -100, "later")], kind="activity",
                                start="2026-02-02", end="2026-02-02"), b"act", "a.csv")
    r = accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st", "s.txt")
    assert r.differences == []
    assert ("2026-02-02", -100, 1) in live(conn)


def test_activity_arriving_after_a_statement_does_not_duplicate_its_period(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st", "s.txt")
    r = accept_batch(conn, 1, batch([("2026-01-05", -450, "a web"), ("2026-02-02", -100, "later")],
                                    kind="activity", start="2026-01-05", end="2026-02-02"), b"act", "a.csv")
    assert r.added == 1 and r.already_held == 1
    assert live(conn) == [("2026-01-05", -450, 0), ("2026-02-02", -100, 1)]


def test_one_statement_row_confirms_only_one_of_two_provisional_rows(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "x"), ("2026-01-06", -450, "y")],
                                kind="activity", start="2026-01-05", end="2026-01-06"), b"act", "a.csv")
    r = accept_batch(conn, 1, batch([("2026-01-06", -450, "Z")]), b"st", "s.txt")
    assert r.confirmed == 1
    # the exact-date pair is taken first, so the 5th is the one left over (statement rule 1)
    assert r.differences == ["only in the earlier export: 2026-01-05"]
    assert live(conn) == [("2026-01-06", -450, 0)]


def test_nearest_statement_row_wins_and_earlier_on_a_tie(conn):
    accept_batch(conn, 1, batch([("2026-01-10", -450, "x")], kind="activity",
                                start="2026-01-10", end="2026-01-10"), b"act", "a.csv")
    r = accept_batch(conn, 1, batch([("2026-01-09", -450, "A"), ("2026-01-11", -450, "B")]), b"st", "s.txt")
    assert r.confirmed == 1
    assert r.differences == []  # the 11th is outside the export's period (statement rule 5)
    statement_row = conn.execute("SELECT matched_id FROM transactions WHERE provisional = 1").fetchone()[0]
    assert conn.execute("SELECT date FROM transactions WHERE id = ?", (statement_row,)).fetchone()[0] == "2026-01-09"


def test_three_days_apart_is_confirmed_and_four_is_not(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "x"), ("2026-01-10", -200, "y")],
                                kind="activity", start="2026-01-05", end="2026-01-10"), b"act", "a.csv")
    r = accept_batch(conn, 1, batch([("2026-01-08", -450, "X"), ("2026-01-14", -200, "Y")]), b"st", "s.txt")
    assert r.confirmed == 1
    # the 14th is outside the export's period, so it is not reported (statement rule 5)
    assert r.differences == ["only in the earlier export: 2026-01-10"]


def test_statement_rows_with_no_provisional_in_the_period_report_nothing(conn):
    r = accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st", "s.txt")
    assert (r.confirmed, r.differences) == (0, [])


def test_other_statements_and_superseded_rows_are_untouched(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "x")], kind="activity",
                                start="2026-01-05", end="2026-01-05"), b"act", "a.csv")
    accept_batch(conn, 1, batch([("2026-01-05", -450, "A")], start="2026-01-01", end="2026-01-31"), b"st1", "s1.txt")
    first = conn.execute("SELECT superseded_by FROM transactions WHERE provisional = 1").fetchone()[0]
    r = accept_batch(conn, 1, batch([("2026-01-30", -300, "B")], start="2026-01-29", end="2026-02-28"),
                     b"st2", "s2.txt")
    assert (r.confirmed, r.differences) == (0, [])
    assert conn.execute("SELECT superseded_by FROM transactions WHERE provisional = 1").fetchone()[0] == first
    assert count(conn, "transactions") == 3
    assert live(conn) == [("2026-01-05", -450, 0), ("2026-01-30", -300, 0)]


def test_a_failure_in_the_supersede_step_rolls_the_statement_back(conn, monkeypatch):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "x")], kind="activity",
                                start="2026-01-05", end="2026-01-05"), b"act", "a.csv")
    real = tracker.store._supersede_provisional

    def then_fail(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("disk gone")
    monkeypatch.setattr(tracker.store, "_supersede_provisional", then_fail)
    with pytest.raises(RuntimeError):
        accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st", "s.txt")
    assert count(conn, "batches") == 1 and count(conn, "transactions") == 1
    assert live(conn) == [("2026-01-05", -450, 1)]
    assert not conn.in_transaction


def test_same_statement_in_another_file_form_is_a_duplicate(conn):
    rows = [("2026-01-05", -450, "A"), ("2026-01-06", -450, "B")]
    first = accept_batch(conn, 1, batch(rows), b"pdf-bytes", "s.pdf")
    r = accept_batch(conn, 1, batch(rows), b"text-bytes", "s.txt")
    assert r.status == "duplicate" and r.batch_id == first.batch_id
    assert count(conn, "batches") == 1 and count(conn, "transactions") == 2


def test_identical_rows_on_a_day_split_across_two_statements_are_both_kept(conn):
    accept_batch(conn, 1, batch([("2026-01-31", -330, "TRANSIT")], start="2026-01-01", end="2026-01-31"),
                 b"a", "a.txt")
    r = accept_batch(conn, 1, batch([("2026-01-31", -330, "TRANSIT"), ("2026-02-10", -100, "CAFE")],
                                    start="2026-01-31", end="2026-02-28"), b"b", "b.txt")
    assert (r.status, r.added, r.already_held) == ("accepted", 2, 0)
    assert [x for x in live(conn) if x[0] == "2026-01-31"] == [("2026-01-31", -330, 0)] * 2


def test_same_period_with_different_transactions_is_not_a_duplicate(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"a", "a.txt")
    r = accept_batch(conn, 1, batch([("2026-01-05", -460, "A")]), b"b", "b.txt")
    # not a duplicate, but a second statement for the period is refused (ruling D)
    assert (r.status, r.added, r.message) == (
        "refused", 0, "this account already has a different statement for this period")
    assert count(conn, "batches") == 1 and count(conn, "transactions") == 1


# --- reconciliation at the statement edge (Plan 2, Task 3) ---

def test_a_charge_that_posts_on_the_next_statement_is_neither_lost_nor_doubled(conn):
    accept_batch(conn, 1, batch([("2026-01-10", -500, "a"), ("2026-01-30", -900, "late")],
                                kind="activity", start="2026-01-10", end="2026-01-30"), b"act", "a.csv")
    accept_batch(conn, 1, batch([("2026-01-10", -500, "A")]), b"st1", "s1.txt")
    assert ("2026-01-30", -900, 1) in live(conn)          # kept: within the last days of the period
    # a card statement's period starts at its earliest charge, so the next one reaches back to the 30th
    r = accept_batch(conn, 1, batch([("2026-01-30", -900, "LATE")], opening=-500,
                                    start="2026-01-30", end="2026-02-28"), b"st2", "s2.txt")
    assert r.confirmed == 1
    assert live(conn) == [("2026-01-10", -500, 0), ("2026-01-30", -900, 0)]


def test_an_export_row_just_past_the_period_end_matches_the_statements_copy(conn):
    accept_batch(conn, 1, batch([("2026-01-31", -900, "LATE")]), b"st", "s.txt")
    r = accept_batch(conn, 1, batch([("2026-02-01", -900, "late")], kind="activity",
                                    start="2026-01-30", end="2026-02-01"), b"act", "a.csv")
    assert (r.added, r.already_held) == (0, 1)
    assert live(conn) == [("2026-01-31", -900, 0)]


def test_a_repeated_charge_after_the_period_is_not_mistaken_for_the_statements_copy(conn):
    accept_batch(conn, 1, batch([("2026-01-30", -450, "coffee")], kind="activity",
                                start="2026-01-30", end="2026-01-30"), b"a1", "a1.csv")
    accept_batch(conn, 1, batch([("2026-01-30", -450, "COFFEE")]), b"st", "s.txt")
    r = accept_batch(conn, 1, batch([("2026-02-01", -450, "coffee")], kind="activity",
                                    start="2026-02-01", end="2026-02-01"), b"a2", "a2.csv")
    assert r.added == 1
    assert live(conn) == [("2026-01-30", -450, 0), ("2026-02-01", -450, 1)]


def test_an_export_row_deep_inside_a_held_statement_that_lacks_it_is_reported_not_counted(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st", "s.txt")
    r = accept_batch(conn, 1, batch([("2026-01-05", -450, "a"), ("2026-01-12", -777, "ghost")],
                                    kind="activity", start="2026-01-05", end="2026-01-12"), b"act", "a.csv")
    assert (r.added, r.already_held, r.differences) == (0, 2, ["only in this export: 2026-01-12"])
    assert live(conn) == [("2026-01-05", -450, 0)]


def test_an_override_on_a_provisional_row_moves_to_the_statement_row(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "shop web")], kind="activity",
                                start="2026-01-05", end="2026-01-05"), b"act", "a.csv")
    old = conn.execute("SELECT id FROM transactions").fetchone()[0]
    conn.execute("INSERT INTO overrides (transaction_id, user_id, category, set_at) VALUES (?, 1, 'Coffee', 'now')", (old,))
    conn.commit()
    accept_batch(conn, 1, batch([("2026-01-06", -450, "SHOP 123")]), b"st", "s.txt")
    new = conn.execute("SELECT id FROM transactions WHERE superseded_by IS NULL").fetchone()[0]
    assert [tuple(r) for r in conn.execute("SELECT transaction_id, category FROM overrides")] == [(new, "Coffee")]


def test_statement_only_rows_are_reported_only_where_an_export_covered_the_date(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "a")], kind="activity",
                                start="2026-01-05", end="2026-01-09"), b"act", "a.csv")
    r = accept_batch(conn, 1, batch([("2026-01-05", -450, "A"), ("2026-01-07", -100, "B"), ("2026-01-25", -300, "C")]),
                     b"st", "s.txt")
    assert r.differences == ["only in the statement: 2026-01-07"]


def test_a_second_different_statement_for_the_same_period_is_refused(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st1", "s1.txt")
    before = (live(conn), count(conn, "batches"), count(conn, "transactions"))
    r = accept_batch(conn, 1, batch([("2026-01-05", -450, "A"), ("2026-01-06", -50, "B")]), b"st2", "s2.txt")
    assert r == tracker.store.AcceptResult(
        "refused", None, 0, 0, "this account already has a different statement for this period",
        code="statement_exists")
    assert (live(conn), count(conn, "batches"), count(conn, "transactions")) == before
    assert not conn.in_transaction


# --- edge cases the rules imply ---

def _row(conn, date):
    return tuple(conn.execute(
        "SELECT superseded_by, matched_id FROM transactions WHERE provisional = 1 AND date = ?", (date,)).fetchone())


def test_two_identical_charges_on_adjacent_days_across_the_edge_pair_by_exact_date(conn):
    # the export lists the later day first; the exact-date pair must still win
    st = accept_batch(conn, 1, batch([("2026-01-31", -300, "TRANSIT")]), b"st", "s.txt")
    r = accept_batch(conn, 1, batch([("2026-02-01", -300, "transit web"), ("2026-01-31", -300, "transit web")],
                                    kind="activity", start="2026-01-31", end="2026-02-01"), b"act", "a.csv")
    assert (r.added, r.already_held, r.differences) == (1, 1, [])
    assert live(conn) == [("2026-01-31", -300, 0), ("2026-02-01", -300, 1)]
    statement_row = conn.execute("SELECT id FROM transactions WHERE provisional = 0").fetchone()[0]
    assert _row(conn, "2026-01-31") == (st.batch_id, statement_row)


def test_two_identical_charges_across_the_edge_when_the_statement_arrives_second(conn):
    accept_batch(conn, 1, batch([("2026-01-30", -300, "transit web"), ("2026-01-31", -300, "transit web")],
                                kind="activity", start="2026-01-30", end="2026-01-31"), b"act", "a.csv")
    # the statement holds only the 31st; the 30th's charge lands on the next one
    r = accept_batch(conn, 1, batch([("2026-01-31", -300, "TRANSIT")], start="2026-01-31", end="2026-02-27"),
                     b"st", "s.txt")
    assert (r.confirmed, r.differences) == (1, [])
    assert live(conn) == [("2026-01-30", -300, 1), ("2026-01-31", -300, 0)]


def test_a_leftover_row_the_next_statement_lacks_is_superseded_and_reported(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "a"), ("2026-01-30", -900, "late")],
                                kind="activity", start="2026-01-05", end="2026-01-30"), b"act", "a.csv")
    accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st1", "s1.txt")
    assert ("2026-01-30", -900, 1) in live(conn)
    r = accept_batch(conn, 1, batch([("2026-02-10", -100, "B")], opening=-450, start="2026-02-01", end="2026-02-28"),
                     b"st2", "s2.txt")
    assert (r.confirmed, r.differences) == (0, ["only in the earlier export: 2026-01-30"])
    assert live(conn) == [("2026-01-05", -450, 0), ("2026-02-10", -100, 0)]
    assert _row(conn, "2026-01-30") == (r.batch_id, None)


def test_a_row_before_the_period_outside_any_held_statement_is_untouched(conn):
    accept_batch(conn, 1, batch([("2026-01-30", -900, "x")], kind="activity",
                                start="2026-01-30", end="2026-01-30"), b"act", "a.csv")
    r = accept_batch(conn, 1, batch([("2026-02-10", -100, "B")], start="2026-02-01", end="2026-02-28"), b"st", "s.txt")
    assert (r.confirmed, r.differences) == (0, [])
    assert ("2026-01-30", -900, 1) in live(conn)


def test_a_row_in_the_last_days_is_not_kept_when_a_later_statement_is_already_held(conn):
    accept_batch(conn, 1, batch([("2026-02-10", -100, "B")], start="2026-02-01", end="2026-02-28"), b"st2", "s2.txt")
    accept_batch(conn, 1, batch([("2026-01-30", -900, "x")], kind="activity",
                                start="2026-01-30", end="2026-01-30"), b"act", "a.csv")
    r = accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st1", "s1.txt")
    assert r.differences == ["only in the earlier export: 2026-01-30"]
    assert ("2026-01-30", -900, 1) not in live(conn)


def test_an_export_row_in_the_last_days_of_a_held_statement_stays_live(conn):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st", "s.txt")
    r = accept_batch(conn, 1, batch([("2026-01-30", -777, "late")], kind="activity",
                                    start="2026-01-30", end="2026-01-30"), b"act", "a.csv")
    assert (r.added, r.already_held, r.differences) == (1, 0, [])
    assert ("2026-01-30", -777, 1) in live(conn)


def test_reuploading_an_activity_export_after_its_statement_adds_nothing(conn):
    rows = [("2026-01-05", -450, "a"), ("2026-01-12", -777, "ghost"), ("2026-01-30", -900, "late")]
    accept_batch(conn, 1, batch(rows, kind="activity", start="2026-01-05", end="2026-01-30"), b"act", "a.csv")
    accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st", "s.txt")
    before = (live(conn), count(conn, "transactions"))
    r = accept_batch(conn, 1, batch(rows, kind="activity", start="2026-01-05", end="2026-01-30"),
                     b"act re-saved", "a2.csv")
    assert (r.status, r.added, r.already_held, r.differences) == ("accepted", 0, 3, [])
    assert (live(conn), count(conn, "transactions")) == before


def test_an_export_row_matching_a_claimed_statement_row_takes_the_next_unclaimed_one(conn):
    accept_batch(conn, 1, batch([("2026-01-10", -450, "x")], kind="activity",
                                start="2026-01-10", end="2026-01-10"), b"a1", "a1.csv")
    st = accept_batch(conn, 1, batch([("2026-01-10", -450, "X"), ("2026-01-12", -450, "Y")]), b"st", "s.txt")
    r = accept_batch(conn, 1, batch([("2026-01-11", -450, "y web")], kind="activity",
                                    start="2026-01-11", end="2026-01-11"), b"a2", "a2.csv")
    assert (r.added, r.already_held, r.differences) == (0, 1, [])
    y = conn.execute("SELECT id FROM transactions WHERE provisional = 0 AND date = '2026-01-12'").fetchone()[0]
    assert _row(conn, "2026-01-11") == (st.batch_id, y)


def test_an_export_row_in_an_overlap_is_reported_when_the_later_statement_lacks_it(conn):
    # the 30th is in the first statement's last days, but the next statement already covers it without it
    accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st1", "s1.txt")
    st2 = accept_batch(conn, 1, batch([("2026-02-10", -100, "B")], start="2026-01-30", end="2026-02-28"),
                       b"st2", "s2.txt")
    r = accept_batch(conn, 1, batch([("2026-01-30", -777, "x")], kind="activity",
                                    start="2026-01-30", end="2026-01-30"), b"act", "a.csv")
    assert (r.added, r.already_held, r.differences) == (0, 1, ["only in this export: 2026-01-30"])
    assert _row(conn, "2026-01-30") == (st2.batch_id, None)



# --- fix round 1: rulings A-D ---

def test_the_pairing_with_the_most_pairs_wins_and_the_override_follows(conn):  # ruling A
    accept_batch(conn, 1, batch([("2026-01-07", -300, "x"), ("2026-01-10", -300, "x")], kind="activity",
                                start="2026-01-07", end="2026-01-10"), b"act", "a.csv")
    seventh = conn.execute("SELECT id FROM transactions WHERE date = '2026-01-07'").fetchone()[0]
    conn.execute("INSERT INTO overrides (transaction_id, user_id, category, set_at) VALUES (?, 1, 'Fares', 'now')",
                 (seventh,))
    conn.commit()
    r = accept_batch(conn, 1, batch([("2026-01-09", -300, "X"), ("2026-01-12", -300, "X")]), b"st", "s.txt")
    assert (r.confirmed, r.differences) == (2, [])
    assert live(conn) == [("2026-01-09", -300, 0), ("2026-01-12", -300, 0)]
    moved = conn.execute("SELECT t.provisional, t.superseded_by FROM overrides o"
                         " JOIN transactions t ON t.id = o.transaction_id").fetchall()
    assert [tuple(m) for m in moved] == [(0, None)]


def test_the_most_pairs_also_win_at_the_end_of_the_period(conn):  # ruling A
    accept_batch(conn, 1, batch([("2026-01-28", -300, "x"), ("2026-01-31", -300, "x")], kind="activity",
                                start="2026-01-28", end="2026-01-31"), b"act", "a.csv")
    r = accept_batch(conn, 1, batch([("2026-01-26", -300, "X"), ("2026-01-29", -300, "X")]), b"st", "s.txt")
    assert (r.confirmed, r.differences) == (2, [])
    assert sum(a for _, a, _ in live(conn)) == -600


def test_the_kept_live_zone_is_the_end_day_and_the_two_before(conn):  # ruling B
    accept_batch(conn, 1, batch([("2026-01-28", -900, "a"), ("2026-01-29", -900, "b")], kind="activity",
                                start="2026-01-28", end="2026-01-29"), b"act", "a.csv")
    r = accept_batch(conn, 1, batch([("2026-01-05", -450, "A")]), b"st1", "s1.txt")
    assert r.differences == ["only in the earlier export: 2026-01-28"]
    assert [x for x in live(conn) if x[1] == -900] == [("2026-01-29", -900, 1)]
    r = accept_batch(conn, 1, batch([("2026-02-01", -900, "B")], opening=-450, start="2026-02-01",
                                    end="2026-02-28"), b"st2", "s2.txt")
    assert (r.confirmed, r.differences) == (1, [])
    assert [x for x in live(conn) if x[1] == -900] == [("2026-02-01", -900, 0)]


def _three_late_january_charges():
    return batch([("2026-01-29", -450, "T"), ("2026-01-30", -450, "T"), ("2026-01-31", -450, "T")])


def _five_february_charges():
    return batch([(f"2026-02-0{d}", -450, "t") for d in range(1, 6)], kind="activity",
                 start="2026-02-01", end="2026-02-05")


def test_an_export_after_the_period_end_does_not_pair_with_dates_it_does_not_cover(conn):  # ruling C
    accept_batch(conn, 1, _three_late_january_charges(), b"st", "s.txt")
    r = accept_batch(conn, 1, _five_february_charges(), b"act", "a.csv")
    assert (r.added, r.already_held, r.differences) == (5, 0, [])
    assert len(live(conn)) == 8


def test_a_statement_does_not_claim_later_export_rows_whose_export_does_not_cover_it(conn):  # ruling C
    accept_batch(conn, 1, _five_february_charges(), b"act", "a.csv")
    r = accept_batch(conn, 1, _three_late_january_charges(), b"st", "s.txt")
    assert (r.confirmed, r.differences) == (0, [])
    assert live(conn) == [("2026-01-29", -450, 0), ("2026-01-30", -450, 0), ("2026-01-31", -450, 0)] + [
        (f"2026-02-0{d}", -450, 1) for d in range(1, 6)]


def test_an_export_row_just_past_the_period_end_is_live_when_its_export_starts_after_it(conn):  # ruling C
    accept_batch(conn, 1, batch([("2026-01-31", -900, "LATE")]), b"st", "s.txt")
    r = accept_batch(conn, 1, batch([("2026-02-01", -900, "late")], kind="activity",
                                    start="2026-02-01", end="2026-02-01"), b"act", "a.csv")
    assert (r.added, r.already_held, r.differences) == (1, 0, [])


def test_an_override_stays_put_when_the_statement_row_already_has_one(conn, monkeypatch):
    accept_batch(conn, 1, batch([("2026-01-05", -450, "x")], kind="activity",
                                start="2026-01-05", end="2026-01-05"), b"act", "a.csv")
    old = conn.execute("SELECT id FROM transactions").fetchone()[0]
    conn.execute("INSERT INTO overrides (transaction_id, user_id, category, set_at) VALUES (?, 1, 'Old', 'now')", (old,))
    conn.commit()
    real = tracker.store._insert_transactions

    def and_an_override(conn, user_id, account_id, batch_id, b):
        result = real(conn, user_id, account_id, batch_id, b)
        conn.execute("INSERT INTO overrides (transaction_id, user_id, category, set_at)"
                     " SELECT id, 1, 'New', 'now' FROM transactions WHERE batch_id = ?", (batch_id,))
        return result
    monkeypatch.setattr(tracker.store, "_insert_transactions", and_an_override)
    r = accept_batch(conn, 1, batch([("2026-01-05", -450, "X")]), b"st", "s.txt")
    assert r.confirmed == 1
    new = conn.execute("SELECT id FROM transactions WHERE provisional = 0").fetchone()[0]
    assert sorted(tuple(o) for o in conn.execute("SELECT transaction_id, category FROM overrides")) == [
        (old, "Old"), (new, "New")]
