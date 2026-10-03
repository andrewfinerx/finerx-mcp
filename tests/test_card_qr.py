"""MCP 2.2 — the card page as a QR in the card view (for a person at a computer).
Held here: it encodes the card page with ``src=<channel>-qr`` and nothing about
the person or the medicine; it is square rows of 0/1 the widget draws itself;
no usable link → no QR, and the card still stands."""
from __future__ import annotations

import segno
from conftest import call

from finerx_mcp import schemas, views


def _decode(rows: list[str]) -> list[list[bool]]:
    return [[c == "1" for c in r] for r in rows]


async def test_the_card_carries_a_qr_of_the_card_page(api) -> None:
    sc = (await call("get_savings_card", {"drug": "atorvastatin-calcium"})).structuredContent
    env = schemas.validate(sc)
    qr = sc["data"]["qr"]
    assert qr["url"].startswith("https://www.finerxfinder.com/") and "/card" in qr["url"]
    assert "src=mcp-qr" in qr["url"]
    assert "atorvastatin" not in qr["url"]
    n = len(qr["rows"])
    assert 21 <= n <= 61 and all(len(r) == n and set(r) <= {"0", "1"} for r in qr["rows"])
    assert env.data.qr.url == qr["url"]


def test_the_rows_are_the_qr_of_that_exact_link() -> None:
    qr = views.card_qr("https://www.finerxfinder.com/en/card?src=chatgpt", "chatgpt")
    assert qr["url"] == "https://www.finerxfinder.com/en/card?src=chatgpt-qr"
    expected = segno.make(qr["url"], error="m", micro=False).matrix
    assert _decode(qr["rows"]) == [[bool(c) for c in row] for row in expected]


def test_the_channel_tag_is_added_or_replaced_and_sanitised() -> None:
    assert views.card_qr("https://x.test/en/card", "claude")["url"] == "https://x.test/en/card?src=claude-qr"
    assert views.card_qr("https://x.test/en/card?a=1", "claude")["url"] == "https://x.test/en/card?a=1&src=claude-qr"
    assert views.card_qr("https://x.test/en/card?src=old&a=1", "Chat GPT!")["url"] == "https://x.test/en/card?src=chatgpt-qr&a=1"


def test_no_usable_link_means_no_qr() -> None:
    for bad in (None, "", "http://x.test/card", "javascript:alert(1)", 42, "https://x.test/" + "a" * 4000):
        assert views.card_qr(bad, "mcp") is None, bad
