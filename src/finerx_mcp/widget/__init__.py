"""The savings card as an MCP App component (ChatGPT Apps SDK + MCP Apps).

``savings_card.html`` is the whole UI: one self-contained document with inline
CSS and vanilla JS, no external script, stylesheet, font or image — the host
serves it under a ``default-src 'none'`` CSP, so anything fetched from outside
would silently not load. It reads the tool's ``structuredContent`` (the same
``/card`` payload the model sees) through whichever bridge the host speaks, and
falls back to the three codes if it is handed nothing at all.

It is a data file inside the package, so hatchling ships it in the wheel
(``[tool.hatch.build.targets.wheel] packages = ["src/finerx_mcp"]`` takes every
file under the package directory) and ``importlib.resources`` finds it whether
the server runs from a checkout, a wheel, or a zipapp.
"""
from __future__ import annotations

from functools import lru_cache
from importlib.resources import files

WIDGET_URI = "ui://widget/savings-card.html"
# The exact mime type MCP Apps hosts match on to treat a resource as a component.
WIDGET_MIME_TYPE = "text/html;profile=mcp-app"
WIDGET_FILE = "savings_card.html"


@lru_cache(maxsize=1)
def load_widget_html() -> str:
    """The widget document. Read once per process (it never changes at runtime)."""
    return files(__package__).joinpath(WIDGET_FILE).read_text(encoding="utf-8")


__all__ = ["WIDGET_URI", "WIDGET_MIME_TYPE", "WIDGET_FILE", "load_widget_html"]
