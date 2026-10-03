// A tool result → what to draw. Pure, so the router is testable without a DOM.

import type { CardView, Envelope, Labels, ToolResultLike, ViewName } from "./types";

export const KNOWN_VIEWS: ReadonlySet<string> = new Set<ViewName>([
  "prices",
  "pharmacies",
  "card",
  "search",
  "equivalent",
  "rx",
  "basket",
  "packages",
  "equivalents",
  "transfer",
]);

export type Interpreted =
  | { kind: "ready"; envelope: Envelope; labels: Labels | null }
  /** Unknown view / missing data: the model-facing text + the card. */
  | { kind: "fallback"; text: string; card: CardView | null; locale?: string; dir?: string; labels: Labels | null }
  /** isError or an `error` block: "prices didn't load" + the card. */
  | { kind: "error"; card: CardView | null; locale?: string; dir?: string; labels: Labels | null };

const isObject = (v: unknown): v is Record<string, any> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

export function labelsOf(result: ToolResultLike | null | undefined): Labels | null {
  const meta = (result && (result._meta || result.meta)) || null;
  const raw = isObject(meta) ? meta["finerx/labels"] : null;
  if (!isObject(raw)) return null;
  const out: Labels = {};
  for (const [k, v] of Object.entries(raw)) if (typeof v === "string") out[k] = v;
  return out;
}

export function textOf(result: ToolResultLike | null | undefined): string {
  const blocks = result && Array.isArray(result.content) ? result.content : [];
  return blocks
    .filter((b: any) => isObject(b) && b.type === "text" && typeof b.text === "string")
    .map((b: any) => b.text as string)
    .join("\n\n")
    .trim();
}

function hasViewData(env: Envelope): boolean {
  const d = env.data;
  if (!isObject(d)) return false;
  if (env.view === "prices") return isObject(d.drug) && typeof d.drug.slug === "string";
  if (env.view === "equivalents") return Array.isArray(d.items) && d.items.some((it: any) => isObject(it) && (it.brand || it.inn));
  if (env.view === "packages") return isObject(d.drug) && typeof d.drug.slug === "string";
  if (env.view === "basket") return Array.isArray(d.items) && d.items.some((it: any) => isObject(it) && isObject(it.drug) && typeof it.drug.slug === "string");
  return true; // pharmacies / card / search / equivalent / rx draw from partial data
}

export function interpret(result: ToolResultLike | null | undefined): Interpreted {
  const labels = labelsOf(result);
  const sc = result && isObject(result.structuredContent) ? (result.structuredContent as Record<string, any>) : null;
  const card = sc && isObject(sc.card) ? (sc.card as CardView) : null;
  const locale = sc && typeof sc.locale === "string" ? sc.locale : undefined;
  const dir = sc && typeof sc.dir === "string" ? sc.dir : undefined;

  if (!result || result.isError || (sc && sc.error)) return { kind: "error", card, locale, dir, labels };
  const isEnvelope = !!sc && typeof sc.schema === "string" && sc.schema.startsWith("finerx.view/") && typeof sc.view === "string";
  if (!isEnvelope) {
    const text = textOf(result);
    return text ? { kind: "fallback", text, card, locale, dir, labels } : { kind: "error", card, locale, dir, labels };
  }
  const env = sc as unknown as Envelope;
  if (!KNOWN_VIEWS.has(env.view) || !hasViewData(env)) {
    return { kind: "fallback", text: textOf(result), card, locale, dir, labels };
  }
  return { kind: "ready", envelope: env, labels };
}

/** Drop undefined / null / "" so a tool never receives an empty argument. */
export function cleanArgs(args: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(args)) if (v !== undefined && v !== null && v !== "") out[k] = v;
  return out;
}
