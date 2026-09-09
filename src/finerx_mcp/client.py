"""HTTP client for the FineRx public REST API.

Reads configuration from the environment:
  FINERX_API_KEY   (required)  the developer key, format ``frx_live_...``
  FINERX_API_BASE  (optional)  base URL of the public API; defaults to the
                               production surface.

The client sends the key as ``Authorization: Bearer ...`` and raises a compact,
LLM-friendly ``FinerxApiError`` on non-2xx responses.

``get`` covers the read-only surface; ``post`` exists for the one write action the
public API offers (``POST /card/email``). Both share the same headers and the same
error mapping, so an MCP tool only ever has to catch ``FinerxApiError``.
"""
from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version

import httpx

DEFAULT_API_BASE = "https://finerxfinder.com/api/public/v1"

try:
    _VERSION = version("finerx-mcp")
except PackageNotFoundError:  # editable/source checkout without install metadata
    _VERSION = "0"
# Identifies MCP traffic to the FineRx API's usage tracker (site vs developer vs
# MCP split) — the server counts any request whose UA starts with "finerx-mcp/".
USER_AGENT = f"finerx-mcp/{_VERSION}"


class FinerxApiError(RuntimeError):
    """Raised on a non-2xx API response, with the status and server detail.

    ``retry_after`` carries the server's ``Retry-After`` header on a 429 so a tool
    can tell the model how long to wait instead of guessing.
    """

    def __init__(self, status_code: int, detail: str, retry_after: str | None = None) -> None:
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after
        super().__init__(f"FineRx API {status_code}: {detail}")


class FinerxClient:
    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("FINERX_API_KEY", "")
        self.api_base = (api_base or os.environ.get("FINERX_API_BASE") or DEFAULT_API_BASE).rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }

    def _require_key(self) -> None:
        if not self.api_key:
            raise FinerxApiError(0, "FINERX_API_KEY is not set. Request a key at finerxfinder.com/developers.")

    @staticmethod
    def _unwrap(resp: httpx.Response) -> dict:
        """Raise on 4xx/5xx with the server's own ``detail``, else return the body."""
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json().get("detail", detail)
            except Exception:
                pass
            raise FinerxApiError(resp.status_code, str(detail), resp.headers.get("Retry-After"))
        # 202/204 bodies may be empty; a tool should not blow up on that.
        if not resp.content:
            return {}
        try:
            return resp.json()
        except Exception:
            return {}

    def get(self, path: str, params: dict | None = None) -> dict:
        self._require_key()
        url = f"{self.api_base}{path}"
        # Drop None-valued params so we never send ?zip=&lat= noise.
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            resp = httpx.get(url, params=clean, headers=self._headers(), timeout=self.timeout)
        except httpx.HTTPError as exc:  # network/timeout
            raise FinerxApiError(0, f"request failed: {exc}") from exc
        return self._unwrap(resp)

    def post(self, path: str, json: dict | None = None) -> dict:
        """POST a JSON body. Same auth, same error shape as ``get``."""
        self._require_key()
        url = f"{self.api_base}{path}"
        headers = {**self._headers(), "Content-Type": "application/json"}
        try:
            resp = httpx.post(url, json=json or {}, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as exc:  # network/timeout
            raise FinerxApiError(0, f"request failed: {exc}") from exc
        return self._unwrap(resp)
