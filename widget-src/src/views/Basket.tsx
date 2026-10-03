// view=basket, inline (MCP 2.2): several medicines at one place. The list of
// packages → where → one row per chain with the SUM of its card prices (only
// where every medicine was seen with a price), each with the dates the prices
// were observed → the card strip. A sum is an addition of observed prices,
// said so under the table; nothing here is computed in the widget.

import { useApp } from "../context";
import { CardStrip } from "../components/CardStrip";
import { LocationLine, type WhereInput } from "../components/Controls";
import { day, hasPrice, miles, money, zoneLabel } from "../format";
import { cleanArgs } from "../result";
import { personZip } from "./Prices";
import type { BasketData, BasketItem, BasketRow, Envelope } from "../types";

const ROWS = 8;

function span(from: string | undefined, to: string | undefined, locale: string): string {
  const a = day(from, locale);
  const b = day(to, locale);
  return !b || a === b ? a : `${a} – ${b}`;
}

export function BasketView({ env }: { env: Envelope }) {
  const { t, locale, run, userZip } = useApp();
  const data = env.data as BasketData;
  const items: BasketItem[] = (data.items || []).filter((it) => it && it.drug && typeof it.drug.slug === "string");
  const rows = (data.rows || []).slice(0, ROWS);
  const knownZip = personZip(data.origin, userZip);
  const summed = rows.some((r) => !!r.total);
  const leftOut = items
    .map((it, i) => (it.priced === false ? `#${i + 1}` : ""))
    .filter(Boolean)
    .join(", ");

  // The same list for another place. Packages travel as parallel lists
  // ("" / 0 = not set); a typed place goes out once and is never kept.
  function again(where: WhereInput) {
    return run(
      "ui_basket",
      cleanArgs({
        slugs: items.map((it) => it.drug.slug),
        strengths: items.map((it) => (it.package && it.package.strength) || ""),
        forms: items.map((it) => (it.package && it.package.form) || ""),
        quantities: items.map((it) => (it.package && it.package.quantity) || 0),
        ...where,
      }),
      { typed: true },
    );
  }
  function open(it: BasketItem) {
    const p = it.package || {};
    return run("ui_prices", cleanArgs({ slug: it.drug.slug, form: p.form, strength: p.strength, quantity: p.quantity, zip: knownZip }));
  }

  return (
    <div class="view" data-view="basket">
      <header class="head">
        <h1 class="title">{t("basketTitle", { n: items.length })}</h1>
      </header>

      <ol class="basket-items" data-testid="basket-items">
        {items.map((it, i) => (
          <li key={it.drug.slug}>
            <button type="button" class="link item" data-testid={`basket-item-${i + 1}`} onClick={() => open(it)}>
              <span class="num" dir="ltr">#{i + 1}</span> <span dir="auto">{it.drug.name}</span>
              {it.package && it.package.label && (
                <span class="muted" dir="auto">
                  {" · "}
                  {it.package.label}
                </span>
              )}
            </button>
            {(it.priced === false || (it.coverage && it.coverage.status && it.coverage.status !== "exact")) && (
              <span class="muted small"> — {t("noPriceShort")}</span>
            )}
          </li>
        ))}
      </ol>

      <LocationLine origin={data.origin} needsZip={!!data.needsZip} onWhere={again} />

      {rows.length > 0 && (
        <>
          {summed && <p class="caption">{t("basketOneChain")}</p>}
          <ul class="rows basket" data-testid="basket-rows">
            {rows.map((r) => (
              <Row key={`${r.family}|${r.zone || ""}`} row={r} n={items.length} />
            ))}
          </ul>
        </>
      )}
      {(data.moreCount || 0) > 0 && (
        <p class="muted small">{data.moreCount === 1 ? t("moreChainOne") : t("moreChains", { n: data.moreCount || 0 })}</p>
      )}

      {data.split && typeof data.split.amount === "number" && (
        <p class="small" data-testid="basket-split">
          {t("basketSplit", { price: money(data.split.amount, locale), n: data.split.chains || 0 })}
          <span class="muted">
            {" · "}
            {t("basketDates", { dates: span(data.split.observedFrom, data.split.observedTo, locale) })}
            {data.split.picks && data.split.picks.length > 0 && (
              <>
                {" · "}
                <span dir="auto">{data.split.picks.map((p, i) => `#${p.item || i + 1} ${p.name}`).join(", ")}</span>
              </>
            )}
          </span>
        </p>
      )}
      {leftOut && rows.length > 0 && (
        <p class="notice" data-testid="basket-left-out">
          {t("basketLeftOut", { items: leftOut })}
        </p>
      )}
      {(data.unmatched || 0) > 0 && (
        <p class="notice" data-testid="basket-unmatched">
          {t("basketUnmatched", { n: data.unmatched || 0 })}
        </p>
      )}
      {rows.length > 0 && <p class="muted small">{t("basketSum")}</p>}
      <p class="muted small">{t("noStock")}</p>

      <CardStrip card={env.card} secondary="save" />
    </div>
  );
}

function Row({ row, n }: { row: BasketRow; n: number }) {
  const { t, locale } = useApp();
  const zone = zoneLabel(row.zone);
  const total = row.total && typeof row.total.amount === "number" ? row.total : null;
  // The amounts and the dates they were observed on share one line (an amount
  // never appears without a date); the first line keeps the chain, the sum
  // and the distance.
  const dist = typeof row.nearestMiles === "number" ? t("miles", { n: miles(row.nearestMiles, locale) }) : "";
  const seen = (row.prices || []).filter(hasPrice).map((p) => p.observedAt).sort();
  const dates = total
    ? span(total.observedFrom, total.observedTo, locale)
    : seen.length
      ? span(seen[0], seen[seen.length - 1], locale)
      : "";
  const missing = total ? "" : t("basketMissing", { items: (row.missing || []).map((i) => `#${i}`).join(", ") });
  const parts = (row.prices || [])
    .map((p, i) => (hasPrice(p) ? `#${i + 1} ${money(p.amount, locale)}` : null))
    .filter(Boolean)
    .join(" · ");
  return (
    <li class="row" data-testid={`basket-row-${row.family}`}>
      <span class="name">
        {row.name}
        {zone && <span class="muted"> ({zone})</span>}
      </span>
      <span class="amt" dir="ltr" title={total ? t("basketTotal", { n: total.count || n }) : undefined}>
        {total ? money(total.amount, locale) : "—"}
      </span>
      <span class="meta">{dist}</span>
      <span class="parts">
        {parts && <span dir="ltr">{parts}</span>}
        {dates && (parts ? " · " : "") + t("basketDates", { dates })}
        {missing && " · " + missing}
      </span>
    </li>
  );
}
