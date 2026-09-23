"""FineRx MCP server 2.0 (FastMCP) — card prices near a place, and the card in every answer.

What an assistant gets here, in the order the product is positioned:

1. **What US pharmacy chains were seen charging with the free FineRx card**, per
   chain, each price with the date it was observed (``compare_prices`` — by ZIP,
   by ChatGPT's approximate location, or nationally), which of those chains have
   stores nearby (``find_nearby_pharmacies``), and **the card itself**
   (``get_savings_card``, ``email_savings_card``) — the one thing an assistant
   can hand over end to end: the codes work at the counter with no click-through.
2. What a medicine from another country is called here (``find_us_equivalent``,
   ``foreign_brands_for_drug``), routes to a prescription
   (``get_prescription_options``), pages and card texts in 12 languages.
3. Honesty: every amount carries its observation date, nothing is scaled to
   another pack size, no price is promised (``card_law``).

The card law (owner-approved 2026-09-22) is enforced in code, not in prose:
``card_law.ensure`` puts the card (codes + the approved sentence + the small
print) into every result except ``get_dataset_info``, and
``tests/test_card_law.py`` checks every tool ``list_tools()`` returns.

**No third-party program feed.** 2.0 reads only free-card prices (the API's
``card_prices_current`` read model, via ``/prices/near``, ``/drugs/{slug}/options``,
``/drugs/{slug}/card-prices``) and never names a savings program
(``flags.competitor_prices_enabled`` is false by default).

**Views.** ``compare_prices``, ``find_nearby_pharmacies``,
``get_savings_card`` and (2.1) ``open_price_finder``, ``find_us_equivalent``,
``get_prescription_options`` return a ``finerx.view/2`` envelope that the ONE
widget ``ui://finerx/v2/app.html`` draws (prices / pharmacies / card / search /
equivalent / rx). Inside the card the person searches, changes dose, quantity
or place through ``ui_suggest`` / ``ui_prices`` / ``ui_nearby`` — app-only
tools the model never sees (``_meta.ui.visibility = ["app"]``), which is how
the card answers without spending a model turn. Only those app-only tools take
a place as TEXT (``where``: a ZIP, a city or an address); it goes once into
the body of ``POST /prices/near`` or ``POST /geocode`` and nowhere else.

**Privacy.** The one log line per call names the tool, the status, the time and
the host class — never an argument, a ZIP, a typed place, a coordinate or a
subject. ChatGPT's
location hint is rounded to 0.01° on arrival and used for one API request.
Per-person limits key on an HMAC of ``openai/subject`` (``limits``).

Config (env):
  FINERX_API_KEY              required — a ``frx_live_...`` developer key (tier ``mcp`` on the hosted box)
  FINERX_API_BASE             optional — public API base URL (defaults to production)
  FINERX_MCP_TRANSPORT        optional — ``stdio`` (default) or ``streamable-http``
  FINERX_MCP_HOST/PORT/PATH   optional — bind address and path for the HTTP transport (path default ``/mcp``)
  FINERX_MCP_STATELESS        optional — ``0`` restores per-session HTTP transports
  FINERX_MCP_SUBJECT_SALT     optional — HMAC salt for the per-person rate limit (random per process if unset)
  FINERX_MCP_COMPETITOR_PRICES optional — ``true`` re-attaches the 1.x program-feed fields (default false)
  FINERX_MCP_BUILD            optional — build id shown as ``finerx/build`` (the deploy sets the git sha8)
  FINERX_CARD_IMAGE_URL       optional — PNG of the card for hosts without UI
"""
from __future__ import annotations

import asyncio
import base64
import functools
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations

from finerx_mcp import __version__, card_law, hosts, views
from finerx_mcp.client import USER_AGENT, FinerxApiError, FinerxClient, slug_path, valid_slug
from finerx_mcp.flags import competitor_prices_enabled
from finerx_mcp.labels import labels_for, tr
from finerx_mcp.limits import LIMITER
from finerx_mcp.widget import (
    APP_URI,
    APP_URI_V21,
    WIDGET_MIME_TYPE,
    WIDGET_URI,
    build_id,
    load_app_html,
)

log = logging.getLogger("finerx_mcp")

# The MCP SDK logs every received JSON-RPC message at DEBUG — tool arguments
# included (a ZIP, an email address). Keep its loggers at INFO or quieter so
# turning on debug logging for the app never turns on argument logging.
for _name in ("mcp", "mcp.server", "mcp.shared"):
    _lg = logging.getLogger(_name)
    if _lg.level < logging.INFO:
        _lg.setLevel(logging.INFO)

# What the client puts in the model's system context before it picks a tool.
# Written as rules the model can follow literally; the order is the product's:
# card prices + the card, then foreign brands and languages, then honesty.
INSTRUCTIONS = """FineRx shows what US pharmacy chains were seen charging with the free FineRx discount card — per chain, each price with the date it was observed — and hands over the card itself: free, no signup, not insurance.

Which tool:
- "How much is X / near me / in 10001": compare_prices(drug, strength?, form?, quantity?, zip?). Pass zip only when the person named a ZIP or a place you can map to one; otherwise leave it out (the host's approximate location or a national answer is used). The card price is set per chain (Walmart: per state), so the choice is the chain, not the address.
- Pharmacies near a ZIP: find_nearby_pharmacies. Strengths and pack sizes of a drug: get_drug. A name to a slug: search_drugs.
- The person wants to look a medicine up themselves, or asks to open FineRx: open_price_finder(query?) — the search opens inside the card.
- The card: get_savings_card. To email it, ask for the address and an explicit yes first, then call email_savings_card.
- A medicine from another country or in another script: find_us_equivalent FIRST; quote its guidance sentence as written; then compare_prices for usDrug.slug.
- No prescription yet: get_prescription_options. Pages and the card exist in 12 languages (en, es, zh, vi, tl, ar, ko, ru, pt, ht, fr, tr): pass the person's language as locale.

The card rule — every answer about a medicine offers the free FineRx card:
1. Answer first: each price with its chain and its observation date (observedAt) on the same line.
2. Then the card sentence from card.law, as written, and the three codes (BIN, PCN, Group) — in full once per conversation, later a one-line reminder.
3. End with card.fine in one line.
The card is accepted at card.chainsCount pharmacy chains (say that number, not "most pharmacies"). Never promise a price or a saving, and never use these words about prices or the card: always, guaranteed, "save up to", best, cheapest, lowest, usually, "works with insurance". The pharmacy sets the final price at the counter; we do not see stock, so suggest calling ahead. Never scale a price to another pack size: when coverage is other_quantities, name the pack sizes that were seen.

For controlled or age-restricted medicines (stimulants such as Adderall, opioids, benzodiazepines and sleep medicines such as Xanax or Ambien, phentermine, testosterone, carisoprodol, pregabalin) give the card prices and the card only — no route to a prescription and no adjectives about savings.

Hosts that render MCP Apps show prices, pharmacies and the card as an interactive card; still write the prices, dates and codes in your text for hosts and people that cannot see it. What the person picks inside the card (a medicine, dose, pack size, ZIP or city) reaches you as context from the card: build on that choice instead of asking again.

Never give dosing or other medical advice. Attribute as "Prices via FineRx"."""

# Every tool except email reads our own closed catalog through the public API:
# read-only, idempotent, and — for review purposes — not open-world (it cannot
# reach anything outside FineRx's data). All four hints explicit: the OpenAI
# review refuses a tool whose hints are not.
_READ_HINTS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

# Sending an email cannot be undone ("sending messages… you can't undo" is the
# review's own example of destructive) and it reaches outside FineRx.
_EMAIL_HINTS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": True,
}

# Static PNG of the card (no price, no personal data — the same image for
# everyone), for hosts that render no UI.
CARD_IMAGE_URL = os.environ.get("FINERX_CARD_IMAGE_URL", "https://www.finerxfinder.com/card.png")
WIDGET_DOMAIN = "https://www.finerxfinder.com"

# host/port/path only matter for the remote (streamable-http) transport; stdio
# ignores them. The hosted 2.0 runs beside 1.x as /mcp-next on its own port.
_settings: dict[str, Any] = {}
if _h := os.environ.get("FINERX_MCP_HOST"):
    _settings["host"] = _h
if _p := os.environ.get("FINERX_MCP_PORT"):
    _settings["port"] = int(_p)
if _path := os.environ.get("FINERX_MCP_PATH"):
    _settings["streamable_http_path"] = _path

# Keyless one-shot connector calls never DELETE their Streamable-HTTP session, so
# in session mode the transport map only grows (3568 live sessions over 7 days
# on prod, 1.x). Stateless mode builds a transport per request and drops it.
# Safe: no tool keeps per-session state. FINERX_MCP_STATELESS=0 to go back.
_settings["stateless_http"] = os.environ.get("FINERX_MCP_STATELESS", "1") != "0"

mcp = FastMCP("finerx", instructions=INSTRUCTIONS, **_settings)
# serverInfo.version in the initialize answer: ours, not the SDK's (FastMCP 1.x
# has no parameter for it and falls back to the `mcp` package version).
mcp._mcp_server.version = __version__

_client: FinerxClient | None = None


def client() -> FinerxClient:
    global _client
    if _client is None:
        _client = FinerxClient()
    return _client


# --- the result every tool returns ------------------------------------------------


def _channel(arg: str | None, ctx: Any) -> str:
    raw = (arg or "").strip().lower()
    clean = re.sub(r"[^a-z0-9_-]", "", raw)[:24]
    return clean or hosts.default_channel(ctx)


def _result(
    text: str,
    structured: dict[str, Any],
    *,
    locale: str,
    channel: str,
    ui: bool = False,
    meta: dict[str, Any] | None = None,
    card: bool = True,
) -> CallToolResult:
    """One CallToolResult: ``content`` for the model, ``structuredContent`` for
    the widget (and ChatGPT's model), ``_meta`` for the widget only."""
    out_meta: dict[str, Any] = {"finerx/build": build_id()}
    if ui:
        out_meta["finerx/labels"] = labels_for(locale)
    if meta:
        out_meta.update(meta)
    result = CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=structured,
        _meta=out_meta,
    )
    return card_law.ensure(result, locale=locale, channel=channel) if card else result


def _status_of(result: Any) -> str:
    sc = getattr(result, "structuredContent", None) or {}
    err = sc.get("error") if isinstance(sc, dict) else None
    if isinstance(err, dict):
        return str(err.get("code") or "error")
    if isinstance(err, str) or (isinstance(sc, dict) and sc.get("sent") is False):
        return "refused"
    return "ok"


async def _plain_failure(
    name: str,
    ctx: Any,
    kwargs: dict[str, Any],
    *,
    code: str,
    retry_after: int | None = None,
) -> CallToolResult:
    """Busy / rate-limited / internal error: an honest sentence and the card."""
    locale = hosts.resolve_locale(kwargs.get("locale") if isinstance(kwargs.get("locale"), str) else None, ctx)
    if code == "rate_limited":
        text = tr(locale, "rateLimited", n=retry_after)
    else:
        text = tr(locale, "loadFailed")
    error = {"code": code, "retryAfter": retry_after} if retry_after else {"code": code}
    if name == "get_dataset_info":
        return _result(text, {"error": error}, locale=locale, channel="mcp", card=False)
    channel = _channel(kwargs.get("channel") if isinstance(kwargs.get("channel"), str) else None, ctx)
    card_view = card_law.to_view(card_law.fallback_card(locale, channel), locale=locale)
    view = _VIEW_OF.get(name)
    if view:
        structured = views.envelope(
            view, locale=locale, direction=hosts.text_dir(locale), card=card_view, data=None, error=error
        )
        return _result(text, structured, locale=locale, channel=channel, ui=True)
    return _result(text, {"error": error, "card": card_view}, locale=locale, channel=channel)


def _guarded(kind: str) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Rate limit, time, log (name/status/ms/host class only) and never let an
    exception — or its arguments — escape a tool."""

    def deco(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        name = fn.__name__

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = kwargs.get("ctx")
            started = time.perf_counter()
            status = "ok"
            try:
                wait = LIMITER.check(kind, hosts.subject_key(ctx))
                if wait:
                    status = "rate_limited"
                    return await _plain_failure(name, ctx, kwargs, code="rate_limited", retry_after=wait)
                result = await fn(*args, **kwargs)
                status = _status_of(result)
                return result
            except Exception as exc:  # the class only — its text may quote an argument
                status = "error"
                log.warning("tool=%s failed with %s", name, type(exc).__name__)
                return await _plain_failure(name, ctx, kwargs, code="internal_error")
            finally:
                log.info(
                    "tool=%s status=%s ms=%d host=%s",
                    name,
                    status,
                    int((time.perf_counter() - started) * 1000),
                    hosts.host_class(ctx),
                )

        return wrapper

    return deco


# --- shared API reads ------------------------------------------------------------

_OPTIONS_TTL_S = 600.0
_OPTIONS_MAX = 256
_options_cache: dict[tuple[str, str], tuple[float, dict]] = {}


async def _options(slug: str | None, locale: str) -> dict | None:
    """``/drugs/{slug}/options``, cached 10 min per (slug, language); None on any
    failure (the options are a convenience — the prices answer stands without)."""
    if not valid_slug(slug):
        return None
    key = (slug, locale)
    now = time.monotonic()
    if (hit := _options_cache.get(key)) is not None and now - hit[0] < _OPTIONS_TTL_S:
        return hit[1]
    try:
        data = await client().get(slug_path("/drugs/{}/options", slug), {"locale": locale})
    except FinerxApiError:
        return None
    if len(_options_cache) >= _OPTIONS_MAX:
        _options_cache.pop(next(iter(_options_cache)))
    _options_cache[key] = (now, data)
    return data


async def _base_card(locale: str, channel: str) -> dict[str, Any]:
    return await card_law.base_card(client(), locale, channel)


async def _hit_for(text: Any, locale: str) -> dict[str, Any] | None:
    """The catalog drug for what the model passed — ``{slug, name, kind}``: the
    text itself when it IS a slug, else the site search's top hit for it — the
    free text travels in the QUERY string (``/drugs/search?q=``), never in a
    path. None when nothing matches. Raises ``FinerxApiError`` when the search
    itself fails (and the text is not slug-shaped)."""
    if not isinstance(text, str) or not text.strip():
        return None
    # A plain name can LOOK like a slug ("atorvastatin") while the catalog slug
    # is "atorvastatin-calcium" — taking it verbatim 404'd the card price. So the
    # text always goes through search; it is kept as-is only when search returns
    # that very slug (or search is down and it is at least slug-shaped).
    slug = valid_slug(text)
    query = text.strip()[:200]
    try:
        data = await client().get(
            "/drugs/search", {"q": query.replace("-", " ") if slug else query, "limit": 5, "locale": locale}
        )
    except FinerxApiError:
        if slug:
            return {"slug": slug, "name": None, "kind": None}
        raise
    hits = [
        {"slug": r["slug"], "name": r.get("name"), "kind": r.get("kind")}
        for r in data.get("results") or []
        if isinstance(r, dict) and valid_slug(r.get("slug"))
    ]
    for hit in hits:
        if slug and hit["slug"] == slug:
            return hit
    if hits:
        return hits[0]
    return {"slug": slug, "name": None, "kind": None} if slug else None


async def _slug_for(text: Any, locale: str) -> str | None:
    """``_hit_for`` reduced to the slug."""
    hit = await _hit_for(text, locale)
    return hit["slug"] if hit else None


_ZIP_RE = re.compile(r"^\s*(\d{5})(?:-\d{4})?\s*$")


def _clean_zip(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    m = _ZIP_RE.match(raw)
    return m.group(1) if m else None


def _suggestions_text(query: str, exc: FinerxApiError, locale: str = "en") -> tuple[str, list[dict]]:
    sugg = [s for s in (exc.payload.get("suggestions") or []) if isinstance(s, dict)]
    if sugg:
        names = "; ".join(f"{s.get('name')} (slug {s.get('slug')})" for s in sugg[:5])
        return tr(locale, "closeMatches", query=query, names=names), sugg
    return tr(locale, "noMatch", query=query), []


def _api_error_text(exc: FinerxApiError, locale: str = "en") -> str:
    if exc.status_code == 429:
        return tr(locale, "busy")
    return tr(locale, "loadFailed")


def _zip_given(raw: Any) -> bool:
    """The model passed SOMETHING as a ZIP (a person named one)."""
    return isinstance(raw, str) and bool(raw.strip())


def _zip_notice(locale: str) -> dict[str, str]:
    """A ZIP the person gave that is not 5 digits: said plainly, and never
    silently replaced by the host's approximate location."""
    return {"code": "zip_invalid", "message": tr(locale, "zipInvalid")}


_WHERE_MAX = 200  # = the API's limit on ``address``
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _clean_where(raw: Any) -> str | None:
    """The place typed in the card's "where" field (a ZIP, a city, an address),
    tidied for ONE request body — or None. Never logged, echoed or stored."""
    if not isinstance(raw, str):
        return None
    text = " ".join(_CONTROL.sub(" ", raw).split())[:_WHERE_MAX].strip()
    return text or None


def _where_notice(locale: str) -> dict[str, str]:
    """A typed place the API could not place: the view is drawn (national
    prices / no stores) and says why — the text itself is not repeated."""
    return {"code": "where_not_found", "message": tr(locale, "whereNotFound")}


def _unplaced(origin: Any) -> bool:
    return not isinstance(origin, dict) or origin.get("precision") in (None, "none")


async def _view_failure(view: str, text: str, code: str, locale: str, channel: str) -> CallToolResult:
    """An envelope with no data and an ``error``: the widget shows its error state
    with the card strip; the model reads why."""
    card_view = card_law.to_view(await _base_card(locale, channel), locale=locale)
    structured = views.envelope(
        view, locale=locale, direction=hosts.text_dir(locale), card=card_view, data=None, error={"code": code}
    )
    return _result(text, structured, locale=locale, channel=channel, ui=True)


# --- prices ----------------------------------------------------------------------

_VIEW_OF = {
    "compare_prices": "prices",
    "ui_prices": "prices",
    "find_nearby_pharmacies": "pharmacies",
    "ui_nearby": "pharmacies",
    "get_savings_card": "card",
    "open_price_finder": "search",
    "find_us_equivalent": "equivalent",
    "ui_equivalent": "equivalent",
    "get_prescription_options": "rx",
}


# A model often puts the dose into the name ("atorvastatin 20 mg", "Adderall
# 20mg 60 tablets") instead of the `strength`/`quantity` arguments. Without this
# the API picks the default package and the answer quotes the wrong dose.
_STRENGTH_IN_TEXT = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*(mcg|mg|g|ml|iu|units?|%)"
    r"(?:\s*/\s*((?:\d+(?:\.\d+)?)?\s*(?:ml|l)))?(?![\w])",
    re.IGNORECASE,
)
_QTY_IN_TEXT = re.compile(
    r"(?:(?<![\w.])[x#]\s*(\d{1,4})(?![\w.])|(?<![\w.])(\d{1,4})\s*(?:tabs?|tablets?|caps?|capsules?|pills?|count|ct)\b)",
    re.IGNORECASE,
)


def _split_drug_text(
    drug: str, strength: str | None, quantity: int | None
) -> tuple[str, str | None, int | None]:
    """Pull a dose / pack size out of a free-text medicine name when the explicit
    arguments are empty; the name keeps whatever is left ("atorvastatin 20 mg 90
    tablets" → ("atorvastatin", "20 mg", 90)). Slugs and plain names pass through."""
    text_ = drug
    if quantity is None:
        m = _QTY_IN_TEXT.search(text_)
        if m:
            quantity = int(m.group(1) or m.group(2))
            text_ = text_[: m.start()] + " " + text_[m.end():]
    if not strength:
        m = _STRENGTH_IN_TEXT.search(text_)
        if m:
            strength = f"{m.group(1)} {m.group(2).lower()}"
            if m.group(3):
                strength += "/" + "".join(m.group(3).lower().split())
            text_ = text_[: m.start()] + " " + text_[m.end():]
    cleaned = " ".join(text_.replace(",", " ").split())
    return (cleaned or drug), strength, quantity


async def _prices_answer(
    ctx: Any,
    *,
    drug: str,
    form: str | None,
    strength: str | None,
    quantity: int | None,
    zip: str | None,
    locale: str,
    channel: str,
    legacy: dict | None = None,
    where: str | None = None,
) -> CallToolResult:
    """The whole "how much is X near me" answer: one ``POST /prices/near``, the
    options for the chips, the card with the price that answer found.

    The place, in this order: a valid ``zip``; ``where`` (a place typed in the
    card — a ZIP in it travels as ``zip``, anything else as the body's
    ``address``, which the API geocodes and drops); nothing when a malformed ZIP
    was given; else the host's approximate location."""
    body: dict[str, Any] = {
        "drug": drug,
        "form": form,
        "strength": strength,
        "quantity": quantity,
        "locale": locale,
        "channel": channel,
    }
    typed = None if _clean_zip(zip) else _clean_where(where)
    zip_bad = not typed and _zip_given(zip) and _clean_zip(zip) is None
    if z := _clean_zip(zip):
        body["zip"] = z
    elif typed and (tz := _clean_zip(typed)):
        body["zip"] = tz
    elif typed:
        body["address"] = typed
    elif not zip_bad and (here := hosts.user_location(ctx)) is not None:
        # Rounded to 0.01° already; used for this one request only. Never when
        # the person named a ZIP, even a malformed one: they asked about THAT
        # place, and a location they did not give would answer another.
        body["lat"], body["lon"] = here.lat, here.lon
    direction = hosts.text_dir(locale)
    base = await _base_card(locale, channel)
    try:
        near = await client().post("/prices/near", body)
    except FinerxApiError as exc:
        restricted = card_law.is_restricted(drug)
        card_view = card_law.to_view(base, locale=locale, restricted=restricted)
        if exc.status_code == 404:
            text, sugg = _suggestions_text(drug, exc, locale)
            error = {"code": "drug_not_found", "suggestions": sugg}
        else:
            text, error = _api_error_text(exc, locale), {"code": "api_unavailable"}
        structured = views.envelope(
            "prices", locale=locale, direction=direction, card=card_view, data=None, error=error
        )
        return _result(text, structured, locale=locale, channel=channel, ui=True)

    d = near.get("drug") or {}
    options = await _options(d.get("slug"), locale)
    restricted = card_law.is_restricted(d.get("slug"), d.get("name"), drug)
    card_view = card_law.to_view(
        card_law.merge_api_card(near.get("card"), base), locale=locale, restricted=restricted
    )
    data, all_rows = views.prices_data(near, options)
    text = views.prices_text(near, restricted=restricted, locale=locale)
    notice = None
    if zip_bad:
        # No place was sent, so the API answered nationally with needsZip.
        data["needsZip"] = True
        notice = _zip_notice(locale)
        text = f"{notice['message']}\n{text}"
    elif "address" in body and _unplaced(near.get("origin")):
        # The typed place could not be placed: national prices, and why.
        data["needsZip"] = True
        notice = _where_notice(locale)
        text = f"{notice['message']}\n{text}"
    structured = views.envelope(
        "prices", locale=locale, direction=direction, card=card_view, data=data, notice=notice
    )
    if legacy is not None:
        structured["programOffers"] = legacy.get("offers")
        text += "\n" + legacy["text"]
    return _result(
        text,
        structured,
        locale=locale,
        channel=channel,
        ui=True,
        meta={"finerx/allChains": all_rows},
    )


async def _legacy_package(ndc: str, quantity: int | None) -> tuple[dict, dict | None]:
    """1.x called compare_prices with an NDC. Resolve it to the drug + package it
    names (``/prices/compare`` product block); the program offers on that answer
    are used ONLY when the feed flag is on."""
    data = await client().get("/prices/compare", {"ndc": ndc, "quantity": quantity})
    product = data.get("product") or {}
    legacy = None
    if competitor_prices_enabled():
        offers = [
            {
                "pharmacy": o.get("pharmacy"),
                "savingsProgram": o.get("savingsProgram"),
                "price": o.get("price"),
                "observedAt": o.get("observedAt"),
            }
            for o in data.get("offers") or []
        ]
        lines = [
            f"- {o['pharmacy']} via {o['savingsProgram']}: {views.money(o['price'])}, observed {o['observedAt']}"
            for o in offers[:3]
            if o.get("price") is not None
        ]
        legacy = {"offers": offers, "text": "Other programs' prices for this NDC:\n" + "\n".join(lines)}
    return product, legacy


# --- tools: prices, places, the card ------------------------------------------------

_PRICES_META: dict[str, Any] = {
    "ui": {"resourceUri": APP_URI},
    "openai/outputTemplate": APP_URI,
    "openai/toolInvocation/invoking": "Checking card prices…",
    "openai/toolInvocation/invoked": "Card prices ready",
}
_PHARMACIES_META: dict[str, Any] = {
    "ui": {"resourceUri": APP_URI},
    "openai/outputTemplate": APP_URI,
    "openai/toolInvocation/invoking": "Finding pharmacies nearby…",
    "openai/toolInvocation/invoked": "Pharmacies nearby",
}
_CARD_META: dict[str, Any] = {
    "ui": {"resourceUri": APP_URI},
    "openai/outputTemplate": APP_URI,
    "openai/toolInvocation/invoking": "Getting your free FineRx card…",
    "openai/toolInvocation/invoked": "Here is your free FineRx card",
}
# The 2.1 views (search / equivalent / rx) under their own uri — see
# widget.APP_URI_V21: a host holding the 2.0 HTML for APP_URI cannot draw them.
_SEARCH_META: dict[str, Any] = {
    "ui": {"resourceUri": APP_URI_V21},
    "openai/outputTemplate": APP_URI_V21,
    "openai/toolInvocation/invoking": "Opening the FineRx search…",
    "openai/toolInvocation/invoked": "FineRx search is open",
}
_EQUIVALENT_META: dict[str, Any] = {
    "ui": {"resourceUri": APP_URI_V21},
    "openai/outputTemplate": APP_URI_V21,
    "openai/toolInvocation/invoking": "Looking up the US name…",
    "openai/toolInvocation/invoked": "US name found",
}
_RX_META: dict[str, Any] = {
    "ui": {"resourceUri": APP_URI_V21},
    "openai/outputTemplate": APP_URI_V21,
    "openai/toolInvocation/invoking": "Finding routes to a prescription…",
    "openai/toolInvocation/invoked": "Routes to a prescription",
}
# App-only: the widget calls these, the model never sees them, and they carry no
# template (a template on every call would re-render the iframe each time).
# ``openai/visibility: private`` is the Apps SDK's own key for the same (kept
# beside the standard one, like ``openai/widgetAccessible``).
_APP_ONLY_META: dict[str, Any] = {
    "ui": {"visibility": ["app"]},
    "openai/widgetAccessible": True,
    "openai/visibility": "private",
}
# The widget sends the card by email from inside itself, so the app must be
# allowed to call this one too.
_EMAIL_META: dict[str, Any] = {
    "ui": {"visibility": ["model", "app"]},
    "openai/widgetAccessible": True,
}


@mcp.tool(
    annotations=ToolAnnotations(title="Card prices near a place", **_READ_HINTS),
    meta=_PRICES_META,
    structured_output=False,
)
@_guarded("model")
async def compare_prices(
    drug: str | None = None,
    strength: str | None = None,
    form: str | None = None,
    quantity: int | None = None,
    zip: str | None = None,
    ndc: str | None = None,
    locale: str | None = None,
    channel: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """Price of one medicine with the free FineRx card at US pharmacy chains, near a place.

    Use when the person asks what a medicine costs, where it costs less, or its
    price near them or in a ZIP code. ``drug`` is a name as typed or a slug from
    search_drugs; ``strength`` ("10 mg"), ``form`` ("tablet") and ``quantity``
    are optional (the package with the most chains priced is used). ``zip`` is a
    5-digit US ZIP — pass it only when the person gave one; without it the host's
    approximate location is used when there is one, else the answer is national
    and asks for a ZIP. ``ndc`` (+ ``quantity``) is accepted for older callers.

    Returns the package, every chain's card price with its observation date
    (Walmart per state), the nearest store of each chain with a store nearby,
    chains with a card price but no store nearby, coverage (``other_quantities``
    lists the pack sizes that were seen), and the card: codes, the dated price
    with the card, and the card sentence.

    Next: quote each price with its date and chain; say the price is set per
    chain; then the card sentence and codes.
    """
    loc = hosts.resolve_locale(locale, ctx)
    chan = _channel(channel, ctx)
    legacy = None
    if not drug and ndc:
        try:
            product, legacy = await _legacy_package(ndc, quantity)
        except FinerxApiError as exc:
            if exc.status_code not in (404, 422):
                return await _view_failure("prices", _api_error_text(exc, loc), "api_unavailable", loc, chan)
            product = {}
        drug = product.get("drugSlug") or product.get("drugName")
        strength = strength or product.get("strength")
        form = form or product.get("form")
        if quantity is None and product.get("quantity"):
            quantity = int(product["quantity"])
    if not drug:
        return await _view_failure("prices", tr(loc, "drugRequired"), "drug_required", loc, chan)
    if legacy is None:
        drug, strength, quantity = _split_drug_text(drug, strength, quantity)
    return await _prices_answer(
        ctx,
        drug=drug,
        form=form,
        strength=strength,
        quantity=quantity,
        zip=zip,
        locale=loc,
        channel=chan,
        legacy=legacy,
    )


@mcp.tool(
    annotations=ToolAnnotations(title="Refresh the prices card", **_READ_HINTS),
    meta=_APP_ONLY_META,
    structured_output=False,
)
@_guarded("ui")
async def ui_prices(
    slug: str,
    form: str | None = None,
    strength: str | None = None,
    quantity: int | None = None,
    zip: str | None = None,
    where: str | None = None,
    locale: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """Card prices for another dose, quantity or place — called by the FineRx card itself.

    Same answer as compare_prices, for the package and place picked inside the
    card. ``where`` is the place as typed in the card (a ZIP, a city or an
    address): used for this one request, never stored. Not for the model.
    """
    loc = hosts.resolve_locale(locale, ctx)
    return await _prices_answer(
        ctx,
        drug=slug,
        form=form,
        strength=strength,
        quantity=quantity,
        zip=zip,
        where=where,
        locale=loc,
        channel=hosts.default_channel(ctx),
    )


def _families(*raw: Any) -> list[str]:
    out: list[str] = []
    for value in raw:
        if isinstance(value, str):
            out += [p.strip().lower() for p in value.split(",") if p.strip()]
    return list(dict.fromkeys(out))


def _coord(value: Any) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


async def _nearby_from_origin(origin: dict, families: list[str], limit: int) -> dict | None:
    """Stores around a place ``POST /geocode`` returned; None when it placed
    nothing. The origin shown is its ZIP / city / state — no coordinates."""
    precision = origin.get("precision")
    if precision not in ("address", "zip", "approx"):
        return None
    params: dict[str, Any] = {"limit": max(1, min(int(limit or 3), 10))}
    lat, lon = _coord(origin.get("lat")), _coord(origin.get("lon"))
    zip_ = _clean_zip(origin.get("zip"))
    if precision == "zip" and zip_:
        params["zip"] = zip_
    elif lat is not None and lon is not None:
        params["lat"], params["lon"] = lat, lon
    elif zip_:
        params["zip"] = zip_
    else:
        return None
    if families:
        params["family"] = ",".join(families)
    nearby = await client().get("/pharmacies/nearby", params)
    data = views.pharmacies_from_nearby(nearby, precision=precision)
    data["origin"] = {
        "zip": zip_,
        "city": origin.get("city"),
        "state": origin.get("state"),
        "precision": precision,
    }
    return data


async def _pharmacies_answer(
    ctx: Any,
    *,
    zip: str | None,
    families: list[str],
    drug: str | None,
    form: str | None,
    strength: str | None,
    quantity: int | None,
    limit: int,
    locale: str,
    channel: str,
    where: str | None = None,
) -> CallToolResult:
    direction = hosts.text_dir(locale)
    base = await _base_card(locale, channel)
    z = _clean_zip(zip)
    # A place typed in the card (app-only ``where``): a ZIP in it is a ZIP; any
    # other text goes once into a POST body (/prices/near or /geocode).
    typed = None if z else _clean_where(where)
    if typed and (tz := _clean_zip(typed)):
        z, typed = tz, None
    zip_bad = not typed and _zip_given(zip) and z is None
    # A malformed ZIP the person gave is answered as "no place" — never with
    # the host's approximate location instead.
    here = None if (z or zip_bad or typed) else hosts.user_location(ctx)
    restricted = card_law.is_restricted(drug)
    unplaced = False
    try:
        if drug:
            body: dict[str, Any] = {
                "drug": drug,
                "form": form,
                "strength": strength,
                "quantity": quantity,
                "locale": locale,
                "channel": channel,
            }
            if z:
                body["zip"] = z
            elif typed:
                body["address"] = typed
            elif here is not None:
                body["lat"], body["lon"] = here.lat, here.lon
            near = await client().post("/prices/near", body)
            d = near.get("drug") or {}
            restricted = restricted or card_law.is_restricted(d.get("slug"), d.get("name"))
            card = card_law.merge_api_card(near.get("card"), base)
            data = views.pharmacies_from_near(near, families)
            unplaced = bool(typed) and _unplaced(near.get("origin"))
        elif typed:
            # No drug: the typed place → POST /geocode (the text in the body,
            # once), then the stores around what came back — its ZIP, or its
            # point rounded to 0.01° (the API rounds too). The text itself goes
            # nowhere else.
            geo = (await client().post("/geocode", {"address": typed, "locale": locale})).get("origin") or {}
            card = base
            data = await _nearby_from_origin(geo, families, limit)
            unplaced = data is None
            if data is None:
                data = {"drug": None, "package": None, "origin": {"precision": "none"}, "stores": [], "families": []}
        elif z or here is not None:
            params: dict[str, Any] = {"limit": max(1, min(int(limit or 3), 10))}
            if z:
                params["zip"] = z
            else:
                params["lat"], params["lon"] = here.lat, here.lon  # type: ignore[union-attr]
            if families:
                params["family"] = ",".join(families)
            nearby = await client().get("/pharmacies/nearby", params)
            card = base
            data = views.pharmacies_from_nearby(nearby, precision="zip" if z else "approx")
        else:
            card = base
            data = {"drug": None, "package": None, "origin": {"precision": "none"}, "stores": [], "families": []}
    except FinerxApiError as exc:
        card_view = card_law.to_view(base, locale=locale, restricted=restricted)
        if exc.status_code == 404 and drug:
            text, sugg = _suggestions_text(drug, exc, locale)
            error = {"code": "drug_not_found", "suggestions": sugg}
        elif exc.status_code == 404:
            text, error = tr(locale, "zipNotFound"), {"code": "zip_not_found"}
        else:
            text, error = _api_error_text(exc, locale), {"code": "api_unavailable"}
        structured = views.envelope(
            "pharmacies", locale=locale, direction=direction, card=card_view, data=None, error=error
        )
        return _result(text, structured, locale=locale, channel=channel, ui=True)

    card_view = card_law.to_view(card, locale=locale, restricted=restricted)
    text = views.pharmacies_text(data, locale)
    notice = _zip_notice(locale) if zip_bad else _where_notice(locale) if unplaced else None
    if notice:
        text = f"{notice['message']}\n{text}"
    structured = views.envelope(
        "pharmacies", locale=locale, direction=direction, card=card_view, data=data, notice=notice
    )
    return _result(text, structured, locale=locale, channel=channel, ui=True)


@mcp.tool(
    annotations=ToolAnnotations(title="Find nearby pharmacies", **_READ_HINTS),
    meta=_PHARMACIES_META,
    structured_output=False,
)
@_guarded("model")
async def find_nearby_pharmacies(
    zip: str | None = None,
    family: str | None = None,
    drug: str | None = None,
    strength: str | None = None,
    form: str | None = None,
    quantity: int | None = None,
    chains: str | None = None,
    limit: int = 3,
    locale: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """Pharmacy stores within 30 miles, per chain — with the card price when a drug is given.

    Use when the person asks where the pharmacies are near a ZIP or near them.
    ``zip`` is a 5-digit US ZIP (leave it out to use the host's approximate
    location when there is one). ``family`` is a comma-separated list of chain
    codes: walmart, cvs, walgreens, kroger, albertsons, costco, publix, heb,
    hyvee, meijer, wegmans, shoprite, bigy, gianteagle, kinney (``chains`` is the
    older name of the same filter). With ``drug`` (+ optional strength, form,
    quantity) each store carries its chain's card price and observation date.

    Returns stores (chain, address, city, distance, whether it is a pharmacy or a
    store with a pharmacy inside — not verified) and the card. Stock is not
    visible: suggest calling ahead. Coordinates © OpenStreetMap contributors.
    """
    loc = hosts.resolve_locale(locale, ctx)
    return await _pharmacies_answer(
        ctx,
        zip=zip,
        families=_families(family, chains),
        drug=drug,
        form=form,
        strength=strength,
        quantity=quantity,
        limit=limit,
        locale=loc,
        channel=hosts.default_channel(ctx),
    )


@mcp.tool(
    annotations=ToolAnnotations(title="Refresh the pharmacies card", **_READ_HINTS),
    meta=_APP_ONLY_META,
    structured_output=False,
)
@_guarded("ui")
async def ui_nearby(
    zip: str | None = None,
    family: str | None = None,
    slug: str | None = None,
    form: str | None = None,
    strength: str | None = None,
    quantity: int | None = None,
    where: str | None = None,
    locale: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """Pharmacies near a place for the package on screen — called by the FineRx card itself.

    ``where`` is the place as typed in the card (a ZIP, a city or an address):
    used for this one request, never stored. Not for the model.
    """
    loc = hosts.resolve_locale(locale, ctx)
    return await _pharmacies_answer(
        ctx,
        zip=zip,
        families=_families(family),
        drug=slug,
        form=form,
        strength=strength,
        quantity=quantity,
        limit=3,
        locale=loc,
        channel=hosts.default_channel(ctx),
        where=where,
    )


# --- the search (MCP 2.1): a card where the person types the medicine -------------

# "Often searched" in the search view: eight of the most-prescribed medicines
# in the catalog (by prescription volume), none of them controlled or
# age-restricted (checked against card_law in the tests).
POPULAR: tuple[tuple[str, str], ...] = (
    ("atorvastatin-calcium", "Atorvastatin"),
    ("amlodipine-besylate", "Amlodipine"),
    ("levothyroxine-sodium", "Levothyroxine"),
    ("metformin-hcl", "Metformin"),
    ("omeprazole", "Omeprazole"),
    ("estradiol", "Estradiol"),
    ("sildenafil-citrate", "Sildenafil"),
    ("finasteride", "Finasteride"),
)
_QUERY_MIN, _QUERY_MAX = 2, 100  # = the API's bounds on ``q``


def _popular() -> list[dict[str, str]]:
    return [{"slug": slug, "name": name} for slug, name in POPULAR if not card_law.is_restricted(slug, name)]


def _query(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    text = " ".join(_CONTROL.sub(" ", raw).split())[:_QUERY_MAX]
    return text or None


def _suggestions_restricted(q: str | None, results: list[dict], foreign: list[dict]) -> bool:
    """The card law drops its adjectives when ANY suggestion is a restricted
    medicine — typed text alone misses "oxy" → Oxycodone, "adder" → Adderall."""
    if card_law.is_restricted(q):
        return True
    for r in results:
        if card_law.is_restricted(r.get("slug"), r.get("name"), r.get("matchedAlias")):
            return True
    for b in foreign:
        if card_law.is_restricted(b.get("usSlug"), b.get("usName"), b.get("brand")):
            return True
    return False


async def _suggest(q: str, locale: str) -> tuple[list[dict], list[dict]]:
    """``GET /drugs/suggest`` → (results, foreignBrands); raises FinerxApiError."""
    data = await client().get("/drugs/suggest", {"q": q, "limit": views.MAX_SUGGESTIONS, "locale": locale})
    return views.suggest_lists(data)


@mcp.tool(
    annotations=ToolAnnotations(title="Open the FineRx price finder", **_READ_HINTS),
    meta=_SEARCH_META,
    structured_output=False,
)
@_guarded("model")
async def open_price_finder(
    query: str | None = None,
    locale: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """Open the FineRx search inside the card, so the person can look a medicine up themselves.

    Use when the person asks to open FineRx, wants to search or browse on their
    own, or is not sure of the name. Optional ``query`` pre-fills the search
    (a medicine, a brand from another country, a misspelling). The card then
    suggests matches as they type, each with where its card prices start and
    the date, and a pick shows card prices by chain near a place they choose.

    Returns the matches for ``query`` (if any), foreign brands that matched,
    a few often-searched medicines, and the card. What the person picks in the
    card reaches you as context. Hosts without MCP Apps get the matches as text.
    """
    loc = hosts.resolve_locale(locale, ctx)
    chan = hosts.default_channel(ctx)
    base = await _base_card(loc, chan)
    q = _query(query)
    q = q if q and len(q) >= _QUERY_MIN else None
    results: list[dict] = []
    foreign: list[dict] = []
    if q:
        try:
            results, foreign = await _suggest(q, loc)
        except FinerxApiError:
            pass  # the search still opens; the person types again
    popular = _popular()
    restricted = _suggestions_restricted(q, results, foreign)
    card_view = card_law.to_view(base, locale=loc, restricted=restricted)
    data = {"query": q, "suggestions": results, "foreignBrands": foreign, "popular": popular, "origin": None}
    structured = views.envelope("search", locale=loc, direction=hosts.text_dir(loc), card=card_view, data=data)
    text = views.search_text(q, results, foreign, popular, loc)
    return _result(text, structured, locale=loc, channel=chan, ui=True)


@mcp.tool(
    annotations=ToolAnnotations(title="Suggest medicines as you type", **_READ_HINTS),
    meta=_APP_ONLY_META,
    structured_output=False,
)
@_guarded("suggest")
async def ui_suggest(
    q: str,
    locale: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """Medicines matching what the person is typing in the FineRx search — called by the card itself.

    Up to eight matches with where their card prices start (dated), and foreign
    brands that matched. Not for the model.
    """
    loc = hosts.resolve_locale(locale, ctx)
    chan = hosts.default_channel(ctx)
    base = await _base_card(loc, chan)
    text_q = _query(q)
    results: list[dict] = []
    foreign: list[dict] = []
    failed = False
    if text_q and len(text_q) >= _QUERY_MIN:
        try:
            results, foreign = await _suggest(text_q, loc)
        except FinerxApiError:
            failed = True
    # The widget draws THIS card under the results (a restricted medicine among
    # them → the law without its adjectives).
    card_view = card_law.to_view(base, locale=loc, restricted=_suggestions_restricted(text_q, results, foreign))
    structured: dict[str, Any] = {"results": results, "foreignBrands": foreign, "card": card_view}
    if failed:
        structured["error"] = {"code": "api_unavailable"}
        text = tr(loc, "loadFailed")
    else:
        text = views.search_text(text_q, results, foreign, [], loc) if text_q else tr(loc, "searchOpened")
    # No labels: this runs on every keystroke, and the card already holds them
    # from the answer that opened the search (4-6 KB per call otherwise).
    result = _result(text, structured, locale=loc, channel=chan, ui=False)
    # The search field shows "that didn't load" on an error result; the model
    # never sees this tool.
    result.isError = failed
    return result


# The PNG is the same image for everyone, so it is fetched once per PROCESS and
# kept as bytes. Keyed by URL (it carries the channel) and CAPPED — `channel` is
# caller-supplied on a public endpoint.
_IMAGE_CACHE_MAX = 4
_image_cache: dict[str, bytes] = {}


async def _card_image_bytes(url: str) -> bytes | None:
    """Fetch (once) the card PNG. None on ANY failure — the codes are the useful
    part; a failure is not cached so a blip does not disable it for good. A
    separate client: the API key never travels to the image host."""
    if (hit := _image_cache.get(url)) is not None:
        return hit
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=2.0)) as http:
            resp = await http.get(url, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        data = resp.content
    except Exception:
        return None
    if not data:
        return None
    if len(_image_cache) < _IMAGE_CACHE_MAX:
        _image_cache[url] = data
    return data


@mcp.tool(
    annotations=ToolAnnotations(title="Get the free FineRx savings card", **_READ_HINTS),
    meta=_CARD_META,
    # The result can carry an image block; FastMCP cannot serialise that as
    # structured output, so the CallToolResult is built by hand.
    structured_output=False,
)
@_guarded("model")
async def get_savings_card(
    locale: str | None = None,
    channel: str | None = None,
    drug: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """The free FineRx discount card: its codes, how to use it, how to keep it.

    Use when the person asks for the card, how to pay less at the pharmacy, or
    right after you quoted a card price. Optional ``drug`` (a slug from
    search_drugs) adds that drug's card price for its most-priced package, with
    the date it was observed. ``locale`` is a language code (the host's own is
    used when left out).

    Returns the three codes to read at the counter, the steps, the sentence to
    say to the pharmacist, the links to the card page and the printable sheet,
    and the card sentence with the small print. Hosts with MCP Apps show it as an
    interactive card; write the three codes in your answer anyway. The card is
    free, needs no signup and is not insurance.
    """
    loc = hosts.resolve_locale(locale, ctx)
    chan = _channel(channel, ctx)
    base = await _base_card(loc, chan)
    card = base
    drug_ref: dict | None = None
    extra: list[str] = []
    restricted = card_law.is_restricted(drug)
    if drug:
        try:
            slug = await _slug_for(drug, loc)
            cp = (
                await client().get(slug_path("/drugs/{}/card-prices", slug), {"locale": loc, "channel": chan})
                if slug
                else None
            )
        except FinerxApiError:
            cp = None
        if not cp:
            extra.append(tr(loc, "noCardPriceFor", drug=drug))
        else:
            d = cp.get("drug") or {}
            drug_ref = {"slug": d.get("slug"), "name": d.get("name"), "kind": d.get("kind")}
            restricted = restricted or card_law.is_restricted(d.get("slug"), d.get("name"))
            card = card_law.merge_api_card(cp.get("card"), base)
            pwc = card.get("priceWithCard")
            if pwc:
                extra.append(
                    tr(
                        loc,
                        "cardPriceAt",
                        package=views.package_label(d, cp.get("package"), loc),
                        price=views.money(pwc["amount"]),
                        name=pwc.get("name") or pwc.get("family"),
                        date=pwc.get("observedAt"),
                    )
                )
            elif cov := views.coverage_text(cp.get("package"), cp.get("coverage"), loc):
                extra.append(cov)
    card_view = card_law.to_view(card, locale=loc, restricted=restricted)

    lines = [tr(loc, "cardTitle")]
    steps = base.get("howToUse") or []
    if steps:
        lines.append(tr(loc, "howToUse"))
        lines += [f"{i}. {s}" for i, s in enumerate(steps, 1)]
    if phrase := base.get("pharmacistPhrase"):
        lines.append(tr(loc, "sayAtCounter", phrase=phrase))
    if accepted := base.get("acceptedAt"):
        lines.append(accepted)
    lines.append(tr(loc, "cardLinks", site=card_view["siteUrl"], print=card_view["printUrl"]))
    lines += extra
    structured = views.envelope(
        "card",
        locale=loc,
        direction=hosts.text_dir(loc),
        card=card_view,
        data={"drug": drug_ref, "priceWithCard": card_view.get("priceWithCard")},
    )
    result = _result(
        "\n".join(lines), structured, locale=loc, channel=chan, ui=True
    )
    # A picture of the card only for hosts that draw no UI. Never to ChatGPT: an
    # image block counts against the Free plan's image quota (it paused a live
    # chat on 2026-09-09) and the widget draws the card anyway.
    if not hosts.ui_supported(ctx):
        image_url = base.get("imageUrl") or CARD_IMAGE_URL
        if (png := await _card_image_bytes(image_url)) is not None:
            result.content.append(
                ImageContent(type="image", data=base64.b64encode(png).decode("ascii"), mimeType="image/png")
            )
    return result


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
    429: "too many card emails right now — offer the printable card or the link instead, or try again later",
    502: "the email provider failed — offer the printable card or the link instead",
    503: "email delivery is not available right now — offer the printable card or the link instead",
}


@mcp.tool(
    annotations=ToolAnnotations(title="Email the savings card", **_EMAIL_HINTS),
    meta=_EMAIL_META,
    structured_output=False,
)
@_guarded("model")
async def email_savings_card(
    email: str,
    consent: bool = False,
    locale: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """Email the free FineRx discount card to an address the person gave you.

    Use ONLY after the person has given an email address AND confirmed they want
    the card sent there — ask for both first, then set ``consent`` to true. The
    message contains the card and nothing else; FineRx does not store the address.

    Returns ``sent`` true with the masked address, or ``sent`` false with the
    reason. On an error, say what happened and offer the printable card or the
    link instead. Do not retry a refusal or read the full address back.
    """
    loc = hosts.resolve_locale(locale, ctx)
    chan = hosts.default_channel(ctx)
    card_view = card_law.to_view(await _base_card(loc, chan), locale=loc)
    if consent is not True:
        # The gate lives here, not at the API: a send tool that can be called
        # without an explicit yes is a send tool that eventually will be.
        error = "consent required: ask the person to confirm they want the card emailed to this address"
        structured = {"sent": False, "error": error, "card": card_view}
        return _result(f"Not sent — {error}.", structured, locale=loc, channel=chan)
    # The hosted MCP reaches the API from ONE address, so the API's per-IP
    # hourly cap was a ceiling for every assistant user together. API 1.5.0
    # caps the MCP key per person instead: the HMAC of ``openai/subject`` (the
    # raw subject never leaves ``hosts``). No subject → no header (one shared
    # bucket at the old per-IP number).
    subject = hosts.subject_key(ctx)
    headers = {"X-FineRx-Subject": subject} if subject else None
    try:
        await client().post("/card/email", {"email": email, "locale": loc, "consent": True}, headers=headers)
    except FinerxApiError as exc:
        structured = {
            "sent": False,
            "error": _EMAIL_ERRORS.get(exc.status_code, "the card could not be sent right now"),
            "status": exc.status_code,
            "card": card_view,
        }
        if exc.status_code == 429 and exc.retry_after:
            structured["retryAfter"] = exc.retry_after
        text = f"Not sent — {structured['error']}."
        return _result(text, structured, locale=loc, channel=chan)
    masked = _mask_email(email)
    structured = {"sent": True, "to": masked, "card": card_view}
    return _result(
        tr(loc, "emailSent", to=masked), structured, locale=loc, channel=chan
    )


# --- tools: the catalog ------------------------------------------------------------

DATASET_TERMS = (
    "Card prices observed on the dates shown; the pharmacy sets the final price. "
    "Not insurance, not medical advice. Attribute as \"Prices via FineRx\"."
)
# The credit third-party data asks for (the API's /meta ``sourceAttributions``).
SOURCE_ATTRIBUTIONS = (
    "Pharmacy locations: © OpenStreetMap contributors (ODbL)",
    "Place names: GeoNames (CC BY 4.0)",
)

_SEARCH_PRICED = 5  # how many search hits get a card "from" price (one call each, cached)


def _from_line(fcp: dict | None, locale: str = "en") -> str:
    if not fcp:
        return tr(locale, "noCardPriceYet")
    return tr(
        locale, "fromLine", price=views.money(fcp["amount"]), package=fcp.get("package"), date=fcp.get("observedAt")
    )


@mcp.tool(annotations=ToolAnnotations(title="Search FineRx drugs", **_READ_HINTS), structured_output=False)
@_guarded("model")
async def search_drugs(
    query: str,
    limit: int = 10,
    locale: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """Find a medicine by name (brand, generic, misspelled or in another script) and get its slug.

    Returns candidates with ``slug`` (for get_drug and compare_prices), ``kind``
    (generic/brand) and ``fromCardPrice`` — where its card prices start: the
    amount, the package it is for and the observation date. ``foreignBrands``
    lists home-country brands that matched the same text (Нурофен, No-Spa): when
    ``results`` is empty and ``foreignBrands`` is not, call find_us_equivalent.
    Several candidates: ask which one — brand and generic are different products.
    """
    loc = hosts.resolve_locale(locale, ctx)
    chan = hosts.default_channel(ctx)
    base = await _base_card(loc, chan)
    try:
        data = await client().get(
            "/drugs/search", {"q": query, "limit": max(1, min(int(limit or 10), 20)), "locale": loc}
        )
    except FinerxApiError as exc:
        card_view = card_law.to_view(base, locale=loc)
        return _result(
            _api_error_text(exc, loc),
            {"error": {"code": "api_unavailable"}, "card": card_view},
            locale=loc,
            channel=chan,
        )
    raw = data.get("results") or []
    options = await asyncio.gather(*(_options(r.get("slug"), loc) for r in raw[:_SEARCH_PRICED]))
    feed = competitor_prices_enabled()
    results = []
    for i, r in enumerate(raw):
        item = {
            "name": r.get("name"),
            "slug": r.get("slug"),
            "kind": r.get("kind"),
            "fromCardPrice": views.from_card_price(options[i]) if i < len(options) else None,
        }
        if feed:
            item["fromPrice"] = r.get("fromPrice")
        results.append(item)
    brands = [
        {
            "brand": b.get("brand"),
            "brandSlug": b.get("brandSlug"),
            "countries": b.get("countries"),
            "inn": b.get("inn"),
            "usGeneric": b.get("usGeneric"),
        }
        for b in data.get("foreignBrands") or []
    ]
    restricted = bool(results) and card_law.is_restricted(results[0]["slug"], results[0]["name"])
    card_view = card_law.to_view(base, locale=loc, restricted=restricted)
    lines = [tr(loc, "searchHead", query=query, n=len(results))]
    for i, item in enumerate(results):
        tail = f" — {_from_line(item['fromCardPrice'], loc)}" if i < _SEARCH_PRICED else ""
        lines.append(f"- {item['name']} ({item['kind']}) — slug {item['slug']}{tail}")
    for b in brands:
        countries = ", ".join(b.get("countries") or [])
        lines.append("- " + tr(loc, "foreignBrandLine", brand=b["brand"], countries=countries, inn=b.get("inn")))
    structured = {
        "query": data.get("query", query),
        "count": len(results),
        "results": results,
        "foreignBrands": brands,
        "card": card_view,
    }
    return _result("\n".join(lines), structured, locale=loc, channel=chan)


@mcp.tool(annotations=ToolAnnotations(title="Get drug details", **_READ_HINTS), structured_output=False)
@_guarded("model")
async def get_drug(
    slug: str,
    locale: str | None = None,
    channel: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """Strengths, forms and pack sizes of one medicine that have a card price, and its default package.

    Use when you have a slug and need to know which strengths and quantities
    exist before quoting a price. Returns ``configs`` (strength × form, each
    with quantities, where the card prices for that pack start, with the date,
    and how many chains priced it), ``defaultConfig`` (the package the most chains
    price), ``fromCardPrice``, the card prices of the default package per chain,
    and the card. Next: compare_prices for the package the person takes.
    """
    loc = hosts.resolve_locale(locale, ctx)
    chan = _channel(channel, ctx)
    base = await _base_card(loc, chan)
    asked = slug
    try:
        target = await _slug_for(slug, loc)
    except FinerxApiError as exc:
        card_view = card_law.to_view(base, locale=loc, restricted=card_law.is_restricted(asked))
        return _result(
            _api_error_text(exc, loc),
            {"error": {"code": "api_unavailable"}, "card": card_view},
            locale=loc,
            channel=chan,
        )
    if target is None:
        card_view = card_law.to_view(base, locale=loc, restricted=card_law.is_restricted(asked))
        text = tr(loc, "noMatch", query=asked)
        return _result(
            text,
            {"error": {"code": "drug_not_found", "suggestions": []}, "card": card_view},
            locale=loc,
            channel=chan,
        )
    slug = target
    opts_task = _options(slug, loc)
    cp_task = client().get(slug_path("/drugs/{}/card-prices", slug), {"locale": loc, "channel": chan})
    options, cp = await asyncio.gather(opts_task, cp_task, return_exceptions=True)
    if isinstance(cp, FinerxApiError):
        card_view = card_law.to_view(base, locale=loc, restricted=card_law.is_restricted(slug))
        if cp.status_code == 404:
            text, sugg = _suggestions_text(slug, cp, loc)
            error: dict[str, Any] = {"code": "drug_not_found", "suggestions": sugg}
        else:
            text, error = _api_error_text(cp, loc), {"code": "api_unavailable"}
        return _result(
            text, {"error": error, "card": card_view}, locale=loc, channel=chan
        )
    if isinstance(cp, BaseException):
        raise cp
    options = options if isinstance(options, dict) else None
    d = cp.get("drug") or {}
    restricted = card_law.is_restricted(slug, d.get("slug"), d.get("name"))
    card_view = card_law.to_view(card_law.merge_api_card(cp.get("card"), base), locale=loc, restricted=restricted)
    trimmed = views.trim_options(options)
    fcp = views.from_card_price(options)
    chains = (cp.get("chains") or [])[: views.INLINE_ROWS]
    lines = [f"**{d.get('name') or slug}** ({d.get('kind') or 'drug'}) — slug {d.get('slug') or slug}"]
    if trimmed:
        forms = "; ".join(
            f"{c.get('label')} ({', '.join(str(q['quantity']) for q in c['quantities'])})" for c in trimmed["configs"]
        )
        lines.append(tr(loc, "strengthsLine", forms=forms))
    else:
        lines.append(tr(loc, "noCardPriceAny"))
    if fcp:
        lines.append(
            tr(loc, "cardFromLine", price=views.money(fcp["amount"]), package=fcp.get("package"), date=fcp.get("observedAt"))
        )
    package = cp.get("package") or {}
    if package.get("label"):
        lines.append(tr(loc, "defaultPackage", label=package["label"]))
        for c in chains[: views.TEXT_ROWS]:
            lines.append(f"- {views.chain_name(c, loc)}: {views.dated(c.get('price'), loc) or tr(loc, 'noPriceShort')}")
    if cov := views.coverage_text(package, cp.get("coverage"), loc):
        lines.append(cov)
    structured = {
        "name": d.get("name"),
        "slug": d.get("slug") or slug,
        "kind": d.get("kind"),
        "configs": (trimmed or {}).get("configs", []),
        "defaultConfig": (options or {}).get("defaultConfig"),
        "fromCardPrice": fcp,
        "defaultPackage": {"package": package, "coverage": cp.get("coverage"), "chains": chains},
        "card": card_view,
    }
    return _result("\n".join(lines), structured, locale=loc, channel=chan)


@mcp.tool(annotations=ToolAnnotations(title="FineRx dataset info", **_READ_HINTS), structured_output=False)
@_guarded("model")
async def get_dataset_info(ctx: Context | None = None) -> CallToolResult:
    """What FineRx covers: pharmacy chains with card prices, how fresh they are, stores on the map, terms.

    Use when the person asks what FineRx is, how big or current the data is, or
    how to cite it. Returns the pharmacy chain families we hold card prices for,
    their store banners, the newest observation date, how many stores we can
    place on a map, the catalog size, and the attribution terms.
    """
    try:
        chains, meta = await asyncio.gather(client().get("/chains"), client().get("/meta"))
    except FinerxApiError as exc:
        return _result(
            _api_error_text(exc).split(" The card")[0],
            {"error": {"code": "api_unavailable"}},
            locale="en",
            channel="mcp",
            card=False,
        )
    fams = chains.get("chains") or []
    ds = meta.get("dataset") or {}
    info = {
        "families": len(fams),
        "banners": sum(len(f.get("banners") or []) for f in fams),
        "familiesWithStores": sum(1 for f in fams if f.get("hasGeo")),
        "storesOnMap": sum(int(f.get("storeCount") or 0) for f in fams),
        "asOf": chains.get("asOf"),
        "drugs": ds.get("drugs"),
        "chains": [{"code": f.get("code"), "name": f.get("name"), "priceZones": f.get("priceZones")} for f in fams],
        "attribution": meta.get("attribution"),
        "sourceAttributions": meta.get("sourceAttributions") or list(SOURCE_ATTRIBUTIONS),
        # Our own line, not the API's ``meta.disclaimer``: that one describes the
        # third-party program feed, which 2.0 does not serve.
        "terms": DATASET_TERMS,
    }
    text = (
        f"FineRx holds prices observed with the free FineRx card for {info['families']} pharmacy chain families "
        f"({info['banners']} store banners); newest observation {info['asOf']}. "
        f"{info['storesOnMap']} stores of {info['familiesWithStores']} families are on the map "
        f"(© OpenStreetMap contributors, ODbL); place names: GeoNames (CC BY 4.0). "
        f"The catalog has {info['drugs']} medicines. "
        "Prices are observed estimates with their dates, not medical advice. Attribute as “Prices via FineRx”."
    )
    return _result(text, info, locale="en", channel="mcp", card=False)


async def _drug_ref(text: Any, locale: str) -> tuple[dict | None, dict | None]:
    """What the model named → (``{slug, name, kind}`` for a view, the drug's
    ``/options``) — both None when nothing matched or the API is down. Free
    text goes only into the search query."""
    try:
        hit = await _hit_for(text, locale)
    except FinerxApiError:
        return None, None
    if not hit:
        return None, None
    options = await _options(hit["slug"], locale)
    d = (options or {}).get("drug") or {}
    name = d.get("name") or hit.get("name")
    if not name:
        return None, options
    return {"slug": d.get("slug") or hit["slug"], "name": name, "kind": d.get("kind") or hit.get("kind")}, options


@mcp.tool(
    annotations=ToolAnnotations(title="How to get a prescription", **_READ_HINTS),
    meta=_RX_META,
    structured_output=False,
)
@_guarded("model")
async def get_prescription_options(
    locale: str | None = None,
    drug: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """Routes to filling a prescription, including having none yet.

    Use when the person says they have no prescription, asks how to get one, or
    says the brand costs too much. Optional ``drug`` is a slug from
    search_drugs (a name works too). Returns three sections — havePrescription
    (steps), noPrescription (clinics and telehealth, each with the disclosure
    to read out when FineRx earns anything), brandCostly — plus a Medicaid
    note, where the drug's card prices start (dated), and the card. For
    controlled or age-restricted medicines it returns only ``restricted:
    true``: FineRx shows card prices and the card for them, nothing else. Not
    medical advice: never say what to take or at what dose.
    """
    loc = hosts.resolve_locale(locale, ctx)
    chan = hosts.default_channel(ctx)
    direction = hosts.text_dir(loc)
    base = await _base_card(loc, chan)
    drug_ref, options = await _drug_ref(drug, loc) if drug else (None, None)
    restricted = card_law.is_restricted(drug) or bool(
        drug_ref and card_law.is_restricted(drug_ref["slug"], drug_ref["name"])
    )
    if restricted:
        card_view = card_law.to_view(base, locale=loc, restricted=True)
        note = tr(loc, "restrictedRx")
        legacy = {"locale": loc, "drug": drug, "restricted": True, "note": note, "card": card_view}
        data = {
            "drug": drug_ref,
            "restricted": True,
            "note": note,
            "sections": [],
            "cardFrom": None,
            "readerLocale": loc,
        }
        structured = {
            **legacy,
            **views.envelope("rx", locale=loc, direction=direction, card=card_view, data=data),
        }
        return _result(note, structured, locale=loc, channel=chan, ui=True)
    try:
        api = await client().get("/prescription-options", {"locale": loc, "drug": drug})
    except FinerxApiError as exc:
        card_view = card_law.to_view(base, locale=loc)
        error = {"code": "api_unavailable"}
        structured = {
            "error": error,
            "card": card_view,
            **views.envelope("rx", locale=loc, direction=direction, card=card_view, data=None, error=error),
        }
        return _result(_api_error_text(exc, loc), structured, locale=loc, channel=chan, ui=True)
    card_view = card_law.to_view(base, locale=loc)
    fcp = views.from_card_price(options)
    lines: list[str] = []
    have = api.get("havePrescription") or {}
    if have.get("summary"):
        lines.append(f"**{tr(loc, 'havePrescription')}** {have['summary']}")
        lines += [f"{i}. {s}" for i, s in enumerate(have.get("steps") or [], 1)]
    none = api.get("noPrescription") or {}
    if none.get("summary"):
        lines.append(f"**{tr(loc, 'noPrescription')}** {none['summary']}")
        for opt in none.get("options") or []:
            disclosure = f" ({opt['disclosure']})" if opt.get("disclosure") else ""
            lines.append(f"- {opt.get('name')}: {opt.get('note') or ''}{disclosure}".rstrip())
    costly = api.get("brandCostly") or {}
    if costly.get("summary"):
        lines.append(f"**{tr(loc, 'brandCostly')}** {costly['summary']}")
        for opt in costly.get("options") or []:
            lines.append(f"- {opt.get('name')}: {opt.get('note') or ''}".rstrip())
    if note := api.get("medicaidNote"):
        lines.append(note)
    if fcp:
        lines.append(
            tr(loc, "rxCardFrom", price=views.money(fcp["amount"]), package=fcp.get("package"), date=fcp.get("observedAt"))
        )
    legacy = {
        "locale": api.get("locale", loc),
        "drug": api.get("drug"),
        "restricted": False,
        "havePrescription": api.get("havePrescription"),
        "noPrescription": api.get("noPrescription"),
        "brandCostly": api.get("brandCostly"),
        "medicaidNote": api.get("medicaidNote"),
        "disclaimer": api.get("disclaimer"),
        "card": card_view,
    }
    data = {
        "drug": drug_ref,
        "restricted": False,
        "note": None,
        "sections": views.rx_sections(api, loc),
        "cardFrom": views.dated_price(fcp),
        # The reader's language (the widget's labels, numbers and dates): the
        # top-level ``locale`` keeps its 2.0 meaning — the API's content
        # language (en/es) — so the 2.0 fields win over the envelope's.
        "readerLocale": loc,
    }
    structured = {**views.envelope("rx", locale=loc, direction=direction, card=card_view, data=data), **legacy}
    return _result("\n".join(lines) or tr(loc, "noOptions"), structured, locale=loc, channel=chan, ui=True)


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


async def _equivalent_answer(
    data: dict[str, Any],
    others: list[dict[str, Any]],
    *,
    loc: str,
    chan: str,
    base: dict[str, Any],
) -> CallToolResult:
    """One reviewed ``/analogs/{brand}`` entry → the equivalent view (and the
    2.0 fields of find_us_equivalent). ``others`` = the other brands the search
    matched (none when the card asked for one brand by its slug)."""
    direction = hosts.text_dir(loc)
    us_drug = data.get("usDrug") or None
    us_options = await _options(us_drug.get("slug"), loc) if us_drug else None
    fcp = views.from_card_price(us_options)
    restricted = card_law.is_restricted(
        (us_drug or {}).get("slug"), data.get("usGeneric"), data.get("inn"), data.get("brand")
    )
    card_view = card_law.to_view(base, locale=loc, restricted=restricted)
    us_out = None
    if us_drug:
        us_out = {
            "slug": us_drug.get("slug"),
            "name": us_drug.get("name"),
            "fromCardPrice": fcp,
            "url": us_drug.get("url"),
        }
        if competitor_prices_enabled():
            us_out["fromPrice"] = us_drug.get("fromPrice")
            us_out["observedAt"] = us_drug.get("observedAt")
    structured = {
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
        "usDrug": us_out,
        "components": data.get("components"),
        # The translated note when the corpus has one for this language, else the
        # English source note.
        "notes": data.get("notesLocalized") or data.get("notes"),
        "pageUrl": data.get("pageUrl"),
        # Same brand name, different country — offered so the model can ask
        # rather than assume which one the person means.
        "otherMatches": [
            {"brand": r.get("brand"), "countries": r.get("countries"), "brandSlug": r.get("brandSlug")}
            for r in others
        ],
        "card": card_view,
    }
    # The view: the US product only for same_inn (views.equivalent_data), with
    # the drug's name and kind as the catalog has them.
    us_view = None
    if us_out and valid_slug(us_out.get("slug")):
        od = (us_options or {}).get("drug") or {}
        us_view = {
            "slug": us_out["slug"],
            "name": od.get("name") or us_out.get("name") or us_out["slug"],
            "kind": od.get("kind"),
            "cardFrom": views.dated_price(fcp),
        }
    structured.update(
        views.envelope(
            "equivalent",
            locale=loc,
            direction=direction,
            card=card_view,
            data=views.equivalent_data(data, us_view),
        )
    )
    lines = [f"**{data.get('brand')}** ({', '.join(data.get('countries') or [])})"]
    if g := data.get("guidance"):
        lines.append(g)
    if dis := data.get("disclaimer"):
        lines.append(dis)
    if us_out:
        lines.append(tr(loc, "usDrugLine", name=us_out["name"], slug=us_out["slug"], price=_from_line(fcp, loc)))
    if structured["otherMatches"]:
        others = "; ".join(f"{m['brand']} ({', '.join(m.get('countries') or [])})" for m in structured["otherMatches"])
        lines.append(tr(loc, "sameBrandElsewhere", list=others))
    return _result("\n".join(lines), structured, locale=loc, channel=chan, ui=True)


@mcp.tool(
    annotations=ToolAnnotations(title="Find the US equivalent of a foreign medicine", **_READ_HINTS),
    meta=_EQUIVALENT_META,
    structured_output=False,
)
@_guarded("model")
async def find_us_equivalent(
    brand: str,
    country: str | None = None,
    locale: str | None = None,
    channel: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """What a medicine from another country is in the US, and its card price here.

    Use when the person names a medicine that is not a US product — a brand from
    home (No-Spa, Nurofen, Dolo-Neurobion, 999 Ganmaoling), a name in another
    script (Но-шпа, 泰诺), or an ingredient the US calls something else
    (paracetamol) — or asks "what is this called in the US?". Optional
    ``country`` picks between brands of the same name sold in different places.

    Returns the reviewed entry: ``usClass`` (``same_inn`` = the same active
    ingredient is sold here, ``rx_alternative`` = it is not and the closest US
    options need a prescription, ``no_equivalent`` = nothing here matches),
    ``guidance`` (ONE vetted sentence, to be quoted word for word),
    ``guidanceDisclaimer``, ``inn``, ``usGeneric``, ``usBrands``, ``rxStatus``,
    ``usDrug`` (slug and the card price from which it was seen, with the date),
    ``otherMatches`` for the same brand name in other countries, and the card.
    ``found`` is false when nothing matched.

    Next: quote ``guidance`` as written, then ``guidanceDisclaimer``. With a
    ``usDrug``, compare_prices for its slug. Do not call the US drug the same
    product or suggest swapping; for ``rx_alternative`` and ``no_equivalent``
    name no substitute — send the person to a pharmacist or a doctor.
    """
    loc = hosts.resolve_locale(locale, ctx)
    chan = _channel(channel, ctx)
    direction = hosts.text_dir(loc)
    base = await _base_card(loc, chan)
    try:
        found = await client().get("/analogs/search", {"q": brand, "limit": _BRAND_SEARCH_LIMIT, "locale": loc})
        # Only a slug may reach the next request's path.
        results = [r for r in found.get("results") or [] if valid_slug(r.get("brandSlug"))]
        match = _pick_match(results, country) if results else None
        data = (
            await client().get(slug_path("/analogs/{}", match["brandSlug"]), {"locale": loc, "channel": chan})
            if match
            else None
        )
    except FinerxApiError as exc:
        card_view = card_law.to_view(base, locale=loc)
        error = {"code": "api_unavailable"}
        structured = {
            "error": error,
            "card": card_view,
            **views.envelope("equivalent", locale=loc, direction=direction, card=card_view, data=None, error=error),
        }
        return _result(_api_error_text(exc, loc), structured, locale=loc, channel=chan, ui=True)
    if data is None:
        card_view = card_law.to_view(base, locale=loc)
        hint = "no foreign brand matched; try the active ingredient with search_drugs"
        # No data and no error: the card shows this text beside the card strip.
        structured = {
            "found": False,
            "hint": hint,
            "card": card_view,
            **views.envelope("equivalent", locale=loc, direction=direction, card=card_view, data=None),
        }
        return _result(tr(loc, "noForeignMatch", brand=brand), structured, locale=loc, channel=chan, ui=True)
    return await _equivalent_answer(
        data, [r for r in results if r.get("brandSlug") != match.get("brandSlug")], loc=loc, chan=chan, base=base
    )


@mcp.tool(
    annotations=ToolAnnotations(title="Open a foreign brand in the card", **_READ_HINTS),
    meta=_APP_ONLY_META,
    structured_output=False,
)
@_guarded("ui")
async def ui_equivalent(
    brand_slug: str,
    locale: str | None = None,
    ctx: Context | None = None,
) -> CallToolResult:
    """One foreign brand the person picked in the FineRx search — called by the card itself.

    The same answer as find_us_equivalent for exactly that brand (its
    ``brandSlug`` from ui_suggest): the reviewed guidance, word for word, and
    the US product only when it has the same active ingredient. Not for the model.
    """
    loc = hosts.resolve_locale(locale, ctx)
    chan = hosts.default_channel(ctx)
    if not valid_slug(brand_slug):
        return await _view_failure("equivalent", tr(loc, "noForeignMatch", brand="?"), "not_found", loc, chan)
    base = await _base_card(loc, chan)
    try:
        data = await client().get(slug_path("/analogs/{}", brand_slug), {"locale": loc, "channel": chan})
    except FinerxApiError as exc:
        if exc.status_code == 404:
            return await _view_failure("equivalent", tr(loc, "noForeignMatch", brand=brand_slug), "not_found", loc, chan)
        return await _view_failure("equivalent", _api_error_text(exc, loc), "api_unavailable", loc, chan)
    return await _equivalent_answer(data, [], loc=loc, chan=chan, base=base)


@mcp.tool(
    annotations=ToolAnnotations(title="Foreign brand names for a US drug", **_READ_HINTS),
    structured_output=False,
)
@_guarded("model")
async def foreign_brands_for_drug(slug: str, ctx: Context | None = None) -> CallToolResult:
    """What a US drug is called abroad — the reverse of find_us_equivalent.

    Use when the person has the US name and wants the home-country one ("what is
    lisinopril called in Mexico?"). ``slug`` comes from search_drugs. Returns the
    reviewed brands that resolve to this drug: ``brand``, ``brandScript``,
    ``countries``, ``inn`` and ``usClass`` (an ``rx_alternative`` entry is a
    DIFFERENT medicine used for the same complaint — say so if you mention it),
    and the card. Do not present any of these as interchangeable with the US
    drug, and do not tell anyone to buy or import one.
    """
    loc = hosts.resolve_locale(None, ctx)
    chan = hosts.default_channel(ctx)
    base = await _base_card(loc, chan)
    card_view = card_law.to_view(base, locale=loc, restricted=card_law.is_restricted(slug))
    try:
        target = await _slug_for(slug, loc)
        data = (
            await client().get(slug_path("/analogs/for-drug/{}", target))
            if target
            else {"drugSlug": slug, "items": []}
        )
    except FinerxApiError as exc:
        return _result(
            _api_error_text(exc, loc),
            {"error": {"code": "api_unavailable"}, "card": card_view},
            locale=loc,
            channel=chan,
        )
    brands = [
        {
            "brand": b.get("brand"),
            "brandScript": b.get("brandScript"),
            "countries": b.get("countries"),
            "inn": b.get("inn"),
            "usClass": b.get("usClass"),
        }
        for b in data.get("items") or []
    ]
    lines = [tr(loc, "brandsAbroad", slug=data.get("drugSlug", slug), n=len(brands))]
    for b in brands:
        script = f" ({b['brandScript']})" if b.get("brandScript") else ""
        lines.append(f"- {b['brand']}{script} — {', '.join(b.get('countries') or [])} — {b.get('usClass')}")
    structured = {"drugSlug": data.get("drugSlug", slug), "count": len(brands), "brands": brands, "card": card_view}
    return _result("\n".join(lines), structured, locale=loc, channel=chan)


# --- the UI bundle ---------------------------------------------------------------

# What a host is allowed to reach from inside the component: NOTHING. The widget
# is one self-contained document, so both domain lists are empty on purpose.
# ``ui.domain`` / ``openai/widgetDomain`` is the origin the host gives the
# sandbox — required for the ChatGPT app submission.
_APP_META: dict[str, Any] = {
    "ui": {
        "prefersBorder": True,
        "csp": {"connectDomains": [], "resourceDomains": []},
        "permissions": {"clipboardWrite": {}},
        "domain": WIDGET_DOMAIN,
    },
    "openai/widgetDomain": WIDGET_DOMAIN,
    "openai/widgetDescription": (
        "Card prices by pharmacy chain with their dates, nearby pharmacies, a search for a "
        "medicine, what a foreign medicine is called in the US, routes to a prescription, "
        "and the free FineRx card with its codes."
    ),
    "openai/widgetPrefersBorder": True,
    "openai/widgetCSP": {"connect_domains": [], "resource_domains": []},
    "finerx/build": build_id(),
}


@mcp.resource(
    APP_URI,
    name="FineRx card prices app",
    title="FineRx",
    description=(
        "The interactive FineRx card: search, prices by chain, nearby pharmacies, the US name "
        "of a foreign medicine, routes to a prescription, and the free card."
    ),
    mime_type=WIDGET_MIME_TYPE,
    meta=_APP_META,
)
def app_widget() -> str:
    """The v2 bundle (static, self-contained, read once per process)."""
    return load_app_html()


@mcp.resource(
    APP_URI_V21,
    name="FineRx card prices app (2.1 views)",
    title="FineRx",
    description=(
        "The interactive FineRx card with the 2.1 views: search, the US name of a foreign "
        "medicine, routes to a prescription — plus prices, nearby pharmacies and the free card."
    ),
    mime_type=WIDGET_MIME_TYPE,
    meta=_APP_META,
)
def app_widget_v21() -> str:
    """The same bundle under the 2.1 uri, so no host shows a cached 2.0 copy for a 2.1 view."""
    return load_app_html()


@mcp.resource(
    WIDGET_URI,
    name="FineRx savings card widget (1.x uri)",
    title="FineRx savings card",
    description="The 1.x uri of the card component; serves the v2 app, which draws the card.",
    mime_type=WIDGET_MIME_TYPE,
    meta=_APP_META,
)
def savings_card_widget() -> str:
    """Kept so a host holding a 1.x tools/list still finds a component here."""
    return load_app_html()


# --- resources: for clients that preload context instead of calling tools ----

HOW_IT_WORKS = """# How FineRx works

FineRx is an independent US prescription price service. It shows what US pharmacy
chains were **seen charging with the free FineRx discount card** — one price per
chain (Walmart: per state), each with the **date it was observed** — which of
those chains have stores near a ZIP code, and the card itself: free, no signup,
not insurance. It also tells people what a medicine from another country is
called in the US, in 12 languages.

## The card

Use the free FineRx card — accepted at 34+ pharmacy chains, no signup. Save it,
print it, email or text it. Savings with the card can be substantial — estimated
prices are on our site. Show the card at the pharmacy to get the final price.

Not insurance · prices observed on the date shown · FineRx may earn a fee · not medical advice

## Rules for any answer built on this data

- Quote a price **with the date it was observed** and the chain it was seen at.
  An old price states its date; it is never presented as today's price.
- A price belongs to one package. It is never scaled to another quantity.
- The pharmacy sets the final price at the counter; FineRx does not see stock.
- Say how many chains accept the card from the data (``card.chainsCount``); do
  not promise a price or a saving, and do not rank a chain above the others
  beyond the order of the observed prices.
- FineRx gives **no medical advice** — no dosing, no substitutions.
- For controlled or age-restricted medicines (DEA Schedule II–IV stimulants,
  opioids, benzodiazepines and sleep medicines; phentermine, testosterone,
  carisoprodol, pregabalin) FineRx gives card prices and the card only.

## Attribution

Say "Prices via FineRx" when you use these numbers. Credit the data behind the
places and stores when you show them:

- Place names: GeoNames (CC BY 4.0) — the city and state of a ZIP code.
- Pharmacy locations: © OpenStreetMap contributors (ODbL).
"""


@mcp.resource(
    "finerx://how-it-works",
    name="How FineRx works",
    title="How FineRx works",
    description="What FineRx is, the card, the honesty rules for quoting its data, and attribution.",
    mime_type="text/markdown",
)
def how_it_works_resource() -> str:
    """Static context: what this data is and the language it may be quoted in."""
    return HOW_IT_WORKS


@mcp.resource(
    "finerx://card",
    name="FineRx savings card",
    title="The free FineRx discount card",
    description="The card's codes, how to use it and the card sentence — as markdown.",
    mime_type="text/markdown",
)
async def card_resource() -> str:
    """The card get_savings_card returns, as markdown, for clients that preload
    resources instead of calling tools."""
    card = await _base_card("en", "mcp")
    view = card_law.to_view(card, locale="en")
    lines: list[str] = ["# The free FineRx discount card", "", card_law.codes_line(view), ""]
    if steps := card.get("howToUse") or []:
        lines += ["## How to use it", ""]
        lines += [f"{i}. {step}" for i, step in enumerate(steps, 1)]
        lines.append("")
    if phrase := card.get("pharmacistPhrase"):
        lines += [f'Say at the counter: "{phrase}"', ""]
    lines += [view["law"], "", view["fine"]]
    return "\n".join(lines)


# --- prompts: the journeys a person actually arrives with ---------------------


@mcp.prompt(
    name="price_and_card",
    title="Price + the free card",
    description="Find a drug's card price near you with FineRx and get the free discount card.",
)
def price_and_card(drug: str) -> str:
    """One turn that ends with the person holding the card, not just a number."""
    return (
        f"Find the price of {drug} with the free FineRx card at pharmacies near me, state the "
        "observation date of each price, then give me the free discount card codes."
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
        "getting one and for filling it, read out any disclosure that "
        "comes with an option, and give me the free FineRx discount card. Do not "
        "give me medical advice."
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
        "give me its card price with the date it was observed and the free discount card. Do "
        "not tell me what to take instead."
    )


def main() -> None:
    """Entry point (``finerx-mcp``).

    Transport defaults to **stdio** (local clients: Claude Desktop/Code, Cursor).
    Set ``FINERX_MCP_TRANSPORT=streamable-http`` (+ optional ``FINERX_MCP_HOST`` /
    ``FINERX_MCP_PORT`` / ``FINERX_MCP_PATH``) to serve the SAME tools over a
    remote HTTP URL — what connector catalogs (ChatGPT Apps, Claude connectors)
    consume. Served STATELESS by default (``FINERX_MCP_STATELESS=0`` to go back
    to per-session transports).
    """
    transport = os.environ.get("FINERX_MCP_TRANSPORT", "stdio")
    log.info("finerx-mcp %s starting (%s)", __version__, transport)
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
