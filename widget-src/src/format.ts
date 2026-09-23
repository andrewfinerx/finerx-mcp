// Money, dates and distances. Latin digits everywhere (`-u-nu-latn`): a price
// or a code is read aloud at a pharmacy counter in the US, so it must look the
// way the receipt will — "$4.20" in every locale (the card law says "$4.20"
// too), and the markup pins those spans to dir="ltr".

import type { Price } from "./types";

function latn(locale: string): string {
  const base = (locale || "en").trim() || "en";
  return base.includes("-u-") ? base : `${base}-u-nu-latn`;
}

export function money(amount: number, _locale?: string): string {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `$${Number(amount).toFixed(2)}`;
  }
}

/** "Sep 21" this year, "Sep 21, 2025" otherwise; the raw ISO if unparseable. */
export function day(iso: string | null | undefined, locale: string, now: Date = new Date()): string {
  if (typeof iso !== "string" || !/^\d{4}-\d{2}-\d{2}/.test(iso)) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  if (Number.isNaN(date.getTime())) return iso;
  try {
    const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", timeZone: "UTC" };
    if (y !== now.getUTCFullYear()) opts.year = "numeric";
    return new Intl.DateTimeFormat(latn(locale), opts).format(date);
  } catch {
    return iso;
  }
}

export function miles(value: number, locale: string): string {
  try {
    return new Intl.NumberFormat(latn(locale), { maximumFractionDigits: 1 }).format(value);
  } catch {
    return value.toFixed(1);
  }
}

/** A price is only drawable with its date; anything less is "no price". */
export function hasPrice(p: Price | null | undefined): p is Price {
  return !!p && typeof p.amount === "number" && Number.isFinite(p.amount) && typeof p.observedAt === "string";
}

/** "tx" → "TX", "mn_nd" → "MN/ND"; the national default zone shows nothing. */
export function zoneLabel(zone: string | null | undefined): string {
  if (!zone || zone === "default") return "";
  return zone.toUpperCase().split("_").join("/");
}
