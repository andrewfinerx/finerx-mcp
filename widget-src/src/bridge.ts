// The host bridge. TWO protocols, both optional, detected at runtime:
//   1. the MCP Apps standard (spec 2026-01-26): JSON-RPC 2.0 over postMessage
//      with the parent frame — Claude, ChatGPT, VS Code, Goose, …;
//   2. the ChatGPT Apps SDK globals on `window.openai` — an ADAPTER, used for
//      what the standard has no word for (widgetState) and as the fallback
//      transport when the standard handshake has not answered.
// The standard goes first (host rule 9). Nothing here may throw into the UI: a
// host that speaks neither protocol still gets a drawn card and three codes.

import type { ToolResultLike } from "./types";

export const PROTOCOL_VERSION = "2026-01-26";
export const APP_INFO = { name: "finerx-app", version: "2.0.0" };
const REQUEST_TIMEOUT_MS = 30_000;

export type DisplayMode = "inline" | "fullscreen" | "pip";

export interface HostContext {
  theme?: string;
  locale?: string;
  displayMode?: DisplayMode;
  availableDisplayModes?: DisplayMode[];
  styles?: { variables?: Record<string, string | undefined> };
  [key: string]: unknown;
}

export type BridgeEvent =
  | { type: "tool-input"; args: Record<string, unknown> }
  | { type: "tool-result"; result: ToolResultLike }
  | { type: "tool-cancelled" }
  | { type: "host-context"; context: HostContext };

export interface Bridge {
  /** Attach listeners and send ui/initialize. Idempotent. */
  start(): void;
  /** Receive events; the latest input/result/context are replayed at once. */
  subscribe(listener: (event: BridgeEvent) => void): () => void;
  hostContext(): HostContext;
  canCallTools(): boolean;
  callTool(name: string, args: Record<string, unknown>): Promise<ToolResultLike>;
  /** Resolves true when some host (or the browser) took the link. */
  openLink(url: string): Promise<boolean>;
  /** Resolves with the mode the host actually granted, or null. */
  requestDisplayMode(mode: DisplayMode): Promise<DisplayMode | null>;
  /** Tell the model what the person picked (replaces the previous context). */
  updateModelContext(text: string, structured?: Record<string, unknown>): void;
  widgetState(): Record<string, unknown> | null;
  setWidgetState(state: Record<string, unknown>): void;
  notifySize(width: number, height: number): void;
}

interface OpenAiGlobals {
  toolInput?: Record<string, unknown> | null;
  toolOutput?: unknown;
  toolResponseMetadata?: Record<string, unknown> | null;
  widgetState?: Record<string, unknown> | null;
  theme?: string;
  locale?: string;
  displayMode?: DisplayMode;
  callTool?: (name: string, args: Record<string, unknown>) => Promise<unknown>;
  setWidgetState?: (state: Record<string, unknown>) => unknown;
  requestDisplayMode?: (args: { mode: DisplayMode }) => Promise<{ mode?: DisplayMode } | undefined>;
  openExternal?: (args: { href: string }) => unknown;
  notifyIntrinsicHeight?: (height: number) => unknown;
}

/** The slice of `window` the bridge touches — a fake one in tests. */
export interface BridgeWindow {
  parent: { postMessage(message: unknown, target: string): void } | null;
  addEventListener(type: string, listener: (event: any) => void): void;
  open?: (url: string, target?: string, features?: string) => unknown;
  openai?: OpenAiGlobals;
}

interface Waiter {
  resolve(value: any): void;
  reject(error: unknown): void;
  timer: ReturnType<typeof setTimeout>;
}

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

export function createBridge(win: BridgeWindow = window as unknown as BridgeWindow): Bridge {
  const pending = new Map<number, Waiter>();
  const listeners = new Set<(event: BridgeEvent) => void>();
  let nextId = 1;
  let started = false;
  let mcpReady = false; // ui/initialize answered: the standard channel is live
  let context: HostContext = {};
  let lastInput: Record<string, unknown> | null = null;
  let lastResult: ToolResultLike | null = null;
  // set_globals fires for ANY global (theme, our own setWidgetState, …); only a
  // new toolOutput object is a new result — re-emitting the old one would undo
  // whatever the person picked in the widget since.
  let seenOpenAiOutput: unknown = null;
  let seenOpenAiInput: unknown = null;

  function hosted(): boolean {
    try {
      return !!win.parent && (win.parent as unknown) !== (win as unknown);
    } catch {
      return false;
    }
  }
  function sdk(): OpenAiGlobals | null {
    try {
      return isObject(win.openai) ? (win.openai as OpenAiGlobals) : null;
    } catch {
      return null;
    }
  }
  /** Standard channel when it answered, or when there is no Apps SDK to try. */
  function useMcp(): boolean {
    return mcpReady || (hosted() && !sdk());
  }

  function post(message: unknown): void {
    try {
      win.parent?.postMessage(message, "*");
    } catch {
      /* no host */
    }
  }
  function notify(method: string, params: Record<string, unknown> = {}): void {
    if (hosted()) post({ jsonrpc: "2.0", method, params });
  }
  function request<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      if (!hosted()) {
        reject(new Error("no host"));
        return;
      }
      const id = nextId++;
      const timer = setTimeout(() => {
        if (pending.delete(id)) reject(new Error("timeout"));
      }, REQUEST_TIMEOUT_MS);
      pending.set(id, { resolve, reject, timer });
      post({ jsonrpc: "2.0", id, method, params });
    });
  }

  function emit(event: BridgeEvent): void {
    if (event.type === "tool-input") lastInput = event.args;
    if (event.type === "tool-result") lastResult = event.result;
    listeners.forEach((listener) => {
      try {
        listener(event);
      } catch {
        /* a render bug must not kill the bridge */
      }
    });
  }
  function mergeContext(partial: unknown): void {
    if (!isObject(partial)) return;
    context = { ...context, ...(partial as HostContext) };
    emit({ type: "host-context", context });
  }

  function onMessage(event: MessageEvent): void {
    // Only the frame that embeds us may talk to us.
    if (win.parent && event.source && (event.source as unknown) !== (win.parent as unknown)) return;
    const msg = event.data;
    if (!isObject(msg) || msg.jsonrpc !== "2.0") return;
    const hasId = msg.id !== undefined && msg.id !== null;
    if (hasId && ("result" in msg || "error" in msg)) {
      const waiter = pending.get(msg.id as number);
      if (!waiter) return;
      pending.delete(msg.id as number);
      clearTimeout(waiter.timer);
      if (msg.error) waiter.reject(msg.error);
      else waiter.resolve(msg.result);
      return;
    }
    const params = isObject(msg.params) ? msg.params : {};
    switch (msg.method) {
      case "ping":
      case "ui/resource-teardown":
        if (hasId) post({ jsonrpc: "2.0", id: msg.id, result: {} });
        return;
      case "ui/notifications/tool-input":
        emit({ type: "tool-input", args: isObject(params.arguments) ? params.arguments : {} });
        return;
      case "ui/notifications/tool-result":
        emit({ type: "tool-result", result: params as ToolResultLike });
        return;
      case "ui/notifications/tool-cancelled":
        emit({ type: "tool-cancelled" });
        return;
      case "ui/notifications/host-context-changed":
        // Spec: params ARE the partial context; older hosts wrapped it.
        mergeContext(isObject(params.hostContext) ? params.hostContext : params);
        return;
      default:
        // tool-input-partial, sandbox-*, anything newer: ignored.
        if (hasId) post({ jsonrpc: "2.0", id: msg.id, error: { code: -32601, message: "Method not found" } });
    }
  }

  /** Apps SDK globals → the same events the standard pushes. */
  function readOpenAi(): void {
    const g = sdk();
    if (!g) return;
    try {
      const partial: HostContext = {};
      if (typeof g.theme === "string") partial.theme = g.theme;
      if (typeof g.locale === "string") partial.locale = g.locale;
      if (typeof g.displayMode === "string") partial.displayMode = g.displayMode;
      if (Object.keys(partial).length) mergeContext(partial);
      if (isObject(g.toolInput) && g.toolInput !== seenOpenAiInput && !lastResult) {
        seenOpenAiInput = g.toolInput;
        emit({ type: "tool-input", args: g.toolInput });
      }
      if (isObject(g.toolOutput) && g.toolOutput !== seenOpenAiOutput) {
        seenOpenAiOutput = g.toolOutput;
        emit({
          type: "tool-result",
          result: { structuredContent: g.toolOutput, _meta: g.toolResponseMetadata ?? null },
        });
      }
    } catch {
      /* ignore */
    }
  }

  const bridge: Bridge = {
    start() {
      if (started) return;
      started = true;
      try {
        win.addEventListener("message", onMessage);
      } catch {
        /* ignore */
      }
      if (sdk()) {
        readOpenAi();
        try {
          win.addEventListener("openai:set_globals", () => readOpenAi());
        } catch {
          /* ignore */
        }
      }
      request<{ hostContext?: HostContext }>("ui/initialize", {
        protocolVersion: PROTOCOL_VERSION,
        appInfo: APP_INFO,
        appCapabilities: { availableDisplayModes: ["inline", "fullscreen"] },
      }).then(
        (result) => {
          mcpReady = true;
          if (isObject(result) && isObject(result.hostContext)) mergeContext(result.hostContext);
          notify("ui/notifications/initialized");
        },
        () => {
          /* no MCP Apps host here */
        },
      );
    },

    subscribe(listener) {
      listeners.add(listener);
      try {
        if (Object.keys(context).length) listener({ type: "host-context", context });
        if (lastResult) listener({ type: "tool-result", result: lastResult });
        else if (lastInput) listener({ type: "tool-input", args: lastInput });
      } catch {
        /* ignore */
      }
      return () => listeners.delete(listener);
    },

    hostContext: () => context,

    canCallTools() {
      return useMcp() || typeof sdk()?.callTool === "function";
    },

    async callTool(name, args) {
      const g = sdk();
      if (!useMcp() && g && typeof g.callTool === "function") {
        const out = await g.callTool(name, args);
        return (isObject(out) ? out : {}) as ToolResultLike;
      }
      const out = await request<ToolResultLike>("tools/call", { name, arguments: args });
      return (isObject(out) ? out : {}) as ToolResultLike;
    },

    async openLink(url) {
      if (!url) return false;
      const g = sdk();
      if (useMcp()) {
        try {
          const out = await request<{ isError?: boolean }>("ui/open-link", { url });
          if (!(isObject(out) && out.isError)) return true;
        } catch {
          /* refused: try the next way */
        }
      }
      if (g && typeof g.openExternal === "function") {
        try {
          g.openExternal({ href: url });
          return true;
        } catch {
          /* fall through */
        }
      }
      if (!hosted() && typeof win.open === "function") {
        try {
          win.open(url, "_blank", "noopener");
          return true;
        } catch {
          /* nothing left */
        }
      }
      return false;
    },

    async requestDisplayMode(mode) {
      const available = context.availableDisplayModes;
      if (Array.isArray(available) && available.length && !available.includes(mode)) return null;
      try {
        if (useMcp()) {
          const out = await request<{ mode?: DisplayMode }>("ui/request-display-mode", { mode });
          return (isObject(out) && typeof out.mode === "string" ? out.mode : null) as DisplayMode | null;
        }
        const g = sdk();
        if (g && typeof g.requestDisplayMode === "function") {
          const out = await g.requestDisplayMode({ mode });
          return (isObject(out) && typeof out.mode === "string" ? out.mode : mode) as DisplayMode;
        }
      } catch {
        /* host said no */
      }
      return null;
    },

    updateModelContext(text, structured) {
      if (!useMcp()) return; // ChatGPT reads widgetState instead
      const params: Record<string, unknown> = { content: [{ type: "text", text }] };
      if (structured) params.structuredContent = structured;
      request("ui/update-model-context", params).catch(() => {
        /* optional */
      });
    },

    widgetState() {
      try {
        const state = sdk()?.widgetState;
        return isObject(state) ? state : null;
      } catch {
        return null;
      }
    },

    setWidgetState(state) {
      try {
        sdk()?.setWidgetState?.(state);
      } catch {
        /* optional */
      }
    },

    notifySize(width, height) {
      notify("ui/notifications/size-changed", { width, height });
      try {
        sdk()?.notifyIntrinsicHeight?.(height);
      } catch {
        /* optional */
      }
    },
  };
  return bridge;
}
