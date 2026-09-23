"""Review fixes of 23.09 (minor): slugs in paths, a malformed ZIP, global rate
ceilings, answers in the reader's language, the GeoNames credit.

The card law itself (every tool, every language) stays in ``test_card_law.py``;
this module checks the behaviours the review asked for, one by one.
"""
from __future__ import annotations

import re

import pytest
import respx
from conftest import BASE, body_of, call, fx, params_of, text_of
from mcp.shared.memory import create_connected_server_and_client_session

from finerx_mcp import limits, schemas, server
from finerx_mcp.card_law import BANNED_RE, undated_amounts
from finerx_mcp.client import FinerxApiError, FinerxClient, slug_path, valid_slug
from finerx_mcp.labels import LOCALES, TEXT_EN, _TEXT, text_for, tr
from finerx_mcp.limits import Limiter

# ChatGPT's approximate location, for the "never replace a ZIP the person gave" checks.
HOST_LOCATION = {"openai/userLocation": {"latitude": 30.2672, "longitude": -97.7431, "country": "US"}}
# What an API path may look like on the wire: the base, then slug-ish segments.
PATH_OK = re.compile(r"^/api/public/v1(/[a-z0-9-]+)+$")


def _paths(api) -> list[str]:
    return [call_.request.url.path for route in api.values() for call_ in route.calls]


# --- 3. only slugs reach a path ------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    ["../card/email", "atorvastatin 20 mg", "Atorvastatin", "a/b", "x?zip=33101", "%2e%2e", "-lead", "", None, 7],
)
def test_slug_path_refuses_what_is_not_a_slug(bad) -> None:
    assert valid_slug(bad) is None
    with pytest.raises(FinerxApiError) as err:
        slug_path("/drugs/{}/options", bad)
    assert err.value.status_code == 400


def test_slug_path_accepts_and_encodes_a_slug() -> None:
    assert slug_path("/drugs/{}/card-prices", "atorvastatin-calcium") == "/drugs/atorvastatin-calcium/card-prices"
    assert valid_slug("a" * 121) == "a" * 121 and valid_slug("a" * 122) is None


async def test_client_refuses_a_path_outside_the_slug_alphabet() -> None:
    client = FinerxClient(api_key="frx_live_test", api_base=BASE)
    with respx.mock(assert_all_mocked=True):  # a request would fail the test
        for path in ("/drugs/../card/email", "/drugs/a b/options", "/drugs//options", "/drugs/x?y=1"):
            with pytest.raises(FinerxApiError) as err:
                await client.get(path)
            assert err.value.status_code == 400
    await client.aclose()


async def test_card_with_free_text_resolves_through_the_search_query(api) -> None:
    result = await call("get_savings_card", {"drug": "Atorvastatin 20 mg"})
    assert params_of(api["search"])["q"] == "Atorvastatin 20 mg"
    assert api["card_prices"].calls[-1].request.url.path.endswith("/drugs/atorvastatin-calcium/card-prices")
    assert "$11.99 with the card at Hy-Vee, observed 2026-09-20" in text_of(result)
    assert all(PATH_OK.match(p) for p in _paths(api)), _paths(api)


@pytest.mark.parametrize("tool,arg", [("get_drug", "slug"), ("foreign_brands_for_drug", "slug"), ("get_savings_card", "drug")])
async def test_a_path_traversal_attempt_never_reaches_a_path(api, tool: str, arg: str) -> None:
    await call(tool, {arg: "../card/email?x=1"})
    assert not api["card_email"].called
    assert all(PATH_OK.match(p) for p in _paths(api)), _paths(api)
    assert params_of(api["search"])["q"] == "../card/email?x=1"  # the text went to the query string


async def test_a_plain_name_that_looks_like_a_slug_still_resolves(api) -> None:
    """"atorvastatin" is slug-shaped, but the catalog slug is atorvastatin-calcium —
    taking it verbatim 404'd the card price on /mcp-next (23.09)."""
    result = await call("get_savings_card", {"drug": "atorvastatin"})
    assert api["search"].called
    assert api["card_prices"].calls[-1].request.url.path.endswith("/drugs/atorvastatin-calcium/card-prices")
    assert "$11.99" in text_of(result)


async def test_get_drug_with_free_text_uses_the_top_hit(api) -> None:
    sc = (await call("get_drug", {"slug": "Lipitor 20mg"})).structuredContent
    assert api["card_prices"].calls[-1].request.url.path.endswith("/drugs/atorvastatin-calcium/card-prices")
    assert sc["slug"] == "atorvastatin-calcium"


async def test_get_drug_with_nothing_matching(api) -> None:
    api["search"].respond(json={"query": "zzz", "count": 0, "results": [], "foreignBrands": []})
    sc = (await call("get_drug", {"slug": "Zzz Qqq"})).structuredContent
    assert sc["error"]["code"] == "drug_not_found"
    assert not api["card_prices"].called


async def test_an_analog_slug_that_is_not_a_slug_is_dropped(api) -> None:
    search = {"query": "x", "count": 1, "results": [{"brand": "Evil", "brandSlug": "../../card/email", "countries": ["RU"]}]}
    api["analog_search"].respond(json=search)
    sc = (await call("find_us_equivalent", {"brand": "Evil"})).structuredContent
    assert sc["found"] is False
    assert not api["analog"].called and not api["card_email"].called


async def test_prices_send_free_text_in_the_body_only(api) -> None:
    await call("compare_prices", {"drug": "Lipitor 20 mg / generic?", "zip": "33101"})
    body = body_of(api["near"])
    # the dose is lifted into `strength`; the rest of the text still travels only in the body
    assert body["drug"] == "Lipitor / generic?" and body["strength"] == "20 mg"
    assert all(PATH_OK.match(p) for p in _paths(api)), _paths(api)


# --- 3. a malformed ZIP the person gave ------------------------------------------------


@pytest.mark.parametrize("bad_zip", ["3310", "331011", "ABCDE", "33 101"])
async def test_a_bad_zip_is_said_plainly_not_replaced_by_the_host_location(api, bad_zip: str) -> None:
    api["near"].respond(json=fx("prices_near_needs_zip"))
    result = await call("compare_prices", {"drug": "atorvastatin", "zip": bad_zip}, meta=HOST_LOCATION)
    body = body_of(api["near"])
    assert "zip" not in body and "lat" not in body and "lon" not in body
    sc = result.structuredContent
    assert sc["notice"] == {"code": "zip_invalid", "message": tr("en", "zipInvalid")}
    assert "error" not in sc  # the view is drawn: national prices + the ZIP field
    assert sc["data"]["needsZip"] is True
    assert sc["card"]["codes"]["group"] == "MYCARD3993"
    schemas.validate(sc)
    text = text_of(result)
    assert text.startswith("A ZIP code must be 5 digits")
    assert bad_zip not in text  # not echoed


async def test_a_bad_zip_in_russian(api) -> None:
    result = await call("compare_prices", {"drug": "atorvastatin", "zip": "123", "locale": "ru"}, meta=HOST_LOCATION)
    assert "ZIP-код должен состоять из 5 цифр" in text_of(result)
    assert result.structuredContent["notice"]["message"] == tr("ru", "zipInvalid")


async def test_zip_plus_four_is_a_valid_zip(api) -> None:
    result = await call("compare_prices", {"drug": "atorvastatin", "zip": "33101-1234"}, meta=HOST_LOCATION)
    assert body_of(api["near"])["zip"] == "33101"
    assert "notice" not in result.structuredContent


async def test_no_zip_still_uses_the_host_location(api) -> None:
    await call("compare_prices", {"drug": "atorvastatin"}, meta=HOST_LOCATION)
    body = body_of(api["near"])
    assert (body["lat"], body["lon"]) == (30.27, -97.74)


async def test_a_bad_zip_for_pharmacies_without_a_drug(api) -> None:
    result = await call("find_nearby_pharmacies", {"zip": "9410"}, meta=HOST_LOCATION)
    assert not api["nearby"].called and not api["near"].called
    sc = result.structuredContent
    assert sc["notice"]["code"] == "zip_invalid"
    assert sc["data"]["origin"]["precision"] == "none" and sc["data"]["stores"] == []
    schemas.validate(sc)
    assert "A ZIP code must be 5 digits" in text_of(result)


async def test_a_bad_zip_for_pharmacies_with_a_drug(api) -> None:
    result = await call("find_nearby_pharmacies", {"zip": "1234", "drug": "atorvastatin"}, meta=HOST_LOCATION)
    body = body_of(api["near"])
    assert "zip" not in body and "lat" not in body
    assert result.structuredContent["notice"]["code"] == "zip_invalid"


async def test_ui_prices_with_a_bad_zip(api) -> None:
    result = await call("ui_prices", {"slug": "atorvastatin-calcium", "zip": "12"}, meta=HOST_LOCATION)
    assert "lat" not in body_of(api["near"])
    assert result.structuredContent["notice"]["code"] == "zip_invalid"


# --- 4. global ceilings over every caller ---------------------------------------------


def test_rotating_subjects_hit_the_model_ceiling() -> None:
    lim = Limiter()
    for i in range(limits.MODEL_GLOBAL_PER_MIN):
        assert lim.check("model", f"s{i}", now=0.0) == 0
    assert lim.check("model", "a-brand-new-subject", now=0.0) >= 1
    assert lim.check("model", None, now=0.0) >= 1  # anonymous callers share the ceiling
    assert lim.check("model", "later", now=0.2) == 0  # the ceiling refills (10/s)


def test_rotating_subjects_hit_the_ui_ceiling() -> None:
    lim = Limiter()
    for i in range(limits.UI_GLOBAL_PER_MIN):
        assert lim.check("ui", f"s{i}", now=0.0) == 0
    assert lim.check("ui", "another", now=0.0) >= 1
    assert lim.check("model", "another", now=0.0) == 0  # the two ceilings are separate


def test_anonymous_calls_count_against_the_ceiling() -> None:
    lim = Limiter()
    for _ in range(limits.ANON_PER_MIN):
        assert lim.check("model", None, now=0.0) == 0
    for i in range(limits.MODEL_GLOBAL_PER_MIN - limits.ANON_PER_MIN):
        assert lim.check("model", f"s{i}", now=0.0) == 0
    assert lim.check("model", "one-more", now=0.0) >= 1


def test_evicting_subjects_does_not_reset_the_ceiling(monkeypatch) -> None:
    monkeypatch.setattr(limits, "MAX_KEYS", 10)
    lim = Limiter()
    for i in range(limits.MODEL_GLOBAL_PER_MIN):
        assert lim.check("model", f"s{i}", now=0.0) == 0
    assert len(lim._subjects) == 10  # most subjects were evicted…
    assert lim.check("model", "s0", now=0.0) >= 1  # …an evicted one comes back fresh, still refused
    assert lim.check("model", "fresh", now=0.0) >= 1


def test_a_call_the_ceiling_refused_does_not_count_for_the_person() -> None:
    lim = Limiter()
    for i in range(limits.MODEL_GLOBAL_PER_MIN):
        lim.check("model", f"s{i}", now=0.0)
    assert lim.check("model", "p", now=0.0) >= 1
    entry = lim._subjects["p"]
    assert entry.day_count == 0 and entry.model.tokens == limits.MODEL_PER_MIN


async def test_the_ceiling_answers_with_the_card(api) -> None:
    server.LIMITER.reset()
    for i in range(limits.MODEL_GLOBAL_PER_MIN):
        server.LIMITER.check("model", f"s{i}")
    result = await call("compare_prices", {"drug": "atorvastatin"}, meta={"openai/subject": "someone-new"})
    sc = result.structuredContent
    assert sc["error"]["code"] == "rate_limited"
    assert sc["card"]["codes"]["group"] == "MYCARD3993"
    assert not api["near"].called


# --- 7. the reader's language in content ------------------------------------------------


def test_content_phrases_exist_in_russian_and_spanish_with_the_same_placeholders() -> None:
    for loc in ("es", "ru"):
        assert set(_TEXT[loc]) == set(TEXT_EN), loc
        for key, value in _TEXT[loc].items():
            assert set(re.findall(r"\{(\w+)\}", value)) == set(re.findall(r"\{(\w+)\}", TEXT_EN[key])), (loc, key)


def test_every_locale_has_every_phrase() -> None:
    for loc in LOCALES:
        got = text_for(loc)
        assert set(got) == set(TEXT_EN), loc
        for key, value in got.items():
            assert set(re.findall(r"\{(\w+)\}", value)) == set(re.findall(r"\{(\w+)\}", TEXT_EN[key])), (loc, key)


def test_english_content_follows_the_card_law() -> None:
    for key, value in TEXT_EN.items():
        assert not BANNED_RE.search(value), key
        assert not re.search(r"\$\s?\d", value), key


def test_tr_fills_placeholders_once() -> None:
    assert tr("en", "rateLimited", n=7) == "Too many requests right now — try again in 7 s."
    assert tr("en", "noMatch", query="{n}") == "No medicine matched “{n}”. Try search_drugs with another spelling."
    assert tr("xx", "noStock") == TEXT_EN["noStock"]  # unknown language → English


async def test_prices_in_russian(api) -> None:
    text = text_of(await call("compare_prices", {"drug": "atorvastatin", "zip": "33101", "locale": "ru"}))
    assert "Цена с бесплатной картой FineRx рядом с Miami, FL (ZIP 33101), по возрастанию:" in text
    assert "Walmart (рядом нет магазина): $11.62 с картой, по наблюдению на 2026-09-20" in text
    assert "Наличие мы не видим" in text
    assert "**Бесплатная карта FineRx:** BIN 610219 · PCN DRX · Группа MYCARD3993" in text
    # (the law sentence is the API's own text, English in the fixture)
    for english in ("Price with the free FineRx card", "We don't see stock", "Free FineRx card", "with the card, observed"):
        assert english not in text, english
    assert undated_amounts(text) == []


async def test_pharmacies_in_spanish(api) -> None:
    text = text_of(await call("find_nearby_pharmacies", {"zip": "33101", "drug": "atorvastatin", "locale": "es"}))
    assert "**Farmacias cerca de Miami, FL (código postal 33101)**" in text
    assert "farmacia dentro de la tienda, sin verificar" in text
    assert "colaboradores de OpenStreetMap" in text
    assert "Pharmacies near" not in text
    assert undated_amounts(text) == []


async def test_a_language_without_its_own_set_borrows_the_widget_phrases(api) -> None:
    text = text_of(await call("compare_prices", {"drug": "atorvastatin", "zip": "33101", "locale": "fr"}))
    assert "$30.15 avec la carte, observé le 2026-09-20" in text
    assert "Nous ne voyons pas les stocks" in text
    assert "Groupe MYCARD3993" in text
    assert "Price with the free FineRx card near" in text  # the rest reads in English
    assert undated_amounts(text) == []


async def test_the_card_tool_in_russian(api) -> None:
    text = text_of(await call("get_savings_card", {"drug": "atorvastatin-calcium", "locale": "ru"}))
    assert "**Бесплатная скидочная карта FineRx**" in text
    assert "$11.99 с картой в Hy-Vee, по наблюдению на 2026-09-20" in text
    assert undated_amounts(text) == []


@pytest.mark.parametrize("locale", ["es", "ru"])
async def test_every_tool_answers_in_the_hosts_language(api, locale: str) -> None:
    from test_card_law import META_ONLY, TOOL_ARGS

    heading = tr(locale, "freeCard")
    for name, args in TOOL_ARGS.items():
        result = await call(name, args, meta={"openai/locale": locale})
        text = text_of(result)
        assert undated_amounts(text) == [], name
        if name in META_ONLY:
            continue
        assert f"**{heading}:**" in text, name
        assert "**Free FineRx card:**" not in text, name


# --- 2. attribution -----------------------------------------------------------------------


async def test_how_it_works_credits_geonames_and_openstreetmap() -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        text = (await session.read_resource("finerx://how-it-works")).contents[0].text
    assert "Place names: GeoNames (CC BY 4.0)" in text
    assert "© OpenStreetMap contributors (ODbL)" in text
    assert not BANNED_RE.search(text)


async def test_dataset_info_carries_the_source_attributions(api) -> None:
    result = await call("get_dataset_info", {})
    assert "Place names: GeoNames (CC BY 4.0)" in result.structuredContent["sourceAttributions"]
    assert "GeoNames (CC BY 4.0)" in text_of(result)
    api["meta"].respond(json={k: v for k, v in fx("meta").items() if k != "sourceAttributions"})
    older = await call("get_dataset_info", {})
    assert older.structuredContent["sourceAttributions"] == list(server.SOURCE_ATTRIBUTIONS)
