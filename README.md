<!-- mcp-name: com.finerxfinder/finerx -->

# FineRx MCP server

Give an AI assistant live access to **FineRx** drug-price data — the same
catalog, package, price-comparison, and nearest-pharmacy data shown on the
FineRx website — **the free FineRx discount card**, and the reviewed map of
**foreign medicine brands to their US equivalent** (pages and card text in
12 languages), through the
[Model Context Protocol](https://modelcontextprotocol.io).

Source: [github.com/andrewfinerx/finerx-mcp](https://github.com/andrewfinerx/finerx-mcp) (public mirror of this package, MIT; issues welcome).

`finerx-mcp` is a thin client over the FineRx **public REST API**
(`/api/public/v1`). It has no direct database access and inherits the public
API's authentication and rate limits, so it adds zero extra attack surface.

## Tools

| Tool | What it does |
|------|--------------|
| `search_drugs(query, limit=10)` | Find drugs by name/alias → candidates with slugs + from-prices, plus any matching foreign brands |
| `get_drug(slug, locale?, channel?)` | A drug's stats + strength/form variants + `savingsCard` |
| `compare_prices(ndc, quantity, locale?, channel?)` | Offer matrix (chain × savings program × price × observation date) + `savingsCard` |
| `find_nearby_pharmacies(zip, chains?, limit=3)` | Nearest store locations per chain around a ZIP |
| `get_dataset_info()` | Dataset coverage, freshness, and attribution/disclaimer terms |
| `get_savings_card(locale?, channel?, drug?)` | The free discount card: codes, how to use it, ways to save it — **plus an image of the card**, and an interactive card in hosts that render MCP Apps |
| `email_savings_card(email, consent, locale?)` | Email the card to an address the person gave, after they said yes |
| `get_prescription_options(locale?, drug?)` | What to do when there is no prescription yet, or the brand costs too much |
| `find_us_equivalent(brand, country?, locale?, channel?)` | A medicine from another country → what it is in the US, the vetted sentence to say, the price, the card |
| `foreign_brands_for_drug(slug)` | What a US drug is called abroad (the reverse lookup) |

Every result embeds a one-line `disclaimer` and, wherever a price appears, an
`observedAt` date. No tool ever returns hidden vendors or an operator reference
price.

The server also ships **`instructions`** (served to the client as system-level
guidance: quote the observation date, call `find_us_equivalent` first for a
medicine from another country, offer the card whenever you quote a price, never
say guaranteed/best/cheapest, never give medical advice), three
**resources** — `finerx://card` (the card as markdown), `finerx://how-it-works`,
and `ui://widget/savings-card.html` (the card as a UI component, below) — and
three **prompts**, `price_and_card(drug)`, `prescription_help(drug?)` and
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
#   usDrug {slug, fromPrice, observedAt}, savingsCard, and the guidance sentence
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

The card is the free LowerMyRx discount card FineRx distributes. It is **not
insurance**, needs no signup, and is credited at the pharmacy counter by the
group code — so an assistant can hand it over completely, with no click-through:

- **`get_savings_card`** returns the three counter codes, what the card is and
  is not, the steps to use it, the sentence to say to the pharmacist, an
  optional observed price with its date, an FAQ and the legal lines — *and* a
  PNG of the card as an image content block, so a chat client can show something
  the person saves to their phone. The PNG is fetched once per process and
  cached in memory; if that fetch fails the tool still returns the card text,
  and `imageUrl` is in the JSON either way for clients that cannot render images.
- **`email_savings_card`** sends one card-only message. It **refuses without
  `consent=true`** and never calls the API in that case — the assistant has to
  ask for the address and an explicit yes first. The result masks the address
  (`j***@example.com`); FineRx does not store it. `503` means email delivery is
  off (offer the image or the link instead), `429` means the abuse cap was hit.
- **`compare_prices` / `get_drug`** carry the same card object as `savingsCard`,
  so the card is present in the same turn as the price. Say "lowest" only when
  `savingsCard.price.isLowest` is true; otherwise repeat the provided `note`.
- Every URL the tools return carries `src=<channel>` (default `mcp`), so the
  assistant that sent someone is visible in FineRx's own analytics — nothing
  about the person is.

## Renders as an app

On a host that supports UI components — **ChatGPT** (Apps SDK) and any host that
implements the standard **MCP Apps** extension, which is how Claude renders one —
`get_savings_card` does not just return JSON: the host draws the card in the
conversation.

- The component is the resource **`ui://widget/savings-card.html`**, served with
  mime type `text/html;profile=mcp-app`. `get_savings_card` points at it from its
  tool `_meta`, under both the standard key (`ui.resourceUri`) and OpenAI's alias
  (`openai/outputTemplate`), so it renders in either kind of host.
- It shows the teal card with the three counter codes (large and selectable), the
  card price for the drug when one is known (with the date it was observed and
  the vetted note — never a "lowest" badge unless `price.isLowest` is true), the
  sentence to say to the pharmacist with a Copy button, the steps, buttons to
  open / print / save / email the card, the FAQ, and the legal lines. Every
  string comes from the tool result's `labels`, so it speaks the same language
  and uses the same words as finerxfinder.com.
- The Email button calls `email_savings_card` from inside the component (which is
  why that tool is declared `ui.visibility: ["model", "app"]` /
  `openai/widgetAccessible`). Consent is a checkbox the person ticks; the address
  is sent once and never written back into the page.
- The document is **entirely self-contained** — inline CSS and vanilla JS, no
  external script, stylesheet, font or image — because hosts serve it under a
  `default-src 'none'` CSP. Links are opened through the host bridge
  (`window.openai.openExternal` or `ui/open-link`), never `window.open`.
- It renders with **no data at all** (a host that sends nothing still shows the
  three codes), with no `price` block, and with no `labels` (English fallbacks).

**Testing it without a host.** The tool result is the whole input, so a mocked
bridge is enough:

```bash
uv run --project packages/finerx-mcp python -c \
  "from finerx_mcp.widget import load_widget_html; open('/tmp/w.html','w').write(load_widget_html())"
```

Prepend a `<script>` that defines `window.openai = {toolOutput: <a /card
response>, theme: "light", locale: "en", callTool: …, openExternal: …}` to that
file and open it in a browser for the ChatGPT bridge; or put the widget in an
`<iframe srcdoc>` and have the parent answer `ui/initialize` and then post a
`ui/notifications/tool-result` notification to exercise the standard bridge.
`get_savings_card`'s `structuredContent` is exactly what the component reads, so
`GET /api/public/v1/card` is a ready-made fixture.

## Prerequisites

- A FineRx developer API key (format `frx_live_...`). Request one by emailing
  **partners@finerxfinder.com** — see <https://finerxfinder.com/developers>.
- [`uv`](https://docs.astral.sh/uv/) installed (provides `uvx`).

## Configuration

The server reads two environment variables:

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `FINERX_API_KEY` | yes | — | Your `frx_live_...` key |
| `FINERX_API_BASE` | no | `https://finerxfinder.com/api/public/v1` | Point at another host for local testing |
| `FINERX_CARD_IMAGE_URL` | no | `https://www.finerxfinder.com/card.png` | PNG `get_savings_card` returns, when the API response names no `delivery.imageUrl` |
| `FINERX_MCP_TRANSPORT` | no | `stdio` | `streamable-http` for the remote endpoint |
| `FINERX_MCP_HOST` / `FINERX_MCP_PORT` | no | `127.0.0.1` / `8000` | Bind address for the HTTP transport |
| `FINERX_MCP_STATELESS` | no | `1` (on) | `0` restores per-session HTTP transports (see below) |

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

Run the unit tests (HTTP is stubbed — no key, no network):

```bash
uv run --project packages/finerx-mcp --with pytest --with pytest-asyncio \
    pytest packages/finerx-mcp/tests -q
```

## Terms

Data is provided under the FineRx public API terms: attribution required
("Prices via FineRx"), prices are observed estimates (not guaranteed or insured
prices) and may be out of date, and nothing here is medical advice. Pharmacy
location coordinates are © OpenStreetMap contributors (ODbL).
