"""What a host (and the ChatGPT review) reads off tools/list and the resources."""
from __future__ import annotations

import re

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from finerx_mcp import server
from finerx_mcp.card_law import BANNED_RE
from finerx_mcp.widget import APP_URI, WIDGET_MIME_TYPE, WIDGET_URI, load_app_html

UI_TOOLS = {"compare_prices", "find_nearby_pharmacies", "get_savings_card"}
APP_ONLY = {"ui_prices", "ui_nearby"}
# Other price programs / services: a tool description must never name, rank or
# disparage one (review rule), nor name the card's own processor.
COMPETITORS = re.compile(
    r"goodrx|singlecare|buzzrx|wellrx|rxsaver|optum|hippo|savehealth|cost ?plus|mark cuban|"
    r"blink|scriptsave|rxgo|lowermyrx|amazon",
    re.IGNORECASE,
)


async def _tools() -> dict:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        return {t.name: t for t in (await session.list_tools()).tools}


async def _resources() -> dict:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        return {str(r.uri): r for r in (await session.list_resources()).resources}


async def test_all_hints_are_explicit_and_read_only_tools_are_closed_world() -> None:
    tools = await _tools()
    for name, tool in tools.items():
        a = tool.annotations
        assert None not in (a.readOnlyHint, a.destructiveHint, a.idempotentHint, a.openWorldHint), name
        if name == "email_savings_card":
            continue
        assert (a.readOnlyHint, a.destructiveHint, a.idempotentHint, a.openWorldHint) == (True, False, True, False), name


async def test_email_is_destructive_and_open_world() -> None:
    a = (await _tools())["email_savings_card"].annotations
    assert (a.readOnlyHint, a.destructiveHint, a.idempotentHint, a.openWorldHint) == (False, True, False, True)


async def test_ui_tools_point_at_the_v2_bundle() -> None:
    tools = await _tools()
    for name in UI_TOOLS:
        meta = tools[name].meta or {}
        assert meta["ui"]["resourceUri"] == meta["openai/outputTemplate"] == APP_URI, name
        assert 0 < len(meta["openai/toolInvocation/invoking"]) <= 64
        assert 0 < len(meta["openai/toolInvocation/invoked"]) <= 64


async def test_app_only_tools_are_hidden_from_the_model_and_carry_no_template() -> None:
    tools = await _tools()
    for name in APP_ONLY:
        meta = tools[name].meta or {}
        assert meta["ui"]["visibility"] == ["app"], name
        assert "resourceUri" not in meta["ui"]
        assert "openai/outputTemplate" not in meta


async def test_tools_without_ui_carry_no_template() -> None:
    for name, tool in (await _tools()).items():
        if name in UI_TOOLS:
            continue
        meta = tool.meta or {}
        assert "openai/outputTemplate" not in meta, name
        assert "resourceUri" not in (meta.get("ui") or {}), name


async def test_the_widget_may_call_email() -> None:
    meta = (await _tools())["email_savings_card"].meta or {}
    assert "app" in meta["ui"]["visibility"] and "model" in meta["ui"]["visibility"]


async def test_no_tool_asks_for_raw_location_fields() -> None:
    """Review rule: no lat/lng/city/address in an input schema (a ZIP is fine)."""
    for name, tool in (await _tools()).items():
        props = set((tool.inputSchema or {}).get("properties", {}))
        assert not props & {"lat", "lon", "lng", "latitude", "longitude", "city", "address", "where"}, name


async def test_descriptions_name_no_competitor_and_make_no_superlative() -> None:
    for name, tool in (await _tools()).items():
        text = f"{tool.title or ''} {tool.description or ''} {(tool.annotations.title or '')}"
        assert not COMPETITORS.search(text), (name, COMPETITORS.search(text))
        assert not BANNED_RE.search(text), (name, BANNED_RE.search(text))


@pytest.mark.parametrize("uri", [APP_URI, WIDGET_URI])
async def test_bundle_resource_meta(uri: str) -> None:
    res = (await _resources())[uri]
    assert res.mimeType == WIDGET_MIME_TYPE == "text/html;profile=mcp-app"
    meta = res.meta or {}
    assert meta["ui"]["domain"] == meta["openai/widgetDomain"] == "https://www.finerxfinder.com"
    assert meta["ui"]["csp"] == {"connectDomains": [], "resourceDomains": []}
    assert meta["openai/widgetCSP"] == {"connect_domains": [], "resource_domains": []}
    assert re.fullmatch(r"[0-9a-f]{8}", meta["finerx/build"])


@pytest.mark.parametrize("uri", [APP_URI, WIDGET_URI])
async def test_both_uris_serve_the_v2_bundle_with_its_meta(uri: str) -> None:
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
        got = await session.read_resource(uri)
    content = got.contents[0]
    assert content.text == load_app_html()
    assert content.mimeType == WIDGET_MIME_TYPE
    assert (content.meta or {})["ui"]["domain"] == "https://www.finerxfinder.com"


def test_bundle_is_self_contained() -> None:
    """Hosts serve it under `default-src 'none'`: nothing may load from outside."""
    html = load_app_html()
    assert not re.search(r"<(script|link|img|iframe|source)\b[^>]*\b(src|href)\s*=", html, re.I)
    assert "@import" not in html
    assert not re.search(r"url\(\s*['\"]?https?://", html)
    assert "ui/initialize" in html and "ui_prices" in html and "email_savings_card" in html
