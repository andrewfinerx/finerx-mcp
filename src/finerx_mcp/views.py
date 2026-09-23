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

from typing import Any

from finerx_mcp.labels import tr
from finerx_mcp.schemas import SCHEMA

INLINE_ROWS = 6  # contract C2: rows ≤ 6 inline, the rest counted in moreCount
TEXT_ROWS = 3  # spec §7: the model gets the three first prices
TEXT_STORES = 5
MAX_STORES = 24  # keeps data ≤ ~4 KB
MAX_CONFIGS = 12
MAX_QUANTITIES = 8

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
    if origin.get("precision") == "zip" and origin.get("zip"):
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
