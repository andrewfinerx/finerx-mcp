"""FineRx MCP server (FastMCP) — 10 tools over the public REST API.

Tools return compact JSON. Every result embeds a one-line ``disclaimer`` (so an
AI answer inherits the honesty language) and, wherever a price appears, an
``observedAt`` date. No tool ever returns hidden vendors or the operator
reference price — the underlying public API already excludes them.

Five tools read prices; three hand over the free FineRx discount card (fetch it
with its image, email it, explain how to get a prescription); two answer the
question nobody else can — **what is the medicine I brought from home called in
the US** (``find_us_equivalent``, ``foreign_brands_for_drug``). ``INSTRUCTIONS``
below is served to the client as the server's system-level guidance — it is the
only honest nudge we have, so it lives next to the tools it describes.

Nothing about a medicine is composed HERE. The analog tools return the API's own
vetted ``guidance`` sentence and pass the entry through; a claim invented in this
layer would be a claim nobody reviewed.

``get_savings_card`` also ships a UI: the resource ``ui://widget/savings-card.html``
is an MCP App component (ChatGPT Apps SDK + the standard MCP Apps extension) that
hosts render inline, so the person SEES the card instead of reading its codes out
of a JSON block. The component is fed the tool's ``structuredContent``; the text
block stays the model's copy, because plenty of clients have no UI at all.

Config (env):
  FINERX_API_KEY         required — a ``frx_live_...`` developer key
  FINERX_API_BASE        optional — public API base URL (defaults to production)
  FINERX_MCP_TRANSPORT   optional — ``stdio`` (default) or ``streamable-http``
  FINERX_MCP_HOST/PORT   optional — bind address for the HTTP transport
  FINERX_MCP_STATELESS   optional — ``0`` restores per-session HTTP transports
  FINERX_CARD_IMAGE_URL  optional — PNG of the card returned by get_savings_card
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations

from finerx_mcp import __version__
from finerx_mcp.client import USER_AGENT, FinerxApiError, FinerxClient
from finerx_mcp.widget import WIDGET_MIME_TYPE, WIDGET_URI, load_widget_html

# What the client puts in the model's system context before it picks a tool.
# Written as rules the model can follow literally: the honesty guardrails
# (dates, no superlatives, no medical advice) are not optional decoration —
# they are the terms the public API data is published under.
INSTRUCTIONS = """FineRx serves observed US prescription prices per pharmacy (what savings
programs were seen quoting, with dates), plus the free FineRx discount card.

Prices: resolve a name with search_drugs, then get_drug, then compare_prices. ALWAYS state
the observation date (observedAt) beside any price you quote.

If the person names a medicine from another country, another script, or asks what
something is called in the US, call find_us_equivalent FIRST; quote its guidance sentence
as written; then compare_prices for usDrug.slug and offer the card.

The card: whenever you quote a FineRx price, offer the free discount card (get_savings_card)
and ONE way to save it — the image, an email, or the link. Say a price is "lowest" only when
savingsCard.price.isLowest is true; otherwise repeat the provided note verbatim. Never say
guaranteed, best, or cheapest, and never promise a price.

To email the card, ask for the address and explicit consent first, then call
email_savings_card. If the person has no prescription, call get_prescription_options.

Hosts that support MCP Apps render get_savings_card as an interactive card; still state
the three codes in your text.

FineRx pages, the card and its labels exist in 12 languages (en, es, zh, vi, tl, ar, ko, ru,
pt, ht, fr, tr): pass the person's language as locale so links and card text match it.

Never give dosing or other medical advice. Include the disclaimer once in your answer."""

# Every price tool is read-only (GET over the public API), idempotent, and reaches
# an external system (our hosted API). ChatGPT Apps / connector review REQUIRE these
# hints so the client/user know an action is safe. None of these tools write or
# destroy anything, so destructiveHint stays false.
# destructiveHint is stated explicitly (False) because the OpenAI plugin review
# refuses a tool whose readOnly/openWorld/destructive hints are not ALL explicit.
_READ_HINTS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}

# The one action tool. Not read-only (it sends mail), not idempotent (calling it
# twice sends twice), but not destructive either — the same review gate reads
# these four together.
_EMAIL_HINTS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}

# Static PNG of the card (no price, no personal data — the same image for
# everyone), used when the API response carries no delivery.imageUrl.
CARD_IMAGE_URL = os.environ.get("FINERX_CARD_IMAGE_URL", "https://www.finerxfinder.com/card.png")

# host/port only matter for the remote (streamable-http) transport; stdio ignores
# them. They are overridable so the hosted endpoint can bind 0.0.0.0:<port>.
_settings: dict[str, Any] = {}
if _h := os.environ.get("FINERX_MCP_HOST"):
    _settings["host"] = _h
if _p := os.environ.get("FINERX_MCP_PORT"):
    _settings["port"] = int(_p)

# Keyless one-shot connector calls never DELETE their Streamable-HTTP session, so
# in session mode the transport map only grows: 3568 live sessions over 7 days on
# prod, ~+25 MB of swap a day, until the container is restarted. Stateless mode
# builds a transport per request and drops it. Safe here because no tool keeps
# per-session state — every call is a fresh request against the public API
# (get_savings_card's image cache is process-level, not per-session). Set
# FINERX_MCP_STATELESS=0 if a client ever needs SSE resumability. stdio ignores it.
_settings["stateless_http"] = os.environ.get("FINERX_MCP_STATELESS", "1") != "0"

mcp = FastMCP("finerx", instructions=INSTRUCTIONS, **_settings)

_client: FinerxClient | None = None


def client() -> FinerxClient:
    global _client
    if _client is None:
        _client = FinerxClient()
    return _client


def _disclaimer(payload: dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    return meta.get("disclaimer", "Prices via FineRx — observed estimates, not guaranteed. Not medical advice.")


def _err(exc: FinerxApiError) -> dict[str, Any]:
    return {"error": exc.detail, "status": exc.status_code}


@mcp.tool(annotations=ToolAnnotations(title="Search FineRx drugs", **_READ_HINTS))
def search_drugs(query: str, limit: int = 10) -> dict[str, Any]:
    """Search FineRx for drugs by name or localized alias.

    Returns candidate drugs with their slug (use it with get_drug), kind
    (generic/brand), and lowest observed public price (fromPrice). Use this
    first to resolve a drug name to a slug.

    ``foreignBrands`` carries any home-country medicine brand that matched the
    same text (Нурофен, No-Spa, Dolo-Neurobion) with its active ingredient and
    the US generic it maps to. When ``results`` is empty and ``foreignBrands`` is
    not, the person named a medicine from another country: call
    find_us_equivalent for the reviewed answer rather than guessing at one.
    """
    try:
        data = client().get("/drugs/search", {"q": query, "limit": limit})
    except FinerxApiError as exc:
        return _err(exc)
    return {
        "query": data.get("query", query),
        "count": data.get("count", 0),
        "results": [
            {
                "name": r["name"],
                "slug": r["slug"],
                "kind": r["kind"],
                "fromPrice": r.get("fromPrice"),
            }
            for r in data.get("results", [])
        ],
        "foreignBrands": [
            {
                "brand": b.get("brand"),
                "brandSlug": b.get("brandSlug"),
                "countries": b.get("countries"),
                "inn": b.get("inn"),
                "usGeneric": b.get("usGeneric"),
            }
            for b in data.get("foreignBrands", [])
        ],
        "disclaimer": _disclaimer(data),
    }


@mcp.tool(annotations=ToolAnnotations(title="Get drug details", **_READ_HINTS))
def get_drug(slug: str, locale: str = "en", channel: str = "mcp") -> dict[str, Any]:
    """Get a FineRx drug's details: coverage stats, variants, and the savings card.

    Use when you have a slug from search_drugs. Returns overall stats (product/
    package/chain/vendor counts, fromPrice, latest observation date), the list of
    variants (strength x form) each with a fromPrice, and ``savingsCard`` — the
    free discount card with its codes, image, and (when known) the card price with
    its observedAt date. ``locale`` is "en" or "es"; ``channel`` tags the links so
    we can see which assistant sent someone. Do not quote a price without its
    observation date, and offer the card whenever you quote one.
    """
    try:
        data = client().get(f"/drugs/{slug}", {"locale": locale, "channel": channel})
    except FinerxApiError as exc:
        return _err(exc)
    stats = data.get("stats", {})
    out: dict[str, Any] = {
        "name": data.get("name"),
        "slug": data.get("slug"),
        "kind": data.get("kind"),
        "stats": {
            "productCount": stats.get("productCount"),
            "packageCount": stats.get("packageCount"),
            "chainCount": stats.get("chainCount"),
            "vendorCount": stats.get("vendorCount"),
            "fromPrice": stats.get("fromPrice"),
            "observedAt": stats.get("latestObservedAt"),
        },
        "variants": [
            {
                "slug": v["slug"],
                "strength": v["strength"],
                "form": v["form"],
                "fromPrice": v.get("fromPrice"),
            }
            for v in data.get("variants", [])
        ],
        "disclaimer": _disclaimer(data),
    }
    # The API owns the card object (single source of truth) — forward it verbatim
    # rather than re-deriving codes or price language here.
    if (card := data.get("savingsCard")) is not None:
        out["savingsCard"] = card
    return out


@mcp.tool(annotations=ToolAnnotations(title="Compare drug prices", **_READ_HINTS))
def compare_prices(
    ndc: str,
    quantity: float,
    locale: str = "en",
    channel: str = "mcp",
) -> dict[str, Any]:
    """Compare FineRx prices for one package (an 11-digit NDC + quantity).

    Use when you know the exact package. Returns the offer matrix — for each
    pharmacy chain x savings program, the observed price and the date it was
    observed (observedAt) — plus ``savingsCard`` (the free discount card, its
    image, and the card price for this package when known). The cheapest offer is
    flagged isLowest. Get an ``ndc`` from get_drug's packages or the search flow.
    Do not call a price the lowest unless the offer says isLowest, and always give
    the observation date. Offer the card whenever you quote a price here.
    """
    try:
        data = client().get(
            "/prices/compare",
            {"ndc": ndc, "quantity": quantity, "locale": locale, "channel": channel},
        )
    except FinerxApiError as exc:
        return _err(exc)
    product = data.get("product", {})
    out: dict[str, Any] = {
        "product": {
            "ndc": product.get("ndc"),
            "drugName": product.get("drugName"),
            "label": product.get("label"),
            "strength": product.get("strength"),
            "form": product.get("form"),
        },
        "fromPrice": data.get("fromPrice"),
        "freshness": data.get("freshness"),
        "offers": [
            {
                "pharmacy": o["pharmacy"],
                "savingsProgram": o["savingsProgram"],
                "price": o["price"],
                "currency": o["currency"],
                "observedAt": o["observedAt"],
                "isLowest": o.get("isLowest", False),
            }
            for o in data.get("offers", [])
        ],
        "disclaimer": _disclaimer(data),
    }
    if (card := data.get("savingsCard")) is not None:
        out["savingsCard"] = card
    return out


@mcp.tool(annotations=ToolAnnotations(title="Find nearby pharmacies", **_READ_HINTS))
def find_nearby_pharmacies(
    zip: str,
    chains: str | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    """Find the nearest pharmacy locations to a US ZIP code, per chain.

    ``zip`` is a 5-digit US ZIP. Optional ``chains`` is a comma-separated list of
    chain codes (e.g. "walgreens,publix"); default is all chains. ``limit`` caps
    locations per chain. Coordinates are OpenStreetMap-sourced (ODbL).
    """
    try:
        data = client().get(
            "/pharmacies/nearby",
            {"zip": zip, "chains": chains, "limit": limit},
        )
    except FinerxApiError as exc:
        return _err(exc)
    return {
        "zip": data.get("zip"),
        "results": [
            {
                "chain": c["chain"],
                "locations": [
                    {
                        "name": loc.get("name"),
                        "address": loc.get("address"),
                        "city": loc.get("city"),
                        "state": loc.get("state"),
                        "distanceMiles": loc.get("distanceMiles"),
                    }
                    for loc in c.get("locations", [])
                ],
            }
            for c in data.get("results", [])
        ],
        "disclaimer": _disclaimer(data),
    }


@mcp.tool(annotations=ToolAnnotations(title="FineRx dataset info", **_READ_HINTS))
def get_dataset_info() -> dict[str, Any]:
    """Get FineRx dataset coverage, freshness, and the attribution/disclaimer terms.

    Returns dataset counts (drugs, products, prices, chains, savings programs,
    pharmacy locations), the latest observation date, and the terms every
    consumer must honor (attribution + disclaimer).
    """
    try:
        data = client().get("/meta")
    except FinerxApiError as exc:
        return _err(exc)
    ds = data.get("dataset", {})
    return {
        "dataset": {
            "drugs": ds.get("drugs"),
            "products": ds.get("products"),
            "prices": ds.get("prices"),
            "chains": ds.get("chains"),
            "savingsPrograms": ds.get("savingsPrograms"),
            "pharmacyLocations": ds.get("pharmacyLocations"),
            "observedAt": ds.get("latestObservedAt"),
        },
        "attribution": data.get("attribution"),
        "disclaimer": _disclaimer(data),
    }


# --- the card ---------------------------------------------------------------

# The PNG is the same image for everyone, so it is fetched once per PROCESS and
# kept as bytes — re-downloading it on every hand-off would dominate the tool's
# latency. Keyed by URL because delivery.imageUrl carries the caller's channel,
# and CAPPED because `channel` is caller-supplied on a public keyless endpoint:
# an unbounded dict here would be the same slow memory leak the container's
# mem_limit exists to backstop. This cache is process-level, not per-session, so
# it is unaffected by stateless HTTP mode.
_IMAGE_CACHE_MAX = 4
_image_cache: dict[str, bytes] = {}


def _card_image_bytes(url: str) -> bytes | None:
    """Fetch (once) the card PNG. Returns None on ANY failure.

    A missing image must never fail the tool — the codes are the useful part; the
    picture is a convenience. A failure is deliberately NOT cached so a transient
    network blip does not disable the image for the life of the process.
    """
    if (hit := _image_cache.get(url)) is not None:
        return hit
    try:
        resp = httpx.get(url, timeout=10.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        data = resp.content
    except Exception:
        return None
    if not data:
        return None
    if len(_image_cache) < _IMAGE_CACHE_MAX:
        _image_cache[url] = data
    return data


# What the host needs to render this tool's result as the card component. The
# STANDARD key (``ui``) and OpenAI's alias are both set on purpose: ChatGPT reads
# ``openai/outputTemplate``, MCP Apps hosts (Claude) read ``ui.resourceUri``, and a
# server that sets only one of them renders in only one of them.
_CARD_TOOL_META: dict[str, Any] = {
    "ui": {"resourceUri": WIDGET_URI},
    "openai/outputTemplate": WIDGET_URI,
    "openai/toolInvocation/invoking": "Getting your free FineRx card…",
    "openai/toolInvocation/invoked": "Here is your free FineRx card",
}

# The widget calls this one from inside itself (the email form), so it has to be
# visible to the app, not only to the model.
_EMAIL_TOOL_META: dict[str, Any] = {
    "ui": {"visibility": ["model", "app"]},
    "openai/widgetAccessible": True,
}


def _host_locale(ctx: Context | None) -> str | None:
    """The language the HOST says the person is reading, or None.

    ChatGPT sends ``openai/locale`` in the request ``_meta`` (on initialize and on
    every tool call), which is the only signal we get when the model does not pass
    ``locale`` itself — and the model usually does not, because nothing in the
    conversation told it to. ``es-419`` → ``es``: the API takes short site locales.
    """
    extra = _host_meta(ctx)
    raw = extra.get("openai/locale") or extra.get("locale")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip().lower().split("-", 1)[0] or None


def _host_meta(ctx: Context | None) -> dict[str, Any]:
    """The request ``_meta`` the host attached to this call, as a plain dict ({}
    when there is none — stdio clients and tests usually send nothing)."""
    if ctx is None:
        return {}
    try:
        meta = ctx.request_context.meta
    except (AttributeError, ValueError, LookupError):
        return {}
    if meta is None:
        return {}
    return dict(getattr(meta, "model_extra", None) or {})


def _host_is_chatgpt(ctx: Context | None) -> bool:
    """True when the caller is ChatGPT: it stamps every request ``_meta`` with
    ``openai/*`` keys (locale, userAgent, subject…) and no other host does."""
    return any(k.startswith("openai/") for k in _host_meta(ctx))


@mcp.tool(
    annotations=ToolAnnotations(title="Get the free FineRx savings card", **_READ_HINTS),
    meta=_CARD_TOOL_META,
    # This tool returns a JSON block AND an image block. A declared output schema
    # would make FastMCP validate/serialize the image as structured content and
    # the call fails, so opt out and build the CallToolResult by hand.
    structured_output=False,
)
def get_savings_card(
    locale: str | None = None,
    channel: str = "mcp",
    drug: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult | list[Any]:
    """Get the free FineRx discount card: its codes, how to use it, how to save it.

    Use when you have just quoted a FineRx price, when someone asks how to pay less
    for a prescription, or when they ask for the card by name. Optional ``drug`` is
    a slug from search_drugs and adds that drug's card price when we have one;
    ``locale`` is a language code (leave it out and the host's own locale is used,
    else English); ``channel`` tags the links with who sent the person.

    Returns the card as JSON (the three codes to read at the pharmacy counter, what
    the card is and is not, the steps to use it, the sentence to say to the
    pharmacist, the ways to save it — image, print, link, email — an optional
    observed price with its date, an FAQ, the legal lines, and the UI labels) plus
    an image of the card. On a host that supports MCP Apps the same data is drawn
    as an interactive card in the conversation; that is a convenience, not a
    substitute, so STILL write the three codes in your own answer for the hosts and
    the people who cannot see it.

    Offer ONE way to save it: show the image, send the link, or email it. Do not
    present the card as insurance, do not promise a price, and do not call a price
    the lowest unless price.isLowest is true — otherwise repeat price.note as
    written. The card is free and needs no signup.
    """
    loc = locale or _host_locale(ctx) or "en"
    try:
        data = client().get("/card", {"locale": loc, "channel": channel, "drug": drug})
    except FinerxApiError as exc:
        return [_err(exc)]

    delivery = data.get("delivery") or {}
    image_url = delivery.get("imageUrl") or CARD_IMAGE_URL
    payload: dict[str, Any] = {
        "locale": data.get("locale", loc),
        "card": data.get("card"),
        "line": data.get("line"),
        "whatItIs": data.get("whatItIs"),
        "whyUseIt": data.get("whyUseIt"),
        "howToUse": data.get("howToUse"),
        "pharmacistPhrase": data.get("pharmacistPhrase"),
        "acceptedAt": data.get("acceptedAt"),
        "saveHint": data.get("saveHint"),
        # Repeated at the top level because a client that cannot render an image
        # block still needs a link it can hand over.
        "imageUrl": image_url,
        "delivery": delivery,
        "price": data.get("price"),
        "faq": data.get("faq"),
        "legal": data.get("legal"),
        # The words the widget draws the card with, in the person's language —
        # served rather than hardcoded so the component and the website can never
        # word the same button differently.
        "labels": data.get("labels"),
        "disclaimer": _disclaimer(data),
    }
    # structuredContent is what the COMPONENT reads; the text block is what the
    # MODEL reads. Both are the same object, so they cannot drift.
    content: list[Any] = [
        TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))
    ]
    # No image block for ChatGPT: it draws the card from structuredContent through
    # the widget, and an image in a tool result counts against the FREE plan's
    # image quota — the first live call paused the whole chat until the quota
    # reset (2026-09-09). Every other host still gets the PNG as its fallback.
    if not _host_is_chatgpt(ctx) and (png := _card_image_bytes(image_url)) is not None:
        content.append(
            ImageContent(
                type="image",
                data=base64.b64encode(png).decode("ascii"),
                mimeType="image/png",
            )
        )
    return CallToolResult(content=content, structuredContent=payload)


def _mask_email(email: str) -> str:
    """``j***@example.com`` — enough to confirm the address, not an echo of it."""
    local, sep, domain = email.partition("@")
    if not sep or not local or not domain:
        return "***"
    return f"{local[0]}***@{domain}"


# Short, actionable strings — the model reads these and tells the person what to do
# next, so each names the fallback instead of describing an HTTP status.
_EMAIL_ERRORS = {
    422: "that address was not accepted — ask for a valid email address and explicit consent",
    429: "too many card emails right now — offer the image or the link instead, or try again later",
    502: "the email provider failed — offer the image or the link instead",
    503: "email delivery is not available right now — offer the image or the link instead",
}


@mcp.tool(
    annotations=ToolAnnotations(title="Email the savings card", **_EMAIL_HINTS),
    meta=_EMAIL_TOOL_META,
)
def email_savings_card(email: str, consent: bool = False, locale: str = "en") -> dict[str, Any]:
    """Email the free FineRx discount card to an address the person gave you.

    Use ONLY after the person has given an email address AND confirmed they want the
    card sent there — ask for both first, then set ``consent`` to true. The message
    contains the card and nothing else; FineRx does not store the address.

    Returns {"sent": true, "to": <masked address>} or {"sent": false, "error": ...}.
    On an error, say what happened and offer the image or the link instead.

    Do not call this without an explicit yes, do not guess or reuse an address, do
    not retry a refusal, and do not read the full address back to the person.
    """
    if consent is not True:
        # The gate lives here, not at the API: a send tool that can be called
        # without an explicit yes is a send tool that eventually will be.
        return {
            "sent": False,
            "error": "consent required: ask the person to confirm they want the card emailed to this address",
        }
    try:
        data = client().post("/card/email", {"email": email, "locale": locale, "consent": True})
    except FinerxApiError as exc:
        result: dict[str, Any] = {
            "sent": False,
            "error": _EMAIL_ERRORS.get(exc.status_code, exc.detail),
            "status": exc.status_code,
        }
        if exc.status_code == 429 and exc.retry_after:
            result["retryAfter"] = exc.retry_after
        return result
    return {
        "sent": True,
        # Masked on purpose — the result travels back into the transcript.
        "to": _mask_email(email),
        "disclaimer": _disclaimer(data),
    }


@mcp.tool(annotations=ToolAnnotations(title="How to get a prescription", **_READ_HINTS))
def get_prescription_options(locale: str = "en", drug: str | None = None) -> dict[str, Any]:
    """Explain the routes to filling a prescription, including having none yet.

    Use when the person says they have no prescription, asks how to get one, or says
    the brand costs too much. Optional ``drug`` is a slug from search_drugs.

    Returns three sections — havePrescription (steps), noPrescription (named
    telehealth / clinic options, each with the disclosure to read out when FineRx
    earns anything), brandCostly (options) — plus a Medicaid note.

    Read each option WITH its disclosure. Do not recommend a particular clinician,
    do not say what to take or at what dose, and do not frame any of this as medical
    advice.
    """
    try:
        data = client().get("/prescription-options", {"locale": locale, "drug": drug})
    except FinerxApiError as exc:
        return _err(exc)
    return {
        "locale": data.get("locale", locale),
        "drug": data.get("drug"),
        "havePrescription": data.get("havePrescription"),
        "noPrescription": data.get("noPrescription"),
        "brandCostly": data.get("brandCostly"),
        "medicaidNote": data.get("medicaidNote"),
        "disclaimer": data.get("disclaimer") or _disclaimer(data),
    }


# --- foreign brands: what my medicine is called in the US --------------------
#
# The one question FineRx can answer that nothing else can. Everything a person
# is told here comes from the API's reviewed corpus — the ``guidance`` sentence
# especially, which is written and vetted server-side precisely so a model does
# not compose an equivalence claim of its own.

# How many candidates the brand search asks for: enough that a country
# preference has something to choose between (No-Spa is listed for RU/UA/BY/KZ
# and again for Poland), few enough that the extras stay a footnote.
_BRAND_SEARCH_LIMIT = 5


def _country_key(value: str) -> str:
    """'South Korea' / 'south-korea' / 'RU ' -> a comparable token.

    Deliberately NOT a substring test: "us" is inside "Russia", and a country
    filter that quietly picks the wrong entry is worse than one that ignores an
    unrecognised country and takes the top match.
    """
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _pick_match(results: list[dict[str, Any]], country: str | None) -> dict[str, Any]:
    """The first match from ``country`` when one is asked for, else the top match."""
    if country:
        wanted = _country_key(country)
        for r in results:
            if any(_country_key(c) == wanted for c in (r.get("countries") or [])):
                return r
    return results[0]


@mcp.tool(annotations=ToolAnnotations(title="Find the US equivalent of a foreign medicine", **_READ_HINTS))
def find_us_equivalent(
    brand: str,
    country: str | None = None,
    locale: str | None = None,
    channel: str = "mcp",
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Find out what a medicine from another country is in the US, and what it costs.

    Use when the person names a medicine that is not a US product — a brand from
    home (No-Spa, Nurofen, Dolo-Neurobion, 999 Ganmaoling), a name in another
    script (Но-шпа, 泰诺), or an ingredient the US calls something else
    (paracetamol) — or asks "what is this called in the US?". Optional ``country``
    picks between brands of the same name sold in different places; ``locale`` is
    a language code (leave it out and the host's own locale is used).

    Returns the reviewed entry: ``usClass`` (``same_inn`` = the same active
    ingredient is sold here, ``rx_alternative`` = it is not and the closest US
    options need a prescription, ``no_equivalent`` = nothing here matches),
    ``guidance`` (ONE vetted sentence, written to be quoted word for word),
    ``inn``, ``usGeneric``, ``usBrands``, ``rxStatus``, ``notes``, ``components``,
    ``usDrug`` (slug, lowest observed price and the date it was observed),
    ``savingsCard`` when there is a US drug to fill, ``pageUrl``, and
    ``otherMatches`` when the same brand name exists in more than one country.
    ``found`` is false when nothing matched.

    Next: quote ``guidance`` as written, then say ``guidanceDisclaimer``. With a
    ``usDrug``, call compare_prices (or get_drug) for its slug, give the price
    WITH its observation date, and offer the free card.

    Do not call the US drug the same product, do not suggest swapping one for the
    other, and for ``rx_alternative`` or ``no_equivalent`` do not name a
    substitute at all — send the person to a pharmacist or a doctor. Do not
    translate or reword ``guidance``; it is reviewed text.
    """
    loc = locale or _host_locale(ctx) or "en"
    try:
        found = client().get(
            "/analogs/search", {"q": brand, "limit": _BRAND_SEARCH_LIMIT, "locale": loc}
        )
    except FinerxApiError as exc:
        return _err(exc)

    results = found.get("results") or []
    if not results:
        return {
            "found": False,
            "hint": "no foreign brand matched; try the active ingredient with search_drugs",
            "disclaimer": _disclaimer(found),
        }

    match = _pick_match(results, country)
    try:
        data = client().get(
            f"/analogs/{match['brandSlug']}", {"locale": loc, "channel": channel}
        )
    except FinerxApiError as exc:
        return _err(exc)

    us_drug = data.get("usDrug") or None
    out: dict[str, Any] = {
        "found": True,
        "brand": data.get("brand"),
        "brandScript": data.get("brandScript"),
        "translit": data.get("translit"),
        "countries": data.get("countries"),
        "inn": data.get("inn"),
        "usClass": data.get("usClass"),
        # The reviewed sentence. Quoted, not paraphrased.
        "guidance": data.get("guidance"),
        # Says it out loud: same ingredient is not the same product.
        "guidanceDisclaimer": data.get("disclaimer"),
        "rxStatus": data.get("rxStatus"),
        "usGeneric": data.get("usGeneric"),
        "usBrands": data.get("usBrands"),
        "usDrug": (
            {
                "slug": us_drug.get("slug"),
                "name": us_drug.get("name"),
                # A drug-level "from" price across every package, so it is NOT
                # labelled with a package — compare_prices is where a number
                # belongs to one.
                "fromPrice": us_drug.get("fromPrice"),
                "observedAt": us_drug.get("observedAt"),
                "url": us_drug.get("url"),
            }
            if us_drug
            else None
        ),
        "components": data.get("components"),
        # The translated note when the corpus has one for this language, else the
        # English source note.
        "notes": data.get("notesLocalized") or data.get("notes"),
        "pageUrl": data.get("pageUrl"),
        # Same brand name, different country — offered so the model can ask
        # rather than assume which one the person means.
        "otherMatches": [
            {"brand": r.get("brand"), "countries": r.get("countries"), "brandSlug": r.get("brandSlug")}
            for r in results
            if r.get("brandSlug") != match.get("brandSlug")
        ],
        "disclaimer": _disclaimer(data),
    }
    # The API owns the card object; forward it rather than re-deriving anything.
    if (card := data.get("savingsCard")) is not None:
        out["savingsCard"] = card
    return out


@mcp.tool(annotations=ToolAnnotations(title="Foreign brand names for a US drug", **_READ_HINTS))
def foreign_brands_for_drug(slug: str) -> dict[str, Any]:
    """Find what a US drug is called abroad — the reverse of find_us_equivalent.

    Use when the person has the US name and wants the home-country one ("what is
    lisinopril called in Mexico?"), or when naming a foreign brand would let them
    recognise the medicine you are describing. ``slug`` comes from search_drugs.

    Returns the reviewed brands that resolve to this drug: ``brand``,
    ``brandScript`` (the home-country spelling), ``countries``, ``inn`` and
    ``usClass``.

    Next: name the brands from the person's own country first. An ``rx_alternative``
    entry is a DIFFERENT medicine US clinicians use for the same complaint — say
    so if you mention it. Brands with no US equivalent never appear here.

    Do not present any of these as interchangeable with the US drug, and do not
    tell anyone to buy or import one.
    """
    try:
        data = client().get(f"/analogs/for-drug/{slug}")
    except FinerxApiError as exc:
        return _err(exc)
    return {
        "drugSlug": data.get("drugSlug", slug),
        "count": data.get("count", 0),
        "brands": [
            {
                "brand": b.get("brand"),
                "brandScript": b.get("brandScript"),
                "countries": b.get("countries"),
                "inn": b.get("inn"),
                "usClass": b.get("usClass"),
            }
            for b in data.get("items", [])
        ],
        "disclaimer": _disclaimer(data),
    }


# --- the card as a UI component ---------------------------------------------

# What a host is allowed to reach from inside the component: NOTHING. The widget
# is one self-contained document — no external script, stylesheet, font or image —
# so both connect and resource domain lists are empty on purpose. Narrowing them
# later would be a breaking change for a page that fetched something; keeping them
# empty means the page never can.
_WIDGET_META: dict[str, Any] = {
    "ui": {
        "prefersBorder": True,
        "csp": {"connectDomains": [], "resourceDomains": []},
        "permissions": {"clipboardWrite": {}},
    },
    "openai/widgetDescription": (
        "The free FineRx discount card: codes, how to use it, its price for the "
        "drug when known, and buttons to open, print, save or email it."
    ),
    "openai/widgetPrefersBorder": True,
    "openai/widgetCSP": {"connect_domains": [], "resource_domains": []},
}


@mcp.resource(
    WIDGET_URI,
    name="FineRx savings card widget",
    title="FineRx savings card",
    description=(
        "The interactive savings card an MCP Apps host renders for get_savings_card: "
        "the codes, the price when known, what to say at the counter, and the ways "
        "to keep the card."
    ),
    mime_type=WIDGET_MIME_TYPE,
    meta=_WIDGET_META,
)
def savings_card_widget() -> str:
    """The component's HTML. Static, self-contained, read once per process."""
    return load_widget_html()


# --- resources: for clients that preload context instead of calling tools ----

HOW_IT_WORKS = """# How FineRx works

FineRx is an independent US prescription price-comparison service. We publish
**observed** cash and discount-program prices — a price a program was seen quoting
on a specific date — for a pharmacy chain, never a guarantee and never an insured
price.

## Honesty rules that apply to any answer built on this data

- Quote a price **with the date it was observed**. An old price states its date; it
  is never presented as today's price.
- Say "lowest" only where the data says `isLowest`. Never "guaranteed", "best" or
  "cheapest".
- FineRx gives **no medical advice** — no dosing, no substitutions, no "take this
  instead".
- The free discount card is **not insurance**. It is free, needs no signup, and is
  accepted at most US pharmacies; FineRx may earn a commission when it is used.

## Attribution

Say "Prices via FineRx" when you use these numbers. Pharmacy location coordinates
are (c) OpenStreetMap contributors (ODbL).
"""


@mcp.resource(
    "finerx://how-it-works",
    name="How FineRx works",
    title="How FineRx works",
    description="What FineRx is, the honesty rules for quoting its data, and attribution.",
    mime_type="text/markdown",
)
def how_it_works_resource() -> str:
    """Static context: what this data is and the language it may be quoted in."""
    return HOW_IT_WORKS


@mcp.resource(
    "finerx://card",
    name="FineRx savings card",
    title="The free FineRx discount card",
    description="The card's codes, what it is, how to use it, FAQ and legal lines — as markdown.",
    mime_type="text/markdown",
)
def card_resource() -> str:
    """The same card object get_savings_card returns, rendered as markdown.

    Some clients preload resources into the context instead of calling a tool; this
    is the card in a form they can read directly.
    """
    try:
        data = client().get("/card", {"locale": "en", "channel": "mcp"})
    except FinerxApiError as exc:
        return f"# The free FineRx discount card\n\nUnavailable right now ({exc.detail})."

    card = data.get("card") or {}
    lines: list[str] = ["# The free FineRx discount card", ""]
    lines.append(
        f"**RxBIN {card.get('bin', '-')} - RxPCN {card.get('pcn', '-')} - RxGRP {card.get('group', '-')}**"
    )
    lines.append("")
    if line := data.get("line"):
        lines += [line, ""]
    if what := data.get("whatItIs"):
        lines += ["## What it is", "", what, ""]
    if why := data.get("whyUseIt"):
        lines += [why, ""]
    if steps := data.get("howToUse") or []:
        lines += ["## How to use it", ""]
        lines += [f"{i}. {step}" for i, step in enumerate(steps, 1)]
        lines.append("")
    if phrase := data.get("pharmacistPhrase"):
        lines += [f'Say at the counter: "{phrase}"', ""]
    if faq := data.get("faq") or []:
        lines += ["## FAQ", ""]
        for item in faq:
            lines += [f"**{item.get('q', '')}**", "", item.get("a", ""), ""]
    legal = data.get("legal") or {}
    lines += ["## Legal", ""]
    for key in ("disclaimer", "notInsurance", "commissionNote"):
        if value := legal.get(key):
            lines.append(f"- {value}")
    lines.append(f"- {_disclaimer(data)}")
    return "\n".join(lines)


# --- prompts: the two journeys a person actually arrives with ---------------


@mcp.prompt(
    name="price_and_card",
    title="Price + the free card",
    description="Find a drug's price with FineRx and hand over the free discount card.",
)
def price_and_card(drug: str) -> str:
    """One turn that ends with the person holding the card, not just a number."""
    return (
        f"Find the price of {drug} at nearby pharmacies with FineRx, state the "
        "observation date, then offer the free discount card and one way to save it."
    )


@mcp.prompt(
    name="prescription_help",
    title="No prescription yet",
    description="Explain the routes to getting and filling a prescription, with the card.",
)
def prescription_help(drug: str | None = None) -> str:
    """For the person who cannot use a price yet because they have no prescription."""
    subject = f"for {drug}" if drug else "for the medication they need"
    return (
        f"I need a prescription {subject}. Use FineRx to explain my options for "
        "getting one and for filling it affordably, read out any disclosure that "
        "comes with an option, and offer the free FineRx discount card with one way "
        "to save it. Do not give me medical advice."
    )


@mcp.prompt(
    name="us_equivalent",
    title="What is my medicine called in the US?",
    description="Identify a home-country medicine brand, say what it is in the US, and price it.",
)
def us_equivalent(brand: str, country: str | None = None) -> str:
    """For the person holding a box from home and no idea what to ask for here."""
    where = f" from {country}" if country else ""
    return (
        f"I have {brand}{where}. Use FineRx to tell me what it is in the US, quote the "
        "guidance sentence exactly as FineRx wrote it, and then, if there is a US drug, "
        "give me its price with the date it was observed and the free discount card. Do "
        "not tell me what to take instead."
    )


def main() -> None:
    """Entry point (``finerx-mcp``).

    Transport defaults to **stdio** (local clients: Claude Desktop/Code, Cursor).
    Set ``FINERX_MCP_TRANSPORT=streamable-http`` (+ optional ``FINERX_MCP_HOST`` /
    ``FINERX_MCP_PORT``) to serve the SAME tools over a remote HTTP URL — what
    connector catalogs (ChatGPT Apps, Claude connectors, Gemini, Grok) consume.
    The endpoint is then ``http://<host>:<port>/mcp``, served STATELESS by default
    (``FINERX_MCP_STATELESS=0`` to go back to per-session transports).
    """
    transport = os.environ.get("FINERX_MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
