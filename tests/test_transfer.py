"""MCP 2.2 — ``get_transfer_steps``: moving a prescription to the chain the
person picked. Held here: the steps are OUR fixed sentences (never composed),
the chain's price is the dated one for the package, a restricted medicine gets
nothing but the card, a failing API still leaves the steps, and the place rules
are compare_prices' own."""
from __future__ import annotations

import json

import pytest
from conftest import body_of, call, fx, params_of, text_of

from finerx_mcp import schemas
from finerx_mcp.card_law import BANNED_RE, undated_amounts
from finerx_mcp.labels import TEXT_EN, tr

STEPS = [TEXT_EN[f"transferStep{i}"] for i in (1, 2, 3, 4)]
NOTES = [TEXT_EN[f"transferNote{i}"] for i in (1, 2, 3)]


async def test_the_steps_are_the_fixed_sentences_in_order(api) -> None:
    result = await call("get_transfer_steps", {"chain": "publix", "drug": "atorvastatin", "zip": "33101"})
    sc = result.structuredContent
    schemas.validate(sc)
    assert sc["data"]["steps"] == STEPS and sc["data"]["notes"] == NOTES
    text = text_of(result)
    for i, s in enumerate(STEPS, 1):
        assert f"{i}. {s}" in text
    assert undated_amounts(text) == [] and not BANNED_RE.search(text)


async def test_the_chain_price_is_the_dated_one_for_the_package(api) -> None:
    near = fx("prices_near")
    publix = next(c for c in near["chains"] if c["family"] == "publix")
    sc = (await call("get_transfer_steps", {"chain": "publix", "drug": "atorvastatin", "zip": "33101"})).structuredContent
    d = sc["data"]
    assert d["chain"] == {"family": "publix", "name": "Publix"}
    assert d["price"] == publix["price"]
    assert d["drug"]["slug"] == near["drug"]["slug"]
    assert 0 < len(d["stores"]) <= 3 and all(s["family"] == "publix" for s in d["stores"])
    assert body_of(api["near"])["zip"] == "33101"


async def test_a_chain_priced_without_a_store_nearby_still_gets_its_price(api) -> None:
    sc = (await call("get_transfer_steps", {"chain": "walmart", "drug": "atorvastatin", "zip": "33101"})).structuredContent
    assert sc["data"]["price"]["amount"] == 11.62 and sc["data"]["stores"] == []


async def test_no_drug_lists_the_chains_stores_near_the_zip(api) -> None:
    sc = (await call("get_transfer_steps", {"chain": "publix", "zip": "33101"})).structuredContent
    assert params_of(api["nearby"])["family"] == "publix" and params_of(api["nearby"])["zip"] == "33101"
    assert sc["data"]["price"] is None and sc["data"]["drug"] is None
    assert [s["family"] for s in sc["data"]["stores"]] == ["publix"]
    assert api["near"].call_count == 0


async def test_nothing_given_is_just_the_steps_and_the_card(api) -> None:
    result = await call("get_transfer_steps", {})
    sc = result.structuredContent
    assert sc["data"]["chain"] is None and sc["data"]["steps"] == STEPS and sc["data"]["stores"] == []
    assert "Moving a prescription to another pharmacy" in text_of(result)
    assert api["near"].call_count == 0 and api["nearby"].call_count == 0
    assert sc["card"]["codes"]["group"] == "MYCARD3993"


@pytest.mark.parametrize("drug", ["oxycodone", "adderall 20 mg", "xanax"])
async def test_a_restricted_medicine_gets_no_steps(api, drug: str) -> None:
    result = await call("get_transfer_steps", {"chain": "cvs", "drug": drug, "zip": "33101"})
    d = result.structuredContent["data"]
    assert d["restricted"] is True and d["steps"] == [] and d["notes"] == [] and d["stores"] == []
    assert "substantial" not in result.structuredContent["card"]["law"]
    assert api["near"].call_count == 0
    assert "next" not in result.structuredContent


async def test_a_name_that_resolves_to_a_restricted_medicine_gets_no_steps(api) -> None:
    api["near"].respond(json={**fx("prices_near"), "drug": {"slug": "oxycodone-hcl", "name": "Oxycodone HCl", "kind": "generic"}})
    d = (await call("get_transfer_steps", {"chain": "cvs", "drug": "percocet"})).structuredContent["data"]
    assert d["restricted"] is True and d["steps"] == []


async def test_api_down_leaves_the_steps(api) -> None:
    api["near"].respond(503)
    sc = (await call("get_transfer_steps", {"chain": "publix", "drug": "atorvastatin", "zip": "33101"})).structuredContent
    assert sc["data"]["steps"] == STEPS and sc["data"]["price"] is None and "error" not in sc


async def test_a_malformed_zip_is_never_replaced_by_the_host_location(api) -> None:
    meta = {"openai/userLocation": {"latitude": 30.27, "longitude": -97.74}}
    result = await call("get_transfer_steps", {"chain": "publix", "drug": "atorvastatin", "zip": "331"}, meta=meta)
    body = body_of(api["near"])
    assert "zip" not in body and "lat" not in body
    assert result.structuredContent["notice"]["code"] == "zip_invalid"


async def test_a_chain_that_is_not_a_code_is_ignored_not_sent(api) -> None:
    sc = (await call("get_transfer_steps", {"chain": "../etc; drop", "zip": "33101"})).structuredContent
    assert sc["data"]["chain"] is None and api["nearby"].call_count == 0


@pytest.mark.parametrize("loc", ["es", "ru"])
async def test_steps_in_the_reader_language(api, loc: str) -> None:
    sc = (await call("get_transfer_steps", {"chain": "publix", "locale": loc})).structuredContent
    assert sc["data"]["steps"] == [tr(loc, f"transferStep{i}") for i in (1, 2, 3, 4)]
    assert sc["data"]["steps"] != STEPS


def test_the_sentences_promise_nothing() -> None:
    for s in STEPS + NOTES:
        assert not BANNED_RE.search(s), s
        assert "$" not in s


async def test_prices_point_at_the_transfer_for_the_first_chain(api) -> None:
    steps = (await call("compare_prices", {"drug": "atorvastatin", "zip": "33101"})).structuredContent["next"]
    move = next(s for s in steps if s["tool"] == "get_transfer_steps")
    assert move["args"]["chain"] == "publix" and move["args"]["drug"] == "atorvastatin-calcium" and move["args"]["zip"] == "33101"
    restricted = (await call("compare_prices", {"drug": "oxycodone", "zip": "33101"})).structuredContent["next"]
    assert all(s["tool"] != "get_transfer_steps" for s in restricted)
    assert "get_transfer_steps" in json.dumps(steps)
