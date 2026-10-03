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
      <CardQr rows={data.qr && data.qr.rows} label={t("qrScan")} />
      <CardStrip card={env.card} secondary="save" face={false} />
    </div>
  );
}

/** The card page as a QR, drawn from the server's module rows (nothing is
 * fetched). Always dark on white with a quiet zone — a scanner needs that in
 * dark mode too. Square rows of "0"/"1" only; anything else draws nothing. */
export function qrPath(rows: unknown): { d: string; size: number } | null {
  if (!Array.isArray(rows) || rows.length < 21 || rows.length > 61) return null;
  const n = rows.length;
  let d = "";
  for (let y = 0; y < n; y++) {
    const row = rows[y];
    if (typeof row !== "string" || row.length !== n || /[^01]/.test(row)) return null;
    for (let x = 0; x < n; x++) if (row[x] === "1") d += `M${x} ${y}h1v1h-1z`;
  }
  return { d, size: n };
}

function CardQr({ rows, label }: { rows: unknown; label: string }) {
  const qr = qrPath(rows);
  if (!qr) return null;
  const pad = 2;
  return (
    <div class="qr" data-testid="card-qr">
      <svg viewBox={`${-pad} ${-pad} ${qr.size + pad * 2} ${qr.size + pad * 2}`} width="112" height="112" role="img" aria-label={label} shape-rendering="crispEdges">
        <rect x={-pad} y={-pad} width={qr.size + pad * 2} height={qr.size + pad * 2} fill="#fff" />
        <path d={qr.d} fill="#000" />
      </svg>
      <p class="small muted">{label}</p>
    </div>
  );
}
