// The 16 price families (contract: one code set everywhere) — display name,
// map colour and the monogram drawn inside a map dot. Every colour carries
// white text at >= 4.5:1, so a monogram reads on either theme.

export const FAMILY_NAMES: Record<string, string> = {
  walmart: "Walmart",
  cvs: "CVS",
  walgreens: "Walgreens",
  kroger: "Kroger",
  albertsons: "Albertsons",
  costco: "Costco",
  publix: "Publix",
  heb: "H-E-B",
  hyvee: "Hy-Vee",
  meijer: "Meijer",
  wegmans: "Wegmans",
  shoprite: "ShopRite",
  bigy: "Big Y",
  gianteagle: "Giant Eagle",
  kinney: "Kinney Drugs",
  capsule: "Capsule",
};

const FAMILY_STYLE: Record<string, [color: string, monogram: string]> = {
  walmart: ["#1d4ed8", "WM"],
  cvs: ["#b91c1c", "CV"],
  walgreens: ["#9d174d", "WG"],
  kroger: ["#4338ca", "KR"],
  albertsons: ["#0369a1", "AB"],
  costco: ["#b45309", "CO"],
  publix: ["#15803d", "PX"],
  heb: ["#c2410c", "HE"],
  hyvee: ["#a21caf", "HV"],
  meijer: ["#0f766e", "MJ"],
  wegmans: ["#7c2d12", "WE"],
  shoprite: ["#be123c", "SR"],
  bigy: ["#6d28d9", "BY"],
  gianteagle: ["#3f6212", "GE"],
  kinney: ["#475569", "KD"],
  capsule: ["#374151", "CP"],
};

export function familyName(code: string): string {
  return FAMILY_NAMES[code] || code;
}

export function familyColor(code: string): string {
  return (FAMILY_STYLE[code] || ["#374151"])[0];
}

export function familyMonogram(code: string, name?: string): string {
  const known = FAMILY_STYLE[code];
  if (known) return known[1];
  return (name || code || "?").replace(/[^\p{L}\p{N}]/gu, "").slice(0, 2).toUpperCase() || "?";
}
