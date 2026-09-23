"""Shared fixtures: the public API is mocked at the HTTP layer with respx.

Payloads live in ``fixtures/api/*.json`` and follow the A1 report (the real
response shapes of API 1.4.0: ``/prices/near``, ``/drugs/{slug}/options``,
``/drugs/{slug}/card-prices``, ``/chains``, ``/card`` …). Nothing here touches
the network: an unrouted request fails the test.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

# Before finerx_mcp is imported: hosts reads the salt at import time.
os.environ.setdefault("FINERX_MCP_SUBJECT_SALT", "test-salt")

import pytest  # noqa: E402
import respx  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402
from mcp.types import CallToolResult, TextContent  # noqa: E402

from finerx_mcp import card_law, server  # noqa: E402
from finerx_mcp.limits import LIMITER  # noqa: E402

BASE = "http://api.test/api/public/v1"
FIXTURES = Path(__file__).parent / "fixtures" / "api"


def fx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def url(pattern: str) -> str:
    """An anchored regex for a path under the API base (query string allowed)."""
    return rf"^{re.escape(BASE)}{pattern}(\?.*)?$"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINERX_API_KEY", "frx_live_test")
    monkeypatch.setenv("FINERX_API_BASE", BASE)
    monkeypatch.delenv("FINERX_MCP_COMPETITOR_PRICES", raising=False)
    server._client = None
    server._options_cache.clear()
    server._image_cache.clear()
    card_law.reset_cache()
    LIMITER.reset()

    async def _no_image(url: str) -> bytes | None:
        return None

    monkeypatch.setattr(server, "_card_image_bytes", _no_image)


def add_routes(router: respx.MockRouter) -> dict[str, respx.Route]:
    """Every endpoint the MCP calls, answered from the fixtures. Order matters:
    the specific paths come before the ``/{slug}`` catch-alls."""
    r: dict[str, respx.Route] = {}
    r["card_email"] = router.post(url__regex=url("/card/email")).respond(202)
    r["card"] = router.get(url__regex=url("/card")).respond(json=fx("card"))
    r["search"] = router.get(url__regex=url("/drugs/search")).respond(json=fx("search"))
    r["options"] = router.get(url__regex=url("/drugs/[^/]+/options")).respond(json=fx("options"))
    r["card_prices"] = router.get(url__regex=url("/drugs/[^/]+/card-prices")).respond(json=fx("card_prices"))
    r["near"] = router.post(url__regex=url("/prices/near")).respond(json=fx("prices_near"))
    r["compare"] = router.get(url__regex=url("/prices/compare")).respond(json=fx("compare_ndc"))
    r["nearby"] = router.get(url__regex=url("/pharmacies/nearby")).respond(json=fx("nearby"))
    r["chains"] = router.get(url__regex=url("/chains")).respond(json=fx("chains"))
    r["meta"] = router.get(url__regex=url("/meta")).respond(json=fx("meta"))
    r["analog_search"] = router.get(url__regex=url("/analogs/search")).respond(json=fx("analog_search"))
    r["for_drug"] = router.get(url__regex=url("/analogs/for-drug/[^/]+")).respond(json=fx("for_drug"))
    r["analog"] = router.get(url__regex=url("/analogs/[^/]+")).respond(json=fx("analog_entry"))
    r["rx"] = router.get(url__regex=url("/prescription-options")).respond(json=fx("prescription_options"))
    return r


@pytest.fixture
def api():
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        routes = add_routes(router)
        yield routes


async def call(name: str, args: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> CallToolResult:
    """Through a REAL in-memory MCP session, so what we assert is what a host gets."""
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        return await session.call_tool(name, args or {}, meta=meta)


def text_of(result: CallToolResult) -> str:
    return "\n".join(b.text for b in result.content if isinstance(b, TextContent))


def body_of(route: respx.Route, i: int = -1) -> dict[str, Any]:
    return json.loads(route.calls[i].request.content)


def params_of(route: respx.Route, i: int = -1) -> dict[str, str]:
    return dict(route.calls[i].request.url.params)
