"""Normalise a bank description to a short merchant key, so one correction covers every charge from a merchant."""
import re

GENERIC = r"\bRETAIL PURCHASE\b|\bPREAUTHORIZED DEBIT\b|\bE-TRANSFER\b|\bINTERNET TRANSFER\b|\bPOINT OF SALE\b"


# Where a charge was made, as banks append it to a card description. Only names that are rarely anything else:
# "LONDON", "VICTORIA", "YORK", "RICHMOND", "HAMILTON" and the like are left out on purpose.
PLACES = {tuple(p.split()) for p in (
    "TORONTO", "ETOBICOKE", "SCARBOROUGH", "NORTH YORK", "EAST YORK", "MISSISSAUGA", "BRAMPTON", "VAUGHAN",
    "MARKHAM", "RICHMOND HILL", "OAKVILLE", "BURLINGTON", "ST CATHARINES", "ST. CATHARINES", "NIAGARA FALLS",
    "OTTAWA", "KITCHENER", "GUELPH", "BARRIE", "MONTREAL", "LAVAL", "VANCOUVER", "BURNABY", "CALGARY", "EDMONTON",
    "WINNIPEG", "HALIFAX", "SASKATOON", "SAN FRANCISCO", "NEW YORK", "SEATTLE", "CHICAGO", "BOSTON",
)}
PROVINCES = {"ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE"}
# A number that opens the description and is the name itself: a street number ("1100 KING ST"), or a numbered
# company ("1234567 ONTARIO LTD"). Any other long number is a reference and is removed.
LEAD_NUMBER = re.compile(r"\s*(\d{4,5}(?=\s+[A-Z])|\d{6,9}(?=\s+(?:ONTARIO|CANADA|QUEBEC|ALBERTA|MANITOBA|B\.?C\.?)\b))\s+")


def _key_v1(description: str) -> str:
    """The first key: references removed, cut at 20 characters, stray punctuation left in."""
    u = re.sub(GENERIC, " ", description.upper())
    u = re.sub(r"\*\w*\d\w*", " ", u)  # a starred reference (it has a digit); a starred name is kept
    u = u.replace("*", " "); u = re.sub(r"#\w+", " ", u); u = re.sub(r"\[\d+\]", "", u)
    u = re.sub(r"\b[A-Z0-9]*\d{4,}[A-Z0-9]*\b", " ", u)   # reference ids, including alphanumeric ones
    return re.sub(r"\s+", " ", u).strip()[:20].strip()


def _key_v2(description: str) -> str:
    """The second key: as the first, without the lone punctuation a removed reference leaves behind."""
    u = re.sub(GENERIC, " ", description.upper())
    u = re.sub(r"\*\w*\d\w*", " ", u)
    u = u.replace("*", " "); u = re.sub(r"#\w+", " ", u); u = re.sub(r"\[\d+\]", "", u)
    u = re.sub(r"\b[A-Z0-9]*\d{4,}[A-Z0-9]*\b", " ", u)
    u = " ".join(t for t in u.split() if any(ch.isalnum() for ch in t))
    u = re.sub(r"^[^\w]+|[^\w]+$", "", u)
    return re.sub(r"^[^\w]+|[^\w]+$", "", u[:20])


# Every key algorithm this ledger has used before the current one. Kept ONLY so `python -m tracker.cli rekey` can
# find stored owner rules keyed an old way. Do not use them for anything else, and do not change them.
PREVIOUS_KEYS = (_key_v1, _key_v2)


def _without_place(tokens: list[str], floor: int) -> list[str]:
    """Drop the place a bank appends ("... TORONTO", "... TORONTO ON"), however often it repeats, while more than
    `floor` tokens stay. "CITY OF TORONTO" keeps its own name."""
    while True:
        end = len(tokens) - 1 if len(tokens) > 1 and tokens[-1] in PROVINCES else len(tokens)
        for size in (2, 1):
            start = end - size
            if start >= max(floor, 1) and tuple(tokens[start:end]) in PLACES and tokens[start - 1] != "OF":
                tokens = tokens[:start]
                break
        else:
            return tokens


def merchant_key(description: str) -> str:
    u = description.upper()
    lead = LEAD_NUMBER.match(u)
    if lead:
        u = u[lead.end():]
    u = re.sub(GENERIC, " ", u)
    u = re.sub(r"\*\w*\d\w*", " ", u)  # a starred reference (it has a digit); a starred name is kept
    u = u.replace("*", " "); u = re.sub(r"#\w+", " ", u); u = re.sub(r"\[\d+\]", "", u)
    u = re.sub(r"\b[A-Z0-9]*\d{4,}[A-Z0-9]*\b", " ", u)   # reference ids, including alphanumeric ones
    # A token with no letter or digit (a lone '#', '*', '-', '/', '&') is what a removed reference leaves behind.
    # Accepted side effect: "A & W" becomes "A W".
    tokens = [t for t in u.split() if any(ch.isalnum() for ch in t)]
    if lead and tokens:
        tokens.insert(0, lead.group(1))
    tokens = _without_place(tokens, 1 + bool(lead and tokens))
    u = re.sub(r"^[^\w]+|[^\w]+$", "", " ".join(tokens))
    if len(u) > 20:  # cut at 20, on a word boundary when there is one: half a word reads as a typo
        cut = u[:20]
        u = cut if u[20] == " " or " " not in cut else cut[:cut.rindex(" ")]
    return re.sub(r"^[^\w]+|[^\w]+$", "", u)
