// view=search (spec §4.2, contract C3'): "a card you type into". Fullscreen:
// the search field (debounce 250 ms, >= 2 characters → `ui_suggest`), results
// with "with card from $X · date", foreign brands badged "→ US", "Often
// searched", the "where" field, then the card. Picking a medicine calls
// `ui_prices` and the prices view replaces this one in the same frame (the app
// keeps this view for "Back to search"). A foreign brand opens the equivalent
// view (`ui_equivalent`) — guidance word for word, "same ingredient is not the
// same product" — and "Prices in the US" goes on from there. The card strip
// is the one `ui_suggest` returned with the results (the law loses its
// adjectives when a restricted medicine is among them). Inline (the host refused fullscreen):
// no free-text field — the chat box is the input there (ChatGPT's "no duplicate
// inputs") — only the suggestions we already hold, "Often searched" and a
// "Search" button that asks for fullscreen again.

import { useEffect, useRef, useState } from "preact/hooks";
import { useApp } from "../context";
import { CardStrip } from "../components/CardStrip";
import { WhereField, placeOf, type WhereInput } from "../components/Controls";
import { day, hasPrice, money } from "../format";
import { cleanArgs } from "../result";
import { personZip } from "./Prices";
import type { CardView, Envelope, ForeignBrand, SearchData, Suggestion, SuggestResult } from "../types";

const DEBOUNCE_MS = 250;
const MIN_CHARS = 2;
const INLINE_SUGGESTIONS = 5;
const MAX_SUGGESTIONS = 8;

/** Envelopes whose fullscreen we already asked for — once, not on every re-mount
 * (coming back from prices re-mounts this view). */
const asked = new WeakSet<object>();

/** What the person had typed and seen, per search envelope, so "Back to
 * search" returns to it. Memory only, dropped with the envelope; an address
 * typed in "where" is not kept here. */
interface Memo {
  query: string;
  found: SuggestResult;
  card: CardView | null;
  zip: string | null;
}
const memo = new WeakMap<object, Memo>();

const isObject = (v: unknown): v is Record<string, any> => typeof v === "object" && v !== null && !Array.isArray(v);

/** The card `ui_suggest` sent with its results (its law matches THEM), if any. */
export function cardOf(sc: unknown): CardView | null {
  const card = isObject(sc) ? sc.card : null;
  return isObject(card) && isObject(card.codes) ? (card as CardView) : null;
}

/** `ui_suggest` answers `{results, foreignBrands}` in structuredContent (or in
 * an envelope's `data`); anything else reads as "nothing found". */
export function suggestionsOf(sc: unknown): SuggestResult {
  const body = isObject(sc) && isObject(sc.data) && !Array.isArray(sc.results) ? sc.data : sc;
  if (!isObject(body)) return { results: [], foreignBrands: [] };
  const results = Array.isArray(body.results) ? body.results.filter((r: any) => isObject(r) && typeof r.slug === "string") : [];
  const foreign = Array.isArray(body.foreignBrands) ? body.foreignBrands.filter((b: any) => isObject(b) && typeof b.brand === "string") : [];
  return { results: results.slice(0, MAX_SUGGESTIONS), foreignBrands: foreign.slice(0, MAX_SUGGESTIONS) };
}

export function SearchView({ env }: { env: Envelope }) {
  const { t, locale, bridge, run, busy, display, goFullscreen, userZip } = useApp();
  const data = (env.data || {}) as SearchData;
  const initial: SuggestResult = {
    results: (data.suggestions || data.results || []).slice(0, MAX_SUGGESTIONS),
    foreignBrands: (data.foreignBrands || []).slice(0, MAX_SUGGESTIONS),
  };
  const full = display === "fullscreen";
  const saved = memo.get(env);
  const [query, setQuery] = useState(saved ? saved.query : (data.query || "").trim());
  const [found, setFound] = useState<SuggestResult>(saved ? saved.found : initial);
  // null = the card of the answer that opened the search
  const [card, setCard] = useState<CardView | null>(saved ? saved.card : null);
  const [searching, setSearching] = useState(false);
  const [failed, setFailed] = useState(false);
  const [where, setWhere] = useState<WhereInput | null>(saved && saved.zip ? { zip: saved.zip } : null);
  const [editingWhere, setEditingWhere] = useState(false);
  const seq = useRef(0);
  const input = useRef<HTMLInputElement>(null);

  // open_price_finder asks for fullscreen; a refusal leaves the inline variant.
  useEffect(() => {
    if (display === "fullscreen" || asked.has(env)) return;
    asked.add(env);
    void goFullscreen();
  }, [env]);

  useEffect(() => {
    if (!full) return;
    try {
      input.current?.focus({ preventScroll: true });
    } catch {
      /* ignore */
    }
  }, [full]);

  useEffect(() => {
    memo.set(env, { query, found, card, zip: where && "zip" in where ? where.zip : null });
  }, [env, query, found, card, where]);

  const first = useRef(true);
  useEffect(() => {
    // Coming back to a remembered search: its results are already on screen.
    if (first.current) {
      first.current = false;
      if (saved) return;
    }
    const q = query.trim();
    const mine = ++seq.current;
    if (q === (data.query || "").trim() || q.length < MIN_CHARS) {
      // The server's own answer for its query; nothing for a stub.
      setFound(q === (data.query || "").trim() ? initial : { results: [], foreignBrands: [] });
      setCard(null);
      setSearching(false);
      setFailed(false);
      return;
    }
    setSearching(true);
    const timer = setTimeout(async () => {
      try {
        const out = await bridge.callTool("ui_suggest", { q, locale });
        if (mine !== seq.current) return;
        setFound(out && !out.isError ? suggestionsOf(out.structuredContent) : { results: [], foreignBrands: [] });
        setCard(out ? cardOf(out.structuredContent) : null);
        setFailed(!out || !!out.isError);
      } catch {
        if (mine === seq.current) setFailed(true);
      } finally {
        if (mine === seq.current) setSearching(false);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  // Where the prices will be for: what the person typed here, else a ZIP they
  // gave before, else nothing (the host's own location goes with the call).
  const place = where || (personZip(data.origin, userZip) ? { zip: personZip(data.origin, userZip) as string } : null);
  function pick(slug: string) {
    return run("ui_prices", cleanArgs({ slug, ...(place || {}) }), { typed: !!where });
  }
  // Every foreign brand opens its equivalent view — also rx_alternative and
  // no_equivalent, whose guidance is the answer.
  function pickForeign(brandSlug: string) {
    return run("ui_equivalent", { brand_slug: brandSlug, locale });
  }
  function setPlace(w: WhereInput) {
    setWhere(w);
    setEditingWhere(false);
    // Only a ZIP reaches the model; an address stays in this frame.
    if ("zip" in w) bridge.updateModelContext(`The person set the location to ZIP ${w.zip} in the FineRx search.`);
  }

  const results = found.results || [];
  const foreign = found.foreignBrands || [];
  const shownResults = full ? results : results.slice(0, INLINE_SUGGESTIONS);
  const shownForeign = full ? foreign : foreign.slice(0, Math.max(0, INLINE_SUGGESTIONS - shownResults.length));
  const popular = (data.popular || []).filter((p) => p && typeof p.slug === "string").slice(0, 8);
  const typed = query.trim().length >= MIN_CHARS;
  const nothing = full && typed && !searching && !failed && !results.length && !foreign.length;

  const knownPlace = placeOf(data.origin);
  const whereText = where ? ("zip" in where ? where.zip : where.where) : knownPlace;

  return (
    <div class="view" data-view="search" data-mode={full ? "full" : "inline"}>
      <header class="head">
        <h1 class="title">{t("searchTitle")}</h1>
        {!full && (
          <button type="button" class="btn small head-btn" data-testid="open-search" onClick={() => void goFullscreen()}>
            {t("openSearch")}
          </button>
        )}
      </header>

      {full && (
        <div class="search-box">
          <input
            ref={input}
            type="search"
            class="search-input"
            dir="auto"
            autocomplete="off"
            spellcheck={false}
            maxLength={80}
            value={query}
            placeholder={t("searchPlaceholder")}
            aria-label={t("searchPlaceholder")}
            data-testid="search-input"
            onInput={(e) => setQuery((e.currentTarget as HTMLInputElement).value)}
          />
          {searching && (
            <span class="muted small search-status" role="status">
              {t("searching")}
            </span>
          )}
        </div>
      )}

      {popular.length > 0 && (
        <div class="popular">
          <span class="small muted">{t("popular")}</span>{" "}
          <span class="chips inline-chips">
            {popular.map((p) => (
              <button type="button" class="chip" key={p.slug} disabled={busy} data-testid={`popular-${p.slug}`} onClick={() => pick(p.slug)}>
                <span dir="auto">{p.name}</span>
              </button>
            ))}
          </span>
        </div>
      )}

      {(shownResults.length > 0 || shownForeign.length > 0) && (
        <ul class="results" data-testid="search-results">
          {shownResults.map((s) => (
            <ResultRow key={s.slug} item={s} onPick={() => pick(s.slug)} />
          ))}
          {shownForeign.map((b) => (
            <ForeignRow key={b.brandSlug || b.brand} item={b} onPick={b.brandSlug ? () => pickForeign(b.brandSlug as string) : undefined} />
          ))}
        </ul>
      )}
      {nothing && (
        <p class="notice" role="status">
          {t("noResults")}
        </p>
      )}
      {failed && (
        <p class="notice err" role="alert">
          {t("actionError")}
        </p>
      )}

      <div class="where search-where">
        {whereText && !editingWhere ? (
          <p class="small">
            <span class="muted">{t("where")}</span> <span dir="auto">{whereText}</span>
            {!where && data.origin?.precision === "approx" ? ` ${t("approx")}` : ""}
            {" · "}
            <button type="button" class="link" onClick={() => setEditingWhere(true)}>
              {t.alt(["changeWhere", "changeZip"])}
            </button>
          </p>
        ) : (
          <>
            <p class="small muted">{t("where")}</p>
            <WhereField onSubmit={setPlace} autoFocus={editingWhere} />
          </>
        )}
      </div>

      <CardStrip card={card || env.card} secondary="save" />
    </div>
  );
}

function kindLabel(kind: string | undefined, t: ReturnType<typeof useApp>["t"]): string {
  if (kind === "generic") return t("kindGeneric");
  if (kind === "brand") return t("kindBrand");
  return "";
}

function ResultRow({ item, onPick }: { item: Suggestion; onPick: () => void }) {
  const { t, locale, busy } = useApp();
  const kind = kindLabel(item.kind, t);
  return (
    <li>
      <button type="button" class="result" disabled={busy} data-testid={`result-${item.slug}`} onClick={onPick}>
        <span class="r-name" dir="auto">
          {item.name}
          {item.matchedAlias && item.matchedAlias.toLowerCase() !== item.name.toLowerCase() && (
            <span class="muted r-alias"> · {item.matchedAlias}</span>
          )}
        </span>
        {kind && <span class="r-kind muted small">{kind}</span>}
        <span class="r-price small">
          {hasPrice(item.cardFrom) ? (
            t("fromWithCard", { price: money(item.cardFrom.amount, locale), date: day(item.cardFrom.observedAt, locale) })
          ) : (
            <span class="muted">{t("noPriceShort")}</span>
          )}
        </span>
        <span class="r-go" aria-hidden="true">
          ›
        </span>
      </button>
    </li>
  );
}

function ForeignRow({ item, onPick }: { item: ForeignBrand; onPick?: () => void }) {
  const { t, busy } = useApp();
  const countries = (item.countries || []).filter(Boolean).join(", ");
  const body = (
    <>
      <span class="r-name" dir="auto">
        {item.brand}
        {countries && <span class="muted"> ({countries})</span>}
      </span>
      <span class="badge">{t("foreignBrand")}</span>
      <span class="r-price small">
        {item.usSlug ? t("inUs", { name: item.usName || item.usSlug }) : <span class="muted">{t("noUsProduct")}</span>}
      </span>
      <span class="r-go" aria-hidden="true">
        {onPick ? "›" : ""}
      </span>
    </>
  );
  return (
    <li>
      {onPick ? (
        <button type="button" class="result foreign" disabled={busy} data-testid={`foreign-${item.brandSlug || item.brand}`} onClick={onPick}>
          {body}
        </button>
      ) : (
        <div class="result foreign static" data-testid={`foreign-${item.brandSlug || item.brand}`}>
          {body}
        </div>
      )}
    </li>
  );
}
