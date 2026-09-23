// Copy the single-file build to the package and enforce the bundle contract:
//   - ≤ 150 KB as is, ≤ 45 KB gzip (the host downloads it on every connect);
//   - nothing loads from outside: no <script src>, <link href>, @import,
//     url(http…), and no http(s) URL at all except the allowlist below.
// Fails (exit 1) on any breach, so `npm run build` fails with it.
// `--check-only` checks the committed file without building/copying.

import { copyFileSync, readFileSync, statSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(here, "../dist/index.html");
const OUT = resolve(here, "../../src/finerx_mcp/widget/app.v2.html");
const RAW_LIMIT = 150 * 1024;
const GZIP_LIMIT = 45 * 1024;

// http(s) strings the bundle may contain because nothing is FETCHED from them:
//  - XML namespace identifiers inside Preact's SVG/MathML support;
//  - the maps "Directions" link, opened through the host (ui/open-link /
//    openExternal) as a navigation, never loaded into the frame.
const ALLOWED_URL_PREFIXES = [
  "http://www.w3.org/",
  "https://www.google.com/maps/dir/",
];

const checkOnly = process.argv.includes("--check-only");
if (!checkOnly) copyFileSync(SRC, OUT);

const html = readFileSync(OUT, "utf8");
const raw = statSync(OUT).size;
const gz = gzipSync(html, { level: 9 }).length;
const problems = [];

if (raw > RAW_LIMIT) problems.push(`raw size ${raw} B > ${RAW_LIMIT} B`);
if (gz > GZIP_LIMIT) problems.push(`gzip size ${gz} B > ${GZIP_LIMIT} B`);
if (/<script[^>]+\bsrc\s*=/i.test(html)) problems.push("external <script src>");
if (/<link[^>]+\bhref\s*=/i.test(html)) problems.push("external <link href>");
if (/@import\b/i.test(html)) problems.push("CSS @import");
if (/url\(\s*['"]?(https?:)?\/\//i.test(html)) problems.push("CSS url() to a remote resource");
for (const m of html.matchAll(/https?:\/\/[^\s"'`)<>\\]*/g)) {
  if (!ALLOWED_URL_PREFIXES.some((p) => m[0].startsWith(p))) problems.push(`URL not allowed: ${m[0]}`);
}

const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
console.log(`app.v2.html: ${kb(raw)} raw, ${kb(gz)} gzip (limits ${kb(RAW_LIMIT)} / ${kb(GZIP_LIMIT)})`);
if (problems.length) {
  for (const p of [...new Set(problems)]) console.error(`bundle check FAILED: ${p}`);
  process.exit(1);
}
