"""The high-level spending groups."""
from tracker.classify import Classified

BLOCKS = ["Food", "Bills", "Subscriptions", "Big purchases", "Buckets", "Everything else"]

CATEGORY_BLOCK = {
    "Groceries": "Food", "Dining & delivery": "Food", "Coffee": "Food", "Bars & alcohol": "Food",
    "Rent": "Bills", "Utilities & internet": "Bills", "Phone": "Bills", "Fees & interest": "Bills",
    "Insurance": "Bills",
    "Subscriptions": "Subscriptions",
}
CATEGORIES = [*CATEGORY_BLOCK, "Transport", "Travel", "Entertainment", "Gifts", "Personal care",
              "Home", "Clothes", "Books & music", "Shopping", "Games",
              "Therapy", "Eye care", "Pharmacy", "Medical & dental",
              "Can't remember"]  # money that left, too long ago to say what for
FOOD_AT_HOME = {"Groceries"}
BIG_PURCHASE_CENTS = 20000  # default until Plan 3 makes it a setting


def block_of(c: Classified) -> str:
    if c.kind == "bucket":
        return "Buckets"
    block = CATEGORY_BLOCK.get(c.category, "Everything else")
    if c.kind == "spending" and c.amount_cents <= -BIG_PURCHASE_CENTS and block == "Everything else":
        return "Big purchases"
    return block
