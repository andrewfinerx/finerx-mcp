"""FineRx MCP server — expose FineRx drug-price data to AI agents.

A thin client over the FineRx public REST API (`/api/public/v1`). No direct DB
access; same auth + rate limits as the public API, zero extra attack surface.
"""

__version__ = "2.2.0"
