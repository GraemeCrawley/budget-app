"""The common format every bank-file connector emits: a statement batch."""
import hashlib
from dataclasses import dataclass
from typing import Optional

FORMAT_VERSION = 1


@dataclass(frozen=True)
class AccountRef:
    key: str  # stable slug, e.g. "cibc-chequing"
    name: str
    kind: str  # "chequing" | "card" | "savings" | "investment"
    institution: str


@dataclass(frozen=True)
class Txn:
    date: str  # ISO YYYY-MM-DD
    amount_cents: int  # signed; negative is money out of the account
    description: str
    uid: str


@dataclass(frozen=True)
class StatementBatch:
    format_version: int
    connector: str
    connector_version: int
    account: AccountRef
    kind: str  # "statement" | "activity"
    period_start: str
    period_end: str
    opening_cents: Optional[int]
    closing_cents: Optional[int]
    transactions: tuple[Txn, ...]


def _normalise(description: str) -> str:
    return " ".join(description.upper().split())


def make_uids(account_key: str, rows: list[tuple[str, int, str]]) -> list[str]:
    """One stable uid per (date, amount_cents, description) row, in order.

    Identical rows are told apart by an ordinal counted within the given list.
    """
    seen: dict[tuple[str, int, str], int] = {}
    uids = []
    for date, amount_cents, description in rows:
        key = (date, amount_cents, _normalise(description))
        seen[key] = seen.get(key, 0) + 1
        raw = f"{account_key}|{key[0]}|{key[1]}|{key[2]}|{seen[key]}"
        uids.append(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20])
    return uids
