// The router: one bundle, the view picked by structuredContent.view (C2).
// State lives here — the current envelope, labels, the in-flight flag, the ZIP
// the person typed and the counter mode — and flows down through Ctx.

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import type { Bridge, BridgeEvent, HostContext } from "./bridge";
import { Ctx, type AppCtx } from "./context";
import { makeT } from "./labels";
import { interpret, type Interpreted } from "./result";
import type { CardView, Envelope, Labels, PharmaciesData, PricesData, ToolResultLike } from "./types";
import { Counter } from "./components/Counter";
import { PricesView } from "./views/Prices";
import { PharmaciesView } from "./views/Pharmacies";
import { CardViewPage } from "./views/Card";
import { Empty, ErrorState, Fallback, Loading } from "./views/States";

type Screen =
  | { kind: "empty" }
  | { kind: "loading"; args: Record<string, unknown> }
  | Exclude<Interpreted, { kind: "ready" }>
  | { kind: "ready"; envelope: Envelope };

const RTL = /^(ar|he|fa|ur)(\b|-|_)/i;

/** Host style variables (MCP Apps `hostContext.styles.variables`) onto :root.
 * Values that could fetch anything (`url(`) are dropped — CSP has no domains. */
function applyHostContext(ctx: HostContext) {
  const root = document.documentElement;
  try {
    if (ctx.theme === "dark" || ctx.theme === "light") root.setAttribute("data-theme", ctx.theme);
    const vars = ctx.styles && ctx.styles.variables;
    if (vars && typeof vars === "object") {
      for (const [name, value] of Object.entries(vars)) {
        if (name.startsWith("--") && typeof value === "string" && !/url\s*\(/i.test(value)) {
          root.style.setProperty(name, value);
        }
      }
    }
    root.setAttribute("data-display", ctx.displayMode || "inline");
  } catch {
    /* keep prefers-color-scheme */
  }
}

function modelNote(env: Envelope): string | null {
  if (env.view === "prices") {
    const d = env.data as PricesData;
    return `The person picked in the FineRx card: ${d.drug.name}${d.package?.label ? `, ${d.package.label}` : ""}. The card now shows card prices for that package.`;
  }
  if (env.view === "pharmacies") {
    const d = env.data as PharmaciesData;
    return `The FineRx card now lists pharmacies${d.drug?.name ? ` for ${d.drug.name}` : ""} near the location the person chose.`;
  }
  return null;
}

export function App({ bridge }: { bridge: Bridge }) {
  const [screen, setScreen] = useState<Screen>({ kind: "empty" });
  const [labels, setLabels] = useState<Labels | null>(null);
  const [hostLocale, setHostLocale] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(false);
  const [userZip, setUserZip] = useState<string | null>(null);
  const [counter, setCounter] = useState(false);
  const grantedFullscreen = useRef(false);
  const restored = useRef(false);

  const acceptLabels = (next: Labels | null) => {
    if (next && Object.keys(next).length) setLabels(next);
  };

  const onEvent = useCallback((event: BridgeEvent) => {
    if (event.type === "host-context") {
      applyHostContext(event.context);
      if (typeof event.context.locale === "string") setHostLocale(event.context.locale);
      if (event.context.displayMode === "inline" && grantedFullscreen.current) {
        // The person left fullscreen from the host's own chrome.
        grantedFullscreen.current = false;
        setCounter(false);
      }
      return;
    }
    if (event.type === "tool-input") {
      setScreen((s) => (s.kind === "empty" || s.kind === "loading" ? { kind: "loading", args: event.args } : s));
      return;
    }
    if (event.type === "tool-cancelled") {
      setScreen((s) => (s.kind === "loading" ? { kind: "error", card: null, labels: null } : s));
      return;
    }
    const out = interpret(event.result);
    acceptLabels(out.labels);
    setActionError(false);
    setScreen(out.kind === "ready" ? { kind: "ready", envelope: out.envelope } : out);
  }, []);

  // Layout effect, not useEffect: Preact runs plain effects after the next
  // animation frame, and a host that mounts the iframe hidden (or a sandboxed
  // out-of-process frame) may not paint for a long while — the result must not
  // wait for a frame to be delivered.
  useLayoutEffect(() => bridge.subscribe(onEvent), [bridge, onEvent]);

  const envelope = screen.kind === "ready" ? screen.envelope : null;
  const locale =
    (envelope && envelope.locale) ||
    (screen.kind === "error" || screen.kind === "fallback" ? screen.locale : undefined) ||
    hostLocale ||
    "en";
  const dirHint = (envelope && envelope.dir) || (screen.kind === "error" || screen.kind === "fallback" ? screen.dir : undefined);
  const dir = dirHint === "rtl" || dirHint === "ltr" ? dirHint : RTL.test(locale) ? "rtl" : "ltr";

  useEffect(() => {
    try {
      document.documentElement.lang = locale;
      document.documentElement.dir = dir;
    } catch {
      /* ignore */
    }
  }, [locale, dir]);

  const rememberState = useCallback(
    (env: Envelope, zip: string | null) => {
      const d = env.data as PricesData | PharmaciesData;
      const pkg = (d && (d as PricesData).package) || {};
      const state: Record<string, unknown> = {
        view: env.view,
        slug: d && d.drug ? d.drug.slug : undefined,
        form: pkg.form,
        strength: pkg.strength,
        quantity: pkg.quantity,
      };
      if (zip) state.zip = zip; // only a ZIP the person typed; never coordinates
      bridge.setWidgetState(state);
    },
    [bridge],
  );

  const run = useCallback(
    async (name: string, args: Record<string, unknown>): Promise<boolean> => {
      const typedZip = typeof args.zip === "string" ? args.zip : null;
      setBusy(true);
      setActionError(false);
      try {
        const result: ToolResultLike = await bridge.callTool(name, args);
        const out = interpret(result);
        acceptLabels(out.labels);
        if (out.kind !== "ready") {
          setActionError(true);
          return false;
        }
        const zip = typedZip || userZip;
        if (typedZip) setUserZip(typedZip);
        setScreen({ kind: "ready", envelope: out.envelope });
        const note = modelNote(out.envelope);
        if (note) bridge.updateModelContext(note);
        rememberState(out.envelope, zip);
        return true;
      } catch {
        setActionError(true);
        return false;
      } finally {
        setBusy(false);
      }
    },
    [bridge, userZip, rememberState],
  );

  // ChatGPT re-mounts the card with the ORIGINAL tool output; widgetState keeps
  // what the person had picked since, so bring that package back once.
  useEffect(() => {
    if (restored.current || !envelope || envelope.view !== "prices") return;
    restored.current = true;
    const saved = bridge.widgetState();
    const d = envelope.data as PricesData;
    if (!saved || saved.view !== "prices" || saved.slug !== d.drug.slug) return;
    const pkg = d.package || {};
    const differs =
      (saved.quantity !== undefined && saved.quantity !== pkg.quantity) ||
      (saved.strength !== undefined && saved.strength !== pkg.strength) ||
      (saved.form !== undefined && saved.form !== pkg.form) ||
      typeof saved.zip === "string";
    if (!differs) return;
    const args: Record<string, unknown> = { slug: d.drug.slug };
    for (const k of ["form", "strength", "quantity", "zip"]) if (saved[k] !== undefined && saved[k] !== null) args[k] = saved[k];
    void run("ui_prices", args);
  }, [envelope, bridge, run]);

  const openCounter = useCallback(() => {
    setCounter(true);
    bridge.requestDisplayMode("fullscreen").then((mode) => {
      grantedFullscreen.current = mode === "fullscreen";
    });
  }, [bridge]);
  const closeCounter = useCallback(() => {
    setCounter(false);
    if (grantedFullscreen.current) {
      grantedFullscreen.current = false;
      void bridge.requestDisplayMode("inline");
    }
  }, [bridge]);

  const t = useMemo(() => makeT(labels), [labels]);
  const ctx: AppCtx = { t, locale, bridge, busy, userZip, run, openCounter };

  const card: CardView | null =
    screen.kind === "ready" ? screen.envelope.card || null : screen.kind === "error" || screen.kind === "fallback" ? screen.card : null;

  let body;
  if (counter) body = <Counter card={card} onClose={closeCounter} />;
  else if (screen.kind === "loading") body = <Loading args={screen.args} />;
  else if (screen.kind === "error") body = <ErrorState card={screen.card} />;
  else if (screen.kind === "fallback") body = <Fallback text={screen.text} card={screen.card} />;
  else if (screen.kind === "ready") {
    const env = screen.envelope;
    body =
      env.view === "prices" ? (
        <PricesView env={env} />
      ) : env.view === "pharmacies" ? (
        <PharmaciesView env={env} />
      ) : (
        <CardViewPage env={env} />
      );
  } else body = <Empty english={/^en\b/i.test(locale)} />;

  return (
    <Ctx.Provider value={ctx}>
      <div class={`fx${busy ? " busy" : ""}`} data-testid="app" dir={dir} lang={locale} aria-busy={busy}>
        {actionError && !counter && (
          <p class="notice err" role="alert">
            {t("actionError")}
          </p>
        )}
        {body}
      </div>
    </Ctx.Provider>
  );
}
