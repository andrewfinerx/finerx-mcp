"""Every view a tool returns validates against the ``finerx.view/2`` models
(``finerx_mcp.schemas``) — the contract the widget is built against (C2)."""
from __future__ import annotations

import pytest
from conftest import call, fx

from finerx_mcp import schemas

CASES = [
    ("compare_prices", {"drug": "atorvastatin", "zip": "33101"}, "prices"),
    ("ui_prices", {"slug": "atorvastatin-calcium", "strength": "20mg", "quantity": 30}, "prices"),
    ("find_nearby_pharmacies", {"zip": "33101"}, "pharmacies"),
    ("find_nearby_pharmacies", {"zip": "33101", "drug": "atorvastatin"}, "pharmacies"),
    ("find_nearby_pharmacies", {}, "pharmacies"),  # no place: needs a ZIP
    ("ui_nearby", {"zip": "33101", "family": "publix", "slug": "atorvastatin-calcium"}, "pharmacies"),
    ("get_savings_card", {}, "card"),
    ("get_savings_card", {"drug": "atorvastatin-calcium"}, "card"),
]


@pytest.mark.parametrize("name,args,view", CASES)
async def test_views_validate(api, name: str, args: dict, view: str) -> None:
    result = await call(name, args)
    sc = result.structuredContent
    assert sc["schema"] == "finerx.view/2"
    assert sc["view"] == view
    env = schemas.validate(sc)
    assert env.card.codes.group == "MYCARD3993"


async def test_prices_rows_are_capped_and_counted(api) -> None:
    sc = (await call("compare_prices", {"drug": "atorvastatin", "zip": "33101"})).structuredContent
    data = sc["data"]
    assert len(data["rows"]) == 6
    assert data["moreCount"] == 1
    assert data["rows"][0]["price"] == {"amount": 30.15, "observedAt": "2026-09-20"}
    assert [p["family"] for p in data["pricesWithoutStores"]] == ["walmart", "capsule"]
    assert data["options"]["configs"][0]["quantities"][0]["cardFrom"]["observedAt"] == "2026-09-20"


async def test_needs_zip_view_validates(api) -> None:
    api["near"].respond(json=fx("prices_near_needs_zip"))
    sc = (await call("compare_prices", {"drug": "atorvastatin"})).structuredContent
    env = schemas.validate(sc)
    assert env.data.needsZip is True
    assert env.data.origin.precision == "none"
    assert all(r.storeCount == 0 for r in env.data.rows)


async def test_error_envelope_validates(api) -> None:
    api["near"].respond(404, json=fx("drug_not_found"))
    sc = (await call("compare_prices", {"drug": "atorvastatinz"})).structuredContent
    env = schemas.validate(sc)
    assert env.data is None
    assert env.error.code == "drug_not_found"
    assert env.error.suggestions[0]["slug"] == "atorvastatin-calcium"


def test_json_schema_exports() -> None:
    out = schemas.envelope_json_schema()
    assert set(out) == {"prices", "pharmacies", "card"}
    assert "schema" in out["prices"]["properties"]
