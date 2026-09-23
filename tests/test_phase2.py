"""MCP 2.1 (phase 2, contract C2'): the search, a place typed as text, the
equivalent and rx views, the per-person email cap — and what must NOT happen:
a typed place in a log, a schema the model sees, an echo, or a foreign brand
offered as the US product when it is a different medicine."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest
from conftest import body_of, call, fx, params_of, text_of

from finerx_mcp import card_law, hosts, schemas, server
from finerx_mcp.card_law import BANNED_RE, RESTRICTED_LAW, undated_amounts
from finerx_mcp.labels import EN, PHASE2_EN, _T, labels_for

ADDRESS = "233 S Wacker Dr, Chicago"
SUBJECT = "v1/sub-7f3a9c-secret-person"
CHATGPT = {
    "openai/subject": SUBJECT,
    "openai/locale": "en-US",
    "openai/userLocation": {"country": "US", "latitude": 25.774312, "longitude": -80.193654},
}
WIDGET_LABELS = Path(__file__).resolve().parents[1] / "widget-src" / "src" / "labels.ts"


def _blob(result) -> str:
    return json.dumps(result.structuredContent, ensure_ascii=False) + text_of(result)


# --- open_price_finder --------------------------------------------------------------


async def test_the_search_opens_with_popular_medicines_and_no_api_search(api) -> None:
    result = await call("open_price_finder", {})
    sc = result.structuredContent
    assert sc["view"] == "search" and sc["schema"] == "finerx.view/2"
    data = sc["data"]
    assert data["query"] is None and data["suggestions"] == [] and data["origin"] is None
    assert len(data["popular"]) == 8
    assert all(not card_law.is_restricted(p["slug"], p["name"]) for p in data["popular"])
    assert not api["suggest"].called
    assert "Often searched:" in text_of(result)
    assert result.meta["finerx/labels"]["searchTitle"] == "Find a medicine"


def test_popular_list_is_slugs_and_never_a_restricted_medicine() -> None:
    assert len(server.POPULAR) == 8
    for slug, name in server.POPULAR:
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug)
        assert not card_law.is_restricted(slug, name), slug


async def test_a_query_prefills_the_search_with_dated_matches(api) -> None:
    result = await call("open_price_finder", {"query": "atorva", "locale": "es"})
    params = params_of(api["suggest"])
    assert params == {"q": "atorva", "limit": "8", "locale": "es"}
    data = result.structuredContent["data"]
    assert data["query"] == "atorva"
    assert data["suggestions"][0] == {
        "slug": "atorvastatin-calcium",
        "name": "Atorvastatin Calcium",
        "kind": "generic",
        "matchedAlias": "atorvastatin",
        "cardFrom": {"amount": 9.0, "observedAt": "2026-09-20"},
    }
    text = text_of(result)
    assert "$9.00" in text and undated_amounts(text) == []
    assert result.meta["finerx/labels"]["searchTitle"] == "Buscar un medicamento"


async def test_a_foreign_brand_leads_to_a_us_product_only_for_the_same_ingredient(api) -> None:
    data = (await call("open_price_finder", {"query": "atorva"})).structuredContent["data"]
    by = {b["brand"]: b for b in data["foreignBrands"]}
    assert by["Atoris"]["usSlug"] == "atorvastatin-calcium" and by["Atoris"]["usClass"] == "same_inn"
    # No-Spa is drotaverine; dicyclomine is a DIFFERENT medicine — never "in the US: dicyclomine".
    assert by["No-Spa"]["usClass"] == "rx_alternative"
    assert by["No-Spa"]["usSlug"] is None and by["No-Spa"]["usName"] is None
    assert by["Analgin"]["usSlug"] is None
    assert "dicyclomine" not in json.dumps(data).lower()


async def test_the_search_still_opens_when_suggest_fails(api) -> None:
    api["suggest"].respond(503)
    result = await call("open_price_finder", {"query": "atorva"})
    sc = result.structuredContent
    assert sc["view"] == "search" and "error" not in sc
    assert sc["data"]["suggestions"] == [] and len(sc["data"]["popular"]) == 8


async def test_a_restricted_query_gets_the_plain_law(api) -> None:
    result = await call("open_price_finder", {"query": "adderall"})
    assert result.structuredContent["card"]["law"] == RESTRICTED_LAW["en"]


# --- ui_suggest -----------------------------------------------------------------------


async def test_ui_suggest_answers_results_and_foreign_brands(api) -> None:
    result = await call("ui_suggest", {"q": "atorva"})
    sc = result.structuredContent
    assert result.isError is False
    assert [r["slug"] for r in sc["results"]] == ["atorvastatin-calcium", "lipitor"]
    assert sc["results"][1]["cardFrom"] is None
    schemas.SuggestResult.model_validate(sc)


async def test_ui_suggest_needs_two_characters_before_it_asks_the_api(api) -> None:
    result = await call("ui_suggest", {"q": " a "})
    assert result.structuredContent["results"] == [] and not api["suggest"].called


async def test_ui_suggest_failure_is_an_error_for_the_card(api) -> None:
    api["suggest"].respond(503)
    result = await call("ui_suggest", {"q": "atorva"})
    assert result.isError is True
    assert result.structuredContent["error"]["code"] == "api_unavailable"
    assert result.structuredContent["card"]["codes"]["bin"] == "610219"


def _suggest_with(results: list[dict], foreign: list[dict] | None = None) -> dict:
    return {"results": results, "foreignBrands": foreign or [], "meta": {}}


async def test_ui_suggest_judges_the_card_law_by_every_suggestion(api) -> None:
    """Typing "oxy" is not a restricted word; Oxycodone among the results is."""
    api["suggest"].respond(json=_suggest_with([
        {"slug": "oxybutynin-chloride", "name": "Oxybutynin Chloride", "kind": "generic", "matchedAlias": None,
         "cardFrom": None},
        {"slug": "oxycodone-hcl", "name": "Oxycodone HCl", "kind": "generic", "matchedAlias": None,
         "cardFrom": {"amount": 12.0, "observedAt": "2026-09-20"}},
    ]))
    assert not card_law.is_restricted("oxy")
    sc = (await call("ui_suggest", {"q": "oxy"})).structuredContent
    assert sc["card"]["law"] == RESTRICTED_LAW["en"]
    opened = (await call("open_price_finder", {"query": "oxy"})).structuredContent
    assert opened["card"]["law"] == RESTRICTED_LAW["en"]


async def test_ui_suggest_restricted_via_a_foreign_brand_or_an_alias(api) -> None:
    api["suggest"].respond(json=_suggest_with(
        [], [{"brand": "Zzbrand", "brandSlug": "zzbrand", "countries": ["MX"], "usClass": "same_inn",
              "usSlug": "adderall", "usName": "Adderall"}],
    ))
    assert (await call("ui_suggest", {"q": "zzb"})).structuredContent["card"]["law"] == RESTRICTED_LAW["en"]
    api["suggest"].respond(json=fx("suggest"))
    plain = await call("ui_suggest", {"q": "atorva"})
    assert plain.structuredContent["card"]["law"] != RESTRICTED_LAW["en"]


async def test_ui_suggest_carries_no_labels(api) -> None:
    """Every keystroke: the card already holds the labels of the search."""
    result = await call("ui_suggest", {"q": "atorva", "locale": "ru"})
    assert "finerx/labels" not in (result.meta or {})
    assert result.meta["finerx/build"]


async def test_typeahead_without_a_subject_has_its_own_bucket(monkeypatch) -> None:
    from finerx_mcp import limits

    lim = limits.Limiter()
    monkeypatch.setattr(limits, "ANON_PER_MIN", 2)
    lim.reset()
    assert lim.check("ui", None, now=0.0) == 0 and lim.check("ui", None, now=0.0) == 0
    assert lim.check("ui", None, now=0.0) > 0  # the shared bucket is empty…
    assert lim.check("suggest", None, now=0.0) == 0  # …the typeahead is not
    # with a subject the typeahead is the person's ui bucket
    for _ in range(limits.UI_PER_MIN):
        assert lim.check("suggest", "s1", now=1.0) == 0
    assert lim.check("ui", "s1", now=1.0) > 0


# --- ui_equivalent: a foreign brand picked in the search ----------------------------------


async def test_ui_equivalent_draws_the_equivalent_view_for_that_brand(api) -> None:
    result = await call("ui_equivalent", {"brand_slug": "nurofen", "locale": "ru"})
    sc = result.structuredContent
    assert sc["view"] == "equivalent" and sc["locale"] == "ru"
    assert str(api["analog"].calls[-1].request.url.path).endswith("/analogs/nurofen")
    assert not api["analog_search"].called  # asked by slug, not searched
    assert sc["data"]["guidance"] == fx("analog_entry")["guidance"]
    assert sc["otherMatches"] == []
    schemas.validate(sc)


@pytest.mark.parametrize("cls", ["rx_alternative", "no_equivalent"])
async def test_ui_equivalent_names_no_us_product_for_another_medicine(api, cls: str) -> None:
    api["analog"].respond(json={**fx("analog_entry"), "usClass": cls})
    sc = (await call("ui_equivalent", {"brand_slug": "nurofen"})).structuredContent
    assert sc["data"]["usClass"] == cls and sc["data"]["us"] is None


async def test_ui_equivalent_refuses_a_non_slug_and_answers_404(api) -> None:
    bad = (await call("ui_equivalent", {"brand_slug": "../drugs/x"})).structuredContent
    assert bad["view"] == "equivalent" and bad["error"]["code"] == "not_found"
    assert not api["analog"].called
    api["analog"].respond(404, json={"detail": "unknown foreign brand"})
    gone = (await call("ui_equivalent", {"brand_slug": "zz-unknown"})).structuredContent
    assert gone["error"]["code"] == "not_found" and gone["card"]["codes"]["bin"] == "610219"


# --- where: a place typed in the card ----------------------------------------------------


async def test_where_goes_into_the_body_as_address_and_wins_over_the_host_location(api) -> None:
    api["near"].respond(json=fx("prices_near_address"))
    result = await call("ui_prices", {"slug": "atorvastatin-calcium", "where": ADDRESS}, meta=CHATGPT)
    body = body_of(api["near"])
    assert body["address"] == ADDRESS
    assert "zip" not in body and "lat" not in body and "lon" not in body
    sc = result.structuredContent
    assert sc["data"]["origin"] == {"zip": "60606", "city": "Chicago", "state": "IL", "precision": "address"}
    assert "near Chicago, IL (ZIP 60606)" in text_of(result)  # the ZIP area, never the address
    assert "Wacker" not in _blob(result)
    schemas.validate(sc)


@pytest.mark.parametrize("where,zip_", [("60606", "60606"), (" 60606-1234 ", "60606")])
async def test_a_zip_typed_in_where_travels_as_a_zip(api, where: str, zip_: str) -> None:
    await call("ui_prices", {"slug": "atorvastatin-calcium", "where": where})
    body = body_of(api["near"])
    assert body["zip"] == zip_ and "address" not in body


async def test_a_zip_argument_wins_over_where(api) -> None:
    await call("ui_prices", {"slug": "atorvastatin-calcium", "zip": "33101", "where": ADDRESS})
    body = body_of(api["near"])
    assert body["zip"] == "33101" and "address" not in body


async def test_where_is_tidied_and_capped_before_it_leaves(api) -> None:
    await call("ui_prices", {"slug": "atorvastatin-calcium", "where": "  12 Main\tSt\n" + "x" * 400})
    address = body_of(api["near"])["address"]
    assert address.startswith("12 Main St x") and len(address) <= 200 and "\n" not in address


async def test_an_unplaced_where_says_so_and_answers_nationally(api) -> None:
    api["near"].respond(json=fx("prices_near_needs_zip"))
    result = await call("ui_prices", {"slug": "atorvastatin-calcium", "where": "Springfield"})
    sc = result.structuredContent
    assert sc["notice"]["code"] == "where_not_found"
    assert sc["data"]["needsZip"] is True
    assert "Springfield" not in _blob(result)
    schemas.validate(sc)


async def test_pharmacies_by_typed_address_geocode_then_list_stores(api) -> None:
    result = await call("ui_nearby", {"where": ADDRESS, "family": "walgreens"})
    assert body_of(api["geocode"]) == {"address": ADDRESS, "locale": "en"}
    params = params_of(api["nearby"])
    assert params["lat"] == "41.88" and params["lon"] == "-87.64" and "zip" not in params
    assert params["family"] == "walgreens"
    sc = result.structuredContent
    assert sc["data"]["origin"] == {"zip": "60606", "city": "Chicago", "state": "IL", "precision": "address"}
    assert "Wacker" not in _blob(result)
    assert not api["near"].called
    schemas.validate(sc)


async def test_pharmacies_by_typed_zip_area_use_the_zip(api) -> None:
    api["geocode"].respond(json={"origin": {"zip": "60606", "city": "Chicago", "state": "IL", "precision": "zip",
                                            "lat": 41.88, "lon": -87.64}})
    await call("ui_nearby", {"where": "Chicago 60606"})
    params = params_of(api["nearby"])
    assert params["zip"] == "60606" and "lat" not in params


async def test_pharmacies_by_an_unplaced_where_ask_again(api) -> None:
    api["geocode"].respond(json={"origin": {"zip": None, "city": None, "state": None, "precision": "none",
                                            "lat": None, "lon": None}})
    result = await call("ui_nearby", {"where": "somewhere nice"})
    assert not api["nearby"].called
    sc = result.structuredContent
    assert sc["notice"]["code"] == "where_not_found"
    assert sc["data"]["origin"]["precision"] == "none"
    schemas.validate(sc)


async def test_pharmacies_for_a_drug_send_where_to_prices_near_only(api) -> None:
    api["near"].respond(json=fx("prices_near_address"))
    await call("ui_nearby", {"where": ADDRESS, "slug": "atorvastatin-calcium"})
    assert body_of(api["near"])["address"] == ADDRESS
    assert not api["geocode"].called and not api["nearby"].called


@pytest.mark.parametrize(
    "name,args",
    [
        ("ui_prices", {"slug": "atorvastatin-calcium", "where": ADDRESS}),
        ("ui_nearby", {"where": ADDRESS}),
        ("ui_nearby", {"where": ADDRESS, "slug": "atorvastatin-calcium"}),
        ("ui_suggest", {"q": "atorva"}),
        ("open_price_finder", {"query": "atorva"}),
        ("find_us_equivalent", {"brand": "Нурофен"}),
        ("get_prescription_options", {"drug": "atorvastatin"}),
    ],
)
async def test_no_typed_place_or_subject_reaches_a_log(api, caplog, name: str, args: dict) -> None:
    caplog.set_level(logging.DEBUG)
    await call(name, args, meta=CHATGPT)
    logged = caplog.text + "\n".join(str(r.args) for r in caplog.records)
    for secret in ("Wacker", "233 S", "41.88", "-87.64", SUBJECT, "25.77"):
        assert secret not in logged, secret
    lines = [r.getMessage() for r in caplog.records if r.name == "finerx_mcp"]
    assert any(line.startswith(f"tool={name} status=ok ms=") for line in lines), lines


# --- email: the per-person cap ---------------------------------------------------------


async def test_card_email_sends_the_subject_hmac_not_the_subject(api) -> None:
    await call("email_savings_card", {"email": "jane@example.com", "consent": True}, meta=CHATGPT)
    headers = api["card_email"].calls[-1].request.headers
    got = headers["X-FineRx-Subject"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{16,128}", got)
    assert SUBJECT not in got and "sub-7f3a9c" not in got
    assert got == hosts.subject_key(type("C", (), {"request_context": type("R", (), {
        "meta": type("M", (), {"model_extra": {"openai/subject": SUBJECT}})()})()})())


async def test_card_email_without_a_subject_sends_no_header(api) -> None:
    await call("email_savings_card", {"email": "jane@example.com", "consent": True})
    assert "X-FineRx-Subject" not in api["card_email"].calls[-1].request.headers


# --- find_us_equivalent → view equivalent ---------------------------------------------


async def test_equivalent_view_quotes_the_api_and_keeps_every_2_0_field(api) -> None:
    result = await call("find_us_equivalent", {"brand": "Нурофен"})
    sc = result.structuredContent
    entry = fx("analog_entry")
    assert sc["view"] == "equivalent"
    data = sc["data"]
    assert data["guidance"] == entry["guidance"]  # verbatim
    assert data["disclaimer"] == entry["disclaimer"]
    assert data["usClass"] == "same_inn" and data["inn"] == "ibuprofen"
    assert data["us"]["slug"] == entry["usDrug"]["slug"]
    assert data["us"]["cardFrom"]["observedAt"]
    for key in ("found", "brand", "guidance", "guidanceDisclaimer", "usDrug", "otherMatches", "usClass"):
        assert key in sc, key  # 2.0 fields ride along
    assert result.meta["finerx/labels"]["pricesInUs"] == "Prices in the US"


@pytest.mark.parametrize("cls", ["rx_alternative", "no_equivalent"])
async def test_equivalent_view_names_no_us_product_for_another_medicine(api, cls: str) -> None:
    entry = fx("analog_entry")
    entry["usClass"] = cls
    api["analog"].respond(json=entry)
    sc = (await call("find_us_equivalent", {"brand": "No-Spa"})).structuredContent
    assert sc["data"]["us"] is None and sc["data"]["usClass"] == cls
    schemas.validate(sc)


async def test_no_foreign_match_draws_the_text_not_an_error(api) -> None:
    api["analog_search"].respond(json={"query": "zzz", "count": 0, "results": []})
    result = await call("find_us_equivalent", {"brand": "zzz"})
    sc = result.structuredContent
    assert sc["found"] is False and sc["view"] == "equivalent"
    assert sc["data"] is None and "error" not in sc


# --- get_prescription_options → view rx ------------------------------------------------


async def test_rx_view_has_the_three_sections_links_and_a_dated_card_price(api) -> None:
    result = await call("get_prescription_options", {"drug": "atorvastatin"})
    sc = result.structuredContent
    assert sc["view"] == "rx"
    data = sc["data"]
    assert data["drug"] == {"slug": "atorvastatin-calcium", "name": "Atorvastatin Calcium", "kind": "generic"}
    assert data["restricted"] is False
    assert [s["title"] for s in data["sections"]] == [
        "If you have a prescription",
        "If you don't have one yet",
        "If the brand costs too much",
    ]
    assert data["sections"][1]["links"] == [
        {"label": "A community health center", "url": "https://findahealthcenter.hrsa.gov"}
    ]
    assert "Medicaid may cover it." in data["sections"][1]["body"]
    fcp = server.views.from_card_price(fx("options"))  # the lowest dated card price of any package
    assert data["cardFrom"] == {"amount": fcp["amount"], "observedAt": fcp["observedAt"]}
    text = text_of(result)
    assert f"Without insurance: with the card from ${fcp['amount']:.2f}" in text and undated_amounts(text) == []
    for key in ("havePrescription", "noPrescription", "brandCostly", "medicaidNote", "disclaimer", "drug"):
        assert key in sc, key  # 2.0 fields ride along


async def test_rx_links_are_https_only_and_keep_their_disclosure(api) -> None:
    rx = fx("prescription_options")
    rx["noPrescription"]["options"] += [
        {"name": "Plain http", "url": "http://example.com", "note": "x", "affiliate": False, "disclosure": None},
        {"name": "Partner", "url": "https://partner.example", "note": "visit", "affiliate": True,
         "disclosure": "FineRx may earn a fee"},
    ]
    api["rx"].respond(json=rx)
    data = (await call("get_prescription_options", {})).structuredContent["data"]
    links = data["sections"][1]["links"]
    assert [link["url"] for link in links] == ["https://findahealthcenter.hrsa.gov", "https://partner.example"]
    assert "FineRx may earn a fee" in links[1]["label"]
    assert "Partner: visit (FineRx may earn a fee)" in data["sections"][1]["body"]
    assert data["drug"] is None


async def test_rx_for_a_name_that_resolves_to_a_restricted_drug(api) -> None:
    api["search"].respond(json={"query": "percocet", "count": 1, "results": [
        {"id": 9, "name": "Oxycodone-Acetaminophen", "slug": "oxycodone-acetaminophen", "kind": "generic"}]})
    api["options"].respond(json={"drug": {"slug": "oxycodone-acetaminophen", "name": "Oxycodone-Acetaminophen",
                                          "kind": "generic"}, "configs": [], "defaultConfig": None})
    result = await call("get_prescription_options", {"drug": "percocet"})
    sc = result.structuredContent
    assert sc["restricted"] is True and sc["data"]["restricted"] is True
    assert sc["data"]["sections"] == [] and sc["data"]["cardFrom"] is None
    assert sc["data"]["drug"]["slug"] == "oxycodone-acetaminophen"  # the "prices with the card" button
    assert not api["rx"].called
    assert sc["card"]["law"] == RESTRICTED_LAW["en"]


async def test_rx_titles_follow_the_reader(api) -> None:
    result = await call("get_prescription_options", {"drug": "atorvastatin", "locale": "ru"})
    sc = result.structuredContent
    # the 2.0 field keeps its meaning (the API's content language); the reader's
    # language rides in the view data
    assert sc["locale"] == fx("prescription_options").get("locale", "ru")
    assert sc["data"]["readerLocale"] == "ru" and sc["dir"] == "ltr"
    schemas.validate(sc)
    assert sc["data"]["sections"][0]["title"] == "Если рецепт есть"
    assert result.meta["finerx/labels"]["rxTitleAny"] == "Как получить рецепт"


# --- labels + instructions ---------------------------------------------------------------


def test_every_widget_label_key_is_served() -> None:
    src = WIDGET_LABELS.read_text(encoding="utf-8")
    block = src.split("FALLBACK_LABELS: Labels = {", 1)[1].split("\n};", 1)[0]
    keys = set(re.findall(r"^\s{2}(\w+):", block, re.M))
    assert keys and keys <= set(EN), sorted(keys - set(EN))


def test_every_locale_translates_every_phase2_key() -> None:
    for loc, table in _T.items():
        missing = set(PHASE2_EN) - set(table)
        assert not missing, (loc, sorted(missing))
        for key in PHASE2_EN:
            assert set(re.findall(r"\{(\w+)\}", table[key])) == set(re.findall(r"\{(\w+)\}", PHASE2_EN[key])), (loc, key)
    for key, value in PHASE2_EN.items():
        assert not BANNED_RE.search(value), key


def test_labels_ship_the_phase2_keys_in_every_language() -> None:
    assert labels_for("zh")["fromWithCard"] == "用卡 {price} 起 · {date}"
    assert labels_for("ar")["backToSearch"] == "العودة إلى البحث"


def test_instructions_name_the_search_and_the_context_from_the_card() -> None:
    new = [ln for ln in server.INSTRUCTIONS.splitlines() if "open_price_finder" in ln or "as context" in ln]
    assert len(new) == 2, new
    for line in new:  # the rest quotes the banned words on purpose, as a ban
        assert not BANNED_RE.search(line), line
