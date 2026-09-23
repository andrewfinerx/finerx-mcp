import { render } from "preact";
import "./styles.css";
import { App } from "./app";
import { createBridge } from "./bridge";

// The bridge starts BEFORE the first render and buffers what the host says, so
// a tool-result that lands during startup is replayed to the App on subscribe.
const bridge = createBridge();
bridge.start();

const root = document.getElementById("app");
if (root) render(<App bridge={bridge} />, root);

// Tell the host how tall the card is (MCP Apps size-changed + ChatGPT's
// notifyIntrinsicHeight): an inline card has no inner scroll, the iframe grows.
let lastHeight = 0;
function reportSize() {
  try {
    const doc = document.documentElement;
    const height = Math.ceil(Math.max(doc.scrollHeight, document.body ? document.body.scrollHeight : 0));
    if (!height || height === lastHeight) return;
    lastHeight = height;
    bridge.notifySize(Math.ceil(doc.clientWidth || 0), height);
  } catch {
    /* ignore */
  }
}
try {
  if (typeof ResizeObserver === "function") new ResizeObserver(reportSize).observe(document.body);
  else window.addEventListener("resize", reportSize);
} catch {
  /* ignore */
}
reportSize();
