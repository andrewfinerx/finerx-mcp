// "Show at the counter": the codes as a pharmacist reads them off a phone held
// across the counter — large monospace, maximum contrast, nothing else to tap.
// The host is asked for fullscreen; when it refuses, this still replaces the
// view in place (the overlay fallback), so the mode works in every host.
//
// No price here (owner, 2026-11-21): this is the card, the screen a person also
// screenshots, and a price on it outlives the day it was seen. The dated price
// stays in the price views and in the law beside the card.

import { useEffect, useRef } from "preact/hooks";
import { useApp } from "../context";
import { codesOf } from "../card";
import type { CardView } from "../types";

// The Member / Cardholder ID, for the pharmacist: in English, like RxBIN/RxPCN/
// RxGRP — the screen faces a US counter. Counters ask for a Member ID before
// they run the card, and this card has no member number: the program's
// Cardholder ID is the patient's own 10-digit phone (LowerMyRx's card for
// MYCARD3993; FineRx support, 2026-11-20). The same words as the site's strip.
export const PHARMACIST_MEMBER_LABEL = "Member / Cardholder ID";
export const PHARMACIST_MEMBER_HINT = "Patient's 10-digit phone";

export function Counter({ card, onClose }: { card: CardView | null | undefined; onClose: () => void }) {
  const { t } = useApp();
  const codes = codesOf(card);
  const close = useRef<HTMLButtonElement>(null);
  // The person's own language gets a line of its own ("Member ID: your 10-digit
  // phone number") when the card is shown in one that is not English.
  const ownLanguage = t("memberIdHint") !== PHARMACIST_MEMBER_HINT;

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
      <div class="counter-member" data-testid="counter-member">
        <p class="counter-mk" dir="ltr">
          {PHARMACIST_MEMBER_LABEL}
        </p>
        <p class="counter-mh" dir="ltr">
          {PHARMACIST_MEMBER_HINT}
        </p>
        {ownLanguage && (
          <p class="counter-mline" dir="auto" data-testid="counter-member-own">
            {t("memberIdLine")}
          </p>
        )}
      </div>
      <p class="counter-ni">{t("notInsurance")}</p>
    </div>
  );
}
