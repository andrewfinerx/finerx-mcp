"""The card law, checked for EVERY tool the server lists.

For each tool from ``list_tools()`` (a new tool without an entry in TOOL_ARGS
fails ``test_every_listed_tool_is_covered``):

* ``structuredContent.card.codes`` is there (except ``get_dataset_info``, mode=meta);
* the text carries the card law sentence and the small print;
* no banned word (``card_law.BANNED_RE``) in the text or the structured payload;
* every ``$N`` in the text has an ISO date on the same line;
* with the API down, the card is STILL there (codes + the no-price law).
"""
from __future__ import annotations

import json
import re

import httpx
import pytest
import respx
from conftest import call, fx, text_of, url
from mcp.shared.memory import create_connected_server_and_client_session

from finerx_mcp import card_law, server
from finerx_mcp.card_law import BANNED_RE, LAW_NO_PRICE, RESTRICTED_LAW, undated_amounts
from finerx_mcp.labels import EN

TOOL_ARGS: dict[str, dict] = {
    "compare_prices": {"drug": "atorvastatin", "zip": "33101"},
    "ui_prices": {"slug": "atorvastatin-calcium", "quantity": 30},
    "find_nearby_pharmacies": {"zip": "33101"},
    "ui_nearby": {"zip": "33101", "slug": "atorvastatin-calcium"},
    "get_savings_card": {"drug": "atorvastatin-calcium"},
    "email_savings_card": {"email": "jane@example.com", "consent": True},
    "search_drugs": {"query": "atorva"},
    "get_drug": {"slug": "atorvastatin-calcium"},
    "get_dataset_info": {},
    "get_prescription_options": {"drug": "atorvastatin-calcium"},
    "find_us_equivalent": {"brand": "Нурофен"},
    "foreign_brands_for_drug": {"slug": "ibuprofen"},
    # MCP 2.1 (phase 2)
    "open_price_finder": {"query": "atorva"},
    "ui_suggest": {"q": "atorva"},
    "ui_equivalent": {"brand_slug": "nurofen"},
}
# The same law with the phase-2 inputs that reach new code paths: a typed place
# (app-only ``where``) on both refresh tools, and the search with no query.
EXTRA_CASES: list[tuple[str, dict]] = [
    ("ui_prices", {"slug": "atorvastatin-calcium", "where": "233 S Wacker Dr, Chicago"}),
    ("ui_nearby", {"where": "233 S Wacker Dr, Chicago"}),
    ("ui_nearby", {"where": "Chicago, IL", "slug": "atorvastatin-calcium"}),
    ("open_price_finder", {}),
    ("get_prescription_options", {"drug": "oxycodone"}),
    ("find_us_equivalent", {"brand": "No-Spa"}),
]
META_ONLY = {"get_dataset_info"}  # the dataset, not a medicine: no card (contract)
CARD_TOOLS = sorted(set(TOOL_ARGS) - META_ONLY)


async def _listed() -> set[str]:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        return {t.name for t in (await session.list_tools()).tools}


async def test_every_listed_tool_is_covered() -> None:
    assert await _listed() == set(TOOL_ARGS)


def _check_words_and_dates(result, text: str) -> None:
    assert not BANNED_RE.search(text), BANNED_RE.search(text)
    blob = json.dumps(result.structuredContent or {}, ensure_ascii=False)
    assert not BANNED_RE.search(blob), BANNED_RE.search(blob)
    assert undated_amounts(text) == []


@pytest.mark.parametrize("name", sorted(TOOL_ARGS))
async def test_card_law_holds_for_every_tool(api, name: str) -> None:
    result = await call(name, TOOL_ARGS[name])
    assert result.isError is False
    text = text_of(result)
    sc = result.structuredContent or {}
    _check_words_and_dates(result, text)
    if name in META_ONLY:
        assert "card" not in sc
        assert "MYCARD3993" not in text
        return
    card = sc["card"]
    assert card["codes"] == {"bin": "610219", "pcn": "DRX", "group": "MYCARD3993"}
    assert card["law"] and card["law"] in text
    assert card["fine"] and card["fine"] in text
    assert "BIN 610219 · PCN DRX · Group MYCARD3993" in text
    assert card["actions"]["smsBody"]


@pytest.mark.parametrize("name,args", EXTRA_CASES)
async def test_card_law_holds_for_phase2_inputs(api, name: str, args: dict) -> None:
    result = await call(name, args)
    text = text_of(result)
    _check_words_and_dates(result, text)
    card = result.structuredContent["card"]
    assert card["codes"]["group"] == "MYCARD3993"
    assert card["law"] in text and card["fine"] in text


@pytest.mark.parametrize("name", CARD_TOOLS)
async def test_the_card_survives_a_dead_api(name: str) -> None:
    """503 on every endpoint: the prices are gone, the card is not."""
    with respx.mock(assert_all_called=False) as router:
        router.route(url__regex=url(".*")).respond(503, json={"detail": "upstream unavailable"})
        result = await call(name, TOOL_ARGS[name])
    text = text_of(result)
    sc = result.structuredContent or {}
    assert sc["card"]["codes"]["group"] == "MYCARD3993"
    assert LAW_NO_PRICE["en"] in text
    assert "MYCARD3993" in text
    _check_words_and_dates(result, text)


@pytest.mark.parametrize("name", ["compare_prices", "get_savings_card", "search_drugs"])
async def test_the_card_survives_a_network_error(name: str) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.route(url__regex=url(".*")).mock(side_effect=httpx.ConnectError("boom"))
        result = await call(name, TOOL_ARGS[name])
    assert result.structuredContent["card"]["codes"]["bin"] == "610219"
    assert LAW_NO_PRICE["en"] in text_of(result)


async def test_the_card_survives_an_internal_error(api, monkeypatch: pytest.MonkeyPatch) -> None:
    """A bug inside a tool still answers with the card, never a stack trace."""

    def _explode(*a, **k):
        raise RuntimeError("bug with zip=33101 inside")

    monkeypatch.setattr(server.views, "prices_data", _explode)
    result = await call("compare_prices", {"drug": "atorvastatin", "zip": "33101"})
    assert result.isError is False
    assert result.structuredContent["error"]["code"] == "internal_error"
    assert result.structuredContent["card"]["codes"]["pcn"] == "DRX"
    assert "33101" not in text_of(result)


async def test_a_last_good_card_outlives_the_api(api) -> None:
    """After one good /card, a later outage still shows the chain count we saw."""
    await call("search_drugs", {"query": "atorva"})
    server._client = None
    card_law._cache.clear()  # the TTL cache — _last_good stays
    with respx.mock(assert_all_called=False) as router:
        router.route(url__regex=url(".*")).respond(503)
        result = await call("get_savings_card", {})
    assert result.structuredContent["card"]["chainsCount"] == 36


async def test_the_price_in_the_law_is_the_dated_one(api) -> None:
    result = await call("compare_prices", {"drug": "atorvastatin", "zip": "33101"})
    card = result.structuredContent["card"]
    assert card["priceWithCard"] == {"amount": 30.15, "family": "publix", "name": "Publix", "observedAt": "2026-09-20"}
    assert "$30.15 (observed 2026-09-20)" in card["law"]


# --- controlled / age-restricted medicines -----------------------------------------


async def test_restricted_drug_gets_prices_and_a_plain_card(api) -> None:
    near = fx("prices_near")
    near["drug"] = {"slug": "amphetamine-dextroamphetamine", "name": "Amphetamine-Dextroamphetamine", "kind": "generic"}
    api["near"].respond(json=near)
    result = await call("compare_prices", {"drug": "adderall", "strength": "20 mg"})
    text = text_of(result)
    card = result.structuredContent["card"]
    assert card["law"] == RESTRICTED_LAW["en"]
    assert "can be substantial" not in text
    assert "Publix: $30.15 with the card, observed 2026-09-20" in text  # prices stay
    assert "don't see stock" in text


async def test_restricted_drug_has_no_route_to_a_prescription(api) -> None:
    result = await call("get_prescription_options", {"drug": "oxycodone-hcl"})
    sc = result.structuredContent
    assert sc["restricted"] is True
    assert "noPrescription" not in sc
    assert not api["rx"].called
    assert "can be substantial" not in text_of(result)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("amphetamine-dextroamphetamine", True),
        ("Adderall XR", True),
        ("lisdexamfetamine-dimesylate", True),
        ("dexmethylphenidate", True),
        ("phentermine-hcl", True),
        ("testosterone-cypionate", True),
        ("hydrocodone-acetaminophen", True),
        ("buprenorphine-hcl-naloxone-hcl", True),
        ("tramadol", True),
        ("atorvastatin-calcium", False),
        ("hydroxyzine-hcl", False),
        ("hydromorphone", True),  # on the list since the 23.09 review
        (None, False),
    ],
)
def test_restricted_list(name, expected: bool) -> None:
    assert card_law.is_restricted(name) is expected


@pytest.mark.parametrize("locale", sorted(LAW_NO_PRICE))
def test_restricted_law_is_a_deletion_of_the_approved_text(locale: str) -> None:
    """Nothing added to the owner-approved sentence — only one part taken out."""
    full, short = LAW_NO_PRICE[locale], RESTRICTED_LAW[locale]
    prefix = len(__import__("os").path.commonprefix([full, short]))
    suffix = len(__import__("os").path.commonprefix([full[::-1], short[::-1]]))
    assert len(short) < len(full)
    assert prefix + suffix >= len(short)


def test_fine_line_never_invents_a_date() -> None:
    assert card_law.fine_line("en", "2026-09-20") == (
        "Not insurance · prices observed 2026-09-20 · FineRx may earn a fee · not medical advice"
    )
    assert card_law.fine_line("en", None) == "Not insurance · FineRx may earn a fee · not medical advice"
    assert "{date}" not in card_law.fine_line("zh", None)


def test_undated_amounts_catches_a_bare_price() -> None:
    assert undated_amounts("CVS $12.40\nWalmart $6.10, observed 2026-09-21") == ["CVS $12.40"]


def test_banned_words_are_caught() -> None:
    for phrase in ("the lowest price", "Always cheaper", "save up to 80%", "works with insurance", "most pharmacies"):
        assert BANNED_RE.search(phrase), phrase
    assert not BANNED_RE.search("prices observed low to high at 34+ pharmacy chains")


def test_english_labels_follow_the_card_law() -> None:
    for key, value in EN.items():
        assert not BANNED_RE.search(value), key
        assert not re.search(r"\$\s?\d", value), key


# --- the restricted list, group by group (review 23.09) ---------------------------

# The INNs the owner's list names, by group: each must be on the list itself.
REQUIRED_INNS = {
    "stimulants": (
        "amphetamine", "dextroamphetamine", "lisdexamfetamine", "methylphenidate",
        "dexmethylphenidate", "methamphetamine", "armodafinil", "modafinil",
    ),
    "opioids": (
        "oxycodone", "hydrocodone", "morphine", "hydromorphone", "oxymorphone", "fentanyl",
        "tramadol", "tapentadol", "codeine", "methadone", "buprenorphine", "meperidine",
    ),
    "sedatives": ("alprazolam", "clonazepam", "lorazepam", "diazepam", "temazepam", "zolpidem", "eszopiclone"),
    "other": ("phentermine", "testosterone", "carisoprodol", "pregabalin"),
}


@pytest.mark.parametrize("group", sorted(REQUIRED_INNS))
def test_every_listed_ingredient_is_restricted(group: str) -> None:
    listed = card_law.RESTRICTED_GROUPS[group]
    for inn in REQUIRED_INNS[group]:
        assert inn in listed, inn
        assert card_law.is_restricted(inn), inn


@pytest.mark.parametrize(
    "name",
    [
        # stimulants — salts, combinations, brands
        "amphetamine-dextroamphetamine", "Amphetamine Sulfate", "dextroamphetamine-saccharate",
        "Vyvanse", "methylphenidate-er", "Concerta", "Focalin XR", "methamphetamine-hcl",
        "armodafinil", "Provigil",
        # opioids
        "oxycodone-acetaminophen", "Oxycodone and Acetaminophen", "hydrocodone-bitartrate-acetaminophen",
        "Morphine Sulfate ER", "MS Contin", "hydromorphone-hcl", "oxymorphone", "fentanyl-transdermal",
        "tramadol-hcl", "tapentadol", "acetaminophen-codeine", "Tylenol with Codeine #3",
        "promethazine-codeine", "methadone-hcl", "buprenorphine-naloxone", "Suboxone", "meperidine",
        # benzodiazepines and sleep medicines
        "alprazolam", "Xanax XR", "clonazepam", "lorazepam", "diazepam", "temazepam",
        "zolpidem-tartrate", "Ambien CR", "eszopiclone", "Lunesta",
        # other
        "phentermine-hcl", "phentermine-topiramate", "Adipex-P", "testosterone-cypionate",
        "Testosterone Enanthate", "AndroGel", "carisoprodol", "Soma", "pregabalin", "Lyrica CR",
    ],
)
def test_restricted_matches_salts_combinations_and_brands(name: str) -> None:
    assert card_law.is_restricted(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "apomorphine",  # contains "morphine", is not an opioid
        "somatropin",  # contains "soma"
        "griseofulvin-ultramicrosize",  # contains "ultram"
        "naloxone", "naltrexone", "hydroxyzine-hcl", "atorvastatin-calcium", "gabapentin",
        "trazodone", "buspirone", "", None,
    ],
)
def test_restricted_does_not_match_a_word_that_only_contains_a_term(name) -> None:
    assert card_law.is_restricted(name) is False


RESTRICTED_SAMPLES = [
    ("amphetamine-dextroamphetamine", "Amphetamine-Dextroamphetamine"),
    ("methylphenidate-hcl", "Methylphenidate HCl"),
    ("oxycodone-acetaminophen", "Oxycodone-Acetaminophen"),
    ("acetaminophen-codeine", "Acetaminophen-Codeine"),
    ("alprazolam", "Alprazolam"),
    ("zolpidem-tartrate", "Zolpidem Tartrate"),
    ("phentermine-hcl", "Phentermine HCl"),
    ("testosterone-cypionate", "Testosterone Cypionate"),
    ("carisoprodol", "Carisoprodol"),
    ("pregabalin", "Pregabalin"),
]


@pytest.mark.parametrize("slug,name", RESTRICTED_SAMPLES)
async def test_restricted_group_has_no_prescription_route(api, slug: str, name: str) -> None:
    result = await call("get_prescription_options", {"drug": slug})
    sc = result.structuredContent
    assert sc["restricted"] is True
    assert "noPrescription" not in sc and "havePrescription" not in sc and "brandCostly" not in sc
    assert not api["rx"].called
    assert sc["card"]["law"] == RESTRICTED_LAW["en"]
    assert "can be substantial" not in text_of(result)


@pytest.mark.parametrize("slug,name", RESTRICTED_SAMPLES)
async def test_restricted_group_prices_carry_the_plain_law(api, slug: str, name: str) -> None:
    near = fx("prices_near")
    near["drug"] = {"slug": slug, "name": name, "kind": "generic"}
    api["near"].respond(json=near)
    # The name as typed is not restricted — the API's resolved slug/name is what matters.
    result = await call("compare_prices", {"drug": "the one my doctor gave me", "zip": "33101"})
    text = text_of(result)
    card = result.structuredContent["card"]
    assert card["law"] == RESTRICTED_LAW["en"]
    assert "can be substantial" not in text and "can be substantial" not in json.dumps(result.structuredContent)
    assert "$30.15 with the card, observed 2026-09-20" in text  # prices stay


@pytest.mark.parametrize("locale", ["es", "ru"])
async def test_restricted_law_in_other_languages(api, locale: str) -> None:
    near = fx("prices_near")
    near["drug"] = {"slug": "oxycodone-acetaminophen", "name": "Oxycodone-Acetaminophen", "kind": "generic"}
    api["near"].respond(json=near)
    result = await call("compare_prices", {"drug": "percocet", "zip": "33101", "locale": locale})
    card = result.structuredContent["card"]
    assert card["law"] == RESTRICTED_LAW[locale]
    assert card["law"] in text_of(result)
    assert LAW_NO_PRICE[locale] not in text_of(result)
