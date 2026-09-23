import { describe, expect, it, vi } from "vitest";
import { createBridge, PROTOCOL_VERSION, type BridgeEvent, type BridgeWindow } from "../src/bridge";

/** A fake window whose parent records what we post and can answer. */
function fakeWindow(openai?: Record<string, unknown>) {
  const handlers: Record<string, Array<(e: any) => void>> = {};
  const posted: any[] = [];
  const parent = { postMessage: vi.fn((m: unknown) => posted.push(m)) };
  const win: BridgeWindow & { fire(type: string, event: any): void } = {
    parent,
    addEventListener: (type, fn) => {
      (handlers[type] ||= []).push(fn);
    },
    openai: openai as any,
    fire(type, event) {
      (handlers[type] || []).forEach((fn) => fn(event));
    },
  };
  const fromHost = (data: unknown) => win.fire("message", { data, source: parent });
  return { win, posted, parent, fromHost };
}

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("MCP Apps bridge (postMessage)", () => {
  it("sends ui/initialize with the 2026-01-26 protocol, then initialized after the answer", async () => {
    const { win, posted, fromHost } = fakeWindow();
    const bridge = createBridge(win);
    bridge.start();
    const init = posted[0];
    expect(init).toMatchObject({
      jsonrpc: "2.0",
      method: "ui/initialize",
      params: { protocolVersion: PROTOCOL_VERSION, appInfo: { name: "finerx-app" } },
    });
    expect(PROTOCOL_VERSION).toBe("2026-01-26");
    fromHost({ jsonrpc: "2.0", id: init.id, result: { protocolVersion: PROTOCOL_VERSION, hostContext: { theme: "dark", locale: "es" } } });
    await tick();
    expect(posted[1]).toMatchObject({ method: "ui/notifications/initialized" });
    expect(bridge.hostContext()).toMatchObject({ theme: "dark", locale: "es" });
  });

  it("delivers tool-input / tool-result / host-context-changed, and replays the latest to a late subscriber", () => {
    const { win, fromHost } = fakeWindow();
    const bridge = createBridge(win);
    bridge.start();
    fromHost({ jsonrpc: "2.0", method: "ui/notifications/tool-input", params: { arguments: { drug: "x" } } });
    fromHost({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: { structuredContent: { a: 1 } } });
    fromHost({ jsonrpc: "2.0", method: "ui/notifications/host-context-changed", params: { theme: "light" } });
    const seen: BridgeEvent[] = [];
    bridge.subscribe((e) => seen.push(e));
    expect(seen.map((e) => e.type)).toEqual(["host-context", "tool-result"]);
    expect((seen[1] as any).result.structuredContent).toEqual({ a: 1 });
  });

  it("ignores messages that do not come from the parent frame", () => {
    const { win } = fakeWindow();
    const bridge = createBridge(win);
    bridge.start();
    const seen: BridgeEvent[] = [];
    bridge.subscribe((e) => seen.push(e));
    win.fire("message", { data: { jsonrpc: "2.0", method: "ui/notifications/tool-result", params: {} }, source: {} });
    expect(seen).toHaveLength(0);
  });

  it("tools/call, open-link, request-display-mode and update-model-context go over JSON-RPC", async () => {
    const { win, posted, fromHost } = fakeWindow();
    const bridge = createBridge(win);
    bridge.start();
    fromHost({ jsonrpc: "2.0", id: posted[0].id, result: {} }); // initialize answered
    await tick();

    const call = bridge.callTool("ui_prices", { slug: "estradiol", quantity: 90 });
    const req = posted.find((m) => m.method === "tools/call");
    expect(req.params).toEqual({ name: "ui_prices", arguments: { slug: "estradiol", quantity: 90 } });
    fromHost({ jsonrpc: "2.0", id: req.id, result: { structuredContent: { ok: true } } });
    await expect(call).resolves.toEqual({ structuredContent: { ok: true } });

    const link = bridge.openLink("https://example.org/x");
    const linkReq = posted.find((m) => m.method === "ui/open-link");
    expect(linkReq.params).toEqual({ url: "https://example.org/x" });
    fromHost({ jsonrpc: "2.0", id: linkReq.id, result: {} });
    await expect(link).resolves.toBe(true);

    const mode = bridge.requestDisplayMode("fullscreen");
    const modeReq = posted.find((m) => m.method === "ui/request-display-mode");
    expect(modeReq.params).toEqual({ mode: "fullscreen" });
    fromHost({ jsonrpc: "2.0", id: modeReq.id, result: { mode: "inline" } });
    await expect(mode).resolves.toBe("inline"); // the host decides

    bridge.updateModelContext("picked 90");
    expect(posted.find((m) => m.method === "ui/update-model-context").params).toEqual({
      content: [{ type: "text", text: "picked 90" }],
    });
  });

  it("answers ping and resource-teardown, rejects unknown requests", () => {
    const { win, posted, fromHost } = fakeWindow();
    createBridge(win).start();
    fromHost({ jsonrpc: "2.0", id: 77, method: "ping" });
    fromHost({ jsonrpc: "2.0", id: 78, method: "ui/resource-teardown", params: { reason: "x" } });
    fromHost({ jsonrpc: "2.0", id: 79, method: "something/new" });
    expect(posted).toContainEqual({ jsonrpc: "2.0", id: 77, result: {} });
    expect(posted).toContainEqual({ jsonrpc: "2.0", id: 78, result: {} });
    expect(posted.find((m) => m.id === 79).error.code).toBe(-32601);
  });

  it("does not ask for a display mode the host said it lacks", async () => {
    const { win, posted, fromHost } = fakeWindow();
    const bridge = createBridge(win);
    bridge.start();
    fromHost({ jsonrpc: "2.0", id: posted[0].id, result: { hostContext: { availableDisplayModes: ["inline"] } } });
    await tick();
    await expect(bridge.requestDisplayMode("fullscreen")).resolves.toBeNull();
    expect(posted.some((m) => m.method === "ui/request-display-mode")).toBe(false);
  });
});

describe("window.openai adapter (ChatGPT)", () => {
  it("reads toolOutput + toolResponseMetadata, and uses callTool/requestDisplayMode/openExternal/widgetState until the standard answers", async () => {
    const openai = {
      toolOutput: { schema: "finerx.view/2", view: "card" },
      toolResponseMetadata: { "finerx/labels": { copy: "Copiar" } },
      theme: "dark",
      widgetState: { slug: "estradiol" },
      callTool: vi.fn(async () => ({ structuredContent: { ok: 1 } })),
      requestDisplayMode: vi.fn(async ({ mode }: { mode: string }) => ({ mode })),
      openExternal: vi.fn(),
      setWidgetState: vi.fn(),
      notifyIntrinsicHeight: vi.fn(),
    };
    const { win } = fakeWindow(openai);
    const bridge = createBridge(win);
    bridge.start();
    const seen: BridgeEvent[] = [];
    bridge.subscribe((e) => seen.push(e));
    const result = seen.find((e) => e.type === "tool-result") as any;
    expect(result.result).toEqual({ structuredContent: openai.toolOutput, _meta: openai.toolResponseMetadata });
    expect(bridge.hostContext().theme).toBe("dark");

    await expect(bridge.callTool("ui_prices", { slug: "s" })).resolves.toEqual({ structuredContent: { ok: 1 } });
    expect(openai.callTool).toHaveBeenCalledWith("ui_prices", { slug: "s" });
    await expect(bridge.requestDisplayMode("fullscreen")).resolves.toBe("fullscreen");
    await bridge.openLink("https://example.org/");
    expect(openai.openExternal).toHaveBeenCalledWith({ href: "https://example.org/" });
    expect(bridge.widgetState()).toEqual({ slug: "estradiol" });
    bridge.setWidgetState({ slug: "x" });
    expect(openai.setWidgetState).toHaveBeenCalledWith({ slug: "x" });
    bridge.notifySize(300, 420);
    expect(openai.notifyIntrinsicHeight).toHaveBeenCalledWith(420);
  });

  it("set_globals re-emits only a NEW toolOutput (our own setWidgetState must not undo a pick)", () => {
    const openai: Record<string, unknown> = { toolOutput: { a: 1 } };
    const { win } = fakeWindow(openai);
    const bridge = createBridge(win);
    bridge.start();
    const seen: BridgeEvent[] = [];
    bridge.subscribe((e) => seen.push(e));
    seen.length = 0;
    win.fire("openai:set_globals", {});
    expect(seen.filter((e) => e.type === "tool-result")).toHaveLength(0);
    openai.toolOutput = { a: 2 };
    win.fire("openai:set_globals", {});
    expect(seen.filter((e) => e.type === "tool-result")).toHaveLength(1);
  });
});

describe("no host at all", () => {
  it("never throws: calls reject or resolve null/false, links fall back to window.open", async () => {
    const open = vi.fn();
    const win: BridgeWindow = { parent: null, addEventListener: () => {}, open };
    const bridge = createBridge(win);
    expect(() => bridge.start()).not.toThrow();
    expect(bridge.canCallTools()).toBe(false);
    await expect(bridge.callTool("x", {})).rejects.toThrow();
    await expect(bridge.requestDisplayMode("fullscreen")).resolves.toBeNull();
    await expect(bridge.openLink("https://example.org/")).resolves.toBe(true);
    expect(open).toHaveBeenCalledWith("https://example.org/", "_blank", "noopener");
    expect(() => bridge.updateModelContext("x")).not.toThrow();
    expect(() => bridge.notifySize(1, 1)).not.toThrow();
  });
});
