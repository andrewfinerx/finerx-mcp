"""``FINERX_MCP_COMPETITOR_PRICES`` (default off): no third-party program price
and no program name reaches an answer; ``isLowest`` is never set."""
from __future__ import annotations

import json
import re

import pytest
from conftest import call, text_of

PROGRAMS = re.compile(r"singlecare|buzzrx|wellrx|goodrx|hippo", re.IGNORECASE)


def _blob(result) -> str:
    return text_of(result) + json.dumps(result.structuredContent or {}, ensure_ascii=False)


@pytest.mark.parametrize(
    "name,args",
    [
        ("compare_prices", {"ndc": "00093505698", "quantity": 30}),
        ("search_drugs", {"query": "atorva"}),
        ("find_us_equivalent", {"brand": "Nurofen"}),
        ("get_drug", {"slug": "atorvastatin-calcium"}),
        ("get_savings_card", {"drug": "atorvastatin-calcium"}),
    ],
)
async def test_flag_off_no_feed_no_program_names(api, name: str, args: dict) -> None:
    result = await call(name, args)
    blob = _blob(result)
    assert not PROGRAMS.search(blob), PROGRAMS.search(blob)
    assert '"isLowest": true' not in blob
    assert '"fromPrice"' not in blob
    assert "programOffers" not in (result.structuredContent or {})


async def test_legacy_ndc_resolves_to_the_card_prices(api) -> None:
    result = await call("compare_prices", {"ndc": "00093505698", "quantity": 30})
    near = json.loads(api["near"].calls[-1].request.content)
    assert near["drug"] == "atorvastatin-calcium"
    assert near["strength"] == "10 mg" and near["form"] == "TABLET, FILM COATED" and near["quantity"] == 30
    assert result.structuredContent["view"] == "prices"


async def test_new_path_never_touches_the_feed(api) -> None:
    await call("compare_prices", {"drug": "atorvastatin", "zip": "33101"})
    await call("search_drugs", {"query": "atorva"})
    assert not api["compare"].called


async def test_flag_on_reattaches_the_legacy_fields(api, monkeypatch) -> None:
    monkeypatch.setenv("FINERX_MCP_COMPETITOR_PRICES", "true")
    result = await call("compare_prices", {"ndc": "00093505698", "quantity": 30})
    offers = result.structuredContent["programOffers"]
    assert {o["savingsProgram"] for o in offers} == {"SingleCare", "BuzzRx"}
    assert "isLowest" not in json.dumps(offers)
    search = await call("search_drugs", {"query": "atorva"})
    assert search.structuredContent["results"][0]["fromPrice"] == 3.21
