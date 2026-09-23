"""API payloads → what a tool returns: the ``finerx.view/2`` envelope the widget
draws, and the markdown ``content`` the model reads.

The two are built from the same payload so they cannot disagree. ``content``
must stand on its own — Claude and the MCP Apps spec never show
``structuredContent`` to the model — so it names the package, the top prices
each WITH its observation date on the same line, and where the place came from.
The card block (codes, law, small print) is appended by the tool
(``card_law.law_block``), not here. Headings and service phrases come from
``labels.tr`` in the reader's language; amounts and dates are data.

Nothing here invents a number: no price is scaled to another quantity, a family
without a price says so, and ``coverage`` decides the wording when the package
asked for was never observed.
"""
from __future__ import annotations

import re
from typing import Any

from finerx_mcp.labels import tr
from finerx_mcp.schemas import SCHEMA

INLINE_ROWS = 6  # contract C2: rows ≤ 6 inline, the rest counted in moreCount
TEXT_ROWS = 3  # spec §7: the model gets the three first prices
TEXT_STORES = 5
MAX_STORES = 24  # keeps data ≤ ~4 KB
MAX_CONFIGS = 12
MAX_QUANTITIES = 8
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,120}$")  # = client.SLUG_RE

# The English phrases (kept as names for callers; the text builders read
# ``labels.tr`` so every language gets its own).
NO_STOCK = tr("en", "noStock")
PER_CHAIN = tr("en", "perChain")
OSM = tr("en", "osm")


def money(amount: Any) -> str:
    return f"${float(amount):,.2f}"


def dated(price: dict | None, locale: str = "en") -> str | None:
    """``$4.20 with the card, observed 2026-09-21`` — the only way an amount is
    ever written (the date always on the same line)."""
    if not isinstance(price, dict) or price.get("amount") is None:
        return None
    return tr(locale, "withCardObserved", price=money(price["amount"]), date=price.get("observedAt"))


def _zone_label(zone: Any, locale: str = "en") -> str:
    if not zone or zone == "default":
        return ""
    return f" ({tr(locale, 'zonePrice', zone=str(zone).replace('_', '/').upper())})"


def chain_name(row: dict, locale: str = "en") -> str:
    return f"{row.get('name') or row.get('family')}{_zone_label(row.get('zone'), locale)}"


def place_label(origin: dict | None, locale: str = "en") -> str | None:
    """"Miami, FL (ZIP 33101)" / "Austin, TX (approximate)" — or None."""
    if not isinstance(origin, dict) or origin.get("precision") in (None, "none"):
        return None
    where = ", ".join(p for p in (origin.get("city"), origin.get("state")) if p)
    # A typed address is placed to the point, but we show only its ZIP area.
    if origin.get("precision") in ("zip", "address") and origin.get("zip"):
        if where:
            return tr(locale, "placeZip", where=where, zip=origin["zip"])
        return tr(locale, "zipOnly", zip=origin["zip"])
    return tr(locale, "placeApprox", where=where or tr(locale, "yourArea"))


def package_label(drug: dict | None, package: dict | None, locale: str = "en") -> str:
    name = (drug or {}).get("name") or (drug or {}).get("slug") or tr(locale, "thisMedicine")
    label = (package or {}).get("label")
    return f"{name} — {label}" if label else name


def coverage_text(package: dict | None, coverage: dict | None, locale: str = "en") -> str | None:
    status = (coverage or {}).get("status")
    qty = (package or {}).get("quantity")
    if status == "other_quantities":
        seen = ", ".join(str(q) for q in (coverage or {}).get("quantities") or [])
        return tr(locale, "coverageOther", quantity=qty, seen=seen)
    if status == "none":
        return tr(locale, "coverageNone")
    return None


# --- options -------------------------------------------------------------------


def trim_options(options: dict | None) -> dict | None:
    """``/options`` → the ``options`` block of the prices view (bounded)."""
    if not isinstance(options, dict) or not options.get("configs"):
        return None
    configs = []
    for cfg in options["configs"][:MAX_CONFIGS]:
        configs.append(
            {
                "form": cfg.get("form"),
                "strength": cfg.get("strength"),
                "label": cfg.get("label"),
                "quantities": [
                    {
                        "quantity": q.get("quantity"),
                        "label": q.get("label"),
                        "cardFrom": q.get("cardFrom"),
                        "chainsPriced": q.get("chainsPriced"),
                    }
                    for q in (cfg.get("quantities") or [])[:MAX_QUANTITIES]
                ],
            }
        )
    return {"configs": configs}


def from_card_price(options: dict | None) -> dict | None:
    """The lowest card price seen for ANY package of the drug, with its date and
    the package it belongs to (a "from" price is meaningless without it)."""
    best: dict | None = None
    for cfg in (options or {}).get("configs") or []:
        for q in cfg.get("quantities") or []:
            cf = q.get("cardFrom")
            if not isinstance(cf, dict) or cf.get("amount") is None:
                continue
            if best is None or cf["amount"] < best["amount"]:
                best = {
                    "amount": cf["amount"],
                    "observedAt": cf.get("observedAt"),
                    "package": q.get("label") or cfg.get("label"),
                }
    return best


# --- prices ----------------------------------------------------------------------


def _row(chain: dict) -> dict:
    return {
        "family": chain.get("family"),
        "name": chain.get("name") or chain.get("family"),
        "price": chain.get("price"),
        "zone": chain.get("zone"),
        "nearestMiles": chain.get("nearestMiles"),
        "storeCount": int(chain.get("storeCount") or 0),
    }


def prices_data(near: dict, options: dict | None) -> tuple[dict, list[dict]]:
    """``POST /prices/near`` (+ ``/options``) → ``prices.data`` and every row
    (for ``_meta["finerx/allChains"]``)."""
    rows = [_row(c) for c in near.get("chains") or []]
    drug = near.get("drug") or {}
    data = {
        "drug": {"slug": drug.get("slug"), "name": drug.get("name"), "kind": drug.get("kind")},
        "package": near.get("package") or {},
        "options": trim_options(options),
        "origin": near.get("origin") or {"precision": "none"},
        "rows": rows[:INLINE_ROWS],
        "pricesWithoutStores": [
            {"family": p.get("family"), "name": p.get("name"), "price": p.get("price")}
            for p in near.get("pricesWithoutStores") or []
            if isinstance(p.get("price"), dict)
        ],
        "moreCount": max(0, len(rows) - INLINE_ROWS),
        "needsZip": bool(near.get("needsZip")),
        "coverage": near.get("coverage") or {"status": "none", "quantities": []},
    }
    return data, rows


def prices_text(near: dict, *, restricted: bool = False, locale: str = "en") -> str:
    drug, package = near.get("drug"), near.get("package")
    place = place_label(near.get("origin"), locale)
    lines = [f"**{package_label(drug, package, locale)}**"]
    if near.get("needsZip") or not place:
        lines.append(tr(locale, "pricesNational"))
    else:
        lines.append(tr(locale, "pricesNear", place=place))
    chains = near.get("chains") or []
    for chain in chains[:TEXT_ROWS]:
        price = dated(chain.get("price"), locale)
        miles = chain.get("nearestMiles")
        where = f" · {tr(locale, 'nearestStore', miles=miles)}" if miles is not None else ""
        lines.append(f"- {chain_name(chain, locale)}: {price or tr(locale, 'noPriceForPackage')}{where}")
    if len(chains) > TEXT_ROWS:
        lines.append(f"- {tr(locale, 'moreChains', n=len(chains) - TEXT_ROWS)}")
    if not chains:
        lines.append(f"- {tr(locale, 'noChain')}")
    for p in (near.get("pricesWithoutStores") or [])[:TEXT_ROWS]:
        price = dated(p.get("price"), locale)
        if price:
            lines.append(f"- {tr(locale, 'noStoreNearby', name=p.get('name'), price=price)}")
    if cov := coverage_text(package, near.get("coverage"), locale):
        lines.append(cov)
    lines.append(tr(locale, "perChain"))
    lines.append(tr(locale, "noStock"))
    if restricted:
        lines.append(tr(locale, "restrictedPrices"))
    return "\n".join(lines)


# --- pharmacies -------------------------------------------------------------------


def _store(store: dict, *, family: str, name: str, price: dict | None) -> dict:
    return {
        "family": family,
        "name": store.get("name") or name,
        "address": store.get("address"),
        "city": store.get("city"),
        "miles": store.get("miles", store.get("distanceMiles")),
        "lat": store.get("lat", store.get("latitude")),
        "lon": store.get("lon", store.get("longitude")),
        "kind": "store" if store.get("kind") == "store" else "pharmacy",
        "price": price,
    }


def _by_miles(stores: list[dict]) -> list[dict]:
    return sorted(stores, key=lambda s: (s.get("miles") is None, s.get("miles") or 0.0))


def pharmacies_from_near(near: dict, families: list[str] | None = None) -> dict:
    """``POST /prices/near`` → ``pharmacies.data``: each family's nearest stores
    with the family's dated card price."""
    wanted = set(families or [])
    stores: list[dict] = []
    for chain in near.get("chains") or []:
        fam = chain.get("family")
        if wanted and fam not in wanted:
            continue
        for s in chain.get("stores") or []:
            stores.append(_store(s, family=fam, name=chain.get("name") or fam, price=chain.get("price")))
    stores = _by_miles(stores)[:MAX_STORES]
    drug = near.get("drug") or {}
    return {
        "drug": {"slug": drug.get("slug"), "name": drug.get("name"), "kind": drug.get("kind")} if drug else None,
        "package": near.get("package"),
        "origin": near.get("origin") or {"precision": "none"},
        "stores": stores,
        "families": sorted({s["family"] for s in stores if s.get("family")}),
    }


def pharmacies_from_nearby(nearby: dict, *, precision: str) -> dict:
    """``GET /pharmacies/nearby`` → ``pharmacies.data`` (no drug, no prices)."""
    stores: list[dict] = []
    for chain in nearby.get("results") or []:
        fam = chain.get("family") or chain.get("chainCode")
        for loc in chain.get("locations") or []:
            stores.append(
                _store(loc, family=loc.get("family") or fam, name=chain.get("chain") or fam, price=None)
            )
    stores = _by_miles(stores)[:MAX_STORES]
    return {
        "drug": None,
        "package": None,
        "origin": {"zip": nearby.get("zip"), "city": None, "state": None, "precision": precision},
        "stores": stores,
        "families": sorted({s["family"] for s in stores if s.get("family")}),
    }


def pharmacies_text(data: dict, locale: str = "en") -> str:
    place = place_label(data.get("origin"), locale)
    if place:
        head = f"**{tr(locale, 'pharmaciesNear', place=place)}**"
    else:
        head = f"**{tr(locale, 'pharmaciesNearby')}**"
    if data.get("drug"):
        head += f" — {package_label(data['drug'], data.get('package'), locale)}"
    lines = [head]
    stores = data.get("stores") or []
    if not place:
        lines.append(tr(locale, "noPlace"))
    elif not stores:
        lines.append(tr(locale, "noStoreInRange"))
    for s in stores[:TEXT_STORES]:
        addr = ", ".join(p for p in (s.get("address"), s.get("city")) if p)
        kind = f" ({tr(locale, 'storeInStore')})" if s.get("kind") == "store" else ""
        miles = f" — {tr(locale, 'milesShort', n=s['miles'])}" if s.get("miles") is not None else ""
        price = dated(s.get("price"), locale)
        tail = f" — {price}" if price else ""
        lines.append(f"- {s.get('name')}{kind}{', ' + addr if addr else ''}{miles}{tail}")
    if len(stores) > TEXT_STORES:
        lines.append(f"- {tr(locale, 'moreNearby', n=len(stores) - TEXT_STORES)}")
    if stores:
        lines.append(tr(locale, "noStock"))
        lines.append(tr(locale, "osm"))
    return "\n".join(lines)


# --- phase 2: search / equivalent / rx (MCP 2.1, contract C2') -----------------------

MAX_SUGGESTIONS = 8
US_CLASSES = ("same_inn", "rx_alternative", "no_equivalent")
_HTTPS = re.compile(r"^https://\S+$")


def dated_price(value: Any) -> dict | None:
    """``{amount, observedAt}`` — or None when either half is missing (an
    amount never travels without its date)."""
    if not isinstance(value, dict) or value.get("amount") is None or not value.get("observedAt"):
        return None
    return {"amount": value["amount"], "observedAt": value["observedAt"]}


def suggestion(hit: dict) -> dict | None:
    """One ``/drugs/suggest`` result → the search view's row (slug-shaped only)."""
    slug = hit.get("slug")
    if not isinstance(slug, str) or not _SLUG.match(slug) or not hit.get("name"):
        return None
    return {
        "slug": slug,
        "name": hit.get("name"),
        "kind": hit.get("kind"),
        "matchedAlias": hit.get("matchedAlias"),
        "cardFrom": dated_price(hit.get("cardFrom")),
    }


def foreign_hit(brand: dict) -> dict | None:
    """A foreign brand the text matched. The US product is named ONLY for
    ``same_inn``: an ``rx_alternative`` is a different medicine (No-Spa is not
    dicyclomine), so it never shows as "in the US: …" and never leads to that
    drug's prices; ``no_equivalent`` has none."""
    if not brand.get("brand"):
        return None
    cls = brand.get("usClass") if brand.get("usClass") in US_CLASSES else None
    us_slug = brand.get("usSlug") if cls == "same_inn" else None
    if not (isinstance(us_slug, str) and _SLUG.match(us_slug)):
        us_slug = None
    slug = brand.get("brandSlug")
    return {
        "brand": brand["brand"],
        "brandSlug": slug if isinstance(slug, str) and _SLUG.match(slug) else None,
        "countries": [c for c in brand.get("countries") or [] if isinstance(c, str)],
        "usClass": cls,
        "usSlug": us_slug,
        "usName": brand.get("usName") if us_slug else None,
    }


def suggest_lists(api: dict) -> tuple[list[dict], list[dict]]:
    """``GET /drugs/suggest`` → (results, foreignBrands), each ≤ 8."""
    results = [r for r in (suggestion(h) for h in api.get("results") or [] if isinstance(h, dict)) if r]
    foreign = [b for b in (foreign_hit(h) for h in api.get("foreignBrands") or [] if isinstance(h, dict)) if b]
    return results[:MAX_SUGGESTIONS], foreign[:MAX_SUGGESTIONS]


def search_text(
    query: str | None, results: list[dict], foreign: list[dict], popular: list[dict], locale: str = "en"
) -> str:
    """What the model reads when the search opens (or a typeahead answers):
    the matches with their dated "from" price, else the popular list."""
    if not query:
        names = ", ".join(p["name"] for p in popular)
        return "\n".join((tr(locale, "searchOpened"), tr(locale, "searchPopular", names=names)))
    if not results and not foreign:
        return tr(locale, "searchNoMatch", query=query)
    lines = [tr(locale, "searchOpenedFor", query=query)]
    for r in results:
        cf = r.get("cardFrom")
        price = (
            tr(locale, "suggestFrom", price=money(cf["amount"]), date=cf["observedAt"])
            if cf
            else tr(locale, "noCardPriceYet")
        )
        lines.append(f"- {r['name']} ({r.get('kind') or '—'}) — slug {r['slug']} — {price}")
    for b in foreign:
        lines.append("- " + tr(locale, "foreignSuggest", brand=b["brand"], countries=", ".join(b["countries"])))
    return "\n".join(lines)


def equivalent_data(entry: dict, us: dict | None) -> dict:
    """``/analogs/{brand}`` → ``equivalent.data``. ``guidance`` and
    ``disclaimer`` are the API's sentences, verbatim; ``us`` only for
    ``same_inn`` (the caller passes it only then)."""
    cls = entry.get("usClass") if entry.get("usClass") in US_CLASSES else None
    return {
        "brand": entry.get("brand"),
        "countries": [c for c in entry.get("countries") or [] if isinstance(c, str)],
        "inn": entry.get("inn"),
        "usClass": cls,
        "guidance": entry.get("guidance"),
        "disclaimer": entry.get("disclaimer"),
        "us": us if cls == "same_inn" else None,
    }


def _option_line(opt: dict) -> str:
    """``name: note (disclosure)`` — a partner's disclosure travels with it."""
    line = str(opt.get("name") or "").strip()
    if opt.get("note"):
        line += f": {opt['note']}"
    if opt.get("disclosure"):
        line += f" ({opt['disclosure']})"
    return line


def _links(options: list) -> list[dict]:
    out = []
    for opt in options or []:
        url = opt.get("url") if isinstance(opt, dict) else None
        if isinstance(url, str) and _HTTPS.match(url) and opt.get("name"):
            label = str(opt["name"])
            if opt.get("disclosure"):
                label += f" ({opt['disclosure']})"
            out.append({"label": label, "url": url})
    return out


def rx_sections(api: dict, locale: str = "en") -> list[dict]:
    """``/prescription-options`` → the rx view's three sections, as the API
    wrote them (en/es text; the titles in the reader's language). Only https
    links; every option line keeps its disclosure."""
    sections: list[dict] = []
    have = api.get("havePrescription") or {}
    if have.get("summary"):
        steps = [f"{i}. {s}" for i, s in enumerate(have.get("steps") or [], 1)]
        sections.append({"title": tr(locale, "rxHave"), "body": "\n".join([have["summary"], *steps]), "links": []})
    none = api.get("noPrescription") or {}
    if none.get("summary"):
        opts = [o for o in none.get("options") or [] if isinstance(o, dict)]
        body = [none["summary"], *(f"- {_option_line(o)}" for o in opts if o.get("name"))]
        if api.get("medicaidNote"):
            body.append(api["medicaidNote"])
        sections.append({"title": tr(locale, "rxNone"), "body": "\n".join(body), "links": _links(opts)})
    costly = api.get("brandCostly") or {}
    if costly.get("summary"):
        opts = [o for o in costly.get("options") or [] if isinstance(o, dict)]
        body = [costly["summary"], *(f"- {_option_line(o)}" for o in opts if o.get("name"))]
        sections.append({"title": tr(locale, "rxBrand"), "body": "\n".join(body), "links": _links(opts)})
    return sections[:3]


# --- envelope ------------------------------------------------------------------------


def envelope(
    view: str,
    *,
    locale: str,
    direction: str,
    card: dict,
    data: dict | None,
    error: dict | None = None,
    notice: dict | None = None,
) -> dict:
    """``error`` = the view could not be drawn (the widget shows its error state
    and the card); ``notice`` = the view IS drawn, with one thing to say about
    the request (``zip_invalid``: the ZIP the person gave is not 5 digits)."""
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "view": view,
        "locale": locale,
        "dir": direction,
        "data": data,
        "card": card,
    }
    if error is not None:
        out["error"] = error
    if notice is not None:
        out["notice"] = notice
    return out
