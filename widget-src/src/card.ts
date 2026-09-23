// The card identity and the approved card law, bundled as the LAST resort: a
// host that hands us nothing (or an API that is down) still leaves a person
// with three usable codes. Same values the API serves. Every real render uses
// `card.codes` / `card.law` / `card.fine` from the payload instead.

import type { Codes, CardView } from "./types";

export const FALLBACK_CODES: Codes = { bin: "610219", pcn: "DRX", group: "MYCARD3993" };

/** The owner-approved EN law, no-price variant, VERBATIM (contract, card law). */
export const FALLBACK_LAW =
  "Use the free FineRx card — accepted at 34+ pharmacy chains, no signup. Save it, print it, email or text it. Savings with the card can be substantial — estimated prices are on our site. Show the card at the pharmacy to get the final price.";

export function codesOf(card: CardView | null | undefined): Codes {
  const c = (card && card.codes) || {};
  const pick = (v: unknown, dflt: string) => (typeof v === "string" && v.trim() ? v.trim() : dflt);
  return {
    bin: pick(c.bin, FALLBACK_CODES.bin),
    pcn: pick(c.pcn, FALLBACK_CODES.pcn),
    group: pick(c.group, FALLBACK_CODES.group),
  };
}
