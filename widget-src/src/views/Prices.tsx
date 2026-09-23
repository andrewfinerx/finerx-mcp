// view=prices, inline (spec §4.1): package → chips → where (ZIP, city or
// address) → chains by card price, each with its date and distance → the card
// strip. Two buttons only.

import { useApp } from "../context";
import { CardStrip } from "../components/CardStrip";
import { ChipRow, LocationLine, type Chip, type WhereInput } from "../components/Controls";
import { day, hasPrice, miles, money, zoneLabel } from "../format";
import { cleanArgs } from "../result";
import type { ConfigOption, Envelope, Origin, PriceRow, PricesData } from "../types";

const INLINE_ROWS = 6;

/** A ZIP goes back to the server only when the person gave it: named in the
 * chat (precision "zip"), resolved from the place they typed ("address"), or
 * typed here. An approximate origin (ChatGPT userLocation) stays the host's. */
export function personZip(origin: Origin | null | undefined, userZip: string | null): string | null {
  const given = origin && (origin.precision === "zip" || origin.precision === "address") ? origin.zip : null;
  return given || userZip || null;
}

const same = (a?: string, b?: string) => (a || "").trim().toLowerCase() === (b || "").trim().toLowerCase();

export function PricesView({ env }: { env: Envelope }) {
  const { t, locale, run, userZip } = useApp();
  const data = env.data as PricesData;
  const drug = data.drug;
  const pkg = data.package || {};
  const origin = data.origin;
  const configs: ConfigOption[] = (data.options && data.options.configs) || [];
  const current = configs.find((c) => same(c.form, pkg.form) && same(c.strength, pkg.strength));
  const coverage = data.coverage || {};
  const status = coverage.status || "exact";

  const knownZip = personZip(origin, userZip);

  // A typed place goes out once: a ZIP as `zip`, anything else as `where`
  // (geocoded by the server); later calls carry the ZIP it resolved to.
  function refine(patch: Record<string, unknown>, where?: WhereInput) {
    return run(
      "ui_prices",
      cleanArgs({
        slug: drug.slug,
        form: pkg.form,
        strength: pkg.strength,
        quantity: pkg.quantity,
        ...patch,
        ...(where || { zip: knownZip }),
      }),
      { typed: !!where },
    );
  }

  const doseChips: Chip[] = configs.map((c) => ({
    key: `${c.form}|${c.strength}`,
    label: c.label || [c.strength, c.form].filter(Boolean).join(" "),
    active: c === current,
    onPick: () =>
      refine({
        form: c.form,
        strength: c.strength,
        // Keep the quantity when the new dose sells it; else let the server pick.
        quantity: (c.quantities || []).some((q) => q.quantity === pkg.quantity) ? pkg.quantity : undefined,
      }),
  }));
  const qtyChips: Chip[] = ((current && current.quantities) || []).map((q) => ({
    key: String(q.quantity),
    label: q.label || String(q.quantity),
    active: q.quantity === pkg.quantity,
    onPick: () => refine({ quantity: q.quantity }),
  }));

  const rows = (data.rows || []).slice(0, INLINE_ROWS);
  const anyPriced = rows.some((r) => hasPrice(r.price));
  // needsZip: there are no stores to rank, only card prices by chain.
  const listed = rows.length ? rows : (data.pricesWithoutStores || []).slice(0, INLINE_ROWS);
  const listedPriced = listed.some((r) => hasPrice(r.price));
  const noStores = rows.length ? (data.pricesWithoutStores || []).filter((r) => hasPrice(r.price)).slice(0, 3) : [];

  return (
    <div class="view" data-view="prices">
      <header class="head">
        <h1 class="title" dir="auto">{drug.name}</h1>
        {pkg.label && <p class="sub" dir="auto">{pkg.label}</p>}
      </header>

      <ChipRow chips={doseChips} label={t("pricesTitle")} />
      <ChipRow chips={qtyChips} label={pkg.label || t("pricesTitle")} />

      <LocationLine origin={origin} needsZip={!!data.needsZip} onWhere={(where) => refine({}, where)} />

      {status !== "exact" && <p class="notice">{t("noPrice")}</p>}
      {status === "other_quantities" && <OtherQuantities data={data} current={current} onPick={(q) => refine({ quantity: q })} />}

      {listedPriced || (status === "exact" && listed.length) ? (
        <>
          <p class="caption">{t("pricesTitle")}</p>
          <ul class="rows" data-testid="price-rows">
            {listed.map((r) => (
              <Row key={`${r.family}|${r.zone || ""}`} row={r} />
            ))}
          </ul>
        </>
      ) : null}
      {(data.moreCount || 0) > 0 && (anyPriced || listedPriced) && (
        <p class="muted small">{data.moreCount === 1 ? t("moreChainOne") : t("moreChains", { n: data.moreCount || 0 })}</p>
      )}
      {noStores.length > 0 && (
        <p class="muted small">
          {t("pricesWithoutStores")}{" "}
          {noStores.map((r, i) => (
            <span key={r.family}>
              {i > 0 ? " · " : ""}
              {r.name} <span dir="ltr">{money(r.price!.amount, locale)}</span> ({day(r.price!.observedAt, locale)})
            </span>
          ))}
        </p>
      )}

      <CardStrip
        card={env.card}
        secondary="allPharmacies"
        onAllPharmacies={() =>
          run(
            "ui_nearby",
            cleanArgs({ slug: drug.slug, form: pkg.form, strength: pkg.strength, quantity: pkg.quantity, zip: knownZip }),
          )
        }
      />
    </div>
  );
}

function Row({ row }: { row: PriceRow }) {
  const { t, locale } = useApp();
  const zone = zoneLabel(row.zone);
  const meta: string[] = [];
  if (typeof row.nearestMiles === "number") meta.push(t("miles", { n: miles(row.nearestMiles, locale) }));
  if (hasPrice(row.price)) meta.push(t("observed", { date: day(row.price.observedAt, locale) }));
  else meta.push(t("noPriceShort"));
  return (
    <li class="row">
      <span class="name">
        {row.name}
        {zone && <span class="muted"> ({zone})</span>}
      </span>
      <span class="amt" dir="ltr">
        {hasPrice(row.price) ? money(row.price.amount, locale) : "—"}
      </span>
      <span class="meta">{meta.join(" · ")}</span>
    </li>
  );
}

/** Coverage "other_quantities": the counts we DO hold a card price for, each a
 * button. A price is never rescaled from one quantity to another. */
function OtherQuantities({
  data,
  current,
  onPick,
}: {
  data: PricesData;
  current: ConfigOption | undefined;
  onPick: (quantity: number) => void;
}) {
  const { t, locale, busy } = useApp();
  const qs = (data.coverage && data.coverage.quantities) || [];
  if (!qs.length) return null;
  const opt = (q: number) => ((current && current.quantities) || []).find((o) => o.quantity === q);
  return (
    <div class="other-q">
      <p class="small">{t("otherQuantities")}</p>
      <div class="chips">
        {qs.map((q) => {
          const o = opt(q);
          const from = o && hasPrice(o.cardFrom) ? o.cardFrom : null;
          return (
            <button type="button" class="chip" key={q} disabled={busy} data-testid={`other-q-${q}`} onClick={() => onPick(q)}>
              <span dir="ltr">{(o && o.label) || q}</span>
              {from && (
                <span class="muted">
                  {" · "}
                  <span dir="ltr">{money(from.amount, locale)}</span> · {day(from.observedAt, locale)}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
