"""The amount a person asked for (#175 stage 2, MCP 2.3).

Two different things travel as "quantity":

* a COUNT of packages or units — "4 pens", "90 tablets", "2 vials", 30;
* what the pharmacy BILLS, in mL or g — "30 g", "10 mL", "2.5 mL", 2.5.

The API takes the first as ``quantity`` and the second as
``billingQuantity`` (it wins when both are given), and never rescales one
into the other: 30 g of a 50 g tube is its own package with its own price, or
it is "not seen" — never 0.6 × the tube's price.

``parse`` reads the ``quantity`` argument of a tool; ``split_text`` pulls a
dose and an amount out of a free-text name ("azelaic acid 15% gel 30 g").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

MAX = 100_000

# Unit words, including the spellings the site's 12 catalogs print (units.ml /
# units.g in apps/web/locales/*.json), so a label read back in Russian,
# Chinese or Arabic is understood too. Never "gr": that is a grain (Armour
# Thyroid 1 gr = 60 mg), a strength.
_ML = r"ml|mls|milliliters?|millilitres?|cc|мл|毫升|مل"
_G = r"g|gm|gms|grams?|grammes?|г|克|غ"
_NUM = r"\d+(?:[.,]\d+)?"

_AMOUNT = re.compile(rf"(?<![\w.,/])({_NUM})\s*({_ML}|{_G})(?![\w/])", re.IGNORECASE)
_ML_ONLY = re.compile(rf"^(?:{_ML})$", re.IGNORECASE)

# A count of packages or units: "x90", "#30", "4 pens", "25 ampules". Not
# "100 units" — that is an insulin strength.
_NOUNS = (
    r"tabs?|tablets?|caps?|capsules?|pills?|count|ct|softgels?|pens?|vials?|tubes?|bottles?|"
    r"amp(?:o|u)les?|amps?|inhalers?|box(?:es)?|packs?|cartons?|syringes?|cartridges?|kits?|"
    r"packets?|pouch(?:es)?|jars?|cans?|patch(?:es)?|suppositor(?:y|ies)|lozenges?|troches?|"
    r"films?|wafers?"
)
_COUNT = re.compile(
    rf"(?:(?<![\w.])[x#×]\s*(\d{{1,5}})(?![\w.])|(?<![\w.,/])(\d{{1,5}})\s*(?:{_NOUNS})\b)",
    re.IGNORECASE,
)

# The dose in a name ("atorvastatin 20 mg", "200 mg/mL", "0.005%"). A bare
# "N mL" is never a dose — it is pulled out as an amount first.
STRENGTH_IN_TEXT = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*(mcg|mg|g|ml|iu|units?|%)"
    r"(?:\s*/\s*((?:\d+(?:\.\d+)?)?\s*(?:ml|l)))?(?![\w])",
    re.IGNORECASE,
)

# Words that make "N g" an amount even without a dose next to it: what comes
# in a tube or a jar is sold by weight ("mupirocin ointment 22 g").
_BY_WEIGHT = re.compile(
    r"\b(?:cream|gel|ointment|lotion|foam|paste|jelly|emulsion|tube|jar|topical|ophthalmic|"
    r"vaginal|rectal|crema|pomada|крем|гель|мазь)\b",
    re.IGNORECASE,
)
# Without a dose or such a word, "N g" below this is the strength of a tablet
# or a vial (valacyclovir 1 g, sucralfate 1 g, ceftriaxone 2 g); tubes and
# jars start at 15 g.
_G_STRENGTH_BELOW = 10.0


@dataclass(frozen=True)
class Pack:
    """What the person asked for: a count, or what is billed (mL / g)."""

    quantity: int | None = None
    billing: float | None = None
    unit: str | None = None  # "ml" | "g" when the person named it
    asked: str | None = None  # as the person put it: "30 g", "4 pens", "2.5"

    @property
    def empty(self) -> bool:
        return self.quantity is None and self.billing is None

    def fields(self) -> dict[str, Any]:
        """The package part of a ``POST /prices/near`` body. ``units:
        billing`` (API 1.6.0) lets the answer be a part of a package — 30 g
        of a 50 g tube — when that is what was asked for or most filled."""
        out: dict[str, Any] = {"quantity": self.quantity, "units": "billing"}
        if self.billing is not None:
            out["billingQuantity"] = self.billing
        return out


def plain(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


def _num(text_: str) -> float | None:
    try:
        return float(text_.replace(",", "."))
    except ValueError:
        return None


def _unit(word: str) -> str:
    return "ml" if _ML_ONLY.match(word) else "g"


def _in_ratio(text_: str, m: re.Match) -> bool:
    """"250 mg / 5 ml", "10 g /15 mL": a concentration, not an amount."""
    return text_[: m.start()].rstrip().endswith("/") or text_[m.end():].lstrip().startswith("/")


def _number(n: float | None, asked: str | None = None) -> Pack:
    if n is None or not (0 < n <= MAX):
        return Pack()
    if float(n).is_integer():
        return Pack(quantity=int(n), asked=asked or plain(n))
    # A fraction is never a count of packages: 2.5 is 2.5 mL (latanoprost).
    return Pack(billing=round(n, 3), asked=asked or plain(n))


def parse(value: Any) -> Pack:
    """The ``quantity`` argument → a ``Pack``. 30 → 30 packages or units; 2.5
    → 2.5 billed (mL / g); "30 g", "10 mL" → billed; "4 pens", "90 tablets",
    "x90" → a count; a label read back ("1 tube · 50 g") → its amount.
    Anything else → nothing (the API then opens the most-filled package)."""
    if value is None or isinstance(value, bool):
        return Pack()
    if isinstance(value, (int, float)):
        return _number(float(value))
    if not isinstance(value, str):
        return Pack()
    s = " ".join(value.split())
    if not s:
        return Pack()
    if re.fullmatch(_NUM, s):
        return _number(_num(s), s)
    for m in _AMOUNT.finditer(s):
        if _in_ratio(s, m):
            continue
        n = _num(m.group(1))
        if n is not None and 0 < n <= MAX:
            return Pack(billing=round(n, 3), unit=_unit(m.group(2)), asked=m.group(0).strip())
        return Pack()
    if m := _COUNT.search(s):
        n = int(m.group(1) or m.group(2))
        return Pack(quantity=n, asked=m.group(0).strip()) if 1 <= n <= MAX else Pack()
    return Pack()


def _cut(text_: str, m: re.Match) -> str:
    return text_[: m.start()] + " " + text_[m.end():]


def split_text(
    drug: str, strength: str | None, form: str | None, pack: Pack
) -> tuple[str, str | None, Pack]:
    """Pull a pack size, an amount and a dose out of a free-text medicine name
    when the explicit arguments are empty; the name keeps what is left.

    "atorvastatin 20 mg 90 tablets" → ("atorvastatin", "20 mg", 90 tablets);
    "azelaic acid 15% gel 30 g" → ("azelaic acid gel", "15 %", 30 g);
    "testosterone cypionate 200 mg/mL 10 mL" → (…, "200 mg/ml", 10 mL);
    "valacyclovir 1 g" → ("valacyclovir", "1 g", nothing) — a dose. Slugs and
    plain names pass through untouched."""
    text_ = drug
    quantity, billing, unit = pack.quantity, pack.billing, pack.unit
    asked = pack.asked
    if quantity is None and billing is None:
        if m := _COUNT.search(text_):
            n = int(m.group(1) or m.group(2))
            if 1 <= n <= MAX:
                quantity, asked = n, m.group(0).strip()
            text_ = _cut(text_, m)
    # An amount in the name is cut out even when one was given explicitly —
    # left in, "30 g" reads as a strength — and counts only when none was.
    for m in _AMOUNT.finditer(text_):
        if _in_ratio(text_, m):
            continue
        n, u = _num(m.group(1)), _unit(m.group(2))
        if n is None or not (0 < n <= MAX):
            continue
        rest = _cut(text_, m)
        if u == "g" and not (
            strength
            or STRENGTH_IN_TEXT.search(rest)
            or _BY_WEIGHT.search(f"{text_} {form or ''}")
            or n >= _G_STRENGTH_BELOW
        ):
            continue  # "valacyclovir 1 g": the dose
        if billing is None and pack.quantity is None:
            billing, unit, asked = round(n, 3), u, m.group(0).strip()
        text_ = rest
        break
    if not strength:
        if m := STRENGTH_IN_TEXT.search(text_):
            strength = f"{m.group(1)} {m.group(2).lower()}"
            if m.group(3):
                strength += "/" + "".join(m.group(3).lower().split())
            text_ = _cut(text_, m)
    cleaned = " ".join(text_.replace(",", " ").split())
    return (cleaned or drug), strength, Pack(quantity=quantity, billing=billing, unit=unit, asked=asked)
