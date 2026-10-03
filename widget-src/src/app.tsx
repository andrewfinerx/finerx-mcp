// The router: one bundle, the view picked by structuredContent.view (C2, C2').
// State lives here — the current envelope, the views it replaced (for "Back"),
// labels, the in-flight flag, the ZIP the person typed, the display mode and
// the counter mode — and flows down through Ctx.

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import type { Bridge, BridgeEvent, DisplayMode, HostContext } from "./bridge";
import { Ctx, type AppCtx } from "./context";
import { makeT } from "./labels";
import { interpret, type Interpreted } from "./result";
import type { BasketData, CardView, Envelope, EquivalentData, Labels, Origin, PharmaciesData, PricesData, ToolResultLike } from "./types";
import { Counter } from "./components/Counter";
import { PricesView } from "./views/Prices";
import { PharmaciesView } from "./views/Pharmacies";
import { CardViewPage } from "./views/Card";
import { SearchView } from "./views/Search";
import { EquivalentView } from "./views/Equivalent";
import { RxView } from "./views/Rx";
import { BasketView } from "./views/Basket";
import { PackagesView } from "./views/Packages";
import { EquivalentsView } from "./views/Equivalents";
import { TransferView } from "./views/Transfer";
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
  } catch {
    /* keep prefers-color-scheme */
  }
}

/** City/state or ZIP — what the model may learn about a place; never an
 * address line (the API never echoes one, and neither do we). */
function placeNote(origin: Origin | null | undefined): string {
  const city = [origin?.city, origin?.state].filter(Boolean).join(", ");
  const place = city || (origin?.zip ? `ZIP ${origin.zip}` : "");
  if (!place || origin?.precision === "none") return "";
  return ` near ${place}${origin?.precision === "approx" ? " (approximate)" : ""}`;
}

/** "Person selected 90 × 1 mg tablet of Estradiol near Austin, TX …" — sent as
 * `ui/update-model-context` after every pick, so the next chat turn knows. */
export function modelNote(env: Envelope): string | null {
  if (env.view === "prices") {
    const d = env.data as PricesData;
    const p = d.package || {};
    const dose = [p.strength, p.form].filter(Boolean).join(" ");
    const pack = p.quantity ? `${p.quantity} × ${dose || d.drug.name}${dose ? ` of ${d.drug.name}` : ""}` : `${d.drug.name}${dose ? ` ${dose}` : ""}`;
    return `Person selected ${pack}${placeNote(d.origin)} in the FineRx card; it now shows card prices by pharmacy chain for that package.`;
  }
  if (env.view === "pharmacies") {
    const d = env.data as PharmaciesData;
    const what = d.drug?.name ? ` for ${d.drug.name}${d.package?.label ? ` (${d.package.label})` : ""}` : "";
    return `Person opened pharmacies${what}${placeNote(d.origin)} in the FineRx card.`;
  }
  if (env.view === "basket") {
    const d = (env.data || {}) as BasketData;
    const names = (d.items || []).map((it) => it.drug && it.drug.name).filter(Boolean);
    if (!names.length) return null;
    return `Person is looking at ${names.join(", ")} together${placeNote(d.origin)} in the FineRx card; it shows the sum of card prices per pharmacy chain.`;
  }
  if (env.view === "equivalent") {
    const d = (env.data || {}) as EquivalentData;
    if (!d.brand) return null;
    return `Person picked the foreign brand ${d.brand} in the FineRx card; it shows what that medicine is in the US.`;
  }
  return null;
}

/** The views a person can step BACK to from the one a pick replaced them with. */
const BACKABLE = new Set(["search", "equivalent", "rx", "prices", "basket", "packages", "equivalents", "transfer"]);

export function App({ bridge }: { bridge: Bridge }) {
  const [screen, setScreen] = useState<Screen>({ kind: "empty" });
  const [labels, setLabels] = useState<Labels | null>(null);
  const [hostLocale, setHostLocale] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(false);
  const [userZip, setUserZip] = useState<string | null>(null);
  const [counter, setCounter] = useState(false);
  const [history, setHistory] = useState<Envelope[]>([]);
  const [display, setDisplay] = useState<DisplayMode>(() => bridge.hostContext().displayMode || "inline");
  const grantedFullscreen = useRef(false);
  const restored = useRef(false);
  const current = useRef<Envelope | null>(null);
  const displayRef = useRef(display);
  displayRef.current = display;

  const acceptLabels = (next: Labels | null) => {
    if (next && Object.keys(next).length) setLabels(next);
  };

  const onEvent = useCallback((event: BridgeEvent) => {
    if (event.type === "host-context") {
      applyHostContext(event.context);
      if (typeof event.context.locale === "string") setHostLocale(event.context.locale);
      const mode = event.context.displayMode;
      if (mode === "inline" || mode === "fullscreen" || mode === "pip") setDisplay(mode);
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
    setHistory([]); // a new answer from the model starts a new trail
    setScreen(out.kind === "ready" ? { kind: "ready", envelope: out.envelope } : out);
  }, []);

  // Layout effect, not useEffect: Preact runs plain effects after the next
  // animation frame, and a host that mounts the iframe hidden (or a sandboxed
  // out-of-process frame) may not paint for a long while — the result must not
  // wait for a frame to be delivered.
  useLayoutEffect(() => bridge.subscribe(onEvent), [bridge, onEvent]);

  const envelope = screen.kind === "ready" ? screen.envelope : null;
  current.current = envelope;
  const readerLocale = envelope && envelope.data && (envelope.data as { readerLocale?: unknown }).readerLocale;
  const locale =
    (typeof readerLocale === "string" && readerLocale) ||
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
  useEffect(() => {
    try {
      document.documentElement.setAttribute("data-display", display);
    } catch {
      /* ignore */
    }
  }, [display]);

  const rememberState = useCallback(
    (env: Envelope, zip: string | null) => {
      if (env.view === "basket" || env.view === "packages" || env.view === "equivalents" || env.view === "transfer") return; // not one package to bring back
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
    async (name: string, args: Record<string, unknown>, opts?: { typed?: boolean }): Promise<boolean> => {
      // Only a ZIP the person TYPED is remembered (userZip, widgetState) — not
      // one named in the chat or resolved from an address. A typed address
      // (`where`) replaces any ZIP typed before, and is never kept itself.
      const typedZip = opts?.typed && typeof args.zip === "string" ? args.zip : null;
      const typedWhere = !!opts?.typed && typeof args.where === "string";
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
        const zip = typedZip || (typedWhere ? null : userZip);
        if (typedZip) setUserZip(typedZip);
        else if (typedWhere) setUserZip(null);
        const before = current.current;
        if (before && before.view !== out.envelope.view && BACKABLE.has(before.view)) {
          setHistory((h) => [...h, before].slice(-4));
        }
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
    // A saved ZIP was typed by the person (widgetState keeps no other).
    void run("ui_prices", args, { typed: typeof saved.zip === "string" });
  }, [envelope, bridge, run]);

  const goFullscreen = useCallback(async (): Promise<"already" | "granted" | "refused"> => {
    if (displayRef.current === "fullscreen") return "already";
    const mode = await bridge.requestDisplayMode("fullscreen");
    if (mode) setDisplay(mode);
    return mode === "fullscreen" ? "granted" : "refused";
  }, [bridge]);
  const goInline = useCallback(() => {
    setDisplay("inline");
    void bridge.requestDisplayMode("inline");
  }, [bridge]);
  const back = () => {
    const prev = history[history.length - 1];
    if (!prev) return;
    setHistory(history.slice(0, -1));
    setActionError(false);
    setScreen({ kind: "ready", envelope: prev });
  };

  const openCounter = useCallback(() => {
    setCounter(true);
    // Already fullscreen (search, the map): nothing to ask, nothing to undo.
    goFullscreen().then((got) => {
      grantedFullscreen.current = got === "granted";
    });
  }, [goFullscreen]);
  const closeCounter = useCallback(() => {
    setCounter(false);
    if (grantedFullscreen.current) {
      grantedFullscreen.current = false;
      goInline();
    }
  }, [goInline]);

  const t = useMemo(() => makeT(labels), [labels]);
  const ctx: AppCtx = { t, locale, bridge, busy, userZip, run, openCounter, display, goFullscreen, goInline };

  const card: CardView | null =
    screen.kind === "ready" ? screen.envelope.card || null : screen.kind === "error" || screen.kind === "fallback" ? screen.card : null;

  let body;
  if (counter) body = <Counter card={card} onClose={closeCounter} />;
  else if (screen.kind === "loading") body = <Loading args={screen.args} />;
  else if (screen.kind === "error") body = <ErrorState card={screen.card} />;
  else if (screen.kind === "fallback") body = <Fallback text={screen.text} card={screen.card} />;
  else if (screen.kind === "ready") {
    const env = screen.envelope;
    const View =
      env.view === "prices"
        ? PricesView
        : env.view === "pharmacies"
          ? PharmaciesView
          : env.view === "search"
            ? SearchView
            : env.view === "equivalent"
              ? EquivalentView
              : env.view === "rx"
                ? RxView
                : env.view === "basket"
                  ? BasketView
                  : env.view === "packages"
                    ? PackagesView
                    : env.view === "equivalents"
                      ? EquivalentsView
                      : env.view === "transfer"
                        ? TransferView
                        : CardViewPage;
    body = <View env={env} />;
  } else body = <Empty english={/^en\b/i.test(locale)} />;

  return (
    <Ctx.Provider value={ctx}>
      <div class={`fx${busy ? " busy" : ""}`} data-testid="app" dir={dir} lang={locale} aria-busy={busy}>
        {actionError && !counter && (
          <p class="notice err" role="alert">
            {t("actionError")}
          </p>
        )}
        {history.length > 0 && !counter && screen.kind === "ready" && (
          <button type="button" class="link back" data-testid="back" onClick={back}>
            <span class="arr" aria-hidden="true">
              ←
            </span>{" "}
            {history[history.length - 1].view === "search" ? t("backToSearch") : t("back")}
          </button>
        )}
        {body}
      </div>
    </Ctx.Provider>
  );
}
