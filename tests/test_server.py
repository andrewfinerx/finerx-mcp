"""Tests for the FineRx MCP server.

The HTTP layer is stubbed by monkeypatching ``FinerxClient.get``/``post`` with
canned payloads shaped like the public API contract — no network, no key, so the
suite is safe to run anywhere. Listing (tools/resources/prompts) goes through a
REAL in-memory MCP session so the annotations and schemas we assert are the ones
a client actually receives; behavioural tests call the tool functions directly.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import ImageContent, TextContent

from finerx_mcp import __version__, server
from finerx_mcp.client import FinerxApiError, FinerxClient
from finerx_mcp.widget import WIDGET_MIME_TYPE, WIDGET_URI, load_widget_html

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

# Grabbed before the autouse fixture stubs the module attribute, so one test can
# still exercise the REAL fetch-and-swallow path.
REAL_CARD_IMAGE_BYTES = server._card_image_bytes

PNG = b"\x89PNG\r\n\x1a\nfake"

CARD_PAYLOAD: dict[str, Any] = {
    "version": "1",
    "updatedAt": "2026-09-01",
    "locale": "en",
    "channel": "mcp",
    "card": {
        "provider": "LowerMyRx",
        "bin": "610219",
        "pcn": "DRX",
        "group": "MYCARD3993",
        "url": "https://finerxfinder.com/en/card?src=mcp",
    },
    "line": "Free discount card - not insurance.",
    "whatItIs": "A free prescription discount card.",
    "whyUseIt": "It can lower the cash price at the counter.",
    "howToUse": ["Show it at the pharmacy.", "Ask them to run it.", "Compare with cash."],
    "pharmacistPhrase": "Please run this discount card on my prescription.",
    "acceptedAt": "Most US pharmacies",
    "saveHint": "Save the image to your phone.",
    "delivery": {
        "cardUrl": "https://finerxfinder.com/en/card?src=mcp",
        "printUrl": "https://finerxfinder.com/en/card/print?src=mcp",
        "imageUrl": "https://www.finerxfinder.com/card.png?src=mcp",
        "emailEndpoint": "/card/email",
        "smsDeepLink": "sms:?&body=...",
        "smsBody": "FineRx card: BIN 610219 PCN DRX GRP MYCARD3993",
        "walletApple": None,
        "walletGoogle": None,
    },
    "price": {
        "price": 14.5,
        "currency": "USD",
        "observedAt": "2026-09-05",
        "pharmacy": "Walgreens",
        "variantLabel": "10 mg tablet, 30",
        "isLowest": False,
        "note": "Cash was lower at this pharmacy when we last checked.",
    },
    "faq": [{"q": f"Q{i}", "a": f"A{i}"} for i in range(6)],
    # The widget draws the card with these; they must survive the tool untouched.
    "labels": {"cardTitle": "Prescription Card", "bin": "BIN", "pcn": "PCN", "group": "Group"},
    "legal": {
        "disclaimer": "Prices are observed estimates.",
        "notInsurance": "This card is not insurance.",
        "commissionNote": "FineRx may earn a commission.",
        "supportPhone": "1-877-823-1273",
        "supportEmail": "support@lowermyrx.com",
    },
    "meta": {"source": "FineRx", "disclaimer": "Prices via FineRx. Not medical advice.", "docsUrl": "x"},
}

SAVINGS_CARD_BLOCK: dict[str, Any] = {
    "card": CARD_PAYLOAD["card"],
    "line": CARD_PAYLOAD["line"],
    "cardUrl": "https://finerxfinder.com/en/card?src=mcp",
    "imageUrl": "https://www.finerxfinder.com/card.png?src=mcp",
    "price": CARD_PAYLOAD["price"],
}

COMPARE_PAYLOAD: dict[str, Any] = {
    "product": {"ndc": "00093505698", "drugName": "Atorvastatin", "label": "x", "strength": "10 mg", "form": "tablet"},
    "fromPrice": 9.0,
    "freshness": {"latestObservedAt": "2026-09-05", "status": "fresh"},
    "offers": [
        {
            "pharmacy": "walgreens",
            "savingsProgram": "singlecare",
            "price": 9.0,
            "currency": "USD",
            "observedAt": "2026-09-05",
            "isLowest": True,
        }
    ],
    "savingsCard": SAVINGS_CARD_BLOCK,
    "meta": {"disclaimer": "Prices via FineRx. Not medical advice."},
}

DRUG_PAYLOAD: dict[str, Any] = {
    "name": "Atorvastatin",
    "slug": "atorvastatin",
    "kind": "generic",
    "stats": {"productCount": 3, "packageCount": 5, "chainCount": 2, "vendorCount": 2,
              "fromPrice": 9.0, "latestObservedAt": "2026-09-05"},
    "variants": [{"slug": "10-mg-tablet", "strength": "10 mg", "form": "tablet", "fromPrice": 9.0}],
    "savingsCard": SAVINGS_CARD_BLOCK,
    "meta": {"disclaimer": "Prices via FineRx. Not medical advice."},
}

PRESCRIPTION_PAYLOAD: dict[str, Any] = {
    "locale": "en",
    "drug": "atorvastatin",
    "havePrescription": {"summary": "Take it to any pharmacy.", "steps": ["Pick a pharmacy.", "Show the card."]},
    "noPrescription": {
        "summary": "You need a prescriber first.",
        "options": [{"name": "A telehealth service", "url": "https://x", "note": "n",
                     "affiliate": True, "disclosure": "FineRx may earn a commission."}],
    },
    "brandCostly": {"summary": "Ask about the generic.", "options": []},
    "medicaidNote": "Medicaid may cover it.",
    "disclaimer": "Not medical advice.",
    "meta": {"disclaimer": "Prices via FineRx. Not medical advice."},
}


# --- the analog corpus: what a foreign brand is in the US -------------------
#
# Shaped exactly like /analogs/search + /analogs/{brand_slug}. "No-Spa" is listed
# for two country groups on purpose: that is the case the ``country`` argument
# exists for, and picking the wrong one would tell someone the wrong thing about
# their medicine.
ANALOG_SEARCH_PAYLOAD: dict[str, Any] = {
    "query": "no-spa",
    "count": 2,
    "results": [
        {
            "brand": "No-Spa",
            "brandSlug": "no-spa",
            "brandScript": "Но-шпа",
            "translit": "No-shpa",
            "matchedName": "No-Spa",
            "countries": ["RU", "UA", "BY", "KZ"],
            "usClass": "rx_alternative",
            "inn": "drotaverine hydrochloride",
            "usGeneric": "dicyclomine",
            "pageUrl": "https://www.finerxfinder.com/en/analog/no-spa",
        },
        {
            "brand": "No-Spa",
            "brandSlug": "no-spa-poland",
            "brandScript": None,
            "translit": None,
            "matchedName": "No-Spa",
            "countries": ["Poland"],
            "usClass": "rx_alternative",
            "inn": "drotaverine",
            "usGeneric": "dicyclomine",
            "pageUrl": "https://www.finerxfinder.com/en/analog/no-spa-poland",
        },
    ],
    "meta": {"disclaimer": "Prices via FineRx. Not medical advice."},
}

ANALOG_ENTRY_PAYLOAD: dict[str, Any] = {
    "brand": "Nurofen",
    "brandSlug": "nurofen",
    "brandScript": "Нурофен",
    "translit": "Nurofen",
    "countries": ["RU", "UA"],
    "inn": "ibuprofen",
    "usClass": "same_inn",
    "usGeneric": "ibuprofen",
    "usBrands": ["Advil", "Motrin"],
    "otcOrRxUs": "otc",
    "rxStatus": "over the counter",
    "notes": "Ibuprofen is widely available OTC in the US.",
    "notesLocalized": "El ibuprofeno se vende sin receta en EE. UU.",
    "components": None,
    "usDrug": {
        "slug": "ibuprofen",
        "name": "Ibuprofen",
        "fromPrice": 4.0,
        "observedAt": "2026-09-05",
        "packageLabel": "200 mg · 30 tablets",
        "url": "https://www.finerxfinder.com/en/drug/ibuprofen",
    },
    "pageUrl": "https://www.finerxfinder.com/en/analog/nurofen",
    "usDrugUrl": "https://www.finerxfinder.com/en/drug/ibuprofen",
    "guidance": (
        "Nurofen contains ibuprofen. In the US the same active ingredient is sold as "
        "ibuprofen (brands: Advil, Motrin); ask the pharmacist for it by that name."
    ),
    "disclaimer": (
        "Same active ingredient does not mean the same product: strength, form and "
        "excipients can differ. Confirm with a pharmacist. Not medical advice."
    ),
    "savingsCard": SAVINGS_CARD_BLOCK,
    "meta": {"disclaimer": "Prices via FineRx. Not medical advice."},
}

FOR_DRUG_PAYLOAD: dict[str, Any] = {
    "drugSlug": "ibuprofen",
    "count": 1,
    "items": [
        {
            "brand": "Nurofen",
            "brandSlug": "nurofen",
            "brandScript": "Нурофен",
            "translit": "Nurofen",
            "countries": ["RU", "UA"],
            "inn": "ibuprofen",
            "usClass": "same_inn",
            "pageUrl": "https://www.finerxfinder.com/en/analog/nurofen",
        }
    ],
    "meta": {"disclaimer": "Prices via FineRx. Not medical advice."},
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test forgets to stub a call, instead of hitting the net."""
    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unstubbed HTTP call")

    monkeypatch.setattr(FinerxClient, "get", _boom)
    monkeypatch.setattr(FinerxClient, "post", _boom)
    monkeypatch.setattr(server, "_card_image_bytes", lambda url: None)
    server._image_cache.clear()


def stub_get(monkeypatch: pytest.MonkeyPatch, payload: Any) -> list[tuple[str, dict | None]]:
    """Record every GET and answer with ``payload`` (a dict, or path->dict)."""
    calls: list[tuple[str, dict | None]] = []

    def _get(self: FinerxClient, path: str, params: dict | None = None) -> dict:
        calls.append((path, params))
        if isinstance(payload, dict) and payload.get("__by_path__"):
            return payload[path]
        return payload

    monkeypatch.setattr(FinerxClient, "get", _get)
    return calls


# --- listing: what a real client sees ---------------------------------------


async def test_lists_all_ten_tools_with_annotations() -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        result = await session.list_tools()

    by_name = {t.name: t for t in result.tools}
    assert set(by_name) == {
        "search_drugs",
        "get_drug",
        "compare_prices",
        "find_nearby_pharmacies",
        "get_dataset_info",
        "get_savings_card",
        "email_savings_card",
        "get_prescription_options",
        "find_us_equivalent",
        "foreign_brands_for_drug",
    }
    for name in (
        "search_drugs",
        "get_drug",
        "compare_prices",
        "get_savings_card",
        "get_prescription_options",
        "find_us_equivalent",
        "foreign_brands_for_drug",
    ):
        assert by_name[name].annotations.readOnlyHint is True, name

    email = by_name["email_savings_card"].annotations
    assert email.readOnlyHint is False
    assert email.destructiveHint is False
    assert email.idempotentHint is False
    assert email.openWorldHint is True
    assert email.title == "Email the savings card"


def test_server_advertises_instructions() -> None:
    """The instructions ARE the product here — they are the only honest nudge."""
    instructions = server.mcp._mcp_server.instructions
    assert instructions == server.INSTRUCTIONS
    for phrase in (
        "get_savings_card",
        "email_savings_card",
        "observation date",
        "isLowest",
        # The analog rule is the headline capability: an assistant that does not
        # reach for it answers "what is No-Spa here?" from memory.
        "find_us_equivalent",
        "quote its guidance sentence",
    ):
        assert phrase in instructions


async def test_lists_resources_and_prompts() -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        resources = await session.list_resources()
        prompts = await session.list_prompts()

    assert {str(r.uri) for r in resources.resources} == {
        "finerx://card",
        "finerx://how-it-works",
        WIDGET_URI,
    }
    assert {p.name for p in prompts.prompts} == {
        "price_and_card",
        "prescription_help",
        "us_equivalent",
    }


async def test_prompt_renders_the_card_offer() -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        got = await session.get_prompt("price_and_card", {"drug": "atorvastatin"})
    text = got.messages[0].content.text
    assert "atorvastatin" in text
    assert "observation date" in text
    assert "free discount card" in text


# --- get_savings_card -------------------------------------------------------


async def test_savings_card_returns_dict_and_image(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = stub_get(monkeypatch, CARD_PAYLOAD)
    monkeypatch.setattr(server, "_card_image_bytes", lambda url: PNG)

    # Through a real session: a list return has to survive FastMCP's content
    # conversion AND the wire, which a direct function call would not prove.
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        result = await session.call_tool("get_savings_card", {"locale": "en", "channel": "chatgpt"})

    assert result.isError is False
    assert calls[0][0] == "/card"
    assert calls[0][1]["channel"] == "chatgpt"
    text, image = result.content
    assert isinstance(text, TextContent)
    assert isinstance(image, ImageContent)
    assert image.mimeType == "image/png"
    assert "MYCARD3993" in text.text
    assert "card.png" in text.text  # imageUrl rides in the dict too

    # structuredContent is what the WIDGET reads; the text block is what the
    # model reads. Same object, so they cannot drift.
    structured = result.structuredContent
    assert structured["card"]["bin"] == "610219"
    assert structured["labels"] == CARD_PAYLOAD["labels"]  # passed through verbatim
    assert json.loads(text.text) == structured


async def test_savings_card_without_image_still_returns_the_card(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_get(monkeypatch, CARD_PAYLOAD)
    monkeypatch.setattr(server, "_card_image_bytes", lambda url: None)

    result = server.get_savings_card()

    assert len(result.content) == 1  # no image block, and the card is still there
    payload = result.structuredContent
    assert payload["card"]["group"] == "MYCARD3993"
    assert payload["imageUrl"].startswith("https://www.finerxfinder.com/card.png")
    assert payload["disclaimer"]
    assert len(payload["faq"]) == 6


async def test_savings_card_image_fetch_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead PNG host must not take the card down with it."""
    stub_get(monkeypatch, CARD_PAYLOAD)

    def _explode(url: str, **kwargs: Any) -> Any:
        raise RuntimeError("network is down")

    monkeypatch.setattr(server.httpx, "get", _explode)
    monkeypatch.setattr(server, "_card_image_bytes", REAL_CARD_IMAGE_BYTES)

    result = server.get_savings_card()

    assert len(result.content) == 1
    assert result.structuredContent["card"]["bin"] == "610219"
    # A failure is not cached, so the next call gets to try again.
    assert server._image_cache == {}


async def test_savings_card_api_error_comes_back_as_an_error_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead API must read as a plain error the model can relay, not a crash."""
    def _boom(self: FinerxClient, path: str, params: dict | None = None) -> dict:
        raise FinerxApiError(503, "upstream unavailable", None)

    monkeypatch.setattr(FinerxClient, "get", _boom)

    out = server.get_savings_card()

    assert out == [{"error": "upstream unavailable", "status": 503}]


# --- the card as a UI component --------------------------------------------


async def test_savings_card_tool_points_at_the_widget() -> None:
    """Both keys, or it renders in only half the hosts: ChatGPT reads
    ``openai/outputTemplate``, MCP Apps hosts read ``ui.resourceUri``."""
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        tools = await session.list_tools()

    by_name = {t.name: t for t in tools.tools}
    meta = by_name["get_savings_card"].meta or {}
    assert meta["ui"]["resourceUri"] == WIDGET_URI
    assert meta["openai/outputTemplate"] == WIDGET_URI
    assert len(meta["openai/toolInvocation/invoking"]) <= 64
    assert len(meta["openai/toolInvocation/invoked"]) <= 64

    # The widget calls this one from inside itself, so the app must be allowed to.
    email_meta = by_name["email_savings_card"].meta or {}
    assert "app" in email_meta["ui"]["visibility"]
    assert email_meta["openai/widgetAccessible"] is True


async def test_widget_resource_is_listed_with_the_app_mime_type() -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        resources = await session.list_resources()

    by_uri = {str(r.uri): r for r in resources.resources}
    assert WIDGET_URI in by_uri
    widget = by_uri[WIDGET_URI]
    assert widget.mimeType == WIDGET_MIME_TYPE == "text/html;profile=mcp-app"
    assert (widget.meta or {})["ui"]["prefersBorder"] is True
    assert (widget.meta or {})["openai/widgetDescription"]


async def test_widget_html_is_self_contained_and_speaks_both_bridges() -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        result = await session.read_resource(WIDGET_URI)

    html = result.contents[0].text
    assert html == load_widget_html()

    # Both host bridges, and the one tool the component calls from inside itself.
    for needle in (
        "window.openai",
        "ui/initialize",
        "ui/notifications/tool-result",
        "ui/notifications/size-changed",
        "email_savings_card",
    ):
        assert needle in html, needle

    # The host serves this under `default-src 'none'`: anything fetched from
    # outside would silently not load, so nothing may be.
    assert not re.search(r"<(script|link|img|iframe|source|use)\b[^>]*\b(src|href)\s*=", html, re.I)
    assert "https://" not in html and "http://" not in html
    assert "@import" not in html

    # The handshake announces the package version; keep them from drifting.
    assert f'APP_VERSION = "{__version__}"' in html


def test_widget_file_ships_inside_the_wheel(tmp_path: Path) -> None:
    """`packages = ["src/finerx_mcp"]` takes every file under the package dir —
    but a widget that is not in the wheel is a resource that 404s in production."""
    if shutil.which("uv") is None:  # pragma: no cover - depends on the machine
        pytest.skip("uv is not installed")
    built = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=PACKAGE_ROOT,
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stderr
    wheels = list(tmp_path.glob("*.whl"))
    assert wheels, "uv build produced no wheel"
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
    assert "finerx_mcp/widget/savings_card.html" in names


# --- the host's own locale ---------------------------------------------------


class _FakeMeta:
    def __init__(self, extra: dict[str, Any] | None) -> None:
        self.model_extra = extra


class _FakeRequestContext:
    def __init__(self, meta: Any) -> None:
        self.meta = meta


class _FakeContext:
    def __init__(self, meta: Any) -> None:
        self.request_context = _FakeRequestContext(meta)


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({"openai/locale": "es-419"}, "es"),
        ({"openai/locale": "ES"}, "es"),
        ({"openai/locale": "  "}, None),
        ({"progressToken": "x"}, None),
        (None, None),
    ],
)
def test_host_locale_reads_the_request_meta(extra: dict | None, expected: str | None) -> None:
    assert server._host_locale(_FakeContext(_FakeMeta(extra))) == expected


def test_host_locale_survives_a_context_without_a_request() -> None:
    """Called outside a request (a direct call, a test) it must answer None, not
    raise — the tool then falls back to English."""
    assert server._host_locale(None) is None
    assert server._host_locale(_FakeContext(None)) is None


async def test_savings_card_uses_the_hosts_locale_when_the_model_gives_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ChatGPT sends `openai/locale` in the request `_meta`; the model almost
    never passes `locale` itself, so this is what answers a Spanish reader."""
    calls = stub_get(monkeypatch, CARD_PAYLOAD)

    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        await session.call_tool("get_savings_card", {}, meta={"openai/locale": "es-419"})

    assert calls[0][1]["locale"] == "es"


async def test_savings_card_sends_no_image_block_to_chatgpt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ChatGPT renders the card through the widget; an image block in the tool
    result only burns the Free plan's image quota (it paused a live chat)."""
    stub_get(monkeypatch, CARD_PAYLOAD)
    monkeypatch.setattr(server, "_card_image_bytes", lambda url: b"\x89PNG")

    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        chatgpt = await session.call_tool(
            "get_savings_card", {}, meta={"openai/locale": "en-US", "openai/userAgent": "ChatGPT"}
        )
        other = await session.call_tool("get_savings_card", {})

    assert [c.type for c in chatgpt.content] == ["text"]
    assert chatgpt.structuredContent and chatgpt.structuredContent["card"]["bin"]
    assert [c.type for c in other.content] == ["text", "image"]


async def test_savings_card_locale_argument_wins_over_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_get(monkeypatch, CARD_PAYLOAD)

    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        await session.call_tool(
            "get_savings_card", {"locale": "pt"}, meta={"openai/locale": "es-419"}
        )

    assert calls[0][1]["locale"] == "pt"


# --- email_savings_card -----------------------------------------------------


async def test_email_refuses_without_consent_and_never_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[Any] = []
    monkeypatch.setattr(FinerxClient, "post", lambda self, path, json=None: posted.append(path))

    out = server.email_savings_card(email="jane@example.com")

    assert out == {
        "sent": False,
        "error": "consent required: ask the person to confirm they want the card emailed to this address",
    }
    assert posted == []


async def test_email_masks_the_address_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, dict | None]] = []

    def _post(self: FinerxClient, path: str, json: dict | None = None) -> dict:
        sent.append((path, json))
        return {"sent": True, "meta": {"disclaimer": "Prices via FineRx. Not medical advice."}}

    monkeypatch.setattr(FinerxClient, "post", _post)

    out = server.email_savings_card(email="jane@example.com", consent=True)

    assert sent == [("/card/email", {"email": "jane@example.com", "locale": "en", "consent": True})]
    assert out["sent"] is True
    assert out["to"] == "j***@example.com"
    assert "jane@example.com" not in str(out)
    assert out["disclaimer"]


@pytest.mark.parametrize(
    ("status", "fragment"),
    [
        (429, "too many card emails"),
        (503, "email delivery is not available right now"),
        (502, "the email provider failed"),
        (422, "that address was not accepted"),
    ],
)
async def test_email_maps_api_errors(monkeypatch: pytest.MonkeyPatch, status: int, fragment: str) -> None:
    def _post(self: FinerxClient, path: str, json: dict | None = None) -> dict:
        raise FinerxApiError(status, "raw server detail", "30" if status == 429 else None)

    monkeypatch.setattr(FinerxClient, "post", _post)

    out = server.email_savings_card(email="jane@example.com", consent=True)

    assert out["sent"] is False
    assert fragment in out["error"]
    assert out["status"] == status
    if status == 429:
        assert out["retryAfter"] == "30"


# --- savingsCard passthrough ------------------------------------------------


async def test_compare_prices_passes_savings_card_through(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = stub_get(monkeypatch, COMPARE_PAYLOAD)

    out = server.compare_prices(ndc="00093505698", quantity=30, locale="es", channel="claude")

    assert calls[0][1]["locale"] == "es"
    assert calls[0][1]["channel"] == "claude"
    assert out["savingsCard"] == SAVINGS_CARD_BLOCK
    assert out["offers"][0]["observedAt"] == "2026-09-05"


async def test_get_drug_passes_savings_card_through(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_get(monkeypatch, DRUG_PAYLOAD)

    out = server.get_drug(slug="atorvastatin")

    assert out["savingsCard"]["card"]["pcn"] == "DRX"
    assert out["stats"]["observedAt"] == "2026-09-05"


async def test_get_drug_without_a_card_omits_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_get(monkeypatch, {k: v for k, v in DRUG_PAYLOAD.items() if k != "savingsCard"})

    assert "savingsCard" not in server.get_drug(slug="atorvastatin")


# --- prescription options ---------------------------------------------------


async def test_prescription_options_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = stub_get(monkeypatch, PRESCRIPTION_PAYLOAD)

    out = server.get_prescription_options(locale="en", drug="atorvastatin")

    assert calls[0][0] == "/prescription-options"
    assert out["noPrescription"]["options"][0]["disclosure"]
    assert out["medicaidNote"]
    assert out["disclaimer"]


# --- resources --------------------------------------------------------------


async def test_card_resource_renders_the_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_get(monkeypatch, CARD_PAYLOAD)

    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        result = await session.read_resource("finerx://card")

    text = result.contents[0].text
    assert "RxBIN 610219" in text
    assert "RxPCN DRX" in text
    assert "RxGRP MYCARD3993" in text
    assert "1. Show it at the pharmacy." in text
    assert "This card is not insurance." in text


async def test_how_it_works_resource_is_static() -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        result = await session.read_resource("finerx://how-it-works")

    text = result.contents[0].text
    assert "not insurance" in text
    assert "Prices via FineRx" in text


# --- foreign brand -> US equivalent -----------------------------------------


def _stub_analogs(
    monkeypatch: pytest.MonkeyPatch,
    search: dict[str, Any],
    entry: dict[str, Any] | None = None,
) -> list[tuple[str, dict | None]]:
    """Answer /analogs/search then /analogs/{slug} — the tool's two hops."""
    calls: list[tuple[str, dict | None]] = []

    def _get(self: FinerxClient, path: str, params: dict | None = None) -> dict:
        calls.append((path, params))
        if path == "/analogs/search":
            return search
        assert entry is not None, f"unexpected entry fetch: {path}"
        return entry

    monkeypatch.setattr(FinerxClient, "get", _get)
    return calls


async def test_find_us_equivalent_returns_the_vetted_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guidance sentence is the product: it must arrive from the API intact,
    not be re-composed here."""
    search = {**ANALOG_SEARCH_PAYLOAD, "results": [
        {
            "brand": "Nurofen",
            "brandSlug": "nurofen",
            "matchedName": "Нурофен",
            "countries": ["RU", "UA"],
            "usClass": "same_inn",
            "inn": "ibuprofen",
            "usGeneric": "ibuprofen",
            "pageUrl": "https://www.finerxfinder.com/en/analog/nurofen",
        }
    ]}
    calls = _stub_analogs(monkeypatch, search, ANALOG_ENTRY_PAYLOAD)

    out = server.find_us_equivalent(brand="Нурофен")

    assert calls[0][0] == "/analogs/search"
    assert calls[0][1]["q"] == "Нурофен"
    assert calls[1][0] == "/analogs/nurofen"
    assert out["found"] is True
    assert out["guidance"] == ANALOG_ENTRY_PAYLOAD["guidance"]
    assert out["guidanceDisclaimer"].startswith("Same active ingredient does not mean")
    assert out["usClass"] == "same_inn"
    assert out["brandScript"] == "Нурофен"
    assert out["rxStatus"] == "over the counter"
    assert out["usBrands"] == ["Advil", "Motrin"]
    # A price never travels without the date it was seen.
    assert out["usDrug"]["fromPrice"] == 4.0
    assert out["usDrug"]["observedAt"] == "2026-09-05"
    assert out["savingsCard"] == SAVINGS_CARD_BLOCK
    assert out["pageUrl"].endswith("/analog/nurofen")
    assert out["otherMatches"] == []
    assert out["disclaimer"]


async def test_find_us_equivalent_prefers_the_asked_for_country(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same brand name, two countries, two entries — the country decides which."""
    entry = {**ANALOG_ENTRY_PAYLOAD, "brand": "No-Spa", "brandSlug": "no-spa-poland"}
    calls = _stub_analogs(monkeypatch, ANALOG_SEARCH_PAYLOAD, entry)

    out = server.find_us_equivalent(brand="No-Spa", country="poland")

    assert calls[1][0] == "/analogs/no-spa-poland"
    # The one it did not pick is offered, not hidden.
    assert out["otherMatches"] == [
        {"brand": "No-Spa", "countries": ["RU", "UA", "BY", "KZ"], "brandSlug": "no-spa"}
    ]


async def test_find_us_equivalent_ignores_an_unknown_country(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrecognised country falls back to the top match rather than guessing —
    and "us" must never substring-match "Russia"."""
    calls = _stub_analogs(monkeypatch, ANALOG_SEARCH_PAYLOAD, ANALOG_ENTRY_PAYLOAD)

    server.find_us_equivalent(brand="No-Spa", country="us")

    assert calls[1][0] == "/analogs/no-spa"


async def test_find_us_equivalent_reports_no_match_without_inventing_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_get(monkeypatch, {"query": "x", "count": 0, "results": [],
                           "meta": {"disclaimer": "Prices via FineRx. Not medical advice."}})

    out = server.find_us_equivalent(brand="zzzqqq")

    assert out["found"] is False
    assert out["hint"] == "no foreign brand matched; try the active ingredient with search_drugs"
    assert out["disclaimer"]
    assert "guidance" not in out


async def test_find_us_equivalent_uses_the_hosts_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """The model almost never passes a locale; the host's own is the fallback that
    answers a Spanish reader in Spanish."""
    calls = _stub_analogs(monkeypatch, ANALOG_SEARCH_PAYLOAD, ANALOG_ENTRY_PAYLOAD)

    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        result = await session.call_tool(
            "find_us_equivalent", {"brand": "No-Spa"}, meta={"openai/locale": "es-419"}
        )

    assert result.isError is False
    assert calls[0][1]["locale"] == "es"
    assert calls[1][1] == {"locale": "es", "channel": "mcp"}
    # The localized note wins over the English source note when we have one.
    assert result.structuredContent["notes"] == ANALOG_ENTRY_PAYLOAD["notesLocalized"]


async def test_find_us_equivalent_relays_an_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(self: FinerxClient, path: str, params: dict | None = None) -> dict:
        raise FinerxApiError(503, "upstream unavailable", None)

    monkeypatch.setattr(FinerxClient, "get", _boom)

    assert server.find_us_equivalent(brand="No-Spa") == {
        "error": "upstream unavailable",
        "status": 503,
    }


async def test_foreign_brands_for_drug_passes_the_corpus_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_get(monkeypatch, FOR_DRUG_PAYLOAD)

    out = server.foreign_brands_for_drug(slug="ibuprofen")

    assert calls[0][0] == "/analogs/for-drug/ibuprofen"
    assert out["drugSlug"] == "ibuprofen"
    assert out["count"] == 1
    assert out["brands"] == [
        {
            "brand": "Nurofen",
            "brandScript": "Нурофен",
            "countries": ["RU", "UA"],
            "inn": "ibuprofen",
            "usClass": "same_inn",
        }
    ]
    assert out["disclaimer"]


async def test_search_drugs_carries_the_foreign_brands(monkeypatch: pytest.MonkeyPatch) -> None:
    """A client that only calls search still learns the analog layer exists."""
    stub_get(monkeypatch, {
        "query": "нурофен",
        "count": 0,
        "results": [],
        "foreignBrands": [
            {
                "brand": "Nurofen",
                "brandSlug": "nurofen",
                "brandScript": "Нурофен",
                "matchedName": "Нурофен",
                "countries": ["RU", "UA"],
                "usClass": "same_inn",
                "inn": "ibuprofen",
                "usGeneric": "ibuprofen",
                "pageUrl": "https://www.finerxfinder.com/en/analog/nurofen",
            }
        ],
        "meta": {"disclaimer": "Prices via FineRx. Not medical advice."},
    })

    out = server.search_drugs(query="нурофен")

    assert out["results"] == []
    assert out["foreignBrands"] == [
        {
            "brand": "Nurofen",
            "brandSlug": "nurofen",
            "countries": ["RU", "UA"],
            "inn": "ibuprofen",
            "usGeneric": "ibuprofen",
        }
    ]


async def test_search_drugs_without_foreign_brands_answers_an_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_get(monkeypatch, {"query": "atorvastatin", "count": 0, "results": [],
                           "meta": {"disclaimer": "Prices via FineRx. Not medical advice."}})

    assert server.search_drugs(query="atorvastatin")["foreignBrands"] == []


async def test_us_equivalent_prompt_asks_for_the_sentence_as_written() -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        got = await session.get_prompt("us_equivalent", {"brand": "No-Spa", "country": "Ukraine"})

    text = got.messages[0].content.text
    assert "No-Spa" in text
    assert "Ukraine" in text
    assert "guidance sentence exactly as FineRx wrote it" in text
    assert "Do not tell me what to take instead." in text
