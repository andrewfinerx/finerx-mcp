"""MCP 2.2 — ``compare_basket``: several medicines at one place, one row per chain.

Held here: a sum exists only where EVERY medicine was seen with a price, it is
the plain addition of those observed prices, and it carries the span of their
dates; a chain without a store in range is not a row when a place is known;
names that matched nothing are counted, never echoed; the place rules are the
ones ``compare_prices`` keeps.
"""
from __future__ import annotations

import json

import httpx
import pytest
from conftest import body_of, call, fx, text_of

from finerx_mcp import card_law, schemas, views
from finerx_mcp.card_law import BANNED_RE, undated_amounts

ORIGIN = {"zip": "77002", "city": "Houston", "state": "TX", "precision": "zip"}


def chain(family: str, amount: float | None, day: str = "2026-09-27", *, stores: int = 2, miles: float = 1.0) -> dict:
    return {
        "family": family,
        "name": family.upper() if family in ("cvs", "heb") else family.capitalize(),
        "price": None if amount is None else {"amount": amount, "observedAt": day},
        "zone": "tx" if family == "walmart" else None,
        "storeCount": stores,
        "nearestMiles": miles,
        "stores": [],
    }


def near(slug: str, name: str, chains: list[dict], *, without: list[dict] | None = None, origin: dict | None = None) -> dict:
    return {
        "origin": origin or ORIGIN,
        "drug": {"slug": slug, "name": name, "kind": "generic"},
        "package": {"form": "Tablet", "strength": "10mg", "quantity": 30, "label": "30 × 10mg Tablet"},
        "coverage": {"status": "exact", "quantities": []},
        "chains": chains,
        "pricesWithoutStores": without or [],
        "needsZip": origin is not None and origin.get("precision") == "none",
        "card": fx("prices_near")["card"],
    }


ATORVA = near(
    "atorvastatin-calcium",
    "Atorvastatin Calcium",
    [chain("walmart", 14.22), chain("heb", 15.62), chain("cvs", 59.98, "2026-10-02")],
    without=[{"family": "capsule", "name": "Capsule", "price": {"amount": 9.0, "observedAt": "2026-09-30"}}],
)
LISINO = near(
    "lisinopril",
    "Lisinopril",
    [chain("walmart", 9.0, "2026-09-30"), chain("heb", 4.0), chain("cvs", 15.34, "2026-10-02")],
)
METFO = near("metformin-hcl", "Metformin HCl", [chain("walmart", 4.0), chain("heb", None), chain("cvs", 11.0)])


def route_by_drug(api, answers: dict[str, dict | int]) -> None:
    """Answer ``POST /prices/near`` by the ``drug`` in its body (a dict = 200,
    an int = that status with the API's not-found body)."""

    def reply(request: httpx.Request) -> httpx.Response:
        got = answers.get(json.loads(request.content)["drug"], 404)
        if isinstance(got, int):
            return httpx.Response(got, json=fx("drug_not_found") if got == 404 else {"detail": "down"})
        return httpx.Response(200, json=got)

    api["near"].mock(side_effect=reply)


BOTH = {"atorvastatin": ATORVA, "lisinopril": LISINO}


async def test_a_row_per_chain_with_the_sum_of_its_card_prices(api) -> None:
    route_by_drug(api, BOTH)
    result = await call("compare_basket", {"drugs": ["atorvastatin", "lisinopril"], "zip": "77002"})
    sc = result.structuredContent
    env = schemas.validate(sc)
    assert sc["view"] == "basket"
    data = sc["data"]
    assert [i["drug"]["slug"] for i in data["items"]] == ["atorvastatin-calcium", "lisinopril"]
    assert [(r["family"], r["total"]["amount"]) for r in data["rows"]] == [
        ("heb", 19.62),
        ("walmart", 23.22),
        ("cvs", 75.32),
    ]
    walmart = data["rows"][1]
    assert walmart["prices"] == [
        {"amount": 14.22, "observedAt": "2026-09-27"},
        {"amount": 9.0, "observedAt": "2026-09-30"},
    ]
    assert (walmart["total"]["observedFrom"], walmart["total"]["observedTo"]) == ("2026-09-27", "2026-09-30")
    assert walmart["total"]["count"] == 2 and all(i["priced"] for i in data["items"])
    assert walmart["zone"] == "tx" and walmart["missing"] == []
    assert env.data.needsZip is False and env.data.unmatched == 0


async def test_split_is_offered_only_when_it_takes_two_chains_and_comes_to_less(api) -> None:
    route_by_drug(api, BOTH)
    data = (await call("compare_basket", {"drugs": ["atorvastatin", "lisinopril"], "zip": "77002"})).structuredContent["data"]
    # Walmart 14.22 + H-E-B 4.00 = 18.22 < 19.62 (the first one-chain sum)
    assert data["split"] == {
        "amount": 18.22,
        "count": 2,
        "observedFrom": "2026-09-27",
        "observedTo": "2026-09-27",
        "chains": 2,
        "picks": [
            {"item": 1, "family": "walmart", "name": "Walmart"},
            {"item": 2, "family": "heb", "name": "HEB"},
        ],
    }
    # One chain is first for every medicine → nothing to split.
    cheap = near("lisinopril", "Lisinopril", [chain("walmart", 3.0), chain("heb", 4.0)])
    assert views.basket_data([ATORVA, cheap])["split"] is None


async def test_a_chain_missing_one_medicine_has_no_sum_and_sorts_after(api) -> None:
    route_by_drug(api, {"atorvastatin": ATORVA, "metformin": METFO})
    sc = (await call("compare_basket", {"drugs": ["atorvastatin", "metformin"], "zip": "77002"})).structuredContent
    rows = sc["data"]["rows"]
    assert [r["family"] for r in rows] == ["walmart", "cvs", "heb"]
    heb = rows[-1]
    assert heb["total"] is None and heb["missing"] == [2] and heb["prices"][1] is None
    schemas.validate(sc)


async def test_no_store_nearby_is_not_a_row_when_the_place_is_known() -> None:
    placed = views.basket_data([ATORVA, LISINO])
    assert "capsule" not in [r["family"] for r in placed["rows"]]
    nowhere = {"zip": None, "city": None, "state": None, "precision": "none"}
    national = near("atorvastatin-calcium", "Atorvastatin Calcium", [], origin=nowhere, without=ATORVA["pricesWithoutStores"])
    data = views.basket_data([national])
    assert [r["family"] for r in data["rows"]] == ["capsule"]
    assert data["needsZip"] is True and data["rows"][0]["storeCount"] == 0


async def test_text_gives_every_sum_with_its_dates_and_no_banned_word(api) -> None:
    route_by_drug(api, BOTH)
    result = await call("compare_basket", {"drugs": ["atorvastatin", "lisinopril"], "zip": "77002"})
    text = text_of(result)
    assert "2 medicines — card prices near Houston, TX (ZIP 77002)" in text
    assert "- Walmart (TX price): $23.22 for 2 medicines, prices observed 2026-09-27 to 2026-09-30 (#1 $14.22, #2 $9.00)" in text
    assert "- HEB: $19.62 for 2 medicines, prices observed 2026-09-27 (#1 $15.62, #2 $4.00)" in text
    assert "One chain per medicine: $18.22 across 2 chains, prices observed 2026-09-27 (#1 Walmart, #2 HEB)." in text
    assert "it is not a quote" in text
    assert undated_amounts(text) == []
    assert not BANNED_RE.search(text)
    assert not BANNED_RE.search(json.dumps(result.structuredContent))


async def test_a_name_that_matches_nothing_is_counted_not_echoed(api) -> None:
    route_by_drug(api, {"atorvastatin": ATORVA})
    result = await call("compare_basket", {"drugs": ["atorvastatin", "zzqqxx"], "zip": "77002"})
    sc = result.structuredContent
    assert sc["data"]["unmatched"] == 1
    assert len(sc["data"]["items"]) == 1
    assert "zzqqxx" not in json.dumps(sc)
    assert "1 of the names matched no medicine" in text_of(result)
    schemas.validate(sc)


async def test_nothing_matched_is_an_error_view_with_the_card(api) -> None:
    route_by_drug(api, {})
    sc = (await call("compare_basket", {"drugs": ["zzqq", "qqzz"]})).structuredContent
    env = schemas.validate(sc)
    assert env.data is None and env.error.code == "drug_not_found"
    assert sc["card"]["codes"]["group"] == "MYCARD3993"


async def test_api_down_is_said_plainly(api) -> None:
    route_by_drug(api, {"atorvastatin": 503, "lisinopril": 503})
    sc = (await call("compare_basket", {"drugs": ["atorvastatin", "lisinopril"]})).structuredContent
    assert sc["error"]["code"] == "api_unavailable" and sc["data"] is None


async def test_more_than_six_are_trimmed_and_said(api) -> None:
    names = [f"drug{i}" for i in range(8)]
    route_by_drug(api, {n: ATORVA for n in names})
    result = await call("compare_basket", {"drugs": names, "zip": "77002"})
    sc = result.structuredContent
    assert api["near"].call_count == 6
    assert len(sc["data"]["items"]) == 6
    assert sc["notice"]["code"] == "basket_trimmed"
    assert "Only the first 6 medicines" in text_of(result)
    schemas.validate(sc)


async def test_dose_and_pack_size_ride_in_the_name_and_the_zip_goes_to_every_call(api) -> None:
    route_by_drug(api, {"atorvastatin": ATORVA, "lisinopril": LISINO})
    await call("compare_basket", {"drugs": ["atorvastatin 40 mg 90 tablets", "lisinopril"], "zip": "77002"})
    bodies = sorted((body_of(api["near"], i) for i in range(2)), key=lambda b: b["drug"])
    assert bodies[0]["drug"] == "atorvastatin" and bodies[0]["strength"] == "40 mg" and bodies[0]["quantity"] == 90
    assert all(b["zip"] == "77002" and "lat" not in b and "address" not in b for b in bodies)


async def test_a_malformed_zip_is_never_replaced_by_the_host_location(api) -> None:
    route_by_drug(api, BOTH)
    meta = {"openai/userLocation": {"latitude": 30.27, "longitude": -97.74}}
    result = await call("compare_basket", {"drugs": ["atorvastatin", "lisinopril"], "zip": "7700"}, meta=meta)
    for i in range(2):
        body = body_of(api["near"], i)
        assert "zip" not in body and "lat" not in body
    sc = result.structuredContent
    assert sc["notice"]["code"] == "zip_invalid" and sc["data"]["needsZip"] is True


async def test_the_model_tool_takes_no_typed_place_and_the_card_tool_does(api) -> None:
    route_by_drug(api, {"atorvastatin-calcium": ATORVA, "lisinopril": LISINO})
    await call(
        "ui_basket",
        {"slugs": ["atorvastatin-calcium", "lisinopril"], "quantities": [90, 0], "where": "233 S Wacker Dr, Chicago"},
    )
    bodies = sorted((body_of(api["near"], i) for i in range(2)), key=lambda b: b["drug"])
    assert all(b["address"] == "233 S Wacker Dr, Chicago" and "zip" not in b for b in bodies)
    assert bodies[0]["quantity"] == 90 and bodies[1].get("quantity") is None
    # Only a slug reaches the API from the card.
    api["near"].reset()
    sc = (await call("ui_basket", {"slugs": ["../../etc", "Not A Slug"]})).structuredContent
    assert sc["error"]["code"] == "drug_required" and api["near"].call_count == 0


async def test_a_restricted_medicine_in_the_list_makes_the_law_plain(api) -> None:
    oxy = near("oxycodone-hcl", "Oxycodone HCl", [chain("walmart", 20.0), chain("heb", 22.0), chain("cvs", 30.0)])
    route_by_drug(api, {"atorvastatin": ATORVA, "oxycodone": oxy})
    result = await call("compare_basket", {"drugs": ["atorvastatin", "oxycodone"], "zip": "77002"})
    law = result.structuredContent["card"]["law"]
    assert law == card_law.RESTRICTED_LAW["en"]
    assert all(s["tool"] != "get_prescription_options" for s in result.structuredContent["next"])


async def test_next_steps_carry_the_slugs_and_ask_for_a_zip_when_national(api) -> None:
    nowhere = {"zip": None, "city": None, "state": None, "precision": "none"}
    route_by_drug(
        api,
        {
            "atorvastatin": near("atorvastatin-calcium", "Atorvastatin Calcium", [chain("walmart", 14.22, stores=0)], origin=nowhere),
            "lisinopril": near("lisinopril", "Lisinopril", [chain("walmart", 9.0, stores=0)], origin=nowhere),
        },
    )
    result = await call("compare_basket", {"drugs": ["atorvastatin", "lisinopril"]})
    first = result.structuredContent["next"][0]
    assert first == {
        "tool": "compare_basket",
        "args": {"drugs": ["atorvastatin-calcium", "lisinopril"]},
        "why": first["why"],
        "ask": "zip",
    }
    assert 'compare_basket(drugs=["atorvastatin-calcium", "lisinopril"])' in text_of(result)
    assert "card prices by chain (no place given)" in text_of(result)


async def test_placed_answer_points_at_the_first_chains_stores(api) -> None:
    route_by_drug(api, BOTH)
    steps = (await call("compare_basket", {"drugs": ["atorvastatin", "lisinopril"], "zip": "77002"})).structuredContent["next"]
    stores = next(s for s in steps if s["tool"] == "find_nearby_pharmacies")
    assert stores["args"] == {"family": "heb", "zip": "77002"}


@pytest.mark.parametrize("loc", ["es", "ru", "ar", "zh"])
async def test_labels_for_the_basket_are_served_in_the_reader_language(api, loc: str) -> None:
    route_by_drug(api, BOTH)
    result = await call("compare_basket", {"drugs": ["atorvastatin", "lisinopril"], "locale": loc})
    labels = result.meta["finerx/labels"]
    assert labels["basketTotal"] != "Sum for all {n}" and "{n}" in labels["basketTotal"]
    assert undated_amounts(text_of(result)) == []


def test_every_locale_translates_every_basket_label() -> None:
    import re

    from finerx_mcp.labels import _T, BASKET_EN

    for loc, table in _T.items():
        assert not set(BASKET_EN) - set(table), loc
        for key, value in BASKET_EN.items():
            assert set(re.findall(r"\{(\w+)\}", table[key])) == set(re.findall(r"\{(\w+)\}", value)), (loc, key)
            assert table[key] != value, (loc, key)
    for key, value in BASKET_EN.items():
        assert not BANNED_RE.search(value), key


async def test_a_medicine_no_chain_prices_is_left_out_of_the_sums_and_said(api) -> None:
    """Live 2026-10-03: metformin had no card price anywhere and the whole table
    read "no chain was seen with a card price for all of them"."""
    none = near("metformin-hcl", "Metformin HCl", [chain("walmart", None), chain("heb", None), chain("cvs", None)])
    none["coverage"] = {"status": "none", "quantities": []}
    route_by_drug(api, {"atorvastatin": ATORVA, "lisinopril": LISINO, "metformin": none})
    result = await call("compare_basket", {"drugs": ["atorvastatin", "lisinopril", "metformin"], "zip": "77002"})
    sc = result.structuredContent
    data = sc["data"]
    assert [i["priced"] for i in data["items"]] == [True, True, False]
    heb = data["rows"][0]
    assert heb["family"] == "heb" and heb["missing"] == [] and heb["prices"][2] is None
    assert heb["total"]["amount"] == 19.62 and heb["total"]["count"] == 2
    text = text_of(result)
    assert "3. Metformin HCl — 30 × 10mg Tablet — no card price seen" in text
    assert "No card price was seen at any of these chains for #3; the sums leave #3 out." in text
    assert "- HEB: $19.62 for 2 medicines, prices observed 2026-09-27 (#1 $15.62, #2 $4.00)" in text
    assert undated_amounts(text) == []
    schemas.validate(sc)


async def test_no_medicine_priced_anywhere_gives_an_empty_table_not_a_sum(api) -> None:
    none = near("metformin-hcl", "Metformin HCl", [chain("walmart", None)])
    data = views.basket_data([none, none])
    assert data["rows"] == [] and data["split"] is None
    assert [i["priced"] for i in data["items"]] == [False, False]


def test_split_needs_a_dollar_of_difference() -> None:
    """Live 2026-10-03: $20.61 across two chains was offered against $20.62 at one."""
    a = near("a", "A", [chain("walmart", 11.62), chain("heb", 11.99)])
    b = near("b", "B", [chain("walmart", 9.00), chain("heb", 8.99)])
    assert views.basket_data([a, b])["split"] is None
    # 11.62 + 4.00 = 15.62 against 15.99 at one chain: still under a dollar.
    assert views.basket_data([a, near("b", "B", [chain("walmart", 9.00), chain("heb", 4.00)])])["split"] is None
    c = near("c", "C", [chain("walmart", 5.00), chain("heb", 15.00)])
    d = near("d", "D", [chain("walmart", 15.00), chain("heb", 5.00)])
    assert views.basket_data([c, d])["split"]["amount"] == 10.0
