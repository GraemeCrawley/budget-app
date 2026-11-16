"""Small parsing helpers shared by connectors."""
import re
from decimal import Decimal, InvalidOperation

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


class ReadableError(ValueError):
    """A ValueError whose message is a plain reason that holds no file contents.

    The registry passes this message on to the caller; any other ValueError is replaced by a generic one.
    """


class NotTaken(Exception):
    """The file was recognised, but it is for a kind of account the tracker does not take yet
    (an investment account, or one in another currency)."""


def cents(text: str) -> int:
    """Parse a money string such as '1,234.56', '$5', '-12.30', '–12.30' or '(12.30)' to integer cents."""
    s = text.strip().replace("–", "-").replace("−", "-")
    negative = s.startswith("(") and s.endswith(")")
    if s.startswith("-"):
        negative = True
        s = s[1:]
    s = s.strip("()").lstrip("-")
    if s.startswith("$"):
        s = s[1:]
    if not re.fullmatch(r"\d[\d,]*(\.\d+)?", s):
        raise ValueError(f"not a money amount: {text!r}")
    try:
        value = Decimal(s.replace(",", "")) * 100
    except InvalidOperation:
        raise ValueError(f"not a money amount: {text!r}")
    if value != value.to_integral_value():
        raise ValueError(f"not a whole number of cents: {text!r}")
    return -int(value) if negative else int(value)


def decode(data: bytes) -> str:
    """UTF-8 (with or without a byte-order mark), falling back to Latin-1."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")
