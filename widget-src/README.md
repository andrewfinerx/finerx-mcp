# FineRx MCP App v2 — widget source

One self-contained HTML file, `../src/finerx_mcp/widget/app.v2.html`, served as the
MCP Apps resource **`ui://finerx/v2/app.html`** (mime `text/html;profile=mcp-app`).
One bundle draws every view; the view is picked by `structuredContent.view` of the
`finerx.view/2` envelope (contract C2): `prices`, `pharmacies`, `card`. An unknown
view falls back to the tool's text content plus the card.

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

Order: the standard channel is used once `ui/initialize` answered (or when there
is no `window.openai` at all); until then, calls go through `window.openai` when
it exists. `widgetState` exists only in ChatGPT; it keeps
`{view, slug, form, strength, quantity}` and a ZIP only when the person typed it
— never coordinates. On a ChatGPT re-mount the widget restores that package once.

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
| Show at the counter | `ui/request-display-mode {mode: "fullscreen"}` (in place if refused) |

A ZIP is sent back only when the person typed it or the origin precision is
`zip` (named in the chat); an approximate origin (ChatGPT `userLocation`) stays
with the host, which sends it again with every call.

## Texts

UI strings come from `_meta["finerx/labels"]`; `src/labels.ts` holds the English
fallback for every key (contract keys + a few widget-only keys the MCP may add:
`bin, pcn, group, zipGo, zipInvalid, other, wallet, emailPlaceholder, emailSend,
emailConsent, sending, emailSent, emailError, actionError, directions,
allFamilies, pharmaciesTitle, pricesWithoutStores, showMore, close,
noPriceShort`). Placeholders: `nearLabel {place}` (also `{city}`),
`observed {date}`, `miles {n}`, `moreChains {n}`, `showMore {n}`.

The card law (`card.law`) and the small print (`card.fine`) are rendered
VERBATIM from the payload. Only when a result carries no card at all does the
widget show the bundled codes and the approved English no-price law.

## Layout rules

System fonts; colours from the host's `hostContext.styles.variables` when sent,
otherwise our tokens (light/dark via `hostContext.theme` or
`prefers-color-scheme`). Brand green (`#047857` / dark `#10B981`) only on the
primary button. Two buttons inline, no inner scrolling, works at 320 px. RTL for
`dir: "rtl"`; prices and codes are pinned `ltr`, money is always `$4.20`.
