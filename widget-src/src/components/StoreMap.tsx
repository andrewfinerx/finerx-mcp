// The pharmacies "map" (spec §4.3): an SVG scheme with no tiles — nothing is
// fetched, so it works under the empty CSP. A local flat projection around the
// origin, rings at 5/10/30 mi, one dot per store coloured by price family with
// its monogram. Where the origin has no coordinates (the API sends city/ZIP
// only), the centre is fitted from the stores' own distances to the person.

import { useApp } from "../context";
import { familyColor, familyMonogram } from "../families";
import { hasPrice, miles, money } from "../format";
import type { Origin, Store } from "../types";

export const RINGS = [5, 10, 30] as const;

const SIZE = 400;
const MID = SIZE / 2;
const RADIUS_PX = 186;
const DOT = 12;
const MI_PER_DEG_LAT = 69.0;

export interface LatLon {
  lat: number;
  lon: number;
}

const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function hasCoords(store: Store): store is Store & { lat: number; lon: number } {
  return num(store.lat) && num(store.lon);
}

/** Miles east / north of `centre` (equirectangular; fine inside 30 mi). */
export function project(centre: LatLon, lat: number, lon: number): [number, number] {
  const kx = MI_PER_DEG_LAT * Math.cos((centre.lat * Math.PI) / 180);
  return [(lon - centre.lon) * kx, (lat - centre.lat) * MI_PER_DEG_LAT];
}

/** Where the person is: the origin's own point when the API sent one, else the
 * point whose distances to the stores best match each store's `miles`
 * (a few Gauss-Newton steps from the distance-weighted mean). */
export function centreOf(origin: Origin | null | undefined, stores: Store[]): LatLon | null {
  if (origin && num(origin.lat) && num(origin.lon)) return { lat: origin.lat, lon: origin.lon };
  const pts = stores.filter(hasCoords);
  if (!pts.length) return null;
  const ref: LatLon = { lat: pts[0].lat, lon: pts[0].lon };
  const xy = pts.map((s) => project(ref, s.lat, s.lon));
  const dist = pts.map((s) => (num(s.miles) ? Math.max(0, s.miles) : null));

  let wx = 0;
  let wy = 0;
  let ws = 0;
  xy.forEach(([x, y], i) => {
    const w = 1 / ((dist[i] ?? 5) + 0.25);
    wx += x * w;
    wy += y * w;
    ws += w;
  });
  let cx = wx / ws;
  let cy = wy / ws;
  const cost = (px: number, py: number) =>
    xy.reduce((acc, [x, y], i) => (dist[i] === null ? acc : acc + (Math.hypot(x - px, y - py) - (dist[i] as number)) ** 2), 0);

  if (dist.filter((d) => d !== null).length >= 3) {
    let best = cost(cx, cy);
    for (let step = 0; step < 25; step++) {
      let a = 0, b = 0, c = 0, gx = 0, gy = 0;
      xy.forEach(([x, y], i) => {
        const d = dist[i];
        if (d === null) return;
        const r = Math.hypot(cx - x, cy - y) || 1e-6;
        const jx = (cx - x) / r;
        const jy = (cy - y) / r;
        const res = r - d;
        a += jx * jx;
        b += jx * jy;
        c += jy * jy;
        gx += jx * res;
        gy += jy * res;
      });
      const det = a * c - b * b;
      if (Math.abs(det) < 1e-9) break;
      const nx = cx - (c * gx - b * gy) / det;
      const ny = cy - (a * gy - b * gx) / det;
      const next = cost(nx, ny);
      if (!Number.isFinite(next) || next >= best) break;
      best = next;
      cx = nx;
      cy = ny;
    }
  }
  const kx = MI_PER_DEG_LAT * Math.cos((ref.lat * Math.PI) / 180);
  return { lat: ref.lat + cy / MI_PER_DEG_LAT, lon: ref.lon + cx / kx };
}

/** The smallest ring that holds most stores (80 %, and at least the nearest
 * three): one far Costco must not shrink the whole neighbourhood to a dot. The
 * rest stay in the list, and the range chips widen the view. */
export function fitExtent(distances: number[]): number {
  const sorted = distances.filter((d) => Number.isFinite(d)).sort((a, b) => a - b);
  if (!sorted.length) return RINGS[0];
  const keep = Math.min(sorted.length, Math.max(3, Math.ceil(sorted.length * 0.8)));
  const far = sorted[keep - 1];
  return RINGS.find((r) => far <= r) || RINGS[RINGS.length - 1];
}

interface Placed {
  store: Store;
  x: number;
  y: number;
}

/** Store dots in px; a dot that would sit on another is walked out on a small
 * spiral so every one of them stays clickable. */
function place(centre: LatLon, stores: Store[], extent: number): Placed[] {
  const scale = RADIUS_PX / extent;
  const out: Placed[] = [];
  for (const store of stores) {
    if (!hasCoords(store)) continue;
    const [mx, my] = project(centre, store.lat, store.lon);
    if (Math.hypot(mx, my) > extent * 1.02) continue;
    let x = MID + mx * scale;
    let y = MID - my * scale;
    for (let k = 1; k <= 12 && out.some((p) => Math.hypot(p.x - x, p.y - y) < DOT * 2 - 2); k++) {
      const angle = k * 2.4;
      x = MID + mx * scale + Math.cos(angle) * DOT * 1.6 * Math.ceil(k / 6);
      y = MID - my * scale + Math.sin(angle) * DOT * 1.6 * Math.ceil(k / 6);
    }
    out.push({ store, x, y });
  }
  return out;
}

export function StoreMap({
  centre,
  stores,
  extent,
  approx,
  selected,
  onSelect,
}: {
  centre: LatLon;
  stores: Store[];
  extent: number;
  approx: boolean;
  selected: Store | null;
  onSelect: (store: Store) => void;
}) {
  const { t, locale } = useApp();
  const scale = RADIUS_PX / extent;
  const dots = place(centre, stores, extent);
  // The selected dot is drawn last, on top of its neighbours.
  const ordered = [...dots.filter((d) => d.store !== selected), ...dots.filter((d) => d.store === selected)];

  return (
    <svg
      class="map"
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      role="group"
      aria-label={t("mapTitle")}
      data-testid="map"
    >
      <circle class="map-bg" cx={MID} cy={MID} r={RADIUS_PX + 8} />
      {RINGS.filter((r) => r <= extent).map((r) => (
        <g key={r} class="ring">
          <circle cx={MID} cy={MID} r={r * scale} />
        </g>
      ))}
      <circle cx={MID} cy={MID} r={approx ? 16 : 10} class="you-halo" aria-hidden="true" />
      {ordered.map(({ store, x, y }) => {
        const active = store === selected;
        const label = [
          store.name,
          num(store.miles) ? t("miles", { n: miles(store.miles, locale) }) : "",
          hasPrice(store.price) ? money(store.price.amount, locale) : "",
        ]
          .filter(Boolean)
          .join(", ");
        return (
          <g
            key={`${store.family}|${store.address || ""}|${x}|${y}`}
            class={`dot${active ? " on" : ""}`}
            role="button"
            tabIndex={0}
            aria-label={label}
            aria-pressed={active}
            data-testid="map-dot"
            data-family={store.family}
            onClick={() => onSelect(store)}
            onKeyDown={(e: KeyboardEvent) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(store);
              }
            }}
          >
            <circle cx={x} cy={y} r={active ? DOT + 3 : DOT} fill={familyColor(store.family)} />
            <text x={x} y={y + 3.5} text-anchor="middle">
              {familyMonogram(store.family, store.name)}
            </text>
          </g>
        );
      })}
      {/* Labels last, with a halo, so a dot never hides them; they take no clicks. */}
      <g class="labels" aria-hidden="true">
        {RINGS.filter((r) => r <= extent).map((r) => (
          // Centred just outside the ring's lower-right point: the same place in
          // either writing direction (the labels arrive translated).
          <text
            key={r}
            class="ring-label"
            text-anchor="middle"
            x={MID + (r * scale) / Math.SQRT2 + 12}
            y={MID + (r * scale) / Math.SQRT2 + 14}
          >
            {t("miles", { n: miles(r, locale) })}
          </text>
        ))}
        <circle cx={MID} cy={MID} r={4.5} class="you-dot" />
        <text class="you-label" x={MID} y={MID - 10} text-anchor="middle">
          {t("you")}
          {approx ? " ≈" : ""}
        </text>
      </g>
    </svg>
  );
}
