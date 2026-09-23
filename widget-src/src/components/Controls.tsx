// Chips, the "where" field (ZIP, city or address) and the "near {city}
// (approximate) · change location" line — the only inputs an inline card may
// carry (no free-text search inline: that would duplicate the chat box, which
// the ChatGPT guidelines forbid; the search field lives in fullscreen only).

import { useEffect, useRef, useState } from "preact/hooks";
import { useApp } from "../context";
import type { Origin } from "../types";

export interface Chip {
  key: string;
  label: string;
  active: boolean;
  onPick: () => void;
  /** A colour dot before the label (the map legend). */
  swatch?: string;
}

/** Up to `max` chips; the rest (never the active one) in an "Other ▾" select. */
export function ChipRow({ chips, label, max = 4 }: { chips: Chip[]; label: string; max?: number }) {
  const { t, busy } = useApp();
  if (chips.length < 2) return null;
  let shown = chips.slice(0, max);
  const active = chips.find((c) => c.active);
  if (active && !shown.includes(active)) shown = [...shown.slice(0, max - 1), active];
  const rest = chips.filter((c) => !shown.includes(c));

  return (
    <div class="chips" role="group" aria-label={label}>
      {shown.map((c) => (
        <button
          type="button"
          key={c.key}
          class="chip"
          aria-pressed={c.active}
          disabled={busy}
          onClick={() => {
            if (!c.active) c.onPick();
          }}
        >
          {c.swatch && <span class="sw" style={{ background: c.swatch }} aria-hidden="true" />}
          <span dir="ltr">{c.label}</span>
        </button>
      ))}
      {rest.length > 0 && (
        <select
          class="chip"
          aria-label={`${label}: ${t("other")}`}
          disabled={busy}
          value=""
          onChange={(e) => {
            const picked = rest.find((c) => c.key === (e.currentTarget as HTMLSelectElement).value);
            if (picked) picked.onPick();
          }}
        >
          <option value="">{t("other")} ▾</option>
          {rest.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

/** What the "where" field hands back: a ZIP travels as `zip` (every server
 * version takes it); anything else as `where` text, which only the app-only
 * tools accept and the server geocodes — the widget never keeps it. */
export type WhereInput = { zip: string } | { where: string };

export function parseWhere(raw: string): WhereInput | null {
  const text = raw.trim().replace(/\s+/g, " ");
  const zip = /^(\d{5})(?:-\d{4})?$/.exec(text);
  if (zip) return { zip: zip[1] };
  // Digits only but not a ZIP ("787"), too short, or too long: not a place.
  if (/^[\d\s-]+$/.test(text) || text.length < 2 || text.length > 200) return null;
  return { where: text };
}

/** ZIP, city or address (contract C3'); the test ids stay `zip-*`. */
export function WhereField({ onSubmit, autoFocus }: { onSubmit: (where: WhereInput) => void; autoFocus?: boolean }) {
  const { t, busy, userZip } = useApp();
  const input = useRef<HTMLInputElement>(null);
  const [invalid, setInvalid] = useState(false);
  // An address (anything that is not a ZIP) leaves the frame once, for the US
  // Census geocoder — say so under the field before it is sent.
  const [addressLike, setAddressLike] = useState(false);

  useEffect(() => {
    if (!autoFocus) return;
    try {
      input.current?.focus({ preventScroll: true });
    } catch {
      /* ignore */
    }
  }, [autoFocus]);

  function submit(event: Event) {
    event.preventDefault();
    const where = parseWhere(input.current?.value || "");
    setInvalid(!where);
    if (where) onSubmit(where);
  }
  const placeholder = t.alt(["wherePlaceholder", "zipPlaceholder"]);

  return (
    <form class="zip" onSubmit={submit} noValidate>
      <input
        ref={input}
        type="text"
        autocomplete="off"
        maxLength={200}
        dir="auto"
        placeholder={placeholder}
        aria-label={placeholder}
        aria-invalid={invalid}
        defaultValue={userZip || ""}
        data-testid="zip-input"
        onInput={(e) => {
          const where = parseWhere((e.currentTarget as HTMLInputElement).value);
          setAddressLike(!!where && "where" in where);
        }}
      />
      <button type="submit" class="btn small" disabled={busy} data-testid="zip-go">
        {t("zipGo")}
      </button>
      {invalid && (
        <p class="status err" role="alert">
          {t.alt(["whereInvalid", "zipInvalid"])}
        </p>
      )}
      {addressLike && !invalid && (
        <p class="small muted where-note" data-testid="where-note">
          {t("whereNote")}
        </p>
      )}
    </form>
  );
}

/** "Austin, TX" / "78704" — city/state/ZIP only, never an address line. */
export function placeOf(origin: Origin | null | undefined): string {
  return [origin?.city, origin?.state].filter(Boolean).join(", ") || origin?.zip || "";
}

/** "Near Austin, TX (approximate) · change location", or the where field itself. */
export function LocationLine({
  origin,
  needsZip,
  onWhere,
}: {
  origin: Origin | null | undefined;
  needsZip: boolean;
  onWhere: (where: WhereInput) => void;
}) {
  const { t } = useApp();
  const [editing, setEditing] = useState(false);
  const place = placeOf(origin);
  const known = !needsZip && origin?.precision !== "none" && !!place;

  if (!known) {
    return (
      <div class="where">
        <p class="notice">{t.alt(["needsWhere", "needsZip"])}</p>
        <WhereField onSubmit={onWhere} autoFocus={needsZip} />
      </div>
    );
  }
  return (
    <div class="where">
      <p class="muted small">
        {t("nearLabel", { place, city: place })}
        {origin?.precision === "approx" ? ` ${t("approx")}` : ""}
        {" · "}
        <button type="button" class="link" aria-expanded={editing} onClick={() => setEditing(!editing)}>
          {t.alt(["changeWhere", "changeZip"])}
        </button>
      </p>
      {editing && <WhereField onSubmit={onWhere} autoFocus />}
    </div>
  );
}
