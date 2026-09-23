// The non-view states every view shares (spec §4.7): loading, error and the
// text fallback for a view this bundle does not know. The card strip stays in
// all of them — the card works whether or not our prices loaded.

import { useApp } from "../context";
import { CardStrip } from "../components/CardStrip";
import type { CardView } from "../types";

export function Loading({ args }: { args: Record<string, unknown> | null }) {
  const { t } = useApp();
  const name = [args?.drug ?? args?.slug, args?.strength].filter((v) => typeof v === "string" && v).join(" ");
  return (
    <div class="view" data-view="loading" aria-busy="true">
      <header class="head">
        <h1 class="title">{name || " "}</h1>
      </header>
      <p class="muted small" role="status">
        {t("loading")}
      </p>
      <ul class="rows skeleton" aria-hidden="true">
        <li class="bar" />
        <li class="bar" />
        <li class="bar" />
      </ul>
      <CardStrip card={null} secondary="save" withLaw={false} />
    </div>
  );
}

export function ErrorState({ card }: { card: CardView | null }) {
  const { t } = useApp();
  return (
    <div class="view" data-view="error">
      <p class="notice" role="alert">
        {t("error")}
      </p>
      <CardStrip card={card} secondary="save" />
    </div>
  );
}

/** A view this bundle does not know (a newer server): the model-facing text as
 * plain text — never HTML — plus the card. */
export function Fallback({ text, card }: { text: string; card: CardView | null }) {
  return (
    <div class="view" data-view="fallback">
      {text && <p class="plain">{text}</p>}
      <CardStrip card={card} secondary="save" />
    </div>
  );
}

/** Nothing from the host yet (or no host at all): the codes still show. The
 * bundled law is English, so other locales wait for the payload's own. */
export function Empty({ english }: { english: boolean }) {
  return (
    <div class="view" data-view="empty">
      <CardStrip card={null} secondary="save" withLaw={english} />
    </div>
  );
}
