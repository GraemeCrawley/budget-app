from tracker.blocks import block_of
from tracker.classify import Classified


def c(amount, category, kind="spending"):
    return Classified(1, "chq", "chequing", "2026-01-05", amount, "X", False, kind, category, False, "t",
                      False)


def test_big_purchase_threshold_is_inclusive_at_20000():
    assert block_of(c(-19999, "Travel")) == "Everything else"
    assert block_of(c(-20000, "Travel")) == "Big purchases"


def test_big_amounts_in_food_or_bills_keep_their_block():
    assert block_of(c(-50000, "Groceries")) == "Food"
    assert block_of(c(-250000, "Rent")) == "Bills"


def test_a_large_refund_is_not_a_big_purchase():
    assert block_of(c(25000, "Travel")) == "Everything else"


def test_bucket_kind_is_buckets_whatever_the_category():
    assert block_of(c(-5000, "Groceries", "bucket")) == "Buckets"
    assert block_of(c(-50000, "Travel", "bucket")) == "Buckets"


def test_unknown_category_is_everything_else():
    assert block_of(c(-100, "Nonsense")) == "Everything else"


def test_the_picker_categories_are_every_block_category_plus_the_extras():
    from tracker.blocks import CATEGORIES, CATEGORY_BLOCK
    assert set(CATEGORIES) == set(CATEGORY_BLOCK) | {
        "Transport", "Travel", "Entertainment", "Gifts", "Personal care", "Home", "Clothes", "Books & music", "Shopping",
        "Games", "Therapy", "Eye care", "Pharmacy", "Medical & dental", "Can't remember"}
    assert not {"Shopping/home", "Health", "Other", "Therapy/health"} & set(CATEGORIES)
    assert not [c for c in CATEGORIES if "/" in c]  # one thing per category, never "this/that"
    assert len(CATEGORIES) == len(set(CATEGORIES))
