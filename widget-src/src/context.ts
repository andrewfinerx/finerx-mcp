import { createContext } from "preact";
import { useContext } from "preact/hooks";
import type { Bridge, DisplayMode } from "./bridge";
import { makeT, type T } from "./labels";

export interface AppCtx {
  t: T;
  locale: string;
  bridge: Bridge;
  /** A widget-initiated tool call is in flight. */
  busy: boolean;
  /** The ZIP the person typed in the widget (never one we derived). */
  userZip: string | null;
  /** Call an app-only tool and draw its result; false when it did not load.
   * `typed`: the place in `args` (zip / where) is what the person just typed. */
  run(name: string, args: Record<string, unknown>, opts?: { typed?: boolean }): Promise<boolean>;
  openCounter(): void;
  /** The mode the host shows us in (host context, or what it granted). */
  display: DisplayMode;
  /** Ask the host for fullscreen: "already" (nothing asked), "granted" (the
   * caller switched it and may switch back) or "refused" (stay inline). */
  goFullscreen(): Promise<"already" | "granted" | "refused">;
  /** Back to inline; call it only after a "granted" of your own. */
  goInline(): void;
}

export const Ctx = createContext<AppCtx>({
  t: makeT(null),
  locale: "en",
  bridge: null as unknown as Bridge,
  busy: false,
  userZip: null,
  run: async () => false,
  openCounter: () => {},
  display: "inline",
  goFullscreen: async () => "refused",
  goInline: () => {},
});

export const useApp = () => useContext(Ctx);
