"""The MCP App components (ChatGPT Apps SDK + the MCP Apps standard).

``app.v2.html`` (MCP 2.0) is the one bundle every view is drawn with — prices,
pharmacies, card — picked by ``structuredContent.view`` of the ``finerx.view/2``
envelope. It is BUILT from ``widget-src/`` (Vite + Preact, singlefile) and the
built file is committed, so neither the wheel nor the box needs Node.

``savings_card.html`` is the 1.x card component. 2.0 no longer serves it (the old
URI ``ui://widget/savings-card.html`` now answers with the v2 bundle, which draws
``view=card``); the file stays in the package for 90 days so a rollback is a
version pin, not a rebuild.

Both are self-contained documents — no external script, stylesheet, font or
image: hosts serve them under a ``default-src 'none'`` CSP, so anything fetched
from outside would silently not load. They are data files inside the package, so
hatchling ships them in the wheel and ``importlib.resources`` finds them whether
the server runs from a checkout, a wheel, or a zipapp.
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from importlib.resources import files

# The exact mime type MCP Apps hosts match on to treat a resource as a component.
WIDGET_MIME_TYPE = "text/html;profile=mcp-app"

# MCP 2.0: the major version of the view contract lives in the path. An
# incompatible change is a NEW uri (v3) — hosts cache templates by uri.
APP_URI = "ui://finerx/v2/app.html"
APP_FILE = "app.v2.html"

# 1.x uri, kept resolvable: a host holding a stale tools/list still finds a
# component there (the v2 bundle, which draws view=card).
WIDGET_URI = "ui://widget/savings-card.html"
WIDGET_FILE = "savings_card.html"


@lru_cache(maxsize=1)
def load_app_html() -> str:
    """The v2 bundle. Read once per process (it never changes at runtime)."""
    return files(__package__).joinpath(APP_FILE).read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_widget_html() -> str:
    """The 1.x card component (kept for rollback; not served by 2.0)."""
    return files(__package__).joinpath(WIDGET_FILE).read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def build_id() -> str:
    """``finerx/build`` — which bundle a host is showing, for diagnostics.

    The deploy sets ``FINERX_MCP_BUILD`` to the git sha8; without it (a pip
    install, a test) it is the first 8 hex of the bundle's own sha256, which
    changes exactly when the file does.
    """
    env = (os.environ.get("FINERX_MCP_BUILD") or "").strip()
    if env:
        return env[:12]
    return hashlib.sha256(load_app_html().encode("utf-8")).hexdigest()[:8]


__all__ = [
    "APP_FILE",
    "APP_URI",
    "WIDGET_FILE",
    "WIDGET_MIME_TYPE",
    "WIDGET_URI",
    "build_id",
    "load_app_html",
    "load_widget_html",
]
