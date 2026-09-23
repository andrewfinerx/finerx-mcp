// view=pharmacies. Inline (phase 1): a list — chain, address, miles, the
// chain's card price with its date, directions — plus "On the map", which asks
// the host for fullscreen. Fullscreen (phase 2, spec §4.3): the SVG scheme with
// rings and family-coloured dots beside the list (under it below 720px); a dot
// opens the store's card with price, date and directions. The family filter
// and the range are local — no tool call for narrowing what we already hold.

import { useEffect, useRef, useState } from "preact/hooks";
import { useApp } from "../context";
import { CardStrip } from "../components/CardStrip";
import { ChipRow, LocationLine, type Chip, type WhereInput } from "../components/Controls";
import { RINGS, StoreMap, centreOf, fitExtent, hasCoords, project } from "../components/StoreMap";
import { familyColor, familyMonogram, familyName } from "../families";
import { day, hasPrice, miles, money } from "../format";
import { cleanArgs } from "../result";
import type { Envelope, PharmaciesData, Store } from "../types";

export { FAMILY_NAMES } from "../families";

const INLINE_STORES = 6;

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
  const { t, locale, run, display, goFullscreen, goInline } = useApp();
  const data = (env.data || {}) as PharmaciesData;
  const stores = data.stores || [];
  const [family, setFamily] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  // "auto" follows the host: fullscreen draws the map, inline the list.
  const [mode, setMode] = useState<"auto" | "map" | "list">("auto");
  const [selected, setSelected] = useState<Store | null>(null);
  const [range, setRange] = useState<number | null>(null);
  const switched = useRef(false);

  useEffect(() => {
    // The person left fullscreen from the host's own chrome.
    if (display !== "fullscreen" && switched.current) {
      switched.current = false;
      setMode("auto");
    }
  }, [display]);
  useEffect(() => setSelected(null), [env]);

  const families = Array.from(new Set([...(data.families || []), ...stores.map((s) => s.family)])).filter((f) =>
    stores.some((s) => s.family === f),
  );
  const filtered = family ? stores.filter((s) => s.family === family) : stores;
  const plotted = filtered.filter(hasCoords);
  const centre = centreOf(data.origin, stores);
  const mapMode = !!centre && stores.some(hasCoords) && (mode === "map" || (mode === "auto" && display === "fullscreen"));

  const chips: Chip[] = [
    { key: "*", label: t("allFamilies"), active: family === null, onPick: () => setFamily(null) },
    ...families.map((f) => ({
      key: f,
      label: familyName(f),
      active: family === f,
      onPick: () => {
        setFamily(f);
        if (selected && selected.family !== f) setSelected(null);
      },
      swatch: mapMode ? familyColor(f) : undefined,
    })),
  ];

  const onWhere = (where: WhereInput) =>
    run(
      "ui_nearby",
      cleanArgs({
        ...where,
        family: family || undefined,
        slug: data.drug?.slug,
        form: data.package?.form,
        strength: data.package?.strength,
        quantity: data.package?.quantity,
      }),
      { typed: true },
    );
  const needsZip = !stores.length && (!data.origin || data.origin.precision === "none");

  async function openMap() {
    setMode("map");
    if ((await goFullscreen()) === "granted") switched.current = true;
  }
  function closeMap() {
    setMode("list");
    setSelected(null);
    if (switched.current) {
      switched.current = false;
      goInline();
    }
  }

  const noStores = (data.pricesWithoutStores || []).filter((r) => hasPrice(r.price)).slice(0, 3);
  const noStoresLine = noStores.length > 0 && (
    <p class="muted small">
      {t("pricesWithoutStores")}{" "}
      {noStores.map((r, i) => (
        <span key={r.family}>
          {i > 0 ? " · " : ""}
          {r.name} <span dir="ltr">{money(r.price!.amount, locale)}</span> ({day(r.price!.observedAt, locale)})
        </span>
      ))}
    </p>
  );

  const head = (
    <header class="head">
      <h1 class="title" dir="auto">{data.drug?.name || t("pharmaciesTitle")}</h1>
      {data.package?.label && <p class="sub" dir="auto">{data.package.label}</p>}
      {stores.some(hasCoords) && !!centre && (
        <button
          type="button"
          class="btn small head-btn"
          data-testid={mapMode ? "map-close" : "map-open"}
          onClick={mapMode ? closeMap : openMap}
        >
          {mapMode ? t("listView") : t("onMap")}
        </button>
      )}
    </header>
  );

  if (mapMode && centre) {
    const distances = plotted.map((s) => (typeof s.miles === "number" ? s.miles : Math.hypot(...project(centre, s.lat, s.lon))));
    const extent = range ?? fitExtent(distances);
    const off = distances.filter((d) => d > extent * 1.02).length;
    const rangeChips: Chip[] = RINGS.map((r) => ({
      key: String(r),
      label: t("miles", { n: miles(r, locale) }),
      active: r === extent,
      onPick: () => setRange(r),
    }));
    return (
      <div class="view" data-view="pharmacies" data-mode="map">
        {head}
        <LocationLine origin={data.origin} needsZip={needsZip} onWhere={onWhere} />
        {families.length > 1 && <ChipRow chips={chips} label={t("pharmaciesTitle")} max={8} />}
        <div class="mapwrap">
          <div class="mapcol">
            <StoreMap
              centre={centre}
              stores={plotted}
              extent={extent}
              approx={data.origin?.precision === "approx" || !(typeof data.origin?.lat === "number")}
              selected={selected}
              onSelect={setSelected}
            />
            <ChipRow chips={rangeChips} label={t("mapRange")} max={3} />
            {off > 0 && <p class="muted small">{t("offMap", { n: off, r: extent })}</p>}
            {selected && <StoreCard store={selected} onClose={() => setSelected(null)} />}
          </div>
          <ul class="rows stores maplist" data-testid="store-rows">
            {filtered.map((s, i) => (
              <StoreRow
                key={`${s.family}|${s.address || ""}|${i}`}
                store={s}
                active={s === selected}
                onSelect={hasCoords(s) ? () => setSelected(s) : undefined}
              />
            ))}
          </ul>
        </div>
        {noStoresLine}
        {stores.length > 0 && <p class="muted small">{t("noStock")}</p>}
        <CardStrip card={env.card} secondary="save" />
      </div>
    );
  }

  const shown = expanded ? filtered : filtered.slice(0, INLINE_STORES);
  const hidden = filtered.length - shown.length;
  return (
    <div class="view" data-view="pharmacies">
      {head}
      <LocationLine origin={data.origin} needsZip={needsZip} onWhere={onWhere} />
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
      {noStoresLine}
      {shown.length > 0 && <p class="muted small">{t("noStock")}</p>}
      <CardStrip card={env.card} secondary="save" />
    </div>
  );
}

function storeMeta(store: Store, t: ReturnType<typeof useApp>["t"], locale: string, withDate: boolean): string[] {
  const meta: string[] = [];
  const addr = [store.address, cityCase(store.city)].filter(Boolean).join(", ");
  if (addr) meta.push(addr);
  if (typeof store.miles === "number") meta.push(t("miles", { n: miles(store.miles, locale) }));
  if (withDate && hasPrice(store.price)) meta.push(t("observed", { date: day(store.price.observedAt, locale) }));
  return meta;
}

function StoreRow({ store, active, onSelect }: { store: Store; active?: boolean; onSelect?: () => void }) {
  const { t, locale, bridge } = useApp();
  const meta = storeMeta(store, t, locale, true);
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    // A dot picked on the map brings its row into the (scrolling) list.
    if (!active) return;
    try {
      ref.current?.scrollIntoView?.({ block: "nearest" });
    } catch {
      /* ignore */
    }
  }, [active]);
  return (
    <li ref={ref} class={`row${active ? " on" : ""}`} data-active={active ? "true" : undefined}>
      {onSelect ? (
        <button type="button" class="name pick" aria-pressed={!!active} onClick={onSelect}>
          <span class="mono" style={{ background: familyColor(store.family) }} aria-hidden="true">
            {familyMonogram(store.family, store.name)}
          </span>
          {store.name}
        </button>
      ) : (
        <span class="name">{store.name}</span>
      )}
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

/** A dot's card: the store, its family's card price with the date, directions. */
function StoreCard({ store, onClose }: { store: Store; onClose: () => void }) {
  const { t, locale, bridge } = useApp();
  const meta = storeMeta(store, t, locale, false);
  return (
    <div class="store-card" data-testid="store-card" role="region" aria-label={store.name}>
      <div class="sc-head">
        <span class="mono" style={{ background: familyColor(store.family) }} aria-hidden="true">
          {familyMonogram(store.family, store.name)}
        </span>
        <b class="sc-name">{store.name}</b>
        <button type="button" class="link sc-x" aria-label={t("close")} onClick={onClose}>
          ×
        </button>
      </div>
      {hasPrice(store.price) ? (
        <p class="sc-price">
          <span class="amt big" dir="ltr">
            {money(store.price.amount, locale)}
          </span>{" "}
          {t("withCard")} · {t("observed", { date: day(store.price.observedAt, locale) })}
        </p>
      ) : (
        <p class="muted small">{t("noPriceShort")}</p>
      )}
      {meta.length > 0 && <p class="muted small">{meta.join(" · ")}</p>}
      {store.kind === "store" && <p class="muted small note">{t("storeInStore")}</p>}
      <button type="button" class="btn small" data-testid="store-directions" onClick={() => bridge.openLink(mapsUrl(store))}>
        {t("directions")}
      </button>
    </div>
  );
}

/** OSM city tags are sometimes all lower case ("miami"); show them as a name. */
function cityCase(city: string | null | undefined): string {
  if (!city) return "";
  if (city !== city.toLowerCase()) return city;
  return city.replace(/(^|[\s-])(\p{L})/gu, (_m, sep: string, ch: string) => sep + ch.toUpperCase());
}
