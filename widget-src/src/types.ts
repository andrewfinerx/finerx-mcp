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
  /** An amount the person named and how many chains were seen below it. */
  compareTo?: { amount: number; below: number; of: number; observedFrom?: string; observedTo?: string } | null;
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
  /** The card page as a QR: square rows of "0"/"1" (MCP 2.2). */
  qr?: { url?: string; rows?: string[] } | null;
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

/** MCP 2.2: one medicine of the list, with the package the prices are for. */
export interface BasketItem {
  drug: Drug;
  package?: Package;
  coverage?: Coverage;
  /** false = no listed chain was seen pricing it; it is left out of every sum. */
  priced?: boolean;
}

/** A sum of observed card prices with the span of their observation dates. */
export interface BasketTotal {
  amount: number;
  /** How many of the items the sum adds. */
  count?: number;
  observedFrom: string;
  observedTo: string;
}

export interface BasketRow {
  family: string;
  name: string;
  zone?: string | null;
  nearestMiles?: number | null;
  storeCount?: number;
  /** One per item, in the items' order; null = no card price seen there. */
  prices?: (Price | null)[];
  /** Only when every item has a price at this chain. */
  total?: BasketTotal | null;
  /** 1-based numbers of the items without a price here. */
  missing?: number[];
}

export interface BasketData {
  items?: BasketItem[];
  origin?: Origin;
  rows?: BasketRow[];
  moreCount?: number;
  split?: (BasketTotal & { chains?: number; picks?: { item?: number; family: string; name: string }[] }) | null;
  needsZip?: boolean;
  unmatched?: number;
}

/** MCP 2.2: moving a prescription to the chain the person picked. */
export interface TransferData {
  chain?: { family: string; name: string } | null;
  drug?: Drug | null;
  package?: Package | null;
  price?: Price | null;
  /** The server's own fixed sentences. Shown VERBATIM. */
  steps?: string[];
  notes?: string[];
  stores?: Store[];
  origin?: Origin;
  restricted?: boolean;
  note?: string | null;
}

/** MCP 2.2: several medicines from another country, each as `equivalent` gives it. */
export interface EquivalentsData {
  items?: (EquivalentData & { brandSlug?: string | null })[];
  unmatched?: number;
}

/** MCP 2.2: every strength × form of one medicine, each pack size with where
 * its card prices start. */
export interface PackagesData {
  drug: Drug;
  configs?: ConfigOption[];
  /** Strengths with a card price that are not in `configs`. */
  moreCount?: number;
  default?: Package | null;
}

export type ViewName = "prices" | "pharmacies" | "card" | "search" | "equivalent" | "rx" | "basket" | "packages" | "equivalents" | "transfer";

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
