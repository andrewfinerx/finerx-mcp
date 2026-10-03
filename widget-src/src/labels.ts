// UI strings. Every real render uses `_meta["finerx/labels"]` off the tool
// result (the MCP serves them in 12 locales, translated from this English);
// these English constants are only the fallback for a key the payload lacks.
// Placeholders are `{name}` and are filled by t(). Keep the card-law bans in
// mind: no always/guaranteed/"save up to"/best/cheapest/usually/lowest/"most
// pharmacies"/"works with insurance" — test/labels.test.ts enforces it.

import type { Labels } from "./types";

export const FALLBACK_LABELS: Labels = {
  // --- contract C2 keys --------------------------------------------------
  pricesTitle: "Price with the FineRx card, low to high",
  nearLabel: "Near {place}",
  approx: "(approximate)",
  changeZip: "change ZIP",
  zipPlaceholder: "ZIP code",
  withCard: "with card",
  observed: "observed {date}",
  miles: "{n} mi",
  moreChains: "+ {n} more chains",
  allPharmacies: "All pharmacies",
  showAtCounter: "Show at the counter",
  save: "Save",
  print: "Print",
  email: "Email",
  sms: "Text message",
  copy: "Copy",
  copied: "Copied",
  noPrice:
    "We haven't seen a card price for this package yet. Estimated prices are on our site; show the card at the pharmacy to get the final price.",
  otherQuantities: "Card prices we have seen for other quantities:",
  needsZip: "Enter a ZIP code to see pharmacies near you. These are card prices by chain.",
  notInsurance: "Not insurance",
  cardTitle: "Prescription Discount Card",
  cardSub: "Free \u00b7 no signup \u00b7 show it to your pharmacist",
  howToTitle: "At the pharmacy counter",
  step1: "Show the card, or read out BIN, PCN and Group.",
  step2: "Ask them to run it as a discount card, not as insurance.",
  step3: "Ask the price with the card and without it, and pay the lower one.",
  moreChainOne: "+ 1 more chain",
  loading: "Loading prices…",
  error: "Prices didn't load. The card still works.",
  storeInStore: "pharmacy in store (not verified)",
  noStock: "We don't see stock — call the pharmacy before you go.",
  // --- widget-only keys (the MCP may add them to finerx/labels) -----------
  bin: "BIN",
  pcn: "PCN",
  group: "Group",
  zipGo: "OK",
  zipInvalid: "Enter a 5-digit ZIP code",
  other: "Other",
  wallet: "Wallet (printable card)",
  emailPlaceholder: "Your email",
  emailSend: "Send card",
  emailConsent:
    "We’ll send one email with your card. We don’t store your address and won’t email you again.",
  sending: "Sending…",
  emailSent: "Sent — check your inbox",
  emailError: "Couldn't send — try again",
  actionError: "That didn't load. Try again.",
  directions: "Directions",
  allFamilies: "All",
  pharmaciesTitle: "Pharmacies nearby",
  pricesWithoutStores: "Card price, no store nearby:",
  showMore: "Show {n} more",
  close: "Close",
  noPriceShort: "no card price seen",
  priceAt: "{price} {withCard} at {name}",
  // --- phase 2 (contract C2' labels: search / map / where / equivalent / rx)
  where: "Where:",
  wherePlaceholder: "ZIP, city or address",
  changeWhere: "change location",
  whereInvalid: "Enter a 5-digit ZIP code, a city or an address",
  needsWhere: "Enter a ZIP code, a city or an address to see pharmacies near you. These are card prices by chain.",
  whereNote: "An address is sent once to the US Census geocoder to find pharmacies nearby. We don't store it.",
  inn: "Active ingredient",
  searchTitle: "Find a medicine",
  searchPlaceholder: "Medicine, or a brand from your country",
  openSearch: "Search",
  popular: "Often searched:",
  searching: "Searching…",
  noResults: "Nothing found. Try the active ingredient, or check the spelling.",
  fromWithCard: "with card from {price} · {date}",
  kindGeneric: "generic",
  kindBrand: "brand",
  foreignBrand: "foreign brand",
  inUs: "in the US: {name}",
  noUsProduct: "no US product listed",
  backToSearch: "Back to search",
  back: "Back",
  onMap: "On the map",
  listView: "List",
  you: "You",
  mapTitle: "Pharmacies on a map",
  mapRange: "Range",
  offMap: "{n} farther than {r} mi — in the list",
  equivalentUs: "In the US",
  usClassSameInn: "same active ingredient",
  usClassRxAlternative: "not sold in the US as the same product",
  usClassNoEquivalent: "no US equivalent",
  sameInnNote: "Same active ingredient is not the same product — ask a pharmacist.",
  pricesInUs: "Prices in the US",
  rxTitle: "How to get a prescription: {name}",
  rxTitleAny: "How to get a prescription",
  rxRestricted:
    "For this medicine FineRx shows only card prices and the free card. Discuss treatment with a licensed clinician.",
  pricesWithCard: "Prices with the card",
  withoutInsurance: "Without insurance:",
  // --- MCP 2.2: the basket (several medicines at one place) ---------------
  basketTitle: "{n} medicines",
  basketOneChain: "All at one chain, by the sum of card prices",
  basketTotal: "Sum for all {n}",
  basketMissing: "no card price for {items}",
  basketSplit: "One chain per medicine: {price} across {n} chains",
  basketDates: "prices observed {dates}",
  basketUnmatched: "{n} not found and left out",
  basketLeftOut: "The sums leave out {items}: no card price seen.",
  qrScan: "At a computer? Scan to open the card on your phone.",
  transferTitle: "Move a prescription to {name}",
  transferTitleAny: "Move a prescription to another pharmacy",
  transferStores: "Nearest stores",
  equivalentsTitle: "Medicines from abroad: what each is in the US",
  equivalentsUnmatched: "{n} not in our reviewed list — left out",
  packagesTitle: "Strengths and pack sizes with a card price",
  moreStrengths: "+ {n} more strengths — name the one you take",
  chainsPriced: "{n} chains",
  compareLine: "Against {price}: {below} of {n} chains were seen below it",
  compareNote: "A card price replaces insurance for that fill: it is not added to a copay and may not count toward a deductible.",
  belowAmount: "below {price}",
  basketSum: "A sum adds up observed card prices. It is not a quote: the pharmacy sets the final price.",
};

export function fill(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (whole, key: string) =>
    Object.prototype.hasOwnProperty.call(vars, key) ? String(vars[key]) : whole,
  );
}

export interface T {
  (key: string, vars?: Record<string, string | number>): string;
  /** The first of `keys` the PAYLOAD carries, else the English of the first:
   * a phase-2 key ("changeWhere") falls back to the phase-1 one ("changeZip")
   * an older server translated, before falling back to English. */
  alt(keys: string[], vars?: Record<string, string | number>): string;
}

/** Payload labels first (non-empty strings only), English fallback second. */
export function makeT(labels: Labels | null | undefined): T {
  const got = (key: string) => (labels && typeof labels[key] === "string" && labels[key].trim() ? labels[key] : "");
  const t = ((key: string, vars?: Record<string, string | number>) =>
    fill(got(key) || FALLBACK_LABELS[key] || key, vars)) as T;
  t.alt = (keys, vars) => {
    for (const key of keys) if (got(key)) return fill(got(key), vars);
    return t(keys[0], vars);
  };
  return t;
}
