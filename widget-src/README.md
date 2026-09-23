# FineRx MCP App v2 — widget source

One self-contained HTML file, `../src/finerx_mcp/widget/app.v2.html`, served as the
MCP Apps resource **`ui://finerx/v2/app.html`** (mime `text/html;profile=mcp-app`).
One bundle draws every view; the view is picked by `structuredContent.view` of the
`finerx.view/2` envelope (contract C2, phase 2 C2'/C3'): `prices`, `pharmacies`
(inline list, or the SVG map in fullscreen), `card`, `search` (fullscreen),
`equivalent`, `rx`. An unknown view falls back to the tool's text content plus
the card. The card strip (teal card face, codes, the law verbatim, two buttons,
the small print) is in every view.

Vite + Preact + TypeScript + `vite-plugin-singlefile`. Node is needed only to
BUILD: the built file is committed, and the Python package (wheel, box deploy)
ships it as a plain data file. `node_modules/` and `dist/` are git-ignored.

## Build and test

```bash
cd packages/finerx-mcp/widget-src
npm install
npm test          # vitest + @testing-library/preact, fixtures in fixtures/*.json
npm run build     # tsc → vite build → scripts/finalize.mjs → ../src/finerx_mcp/widget/app.v2.html
npm run check     # re-check the committed file only (size + no external resources)
```

`scripts/finalize.mjs` fails the build when the file is over **150 KB raw or
45 KB gzip**, or when it contains anything that would load from outside
(`<script src>`, `<link href>`, `@import`, remote `url()`), or any `http(s)://`
string outside a short allowlist (XML namespace ids inside Preact; the Google
Maps "Directions" link, which is opened through the host as a navigation and
never loaded into the frame). Hosts serve the widget with empty CSP domain lists.

Rebuild and commit `app.v2.html` whenever `src/` changes.

## How the bridge works (`src/bridge.ts`)

Two protocols, both optional, detected at runtime; nothing in the bridge may
throw into the UI.

1. **MCP Apps standard** (spec 2026-01-26), JSON-RPC 2.0 over `postMessage` with
   the parent frame (messages from any other source are ignored):
   - app → host: `ui/initialize` (`protocolVersion: "2026-01-26"`, `appInfo`,
     `appCapabilities.availableDisplayModes`) → `ui/notifications/initialized`;
     `tools/call`; `ui/open-link`; `ui/request-display-mode`;
     `ui/update-model-context` (after every pick in the widget);
     `ui/notifications/size-changed`;
   - host → app: `ui/notifications/tool-input` (loading skeleton),
     `tool-result`, `tool-cancelled`, `host-context-changed` (theme, style
     variables, locale, display mode — merged), `ping` and
     `ui/resource-teardown` (answered `{}`); unknown requests get −32601.
2. **`window.openai` adapter** (ChatGPT Apps SDK): `toolOutput` +
   `toolResponseMetadata` (read on start and on `openai:set_globals`, only when
   the object changed), `callTool`, `requestDisplayMode`, `openExternal`,
   `widgetState`/`setWidgetState`, `notifyIntrinsicHeight`.
   `ui/update-model-context` goes over the standard channel only (ChatGPT reads
   `widgetState` instead).

Order: the standard channel is used once `ui/initialize` answered (or when there
is no `window.openai` at all); until then, calls go through `window.openai` when
it exists. `widgetState` exists only in ChatGPT; it keeps
`{view, slug, form, strength, quantity}` and a ZIP only when the person TYPED it
(not one named in the chat, not one resolved from an address) — never an
address, never coordinates. On a ChatGPT re-mount the widget restores that
package once.

The bridge buffers the latest tool input/result/host context and replays them to
a subscriber, so a result that arrives before the first render is not lost.

## What the widget calls

| Action | Tool call |
|---|---|
| dose / quantity chip, "other quantity" button | `ui_prices {slug, form, strength, quantity, zip?}` |
| ZIP field in prices | `ui_prices {…package, zip}` |
| "All pharmacies" | `ui_nearby {slug, form, strength, quantity, zip?}` |
| ZIP field in pharmacies | `ui_nearby {zip, family?, slug?, form?, strength?, quantity?}` |
| Save ▾ → Email (consent checkbox required) | `email_savings_card {email, consent: true, locale}` |
| Directions | `ui/open-link` to Google Maps with the STORE's coordinates |
| Save ▾ → Print / Wallet (stand-in until phase 3) | `ui/open-link` to `card.printUrl` |
| Save ▾ → SMS | `ui/open-link` to `sms:?&body=<card.actions.smsBody>` |
| Show at the counter | `ui/request-display-mode {mode: "fullscreen"}` (in place if refused; nothing asked when already fullscreen) |
| **"Where" field** (prices, pharmacies, search) | a 5-digit ZIP (or ZIP+4) → `zip`; any other text (city, address, ≤200 chars) → `where`, sent ONCE; later calls carry the ZIP the server resolved (`origin.precision: "address"`). While the text is not a ZIP, `whereNote` under the field says it goes once to the US Census geocoder and is not stored |
| search: typing (≥2 chars, debounce 250 ms) | `ui_suggest {q, locale}` — the card strip then shows the card THAT answer carries (its law has no adjectives when a restricted medicine is among the results) |
| search: a result / "Often searched" | `ui_prices {slug, zip? \| where?}` → the prices view in the same frame, "Back to search" returns (query and results kept) |
| search: a foreign brand (every class) | `ui_equivalent {brand_slug, locale}` → the equivalent view (guidance verbatim, "same ingredient ≠ same product"); "Prices in the US" goes on from there, "Back to search" returns |
| search opened (`open_price_finder`) | `ui/request-display-mode fullscreen` once; refused → inline: suggestions (≤5), "Often searched", a "Search" button, NO free-text field |
| pharmacies: "On the map" / "List" | `ui/request-display-mode fullscreen` / back to `inline` (only if the map asked for it) |
| pharmacies: family chips, range chips (5/10/30 mi), a dot, a list row | local, no tool call; a dot opens the store card (price + date + Directions) |
| equivalent: "Prices in the US" (only `usClass: same_inn`) | `ui_prices {slug: us.slug}` |
| rx: "Prices with the card" / an official link | `ui_prices {slug: drug.slug}` / `ui/open-link` (https only) |
| after every pick that draws prices/pharmacies | `ui/update-model-context` — "Person selected 90 × 40 mg tablet of Atorvastatin near Austin, TX …": package + city/state or ZIP, never an address |

A ZIP is sent back only when the person gave it: typed here, named in the chat
(origin precision `zip`) or resolved from the place they typed (`address`); an
approximate origin (ChatGPT `userLocation`) stays with the host, which sends it
again with every call. `where` text is never stored, logged or echoed into the
model context.

Any view reached by a pick from `search`, `equivalent`, `rx` or `prices` gets a
"← Back" link (to the view it replaced); a new result from the model clears it.

## Texts

UI strings come from `_meta["finerx/labels"]`; `src/labels.ts` holds the English
fallback for every key (contract keys + a few widget-only keys the MCP may add:
`bin, pcn, group, zipGo, zipInvalid, other, wallet, emailPlaceholder, emailSend,
emailConsent, sending, emailSent, emailError, actionError, directions,
allFamilies, pharmaciesTitle, pricesWithoutStores, showMore, close,
noPriceShort`) and the phase-2 keys (`where, wherePlaceholder, changeWhere,
whereInvalid, needsWhere, searchTitle, searchPlaceholder, openSearch, popular,
searching, noResults, fromWithCard, kindGeneric, kindBrand, foreignBrand, inUs,
noUsProduct, backToSearch, back, onMap, listView, you, mapTitle, mapRange,
offMap, equivalentUs, usClassSameInn, usClassRxAlternative, usClassNoEquivalent,
sameInnNote, pricesInUs, rxTitle, rxTitleAny, rxRestricted, pricesWithCard,
withoutInsurance, whereNote, inn`). A phase-2 key the payload lacks falls back to the phase-1
key an older server translated (`changeWhere` → `changeZip`, `wherePlaceholder`
→ `zipPlaceholder`, `whereInvalid` → `zipInvalid`, `needsWhere` → `needsZip`),
then to English. Placeholders: `nearLabel {place}` (also `{city}`),
`observed {date}`, `miles {n}`, `moreChains {n}`, `showMore {n}`,
`fromWithCard {price} {date}`, `inUs {name}`, `offMap {n} {r}`, `rxTitle {name}`.

`guidance` / `disclaimer` (equivalent) and the rx sections are the API's own
text, rendered verbatim; the restricted-rx sentence is `data.note` when sent.

The card law (`card.law`) and the small print (`card.fine`) are rendered
VERBATIM from the payload. Only when a result carries no card at all does the
widget show the bundled codes and the approved English no-price law.

## Layout rules

System fonts; colours from the host's `hostContext.styles.variables` when sent,
otherwise our tokens (light/dark via `hostContext.theme` or
`prefers-color-scheme`). Brand green (`#047857` / dark `#10B981`) only on the
primary button. Two buttons inline, no inner scrolling, works at 320 px. RTL for
`dir: "rtl"`; prices and codes are pinned `ltr`, money is always `$4.20`.
Fullscreen widens the column to 72 rem; the map sits beside the list at
≥ 720 px and above it below that.

**The map** (`components/StoreMap.tsx`) is an SVG scheme, no tiles, nothing
fetched: an equirectangular projection around the person (the origin's
`lat`/`lon` when the API sends them, otherwise fitted from the stores' own
`miles` by least squares — then marked "You ≈"), rings at 5/10/30 mi (the
default range holds 80 % of the stores; farther ones stay in the list), one dot
per store in its family's colour with a monogram (`src/families.ts`, white text
≥ 4.5:1 on every colour), overlapping dots walked apart so each stays
clickable.
