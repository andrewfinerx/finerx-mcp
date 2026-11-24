"""MCP 2.3 (#175 stage 2): millilitres and grams — a count of packages or what
the pharmacy bills, never one scaled into the other."""
from __future__ import annotations

import pytest
from conftest import body_of, call, fx, params_of, text_of

from finerx_mcp import schemas
from finerx_mcp.amounts import Pack, parse, split_text

NOTE = "A pharmacy may dispense only the whole package (50 g each)."


@pytest.mark.parametrize(
    "value, pack",
    [
        (None, Pack()),
        (True, Pack()),
        (0, Pack()),
        (-3, Pack()),
        (30, Pack(quantity=30, asked="30")),
        (10.0, Pack(quantity=10, asked="10")),
        (2.5, Pack(billing=2.5, asked="2.5")),
        ("90", Pack(quantity=90, asked="90")),
        ("2.5", Pack(billing=2.5, asked="2.5")),
        ("30 g", Pack(billing=30, unit="g", asked="30 g")),
        ("50gm", Pack(billing=50, unit="g", asked="50gm")),
        ("10 mL", Pack(billing=10, unit="ml", asked="10 mL")),
        ("2.5ml", Pack(billing=2.5, unit="ml", asked="2.5ml")),
        ("2,5 мл", Pack(billing=2.5, unit="ml", asked="2,5 мл")),
        ("50 г", Pack(billing=50, unit="g", asked="50 г")),
        ("4 pens", Pack(quantity=4, asked="4 pens")),
        ("25 ampules", Pack(quantity=25, asked="25 ampules")),
        ("90 tablets", Pack(quantity=90, asked="90 tablets")),
        ("x90", Pack(quantity=90, asked="x90")),
        # a label read back: its amount
        ("1 tube · 50 g", Pack(billing=50, unit="g", asked="50 g")),
        ("30 g · from a 50 g tube", Pack(billing=30, unit="g", asked="30 g")),
        ("4 pens · 2 mL", Pack(billing=2, unit="ml", asked="2 mL")),
        ("2 bottles · 60 tablets", Pack(quantity=2, asked="2 bottles")),
        # a concentration is not an amount; nonsense is nothing
        ("250 mg/5 mL", Pack()),
        ("a lot", Pack()),
        ("", Pack()),
    ],
)
def test_parse(value, pack):
    assert parse(value) == pack


@pytest.mark.parametrize(
    "text_, name, strength, pack",
    [
        ("azelaic acid 30 g", "azelaic acid", None, Pack(billing=30, unit="g", asked="30 g")),
        ("azelaic acid 15% gel 30 g", "azelaic acid gel", "15 %", Pack(billing=30, unit="g", asked="30 g")),
        (
            "testosterone cypionate 200 mg/mL 10 mL",
            "testosterone cypionate", "200 mg/ml", Pack(billing=10, unit="ml", asked="10 mL"),
        ),
        ("latanoprost 0.005% 2.5 ml", "latanoprost", "0.005 %", Pack(billing=2.5, unit="ml", asked="2.5 ml")),
        ("albuterol 2.5mg/3ml 75 ml", "albuterol", "2.5 mg/3ml", Pack(billing=75, unit="ml", asked="75 ml")),
        ("albuterol 0.083% 25 ampules", "albuterol", "0.083 %", Pack(quantity=25, asked="25 ampules")),
        ("Trulicity 1.5 mg/0.5 mL 4 pens", "Trulicity", "1.5 mg/0.5ml", Pack(quantity=4, asked="4 pens")),
        ("mupirocin ointment 2% 22 g", "mupirocin ointment", "2 %", Pack(billing=22, unit="g", asked="22 g")),
        ("erythromycin ophthalmic ointment 3.5 g", "erythromycin ophthalmic ointment", None,
         Pack(billing=3.5, unit="g", asked="3.5 g")),
        # "N g" alone and small is the dose of a tablet or a vial
        ("valacyclovir 1 g", "valacyclovir", "1 g", Pack()),
        ("valacyclovir 1 g 30 tablets", "valacyclovir", "1 g", Pack(quantity=30, asked="30 tablets")),
        ("sucralfate 1 g/10 ml", "sucralfate", "1 g/10ml", Pack()),
        ("amoxicillin 400 mg / 5 ml 100 ml", "amoxicillin", "400 mg/5ml", Pack(billing=100, unit="ml", asked="100 ml")),
    ],
)
def test_split_text(text_, name, strength, pack):
    assert split_text(text_, None, None, Pack()) == (name, strength, pack)


def test_an_explicit_amount_wins_and_the_one_in_the_name_is_not_a_strength():
    assert split_text("azelaic acid 30 g", None, None, parse("50 g")) == (
        "azelaic acid", None, Pack(billing=50, unit="g", asked="50 g"),
    )
    assert split_text("atorvastatin 20 mg", "40 mg", None, parse(90)) == (
        "atorvastatin 20 mg", "40 mg", Pack(quantity=90, asked="90"),
    )


def test_fields():
    assert Pack().fields() == {"quantity": None, "units": "billing"}
    assert parse("30 g").fields() == {"quantity": None, "units": "billing", "billingQuantity": 30}
    assert parse(90).fields() == {"quantity": 90, "units": "billing"}


def _azelaic(**overrides) -> dict:
    near = fx("prices_near")
    near["drug"] = {"slug": "azelaic-acid", "name": "Azelaic Acid", "kind": "generic"}
    near["package"] = {
        "form": "Gel", "strength": "15%", "quantity": 0.6, "label": "15% Gel · 30 g · from a 50 g tube",
        "billingQuantity": 30, "billingUnit": "g", "packageSize": 50, "packageNoun": "tube",
        "contentNoun": None, "splittable": False, "labelNote": NOTE, "cardForm": None, "cardStrength": None,
    }
    near["coverage"] = {"status": "exact", "quantities": [0.6, 1, 2], "billingQuantities": [30, 50, 100]}
    near.update(overrides)
    return near


def _azelaic_options() -> dict:
    return {
        "drug": {"slug": "azelaic-acid", "name": "Azelaic Acid", "kind": "generic"},
        "configs": [
            {
                "form": "Gel", "strength": "15%", "label": "15% Gel",
                "quantities": [
                    {"quantity": 0.6, "label": "15% Gel · 30 g · from a 50 g tube", "billingQuantity": 30,
                     "labelNote": NOTE, "cardFrom": {"amount": 31.2, "observedAt": "2026-11-24"}, "chainsPriced": 9},
                    {"quantity": 1, "label": "15% Gel · 1 tube · 50 g", "billingQuantity": 50,
                     "cardFrom": {"amount": 35.89, "observedAt": "2026-11-24"}, "chainsPriced": 16},
                    {"quantity": 2, "label": "15% Gel · 2 tubes · 100 g", "billingQuantity": 100,
                     "cardFrom": {"amount": 70.1, "observedAt": "2026-11-24"}, "chainsPriced": 12},
                ],
            }
        ],
        "defaultConfig": {"form": "Gel", "strength": "15%", "quantity": 1},
    }


async def test_compare_prices_sends_grams_as_the_billed_amount(api) -> None:
    api["near"].respond(json=_azelaic())
    api["options"].respond(json=_azelaic_options())
    result = await call("compare_prices", {"drug": "azelaic acid", "quantity": "30 g", "zip": "33101"})
    body = body_of(api["near"])
    assert body["billingQuantity"] == 30 and body["units"] == "billing"
    assert "quantity" not in body  # never a count of 0.6 tubes
    assert params_of(api["options"])["units"] == "billing"
    text = text_of(result)
    assert "Azelaic Acid — 15% Gel · 30 g · from a 50 g tube" in text
    assert NOTE in text
    env = schemas.validate(result.structuredContent)
    assert env.data.package.labelNote == NOTE
    assert [q.billingQuantity for q in env.data.options.configs[0].quantities] == [30, 50, 100]


async def test_an_amount_in_the_name_is_not_a_strength(api) -> None:
    await call("compare_prices", {"drug": "testosterone cypionate 200 mg/mL 10 mL"})
    body = body_of(api["near"])
    assert body["drug"] == "testosterone cypionate"
    assert body["strength"] == "200 mg/ml"
    assert body["billingQuantity"] == 10
    await call("compare_prices", {"drug": "azelaic acid 30 g"})
    body = body_of(api["near"])
    assert body["drug"] == "azelaic acid" and "strength" not in body and body["billingQuantity"] == 30


async def test_an_amount_not_seen_is_named_as_asked_with_the_sizes_seen(api) -> None:
    near = _azelaic()
    near["package"] = {"form": "Gel", "strength": "15%", "quantity": None, "label": "15% Gel"}
    near["coverage"] = {"status": "other_quantities", "quantities": [1, 2], "billingQuantities": [50, 100]}
    api["near"].respond(json=near)
    api["options"].respond(json=_azelaic_options())
    text = text_of(await call("compare_prices", {"drug": "azelaic acid", "quantity": "45 g"}))
    assert "We have not seen a card price for 45 g" in text
    assert "1 tube · 50 g, 2 tubes · 100 g" in text
    assert "None" not in text


async def test_a_count_of_pens_stays_a_count(api) -> None:
    await call("compare_prices", {"drug": "trulicity", "quantity": "4 pens"})
    body = body_of(api["near"])
    assert body["quantity"] == 4 and "billingQuantity" not in body


async def test_the_card_picks_a_part_of_a_package_by_its_amount(api) -> None:
    api["near"].respond(json=_azelaic())
    result = await call("ui_prices", {"slug": "azelaic-acid", "form": "Gel", "strength": "15%", "billing_quantity": 30})
    body = body_of(api["near"])
    assert body["billingQuantity"] == 30 and "quantity" not in body
    schemas.validate(result.structuredContent)
    # an older card sends the fraction itself: the default package answers
    await call("ui_prices", {"slug": "azelaic-acid", "quantity": 0.6})
    body = body_of(api["near"])
    assert "quantity" not in body and "billingQuantity" not in body
    await call("ui_nearby", {"slug": "azelaic-acid", "zip": "33101", "billing_quantity": 30})
    assert body_of(api["near"])["billingQuantity"] == 30


async def test_pharmacies_and_the_basket_take_amounts_too(api) -> None:
    await call("find_nearby_pharmacies", {"zip": "33101", "drug": "latanoprost 0.005%", "quantity": "2.5 mL"})
    body = body_of(api["near"])
    assert body["billingQuantity"] == 2.5 and body["strength"] == "0.005 %"
    await call("compare_basket", {"drugs": ["azelaic acid 15% gel 30 g", "atorvastatin 20 mg 90 tablets"], "zip": "33101"})
    bodies = [body_of(api["near"], i) for i in (-2, -1)]
    by_drug = {b["drug"]: b for b in bodies}
    assert by_drug["azelaic acid gel"]["billingQuantity"] == 30
    assert by_drug["atorvastatin"]["quantity"] == 90 and "billingQuantity" not in by_drug["atorvastatin"]
    await call("ui_basket", {"slugs": ["azelaic-acid", "atorvastatin-calcium"], "quantities": [0, 90], "billing_quantities": [30, 0]})
    bodies = [body_of(api["near"], i) for i in (-2, -1)]
    by_drug = {b["drug"]: b for b in bodies}
    assert by_drug["azelaic-acid"]["billingQuantity"] == 30
    assert by_drug["atorvastatin-calcium"]["quantity"] == 90


async def test_get_drug_lists_pack_sizes_by_label(api) -> None:
    api["options"].respond(json=_azelaic_options())
    text = text_of(await call("get_drug", {"slug": "azelaic-acid"}))
    assert "15% Gel (30 g · from a 50 g tube, 1 tube · 50 g, 2 tubes · 100 g)" in text


API_NOTE = "Pharmacies usually dispense whole packages (50 g each)."
OUR_NOTE = "A pharmacy may dispense only the whole package (50 g each)."


async def test_the_whole_package_note_keeps_to_the_card_law_words(api) -> None:
    """The API's English note says "usually" — a card-law word no text or card
    of ours may carry (card_law.BANNED_RE): the same fact, said without it."""
    from finerx_mcp.card_law import BANNED_RE

    near = _azelaic()
    near["package"]["labelNote"] = API_NOTE
    options = _azelaic_options()
    options["configs"][0]["quantities"][0].update(labelNote=API_NOTE, packageSize=50, billingUnit="g")
    api["near"].respond(json=near)
    api["options"].respond(json=options)
    result = await call("compare_prices", {"drug": "azelaic acid", "quantity": "30 g"})
    text = text_of(result)
    assert OUR_NOTE in text
    assert not BANNED_RE.search(text)
    import json

    assert not BANNED_RE.search(json.dumps(result.structuredContent, ensure_ascii=False))
    assert result.structuredContent["data"]["package"]["labelNote"] == OUR_NOTE
    # another language's note is the API's own, untouched
    near = _azelaic()
    near["package"]["labelNote"] = "Аптеки обычно отпускают упаковку целиком (по 50 г)."
    api["near"].respond(json=near)
    text = text_of(await call("compare_prices", {"drug": "azelaic acid", "quantity": "30 g", "locale": "ru"}))
    assert "Аптеки обычно отпускают упаковку целиком (по 50 г)." in text


def test_package_note_without_a_size():
    from finerx_mcp.views import package_note

    assert package_note({"labelNote": API_NOTE}) == "A pharmacy may dispense only the whole package."
    assert package_note({"labelNote": API_NOTE, "packageSize": 0.5, "billingUnit": "ml"}) == (
        "A pharmacy may dispense only the whole package (0.5 mL each)."
    )
    assert package_note({"labelNote": None}) is None
    assert package_note({}) is None


def test_a_from_price_is_never_a_part_of_an_unsplittable_package():
    from finerx_mcp.views import from_card_price

    best = from_card_price(_azelaic_options())
    assert best == {"amount": 35.89, "observedAt": "2026-11-24", "package": "15% Gel · 1 tube · 50 g"}
    only_part = {"configs": [{"label": "15% Gel", "quantities": [_azelaic_options()["configs"][0]["quantities"][0]]}]}
    assert from_card_price(only_part)["amount"] == 31.2  # unless that is all there is
