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


def trim_options(options: dict | None, limit: int | None = MAX_CONFIGS) -> dict | None:
    """``/options`` → the ``options`` block of the prices view (bounded;
    ``limit=None`` keeps every strength, for a caller that bounds it itself)."""
    if not isinstance(options, dict) or not options.get("configs"):
        return None
    configs = []
    for cfg in options["configs"][:limit]:
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
                    for q in (cfg.get("quantities") or [])[: MAX_QUANTITIES if limit is not None else None]
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


# --- packages (MCP 2.2): every strength and pack size with a card price ------------


def _same(a: Any, b: Any) -> bool:
    return str(a or "").strip().lower() == str(b or "").strip().lower()


PACKAGE_CONFIGS = 6  # an inline card: a few strengths, the common pack sizes
PACKAGE_QUANTITIES = 4
_COMMON_QUANTITIES = (30, 90, 60)


def _pack_sizes(quantities: list[dict], default_qty: Any) -> list[dict]:
    """Up to ``PACKAGE_QUANTITIES`` pack sizes of one strength: the default one,
    then 30 / 90 / 60, then the rest — shown smallest first."""

    def order(q: dict) -> tuple:
        n = q.get("quantity")
        common = _COMMON_QUANTITIES.index(n) if n in _COMMON_QUANTITIES else len(_COMMON_QUANTITIES)
        return (n != default_qty, common, n if isinstance(n, (int, float)) else 0)

    kept = sorted(quantities, key=order)[:PACKAGE_QUANTITIES]
    return sorted(kept, key=lambda q: q.get("quantity") or 0)


def packages_data(drug: dict, default_package: dict | None, options: dict | None = None) -> dict:
    """``get_drug``'s answer → ``packages.data``: strengths × forms, each with a
    few pack sizes — where the card prices start (dated) and how many chains
    priced it. ``default`` marks the package the most chains price.

    Bounded for an inline card: the default package's strength FIRST (live
    2026-10-03: levothyroxine's default fell outside the list, behind a dozen
    capsule boxes), then the others in the API's order, ``PACKAGE_CONFIGS`` in
    all; ``moreCount`` says how many strengths are not shown. No per-unit figure:
    a quantity can count boxes or pens, and dividing by it then misleads."""
    d = default_package if isinstance(default_package, dict) else {}
    every = (trim_options(options, limit=None) or {}).get("configs") if options else None
    every = every if every is not None else list(drug.get("configs") or [])
    is_default = lambda c: _same(c.get("form"), d.get("form")) and _same(c.get("strength"), d.get("strength"))  # noqa: E731
    ordered = [c for c in every if is_default(c)] + [c for c in every if not is_default(c)]
    shown = [
        {**c, "quantities": _pack_sizes(c.get("quantities") or [], d.get("quantity") if is_default(c) else None)}
        for c in ordered[:PACKAGE_CONFIGS]
    ]
    return {
        "drug": {"slug": drug.get("slug"), "name": drug.get("name"), "kind": drug.get("kind")},
        "configs": shown,
        "moreCount": max(0, len(every) - len(shown)),
        "default": {"form": d.get("form"), "strength": d.get("strength"), "quantity": d.get("quantity")},
    }


# --- an amount the person named (a copay, what they pay now, a target) ------------

COMPARE_MAX = 100_000.0


def compare_to(near: dict, amount: Any) -> dict | None:
    """How many chains were seen with a card price BELOW the amount the person
    named for this package — a count of observed prices, with the span of their
    dates; no difference is computed and nothing is promised. None when the
    amount is not a usable number or no chain has a price."""
    try:
        value = round(float(amount), 2)
    except (TypeError, ValueError):
        return None
    if isinstance(amount, bool) or not (0 < value <= COMPARE_MAX):
        return None
    prices = [
        p
        for p in (dated_price(c.get("price")) for c in (near.get("chains") or []) + (near.get("pricesWithoutStores") or []))
        if p
    ]
    if not prices:
        return None
    dates = [p["observedAt"] for p in prices]
    return {
        "amount": value,
        "below": sum(1 for p in prices if p["amount"] < value),
        "of": len(prices),
        "observedFrom": min(dates),
        "observedTo": max(dates),
    }


def compare_to_text(against: dict, locale: str = "en") -> str:
    lo, hi = against["observedFrom"], against["observedTo"]
    dates = lo if lo == hi else tr(locale, "basketDates", lo=lo, hi=hi)
    return "\n".join(
        (
            tr(
                locale,
                "compareTo",
                amount=money(against["amount"]),
                below=against["below"],
                of=against["of"],
                dates=dates,
            ),
            tr(locale, "compareToNote"),
        )
    )


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


# --- the basket (MCP 2.2): several medicines, one place ----------------------------

BASKET_ROWS = 8
# Going to two pharmacies for a few cents is not an option worth naming.
SPLIT_MIN_GAIN = 1.0


def _span(dates: list[str]) -> tuple[str, str]:
    return min(dates), max(dates)


def basket_data(nears: list[dict], *, unmatched: int = 0) -> dict:
    """Several ``POST /prices/near`` answers for ONE place → ``basket.data``.

    A row is a chain; its ``prices`` line up with ``items``. An item no listed
    chain was seen pricing is marked ``priced: false`` and left out of every
    sum (live 2026-10-03: one such medicine emptied the whole table). ``total``
    exists only when the chain was seen with a card price for EVERY priced
    item — it is the sum of those observed prices (nothing is scaled or filled
    in), with how many it adds (``count``) and the span of their observation
    dates. ``split`` is the sum of each priced item's own first price across
    the chains listed, offered only when it takes more than one chain and comes
    to at least ``SPLIT_MIN_GAIN`` less than every one-chain total.

    With a place, only chains with a store in range are rows; without one the
    chains with a card price and no store nearby are rows too."""
    first = nears[0] if nears else {}
    needs_zip = any(bool(n.get("needsZip")) for n in nears)
    origin = first.get("origin") or {"precision": "none"}
    placed = not needs_zip and origin.get("precision") not in (None, "none")
    items = []
    by_item: list[dict[str, dict]] = []
    info: dict[str, dict] = {}
    for near in nears:
        d = near.get("drug") or {}
        items.append(
            {
                "drug": {"slug": d.get("slug"), "name": d.get("name"), "kind": d.get("kind")},
                "package": near.get("package") or {},
                "coverage": near.get("coverage") or {"status": "none", "quantities": []},
            }
        )
        prices: dict[str, dict] = {}
        chains = list(near.get("chains") or [])
        if not placed:
            chains += [{**p, "storeCount": 0} for p in near.get("pricesWithoutStores") or []]
        for c in chains:
            fam = c.get("family")
            if not fam:
                continue
            row = info.setdefault(
                fam,
                {
                    "family": fam,
                    "name": c.get("name") or fam,
                    "zone": c.get("zone"),
                    "nearestMiles": c.get("nearestMiles"),
                    "storeCount": int(c.get("storeCount") or 0),
                },
            )
            if row.get("zone") is None and c.get("zone"):
                row["zone"] = c.get("zone")
            if (price := dated_price(c.get("price"))) and fam not in prices:
                prices[fam] = price
        by_item.append(prices)

    priced_idx = [i for i in range(len(items)) if by_item[i]]
    for i, item in enumerate(items):
        item["priced"] = i in priced_idx

    rows: list[dict] = []
    for fam, meta in info.items():
        prices = [by_item[i].get(fam) for i in range(len(items))]
        seen = [p for p in prices if p]
        if not seen:
            continue
        missing = [i + 1 for i in priced_idx if not prices[i]]
        total = None
        if not missing:
            lo, hi = _span([p["observedAt"] for p in seen])
            total = {
                "amount": round(sum(p["amount"] for p in seen), 2),
                "count": len(seen),
                "observedFrom": lo,
                "observedTo": hi,
            }
        rows.append({**meta, "prices": prices, "total": total, "missing": missing})
    rows.sort(key=lambda r: (len(r["missing"]), sum(p["amount"] for p in r["prices"] if p), r["name"]))

    split = None
    picks: list[tuple[int, dict, dict]] = []
    for i in priced_idx:
        price, row = min(((r["prices"][i], r) for r in rows if r["prices"][i]), key=lambda pr: pr[0]["amount"])
        picks.append((i + 1, price, row))
    if len(picks) > 1:
        amount = round(sum(p["amount"] for _, p, _ in picks), 2)
        chains_used = {r["family"] for _, _, r in picks}
        totals = [r["total"]["amount"] for r in rows if r["total"]]
        if len(chains_used) > 1 and (not totals or amount <= min(totals) - SPLIT_MIN_GAIN):
            lo, hi = _span([p["observedAt"] for _, p, _ in picks])
            split = {
                "amount": amount,
                "count": len(picks),
                "observedFrom": lo,
                "observedTo": hi,
                "chains": len(chains_used),
                "picks": [{"item": n, "family": r["family"], "name": r["name"]} for n, _, r in picks],
            }
    return {
        "items": items,
        "origin": origin,
        "rows": rows[:BASKET_ROWS],
        "moreCount": max(0, len(rows) - BASKET_ROWS),
        "split": split,
        "needsZip": needs_zip or not placed,
        "unmatched": int(unmatched),
    }


def _dates(lo: str, hi: str, locale: str) -> str:
    return lo if lo == hi else tr(locale, "basketDates", lo=lo, hi=hi)


def basket_text(data: dict, *, restricted: bool = False, locale: str = "en") -> str:
    """What the model reads: the packages, then the chains by the sum of their
    card prices — every amount on a line with the dates it was observed."""
    items = data.get("items") or []
    n = len(items)
    place = None if data.get("needsZip") else place_label(data.get("origin"), locale)
    head = tr(locale, "basketHead", n=n, place=place) if place else tr(locale, "basketHeadNational", n=n)
    lines = [f"**{head}**"]
    for i, it in enumerate(items, 1):
        line = f"{i}. {package_label(it.get('drug'), it.get('package'), locale)}"
        if it.get("priced") is False:
            line += f" — {tr(locale, 'noPriceShort')}"
        elif cov := coverage_text(it.get("package"), it.get("coverage"), locale):
            line += f" — {cov}"
        lines.append(line)
    unpriced = ", ".join(f"#{i}" for i, it in enumerate(items, 1) if it.get("priced") is False)
    if unpriced and len(unpriced.split(",")) < n:
        lines.append(tr(locale, "basketUnpriced", items=unpriced))
    rows = data.get("rows") or []
    if any(r.get("total") for r in rows):
        lines.append(tr(locale, "basketOneChain"))
    elif rows:
        lines.append(tr(locale, "basketNoChain"))
    for r in rows[:TEXT_STORES]:
        name = chain_name(r, locale)
        if t := r.get("total"):
            parts = ", ".join(f"#{i} {money(p['amount'])}" for i, p in enumerate(r["prices"], 1) if p)
            where = f" · {tr(locale, 'nearestStore', miles=r['nearestMiles'])}" if r.get("nearestMiles") is not None else ""
            lines.append(
                "- "
                + tr(
                    locale,
                    "basketRow",
                    name=name,
                    total=money(t["amount"]),
                    n=t["count"],
                    dates=_dates(t["observedFrom"], t["observedTo"], locale),
                )
                + f" ({parts}){where}"
            )
        else:
            lines.append(
                "- " + tr(locale, "basketRowMissing", name=name, items=", ".join(f"#{i}" for i in r.get("missing") or []))
            )
    if not rows:
        lines.append(f"- {tr(locale, 'noChain')}")
    if s := data.get("split"):
        picks = ", ".join(f"#{p['item']} {p['name']}" for p in s.get("picks") or [])
        lines.append(
            tr(
                locale,
                "basketSplit",
                total=money(s["amount"]),
                chains=s["chains"],
                dates=_dates(s["observedFrom"], s["observedTo"], locale),
                picks=picks,
            )
        )
    if data.get("unmatched"):
        lines.append(tr(locale, "basketUnmatched", n=data["unmatched"]))
    lines.append(tr(locale, "basketSum"))
    lines.append(tr(locale, "perChain"))
    lines.append(tr(locale, "noStock"))
    if restricted:
        lines.append(tr(locale, "restrictedPrices"))
    return "\n".join(lines)


# --- the card on a phone: a QR of the card page (MCP 2.2) ----------------------------

QR_MAX_MODULES = 61


def card_qr(site_url: Any, channel: str) -> dict | None:
    """A QR code of the card page, as rows of "0"/"1" the widget draws itself
    (it may load nothing from outside). The link is the card page with
    ``src=<channel>-qr``, so a scan is attributable to the channel — never to a
    person. None when there is no usable https link or the encoder is missing."""
    if not isinstance(site_url, str) or not _HTTPS.match(site_url):
        return None
    tag = re.sub(r"[^a-z0-9_-]", "", (channel or "mcp").lower())[:21] + "-qr"
    base = site_url.split("#", 1)[0]
    if re.search(r"[?&]src=", base):
        url = re.sub(r"([?&]src=)[^&]*", lambda m: m.group(1) + tag, base, count=1)
    else:
        url = f"{base}{'&' if '?' in base else '?'}src={tag}"
    try:
        import segno

        matrix = segno.make(url, error="m", micro=False).matrix
    except Exception:  # no encoder, or a link it cannot encode: the card stands without
        return None
    rows = ["".join("1" if cell else "0" for cell in row) for row in matrix]
    if not rows or len(rows) > QR_MAX_MODULES or any(len(r) != len(rows) for r in rows):
        return None
    return {"url": url, "rows": rows}


# --- moving a prescription (MCP 2.2) -------------------------------------------------

TRANSFER_STEPS = ("transferStep1", "transferStep2", "transferStep3", "transferStep4")
TRANSFER_NOTES = ("transferNote1", "transferNote2", "transferNote3")


def transfer_data(
    locale: str,
    *,
    family: str | None = None,
    near: dict | None = None,
    nearby: dict | None = None,
    precision: str = "zip",
    restricted: bool = False,
    note: str | None = None,
) -> dict:
    """The transfer view. The steps and notes are our own fixed sentences
    (``labels.TEXT``); the chain's dated card price and its nearest stores come
    from ``/prices/near`` (a drug was named) or ``/pharmacies/nearby``."""
    if restricted:
        return {
            "chain": None, "drug": None, "package": None, "price": None, "steps": [], "notes": [],
            "stores": [], "origin": {"precision": "none"}, "restricted": True, "note": note,
        }  # fmt: skip
    chain = {"family": family, "name": family} if family else None
    price = None
    stores: list[dict] = []
    origin: dict = {"precision": "none"}
    drug = None
    package = None
    if near:
        d = near.get("drug") or {}
        drug = {"slug": d.get("slug"), "name": d.get("name"), "kind": d.get("kind")}
        package = near.get("package") or {}
        origin = near.get("origin") or origin
        for c in near.get("chains") or []:
            if family and c.get("family") == family:
                chain = {"family": family, "name": c.get("name") or family}
                price = dated_price(c.get("price"))
                stores = [_store(s, family=family, name=c.get("name") or family, price=None) for s in c.get("stores") or []]
        if family and price is None:
            for p in near.get("pricesWithoutStores") or []:
                if p.get("family") == family:
                    chain = {"family": family, "name": p.get("name") or family}
                    price = dated_price(p.get("price"))
    elif nearby:
        got = pharmacies_from_nearby(nearby, precision=precision)
        origin = got["origin"]
        stores = [s for s in got["stores"] if s.get("family") == family]
        if stores:
            for c in nearby.get("results") or []:
                if (c.get("family") or c.get("chainCode")) == family and c.get("chain"):
                    chain = {"family": family, "name": c["chain"]}
    return {
        "chain": chain,
        "drug": drug,
        "package": package,
        "price": price,
        "steps": [tr(locale, k) for k in TRANSFER_STEPS],
        "notes": [tr(locale, k) for k in TRANSFER_NOTES],
        "stores": _by_miles(stores)[:3],
        "origin": origin,
        "restricted": False,
        "note": None,
    }


def transfer_text(data: dict, locale: str = "en") -> str:
    chain = data.get("chain") or {}
    head = tr(locale, "transferHead", name=chain["name"]) if chain.get("name") else tr(locale, "transferHeadAny")
    lines = [f"**{head}**"]
    if data.get("drug") and (price := dated(data.get("price"), locale)):
        lines.append(f"{package_label(data['drug'], data.get('package'), locale)} — {chain.get('name')}: {price}")
    lines += [f"{i}. {s}" for i, s in enumerate(data.get("steps") or [], 1)]
    lines += [f"- {n}" for n in data.get("notes") or []]
    stores = data.get("stores") or []
    for s in stores:
        addr = ", ".join(p for p in (s.get("address"), s.get("city")) if p)
        miles = f" — {tr(locale, 'milesShort', n=s['miles'])}" if s.get("miles") is not None else ""
        lines.append(f"- {s.get('name')}{', ' + addr if addr else ''}{miles}")
    if stores:
        lines.append(tr(locale, "osm"))
    return "\n".join(lines)


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
