"""What the calling HOST tells us about itself — and nothing it did not.

Everything here reads the request ``_meta`` a host attaches to a tool call (and,
where a session exists, the capabilities it declared at initialize). The hosted
endpoint is STATELESS, so a per-request signal is the only reliable one: no
``initialize`` is replayed for a tool call, and ``client_params`` is usually
absent.

* ``ui_supported`` — can this host render an MCP App? First the standard
  signal (the ``io.modelcontextprotocol/ui`` extension, in the declared
  capabilities or in the request ``_meta``), then ChatGPT's own ``openai/*``
  keys. A host that says neither gets text (and, for the card, a PNG).
* ``user_location`` — ChatGPT's ``openai/userLocation`` hint, reduced at once to
  coordinates rounded to 0.01° (~1 km). It is used for ONE API request and never
  stored, logged or echoed; the API reduces it further to the nearest ZIP area.
* ``subject_key`` — ``HMAC(FINERX_MCP_SUBJECT_SALT, openai/subject)``, the
  per-person rate-limit key. The raw subject never leaves this module.

PRIVACY: no function here logs, and none returns the raw ``_meta``.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Any

UI_EXTENSION = "io.modelcontextprotocol/ui"

# The 12 site locales (apps/web/lib/i18n.ts). Anything else answers in English.
LOCALES = ("en", "es", "zh", "vi", "tl", "ar", "ko", "ru", "pt", "ht", "fr", "tr")
RTL_LOCALES = frozenset({"ar"})

# A per-process fallback salt when the env has none: keys stay stable for the
# life of the process (so the limiter works) and mean nothing outside it.
_SALT = (os.environ.get("FINERX_MCP_SUBJECT_SALT") or "").encode() or secrets.token_bytes(32)

_US = {"us", "usa", "united states", "united states of america"}


def host_meta(ctx: Any) -> dict[str, Any]:
    """The request ``_meta`` the host attached to this call, as a plain dict ({}
    when there is none — stdio clients and tests usually send nothing)."""
    if ctx is None:
        return {}
    try:
        meta = ctx.request_context.meta
    except (AttributeError, ValueError, LookupError):
        return {}
    if meta is None:
        return {}
    return dict(getattr(meta, "model_extra", None) or {})


def _declared_capabilities(ctx: Any) -> dict[str, Any]:
    """Capabilities from ``initialize`` — only when this transport kept a session."""
    try:
        params = ctx.request_context.session.client_params
    except (AttributeError, ValueError, LookupError):
        return {}
    caps = getattr(params, "capabilities", None)
    if caps is None:
        return {}
    try:
        return caps.model_dump(exclude_none=True)
    except Exception:
        return {}


def _mentions(obj: Any, key: str, depth: int = 3) -> bool:
    if depth < 0:
        return False
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.startswith(key):
                return True
            if _mentions(v, key, depth - 1):
                return True
    return False


def is_chatgpt(ctx: Any) -> bool:
    """ChatGPT stamps every request ``_meta`` with ``openai/*`` keys (locale,
    userAgent, subject…); no other host does."""
    return any(k.startswith("openai/") for k in host_meta(ctx))


def ui_supported(ctx: Any) -> bool:
    if _mentions(_declared_capabilities(ctx), UI_EXTENSION):
        return True
    meta = host_meta(ctx)
    if _mentions(meta, UI_EXTENSION):
        return True
    return any(k.startswith("openai/") for k in meta)


def host_class(ctx: Any) -> str:
    """For the log line only: ``chatgpt`` | ``apps`` (another MCP Apps host) |
    ``text``. Never anything that identifies a person."""
    if is_chatgpt(ctx):
        return "chatgpt"
    return "apps" if ui_supported(ctx) else "text"


def default_channel(ctx: Any) -> str:
    """The ``?src=`` tag on our links when the model passes none. A channel is a
    surface, not a person — everyone on it shares the tag."""
    return "chatgpt" if is_chatgpt(ctx) else "mcp"


def short_locale(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    loc = raw.strip().lower().replace("_", "-").split("-", 1)[0]
    return loc if loc in LOCALES else None


def host_locale(ctx: Any) -> str | None:
    """The language the HOST says the person is reading (``openai/locale``,
    ``es-419`` → ``es``), or None."""
    meta = host_meta(ctx)
    return short_locale(meta.get("openai/locale") or meta.get("locale"))


def resolve_locale(arg: str | None, ctx: Any) -> str:
    """The model's ``locale`` argument, else the host's, else English."""
    return short_locale(arg) or host_locale(ctx) or "en"


def text_dir(locale: str) -> str:
    return "rtl" if locale in RTL_LOCALES else "ltr"


@dataclass(frozen=True)
class Location:
    """A coarse position: 0.01° (~1 km). The only form a coordinate takes here."""

    lat: float
    lon: float


def _coord(value: Any, lo: float, hi: float) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or not lo <= v <= hi:  # NaN / out of range
        return None
    return round(v, 2)


def user_location(ctx: Any) -> Location | None:
    """ChatGPT's approximate location hint, rounded, US only. None otherwise.

    Claude and the MCP Apps standard send no location; the widget's ZIP field is
    the path there.
    """
    raw = host_meta(ctx).get("openai/userLocation")
    if not isinstance(raw, dict):
        return None
    country = raw.get("country")
    if isinstance(country, str) and country.strip() and country.strip().lower() not in _US:
        return None  # FineRx prices US pharmacies only
    lat = _coord(raw.get("latitude", raw.get("lat")), -90.0, 90.0)
    lon = _coord(raw.get("longitude", raw.get("lon")), -180.0, 180.0)
    if lat is None or lon is None:
        return None
    return Location(lat=lat, lon=lon)


def subject_key(ctx: Any) -> str | None:
    """HMAC of ``openai/subject`` (ChatGPT's anonymous per-user id), or None."""
    subject = host_meta(ctx).get("openai/subject")
    if not isinstance(subject, str) or not subject:
        return None
    return hmac.new(_SALT, subject.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
