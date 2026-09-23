// view=card (spec §4.4): the price the card was seen at, if any, then the card
// strip with "Show at the counter" + "Save ▾" (Wallet, print, email, SMS).

import { useApp } from "../context";
import { CardStrip, CodesLine } from "../components/CardStrip";
import { codesOf } from "../card";
import { day, hasPrice, money } from "../format";
import type { CardData, Envelope } from "../types";

export function CardViewPage({ env }: { env: Envelope }) {
  const { t, locale } = useApp();
  const data = (env.data || {}) as CardData;
  const pwc = data.priceWithCard || env.card?.priceWithCard || null;
  const codes = codesOf(env.card);
  return (
    <div class="view" data-view="card">
      {data.drug?.name && (
        <header class="head">
          <h1 class="title" dir="auto">{data.drug.name}</h1>
        </header>
      )}
      {pwc && hasPrice(pwc) && (
        <p class="headline">
          <span class="amt big" dir="ltr">
            {money(pwc.amount, locale)}
          </span>{" "}
          {t("withCard")}
          {pwc.name ? ` · ${pwc.name}` : ""} · {t("observed", { date: day(pwc.observedAt, locale) })}
        </p>
      )}
      <CodesLine bin={codes.bin} pcn={codes.pcn} group={codes.group} full />
      <section class="howto" aria-label={t("howToTitle")}>
        <p class="caption">{t("howToTitle")}</p>
        <ol>
          <li>{t("step1")}</li>
          <li>{t("step2")}</li>
          <li>{t("step3")}</li>
        </ol>
      </section>
      <CardStrip card={env.card} secondary="save" face={false} />
    </div>
  );
}
