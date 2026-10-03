// view=transfer, inline (MCP 2.2): moving a prescription to the chain the
// person picked. The chain's dated card price (when a medicine was named), the
// steps and notes exactly as the server sent them (its own fixed sentences),
// the nearest stores of that chain with directions, then the card. A
// controlled or age-restricted medicine shows only the note and the card.

import { useApp } from "../context";
import { CardStrip, type SecondaryAction } from "../components/CardStrip";
import { day, hasPrice, miles, money } from "../format";
import { cleanArgs } from "../result";
import { mapsUrl } from "./Pharmacies";
import { personZip } from "./Prices";
import type { Envelope, TransferData } from "../types";

export function TransferView({ env }: { env: Envelope }) {
  const { t, locale, run, userZip, bridge } = useApp();
  const data = (env.data || {}) as TransferData;
  const chain = data.chain && typeof data.chain.name === "string" ? data.chain : null;
  const steps = (data.steps || []).filter((s) => typeof s === "string" && s.trim());
  const notes = (data.notes || []).filter((s) => typeof s === "string" && s.trim());
  const stores = (data.stores || []).slice(0, 3);
  const drug = data.drug && typeof data.drug.slug === "string" ? data.drug : null;
  const pkg = data.package || {};
  const zip = personZip(data.origin, userZip);

  if (data.restricted) {
    return (
      <div class="view" data-view="transfer">
        <header class="head">
          <h1 class="title">{t("transferTitleAny")}</h1>
        </header>
        <p class="notice" data-testid="transfer-restricted">
          {(typeof data.note === "string" && data.note.trim()) || t("rxRestricted")}
        </p>
        <CardStrip card={env.card} secondary="save" />
      </div>
    );
  }

  const secondary: SecondaryAction | "save" = drug
    ? {
        key: "prices",
        label: t("pricesWithCard"),
        onClick: () => run("ui_prices", cleanArgs({ slug: drug.slug, form: pkg.form, strength: pkg.strength, quantity: pkg.quantity, zip })),
      }
    : "save";

  return (
    <div class="view" data-view="transfer">
      <header class="head">
        <h1 class="title" dir="auto">{chain ? t("transferTitle", { name: chain.name }) : t("transferTitleAny")}</h1>
      </header>

      {drug && chain && hasPrice(data.price) && (
        <p class="headline" data-testid="transfer-price">
          <span dir="auto">{drug.name}</span>
          {pkg.label && <span class="muted" dir="auto"> · {pkg.label}</span>}
          {": "}
          <strong dir="ltr">{money(data.price.amount, locale)}</strong> {t("withCard")}
          <span class="muted"> · {t("observed", { date: day(data.price.observedAt, locale) })}</span>
        </p>
      )}

      <ol class="steps" data-testid="transfer-steps">
        {steps.map((s, i) => (
          <li key={i} dir="auto">
            {s}
          </li>
        ))}
      </ol>
      {notes.length > 0 && (
        <ul class="notes muted small" data-testid="transfer-notes">
          {notes.map((n, i) => (
            <li key={i} dir="auto">
              {n}
            </li>
          ))}
        </ul>
      )}

      {stores.length > 0 && (
        <>
          <p class="caption">{t("transferStores")}</p>
          <ul class="rows stores" data-testid="transfer-stores">
            {stores.map((s, i) => (
              <li class="row" key={`${s.address}-${i}`}>
                <span class="name" dir="auto">{s.name}</span>
                <span class="amt small" dir="ltr">{typeof s.miles === "number" ? t("miles", { n: miles(s.miles, locale) }) : ""}</span>
                <span class="meta">
                  <span dir="auto">{[s.address, s.city].filter(Boolean).join(", ")}</span>
                  {s.kind === "store" ? ` · ${t("storeInStore")}` : ""}
                  {" · "}
                  <button type="button" class="link" data-testid="transfer-directions" onClick={() => bridge.openLink(mapsUrl(s))}>
                    {t("directions")}
                  </button>
                </span>
              </li>
            ))}
          </ul>
          <p class="muted small">{t("noStock")}</p>
        </>
      )}

      <CardStrip card={env.card} secondary={secondary} />
    </div>
  );
}
