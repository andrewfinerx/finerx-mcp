// The `finerx.view/2` envelope (contract C2, phase-2 views C2') as the widget
// reads it. Hand-kept, mirroring the MCP's Pydantic schemas. Every field is
// treated as optional at runtime — the widget must draw something sane from a
// partial or older payload.

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
  /** "address" = geocoded from what the person typed in the "where" field (phase 2). */
  precision?: "zip" | "approx" | "address" | "none";
  /** Rounded to 0.01° by the API when present (the map centre); never stored. */
  lat?: number | null;
  lon?: number | null;
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
  pricesWithoutStores?: PriceRow[];
}

export interface CardData {
  drug?: Drug | null;
  priceWithCard?: PriceWithCard | null;
}

/** One suggestion of `ui_suggest` / `open_price_finder` (contract C1'.1). */
export interface Suggestion {
  slug: string;
  name: string;
  kind?: string;
  matchedAlias?: string | null;
  cardFrom?: Price | null;
}

/** A brand from another country the query matched (C1'.1 `foreignBrands`). */
export interface ForeignBrand {
  brand: string;
  brandSlug?: string;
  countries?: string[];
  usSlug?: string | null;
  usName?: string | null;
}

export interface SuggestResult {
  results?: Suggestion[];
  foreignBrands?: ForeignBrand[];
}

export interface SearchData extends SuggestResult {
  query?: string | null;
  suggestions?: Suggestion[];
  popular?: Drug[];
  origin?: Origin | null;
}

export type UsClass = "same_inn" | "rx_alternative" | "no_equivalent";

export interface EquivalentData {
  brand?: string;
  countries?: string[];
  inn?: string | null;
  usClass?: UsClass | string;
  /** The reviewed sentence from the API. Shown VERBATIM. */
  guidance?: string | null;
  /** The API's "same ingredient is not the same product" sentence, when sent. */
  disclaimer?: string | null;
  us?: (Drug & { cardFrom?: Price | null }) | null;
}

export interface RxLink {
  label: string;
  url: string;
}

export interface RxSection {
  title?: string;
  body?: string;
  links?: RxLink[];
}

export interface RxData {
  drug?: Drug | null;
  restricted?: boolean;
  /** Optional server wording of the restricted note. */
  note?: string | null;
  sections?: RxSection[];
  cardFrom?: Price | null;
  /** The reader's language; the envelope's `locale` of an rx answer keeps its
   * 2.0 meaning (the content language, en/es). */
  readerLocale?: string | null;
}

export type ViewName = "prices" | "pharmacies" | "card" | "search" | "equivalent" | "rx";

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
