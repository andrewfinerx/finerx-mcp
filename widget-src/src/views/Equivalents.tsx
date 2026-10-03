// view=equivalents, inline (MCP 2.2): several medicines from another country.
// One block per medicine: the brand, where it is from, the reviewed sentence
// VERBATIM, and — only when the US sells the same active ingredient — the US
// name with where its card prices start. Nothing is offered in place of a
// medicine the US does not sell. A tap opens that brand's own view.

import { useApp } from "../context";
import { CardStrip, type SecondaryAction } from "../components/CardStrip";
import { day, hasPrice, money } from "../format";
import { cleanArgs } from "../result";
import { personZip } from "./Prices";
import type { Envelope, EquivalentsData } from "../types";

const CLASS_KEY: Record<string, string> = {
  same_inn: "usClassSameInn",
  rx_alternative: "usClassRxAlternative",
  no_equivalent: "usClassNoEquivalent",
};

export function EquivalentsView({ env }: { env: Envelope }) {
  const { t, locale, run, userZip, busy } = useApp();
  const data = (env.data || {}) as EquivalentsData;
  const items = (data.items || []).filter((it) => it && (it.brand || it.inn));
  const zip = personZip(null, userZip);
  // Only the same-ingredient medicines lead on to US prices.
  const priced = items
    .filter((it) => it.usClass === "same_inn" && it.us && typeof it.us.slug === "string")
    .map((it) => it.us!.slug)
    .filter((slug, i, all) => all.indexOf(slug) === i);

  const secondary: SecondaryAction | "save" =
    priced.length > 1
      ? { key: "prices", label: t("pricesInUs"), onClick: () => run("ui_basket", cleanArgs({ slugs: priced, zip })) }
      : priced.length === 1
        ? { key: "prices", label: t("pricesInUs"), onClick: () => run("ui_prices", cleanArgs({ slug: priced[0], zip })) }
        : "save";

  return (
    <div class="view" data-view="equivalents">
      <header class="head">
        <h1 class="title">{t("equivalentsTitle")}</h1>
      </header>

      <ol class="eq-list" data-testid="equivalents">
        {items.map((it, i) => {
          const cls = typeof it.usClass === "string" ? it.usClass : "";
          const us = cls === "same_inn" && it.us && typeof it.us.slug === "string" ? it.us : null;
          const countries = (it.countries || []).filter(Boolean).join(", ");
          return (
            <li class="eq" key={it.brandSlug || `${it.brand}-${i}`} data-testid={`eq-${i + 1}`}>
              <p class="eq-head">
                {it.brandSlug ? (
                  <button type="button" class="link name" disabled={busy} data-testid={`eq-open-${i + 1}`} onClick={() => run("ui_equivalent", { brand_slug: it.brandSlug })}>
                    <span dir="auto">{it.brand || it.inn}</span>
                  </button>
                ) : (
                  <span class="name" dir="auto">{it.brand || it.inn}</span>
                )}
                {countries && <span class="muted small" dir="auto"> · {countries}</span>}
                {CLASS_KEY[cls] && <span class="badge">{t(CLASS_KEY[cls])}</span>}
              </p>
              {it.guidance && (
                <p class="guidance" dir="auto">
                  {it.guidance}
                </p>
              )}
              {us && (
                <p class="small">
                  {t("inUs", { name: us.name })}
                  {hasPrice(us.cardFrom) && (
                    <span class="muted">
                      {" · "}
                      {t("fromWithCard", { price: money(us.cardFrom.amount, locale), date: day(us.cardFrom.observedAt, locale) })}
                    </span>
                  )}
                </p>
              )}
            </li>
          );
        })}
      </ol>

      <p class="notice" data-testid="same-inn-note">
        {t("sameInnNote")}
      </p>
      {(data.unmatched || 0) > 0 && (
        <p class="notice" data-testid="equivalents-unmatched">
          {t("equivalentsUnmatched", { n: data.unmatched || 0 })}
        </p>
      )}

      <CardStrip card={env.card} secondary={secondary} />
    </div>
  );
}
