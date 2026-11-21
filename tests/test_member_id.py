"""MCP 2.2.1: the Member / Cardholder ID, and no price on the card itself.

Counters ask for a Member ID before they run the card (FineRx support,
2026-11-20: a Walgreens customer could not fill a prescription), and this card
has no member number: the program's Cardholder ID is the patient's own 10-digit
phone (LowerMyRx's card for group MYCARD3993 says so). The site says so since
2026-11-21 (PR #179/#180); this is the same line in the chat:

* the widget's card face (a white strip under the codes), the counter screen,
  the card view's 4th step — labels in all 12 languages, verbatim from the site;
* the text every answer ends with (the codes line), the fallback SMS body, the
  server instructions and the how-it-works resource;
* the counter screen and the card view carry no price (owner, 2026-11-21) — the
  dated price stays in the law sentence beside the card and in the price views.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import respx
from conftest import call, text_of, url
from test_card_law import CARD_TOOLS, TOOL_ARGS

from finerx_mcp import card_law, server
from finerx_mcp.labels import EN, LOCALES, MEMBER_EN, _MEMBER, labels_for, text_for
from finerx_mcp.widget import load_app_html, load_widget_html

MEMBER_LINE_EN = "Member ID: your 10-digit phone number"
# The site's catalogs, present in the monorepo checkout (not in the public mirror).
SITE_LOCALES = Path(__file__).resolve().parents[3] / "apps" / "web" / "locales"
# label key → the key it copies in the site's `savings` catalog section
SITE_KEYS = {
    "memberIdLabel": "memberIdLabel",
    "memberIdHint": "memberIdHint",
    "memberIdLine": "memberIdLine",
    "step4": "cardPageHow4",
}


# --- the words ---------------------------------------------------------------------------


@pytest.mark.skipif(not SITE_LOCALES.is_dir(), reason="the site catalogs live in the monorepo only")
@pytest.mark.parametrize("locale", LOCALES)
def test_member_strings_are_the_site_catalog_verbatim(locale: str) -> None:
    catalog = json.loads((SITE_LOCALES / f"{locale}.json").read_text(encoding="utf-8"))
    ours = MEMBER_EN if locale == "en" else _MEMBER[locale]
    for key, site_key in SITE_KEYS.items():
        assert ours[key] == catalog["savings"][site_key], (locale, key)
    # the 4th step is also the API's howToUse4 (card section) — one sentence
    assert ours["step4"] == catalog["card"]["howToUse4"], locale
    assert text_for(locale)["memberIdLine"] == catalog["savings"]["memberIdLine"], locale


@pytest.mark.parametrize("locale", LOCALES)
def test_every_language_serves_the_member_labels(locale: str) -> None:
    got = labels_for(locale)
    for key in MEMBER_EN:
        assert got[key].strip(), (locale, key)
    for key in ("memberIdHint", "memberIdLine", "step4"):
        assert "10" in got[key], (locale, key)  # the ten digits, in every language
    if locale != "en":
        assert got["memberIdHint"] != EN["memberIdHint"], locale


def test_the_english_member_words_follow_the_card_law() -> None:
    for key, value in MEMBER_EN.items():
        assert not card_law.BANNED_RE.search(value), key
        assert not re.search(r"\$\s?\d", value), key


@pytest.mark.parametrize("locale", LOCALES)
def test_the_codes_line_carries_the_member_id_in_every_language(locale: str) -> None:
    view = card_law.to_view(card_law.fallback_card(locale), locale=locale)
    line = card_law.codes_line(view, locale)
    assert "MYCARD3993" in line
    assert line.endswith(text_for(locale)["memberIdLine"]), (locale, line)


# --- every answer ------------------------------------------------------------------------


@pytest.mark.parametrize("name", CARD_TOOLS)
async def test_every_card_answer_tells_the_member_id(api, name: str) -> None:
    result = await call(name, TOOL_ARGS[name])
    assert MEMBER_LINE_EN in text_of(result), name
    assert MEMBER_LINE_EN in result.structuredContent["card"]["actions"]["smsBody"], name


@pytest.mark.parametrize("name", ["get_savings_card", "compare_prices", "find_nearby_pharmacies"])
async def test_the_member_id_survives_a_dead_api(name: str) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.route(url__regex=url(".*")).respond(503, json={"detail": "upstream unavailable"})
        result = await call(name, TOOL_ARGS[name])
    assert MEMBER_LINE_EN in text_of(result), name
    assert result.structuredContent["card"]["actions"]["smsBody"] == card_law.SMS_BODY


async def test_get_savings_card_tells_the_member_id_in_spanish(api) -> None:
    result = await call("get_savings_card", {"locale": "es"})
    assert "N.º de miembro: tu número de teléfono de 10 dígitos" in text_of(result)
    labels = result.meta["finerx/labels"]
    assert labels["memberIdLabel"] == "N.º de miembro / titular"
    assert labels["memberIdHint"] == "Teléfono del paciente (10 dígitos)"
    assert labels["step4"].startswith("Si te piden un número de miembro")


async def test_get_savings_card_lists_the_api_steps_with_the_member_one(api) -> None:
    text = text_of(await call("get_savings_card", {}))
    assert "4. If they ask for a Member ID, give your 10-digit phone number." in text
    assert "Member ID: my 10-digit phone number." in text  # the phrase for the counter


def test_the_fallback_sms_body_is_card_only_with_the_member_id() -> None:
    body = card_law.SMS_BODY
    assert MEMBER_LINE_EN in body
    assert "MYCARD3993" in body
    assert not re.search(r"\$\s?\d", body)
    assert card_law.to_view(card_law.fallback_card("en"), locale="en")["actions"]["smsBody"] == body


def test_instructions_and_how_it_works_name_the_member_id() -> None:
    for text in (server.INSTRUCTIONS, server.HOW_IT_WORKS):
        assert MEMBER_LINE_EN in text
        assert "10-digit phone number" in text


async def test_the_card_resource_carries_the_member_id(api) -> None:
    assert MEMBER_LINE_EN in await server.card_resource()


# --- the widget bundle (built from widget-src/, committed) ---------------------------------


def test_the_bundle_draws_the_member_strip_and_no_counter_price() -> None:
    html = load_app_html()
    for needle in ("cf-member", "counter-member", "Member / Cardholder ID", "Patient's 10-digit phone", "cf-trees"):
        assert needle in html, needle
    # the counter screen printed a dated price under the codes until 2.2.0
    assert "counter-price" not in html


def test_the_1x_component_carries_the_member_strip_too() -> None:
    html = load_widget_html()
    assert "Member / Cardholder ID" in html
    assert "Patient's 10-digit phone" in html
