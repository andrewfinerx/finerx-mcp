"""``next`` — the calls that fit after an answer (``finerx_mcp.next_steps``).

What is held here: a step names a tool the MODEL can call, with arguments that
tool accepts; the arguments come from the answer, never from what the person
typed; a restricted medicine gets no route to a prescription; a different
medicine is never the next step of a foreign brand; and the text the model reads
says the same as the data.
"""
from __future__ import annotations

import json

import pytest
from conftest import call, fx, text_of
from mcp.shared.memory import create_connected_server_and_client_session

from finerx_mcp import next_steps, schemas, server
from finerx_mcp.card_law import BANNED_RE

# Every model-facing tool, with inputs that reach each builder.
CASES: list[tuple[str, dict]] = [
    ("compare_prices", {"drug": "atorvastatin", "zip": "33101"}),
    ("compare_prices", {"drug": "oxycodone", "zip": "33101"}),
    ("find_nearby_pharmacies", {"zip": "33101"}),
    ("find_nearby_pharmacies", {"zip": "33101", "drug": "atorvastatin"}),
    ("find_nearby_pharmacies", {}),
    ("get_savings_card", {}),
    ("get_savings_card", {"drug": "atorvastatin-calcium"}),
    ("email_savings_card", {"email": "jane@example.com", "consent": True}),
    ("search_drugs", {"query": "atorva"}),
    ("get_drug", {"slug": "atorvastatin-calcium"}),
    ("open_price_finder", {"query": "atorva"}),
    ("find_us_equivalent", {"brand": "Нурофен"}),
    ("get_prescription_options", {"drug": "atorvastatin"}),
    ("get_prescription_options", {"drug": "oxycodone"}),
    ("get_prescription_options", {}),
    ("foreign_brands_for_drug", {"slug": "ibuprofen"}),
]


async def _tools() -> dict[str, dict]:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        listed = (await session.list_tools()).tools
    return {t.name: {"props": set((t.inputSchema or {}).get("properties") or {}), "meta": t.meta or {}} for t in listed}


def _model_visible(meta: dict) -> bool:
    return "model" in ((meta.get("ui") or {}).get("visibility") or ["model"])


@pytest.mark.parametrize("name,args", CASES)
async def test_steps_are_calls_the_model_can_make(api, name: str, args: dict) -> None:
    tools = await _tools()
    result = await call(name, args)
    steps = result.structuredContent.get("next")
    assert steps, f"{name} offers no next step"
    assert len(steps) <= next_steps.MAX_STEPS
    for s in steps:
        schemas.NextStep.model_validate(s)
        assert s["tool"] in tools, s
        assert _model_visible(tools[s["tool"]]["meta"]), f"{s['tool']} is app-only"
        assert set(s["args"]) <= tools[s["tool"]]["props"], s
        assert not BANNED_RE.search(s["why"])
        assert "$" not in s["why"]


@pytest.mark.parametrize("name,args", CASES)
async def test_text_says_the_same_steps_before_the_card(api, name: str, args: dict) -> None:
    result = await call(name, args)
    text = text_of(result)
    card = result.structuredContent["card"]
    head = text.index("Next (calls that fit this answer")
    assert head < text.index(card["law"]), "the card block closes the answer"
    block = text[head:].split("\n\n")[0]
    assert block == next_steps.text_block(result.structuredContent["next"])


async def test_prices_fill_in_the_package_and_the_zip_given(api) -> None:
    steps = (await call("compare_prices", {"drug": "atorvastatin", "zip": "33101"})).structuredContent["next"]
    assert steps[0] == {
        "tool": "get_savings_card",
        "args": {"drug": "atorvastatin-calcium"},
        "why": steps[0]["why"],
    }
    near = next(s for s in steps if s["tool"] == "find_nearby_pharmacies")
    assert near["args"] == {
        "drug": "atorvastatin-calcium",
        "strength": "10mg",
        "form": "Tablet",
        "quantity": 30,
        "zip": "33101",
    }


async def test_national_answer_asks_for_a_zip_first(api) -> None:
    api["near"].respond(json=fx("prices_near_needs_zip"))
    steps = (await call("compare_prices", {"drug": "atorvastatin"})).structuredContent["next"]
    assert steps[0]["tool"] == "compare_prices"
    assert steps[0]["ask"] == "zip"
    assert steps[0]["args"]["drug"] == "atorvastatin-calcium"
    assert "zip" not in steps[0]["args"]
    assert all(s["tool"] != "find_nearby_pharmacies" for s in steps)


async def test_a_typed_place_never_becomes_an_argument(api) -> None:
    """``where`` (app-only) is used for one request; the ZIP it resolved to is
    not handed on as if the person had given it."""
    api["near"].respond(json=fx("prices_near_address"))
    typed = "233 S Wacker Dr, Chicago"
    result = await call("ui_prices", {"slug": "atorvastatin-calcium", "where": typed})
    blob = json.dumps(result.structuredContent.get("next") or [])
    assert "Wacker" not in blob
    assert all("zip" not in s["args"] for s in result.structuredContent.get("next") or [])


async def test_what_the_person_typed_is_not_echoed(api) -> None:
    for name, args, typed in (
        ("search_drugs", {"query": "atorva"}, "atorva"),
        ("open_price_finder", {"query": "atorva"}, "atorva"),
        ("find_us_equivalent", {"brand": "Нурофен"}, "Нурофен"),
    ):
        steps = (await call(name, args)).structuredContent["next"]
        values = [v for s in steps for v in s["args"].values()]
        assert typed not in values, name


@pytest.mark.parametrize(
    "name,args",
    [
        ("compare_prices", {"drug": "oxycodone", "zip": "33101"}),
        ("get_prescription_options", {"drug": "oxycodone"}),
        ("get_drug", {"slug": "oxycodone"}),
    ],
)
async def test_restricted_medicine_gets_no_prescription_route(api, name: str, args: dict) -> None:
    api["search"].respond(json={"results": [{"slug": "oxycodone-hcl", "name": "Oxycodone HCl", "kind": "generic"}]})
    steps = (await call(name, args)).structuredContent.get("next") or []
    assert all(s["tool"] != "get_prescription_options" for s in steps)


def test_foreign_brand_leads_to_a_us_drug_only_for_the_same_ingredient() -> None:
    us = {"slug": "dicyclomine-hcl", "name": "Dicyclomine"}
    same = next_steps.after_equivalent({"usClass": "same_inn", "us": us})
    assert [s["tool"] for s in same] == ["compare_prices", "get_savings_card"]
    # A different medicine is never priced as the brand's next step — even if a
    # US drug were (wrongly) passed in.
    other = next_steps.after_equivalent({"usClass": "rx_alternative", "us": us})
    assert [s["tool"] for s in other] == ["get_prescription_options"]
    assert other[0]["args"] == {}
    assert next_steps.after_equivalent({"usClass": "rx_alternative", "us": us}, restricted=True) == []
    assert next_steps.after_equivalent({"usClass": "no_equivalent", "us": us}) == []
    assert next_steps.after_equivalent(None) == []


def test_one_match_goes_to_prices_several_ask_which() -> None:
    one = next_steps.after_matches([{"slug": "estradiol", "name": "Estradiol"}], [], detail=True)
    assert [(s["tool"], s["args"]) for s in one] == [
        ("compare_prices", {"drug": "estradiol"}),
        ("get_drug", {"slug": "estradiol"}),
    ]
    # Several matches still lead to prices — of the first one (a routing eval on
    # a real model stopped at the search when the step said "ask which").
    many = next_steps.after_matches([{"slug": "estradiol"}, {"slug": "estrace"}], [{"brand": "Estrofem"}])
    assert len(many) == 1 and "ask" not in many[0] and many[0]["args"] == {"drug": "estradiol"}
    assert "another match" in many[0]["why"]
    foreign = next_steps.after_matches([], [{"brand": "Estrofem", "countries": ["DK"]}])
    assert [(s["tool"], s["args"]) for s in foreign] == [("find_us_equivalent", {"brand": "Estrofem"})]
    assert next_steps.after_matches([], []) == []
    # Not a slug → not an argument.
    assert next_steps.after_matches([{"slug": "../etc/passwd"}], []) == []


def test_unseen_pack_size_points_at_one_that_was_seen() -> None:
    data = {
        "drug": {"slug": "estradiol"},
        "package": {"form": "Tablet", "strength": "1mg", "quantity": 45},
        "origin": {"precision": "zip", "zip": "78704"},
        "rows": [],
        "needsZip": False,
        "coverage": {"status": "other_quantities", "quantities": [30, 90]},
    }
    steps = next_steps.after_prices(data)
    other = next(s for s in steps if s["tool"] == "compare_prices")
    assert other["args"] == {"drug": "estradiol", "strength": "1mg", "form": "Tablet", "quantity": 30, "zip": "78704"}


def test_unseen_pack_size_is_not_sent_to_the_stores() -> None:
    """Live 2026-10-03: Ozempic × 7 (never seen) offered the stores for × 7."""
    data = {
        "drug": {"slug": "ozempic"},
        "package": {"form": "Multidose Pen", "strength": "2mg/3ml", "quantity": 7},
        "origin": {"precision": "zip", "zip": "33101"},
        "rows": [{"storeCount": 3}],
        "needsZip": False,
        "coverage": {"status": "other_quantities", "quantities": [1]},
    }
    steps = next_steps.after_prices(data)
    assert all(s["tool"] != "find_nearby_pharmacies" for s in steps)
    assert [s["args"].get("quantity") for s in steps if s["tool"] == "compare_prices"] == [1]


def test_a_zip_is_handed_on_only_when_the_person_gave_it() -> None:
    row = {"storeCount": 2}
    base = {"drug": {"slug": "estradiol"}, "package": {}, "rows": [row], "needsZip": False, "coverage": {}}
    for origin, expected in (
        ({"precision": "zip", "zip": "78704"}, "78704"),
        ({"precision": "address", "zip": "60606"}, None),
        ({"precision": "approx", "zip": None}, None),
        ({"precision": "zip", "zip": "7870"}, None),
    ):
        near = next(s for s in next_steps.after_prices({**base, "origin": origin}) if s["tool"] == "find_nearby_pharmacies")
        assert near["args"].get("zip") == expected, origin


def test_blank_arguments_are_dropped_and_the_text_reads_as_a_call() -> None:
    s = next_steps.step("compare_prices", "why", ask="zip", drug="estradiol", strength=None, form="", quantity=30)
    assert s["args"] == {"drug": "estradiol", "quantity": 30}
    assert next_steps.call_text(s) == (
        '- ask for a 5-digit US ZIP, then compare_prices(drug="estradiol", quantity=30) — why'
    )
    assert next_steps.text_block([]) == ""


async def test_failed_email_points_at_the_printable_card(api) -> None:
    api["card_email"].respond(503)
    result = await call("email_savings_card", {"email": "jane@example.com", "consent": True})
    assert [s["tool"] for s in result.structuredContent["next"]] == ["get_savings_card"]


async def test_unknown_name_with_one_suggestion_points_at_it(api) -> None:
    api["near"].respond(404, json=fx("drug_not_found"))
    sc = (await call("compare_prices", {"drug": "atorvastatinz"})).structuredContent
    slugs = [s["slug"] for s in sc["error"]["suggestions"]]
    steps = sc["next"]
    assert steps[0]["tool"] == "compare_prices" and steps[0]["args"] == {"drug": slugs[0]}
    schemas.validate(sc)


@pytest.mark.parametrize("name,args", [("get_dataset_info", {}), ("ui_suggest", {"q": "atorva"})])
async def test_no_steps_where_there_is_no_medicine_or_no_model(api, name: str, args: dict) -> None:
    assert "next" not in (await call(name, args)).structuredContent


def test_instructions_say_how_to_use_next() -> None:
    line = next(ln for ln in server.INSTRUCTIONS.splitlines() if "`next`" in ln)
    assert "`ask`" in line and not BANNED_RE.search(line)
