"""``finerx.view/2`` — the structuredContent the v2 widget draws (contract C2).

Pydantic models of the envelope, one per view. They document the contract and
``tests/test_schemas.py`` validates every UI tool's output against them; the
widget keeps a hand-written mirror in ``widget-src/src/types.ts`` until phase 2
generates it from ``envelope_json_schema()``.

Rules the models encode: every price is ``{amount, observedAt}`` (an ISO date,
never absent next to an amount); a view's ``data`` carries no place finer than
the ZIP area (``origin``) and no store beyond the nearest few; ``card`` is
present in every envelope.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA = "finerx.view/2"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Price(_M):
    amount: float
    observedAt: date


class Codes(_M):
    bin: str
    pcn: str
    group: str


class PriceWithCard(_M):
    amount: float
    family: str | None = None
    name: str | None = None
    observedAt: date


class CardActions(_M):
    smsBody: str
    emailEnabled: bool


class CardView(_M):
    codes: Codes
    priceWithCard: PriceWithCard | None = None
    law: str = Field(min_length=1)
    fine: str = Field(min_length=1)
    chainsCount: int | None = None
    siteUrl: str
    printUrl: str
    actions: CardActions


class DrugRef(_M):
    slug: str
    name: str
    kind: str | None = None


class PackageRef(_M):
    form: str | None = None
    strength: str | None = None
    quantity: int | None = None
    label: str | None = None


class QuantityOption(_M):
    quantity: int
    label: str | None = None
    cardFrom: Price | None = None
    chainsPriced: int | None = None


class ConfigOption(_M):
    form: str | None = None
    strength: str | None = None
    label: str | None = None
    quantities: list[QuantityOption] = []


class Options(_M):
    configs: list[ConfigOption]


class Origin(_M):
    zip: str | None = None
    city: str | None = None
    state: str | None = None
    precision: Literal["zip", "approx", "none"]


class Coverage(_M):
    status: Literal["exact", "other_quantities", "none"]
    quantities: list[int] = []


class PriceRow(_M):
    family: str
    name: str
    price: Price | None = None
    zone: str | None = None
    nearestMiles: float | None = None
    storeCount: int = 0


class PriceWithoutStore(_M):
    family: str
    name: str
    price: Price


class PricesData(_M):
    drug: DrugRef
    package: PackageRef
    options: Options | None = None
    origin: Origin
    rows: list[PriceRow] = Field(max_length=6)
    pricesWithoutStores: list[PriceWithoutStore] = []
    moreCount: int = 0
    needsZip: bool
    coverage: Coverage


class Store(_M):
    family: str
    name: str
    address: str | None = None
    city: str | None = None
    miles: float | None = None
    lat: float | None = None
    lon: float | None = None
    kind: Literal["pharmacy", "store"] = "pharmacy"
    price: Price | None = None


class PharmaciesData(_M):
    drug: DrugRef | None = None
    package: PackageRef | None = None
    origin: Origin
    stores: list[Store] = []
    families: list[str] = []


class CardData(_M):
    drug: DrugRef | None = None
    priceWithCard: PriceWithCard | None = None


class ErrorInfo(_M):
    code: str
    message: str | None = None
    retryAfter: int | None = None
    suggestions: list[dict[str, Any]] | None = None


class Notice(_M):
    """Something to say about a view that IS drawn (unlike ``error``)."""

    code: Literal["zip_invalid"]
    message: str = Field(min_length=1)


class _Envelope(_M):
    schema_: Literal["finerx.view/2"] = Field(alias="schema")
    locale: str
    dir: Literal["ltr", "rtl"]
    card: CardView
    error: ErrorInfo | None = None
    notice: Notice | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PricesEnvelope(_Envelope):
    view: Literal["prices"]
    data: PricesData | None = None


class PharmaciesEnvelope(_Envelope):
    view: Literal["pharmacies"]
    data: PharmaciesData | None = None


class CardEnvelope(_Envelope):
    view: Literal["card"]
    data: CardData | None = None


ENVELOPES: dict[str, type[_Envelope]] = {
    "prices": PricesEnvelope,
    "pharmacies": PharmaciesEnvelope,
    "card": CardEnvelope,
}


def validate(structured: dict[str, Any]) -> _Envelope:
    """Parse one envelope by its ``view`` (raises ``ValidationError``)."""
    model = ENVELOPES[structured["view"]]
    return model.model_validate(structured)


def envelope_json_schema() -> dict[str, Any]:
    """JSON Schema of the three envelopes (phase 2: → ``widget-src/src/types.gen.ts``)."""
    return {name: model.model_json_schema(by_alias=True) for name, model in ENVELOPES.items()}
