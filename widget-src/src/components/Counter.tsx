// "Show at the counter": the codes as a pharmacist reads them off a phone held
// across the counter — large monospace, maximum contrast, nothing else to tap.
// The host is asked for fullscreen; when it refuses, this still replaces the
// view in place (the overlay fallback), so the mode works in every host.

import { useEffect, useRef } from "preact/hooks";
import { useApp } from "../context";
import { codesOf } from "../card";
import { day, hasPrice, money } from "../format";
import type { CardView } from "../types";

export function Counter({ card, onClose }: { card: CardView | null | undefined; onClose: () => void }) {
  const { t, locale } = useApp();
  const codes = codesOf(card);
  const close = useRef<HTMLButtonElement>(null);
  const pwc = card?.priceWithCard;

  useEffect(() => {
    try {
      close.current?.focus({ preventScroll: true });
    } catch {
      /* ignore */
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div class="counter" role="dialog" aria-modal="true" aria-label={t("showAtCounter")} data-testid="counter">
      <button type="button" class="btn counter-close" ref={close} onClick={onClose}>
        {t("close")}
      </button>
      <dl class="counter-codes" dir="ltr">
        <div>
          <dt>RxBIN</dt>
          <dd>{codes.bin}</dd>
        </div>
        <div>
          <dt>RxPCN</dt>
          <dd>{codes.pcn}</dd>
        </div>
        <div>
          <dt>RxGRP</dt>
          <dd>{codes.group}</dd>
        </div>
      </dl>
      {pwc && hasPrice(pwc) && (
        <p class="counter-price">
          <span dir="ltr">{money(pwc.amount, locale)}</span> {t("withCard")}
          {pwc.name ? ` · ${pwc.name}` : ""} · {t("observed", { date: day(pwc.observedAt, locale) })}
        </p>
      )}
      <p class="counter-ni">{t("notInsurance")}</p>
    </div>
  );
}
