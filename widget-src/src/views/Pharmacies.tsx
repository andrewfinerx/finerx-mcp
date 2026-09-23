// view=pharmacies, inline list (phase 1; the fullscreen SVG map is phase 2):
// chain, address, miles, the chain's card price with its date, directions.
// The family filter is local — no tool call for narrowing a list we hold.

import { useState } from "preact/hooks";
import { useApp } from "../context";
import { CardStrip } from "../components/CardStrip";
import { ChipRow, LocationLine, type Chip } from "../components/Controls";
import { day, hasPrice, miles, money } from "../format";
import { cleanArgs } from "../result";
import type { Envelope, PharmaciesData, Store } from "../types";

const INLINE_STORES = 6;

/** Display names of the 16 price families (contract: one code set everywhere). */
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

/** Directions open in the person's maps app through the host; only the STORE's
 * coordinates travel, never the person's own location. */
export function mapsUrl(store: Store): string {
  const dest =
    typeof store.lat === "number" && typeof store.lon === "number"
      ? `${store.lat},${store.lon}`
      : [store.name, store.address, store.city].filter(Boolean).join(", ");
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(dest)}`;
}

export function PharmaciesView({ env }: { env: Envelope }) {
  const { t, run } = useApp();
  const data = (env.data || {}) as PharmaciesData;
  const stores = data.stores || [];
  const [family, setFamily] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const families = Array.from(new Set([...(data.families || []), ...stores.map((s) => s.family)])).filter((f) =>
    stores.some((s) => s.family === f),
  );
  const chips: Chip[] = [
    { key: "*", label: t("allFamilies"), active: family === null, onPick: () => setFamily(null) },
    ...families.map((f) => ({
      key: f,
      label: FAMILY_NAMES[f] || f,
      active: family === f,
      onPick: () => setFamily(f),
    })),
  ];
  const filtered = family ? stores.filter((s) => s.family === family) : stores;
  const shown = expanded ? filtered : filtered.slice(0, INLINE_STORES);
  const hidden = filtered.length - shown.length;

  const onZip = (zip: string) =>
    run(
      "ui_nearby",
      cleanArgs({
        zip,
        family: family || undefined,
        slug: data.drug?.slug,
        form: data.package?.form,
        strength: data.package?.strength,
        quantity: data.package?.quantity,
      }),
    );
  const needsZip = !stores.length && (!data.origin || data.origin.precision === "none");

  return (
    <div class="view" data-view="pharmacies">
      <header class="head">
        <h1 class="title" dir="auto">{data.drug?.name || t("pharmaciesTitle")}</h1>
        {data.package?.label && <p class="sub" dir="auto">{data.package.label}</p>}
      </header>
      <LocationLine origin={data.origin} needsZip={needsZip} onZip={onZip} />
      {families.length > 1 && <ChipRow chips={chips} label={t("pharmaciesTitle")} max={6} />}
      {shown.length > 0 && (
        <ul class="rows stores" data-testid="store-rows">
          {shown.map((s, i) => (
            <StoreRow key={`${s.family}|${s.address || ""}|${i}`} store={s} />
          ))}
        </ul>
      )}
      {hidden > 0 && (
        <button type="button" class="link" onClick={() => setExpanded(true)}>
          {t("showMore", { n: hidden })}
        </button>
      )}
      {shown.length > 0 && <p class="muted small">{t("noStock")}</p>}
      <CardStrip card={env.card} secondary="save" />
    </div>
  );
}

function StoreRow({ store }: { store: Store }) {
  const { t, locale, bridge } = useApp();
  const meta: string[] = [];
  const addr = [store.address, cityCase(store.city)].filter(Boolean).join(", ");
  if (addr) meta.push(addr);
  if (typeof store.miles === "number") meta.push(t("miles", { n: miles(store.miles, locale) }));
  if (hasPrice(store.price)) meta.push(t("observed", { date: day(store.price.observedAt, locale) }));
  return (
    <li class="row">
      <span class="name">{store.name}</span>
      <span class="amt" dir="ltr">
        {hasPrice(store.price) ? money(store.price.amount, locale) : "—"}
      </span>
      <span class="meta">
        {meta.join(" · ")}
        {store.kind === "store" && <span class="note"> · {t("storeInStore")}</span>}
        {" · "}
        <button type="button" class="link" data-testid="directions" onClick={() => bridge.openLink(mapsUrl(store))}>
          {t("directions")}
        </button>
      </span>
    </li>
  );
}

/** OSM city tags are sometimes all lower case ("miami"); show them as a name. */
function cityCase(city: string | null | undefined): string {
  if (!city) return "";
  if (city !== city.toLowerCase()) return city;
  return city.replace(/(^|[\s-])(\p{L})/gu, (_m, sep: string, ch: string) => sep + ch.toUpperCase());
}
