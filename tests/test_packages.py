"""MCP 2.2 — ``get_drug`` as the "packages" view: every strength and pack size
with a card price. Held here: every 2.0 key is still there beside the envelope;
each "from" price carries its date; the default package is the one the answer
names; a failure is still a plain error with the card."""
from __future__ import annotations

from conftest import call, fx, text_of

from finerx_mcp import schemas
from finerx_mcp.card_law import undated_amounts

LEGACY = {"name", "slug", "kind", "configs", "defaultConfig", "fromCardPrice", "defaultPackage", "card"}


async def test_the_view_rides_beside_every_2_0_key(api) -> None:
    sc = (await call("get_drug", {"slug": "atorvastatin-calcium"})).structuredContent
    assert LEGACY <= set(sc)
    env = schemas.validate(sc)
    assert sc["view"] == "packages" and env.data.drug.slug == sc["slug"]
    assert {c["strength"] for c in sc["data"]["configs"]} <= {c["strength"] for c in sc["configs"]}
    assert sc["data"]["default"] == {
        k: sc["defaultPackage"]["package"].get(k) for k in ("form", "strength", "quantity")
    }


async def test_every_from_price_in_the_view_has_its_date(api) -> None:
    sc = (await call("get_drug", {"slug": "atorvastatin-calcium"})).structuredContent
    priced = [q["cardFrom"] for c in sc["data"]["configs"] for q in c["quantities"] if q.get("cardFrom")]
    assert priced and all(p.get("observedAt") and p.get("amount") is not None for p in priced)
    assert undated_amounts(text_of(await call("get_drug", {"slug": "atorvastatin-calcium"}))) == []


async def test_it_carries_the_labels_and_the_2_2_template(api) -> None:
    result = await call("get_drug", {"slug": "atorvastatin-calcium", "locale": "ru"})
    labels = result.meta["finerx/labels"]
    assert labels["packagesTitle"] == "Дозировки и упаковки, для которых есть цена с картой"
    assert "{n}" in labels["chainsPriced"]


async def test_an_unknown_drug_is_still_a_plain_error_with_the_card(api) -> None:
    api["search"].respond(json={"results": []})
    sc = (await call("get_drug", {"slug": "zz not a drug"})).structuredContent
    assert sc["error"]["code"] == "drug_not_found" and sc["card"]["codes"]["bin"] == "610219"


async def test_api_down_on_card_prices_is_said(api) -> None:
    api["card_prices"].respond(503)
    sc = (await call("get_drug", {"slug": "atorvastatin-calcium"})).structuredContent
    assert sc["error"]["code"] == "api_unavailable"


async def test_no_options_gives_an_empty_list_not_a_crash(api) -> None:
    api["options"].respond(503)
    sc = (await call("get_drug", {"slug": "atorvastatin-calcium"})).structuredContent
    assert sc["data"]["configs"] == [] and schemas.validate(sc).view == "packages"


def test_the_default_strength_comes_first_and_the_rest_are_counted() -> None:
    """Live 2026-10-03: levothyroxine has more strengths than the bound, and the
    default package's strength (100mcg tablet) sat behind a dozen capsule boxes."""
    from finerx_mcp import views

    configs = [
        {"form": "Tablet", "strength": f"{n}mcg", "label": f"{n}mcg Tablet", "quantities": [{"quantity": 30}]}
        for n in (25, 50, 75, 88, 100, 112, 125, 137, 150, 175, 200, 300, 13, 44, 62)
    ]
    options = {"configs": [*configs[:4], *configs[5:], configs[4]]}  # 100mcg comes last
    data = views.packages_data({"slug": "x", "name": "X"}, {"form": "Tablet", "strength": "100mcg", "quantity": 30}, options)
    assert len(data["configs"]) == 6
    assert data["configs"][0]["strength"] == "100mcg"
    assert data["moreCount"] == 9
    assert schemas.PackagesData.model_validate(data).moreCount == 9
    few = views.packages_data({"slug": "x", "name": "X"}, {"form": "Tablet", "strength": "50mcg"}, {"configs": configs[:3]})
    assert few["moreCount"] == 0 and [c["strength"] for c in few["configs"]] == ["50mcg", "25mcg", "75mcg"]


def test_a_strength_shows_the_default_and_the_common_pack_sizes() -> None:
    from finerx_mcp import views

    qs = [{"quantity": n} for n in (10, 14, 15, 30, 45, 60, 90, 100)]
    options = {"configs": [{"form": "Tablet", "strength": "10mg", "quantities": qs}, {"form": "Tablet", "strength": "20mg", "quantities": qs}]}
    data = views.packages_data({"slug": "x", "name": "X"}, {"form": "Tablet", "strength": "10mg", "quantity": 45}, options)
    assert [q["quantity"] for q in data["configs"][0]["quantities"]] == [30, 45, 60, 90]
    assert [q["quantity"] for q in data["configs"][1]["quantities"]] == [10, 30, 60, 90]


async def test_no_per_unit_figure_is_served(api) -> None:
    result = await call("get_drug", {"slug": "atorvastatin-calcium"})
    assert "perUnit" not in result.meta["finerx/labels"]
