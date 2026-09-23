/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// One self-contained HTML file: every script and style is inlined, because the
// host serves the widget under a `default-src 'none'`-style CSP with no
// connect/resource domains. scripts/finalize.mjs copies dist/index.html to
// ../src/finerx_mcp/widget/app.v2.html and enforces the size budget.
export default defineConfig({
  publicDir: false,
  esbuild: { jsx: "automatic", jsxImportSource: "preact", legalComments: "none" },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2020",
    cssCodeSplit: false,
    assetsInlineLimit: 100_000_000,
    modulePreload: { polyfill: false },
    reportCompressedSize: false,
  },
  plugins: [viteSingleFile({ removeViteModuleLoader: true })],
  test: {
    environment: "jsdom",
    globals: true,
    include: ["test/**/*.test.{ts,tsx}"],
  },
});
