// view=rx (spec §4.6): how to get a prescription — the API's sections as they
// are (title, body, official links opened through the host), the card price
// with its date, "Prices with the card" → `ui_prices`, the card. A restricted
// medicine (controlled / age-restricted) shows ONE sentence — card prices and
// the card only, see a licensed clinician — and no route to a prescription.

import { useApp } from "../context";
import { CardStrip } from "../components/CardStrip";
import { day, hasPrice, money } from "../format";
import { cleanArgs } from "../result";
import { personZip } from "./Prices";
import type { Envelope, RxData, RxLink } from "../types";

/** Only web links leave the frame, and only through the host. */
const safeUrl = (url: unknown): url is string => typeof url === "string" && /^https:\/\/[^\s]+$/i.test(url);

export function RxView({ env }: { env: Envelope }) {
  const { t, locale, run, bridge, userZip } = useApp();
  const data = (env.data || {}) as RxData;
  const drug = data.drug && typeof data.drug.slug === "string" ? data.drug : null;
  const restricted = data.restricted === true;
  const sections = restricted ? [] : (data.sections || []).filter((s) => s && (s.title || s.body));
  const zip = personZip(null, userZip);

  return (
    <div class="view" data-view="rx" data-restricted={restricted ? "true" : undefined}>
      <header class="head">
        <h1 class="title" dir="auto">
          {/* A restricted medicine gets no "how to get a prescription" heading. */}
          {restricted && drug?.name ? drug.name : drug?.name ? t("rxTitle", { name: drug.name }) : t("rxTitleAny")}
        </h1>
      </header>

      {restricted ? (
        <p class="notice" data-testid="rx-restricted">
          {(typeof data.note === "string" && data.note.trim()) || t("rxRestricted")}
        </p>
      ) : (
        <ol class="rx-sections" data-testid="rx-sections">
          {sections.map((s, i) => (
            <li class="rx-sec" key={`${i}|${s.title || ""}`}>
              {s.title && (
                <h2 class="rx-title" dir="auto">
                  {s.title}
                </h2>
              )}
              {s.body && (
                <p class="plain rx-body" dir="auto">
                  {s.body}
                </p>
              )}
              {(s.links || []).filter((l: RxLink) => l && l.label && safeUrl(l.url)).length > 0 && (
                <div class="rx-links">
                  {(s.links || [])
                    .filter((l: RxLink) => l && l.label && safeUrl(l.url))
                    .map((l: RxLink) => (
                      <button
                        type="button"
                        class="link rx-link"
                        key={l.url}
                        data-testid="rx-link"
                        onClick={() => void bridge.openLink(l.url)}
                      >
                        {l.label} <span aria-hidden="true">↗</span>
                      </button>
                    ))}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}

      {hasPrice(data.cardFrom) && (
        <p class="headline">
          <span class="muted">{t("withoutInsurance")}</span>{" "}
          {t("fromWithCard", { price: money(data.cardFrom.amount, locale), date: day(data.cardFrom.observedAt, locale) })}
        </p>
      )}

      <CardStrip
        card={env.card}
        secondary={
          drug
            ? {
                key: "prices-card",
                label: t("pricesWithCard"),
                onClick: () => void run("ui_prices", cleanArgs({ slug: drug.slug, zip })),
              }
            : "save"
        }
      />
    </div>
  );
}
