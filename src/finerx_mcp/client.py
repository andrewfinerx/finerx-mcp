"""Async HTTP client for the FineRx public REST API.

Reads configuration from the environment:
  FINERX_API_KEY   (required)  the developer key, format ``frx_live_...``
  FINERX_API_BASE  (optional)  base URL of the public API; defaults to the
                               production surface.

The client sends the key as ``Authorization: Bearer ...`` and raises a compact,
LLM-friendly ``FinerxApiError`` on non-2xx responses.

**Async since 2.0.** 1.x called the synchronous ``httpx.get`` from inside the
FastMCP event loop, so one slow answer (the gabapentin package wall, ~3 s) froze
every other caller of the process. Now every call goes through ONE pooled
``httpx.AsyncClient`` (8 s total / 2 s connect, at most 20 connections) and an
``asyncio.Semaphore(16)`` on outbound requests; when the semaphore stays full for
``_BUSY_WAIT_S`` the call fails fast with a 503 "busy" instead of queueing
forever.

Privacy: the ``httpx``/``httpcore`` loggers are capped at WARNING here. At INFO
httpx logs every request line — ``GET …/pharmacies/nearby?zip=…&lat=…`` — and a
ZIP or a coordinate must never reach a log (contract, privacy rule).

**Paths carry slugs only.** A model argument is free text, and free text in a
URL path can walk to another endpoint (``../card/email``) or smuggle a query.
So a path is built with ``slug_path("/drugs/{}/options", slug)``: every segment
must match ``SLUG_RE`` and is percent-encoded, and ``_send`` refuses any path
outside ``[A-Za-z0-9/_%-]`` or with an empty segment. Free text goes only into a
query string (``/drugs/search?q=``) or a POST body (``/prices/near``).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from urllib.parse import quote

import httpx

DEFAULT_API_BASE = "https://finerxfinder.com/api/public/v1"

try:
    _VERSION = version("finerx-mcp")
except PackageNotFoundError:  # editable/source checkout without install metadata
    _VERSION = "0"
# Identifies MCP traffic to the FineRx API's usage tracker (site vs developer vs
# MCP split) — the server counts any request whose UA starts with "finerx-mcp/".
USER_AGENT = f"finerx-mcp/{_VERSION}"

TIMEOUT = httpx.Timeout(8.0, connect=2.0)
LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=20)
MAX_IN_FLIGHT = 16
_BUSY_WAIT_S = 5.0

# What may stand in a path segment: a catalog slug (drugs, analog brands).
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,120}$")
# What a whole path may look like once built (defence in depth for _send).
_PATH_RE = re.compile(r"^(/[A-Za-z0-9_%-]+)+$")

for _name in ("httpx", "httpcore"):
    _lg = logging.getLogger(_name)
    if _lg.level < logging.WARNING:
        _lg.setLevel(logging.WARNING)


class FinerxApiError(RuntimeError):
    """Raised on a non-2xx API response, with the status and server detail.

    ``retry_after`` carries the server's ``Retry-After`` header on a 429 so a tool
    can tell the model how long to wait instead of guessing. ``payload`` is the
    JSON error body when there was one — ``POST /prices/near`` answers an unknown
    drug with ``{"error": "drug_not_found", "suggestions": [...]}``, and those
    suggestions are the useful part of the answer.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        retry_after: str | None = None,
        payload: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after
        self.payload = payload or {}
        super().__init__(f"FineRx API {status_code}: {detail}")


def valid_slug(value: Any) -> str | None:
    """``value`` when it is a catalog slug (``SLUG_RE``), else None."""
    return value if isinstance(value, str) and SLUG_RE.match(value) else None


def slug_path(template: str, *slugs: Any) -> str:
    """``template`` with each ``{}`` replaced by a validated, percent-encoded
    slug. Raises ``FinerxApiError(400, "invalid slug")`` — before any request —
    when a value is not a slug (free text, ``..``, a query, a space)."""
    parts: list[str] = []
    for value in slugs:
        slug = valid_slug(value)
        if slug is None:
            raise FinerxApiError(400, "invalid slug")
        parts.append(quote(slug, safe=""))
    return template.format(*parts)


class FinerxClient:
    """One per process. The pooled AsyncClient and the semaphore belong to the
    event loop they were first used on; a call from another loop (tests run one
    loop per test) gets a fresh pair instead of a "bound to a different event
    loop" error."""

    def __init__(self, api_key: str | None = None, api_base: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("FINERX_API_KEY", "")
        self.api_base = (api_base or os.environ.get("FINERX_API_BASE") or DEFAULT_API_BASE).rstrip("/")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._http: httpx.AsyncClient | None = None
        self._sem: asyncio.Semaphore | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }

    def _require_key(self) -> None:
        if not self.api_key:
            raise FinerxApiError(0, "FINERX_API_KEY is not set. Request a key at finerxfinder.com/developers.")

    def _pool(self) -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
        loop = asyncio.get_running_loop()
        if self._http is None or self._sem is None or self._loop is not loop:
            self._loop = loop
            self._http = httpx.AsyncClient(timeout=TIMEOUT, limits=LIMITS, headers=self._headers())
            self._sem = asyncio.Semaphore(MAX_IN_FLIGHT)
        return self._http, self._sem

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
        self._http = None
        self._sem = None
        self._loop = None

    @staticmethod
    def _unwrap(resp: httpx.Response) -> dict:
        """Raise on 4xx/5xx with the server's own ``detail``, else return the body."""
        if resp.status_code >= 400:
            detail: Any = resp.text
            payload: dict | None = None
            try:
                body = resp.json()
                if isinstance(body, dict):
                    payload = body
                    detail = body.get("detail") or body.get("error") or detail
            except Exception:
                pass
            raise FinerxApiError(resp.status_code, str(detail), resp.headers.get("Retry-After"), payload)
        # 202/204 bodies may be empty; a tool should not blow up on that.
        if not resp.content:
            return {}
        try:
            body = resp.json()
        except Exception:
            return {}
        return body if isinstance(body, dict) else {}

    async def _send(self, method: str, path: str, **kwargs: Any) -> dict:
        if not _PATH_RE.match(path):
            raise FinerxApiError(400, "invalid path")
        self._require_key()
        http, sem = self._pool()
        try:
            await asyncio.wait_for(sem.acquire(), timeout=_BUSY_WAIT_S)
        except asyncio.TimeoutError as exc:
            raise FinerxApiError(503, "busy", str(int(_BUSY_WAIT_S))) from exc
        try:
            resp = await http.request(method, f"{self.api_base}{path}", **kwargs)
        except httpx.HTTPError as exc:  # network/timeout — the type only, never the URL
            raise FinerxApiError(0, f"request failed: {type(exc).__name__}") from exc
        finally:
            sem.release()
        return self._unwrap(resp)

    async def get(self, path: str, params: dict | None = None) -> dict:
        # Drop None-valued params so we never send ?zip=&lat= noise.
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        return await self._send("GET", path, params=clean)

    async def post(self, path: str, json: dict | None = None, headers: dict[str, str] | None = None) -> dict:
        """POST a JSON body. Same auth, same error shape as ``get``. ``headers``
        adds request headers (``X-FineRx-Subject`` on the card email)."""
        body = {k: v for k, v in (json or {}).items() if v is not None}
        return await self._send(
            "POST", path, json=body, headers={"Content-Type": "application/json", **(headers or {})}
        )
