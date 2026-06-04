/**
 * speakVocab.ts — the single source of human vocabulary the Speak lanes share
 * (Speak Private↔Public spine, SPR-01 M3).
 *
 * Both lanes (YoursLane / PublicLane, owned by SPR-02 / SPR-03) and the payout-
 * legibility surfaces (SPR-04) MUST render gate copy, lane labels, and the
 * agreement words from here — so the two parallel builders cannot drift in tone
 * or quietly invent a phrase that grants the user false agency. The canonical
 * decision record is `docs/decisions/speak-private-public-spine.md`; the
 * `gateHonesty.contract.test.tsx` next to the lanes is this module's enforcement.
 *
 * Division of labor with speakApi.ts:
 *   - speakApi.ts owns the enum→word MAPPINGS (`toAgreementKind`, the VoiceState
 *     translation) and the backend reason strings shown verbatim
 *     (`publicPublishingReason` / `disbursementReason`). It is the data edge.
 *   - speakVocab.ts owns the UI FRAME: labels and the fixed gate sentences the
 *     surface says around those backend reasons. It houses NO enum maps; it
 *     re-exports the ones speakApi already defines so there is exactly one of
 *     each (`VoiceState`, `toAgreementKind`, the agreement `kind` literals).
 *
 * Honesty rules this module is held to (and the contract test enforces):
 *   1. The agreement words are corroborated / single / disagreement — NEVER
 *      "proven" or "true". (Inherited from speakApi's `AgreementPoint["kind"]`.)
 *   2. No GATE phrase contains a verb that implies the USER can act on the gate
 *      — no "enable / unlock / activate / close the gate" as a user action.
 *      Gates are read-only operator actions; the phrasing describes a FUTURE
 *      state ("Public sharing opens after a legal review (G2/G3)."), never an
 *      affordance the surface offers.
 *   3. No raw env-flag name (ANTIEK_SPEAK_PUBLIC_PUBLISHING, _PUBLIC_ECOSYSTEM,
 *      ANTIEK_STRIPE_PROVIDER) appears in any string meant for rendering.
 */
import type { VoiceState, AgreementPoint } from "./speakApi";
import { toAgreementKind } from "./speakApi";

// Re-export the enum→word machinery rather than redefine it: speakApi is the
// single owner of the mappings; speakVocab is the single owner of the labels.
export type { VoiceState } from "./speakApi";
export { toAgreementKind } from "./speakApi";

/** The agreement vocabulary, as a value, for places that enumerate it (e.g. a
 *  legend). Mirrors `AgreementPoint["kind"]` from speakApi exactly — never adds
 *  "proven"/"true". */
export type AgreementKind = AgreementPoint["kind"];

/** Human labels for the two Speak tabs/lanes. The shell and both lanes use
 *  these so "yours" vs "public" reads identically wherever it appears. */
export const LANE_LABELS = {
  /** The operator's private/invited projects — the people they're remembering. */
  yours: "People you're remembering",
  /** The browsable feed of public-intent remembrances. */
  public: "Public remembrances",
} as const;

/** Short word for each agreement kind, for inline rendering / legends. These
 *  are the ONLY words the surface may say for corroboration state. Aligned to
 *  the SHIPPED Speak console (modes/Speak/index.tsx): the agreement-point
 *  surface renders "Corroborated · …", "People remember this differently",
 *  and "One person so far"; the draft surface (~:483) says "people disagreed".
 *  These short forms match that phrasing so Wave-2 inherits ONE vocabulary —
 *  "corroborated" / "one person" / "people disagree" — never "proven"/"true". */
export const AGREEMENT_WORDS: Record<AgreementKind, string> = {
  corroborated: "corroborated",
  single: "one person",
  disagreement: "people disagree",
};

/**
 * Gate phrasing — plain, FUTURE-TENSE sentences describing what is gated and
 * what opens it. Each is read-only copy: it states a future state the system
 * will reach when the operator clears a legal/ecosystem gate post-counsel. It
 * offers the user NO action and names NO env flag.
 *
 * Mirrors the human meaning of substrate/speak/gate_status.py and
 * substrate/speak/invitations.py WITHOUT copying their flag names:
 *   - publicSharing  ↔ public_publishing_allowed() (G2 lawyer review + G3 opt-in)
 *   - disbursement   ↔ disbursement_allowed()      (money routes after G2/G3)
 *   - publicEcosystem ↔ public_ecosystem_enabled() (G7, open contribution)
 *
 * Each entry carries a short `label` (the gate's name in human terms) and a
 * `whenGated` sentence (what's true today + what opens it). Lanes show the
 * backend's verbatim reason (publicPublishingReason / disbursementReason) for
 * detail; these frame it.
 */
export const GATE_PHRASES = {
  /** G2/G3 — publishing a remembrance publicly. */
  publicSharing: {
    label: "Public sharing",
    whenGated:
      "Public sharing opens after a legal review (G2/G3). Until then a " +
      "remembrance stays private to you and the people you invite.",
  },
  /** G2/G3 — money actually leaving escrow to contributors. */
  disbursement: {
    label: "Contributor payouts",
    whenGated:
      "Contributor shares accrue to escrow now; money begins routing once the " +
      "legal review clears (G2/G3).",
  },
  /** G7 — the open public-contribution ecosystem (multi-user). */
  publicEcosystem: {
    label: "Open public contributions",
    whenGated:
      "Open public contributions arrive after the ecosystem review (G7); for " +
      "now, contributions come through your invites.",
  },
} as const;

export type GatePhraseKey = keyof typeof GATE_PHRASES;

/** Every rendered string this module exposes, flattened — the surface the
 *  gate-honesty contract test scans. Keeping it derived (not hand-maintained)
 *  means a new label/phrase is automatically covered by the test. */
export function allRenderedPhrases(): string[] {
  const out: string[] = [
    ...Object.values(LANE_LABELS),
    ...Object.values(AGREEMENT_WORDS),
  ];
  for (const gate of Object.values(GATE_PHRASES)) {
    out.push(gate.label, gate.whenGated);
  }
  return out;
}

/** Just the gate sentences/labels — the strings held to the read-only,
 *  no-false-agency, no-flag-name discipline. */
export function gatePhraseStrings(): string[] {
  const out: string[] = [];
  for (const gate of Object.values(GATE_PHRASES)) {
    out.push(gate.label, gate.whenGated);
  }
  return out;
}

// A no-op reference so the imported `VoiceState` type is part of this module's
// public contract (lanes import VoiceState from here as the single vocab door)
// without an unused-import error under TS strict.
export type SpeakVoiceState = VoiceState;
