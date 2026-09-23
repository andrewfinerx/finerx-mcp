"""Feature flags (env, read at CALL time so an operator flip needs no rebuild).

``FINERX_MCP_COMPETITOR_PRICES`` — default **false**. The public API also serves
prices from a feed of third-party savings programs (``/prices/compare`` offers,
the ``fromPrice``/``stats`` figures on search and drug detail). Whether that feed
may be republished to assistants is an open legal question (owner decision
2026-09-22), so MCP 2.0 reads ONLY free-card prices (``card_prices_current``
through ``/prices/near``, ``/drugs/{slug}/options``, ``/card-prices``) and never
names a program. With the flag off:

* no tool forwards a feed price (``fromPrice``, ``offers``, ``stats.*``);
* no tool names a savings program;
* ``isLowest`` is never set (it was computed against the feed).

Turning it on (a separate MINOR release, after the lawyer) only re-attaches the
1.x feed fields to the legacy ``compare_prices(ndc=…)`` path and to
``search_drugs``; every 2.0 surface stays card-only.
"""
from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}


def competitor_prices_enabled() -> bool:
    return os.environ.get("FINERX_MCP_COMPETITOR_PRICES", "false").strip().lower() in _TRUE
