import { createContext } from "preact";
import { useContext } from "preact/hooks";
import type { Bridge } from "./bridge";
import { makeT, type T } from "./labels";

export interface AppCtx {
  t: T;
  locale: string;
  bridge: Bridge;
  /** A widget-initiated tool call is in flight. */
  busy: boolean;
  /** The ZIP the person typed in the widget (never one we derived). */
  userZip: string | null;
  /** Call an app-only tool and draw its result; false when it did not load. */
  run(name: string, args: Record<string, unknown>): Promise<boolean>;
  openCounter(): void;
}

export const Ctx = createContext<AppCtx>({
  t: makeT(null),
  locale: "en",
  bridge: null as unknown as Bridge,
  busy: false,
  userZip: null,
  run: async () => false,
  openCounter: () => {},
});

export const useApp = () => useContext(Ctx);
