// The card, in EVERY view (host rule 1): codes with copy, the card law exactly
// as the payload words it, two buttons, the small print. It is a way to get the
// price on screen, not a banner — so it sits after the answer, never above it.

import { useRef, useState } from "preact/hooks";
import type { ComponentChildren } from "preact";
import { useApp } from "../context";
import { FALLBACK_LAW, codesOf } from "../card";
import type { CardView } from "../types";

export interface SecondaryAction {
  key: string;
  label: string;
  onClick: () => void;
}

interface Props {
  card: CardView | null | undefined;
  /** The second of the two inline buttons: a view's own next step
   * ("Prices in the US", "Prices with the card") or Save ▾. */
  secondary: "allPharmacies" | "save" | SecondaryAction;
  onAllPharmacies?: () => void;
  /** Loading has no law yet — it arrives with the data, in the person's language. */
  withLaw?: boolean;
  /** The card view draws the full face above; the strip then shows the law and buttons only. */
  face?: boolean;
}

export function CardStrip({ card, secondary, onAllPharmacies, withLaw = true, face = true }: Props) {
  const { t, openCounter, busy } = useApp();
  const codes = codesOf(card);
  const law = (card && typeof card.law === "string" && card.law.trim()) || FALLBACK_LAW;
  const fine = (card && typeof card.fine === "string" && card.fine.trim()) || t("notInsurance");
  const [saveOpen, setSaveOpen] = useState(false);

  return (
    <section class="strip" data-testid="card-strip">
      <div class={face ? "strip-top" : "strip-top noface"}>
        {face && <CodesLine bin={codes.bin} pcn={codes.pcn} group={codes.group} />}
        {withLaw && (
          <p class="law" data-testid="card-law">
            {law}
          </p>
        )}
      </div>
      <div class="actions">
        <button type="button" class="btn primary" onClick={openCounter}>
          {t("showAtCounter")}
        </button>
        {typeof secondary === "object" ? (
          <button type="button" class="btn" disabled={busy} data-testid={`action-${secondary.key}`} onClick={secondary.onClick}>
            {secondary.label}
          </button>
        ) : secondary === "allPharmacies" ? (
          <button type="button" class="btn" disabled={busy} onClick={onAllPharmacies}>
            {t("allPharmacies")}
          </button>
        ) : (
          <button
            type="button"
            class="btn"
            aria-expanded={saveOpen}
            data-testid="save-toggle"
            onClick={() => setSaveOpen(!saveOpen)}
          >
            {t("save")} <span aria-hidden="true">▾</span>
          </button>
        )}
      </div>
      {secondary === "save" && saveOpen && <SaveMenu card={card} />}
      <p class="fine" data-testid="card-fine">
        {fine}
      </p>
    </section>
  );
}

// A faint treeline of ROUND crowns along the foot of the teal face — the site's
// card (apps/web SavingsCard, owner pick 2026-11-21, canvas variant E2 "soft
// treeline"). Two layers in white, the back canopy at 6 %, the front at 10 %,
// each drawn as ONE group so overlapping crowns do not stack their opacity; the
// site's 416×70 box, scaled with the aspect kept so the crowns stay round.
type Crown = readonly [cx: number, cy: number, r: number];
const CANOPY_BACK: readonly Crown[] = [
  [-4, 44, 16], [22, 40, 17], [50, 43, 15], [76, 38, 18], [104, 42, 16],
  [130, 45, 14], [156, 39, 18], [184, 42, 16], [212, 46, 14], [238, 40, 17],
  [266, 43, 15], [292, 37, 19], [322, 42, 16], [348, 45, 14], [374, 40, 17],
  [402, 43, 16], [424, 46, 14],
];
// Three taller round trees standing out of the back canopy: crown + trunk.
const TALL_TREES: readonly (readonly [cx: number, cy: number, r: number, trunkTop: number, trunkH: number])[] = [
  [118, 20, 11, 28, 14],
  [262, 17, 12, 26, 14],
  [390, 22, 10, 29, 12],
];
const CANOPY_FRONT: readonly Crown[] = [
  [10, 58, 18], [52, 54, 22], [98, 60, 17], [140, 55, 21], [186, 59, 18],
  [230, 53, 23], [276, 60, 17], [318, 55, 21], [362, 58, 19], [406, 54, 22],
];

function Treeline() {
  return (
    <svg class="cf-trees" aria-hidden="true" viewBox="0 0 416 70" preserveAspectRatio="xMidYMax meet">
      <g fill="#fff" opacity="0.06">
        <rect x="0" y="46" width="416" height="24" />
        {CANOPY_BACK.map(([cx, cy, r]) => (
          <circle key={`b${cx}`} cx={cx} cy={cy} r={r} />
        ))}
        {TALL_TREES.map(([cx, cy, r, trunkTop, trunkH]) => (
          <g key={`t${cx}`}>
            <circle cx={cx} cy={cy} r={r} />
            <rect x={cx - 1.25} y={trunkTop} width="2.5" height={trunkH} />
          </g>
        ))}
      </g>
      <g fill="#fff" opacity="0.1">
        <rect x="0" y="58" width="416" height="12" />
        {CANOPY_FRONT.map(([cx, cy, r]) => (
          <circle key={`f${cx}`} cx={cx} cy={cy} r={r} />
        ))}
      </g>
    </svg>
  );
}

/** The slim white strip at the foot of the card, for the pharmacist (site
 * variant E2): counters ask for a Member ID before they run the card, and this
 * card has no member number — the program's Cardholder ID is the patient's own
 * 10-digit phone (LowerMyRx's card for group MYCARD3993 says so; FineRx support,
 * 2026-11-20). The label over the hint, and a line to write the number on, for
 * the person who prints or screenshots the card. No price, ever (2026-11-21). */
function MemberStrip() {
  const { t } = useApp();
  return (
    <div class="cf-member" data-testid="card-member">
      <div class="cf-member-text">
        <p class="cf-mk">{t("memberIdLabel")}</p>
        <p class="cf-mh">{t("memberIdHint")}</p>
      </div>
      <span class="cf-line" aria-hidden="true" />
    </div>
  );
}

/** The card itself — the teal face the site uses (SavingsCard #1FA6A6 → #0C7C7C,
 * the treeline, the faint wordmark top-right, the white Member ID strip), so the
 * person recognises the same object on the site, in the chat and on paper.
 * `full` adds the "free · no signup" line; the compact face sits in every view. */
export function CodesLine({ bin, pcn, group, full = false }: { bin: string; pcn: string; group: string; full?: boolean }) {
  const { t } = useApp();
  const [copied, setCopied] = useState(false);
  const ref = useRef<HTMLParagraphElement>(null);
  // What the person keeps: the codes and the Member ID line, as the site's Copy
  // (CouponActions) — no drug, no price.
  const text = `${t("bin")} ${bin} · ${t("pcn")} ${pcn} · ${t("group")} ${group}\n${t("memberIdLine")}`;

  function done() {
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  // No clipboard permission: select the codes so they can be copied by hand
  // rather than leaving a button that silently does nothing.
  function selectCodes() {
    try {
      const node = ref.current;
      if (!node) return;
      const range = document.createRange();
      range.selectNodeContents(node);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
      if (document.execCommand && document.execCommand("copy")) done();
    } catch {
      /* nothing more we can do */
    }
  }
  function copy() {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, selectCodes);
        return;
      }
    } catch {
      /* fall through */
    }
    selectCodes();
  }

  return (
    <div class={`cardface${full ? " full" : ""}`} data-testid="card-face">
      <div class="cf-face">
        <Treeline />
        {/* faint wordmark in the top-right corner, bleeding off the edge — up
            here it stays clear of the treeline (the site, 2026-11-21) */}
        <span class="cf-mark" aria-hidden="true">
          FineRx
        </span>
        <div class="cf-inner">
          <p class="cf-brand">FineRx</p>
          <p class="cf-title">{t("cardTitle")}</p>
          {full && <p class="cf-sub">{t("cardSub")}</p>}
          <p class="cf-codes" dir="ltr" ref={ref} data-testid="card-codes">
            <span class="cf-code">
              <span class="k">{t("bin")}</span> <b>{bin}</b>
            </span>
            <span class="sep"> · </span>
            <span class="cf-code">
              <span class="k">{t("pcn")}</span> <b>{pcn}</b>
            </span>
            <span class="sep"> · </span>
            <span class="cf-code">
              <span class="k">{t("group")}</span> <b>{group}</b>
            </span>
          </p>
          <div class="cf-foot">
            <span class="cf-note">{t("notInsurance")}</span>
            <button type="button" class="cf-copy" onClick={copy} aria-live="polite">
              {copied ? t("copied") : t("copy")}
            </button>
          </div>
        </div>
      </div>
      <MemberStrip />
    </div>
  );
}

function SaveMenu({ card }: { card: CardView | null | undefined }) {
  const { t, bridge } = useApp();
  const [emailOpen, setEmailOpen] = useState(false);
  const printUrl = (card && card.printUrl) || "";
  const smsBody = (card && card.actions && card.actions.smsBody) || "";
  const canEmail = !!card && card.actions?.emailEnabled !== false && bridge.canCallTools();

  function print() {
    if (printUrl) {
      bridge.openLink(printUrl);
      return;
    }
    try {
      window.print();
    } catch {
      /* sandbox without print */
    }
  }

  const items: Array<[string, ComponentChildren, () => void]> = [
    // Wallet passes come later (phase 3); until then the printable card is the
    // honest stand-in, and the label says so.
    ["wallet", t("wallet"), print],
    ["print", t("print"), print],
  ];
  if (canEmail) items.push(["email", t("email"), () => setEmailOpen(!emailOpen)]);
  if (smsBody) items.push(["sms", t("sms"), () => bridge.openLink(`sms:?&body=${encodeURIComponent(smsBody)}`)]);

  return (
    <div class="save-menu" data-testid="save-menu">
      <div class="save-items">
        {items.map(([key, label, onClick]) => (
          <button type="button" class="btn small" key={key} data-testid={`save-${key}`} onClick={onClick}>
            {label}
          </button>
        ))}
      </div>
      {emailOpen && <EmailForm />}
    </div>
  );
}

/** The one action in the widget. The address is typed here, sent once through
 * `email_savings_card`, and never written back into the page or any state. */
function EmailForm() {
  const { t, bridge, locale } = useApp();
  const [status, setStatus] = useState<{ kind: "idle" | "sending" | "ok" | "err"; text?: string }>({ kind: "idle" });
  const input = useRef<HTMLInputElement>(null);
  const consent = useRef<HTMLInputElement>(null);

  async function submit(event: Event) {
    event.preventDefault();
    const address = (input.current?.value || "").trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(address) || !consent.current?.checked) {
      setStatus({ kind: "err", text: t("emailError") });
      return;
    }
    setStatus({ kind: "sending" });
    try {
      const out = await bridge.callTool("email_savings_card", { email: address, consent: true, locale });
      const sc = (out && (out.structuredContent as Record<string, unknown>)) || {};
      const failed = out?.isError || sc.sent === false || typeof sc.error === "string";
      if (failed) {
        setStatus({ kind: "err", text: t("emailError") });
      } else {
        if (input.current) input.current.value = "";
        setStatus({ kind: "ok" });
      }
    } catch {
      setStatus({ kind: "err", text: t("emailError") });
    }
  }

  if (status.kind === "ok") {
    return (
      <p class="status" role="status">
        {t("emailSent")}
      </p>
    );
  }
  return (
    <form class="email-form" onSubmit={submit} noValidate>
      <input
        ref={input}
        type="email"
        autocomplete="email"
        inputMode="email"
        placeholder={t("emailPlaceholder")}
        aria-label={t("emailPlaceholder")}
        data-testid="email-input"
      />
      <label class="consent">
        <input ref={consent} type="checkbox" data-testid="email-consent" />
        <span>{t("emailConsent")}</span>
      </label>
      <button type="submit" class="btn" disabled={status.kind === "sending"} data-testid="email-send">
        {status.kind === "sending" ? t("sending") : t("emailSend")}
      </button>
      {status.kind === "err" && (
        <p class="status err" role="alert">
          {status.text}
        </p>
      )}
    </form>
  );
}
