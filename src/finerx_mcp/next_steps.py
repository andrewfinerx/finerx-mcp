"""``next`` — the calls that fit after an answer, with their arguments filled in.

An assistant that has just read a price has to work out for itself that the card
comes next, which tool hands it over and what to pass. It guesses, and a guess
drops the slug or the package. So every model-facing result says it: up to three
steps, each ``{tool, args, why}``, built from the answer itself — the slug the
API resolved, the package it priced, the ZIP it answered for.

``ask`` names the one thing to get from the person before calling (a ZIP, the
medicine, which of several, an email address and a yes); the arguments already
known are still filled in.

Rules the builders keep:

* Arguments are data FineRx returned (a slug, a package, a 5-digit ZIP the
  person gave) — never the text the person typed, and never a place finer than
  the ZIP the answer already shows.
* A controlled or age-restricted medicine gets prices and the card only: no
  step leads to a prescription route.
* For a foreign brand, the US drug is a next step only when it has the same
  active ingredient (``same_inn``); nothing is offered in place of the others.
* ``why`` is plain and promises nothing: no amounts, none of the card law's
  banned words.
"""
from __future__ import annotations

import re
from typing import Any

MAX_STEPS = 3
ASKS = ("zip", "medicine", "which_medicine", "email_and_consent")

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,120}$")  # = client.SLUG_RE
_ZIP = re.compile(r"^\d{5}$")

_ASK_TEXT = {
    "zip": "ask for a 5-digit US ZIP, then",
    "medicine": "ask which medicine, then",
    "which_medicine": "ask which of the matches they mean, then",
    "email_and_consent": "ask for the email address and an explicit yes, then",
}


def step(tool: str, why: str, *, ask: str | None = None, **args: Any) -> dict[str, Any]:
    """One step; empty arguments are dropped so a call never carries a blank."""
    out: dict[str, Any] = {
        "tool": tool,
        "args": {k: v for k, v in args.items() if v is not None and v != "" and v != []},
        "why": why,
    }
    if ask:
        out["ask"] = ask
    return out


def _slug(value: Any) -> str | None:
    return value if isinstance(value, str) and _SLUG.match(value) else None


def _package(package: dict | None) -> dict[str, Any]:
    p = package if isinstance(package, dict) else {}
    qty = p.get("quantity")
    return {
        "strength": p.get("strength"),
        "form": p.get("form"),
        "quantity": qty if isinstance(qty, int) and not isinstance(qty, bool) else None,
    }


def _given_zip(origin: dict | None) -> str | None:
    """The ZIP the person gave (``precision: zip``) — not one derived from a
    typed address or from the host's approximate location."""
    o = origin if isinstance(origin, dict) else {}
    z = o.get("zip")
    return z if o.get("precision") == "zip" and isinstance(z, str) and _ZIP.match(z) else None


def _placed(origin: dict | None) -> bool:
    return isinstance(origin, dict) and origin.get("precision") not in (None, "none")


def _cap(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return steps[:MAX_STEPS]


# --- one builder per answer ---------------------------------------------------------


def after_prices(data: dict | None, *, restricted: bool = False) -> list[dict[str, Any]]:
    d = data if isinstance(data, dict) else {}
    slug = _slug((d.get("drug") or {}).get("slug"))
    if not slug:
        return []
    pkg = _package(d.get("package"))
    origin = d.get("origin")
    steps: list[dict[str, Any]] = []
    if d.get("needsZip"):
        steps.append(
            step(
                "compare_prices",
                "These are national prices; with a ZIP the answer shows which chains have a store nearby.",
                ask="zip",
                drug=slug,
                **pkg,
            )
        )
    steps.append(
        step("get_savings_card", "The card that gets these prices, to keep, print or send.", drug=slug)
    )
    first = next(
        (r for r in d.get("rows") or [] if isinstance(r, dict) and isinstance(r.get("price"), dict) and r.get("family")),
        None,
    )
    if first and not restricted and not d.get("needsZip"):
        steps.append(
            step(
                "get_transfer_steps",
                "Only if their prescription is at another pharmacy: how to move it to the first chain in the list.",
                chain=first["family"],
                drug=slug,
                **pkg,
                zip=_given_zip(origin),
            )
        )
    coverage = d.get("coverage") or {}
    seen = [q for q in coverage.get("quantities") or [] if isinstance(q, int) and not isinstance(q, bool)]
    # A package nobody was seen pricing: the stores would come back without a
    # price, so the step is the pack size that WAS seen, not the stores.
    unpriced = coverage.get("status") in ("other_quantities", "none")
    if coverage.get("status") == "other_quantities" and seen:
        steps.append(
            step(
                "compare_prices",
                "This pack size was not seen with a price; this one was. Never scale a price between sizes.",
                drug=slug,
                **{**pkg, "quantity": seen[0]},
                zip=_given_zip(origin),
            )
        )
    has_store = any(int(r.get("storeCount") or 0) > 0 for r in d.get("rows") or [] if isinstance(r, dict))
    if has_store and _placed(origin) and not unpriced:
        steps.append(
            step(
                "find_nearby_pharmacies",
                "Addresses and distances of the stores of these chains.",
                drug=slug,
                **pkg,
                zip=_given_zip(origin),
            )
        )
    if not restricted:
        steps.append(
            step(
                "get_prescription_options",
                "Only if the person says they have no prescription yet.",
                drug=slug,
            )
        )
    return _cap(steps)


def after_pharmacies(data: dict | None, *, restricted: bool = False) -> list[dict[str, Any]]:
    d = data if isinstance(data, dict) else {}
    origin = d.get("origin")
    slug = _slug((d.get("drug") or {}).get("slug"))
    pkg = _package(d.get("package"))
    steps: list[dict[str, Any]] = []
    if not _placed(origin):
        steps.append(
            step(
                "find_nearby_pharmacies",
                "No place was given, so no store could be listed.",
                ask="zip",
                drug=slug,
                **(pkg if slug else {}),
            )
        )
    elif slug:
        steps.append(
            step(
                "compare_prices",
                "Every chain's card price for this package, with dates.",
                drug=slug,
                **pkg,
                zip=_given_zip(origin),
            )
        )
    else:
        steps.append(
            step(
                "compare_prices",
                "Card prices at these chains for a medicine the person names.",
                ask="medicine",
                zip=_given_zip(origin),
            )
        )
    steps.append(step("get_savings_card", "The card to show at any of these pharmacies.", drug=slug))
    return _cap(steps)


def after_card(data: dict | None) -> list[dict[str, Any]]:
    d = data if isinstance(data, dict) else {}
    slug = _slug((d.get("drug") or {}).get("slug"))
    steps: list[dict[str, Any]] = []
    if slug:
        steps.append(step("compare_prices", "What each chain was seen charging with this card.", drug=slug))
    else:
        steps.append(
            step("compare_prices", "What the card gets for a medicine the person takes.", ask="medicine")
        )
    steps.append(
        step(
            "email_savings_card",
            "Only if the person wants the card in their inbox. Never send without their yes.",
            ask="email_and_consent",
        )
    )
    return _cap(steps)


def after_matches(
    results: list[dict] | None, foreign: list[dict] | None, *, detail: bool = False
) -> list[dict[str, Any]]:
    """After a search (``search_drugs``, ``open_price_finder``): the prices of
    the closest match; only a foreign brand → what it is in the US.

    Several matches still lead to prices, of the FIRST one. Telling the model
    to ask first stopped it there: a routing eval on a real model (2026-10-03)
    answered "how much is atorvastatin 40 mg" with a question instead of a
    price. The step says the match is the closest one and that another may have
    been meant."""
    slugs = [s for s in (_slug(r.get("slug")) for r in results or [] if isinstance(r, dict)) if s]
    brands = [b.get("brand") for b in foreign or [] if isinstance(b, dict) and b.get("brand")]
    steps: list[dict[str, Any]] = []
    if len(slugs) == 1:
        steps.append(step("compare_prices", "Card prices by chain for this medicine.", drug=slugs[0]))
        if detail:
            steps.append(
                step("get_drug", "Its strengths and pack sizes, if the person has not said theirs.", slug=slugs[0])
            )
    elif slugs:
        steps.append(
            step(
                "compare_prices",
                "Card prices for the closest match. Pass the strength and pack size the person gave. "
                "Brand and generic are different products: if they may have meant another match, say which one you priced.",
                drug=slugs[0],
            )
        )
    if brands and not slugs:
        steps.append(
            step(
                "find_us_equivalent",
                "The text matched a brand from another country, not a US product.",
                brand=brands[0],
            )
        )
    return _cap(steps)


def after_drug(structured: dict | None, *, restricted: bool = False) -> list[dict[str, Any]]:
    s = structured if isinstance(structured, dict) else {}
    slug = _slug(s.get("slug"))
    if not slug:
        return []
    pkg = _package((s.get("defaultPackage") or {}).get("package"))
    steps = [
        step(
            "compare_prices",
            "Prices near the person. The package filled in is the one most chains price; "
            "use the person's own strength and quantity when they gave them.",
            drug=slug,
            **pkg,
        ),
        step("get_savings_card", "The card that gets these prices.", drug=slug),
    ]
    if not restricted:
        steps.append(
            step("get_prescription_options", "Only if the person says they have no prescription yet.", drug=slug)
        )
    return _cap(steps)


def after_equivalent(data: dict | None, *, restricted: bool = False) -> list[dict[str, Any]]:
    """``data`` is the equivalent VIEW's data: its ``us`` exists only for
    ``same_inn``, so a different medicine can never become a next step here."""
    d = data if isinstance(data, dict) else {}
    us_slug = _slug((d.get("us") or {}).get("slug"))
    if d.get("usClass") == "same_inn" and us_slug:
        return _cap(
            [
                step(
                    "compare_prices",
                    "Card prices in the US for the same active ingredient. Same ingredient is not the same product.",
                    drug=us_slug,
                ),
                step("get_savings_card", "The card, for when a US prescriber has written the prescription.", drug=us_slug),
            ]
        )
    if d.get("usClass") == "rx_alternative" and not restricted:
        return [
            step(
                "get_prescription_options",
                "This product is not sold in the US. Where to see a US clinician; name no substitute.",
            )
        ]
    return []


def after_transfer(data: dict | None) -> list[dict[str, Any]]:
    d = data if isinstance(data, dict) else {}
    slug = _slug((d.get("drug") or {}).get("slug"))
    family = (d.get("chain") or {}).get("family")
    steps: list[dict[str, Any]] = [
        step("get_savings_card", "The card to show at pickup at the new pharmacy.", drug=slug)
    ]
    if slug:
        steps.append(
            step(
                "compare_prices",
                "What each chain was seen charging for this package, if they have not chosen one yet.",
                drug=slug,
                **_package(d.get("package")),
                zip=_given_zip(d.get("origin")),
            )
        )
    elif family and not d.get("stores"):
        steps.append(
            step(
                "find_nearby_pharmacies",
                "The stores of this chain near the person.",
                ask="zip",
                family=family,
            )
        )
    return _cap(steps)


def after_equivalents(items: list[dict] | None) -> list[dict[str, Any]]:
    """Only the medicines with the SAME active ingredient lead on to US prices."""
    slugs: list[str] = []
    for it in items or []:
        if not isinstance(it, dict) or it.get("usClass") != "same_inn":
            continue
        if (s := _slug((it.get("us") or {}).get("slug"))) and s not in slugs:
            slugs.append(s)
    if len(slugs) > 1:
        return [
            step(
                "compare_basket",
                "Card prices in the US for the ones with the same active ingredient, by pharmacy chain. "
                "Same ingredient is not the same product.",
                drugs=slugs,
            ),
            step("get_savings_card", "The card, for when a US prescriber has written the prescriptions."),
        ]
    if slugs:
        return [
            step(
                "compare_prices",
                "Card prices in the US for the same active ingredient. Same ingredient is not the same product.",
                drug=slugs[0],
            ),
            step("get_savings_card", "The card, for when a US prescriber has written the prescription.", drug=slugs[0]),
        ]
    return []


def after_rx(data: dict | None) -> list[dict[str, Any]]:
    d = data if isinstance(data, dict) else {}
    slug = _slug((d.get("drug") or {}).get("slug"))
    if not slug:
        return [step("compare_prices", "Card prices once the person names the medicine.", ask="medicine")]
    steps = [step("compare_prices", "What this medicine costs with the card, by chain.", drug=slug)]
    if not d.get("restricted"):
        steps.append(step("get_savings_card", "The card to use once there is a prescription.", drug=slug))
    return _cap(steps)


def after_basket(data: dict | None) -> list[dict[str, Any]]:
    d = data if isinstance(data, dict) else {}
    slugs = [s for s in (_slug((it.get("drug") or {}).get("slug")) for it in d.get("items") or []) if s]
    if not slugs:
        return []
    origin = d.get("origin")
    steps: list[dict[str, Any]] = []
    if d.get("needsZip"):
        steps.append(
            step(
                "compare_basket",
                "These sums are by chain nationally; with a ZIP only chains with a store nearby are listed.",
                ask="zip",
                drugs=slugs,
            )
        )
    steps.append(step("get_savings_card", "One card covers every medicine in the list."))
    rows = [r for r in d.get("rows") or [] if isinstance(r, dict) and r.get("total")]
    if rows and not d.get("needsZip") and int(rows[0].get("storeCount") or 0) > 0:
        steps.append(
            step(
                "find_nearby_pharmacies",
                "Addresses of the first chain in the list.",
                family=rows[0].get("family"),
                zip=_given_zip(origin),
            )
        )
    steps.append(
        step("compare_prices", "Other strengths or pack sizes of one of them.", ask="which_medicine")
    )
    return _cap(steps)


def after_foreign_brands(drug_slug: Any) -> list[dict[str, Any]]:
    slug = _slug(drug_slug)
    return [step("compare_prices", "Card prices for this drug in the US.", drug=slug)] if slug else []


def after_email(sent: bool) -> list[dict[str, Any]]:
    if sent:
        return [step("compare_prices", "What the card gets for a medicine the person takes.", ask="medicine")]
    return [step("get_savings_card", "The email did not go out: offer the printable card and the link instead.")]


def after_not_found(suggestions: list[dict] | None) -> list[dict[str, Any]]:
    """The API did not know the name and offered ones it does."""
    return after_matches(suggestions, None)


# --- what the model reads -----------------------------------------------------------


def _arg(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_arg(v) for v in value) + "]"
    return '"' + str(value).replace('"', "'") + '"'


def call_text(s: dict[str, Any]) -> str:
    args = ", ".join(f"{k}={_arg(v)}" for k, v in (s.get("args") or {}).items())
    call = f"{s['tool']}({args})"
    if ask := _ASK_TEXT.get(s.get("ask") or ""):
        call = f"{ask} {call}"
    return f"- {call} — {s['why']}"


def text_block(steps: list[dict[str, Any]]) -> str:
    """The same steps as ``structuredContent.next``, for a model that is shown
    only ``content``. English on purpose: it is read by the model, not the person."""
    if not steps:
        return ""
    return "\n".join(["Next (calls that fit this answer, arguments filled in from it):", *map(call_text, steps)])
