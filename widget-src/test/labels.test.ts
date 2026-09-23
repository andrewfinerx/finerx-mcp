import { describe, expect, it } from "vitest";
import { FALLBACK_LABELS, fill, makeT } from "../src/labels";
import { FALLBACK_LAW } from "../src/card";

const BANNED = /\b(always|guaranteed|save up to|best|cheapest|usually|works with insurance|most pharmacies|lowest)\b/i;

// Contract C2: the minimum label keys the MCP sends; the bundle must carry an
// English fallback for each so a partial payload never renders a blank.
const CONTRACT_KEYS = [
  "pricesTitle", "nearLabel", "approx", "changeZip", "zipPlaceholder", "withCard", "observed", "miles",
  "moreChains", "allPharmacies", "showAtCounter", "save", "print", "email", "sms", "copy", "copied",
  "noPrice", "otherQuantities", "needsZip", "notInsurance", "loading", "error", "storeInStore", "noStock",
];

describe("labels", () => {
  it("has an English fallback for every contract key", () => {
    for (const key of CONTRACT_KEYS) expect(FALLBACK_LABELS[key], key).toBeTruthy();
  });

  it("no fallback string uses a banned card-law word", () => {
    for (const [key, text] of Object.entries(FALLBACK_LABELS)) expect(text, key).not.toMatch(BANNED);
  });

  it("the bundled law is the approved no-price text, verbatim", () => {
    expect(FALLBACK_LAW).toBe(
      "Use the free FineRx card — accepted at 34+ pharmacy chains, no signup. Save it, print it, email or text it. Savings with the card can be substantial — estimated prices are on our site. Show the card at the pharmacy to get the final price.",
    );
  });

  it("payload wins, blanks fall back, placeholders fill", () => {
    const t = makeT({ copy: "Copiar", save: "  " });
    expect(t("copy")).toBe("Copiar");
    expect(t("save")).toBe("Save");
    expect(t("moreChains", { n: 3 })).toBe("+ 3 more chains");
    expect(fill("{a} {b}", { a: 1 })).toBe("1 {b}");
  });
});
