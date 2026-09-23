// view=equivalent (spec §4.5): a medicine from another country → its active
// ingredient → the US product, the API's guidance sentence VERBATIM, the
// "same ingredient is not the same product" line, then the card. Only a
// `same_inn` entry offers "Prices in the US": for `rx_alternative` and
// `no_equivalent` naming a US product would be naming a substitute.

import { useApp } from "../context";
import { CardStrip } from "../components/CardStrip";
import { day, hasPrice, money } from "../format";
import { cleanArgs } from "../result";
import { personZip } from "./Prices";
import type { EquivalentData, Envelope } from "../types";

const CLASS_KEY: Record<string, string> = {
  same_inn: "usClassSameInn",
  rx_alternative: "usClassRxAlternative",
  no_equivalent: "usClassNoEquivalent",
};

export function EquivalentView({ env }: { env: Envelope }) {
  const { t, locale, run, userZip } = useApp();
  const data = (env.data || {}) as EquivalentData;
  const cls = typeof data.usClass === "string" ? data.usClass : "";
  const us = data.us && typeof data.us.slug === "string" ? data.us : null;
  const priced = cls === "same_inn" && us ? us : null;
  const countries = (data.countries || []).filter(Boolean).join(", ");
  const classLabel = CLASS_KEY[cls] ? t(CLASS_KEY[cls]) : "";
  const zip = personZip(null, userZip);

  return (
    <div class="view" data-view="equivalent">
      <header class="head">
        <h1 class="title" dir="auto">
          {data.brand || data.inn || t("equivalentUs")}
        </h1>
        {countries && (
          <p class="sub" dir="auto">
            {countries}
          </p>
        )}
      </header>

      <ol class="flow" aria-label={t("equivalentUs")}>
        <li class="flow-step">
          <span class="flow-k">{t("foreignBrand")}</span>
          <span class="flow-v" dir="auto">
            {data.brand || "—"}
          </span>
        </li>
        {data.inn && (
          <li class="flow-step">
            <span class="flow-k">{t("inn")}</span>
            <span class="flow-v" dir="auto">
              {data.inn}
            </span>
          </li>
        )}
        <li class={`flow-step${priced ? " us" : " none"}`} data-testid="flow-us">
          <span class="flow-k">{t("equivalentUs")}</span>
          <span class="flow-v" dir="auto">
            {priced ? priced.name : classLabel || "—"}
          </span>
        </li>
      </ol>

      {classLabel && priced && <p class="badge-line"><span class="badge">{classLabel}</span></p>}

      {data.guidance && (
        <p class="guidance" dir="auto" data-testid="guidance">
          {data.guidance}
        </p>
      )}
      <p class="notice" data-testid="same-inn-note">
        {(typeof data.disclaimer === "string" && data.disclaimer.trim()) || t("sameInnNote")}
      </p>

      {priced && hasPrice(priced.cardFrom) && (
        <p class="headline">
          {priced.name}:{" "}
          {t("fromWithCard", { price: money(priced.cardFrom.amount, locale), date: day(priced.cardFrom.observedAt, locale) })}
        </p>
      )}

      <CardStrip
        card={env.card}
        secondary={
          priced
            ? {
                key: "prices-us",
                label: t("pricesInUs"),
                onClick: () => void run("ui_prices", cleanArgs({ slug: priced.slug, zip })),
              }
            : "save"
        }
      />
    </div>
  );
}
