"""Behaviour of the 2.0 tools over a mocked public API (respx, fixtures/api).

Listing goes through a REAL in-memory MCP session so the schemas and metadata
we assert are the ones a client receives; so do the tool calls (``call``).
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from conftest import body_of, call, fx, params_of, text_of
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import ImageContent

from finerx_mcp import __version__, server
from finerx_mcp.client import FinerxClient
from finerx_mcp.labels import LOCALES, labels_for
from finerx_mcp.limits import Limiter
from finerx_mcp.widget import APP_URI, APP_URI_V21, WIDGET_URI

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PNG = b"\x89PNG\r\n\x1a\nfake"


# --- listing ---------------------------------------------------------------------


async def test_lists_the_phase_one_and_two_tools() -> None:
    """Every 2.0 tool is still listed (2.1 only adds) + the two phase-2 tools."""
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        names = {t.name for t in (await session.list_tools()).tools}
    assert names - {"open_price_finder", "ui_suggest", "ui_equivalent"} == {
        "search_drugs",
        "get_drug",
        "compare_prices",
        "find_nearby_pharmacies",
        "get_dataset_info",
        "get_savings_card",
        "email_savings_card",
        "get_prescription_options",
        "find_us_equivalent",
        "foreign_brands_for_drug",
        "ui_prices",
        "ui_nearby",
    }
    assert {"open_price_finder", "ui_suggest"} <= names


async def test_version_is_the_release_candidate() -> None:
    assert __version__ == "2.1.0"
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        init = await session.initialize()
    assert init.serverInfo.version == "2.1.0"


def test_instructions_carry_the_card_rule() -> None:
    instructions = server.mcp._mcp_server.instructions
    assert instructions == server.INSTRUCTIONS
    for phrase in (
        "compare_prices",
        "get_savings_card",
        "email_savings_card",
        "find_us_equivalent",
        "quote its guidance sentence",
        "observation date",
        "card.law",
        "card.fine",
        "card.chainsCount",
        "12 languages",
        "no route to a prescription",
    ):
        assert phrase in instructions, phrase
    # Positioning order: prices + card first, analogs/languages next, honesty after.
    assert instructions.index("compare_prices") < instructions.index("find_us_equivalent") < instructions.index("The card rule")
    assert "isLowest" not in instructions


async def test_lists_resources_and_prompts() -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        resources = await session.list_resources()
        prompts = await session.list_prompts()
    assert {str(r.uri) for r in resources.resources} == {
        APP_URI,
        APP_URI_V21,
        WIDGET_URI,
        "finerx://card",
        "finerx://how-it-works",
    }
    assert {p.name for p in prompts.prompts} == {"price_and_card", "prescription_help", "us_equivalent"}


async def test_prompt_renders_the_card_offer() -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        got = await session.get_prompt("price_and_card", {"drug": "atorvastatin"})
    text = got.messages[0].content.text
    assert "atorvastatin" in text and "observation date" in text and "free discount card" in text


async def test_how_it_works_has_no_lowest_and_no_most_pharmacies() -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        text = (await session.read_resource("finerx://how-it-works")).contents[0].text
    assert "lowest" not in text.lower() and "most pharmacies" not in text.lower() and "most us pharmacies" not in text.lower()
    assert "34+ pharmacy chains" in text and "Prices via FineRx" in text


async def test_card_resource_renders_codes_and_law_but_not_the_site_faq(api) -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        text = (await session.read_resource("finerx://card")).contents[0].text
    assert "BIN 610219 · PCN DRX · Group MYCARD3993" in text
    assert "1. Show the pharmacist the card" in text
    assert "Usually" not in text  # the site FAQ carries banned words; never forwarded


# --- compare_prices / ui_prices ----------------------------------------------------


async def test_compare_prices_one_call_for_the_answer(api) -> None:
    result = await call("compare_prices", {"drug": "atorvastatin", "strength": "10 mg", "zip": "33101", "locale": "es"})
    body = body_of(api["near"])
    assert body == {"drug": "atorvastatin", "strength": "10 mg", "zip": "33101", "locale": "es", "channel": "mcp"}
    assert api["options"].called  # the chips
    sc = result.structuredContent
    assert sc["locale"] == "es" and sc["dir"] == "ltr"
    meta = result.meta or {}
    assert meta["finerx/labels"]["allPharmacies"] == "Todas las farmacias"
    assert len(meta["finerx/allChains"]) == 7
    text = text_of(result)
    # The headings follow the reader's language (labels.tr); amounts and dates are data.
    assert "cerca de Miami, FL (código postal 33101)" in text
    assert "Walmart (sin tienda cercana): $11.62 con la tarjeta, observado el 2026-09-20" in text
    assert "near Miami" not in text and "with the card, observed" not in text


async def test_compare_prices_in_arabic_is_rtl(api) -> None:
    result = await call("compare_prices", {"drug": "atorvastatin", "zip": "33101"}, meta={"openai/locale": "ar"})
    assert result.structuredContent["dir"] == "rtl"
    assert result.meta["finerx/labels"]["copy"] == "نسخ"


async def test_compare_prices_needs_a_drug(api) -> None:
    result = await call("compare_prices", {})
    assert result.structuredContent["error"]["code"] == "drug_required"
    assert not api["near"].called


async def test_unknown_drug_offers_the_close_matches(api) -> None:
    api["near"].respond(404, json=fx("drug_not_found"))
    result = await call("compare_prices", {"drug": "atorvastatinz"})
    assert "Atorvastatin Calcium (slug atorvastatin-calcium)" in text_of(result)
    assert result.structuredContent["error"]["suggestions"][0]["slug"] == "atorvastatin-calcium"


async def test_other_quantities_are_named_never_scaled(api) -> None:
    near = fx("prices_near")
    near["package"]["quantity"] = 45
    near["coverage"] = {"status": "other_quantities", "quantities": [30, 90]}
    for c in near["chains"]:
        c["price"] = None
    near["pricesWithoutStores"] = []
    near["card"]["priceWithCard"] = None
    api["near"].respond(json=near)
    text = text_of(await call("compare_prices", {"drug": "atorvastatin", "quantity": 45, "zip": "33101"}))
    assert "We have not seen a card price for 45" in text
    assert "30, 90" in text
    assert "no card price seen for this package" in text


async def test_walmart_zone_is_named(api) -> None:
    api["near"].respond(json=fx("prices_near_needs_zip"))
    text = text_of(await call("compare_prices", {"drug": "atorvastatin"}))
    assert "no place given" in text
    assert "Walmart: $13.80" in text  # the default zone is not labelled


async def test_ui_prices_uses_the_host_location_and_the_slug(api) -> None:
    meta = {"openai/userLocation": {"latitude": 30.2672, "longitude": -97.7431, "country": "US"}}
    result = await call("ui_prices", {"slug": "atorvastatin-calcium", "quantity": 90}, meta=meta)
    body = body_of(api["near"])
    assert body["drug"] == "atorvastatin-calcium" and body["quantity"] == 90
    assert (body["lat"], body["lon"]) == (30.27, -97.74)
    assert body["channel"] == "chatgpt"
    assert result.structuredContent["view"] == "prices"


# --- pharmacies -------------------------------------------------------------------------


async def test_nearby_without_a_drug_lists_stores(api) -> None:
    result = await call("find_nearby_pharmacies", {"zip": "33101", "chains": "walgreens,publix"})
    params = params_of(api["nearby"])
    assert params["zip"] == "33101" and params["family"] == "walgreens,publix"
    data = result.structuredContent["data"]
    assert [s["family"] for s in data["stores"]] == ["publix", "walgreens"]  # by distance
    assert data["origin"]["precision"] == "zip"
    assert "OpenStreetMap" in text_of(result)


async def test_nearby_with_a_drug_carries_each_chains_card_price(api) -> None:
    result = await call("find_nearby_pharmacies", {"zip": "33101", "drug": "atorvastatin", "family": "cvs,kroger"})
    assert not api["nearby"].called
    stores = result.structuredContent["data"]["stores"]
    assert {s["family"] for s in stores} == {"cvs", "kroger"}
    kroger = next(s for s in stores if s["family"] == "kroger")
    assert kroger["kind"] == "store" and kroger["price"] == {"amount": 44.0, "observedAt": "2026-09-16"}
    assert "pharmacy in store, not verified" in text_of(result)


async def test_ui_nearby_filters_by_family(api) -> None:
    await call("ui_nearby", {"zip": "33101", "family": "publix"})
    assert params_of(api["nearby"])["family"] == "publix"


# --- the card ----------------------------------------------------------------------------


async def test_card_for_a_text_host_includes_the_png(api, monkeypatch) -> None:
    async def _png(url: str) -> bytes:
        return PNG

    monkeypatch.setattr(server, "_card_image_bytes", _png)
    result = await call("get_savings_card", {})
    assert [c.type for c in result.content] == ["text", "image"]
    assert isinstance(result.content[1], ImageContent)


@pytest.mark.parametrize(
    "meta",
    [
        {"openai/locale": "en-US", "openai/userAgent": "ChatGPT"},
        {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}},
    ],
)
async def test_card_for_a_ui_host_has_no_png(api, monkeypatch, meta) -> None:
    async def _png(url: str) -> bytes:
        return PNG

    monkeypatch.setattr(server, "_card_image_bytes", _png)
    result = await call("get_savings_card", {}, meta=meta)
    assert [c.type for c in result.content] == ["text"]
    assert result.structuredContent["view"] == "card"


async def test_card_with_a_drug_quotes_its_dated_price(api) -> None:
    result = await call("get_savings_card", {"drug": "atorvastatin-calcium"})
    assert "$11.99 with the card at Hy-Vee, observed 2026-09-20" in text_of(result)
    data = result.structuredContent["data"]
    assert data["drug"]["slug"] == "atorvastatin-calcium"
    assert data["priceWithCard"]["observedAt"] == "2026-09-20"


async def test_card_with_an_unknown_drug_still_answers(api) -> None:
    api["card_prices"].respond(404, json=fx("drug_not_found"))
    result = await call("get_savings_card", {"drug": "nope"})
    assert "No card price on file" in text_of(result)
    assert result.structuredContent["data"]["priceWithCard"] is None


async def test_card_uses_the_hosts_locale(api) -> None:
    await call("get_savings_card", {}, meta={"openai/locale": "es-419"})
    assert params_of(api["card"])["locale"] == "es"
    await call("get_savings_card", {"locale": "pt"}, meta={"openai/locale": "es-419"})
    assert params_of(api["card"])["locale"] == "pt"


async def test_card_endpoint_is_cached_per_language(api) -> None:
    await call("get_savings_card", {})
    await call("search_drugs", {"query": "atorva"})
    assert api["card"].call_count == 1


# --- email ---------------------------------------------------------------------------------


async def test_email_refuses_without_consent_and_never_posts(api) -> None:
    result = await call("email_savings_card", {"email": "jane@example.com"})
    sc = result.structuredContent
    assert sc["sent"] is False and sc["error"].startswith("consent required")
    assert not api["card_email"].called
    assert sc["card"]["codes"]["bin"] == "610219"


async def test_email_masks_the_address_on_success(api) -> None:
    result = await call("email_savings_card", {"email": "jane@example.com", "consent": True})
    assert body_of(api["card_email"]) == {"email": "jane@example.com", "locale": "en", "consent": True}
    sc = result.structuredContent
    assert sc == {**sc, "sent": True, "to": "j***@example.com"}
    assert "jane@example.com" not in text_of(result)


@pytest.mark.parametrize(
    ("status", "fragment"),
    [
        (429, "too many card emails"),
        (503, "email delivery is not available right now"),
        (502, "the email provider failed"),
        (422, "that address was not accepted"),
    ],
)
async def test_email_maps_api_errors(api, status: int, fragment: str) -> None:
    api["card_email"].respond(status, json={"detail": "raw"}, headers={"Retry-After": "30"} if status == 429 else {})
    sc = (await call("email_savings_card", {"email": "jane@example.com", "consent": True})).structuredContent
    assert sc["sent"] is False and fragment in sc["error"] and sc["status"] == status
    if status == 429:
        assert sc["retryAfter"] == "30"


# --- catalog ---------------------------------------------------------------------------------


async def test_search_gives_card_from_prices_with_package_and_date(api) -> None:
    sc = (await call("search_drugs", {"query": "atorva"})).structuredContent
    first = sc["results"][0]
    assert first["fromCardPrice"] == {"amount": 9.4, "observedAt": "2026-09-21", "package": "30 × 20mg Tablet"}
    assert "fromPrice" not in first


async def test_search_carries_the_foreign_brands(api) -> None:
    body = fx("search")
    body["results"] = []
    body["foreignBrands"] = [
        {"brand": "Nurofen", "brandSlug": "nurofen", "countries": ["RU", "UA"], "inn": "ibuprofen", "usGeneric": "ibuprofen"}
    ]
    api["search"].respond(json=body)
    result = await call("search_drugs", {"query": "нурофен"})
    assert result.structuredContent["foreignBrands"][0]["brandSlug"] == "nurofen"
    assert "call find_us_equivalent" in text_of(result)


async def test_get_drug_has_configs_not_package_counts(api) -> None:
    sc = (await call("get_drug", {"slug": "atorvastatin-calcium"})).structuredContent
    assert sc["defaultConfig"] == {"form": "Tablet", "strength": "10mg", "quantity": 30}
    assert sc["configs"][0]["quantities"][0]["cardFrom"]["observedAt"] == "2026-09-20"
    assert sc["defaultPackage"]["chains"][1]["zone"] == "tx"
    assert "packageCount" not in str(sc) and "stats" not in sc


async def test_get_drug_unknown(api) -> None:
    api["card_prices"].respond(404, json=fx("drug_not_found"))
    sc = (await call("get_drug", {"slug": "nope"})).structuredContent
    assert sc["error"]["code"] == "drug_not_found"


async def test_dataset_info_is_card_coverage_without_the_card(api) -> None:
    result = await call("get_dataset_info", {})
    sc = result.structuredContent
    assert sc["families"] == 3 and sc["asOf"] == "2026-09-22" and sc["storesOnMap"] == 17733
    assert "savingsPrograms" not in sc and "prices" not in sc and "card" not in sc


async def test_prescription_options_pass_through_with_the_card(api) -> None:
    result = await call("get_prescription_options", {"drug": "atorvastatin-calcium"})
    sc = result.structuredContent
    assert sc["restricted"] is False
    assert sc["noPrescription"]["options"][0]["name"] == "A community health center"
    assert "Medicaid may cover it." in text_of(result)


# --- foreign brands -----------------------------------------------------------------------


async def test_find_us_equivalent_returns_the_vetted_sentence(api) -> None:
    result = await call("find_us_equivalent", {"brand": "Нурофен"})
    sc = result.structuredContent
    assert params_of(api["analog_search"])["q"] == "Нурофен"
    assert sc["guidance"] == fx("analog_entry")["guidance"]
    assert sc["guidance"] in text_of(result)
    assert sc["guidanceDisclaimer"].startswith("Same active ingredient does not mean")
    assert sc["usDrug"]["fromCardPrice"]["observedAt"] == "2026-09-21"
    assert "savingsCard" not in sc


async def test_find_us_equivalent_prefers_the_asked_for_country(api) -> None:
    search = fx("analog_search")
    search["results"] = [
        {**search["results"][0], "brand": "No-Spa", "brandSlug": "no-spa", "countries": ["RU", "UA", "BY", "KZ"]},
        {**search["results"][0], "brand": "No-Spa", "brandSlug": "no-spa-poland", "countries": ["Poland"]},
    ]
    api["analog_search"].respond(json=search)
    sc = (await call("find_us_equivalent", {"brand": "No-Spa", "country": "poland"})).structuredContent
    assert str(api["analog"].calls[-1].request.url).split("?")[0].endswith("/analogs/no-spa-poland")
    assert sc["otherMatches"] == [{"brand": "No-Spa", "countries": ["RU", "UA", "BY", "KZ"], "brandSlug": "no-spa"}]
    # "us" must never substring-match "Russia": unknown country → the top match.
    await call("find_us_equivalent", {"brand": "No-Spa", "country": "us"})
    assert str(api["analog"].calls[-1].request.url).split("?")[0].endswith("/analogs/no-spa")


async def test_find_us_equivalent_reports_no_match(api) -> None:
    api["analog_search"].respond(json={"query": "x", "count": 0, "results": []})
    sc = (await call("find_us_equivalent", {"brand": "zzzqqq"})).structuredContent
    assert sc["found"] is False
    assert sc["hint"] == "no foreign brand matched; try the active ingredient with search_drugs"
    assert "guidance" not in sc and sc["card"]["codes"]["group"] == "MYCARD3993"


async def test_foreign_brands_for_drug(api) -> None:
    sc = (await call("foreign_brands_for_drug", {"slug": "ibuprofen"})).structuredContent
    assert sc["brands"] == [
        {"brand": "Nurofen", "brandScript": "Нурофен", "countries": ["RU", "UA"], "inn": "ibuprofen", "usClass": "same_inn"}
    ]


# --- limits, concurrency, packaging -------------------------------------------------------


def test_limiter_buckets() -> None:
    lim = Limiter()
    assert all(lim.check("model", "a", now=0.0) == 0 for _ in range(30))
    assert lim.check("model", "a", now=0.0) >= 1  # 31st in the same instant
    assert lim.check("model", "b", now=0.0) == 0  # another person is unaffected
    assert lim.check("model", "a", now=2.1) == 0  # one token back after 2 s
    assert all(lim.check("ui", "a", now=0.0) == 0 for _ in range(90))
    assert lim.check("ui", "a", now=0.0) >= 1
    anon = Limiter()
    assert all(anon.check("model", None, now=0.0) == 0 for _ in range(300))
    assert anon.check("ui", None, now=0.0) >= 1


def test_limiter_day_cap() -> None:
    lim = Limiter()
    t = 0.0
    for _ in range(400):
        t += 2.0  # well under 30/min
        assert lim.check("model", "a", now=t) == 0
    assert lim.check("model", "a", now=t + 100) > 60


async def test_rate_limited_call_answers_with_the_card(api, monkeypatch) -> None:
    monkeypatch.setattr(server.LIMITER, "check", lambda kind, subject: 7)
    result = await call("compare_prices", {"drug": "atorvastatin"}, meta={"openai/subject": "s"})
    assert "try again in 7 s" in text_of(result)
    sc = result.structuredContent
    assert sc["error"] == {"code": "rate_limited", "retryAfter": 7}
    assert sc["card"]["codes"]["group"] == "MYCARD3993"
    assert not api["near"].called


async def test_calls_run_concurrently(api) -> None:
    """The client is async: two slow API answers overlap instead of queueing."""
    import httpx

    async def _slow(request):
        await asyncio.sleep(0.3)
        return httpx.Response(200, json=fx("chains") if "chains" in str(request.url) else fx("meta"))

    api["chains"].mock(side_effect=_slow)
    api["meta"].mock(side_effect=_slow)
    started = asyncio.get_running_loop().time()
    await asyncio.gather(call("get_dataset_info", {}), call("get_dataset_info", {}))
    assert asyncio.get_running_loop().time() - started < 0.55


async def test_client_without_a_key_fails_soft(monkeypatch) -> None:
    monkeypatch.setenv("FINERX_API_KEY", "")
    server._client = FinerxClient(api_key="")
    result = await call("compare_prices", {"drug": "atorvastatin"})
    assert result.structuredContent["card"]["codes"]["bin"] == "610219"


def test_labels_cover_every_locale_and_keep_placeholders() -> None:
    import re

    en = labels_for("en")
    assert len(LOCALES) == 12
    for loc in LOCALES:
        got = labels_for(loc)
        assert set(got) == set(en), loc
        for key, value in got.items():
            assert set(re.findall(r"\{(\w+)\}", value)) == set(re.findall(r"\{(\w+)\}", en[key])), (loc, key)


def test_wheel_ships_both_bundles(tmp_path: Path) -> None:
    if shutil.which("uv") is None:  # pragma: no cover - depends on the machine
        pytest.skip("uv is not installed")
    built = subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path)], cwd=PACKAGE_ROOT, capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    wheels = list(tmp_path.glob("*.whl"))
    assert wheels and "2.1.0" in wheels[0].name
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
    assert "finerx_mcp/widget/app.v2.html" in names
    assert "finerx_mcp/widget/savings_card.html" in names
    assert not any("widget-src" in n or "node_modules" in n for n in names)


def test_dose_and_pack_size_are_pulled_out_of_free_text():
    """A model often writes the dose into the name; the default package would
    then quote the wrong dose ("atorvastatin 20 mg" answered with 10 mg)."""
    from finerx_mcp.server import _split_drug_text as split

    assert split("atorvastatin 20 mg", None, None) == ("atorvastatin", "20 mg", None)
    assert split("Adderall 20mg 60 tablets", None, None) == ("Adderall", "20 mg", 60)
    assert split("lisinopril 10mg x90", None, None) == ("lisinopril", "10 mg", 90)
    assert split("insulin glargine 100 units/ml", None, None) == ("insulin glargine", "100 units/ml", None)
    assert split("amoxicillin 250 mg/5 ml suspension", None, None) == ("amoxicillin suspension", "250 mg/5ml", None)
    # explicit arguments win; plain names and slugs pass through untouched
    assert split("atorvastatin 20 mg", "40 mg", 90) == ("atorvastatin 20 mg", "40 mg", 90)
    assert split("atorvastatin-calcium", None, None) == ("atorvastatin-calcium", None, None)
    assert split("estradiol", None, None) == ("estradiol", None, None)
