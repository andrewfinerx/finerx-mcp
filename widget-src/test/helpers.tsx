import { render, act } from "@testing-library/preact";
import { vi } from "vitest";
import { App } from "../src/app";
import type { Bridge, BridgeEvent, HostContext } from "../src/bridge";
import type { ToolResultLike } from "../src/types";

export const FIXTURE_NAMES = [
  "prices-exact",
  "prices-other-quantities",
  "prices-needs-zip",
  "prices-rtl-ar",
  "pharmacies",
  "card",
  "error",
] as const;

const files = import.meta.glob("../fixtures/*.json", { eager: true, import: "default" }) as Record<string, ToolResultLike>;

export function fixture(name: string): ToolResultLike {
  const got = files[`../fixtures/${name}.json`];
  if (!got) throw new Error(`no fixture ${name}`);
  return JSON.parse(JSON.stringify(got));
}

export type MockBridge = Bridge & {
  push(event: BridgeEvent): void;
  callTool: ReturnType<typeof vi.fn>;
  openLink: ReturnType<typeof vi.fn>;
  requestDisplayMode: ReturnType<typeof vi.fn>;
  updateModelContext: ReturnType<typeof vi.fn>;
  setWidgetState: ReturnType<typeof vi.fn>;
};

/** A bridge that records every call; tool calls answer with `reply` (or a fixture). */
export function mockBridge(opts: { reply?: (name: string, args: any) => ToolResultLike; widgetState?: Record<string, unknown> | null } = {}): MockBridge {
  const listeners = new Set<(e: BridgeEvent) => void>();
  let ctx: HostContext = {};
  const bridge = {
    start: vi.fn(),
    subscribe(listener: (e: BridgeEvent) => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    hostContext: () => ctx,
    canCallTools: () => true,
    callTool: vi.fn(async (name: string, args: any) => (opts.reply ? opts.reply(name, args) : fixture(name === "ui_nearby" ? "pharmacies" : "prices-exact"))),
    openLink: vi.fn(async () => true),
    requestDisplayMode: vi.fn(async (mode: string) => mode),
    updateModelContext: vi.fn(),
    widgetState: () => opts.widgetState ?? null,
    setWidgetState: vi.fn(),
    notifySize: vi.fn(),
    push(event: BridgeEvent) {
      if (event.type === "host-context") ctx = { ...ctx, ...event.context };
      listeners.forEach((l) => l(event));
    },
  };
  return bridge as unknown as MockBridge;
}

/** Render the App and deliver `result` the way a host does (tool-result). */
export async function renderWith(result: ToolResultLike | null, bridge = mockBridge()) {
  const utils = render(<App bridge={bridge} />);
  if (result) {
    await act(() => {
      bridge.push({ type: "tool-result", result });
    });
  }
  return { ...utils, bridge };
}

/** Let pending promises (tool calls) settle inside act(). */
export async function flush() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}
