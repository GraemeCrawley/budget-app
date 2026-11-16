"""take_upload: what a file becomes, and the fixed sentences when it cannot be taken."""
import re
from pathlib import Path

import pytest

from connectors.batch import AccountRef
from tracker.store import ensure_account, open_db
from tracker.uploads import REASONS, take_upload

FX = Path(__file__).parent.parent / "fixtures" / "connectors"
CARD = AccountRef("invented-card", "Invented Card", "card", "")
# a card export that lists charges as positive numbers (and the one refund as negative)
CARD_CSV = (b"Date,Description,Amount\n2026-04-02,INVENTED SHOP,12.50\n2026-04-03,INVENTED CAFE,8.00\n"
            b"2026-04-09,INVENTED REFUND,-5.00\n")
CARD_CSV_2 = b"Date,Description,Amount\n2026-05-02,INVENTED SHOP,3.25\n2026-05-03,INVENTED CAFE,4.75\n"


@pytest.fixture
def conn(tmp_path):
    return open_db(str(tmp_path / "t.db"))


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def hold(conn, ref=CARD):
    with conn:
        ensure_account(conn, 1, ref)


def test_a_self_identifying_statement_is_filed_under_its_own_account(conn):
    out = take_upload(conn, 1, "x.txt", (FX / "cibc_statement.txt").read_bytes())
    assert (out.ok, out.code, out.needs) == (True, "ok", None)
    (b,) = out.batches
    assert (b["account"], b["account_name"], b["kind"], b["status"]) == \
        ("cibc-chequing", "CIBC chequing", "statement", "accepted")
    assert (b["period_start"], b["period_end"], b["added"], b["can_widen"]) == ("2026-02-01", "2026-02-28", 4, False)
    assert conn.execute("SELECT key, kind FROM accounts").fetchall()[0][:] == ("cibc-chequing", "chequing")
    assert count(conn, "batches") == 1


def test_naming_the_wrong_account_stores_nothing_and_says_whose_file_it_is(conn):
    hold(conn)
    out = take_upload(conn, 1, "x.txt", (FX / "cibc_statement.txt").read_bytes(), account_key="invented-card")
    # the account is not held, so the file is named by its connector, never by anything read from the file
    assert (out.ok, out.code, out.needs) == (False, "wrong_account", {"file_is_for": "cibc_chequing"})
    assert out.reason == REASONS["wrong_account"]
    assert count(conn, "batches") == 0 and count(conn, "accounts") == 1
    with conn:  # now the account is held under its own name: that name is given
        conn.execute("UPDATE accounts SET name = 'My Chequing' WHERE key = 'invented-card'")
        ensure_account(conn, 1, AccountRef("cibc-chequing", "Other", "chequing", "CIBC"))
        conn.execute("UPDATE accounts SET name = 'My Chequing' WHERE key = 'cibc-chequing'")
    out = take_upload(conn, 1, "x.txt", (FX / "cibc_statement.txt").read_bytes(), account_key="invented-card")
    assert out.needs == {"file_is_for": "My Chequing"} and count(conn, "batches") == 0


def test_a_generic_export_without_an_account_asks_for_one(conn):
    out = take_upload(conn, 1, "export.csv", CARD_CSV)
    assert (out.ok, out.code, out.needs) == (False, "account_needed", {"choose_account": True})
    assert out.reason == REASONS["account_needed"] and count(conn, "batches") == 0
    # a key that is not held is as good as none: the kind is unknown
    out = take_upload(conn, 1, "export.csv", CARD_CSV, account_key="nowhere")
    assert out.code == "account_needed" and count(conn, "accounts") == 0


def amounts(conn):
    return [r[0] for r in conn.execute("SELECT amount_cents FROM transactions ORDER BY date")]


def test_a_card_export_with_positive_charges_is_stopped_until_signs_are_stated(conn):
    hold(conn)
    out = take_upload(conn, 1, "export.csv", CARD_CSV, account_key="invented-card")
    assert (out.ok, out.code, out.needs) == (False, "signs_look_reversed", {"choose_signs": True})
    assert out.reason == REASONS["signs_look_reversed"]
    assert count(conn, "batches") == 0 and count(conn, "transactions") == 0
    out = take_upload(conn, 1, "export.csv", CARD_CSV, account_key="invented-card", signs="flip")
    assert out.ok and out.batches[0]["added"] == 3
    assert amounts(conn) == [-1250, -800, 500]
    assert conn.execute("SELECT flip_sign FROM accounts").fetchone()[0] == 1
    # the next export of that account needs no signs argument
    out = take_upload(conn, 1, "may.csv", CARD_CSV_2, account_key="invented-card")
    assert out.ok and amounts(conn) == [-1250, -800, 500, -325, -475]


def test_a_flipped_account_keeps_the_same_uids_for_the_same_rows(conn):
    hold(conn)
    take_upload(conn, 1, "a.csv", CARD_CSV, account_key="invented-card", signs="flip")
    # an overlapping export: the two shared rows are already held, only the new one is added
    more = CARD_CSV + b"2026-04-10,INVENTED SHOP,1.00\n"
    out = take_upload(conn, 1, "b.csv", more, account_key="invented-card")
    assert out.ok and (out.batches[0]["added"], out.batches[0]["already_held"]) == (1, 3)


def test_signs_as_is_keeps_the_amounts(conn):
    hold(conn)
    out = take_upload(conn, 1, "export.csv", CARD_CSV, account_key="invented-card", signs="as_is")
    assert out.ok and amounts(conn) == [1250, 800, -500]
    assert conn.execute("SELECT flip_sign FROM accounts").fetchone()[0] == 0


def test_charges_already_negative_need_no_signs_and_a_chequing_account_is_never_asked(conn):
    hold(conn)
    out = take_upload(conn, 1, "e.csv", b"Date,Description,Amount\n2026-04-02,INVENTED SHOP,-12.50\n",
                      account_key="invented-card")
    assert out.ok
    hold(conn, AccountRef("invented-chq", "Invented Chq", "chequing", ""))
    out = take_upload(conn, 1, "e.csv", b"Date,Description,Amount\n2026-04-02,PAY,1200.00\n2026-04-03,PAY,10.00\n",
                      account_key="invented-chq")
    assert out.ok and out.code == "ok"


def test_a_duplicate_upload_is_ok_and_marked_duplicate(conn):
    hold(conn)
    take_upload(conn, 1, "a.csv", CARD_CSV, account_key="invented-card", signs="flip")
    out = take_upload(conn, 1, "a.csv", CARD_CSV, account_key="invented-card")
    assert out.ok and out.batches[0]["status"] == "duplicate" and count(conn, "batches") == 1


def test_a_second_different_statement_for_a_period_has_its_own_sentence(conn):
    text = (FX / "cibc_statement.txt").read_text()
    assert take_upload(conn, 1, "a.txt", text.encode()).ok
    other = text.replace("Feb 14 ", "Feb 15 ")
    out = take_upload(conn, 1, "b.txt", other.encode())
    assert (out.ok, out.code) == (False, "statement_exists") and out.reason == REASONS["statement_exists"]
    assert count(conn, "batches") == 1


def test_a_file_for_a_held_account_of_another_kind_is_a_kind_mismatch(conn):
    hold(conn, AccountRef("cibc-chequing", "CIBC chequing", "card", "CIBC"))
    out = take_upload(conn, 1, "x.txt", (FX / "cibc_statement.txt").read_bytes())
    assert (out.ok, out.code) == (False, "kind_mismatch") and out.reason == REASONS["kind_mismatch"]
    assert count(conn, "batches") == 0


def test_no_reason_sentence_quotes_the_file(conn):
    text = (FX / "cibc_statement.txt").read_text().replace("$2,420.00", "$2,421.00")
    out = take_upload(conn, 1, "secret-name.txt", text.encode())
    assert (out.ok, out.code) == (False, "failed_checks")
    assert out.reason == REASONS["balance_mismatch"]
    assert not re.search(r"\d{3,}", str(out)) and "secret" not in str(out) and "INVENTED" not in str(out)
    assert count(conn, "batches") == 0
    for sentence in REASONS.values():
        assert not re.search(r"\d{3,}", sentence)


def test_every_failure_code_has_a_sentence():
    codes = {"no_format", "unreadable_pdf", "unreadable_row", "no_transactions", "account_needed", "failed_checks",
             "format_version", "batch_kind", "account_kind", "bad_period", "bad_amount", "bad_description",
             "bad_uid", "bad_date", "outside_period", "duplicate_uid", "missing_balance", "balance_mismatch",
             "wrong_account", "signs_look_reversed", "too_large", "kind_mismatch", "statement_exists", "not_taken"}
    assert set(REASONS) == codes
    assert all(isinstance(s, str) and s.endswith(".") for s in REASONS.values())


def test_unreadable_files_get_their_fixed_sentences(conn):
    assert take_upload(conn, 1, "m.bin", b"hello\n").reason == REASONS["no_format"]
    assert take_upload(conn, 1, "m.bin", b"hello\n").code == "no_format"
    out = take_upload(conn, 1, "x.csv", b"%PDF-1.4 not really")
    assert (out.code, out.reason) == ("unreadable_pdf", REASONS["unreadable_pdf"])


def test_a_two_batch_file_with_one_bad_batch_stores_neither(conn, monkeypatch):
    import tracker.uploads as uploads
    from connectors.registry import parse_file
    (first,) = parse_file("x.txt", (FX / "cibc_statement.txt").read_bytes())
    from dataclasses import replace
    second = replace(first, account=AccountRef("second-account", "Second", "chequing", ""))
    monkeypatch.setattr(uploads, "parse_file", lambda *a, **k: [first, second])
    hold(conn, AccountRef("second-account", "Second", "card", ""))  # held as a card: the second batch is refused
    out = take_upload(conn, 1, "x.txt", b"whatever")
    assert (out.ok, out.code) == (False, "kind_mismatch")
    assert count(conn, "batches") == 0 and count(conn, "transactions") == 0
    assert [r[0] for r in conn.execute("SELECT key FROM accounts")] == ["second-account"]  # the first was not left behind
    assert not conn.in_transaction


def test_a_two_batch_file_with_two_good_batches_stores_both(conn, monkeypatch):
    import tracker.uploads as uploads
    from dataclasses import replace
    from connectors.registry import parse_file
    (first,) = parse_file("x.txt", (FX / "cibc_statement.txt").read_bytes())
    second = replace(first, account=AccountRef("second-account", "Second", "chequing", ""))
    monkeypatch.setattr(uploads, "parse_file", lambda *a, **k: [first, second])
    out = take_upload(conn, 1, "x.txt", b"whatever")
    assert out.ok and [b["account"] for b in out.batches] == ["cibc-chequing", "second-account"]
    assert count(conn, "batches") == 2


def test_the_period_can_only_widen_inside_these_bounds(conn):
    from tracker.uploads import PeriodRefused, widen_period
    hold(conn)
    out = take_upload(conn, 1, "a.csv", CARD_CSV, account_key="invented-card", signs="flip")
    bid = out.batches[0]["id"]
    assert (out.batches[0]["period_start"], out.batches[0]["period_end"], out.batches[0]["can_widen"]) == \
        ("2026-04-02", "2026-04-09", True)
    with conn:
        conn.execute("UPDATE batches SET received_at = '2026-05-01T02:30:00+00:00'")  # 10:30 pm on Apr 30 in Toronto
    for start, end in [("2026-04-03", "2026-04-09"), ("2026-04-02", "2026-04-08"),   # shrinks
                       ("2026-04-02", "2026-05-01"),                                  # after the day received
                       ("2026-02-01", "2026-04-09"),                                  # more than 45 days before the rows
                       ("2026-04-02", "2026-05-30"),                                  # more than 45 days after the rows
                       ("2026-04-10", "2026-04-01"), ("nonsense", "2026-04-09")]:
        with pytest.raises(PeriodRefused):
            widen_period(conn, 1, bid, start, end)
    got = widen_period(conn, 1, bid, "2026-03-01", "2026-04-30")  # the evening export covers that day
    assert (got["period_start"], got["period_end"], got["can_widen"]) == ("2026-03-01", "2026-04-30", False)
    assert not conn.in_transaction


def test_another_users_batch_is_not_found(conn):
    from tracker.uploads import widen_period
    hold(conn)
    bid = take_upload(conn, 1, "a.csv", CARD_CSV, account_key="invented-card", signs="flip").batches[0]["id"]
    with pytest.raises(LookupError):
        widen_period(conn, 2, bid, "2026-04-01", "2026-04-30")
    with pytest.raises(LookupError):
        widen_period(conn, 1, bid + 100, "2026-04-01", "2026-04-30")


def flip_of(conn, key="invented-card"):
    return conn.execute("SELECT flip_sign FROM accounts WHERE key = ?", (key,)).fetchone()[0]


def test_a_duplicate_upload_with_flip_does_not_change_the_setting(conn):
    hold(conn)
    assert take_upload(conn, 1, "a.csv", CARD_CSV, account_key="invented-card", signs="as_is").ok
    out = take_upload(conn, 1, "a.csv", CARD_CSV, account_key="invented-card", signs="flip")
    assert out.ok and out.batches[0]["status"] == "duplicate"
    assert flip_of(conn) == 0 and amounts(conn) == [1250, 800, -500]


def test_a_non_card_account_is_never_flipped_even_with_the_column_set(conn):
    hold(conn, AccountRef("invented-chq", "Invented Chq", "chequing", ""))
    with conn:
        conn.execute("UPDATE accounts SET flip_sign = 1")
    out = take_upload(conn, 1, "e.csv", b"Date,Description,Amount\n2026-04-02,PAY,1200.00\n2026-04-03,SHOP,-10.00\n",
                      account_key="invented-chq")
    assert out.ok and amounts(conn) == [120000, -1000]
    assert take_upload(conn, 1, "f.csv", CARD_CSV, account_key="invented-chq", signs="flip").ok
    assert flip_of(conn, "invented-chq") == 1  # untouched, and the rows were stored as given
    assert 1250 in amounts(conn)


def test_as_is_on_a_flipped_card_account_turns_flipping_off_and_stores_as_given(conn):
    hold(conn)
    take_upload(conn, 1, "a.csv", CARD_CSV, account_key="invented-card", signs="flip")
    assert flip_of(conn) == 1
    out = take_upload(conn, 1, "may.csv", CARD_CSV_2, account_key="invented-card", signs="as_is")
    assert out.ok and flip_of(conn) == 0
    assert amounts(conn)[-2:] == [325, 475]
    # a duplicate with as_is does not turn it back off or on
    with conn:
        conn.execute("UPDATE accounts SET flip_sign = 1")
    dup = take_upload(conn, 1, "may.csv", CARD_CSV_2, account_key="invented-card", signs="as_is")
    assert dup.batches[0]["status"] == "duplicate" and flip_of(conn) == 1


def test_a_refusal_from_accept_batch_is_mapped_by_its_code_not_its_text(conn, monkeypatch):
    import tracker.uploads as uploads
    from tracker.store import AcceptResult
    monkeypatch.setattr(uploads, "accept_batch", lambda *a, **k: AcceptResult("refused", None, 0, 0, "Invented 99999", code="statement_exists"))
    out = take_upload(conn, 1, "x.txt", (FX / "cibc_statement.txt").read_bytes())
    assert out.code == "statement_exists" and count(conn, "batches") == 0
    monkeypatch.setattr(uploads, "accept_batch", lambda *a, **k: AcceptResult("refused", None, 0, 0, "Invented 99999", code="failed_checks"))
    out = take_upload(conn, 1, "x.txt", (FX / "cibc_statement.txt").read_bytes())
    assert (out.code, out.reason) == ("failed_checks", REASONS["failed_checks"])


def test_a_wrong_account_file_for_an_account_not_held_is_named_by_its_connector(conn, monkeypatch):
    import tracker.uploads
    from dataclasses import replace
    real = tracker.uploads.parse_file

    def named_from_the_file(*args):
        return [replace(b, account=replace(b.account, name="WORDS FROM THE FILE")) for b in real(*args)]
    monkeypatch.setattr(tracker.uploads, "parse_file", named_from_the_file)
    hold(conn)
    out = take_upload(conn, 1, "x.txt", (FX / "cibc_statement.txt").read_bytes(), account_key="invented-card")
    assert out.needs == {"file_is_for": "cibc_chequing"}


def test_a_batch_that_stored_no_rows_widens_only_45_days_beyond_its_own_period(conn):
    from tracker.uploads import PeriodRefused, widen_period
    hold(conn)
    take_upload(conn, 1, "a.csv", CARD_CSV, account_key="invented-card", signs="flip")
    again = take_upload(conn, 1, "b.csv", CARD_CSV + b"\n", account_key="invented-card")  # every row already held
    (b,) = again.batches
    assert (b["status"], b["added"], b["already_held"]) == ("accepted", 0, 3)
    assert count(conn, "transactions") == 3
    with conn:
        conn.execute("UPDATE batches SET received_at = '2026-12-01T12:00:00+00:00'")
    for start, end in [("2026-02-15", "2026-04-09"), ("2026-04-02", "2026-05-25")]:
        with pytest.raises(PeriodRefused, match="forty-five"):
            widen_period(conn, 1, b["id"], start, end)
    got = widen_period(conn, 1, b["id"], "2026-03-01", "2026-05-20")
    assert (got["period_start"], got["period_end"]) == ("2026-03-01", "2026-05-20")


WS_NAME = "Rainy_Day-monthly-statement-transactions-XX0000000CAD-2026-02-01.csv"


def test_a_cash_statement_for_an_account_held_as_chequing_keeps_the_held_kind(conn):
    hold(conn, AccountRef("wealthsimple-rainy-day", "Rainy Day", "chequing", "Wealthsimple"))
    out = take_upload(conn, 1, WS_NAME, (FX / "ws_cash_monthly.csv").read_bytes())
    assert (out.ok, out.code) == (True, "ok")
    assert conn.execute("SELECT kind FROM accounts").fetchone()[0] == "chequing"


def test_an_investment_statement_is_refused_in_its_own_words(conn):
    data = (b'"date","transaction","description","amount","balance","currency"\n'
            b'"2026-01-05","BUY","Invented Fund: Bought 1.0000 shares","-10.00","90.00","CAD"\n')
    out = take_upload(conn, 1, WS_NAME, data)
    assert (out.ok, out.code) == (False, "not_taken") and out.reason == REASONS["not_taken"]
    assert count(conn, "accounts") == 0
