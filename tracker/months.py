"""Monthly facts: income, spending by block, saving and the savings rate. All sums are integer cents."""
import sqlite3
from dataclasses import dataclass
from typing import Optional

from tracker.blocks import BLOCKS, CATEGORY_BLOCK, FOOD_AT_HOME, block_of
from tracker.classify import Classified, classify
from tracker.coverage import coverage, month_is_complete


@dataclass
class MonthFacts:
    month: str
    income_cents: int
    spending_cents: int
    saving_cents: int
    savings_rate: float | None
    blocks: dict[str, int]
    categories: dict[str, dict[str, int]]  # group -> category -> cents: what each group is made of
    food_out_cents: int
    food_home_cents: int
    complete: bool
    provisional: bool
    one_off_income: bool
    one_off_spending: bool  # a charge the owner marked one-off, so the month runs low
    uncategorised_count: int
    unconfirmed_income_count: int  # rows counted as income only because no rule matched money in
    reviewed: bool = False
    changed_since_review: bool = False  # reviewed, but today's income or spending differs from then


def month_facts(conn: sqlite3.Connection, user_id: int,
                classified: Optional[list[Classified]] = None) -> list[MonthFacts]:
    """Facts for every month. Pass `classified` (the user's classify() result) to avoid classifying again."""
    by_month: dict[str, list] = {}
    for c in classify(conn, user_id) if classified is None else classified:
        by_month.setdefault(c.date[:7], []).append(c)
    cov = coverage(conn, user_id)
    reviews = {r["month"]: r for r in conn.execute(
        "SELECT month, income_cents, spending_cents FROM month_reviews WHERE user_id = ?", (user_id,))}

    facts = []
    for month in sorted(by_month):
        income = saving = food_out = food_home = 0
        blocks = {name: 0 for name in BLOCKS}
        categories: dict[str, dict[str, int]] = {}
        for c in by_month[month]:
            if c.kind == "income":
                income += c.amount_cents
            elif c.kind == "saving":
                saving -= c.amount_cents
            elif c.kind in ("spending", "bucket", "offset"):
                # spending and bucket money out is negative, an offset is money in: both subtract
                amount = -c.amount_cents
                blocks[block_of(c)] += amount
                within = categories.setdefault(block_of(c), {})
                within[c.category] = within.get(c.category, 0) + amount
                if c.kind != "bucket" and CATEGORY_BLOCK.get(c.category) == "Food":
                    if c.category in FOOD_AT_HOME:
                        food_home += amount
                    else:
                        food_out += amount
        spending = sum(blocks.values())
        seen = reviews.get(month)
        facts.append(MonthFacts(
            month=month, income_cents=income, spending_cents=spending, saving_cents=saving,
            savings_rate=round((income - spending) / income, 4) if income > 0 else None,
            blocks=blocks, categories=categories, food_out_cents=food_out, food_home_cents=food_home,
            complete=month_is_complete(cov, month),
            provisional=any(c.provisional for c in by_month[month]),
            one_off_income=any(c.kind == "income" and c.one_off for c in by_month[month]),
            one_off_spending=any(c.kind == "spending" and c.one_off and c.amount_cents < 0 for c in by_month[month]),
            uncategorised_count=sum(1 for c in by_month[month] if c.category == "Uncategorised"
                                    and c.kind not in ("transfer", "income", "saving")),
            unconfirmed_income_count=sum(1 for c in by_month[month] if c.kind == "income" and c.guessed),
            reviewed=seen is not None,
            changed_since_review=seen is not None and (seen["income_cents"], seen["spending_cents"]) != (income, spending)))
    return facts
