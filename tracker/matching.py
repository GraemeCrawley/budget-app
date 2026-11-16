"""Whether a classification rule matches a row. Imports nothing from the tracker, so the store and classify can
both use it without an import cycle (tracker.rules imports tracker.store)."""


def sign_of(amount_cents: int) -> int:
    return 1 if amount_cents > 0 else -1 if amount_cents < 0 else 0


def rule_matches(rule, pattern, row, key: str) -> bool:
    """`rule` has a Rule's attributes, `pattern` is its compiled pattern, `row` maps account_key, amount_cents,
    date and description, and `key` is the row's merchant key."""
    if rule.merchant_key is not None and rule.merchant_key != key:
        return False
    amount = row["amount_cents"]
    if rule.account_key is not None and rule.account_key != row["account_key"]:
        return False
    if rule.sign is not None and rule.sign != sign_of(amount):
        return False
    if rule.min_cents is not None and abs(amount) < rule.min_cents:
        return False
    if rule.max_cents is not None and abs(amount) > rule.max_cents:
        return False
    if rule.date_from is not None and row["date"] < rule.date_from:
        return False
    if rule.date_to is not None and row["date"] > rule.date_to:
        return False
    return pattern.search(row["description"]) is not None
