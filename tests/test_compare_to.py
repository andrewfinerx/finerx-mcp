"""``compare_to`` — an amount the person named (a copay, what they pay now, a
price they want to hear about) against the card prices of ONE package.

Held here: it is a COUNT of observed prices below the amount, with the span of
their dates; nothing is subtracted or promised; an unusable amount changes
nothing; the insurance sentence travels with it; the card's refresh keeps it.
"""
from __future__ import annotations

import json

import pytest
from conftest import body_of, call, fx, text_of

from finerx_mcp import schemas, views
from finerx_mcp.card_law import BANNED_RE, undated_amounts

ARGS = {"drug": "atorvastatin", "zip": "33101"}


async def test_counts_the_chains_seen_below_the_amount(api) -> None:
    near = fx("prices_near")
    prices = [c["price"]["amount"] for c in near["chains"] if c.get("price")] + [
        p["price"]["amount"] for p in near["pricesWithoutStores"]
    ]
    result = await call("compare_prices", {**ARGS, "compare_to": 31})
    sc = result.structuredContent
    against = sc["data"]["compareTo"]
    assert against["amount"] == 31.0
    assert against["of"] == len(prices)
    assert against["below"] == sum(1 for p in prices if p < 31)
    assert against["observedFrom"] <= against["observedTo"]
    schemas.validate(sc)


async def test_text_states_the_count_with_dates_and_the_insurance_sentence(api) -> None:
    result = await call("compare_prices", {**ARGS, "compare_to": 31})
    text = text_of(result)
    against = result.structuredContent["data"]["compareTo"]
    line = next(ln for ln in text.splitlines() if ln.startswith("Against $31.00"))
    assert f"{against['below']} of {against['of']} chains were seen below it" in line
    assert against["observedFrom"] in line
    assert "A card price replaces insurance for that fill: it is not added to a copay" in text
    assert undated_amounts(text) == []
    assert not BANNED_RE.search(text) and not BANNED_RE.search(json.dumps(result.structuredContent))


async def test_no_amount_means_no_block_and_the_answer_is_unchanged(api) -> None:
    plain = await call("compare_prices", ARGS)
    assert "compareTo" not in plain.structuredContent["data"]
    assert "Against $" not in text_of(plain)
    with_amount = await call("compare_prices", {**ARGS, "compare_to": 31})
    rest = {k: v for k, v in with_amount.structuredContent["data"].items() if k != "compareTo"}
    assert rest == plain.structuredContent["data"]


@pytest.mark.parametrize("bad", [0, -5, 1e9, True, "abc", None, float("nan")])
def test_an_unusable_amount_is_ignored(bad) -> None:
    assert views.compare_to(fx("prices_near"), bad) is None


def test_nothing_priced_means_nothing_to_compare() -> None:
    near = {"chains": [{"family": "cvs", "name": "CVS", "price": None}], "pricesWithoutStores": []}
    assert views.compare_to(near, 20) is None


def test_equal_is_not_below() -> None:
    near = {
        "chains": [
            {"family": "a", "price": {"amount": 20.0, "observedAt": "2026-10-01"}},
            {"family": "b", "price": {"amount": 19.99, "observedAt": "2026-10-02"}},
            {"family": "c", "price": {"amount": 30.0}},  # no date → not a price
        ],
        "pricesWithoutStores": [],
    }
    got = views.compare_to(near, "20")
    assert got == {"amount": 20.0, "below": 1, "of": 2, "observedFrom": "2026-10-01", "observedTo": "2026-10-02"}


async def test_the_amount_never_reaches_the_api(api) -> None:
    await call("compare_prices", {**ARGS, "compare_to": 31})
    assert "compare_to" not in body_of(api["near"]) and "compareTo" not in body_of(api["near"])


async def test_the_card_refresh_keeps_the_amount(api) -> None:
    sc = (await call("ui_prices", {"slug": "atorvastatin-calcium", "quantity": 90, "compare_to": 31})).structuredContent
    assert sc["data"]["compareTo"]["amount"] == 31.0


async def test_restricted_medicine_still_gets_only_the_count(api) -> None:
    api["near"].respond(json={**fx("prices_near"), "drug": {"slug": "oxycodone-hcl", "name": "Oxycodone HCl", "kind": "generic"}})
    result = await call("compare_prices", {"drug": "oxycodone", "zip": "33101", "compare_to": 31})
    assert result.structuredContent["data"]["compareTo"]["of"] > 0
    assert "substantial" not in result.structuredContent["card"]["law"]


@pytest.mark.parametrize("loc", ["es", "ru", "ar"])
async def test_labels_and_text_in_the_reader_language(api, loc: str) -> None:
    result = await call("compare_prices", {**ARGS, "compare_to": 31, "locale": loc})
    labels = result.meta["finerx/labels"]
    assert labels["compareLine"] != "Against {price}: {below} of {n} chains were seen below it"
    assert {"{price}", "{below}", "{n}"} <= {f"{{{k}}}" for k in ("price", "below", "n") if "{" + k + "}" in labels["compareLine"]}
    assert undated_amounts(text_of(result)) == []


def test_instructions_say_no_alerts_and_how_to_watch() -> None:
    from finerx_mcp import server

    line = next(ln for ln in server.INSTRUCTIONS.splitlines() if "compare_to" in ln)
    assert "FineRx sends no alerts" in line and "not added to a copay" in line
    assert not BANNED_RE.search(line)
