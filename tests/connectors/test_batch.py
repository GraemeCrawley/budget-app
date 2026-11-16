from connectors.batch import make_uids

def test_uids_are_stable_and_distinguish_identical_same_day_rows():
    rows = [("2026-01-05", -450, "CORNER SHOP"), ("2026-01-05", -450, "CORNER SHOP"),
            ("2026-01-06", -450, "CORNER SHOP")]
    a = make_uids("acct-x", rows)
    assert len(set(a)) == 3
    assert a == make_uids("acct-x", rows)

def test_uid_ignores_case_and_spacing_but_not_account():
    one = make_uids("acct-x", [("2026-01-05", -450, "Corner  Shop")])
    two = make_uids("acct-x", [("2026-01-05", -450, "CORNER SHOP")])
    other = make_uids("acct-y", [("2026-01-05", -450, "CORNER SHOP")])
    assert one == two and one != other

def test_uid_of_a_day_does_not_depend_on_other_days_in_the_file():
    full = make_uids("a", [("2026-01-05", -100, "X"), ("2026-01-06", -200, "Y"), ("2026-01-06", -200, "Y")])
    part = make_uids("a", [("2026-01-06", -200, "Y"), ("2026-01-06", -200, "Y")])
    assert full[1:] == part
