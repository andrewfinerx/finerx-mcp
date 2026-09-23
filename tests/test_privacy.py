"""No ZIP, coordinate, subject or email address reaches a log line — and a
coordinate reaches the API only rounded to 0.01°."""
from __future__ import annotations

import json
import logging

import pytest
from conftest import body_of, call, fx, params_of, text_of

from finerx_mcp import hosts

LOCATION = {
    "city": "Miami",
    "region": "Florida",
    "country": "US",
    "timezone": "America/New_York",
    "latitude": 25.774312,
    "longitude": -80.193654,
}
SUBJECT = "v1/sub-7f3a9c-secret-person"
CHATGPT = {"openai/userLocation": LOCATION, "openai/subject": SUBJECT, "openai/locale": "en-US"}
SECRETS = ("33101", "25.77", "-80.19", "25.774312", "80.193654", SUBJECT, "sub-7f3a9c", "jane@example.com")


def _assert_clean(caplog: pytest.LogCaptureFixture) -> None:
    logged = caplog.text + "\n".join(str(r.args) for r in caplog.records)
    for secret in (*SECRETS, hosts.subject_key(_Ctx(CHATGPT)) or "never"):
        assert secret not in logged, secret


class _Meta:
    def __init__(self, extra: dict) -> None:
        self.model_extra = extra


class _Req:
    def __init__(self, extra: dict) -> None:
        self.meta = _Meta(extra)


class _Ctx:
    def __init__(self, extra: dict) -> None:
        self.request_context = _Req(extra)


@pytest.mark.parametrize(
    "name,args",
    [
        ("compare_prices", {"drug": "atorvastatin", "zip": "33101"}),
        ("compare_prices", {"drug": "atorvastatin"}),
        ("ui_prices", {"slug": "atorvastatin-calcium", "zip": "33101"}),
        ("find_nearby_pharmacies", {"zip": "33101"}),
        ("find_nearby_pharmacies", {}),
        ("ui_nearby", {"zip": "33101"}),
        ("email_savings_card", {"email": "jane@example.com", "consent": True}),
    ],
)
async def test_logs_carry_no_place_subject_or_address(api, caplog, name: str, args: dict) -> None:
    caplog.set_level(logging.DEBUG)
    await call(name, args, meta=CHATGPT)
    _assert_clean(caplog)
    lines = [r.getMessage() for r in caplog.records if r.name == "finerx_mcp"]
    assert any(line.startswith(f"tool={name} status=ok ms=") and line.endswith("host=chatgpt") for line in lines), lines


async def test_errors_are_logged_without_their_text(api, caplog, monkeypatch) -> None:
    from finerx_mcp import server

    def _explode(*a, **k):
        raise ValueError("zip=33101 lat=25.774312")

    monkeypatch.setattr(server.views, "prices_text", _explode)
    caplog.set_level(logging.DEBUG)
    await call("compare_prices", {"drug": "atorvastatin", "zip": "33101"}, meta=CHATGPT)
    _assert_clean(caplog)
    assert "failed with ValueError" in caplog.text


async def test_user_location_is_rounded_before_it_leaves(api) -> None:
    result = await call("compare_prices", {"drug": "atorvastatin"}, meta=CHATGPT)
    body = body_of(api["near"])
    assert body["lat"] == 25.77 and body["lon"] == -80.19
    assert "zip" not in body
    blob = json.dumps(result.structuredContent) + text_of(result)
    assert "25.774312" not in blob and SUBJECT not in blob


async def test_a_zip_wins_over_the_location_hint(api) -> None:
    await call("compare_prices", {"drug": "atorvastatin", "zip": "10001-1234"}, meta=CHATGPT)
    body = body_of(api["near"])
    assert body["zip"] == "10001"
    assert "lat" not in body and "lon" not in body


async def test_a_location_outside_the_us_is_not_used(api) -> None:
    meta = {**CHATGPT, "openai/userLocation": {**LOCATION, "country": "DE"}}
    api["near"].respond(json=fx("prices_near_needs_zip"))
    await call("compare_prices", {"drug": "atorvastatin"}, meta=meta)
    body = body_of(api["near"])
    assert "lat" not in body and "zip" not in body


async def test_nearby_by_location_sends_only_rounded_coordinates(api) -> None:
    await call("find_nearby_pharmacies", {}, meta=CHATGPT)
    params = params_of(api["nearby"])
    assert params["lat"] == "25.77" and params["lon"] == "-80.19"


async def test_no_place_means_no_nearby_call(api) -> None:
    result = await call("find_nearby_pharmacies", {})
    assert not api["nearby"].called
    assert result.structuredContent["data"]["origin"]["precision"] == "none"
    assert "ZIP" in text_of(result)


def test_subject_key_is_a_keyed_hash() -> None:
    key = hosts.subject_key(_Ctx({"openai/subject": SUBJECT}))
    assert key and SUBJECT not in key and len(key) == 32
    assert key == hosts.subject_key(_Ctx({"openai/subject": SUBJECT}))
    assert hosts.subject_key(_Ctx({})) is None


def test_location_parsing_is_strict() -> None:
    assert hosts.user_location(_Ctx({"openai/userLocation": {"latitude": "nan", "longitude": 1}})) is None
    assert hosts.user_location(_Ctx({"openai/userLocation": {"latitude": 95, "longitude": 1}})) is None
    assert hosts.user_location(_Ctx({"openai/userLocation": "Miami"})) is None
    loc = hosts.user_location(_Ctx({"openai/userLocation": {"latitude": "40.7484", "longitude": "-73.9857"}}))
    assert (loc.lat, loc.lon) == (40.75, -73.99)
