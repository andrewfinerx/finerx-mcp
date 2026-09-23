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
};

export function fill(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (whole, key: string) =>
    Object.prototype.hasOwnProperty.call(vars, key) ? String(vars[key]) : whole,
  );
}

/** Payload labels first (non-empty strings only), English fallback second. */
export function makeT(labels: Labels | null | undefined) {
  return (key: string, vars?: Record<string, string | number>): string => {
    const got = labels && typeof labels[key] === "string" && labels[key].trim() ? labels[key] : "";
    return fill(got || FALLBACK_LABELS[key] || key, vars);
  };
}

export type T = ReturnType<typeof makeT>;
