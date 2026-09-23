// The `finerx.view/2` envelope (contract C2) as the widget reads it. Hand-kept
// for phase 1; phase 2 replaces it with types.gen.ts exported from the MCP's
// Pydantic schemas. Every field is treated as optional at runtime — the widget
// must draw something sane from a partial or older payload.

export interface Price {
  amount: number;
  /** ISO date (YYYY-MM-DD) the price was observed. Never shown without it. */
  observedAt: string;
}

export interface Codes {
  bin: string;
  pcn: string;
  group: string;
}

export interface PriceWithCard extends Price {
  family?: string;
  name?: string;
}

/** CARD from the API + `actions` added by the MCP (CARD_VIEW). */
export interface CardView {
  codes?: Partial<Codes>;
  priceWithCard?: PriceWithCard | null;
  /** The card law, already localized with {price}/{date} filled in. Shown verbatim. */
  law?: string;
  /** The small print line ("Not insurance · prices observed … · …"). Shown verbatim. */
  fine?: string;
  chainsCount?: number;
  siteUrl?: string;
  printUrl?: string;
  actions?: { smsBody?: string; emailEnabled?: boolean };
}

export interface Drug {
  slug: string;
  name: string;
  kind?: string;
}

export interface Package {
  form?: string;
  strength?: string;
  quantity?: number;
  label?: string;
}

export interface QuantityOption {
  quantity: number;
  label?: string;
  cardFrom?: Price | null;
  chainsPriced?: number;
}

export interface ConfigOption {
  form: string;
  strength: string;
  label?: string;
  quantities?: QuantityOption[];
}

export interface Origin {
  zip?: string | null;
  city?: string | null;
  state?: string | null;
  precision?: "zip" | "approx" | "none";
}

export interface Coverage {
  status?: "exact" | "other_quantities" | "none";
  quantities?: number[];
}

export interface PriceRow {
  family: string;
  name: string;
  price?: Price | null;
  zone?: string | null;
  nearestMiles?: number | null;
  storeCount?: number;
}

export interface PricesData {
  drug: Drug;
  package?: Package;
  options?: { configs?: ConfigOption[] } | null;
  origin?: Origin;
  rows?: PriceRow[];
  pricesWithoutStores?: PriceRow[];
  moreCount?: number;
  needsZip?: boolean;
  coverage?: Coverage;
}

export interface Store {
  family: string;
  name: string;
  address?: string;
  city?: string;
  miles?: number | null;
  lat?: number | null;
  lon?: number | null;
  kind?: "pharmacy" | "store";
  price?: Price | null;
}

export interface PharmaciesData {
  drug?: Drug | null;
  package?: Package | null;
  origin?: Origin;
  stores?: Store[];
  families?: string[];
}

export interface CardData {
  drug?: Drug | null;
  priceWithCard?: PriceWithCard | null;
}

export type ViewName = "prices" | "pharmacies" | "card";

export interface Envelope {
  schema: string;
  view: string;
  locale?: string;
  dir?: "ltr" | "rtl";
  data?: unknown;
  card?: CardView | null;
  error?: { code?: string } | null;
}

/** A CallToolResult (MCP) or the shape window.openai.callTool resolves with. */
export interface ToolResultLike {
  content?: unknown;
  structuredContent?: unknown;
  _meta?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
  isError?: boolean;
}

export type Labels = Record<string, string>;
