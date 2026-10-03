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
    """Where the answer is for — never finer than a ZIP area / a city, and no
    coordinates (a typed address comes back as its ZIP, city and state, with
    ``precision: "address"``; phase 2)."""

    zip: str | None = None
    city: str | None = None
    state: str | None = None
    precision: Literal["zip", "approx", "address", "none"]


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


class CompareTo(_M):
    """An amount the person named (a copay, what they pay now, a target) and how
    many of the chains with a card price were seen below it."""

    amount: float
    below: int
    of: int
    observedFrom: date
    observedTo: date


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
    compareTo: CompareTo | None = None


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


class QrCode(_M):
    """The card page as a QR: square rows of "0"/"1" the widget draws itself."""

    url: str = Field(pattern=r"^https://\S+$")
    rows: list[str] = Field(min_length=21, max_length=61)


class CardData(_M):
    drug: DrugRef | None = None
    priceWithCard: PriceWithCard | None = None
    qr: QrCode | None = None


# --- phase 2 (MCP 2.1, contract C2'): search / equivalent / rx ------------------


class Suggestion(_M):
    """One typeahead hit (API ``/drugs/suggest`` results): ``cardFrom`` = the
    lowest family price of the drug's default package, with its date."""

    slug: str
    name: str
    kind: str | None = None
    matchedAlias: str | None = None
    cardFrom: Price | None = None


class ForeignBrandHit(_M):
    """A brand from another country the text matched. ``usSlug``/``usName`` only
    for ``same_inn`` (the same active ingredient is sold here): an
    ``rx_alternative`` is a different medicine and is never offered as "the US
    product" of the brand."""

    brand: str
    brandSlug: str | None = None
    countries: list[str] = []
    usClass: Literal["same_inn", "rx_alternative", "no_equivalent"] | None = None
    usSlug: str | None = None
    usName: str | None = None


class SuggestResult(_M):
    """``ui_suggest`` structuredContent (not an envelope: the search view calls
    it as you type and keeps its own frame)."""

    results: list[Suggestion] = Field(default=[], max_length=8)
    foreignBrands: list[ForeignBrandHit] = Field(default=[], max_length=8)
    card: CardView


class SearchData(_M):
    query: str | None = None
    suggestions: list[Suggestion] = Field(default=[], max_length=8)
    foreignBrands: list[ForeignBrandHit] = Field(default=[], max_length=8)
    popular: list[DrugRef] = Field(default=[], max_length=8)
    origin: Origin | None = None


class UsProduct(_M):
    slug: str
    name: str
    kind: str | None = None
    cardFrom: Price | None = None


class EquivalentData(_M):
    brand: str | None = None
    countries: list[str] = []
    inn: str | None = None
    usClass: Literal["same_inn", "rx_alternative", "no_equivalent"] | None = None
    # The API's reviewed sentence, verbatim — never composed here.
    guidance: str | None = None
    # The API's "same active ingredient is not the same product" sentence.
    disclaimer: str | None = None
    # Only for same_inn: naming a US product for the other classes would be
    # naming a substitute.
    us: UsProduct | None = None


class RxLink(_M):
    label: str = Field(min_length=1)
    url: str = Field(pattern=r"^https://\S+$")


class RxSection(_M):
    title: str
    body: str
    links: list[RxLink] = []


class RxData(_M):
    drug: DrugRef | None = None
    restricted: bool
    # The restricted sentence (only prices and the card; see a clinician).
    note: str | None = None
    sections: list[RxSection] = Field(default=[], max_length=3)
    cardFrom: Price | None = None
    # The reader's language (labels, numbers, dates). The envelope's top-level
    # ``locale`` keeps get_prescription_options' 2.0 meaning: the API's content
    # language (en/es).
    readerLocale: str | None = None


# --- MCP 2.2: transfer — moving a prescription to another pharmacy ---------------


class ChainRef(_M):
    family: str
    name: str


class TransferData(_M):
    chain: ChainRef | None = None
    drug: DrugRef | None = None
    package: PackageRef | None = None
    # The chain's card price for the package, when a drug was named.
    price: Price | None = None
    # Our own fixed sentences, in the reader's language where we have them.
    steps: list[str] = Field(default=[], max_length=4)
    notes: list[str] = Field(default=[], max_length=3)
    stores: list[Store] = Field(default=[], max_length=3)
    origin: Origin
    restricted: bool
    note: str | None = None


# --- MCP 2.2: equivalents — several medicines from another country ---------------


class EquivalentItem(EquivalentData):
    brandSlug: str | None = None


class EquivalentsData(_M):
    items: list[EquivalentItem] = Field(max_length=6)
    # Names that matched no reviewed brand (the count only).
    unmatched: int = 0


# --- MCP 2.2: packages — the strengths and pack sizes of one medicine --------------


class PackagesData(_M):
    drug: DrugRef
    configs: list[ConfigOption] = Field(default=[], max_length=6)
    # Strengths with a card price that are not in ``configs``.
    moreCount: int = 0
    # The package the most chains price (what compare_prices opens with).
    default: PackageRef | None = None


# --- MCP 2.2: the basket — several medicines at one place ------------------------


class BasketItem(_M):
    drug: DrugRef
    package: PackageRef
    coverage: Coverage
    # False = no listed chain was seen pricing it: it is left out of every sum.
    priced: bool = True


class BasketTotal(_M):
    """A sum of observed card prices with the span of their observation dates —
    an amount still never travels without a date."""

    amount: float
    # How many of the items the sum adds (the priced ones).
    count: int
    observedFrom: date
    observedTo: date


class BasketRow(_M):
    family: str
    name: str
    zone: str | None = None
    nearestMiles: float | None = None
    storeCount: int = 0
    # One per item, in the items' order; None = no card price seen there.
    prices: list[Price | None] = Field(max_length=6)
    # Only when every item has a price at this chain.
    total: BasketTotal | None = None
    # 1-based numbers of the PRICED items without a price here.
    missing: list[int] = []


class BasketPick(_M):
    # 1-based number of the item this chain is for.
    item: int
    family: str
    name: str


class BasketSplit(BasketTotal):
    chains: int
    picks: list[BasketPick] = Field(max_length=6)


class BasketData(_M):
    items: list[BasketItem] = Field(max_length=6)
    origin: Origin
    rows: list[BasketRow] = Field(max_length=8)
    moreCount: int = 0
    split: BasketSplit | None = None
    needsZip: bool
    # Names that matched no medicine (the count only — the text is not echoed).
    unmatched: int = 0


class ErrorInfo(_M):
    code: str
    message: str | None = None
    retryAfter: int | None = None
    suggestions: list[dict[str, Any]] | None = None


class Notice(_M):
    """Something to say about a view that IS drawn (unlike ``error``):
    ``zip_invalid`` — the ZIP given is not 5 digits; ``where_not_found`` — the
    typed place (``where``) could not be placed (phase 2)."""

    code: Literal["zip_invalid", "where_not_found", "basket_trimmed"]
    message: str = Field(min_length=1)


class NextStep(_M):
    """One call that fits after this answer (``next_steps``): the arguments are
    filled in from the answer; ``ask`` names the one thing to get from the
    person first. For the model — the widget does not draw it."""

    tool: str = Field(min_length=1)
    args: dict[str, str | int | bool | list[str]] = {}
    why: str = Field(min_length=1)
    ask: Literal["zip", "medicine", "which_medicine", "email_and_consent"] | None = None


class _Envelope(_M):
    schema_: Literal["finerx.view/2"] = Field(alias="schema")
    locale: str
    dir: Literal["ltr", "rtl"]
    card: CardView
    error: ErrorInfo | None = None
    notice: Notice | None = None
    next: list[NextStep] | None = Field(default=None, max_length=3)

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


class SearchEnvelope(_Envelope):
    view: Literal["search"]
    data: SearchData | None = None


class _LegacyEnvelope(_Envelope):
    """``find_us_equivalent`` and ``get_prescription_options`` answered with
    their own keys in 2.0 (``found``, ``guidance``, ``havePrescription``, …).
    2.1 draws them as views but keeps every 2.0 key beside the envelope — the
    contract allows additions only."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class EquivalentEnvelope(_LegacyEnvelope):
    view: Literal["equivalent"]
    data: EquivalentData | None = None


class RxEnvelope(_LegacyEnvelope):
    view: Literal["rx"]
    data: RxData | None = None


class BasketEnvelope(_Envelope):
    view: Literal["basket"]
    data: BasketData | None = None


class PackagesEnvelope(_LegacyEnvelope):
    """``get_drug`` keeps every 2.0 key beside the envelope."""

    view: Literal["packages"]
    data: PackagesData | None = None


class EquivalentsEnvelope(_Envelope):
    view: Literal["equivalents"]
    data: EquivalentsData | None = None


class TransferEnvelope(_Envelope):
    view: Literal["transfer"]
    data: TransferData | None = None


ENVELOPES: dict[str, type[_Envelope]] = {
    "transfer": TransferEnvelope,
    "equivalents": EquivalentsEnvelope,
    "packages": PackagesEnvelope,
    "basket": BasketEnvelope,
    "prices": PricesEnvelope,
    "pharmacies": PharmaciesEnvelope,
    "card": CardEnvelope,
    "search": SearchEnvelope,
    "equivalent": EquivalentEnvelope,
    "rx": RxEnvelope,
}


def validate(structured: dict[str, Any]) -> _Envelope:
    """Parse one envelope by its ``view`` (raises ``ValidationError``)."""
    model = ENVELOPES[structured["view"]]
    return model.model_validate(structured)


def envelope_json_schema() -> dict[str, Any]:
    """JSON Schema of the envelopes (phase 2: → ``widget-src/src/types.gen.ts``)."""
    return {name: model.model_json_schema(by_alias=True) for name, model in ENVELOPES.items()}
