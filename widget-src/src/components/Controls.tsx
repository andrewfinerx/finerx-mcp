// Chips, the ZIP field and the "near {city} (approximate) · change ZIP" line —
// the only inputs an inline card may carry (no free-text search: that would
// duplicate the chat box, which the ChatGPT guidelines forbid).

import { useEffect, useRef, useState } from "preact/hooks";
import { useApp } from "../context";
import type { Origin } from "../types";

export interface Chip {
  key: string;
  label: string;
  active: boolean;
  onPick: () => void;
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

export function ZipField({ onSubmit, autoFocus }: { onSubmit: (zip: string) => void; autoFocus?: boolean }) {
  const { t, busy, userZip } = useApp();
  const input = useRef<HTMLInputElement>(null);
  const [invalid, setInvalid] = useState(false);

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
    const zip = (input.current?.value || "").trim();
    if (!/^\d{5}$/.test(zip)) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    onSubmit(zip);
  }

  return (
    <form class="zip" onSubmit={submit} noValidate>
      <input
        ref={input}
        type="text"
        inputMode="numeric"
        autocomplete="postal-code"
        maxLength={5}
        pattern="[0-9]{5}"
        dir="ltr"
        placeholder={t("zipPlaceholder")}
        aria-label={t("zipPlaceholder")}
        aria-invalid={invalid}
        defaultValue={userZip || ""}
        data-testid="zip-input"
      />
      <button type="submit" class="btn small" disabled={busy} data-testid="zip-go">
        {t("zipGo")}
      </button>
      {invalid && (
        <p class="status err" role="alert">
          {t("zipInvalid")}
        </p>
      )}
    </form>
  );
}

/** "Near Austin, TX (approximate) · change ZIP", or the ZIP field itself. */
export function LocationLine({
  origin,
  needsZip,
  onZip,
}: {
  origin: Origin | undefined;
  needsZip: boolean;
  onZip: (zip: string) => void;
}) {
  const { t } = useApp();
  const [editing, setEditing] = useState(false);
  const place = [origin?.city, origin?.state].filter(Boolean).join(", ") || origin?.zip || "";
  const known = !needsZip && origin?.precision !== "none" && !!place;

  if (!known) {
    return (
      <div class="where">
        <p class="notice">{t("needsZip")}</p>
        <ZipField onSubmit={onZip} autoFocus={needsZip} />
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
          {t("changeZip")}
        </button>
      </p>
      {editing && <ZipField onSubmit={onZip} autoFocus />}
    </div>
  );
}
