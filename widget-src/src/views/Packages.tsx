// view=packages, inline (MCP 2.2): get_drug as a card. Every strength × form
// the card has a price for; under each, its pack sizes with where the card
// prices start (dated) and how many chains priced it. A tap opens that
// package's prices by chain. No per-unit figure: a quantity can count boxes or
// pens, and dividing by it then misleads.

import { useApp } from "../context";
import { CardStrip } from "../components/CardStrip";
import { day, hasPrice, money } from "../format";
import { cleanArgs } from "../result";
import { personZip } from "./Prices";
import type { ConfigOption, Envelope, PackagesData, QuantityOption } from "../types";

const CONFIGS = 6;
const QUANTITIES = 4;

const same = (a?: string, b?: string) => (a || "").trim().toLowerCase() === (b || "").trim().toLowerCase();

export function PackagesView({ env }: { env: Envelope }) {
  const { t, locale, run, userZip, busy } = useApp();
  const data = env.data as PackagesData;
  const drug = data.drug;
  const configs: ConfigOption[] = (data.configs || []).slice(0, CONFIGS);
  const def = data.default || {};
  const zip = personZip(null, userZip);

  function open(c: ConfigOption, q: QuantityOption) {
    return run("ui_prices", cleanArgs({ slug: drug.slug, form: c.form, strength: c.strength, quantity: q.quantity, zip }));
  }

  return (
    <div class="view" data-view="packages">
      <header class="head">
        <h1 class="title" dir="auto">{drug.name}</h1>
      </header>
      {configs.length > 0 ? <p class="caption">{t("packagesTitle")}</p> : <p class="notice">{t("noPrice")}</p>}

      {configs.map((c) => {
        const qs = (c.quantities || []).slice(0, QUANTITIES);
        return (
          <section class="pkg" key={`${c.form}|${c.strength}`} data-testid={`pkg-${c.strength}-${c.form}`}>
            <h2 class="pkg-h" dir="auto">{c.label || [c.strength, c.form].filter(Boolean).join(" ")}</h2>
            <ul class="rows">
              {qs.map((q) => {
                const from = hasPrice(q.cardFrom) ? q.cardFrom : null;
                const isDefault = same(c.form, def.form) && same(c.strength, def.strength) && q.quantity === def.quantity;
                const meta: string[] = [];
                if (from) meta.push(t("observed", { date: day(from.observedAt, locale) }));
                if (typeof q.chainsPriced === "number" && q.chainsPriced > 0) meta.push(t("chainsPriced", { n: q.chainsPriced }));
                return (
                  <li class={`row${isDefault ? " on" : ""}`} key={q.quantity}>
                    <button type="button" class="link name" disabled={busy} data-testid={`pkg-open-${c.strength}-${q.quantity}`} onClick={() => open(c, q)}>
                      <span dir="ltr">{q.label || `${q.quantity}`}</span>
                    </button>
                    <span class="amt" dir="ltr">{from ? money(from.amount, locale) : "—"}</span>
                    <span class="meta">{from ? meta.join(" · ") : t("noPriceShort")}</span>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}

      {(data.moreCount || 0) > 0 && (
        <p class="muted small" data-testid="more-strengths">
          {t("moreStrengths", { n: data.moreCount || 0 })}
        </p>
      )}

      <CardStrip
        card={env.card}
        secondary={{
          key: "prices",
          label: t("pricesWithCard"),
          onClick: () => run("ui_prices", cleanArgs({ slug: drug.slug, form: def.form, strength: def.strength, quantity: def.quantity, zip })),
        }}
      />
    </div>
  );
}
