"""MCP 2.2 — ``find_us_equivalents``: the list of medicines a person brought from
another country. Held here: each entry is the reviewed one, guidance verbatim;
a US product (and its price) appears ONLY for the same active ingredient; names
that matched nothing are counted, never echoed or guessed; the next step prices
only the same-ingredient ones."""
from __future__ import annotations

import json

import httpx
from conftest import call, fx, text_of, url

from finerx_mcp import schemas
from finerx_mcp.card_law import BANNED_RE, undated_amounts

NOSPA = {
    **fx("analog_entry"),
    "brand": "No-Spa",
    "brandSlug": "no-spa",
    "brandScript": "Но-шпа",
    "countries": ["RU", "PL"],
    "inn": "drotaverine",
    "usClass": "rx_alternative",
    "usGeneric": "dicyclomine",
    "usBrands": [],
    "usDrug": {"slug": "dicyclomine-hcl", "name": "Dicyclomine HCl", "url": "https://www.finerxfinder.com/en/drug/dicyclomine-hcl"},
    "guidance": "No-Spa (drotaverine) is not sold in the US. Ask a US clinician about the options for your symptoms.",
}
SEARCH = {
    "нурофен": [fx("analog_search")["results"][0]],
    "no-spa": [{"brand": "No-Spa", "brandSlug": "no-spa", "countries": ["RU", "PL"], "usClass": "rx_alternative"}],
}


def route(api, router_entries: dict[str, dict] | None = None) -> None:
    entries = router_entries or {"nurofen": fx("analog_entry"), "no-spa": NOSPA}

    def search(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("q", "").lower()
        return httpx.Response(200, json={"results": SEARCH.get(q, [])})

    def entry(request: httpx.Request) -> httpx.Response:
        slug = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=entries[slug]) if slug in entries else httpx.Response(404, json={"detail": "unknown foreign brand"})

    api["analog_search"].mock(side_effect=search)
    api["analog"].mock(side_effect=entry)


async def test_one_entry_per_medicine_guidance_verbatim(api) -> None:
    route(api)
    result = await call("find_us_equivalents", {"brands": ["Нурофен", "No-Spa"]})
    sc = result.structuredContent
    schemas.validate(sc)
    items = sc["data"]["items"]
    assert [i["brand"] for i in items] == ["Nurofen", "No-Spa"]
    assert items[0]["guidance"] == fx("analog_entry")["guidance"]
    assert items[1]["guidance"] == NOSPA["guidance"]
    text = text_of(result)
    assert fx("analog_entry")["guidance"] in text and NOSPA["guidance"] in text
    assert undated_amounts(text) == [] and not BANNED_RE.search(text)


async def test_a_us_product_only_for_the_same_active_ingredient(api) -> None:
    route(api)
    result = await call("find_us_equivalents", {"brands": ["Нурофен", "No-Spa"]})
    same, alt = result.structuredContent["data"]["items"]
    assert same["usClass"] == "same_inn" and same["us"]["slug"] == "atorvastatin-calcium"
    assert same["us"]["cardFrom"]["observedAt"]
    assert alt["usClass"] == "rx_alternative" and alt["us"] is None
    blob = json.dumps(result.structuredContent) + text_of(result)
    assert "dicyclomine" not in blob.lower()


async def test_names_that_match_nothing_are_counted_not_echoed(api) -> None:
    route(api)
    result = await call("find_us_equivalents", {"brands": ["Нурофен", "Zzqqbrand", "No-Spa"]})
    sc = result.structuredContent
    assert sc["data"]["unmatched"] == 1 and len(sc["data"]["items"]) == 2
    assert "zzqqbrand" not in json.dumps(sc).lower()
    assert "1 of the names matched no reviewed brand" in text_of(result)


async def test_nothing_matched_is_an_error_with_the_card(api) -> None:
    route(api)
    sc = (await call("find_us_equivalents", {"brands": ["Zzqq", "Qqzz"]})).structuredContent
    env = schemas.validate(sc)
    assert env.data is None and env.error.code == "not_found" and sc["card"]["codes"]["pcn"] == "DRX"


async def test_api_down_is_said(api) -> None:
    api["analog_search"].respond(503)
    sc = (await call("find_us_equivalents", {"brands": ["Нурофен", "No-Spa"]})).structuredContent
    assert sc["error"]["code"] == "api_unavailable"


async def test_more_than_six_are_cut_to_six(api) -> None:
    route(api)
    await call("find_us_equivalents", {"brands": ["Нурофен"] * 9})
    assert api["analog_search"].call_count == 6


async def test_next_prices_only_the_same_ingredient_ones(api) -> None:
    route(api)
    steps = (await call("find_us_equivalents", {"brands": ["Нурофен", "No-Spa"]})).structuredContent["next"]
    assert steps[0]["tool"] == "compare_prices" and steps[0]["args"] == {"drug": "atorvastatin-calcium"}
    assert "dicyclomine-hcl" not in json.dumps(steps)
    only_alt = (await call("find_us_equivalents", {"brands": ["No-Spa"]})).structuredContent
    assert "next" not in only_alt


async def test_two_same_ingredient_medicines_lead_to_the_basket(api) -> None:
    second = {**fx("analog_entry"), "brand": "Panadol", "brandSlug": "panadol", "usDrug": {"slug": "acetaminophen", "name": "Acetaminophen"}}
    SEARCH["panadol"] = [{"brand": "Panadol", "brandSlug": "panadol", "countries": ["UK"], "usClass": "same_inn"}]
    try:
        route(api, {"nurofen": fx("analog_entry"), "panadol": second})
        steps = (await call("find_us_equivalents", {"brands": ["Нурофен", "Panadol"]})).structuredContent["next"]
        assert steps[0]["tool"] == "compare_basket"
        assert steps[0]["args"] == {"drugs": ["atorvastatin-calcium", "acetaminophen"]}
    finally:
        SEARCH.pop("panadol")


async def test_a_restricted_ingredient_in_the_list_makes_the_law_plain(api) -> None:
    oxy = {**fx("analog_entry"), "brand": "Oxybrand", "brandSlug": "oxybrand", "inn": "oxycodone", "usGeneric": "oxycodone"}
    SEARCH["oxybrand"] = [{"brand": "Oxybrand", "brandSlug": "oxybrand", "countries": ["DE"], "usClass": "same_inn"}]
    try:
        route(api, {"nurofen": fx("analog_entry"), "oxybrand": oxy})
        sc = (await call("find_us_equivalents", {"brands": ["Нурофен", "Oxybrand"]})).structuredContent
        assert "substantial" not in sc["card"]["law"]
    finally:
        SEARCH.pop("oxybrand")
