<!-- mcp-name: com.finerxfinder/finerx -->

# FineRx MCP server

Give an AI assistant what US pharmacy chains were **seen charging with the free
FineRx discount card** — per chain, each price with the date it was observed,
near a ZIP code or nationally — the pharmacies nearby, **the card itself**, and
the reviewed map of **foreign medicine brands to their US equivalent** (pages and
card text in 12 languages), through the
[Model Context Protocol](https://modelcontextprotocol.io).

Source: [github.com/andrewfinerx/finerx-mcp](https://github.com/andrewfinerx/finerx-mcp) (public mirror of this package, MIT; issues welcome).

`finerx-mcp` is a thin client over the FineRx **public REST API**
(`/api/public/v1`). It has no direct database access and inherits the public
API's authentication and rate limits, so it adds zero extra attack surface.

## What changed in 2.0

- Prices are **card prices by pharmacy chain** with their observation date
  (Walmart per state), from one call per question; no other savings program's
  prices are read or named. `compare_prices` takes a drug name instead of an NDC
  (`ndc` + `quantity` still work), and a ZIP is optional.
- **The card travels with every answer**: each result carries a `card` block
  (codes, the dated price with the card, the card sentence, the small print) and
  ends its text with them.
- One UI bundle, `ui://finerx/v2/app.html`, draws prices, nearby pharmacies and
  the card; inside it the person changes dose, quantity or ZIP through two
  app-only tools the model does not see.
- `fromPrice` → `fromCardPrice`, `packageCount` is gone, `get_savings_card`
  returns the `finerx.view/2` envelope.

## Tools

| Tool | What it does |
|------|--------------|
| `compare_prices(drug, strength?, form?, quantity?, zip?, ndc?, locale?)` | Card price of one package at each pharmacy chain, with dates; nearest store of each chain; chains priced but without a store nearby; the card. Place: `zip`, else the host's approximate location (ChatGPT), else national |
| `find_nearby_pharmacies(zip?, family?, drug?, strength?, form?, quantity?)` | Stores within 30 miles per chain family; with `drug`, each with its chain's dated card price |
| `get_savings_card(locale?, channel?, drug?)` | The free card: codes, how to use it, what to say at the counter, links — plus a PNG for hosts that draw no UI |
| `email_savings_card(email, consent, locale?)` | Email the card to an address the person gave, after they said yes |
| `search_drugs(query, limit=10)` | Name → slug, with `fromCardPrice` (amount, package, date) and matching foreign brands |
| `get_drug(slug, locale?)` | Strengths × forms × pack sizes that have a card price, the default package and its prices by chain |
| `find_us_equivalent(brand, country?, locale?)` | A medicine from another country → what it is in the US, the vetted sentence to say, its card price |
| `foreign_brands_for_drug(slug)` | What a US drug is called abroad (the reverse lookup) |
| `get_prescription_options(locale?, drug?)` | What to do with no prescription yet (for controlled / age-restricted medicines: card prices and the card only) |
| `get_dataset_info()` | Card-price coverage: chain families, banners, newest observation, stores on the map |
| `ui_prices`, `ui_nearby` | App-only (`_meta.ui.visibility: ["app"]`): called by the UI, hidden from the model |

Every price carries its `observedAt` date and is never scaled to another pack
size. The server also ships **`instructions`** (the card rule: answer with each
price and its date, then the card sentence and codes, then the small print; no
promises of a price or a saving; `find_us_equivalent` first for a medicine from
another country; no medical advice), the resources `finerx://card`,
`finerx://how-it-works` and the UI bundle, and three **prompts**,
`price_and_card(drug)`, `prescription_help(drug?)` and
`us_equivalent(brand, country?)`.

## US equivalents (the thing nobody else does)

An immigrant does not search "atorvastatin" — they search Но-шпа, Nurofen,
Dolo-Neurobion, 999 Ganmaoling. FineRx holds a reviewed corpus mapping those
brands to their US status, and `find_us_equivalent` is how an assistant reaches
it instead of answering from memory.

```python
find_us_equivalent(brand="Но-шпа")
# → usClass "rx_alternative", inn "drotaverine hydrochloride",
#   guidance "No-Spa (drotaverine hydrochloride) is not sold in the US as the same
#             product; the closest US options need a prescription. Ask a doctor or
#             pharmacist which one fits."
#   otherMatches [{"brand": "No-Spa", "countries": ["Poland"], ...}]

find_us_equivalent(brand="Nurofen", country="Turkey")
# → usClass "same_inn", usGeneric "ibuprofen", usBrands ["Advil", "Motrin"],
#   usDrug {slug, fromCardPrice {amount, package, observedAt}}, the card, and the guidance sentence
#   that names ibuprofen as the thing to ask the pharmacist for.
```

Three classes, and the difference between them is the whole honesty of the
feature: **`same_inn`** means the same active ingredient is sold here (not the
same product — strength, form and excipients differ, which is what
`guidanceDisclaimer` says); **`rx_alternative`** means it is not sold here and
the closest US options need a prescription, so the answer is "ask a clinician",
never a named swap; **`no_equivalent`** means nothing here matches, and the
`components` breakdown states each ingredient's own US status rather than
inventing a substitute.

`guidance` is written and reviewed server-side. **Quote it; do not paraphrase,
translate or extend it** — a sentence composed by the model is a medical claim
nobody reviewed. `foreign_brands_for_drug(slug)` is the reverse ("what is
lisinopril called in Mexico?"), and `search_drugs` carries a `foreignBrands`
list so a client that only calls search still finds the corpus.

## Handing over the card

The card is free, is **not insurance**, needs no signup, and is credited at the
pharmacy counter by its group code — so an assistant can hand it over
completely, with no click-through.

- **Every result** (except `get_dataset_info`) carries `structuredContent.card`
  — `codes`, `priceWithCard` (amount, chain, `observedAt`) or null, `law` (the
  approved card sentence in the person's language), `fine` (the small print),
  `chainsCount`, `siteUrl`, `printUrl`, `actions` — and its text ends with the
  codes, the sentence and the small print. If the API is unreachable, the codes
  still come back (last good answer, then built-in constants).
- **`get_savings_card`** adds the steps, the sentence to say to the pharmacist
  and the links; hosts that draw no UI also get a PNG of the card (never
  ChatGPT, where an image counts against the Free plan's image quota).
- **`email_savings_card`** sends one card-only message. It **refuses without
  `consent=true`** and never calls the API in that case. The result masks the
  address (`j***@example.com`); FineRx does not store it.
- Every URL carries `src=<channel>` (`chatgpt` or `mcp` by default), so the
  surface that sent someone is visible in FineRx's own analytics — nothing about
  the person is.

## Renders as an app

On a host that supports UI components — **ChatGPT** (Apps SDK) and any host that
implements the standard **MCP Apps** extension (Claude) — `compare_prices`,
`find_nearby_pharmacies` and `get_savings_card` are drawn by one bundle,
**`ui://finerx/v2/app.html`** (mime `text/html;profile=mcp-app`), picked by
`structuredContent.view` of the `finerx.view/2` envelope. Tool `_meta` names it
under both `ui.resourceUri` and `openai/outputTemplate`; the resource `_meta`
carries `ui.domain` / `openai/widgetDomain`, an empty CSP and `finerx/build`.
UI strings arrive in `_meta["finerx/labels"]` in the person's language. The
bundle is built from `widget-src/` (Vite + Preact, single file, no external
resources) — see `widget-src/README.md`.

## Prerequisites

- A FineRx developer API key (format `frx_live_...`). Request one by emailing
  **partners@finerxfinder.com** — see <https://finerxfinder.com/developers>.
- [`uv`](https://docs.astral.sh/uv/) installed (provides `uvx`).

## Configuration

The server reads these environment variables:

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `FINERX_API_KEY` | yes | — | Your `frx_live_...` key |
| `FINERX_API_BASE` | no | `https://finerxfinder.com/api/public/v1` | Point at another host for local testing |
| `FINERX_CARD_IMAGE_URL` | no | `https://www.finerxfinder.com/card.png` | PNG `get_savings_card` returns to hosts without UI, when the API names no `delivery.imageUrl` |
| `FINERX_MCP_TRANSPORT` | no | `stdio` | `streamable-http` for the remote endpoint |
| `FINERX_MCP_HOST` / `FINERX_MCP_PORT` | no | `127.0.0.1` / `8000` | Bind address for the HTTP transport |
| `FINERX_MCP_PATH` | no | `/mcp` | HTTP path of the endpoint |
| `FINERX_MCP_STATELESS` | no | `1` (on) | `0` restores per-session HTTP transports (see below) |
| `FINERX_MCP_SUBJECT_SALT` | no | random per process | HMAC salt for the per-person rate limit (ChatGPT `openai/subject`) |
| `FINERX_MCP_COMPETITOR_PRICES` | no | `false` | Keep off: other programs' prices are not served in 2.0 |

## Install & run

Run directly with `uvx` (no manual install needed):

```bash
FINERX_API_KEY=frx_live_xxxxxxxx uvx finerx-mcp
```

The server speaks MCP over **stdio** by default.

### Remote (HTTP) mode

The same tools can be served over **Streamable HTTP** — the transport that
connector catalogs (ChatGPT Apps, Claude connectors, Gemini, Grok) consume, so a
user adds FineRx by URL with no local install. Set the transport (and, for a
hosted deployment, the bind host/port):

```bash
FINERX_API_KEY=frx_live_xxxx \
FINERX_MCP_TRANSPORT=streamable-http \
FINERX_MCP_HOST=0.0.0.0 FINERX_MCP_PORT=9000 \
uvx finerx-mcp
# → endpoint at http://<host>:9000/mcp
```

Defaults stay stdio, so existing Claude Desktop/Code/Cursor configs are
unaffected. The HTTP endpoint calls the same public REST API with the server's
`FINERX_API_KEY`, so hosting it exposes no data beyond the already-public API.

**HTTP mode is stateless by default.** Keyless one-shot connector calls — a
catalog probe, a single tool call from a chat — open a Streamable-HTTP session
and never DELETE it, so in session mode the transport map only grows (measured
on the hosted endpoint: 3568 sessions over 7 days, ~25 MB of swap a day, until
the container restarts). Stateless mode builds a transport per request and drops
it. It is safe here because no tool keeps per-session state: every call is a
fresh request against the public API, and the card-image cache is process-level,
not per-session. Set `FINERX_MCP_STATELESS=0` if you need SSE resumability;
stdio ignores the setting entirely.

## Claude Desktop

Add to your `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "finerx": {
      "command": "uvx",
      "args": ["finerx-mcp"],
      "env": {
        "FINERX_API_KEY": "frx_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

Restart Claude Desktop; the FineRx tools appear in the tools menu.

## Claude Code

```bash
claude mcp add finerx --env FINERX_API_KEY=frx_live_xxxx -- uvx finerx-mcp
```

Or add it to `.mcp.json` in your project:

```json
{
  "mcpServers": {
    "finerx": {
      "command": "uvx",
      "args": ["finerx-mcp"],
      "env": { "FINERX_API_KEY": "frx_live_xxxxxxxx" }
    }
  }
}
```

## Local development

Run against a local FineRx stack (e.g. the dev proxy on `:8080`):

```bash
export FINERX_API_KEY=frx_live_...        # a key you created via the CLI
export FINERX_API_BASE=http://localhost:8080/api/public/v1
uv run --project packages/finerx-mcp finerx-mcp
```

A smoke test that drives one tool call end-to-end lives at
`scripts/smoke_mcp.py` in the FineRx repo.

Run the unit tests (the API is mocked with respx — no key, no network):

```bash
cd packages/finerx-mcp && uv run --extra dev pytest -q
```

## Terms

Data is provided under the FineRx public API terms: attribution required
("Prices via FineRx"), prices are observed estimates with their dates and may
have changed — the pharmacy sets the final price — the card is not insurance,
and nothing here is medical advice. Pharmacy
location coordinates are © OpenStreetMap contributors (ODbL); place names (the
city and state of a ZIP code) come from GeoNames (CC BY 4.0).
