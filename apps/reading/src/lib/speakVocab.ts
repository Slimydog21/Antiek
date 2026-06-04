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

// Re-export the enum→word machinery rather than redefine it: speakApi is the
// single owner of the mappings; speakVocab is the single owner of the labels.
// (The re-export below pulls `toAgreementKind` straight from speakApi — no
// local import is needed, and a local one would be flagged unused under the
// app's noUnusedLocals.)
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

/**
 * PAYOUT_COPY — the canonical, honest explanation of HOW a contributor's share
 * is decided (SPR-04 M3). This is the one place both payout surfaces — the
 * public-lane explainer (PublicLane, owns the basis line) and the operator's
 * SpeakSettings payout section — read the §9.3 Option-B basis, the slop-earns-$0
 * rule, and the verifier-not-requester rule, so the two cannot drift.
 *
 * These are STATE / EXPLANATION sentences, not gate phrases: each describes how
 * the *already-shipped* grading works, grants the user NO action over a gate,
 * and names NO env flag — so they live OUTSIDE `gatePhraseStrings()` (not held
 * to the future-tense "what opens it" discipline) but INSIDE
 * `allRenderedPhrases()`, so the env-flag-leak scan still covers them.
 *
 * Grounded in the shipped backend, NOT invented:
 *   - `basis`            ↔ §9.3 Option-B `claim_confidence × (6 − source_tier)`
 *                          (contributor.py:14-15) — stated in human words,
 *                          never the formula and never a per-second/airtime
 *                          model (the rejected alternative, decision doc §"Payout
 *                          basis"). Shared verbatim with the public lane via
 *                          `PUBLIC_LANE_LABELS.explainerPayoutBasis` below.
 *   - `slopEarnsZero`    ↔ the slop gate: a contribution scoring below
 *                          `DEFAULT_SLOP_THRESHOLD` (0.4) earns $0
 *                          (contributor.py:191 / payout_verifier.py PASSING_SCORE).
 *   - `verifierNotRequester` ↔ the grade is the verifier's score, never the
 *                          requester's choice; the requester supplies only the
 *                          goal + budget, never a pass/deny (payout_verifier.py
 *                          header + :54). It is a heuristic/prompt-rubric grader,
 *                          NOT a trained model — phrased so as not to overclaim.
 */
export const PAYOUT_COPY = {
  /** §9.3 Option-B basis, in human words. Shared with the public lane so the
   *  two payout surfaces say it identically (see PUBLIC_LANE_LABELS below). */
  basis:
    "A contribution's share is weighted by how well-corroborated and " +
    "well-sourced it is — by the quality of what's remembered, nothing else.",
  /** The slop gate: below the quality threshold, a contribution earns $0. */
  slopEarnsZero:
    "A low-effort answer earns nothing — only substance is paid.",
  /** The grade comes from the system's verifier checking the answer against the
   *  information goal, not from the requester. A heuristic check, not a trained
   *  model — so it is not overclaimed. */
  verifierNotRequester:
    "Each contribution is graded by the system — a verifier checking the " +
    "answer against the goal — not by the person who asked. A requester can't " +
    "withhold pay from a good answer.",
} as const;

export type PayoutCopyKey = keyof typeof PAYOUT_COPY;

/**
 * Public-lane copy (SPR-03) — plain, honest, NON-gate sentences the public
 * lane says around the feed and the gate phrases above. These grant the user
 * NO agency over a gate and name NO env flag, so — like VOICE_STATE_LABELS —
 * they live OUTSIDE `gatePhraseStrings()` (they are not gate phrases held to
 * the future-tense / no-user-action discipline) but INSIDE
 * `allRenderedPhrases()` so the env-flag-leak scan still covers them.
 *
 * Two honesty rules they encode (SPR-03 M3 + M5):
 *   - M5 lifecycle: the feed lists public-INTENT projects, and `FeedItem`
 *     carries NO "published" flag, so the lane MUST NOT claim "published".
 *     `intendedPublic` says "intended public", never "published".
 *   - M3 CTA: open public contribution by strangers is not live (G7), so the
 *     CTA copy is honest that the working "Add your memory" action is the
 *     operator opening their OWN public-intent project — not a live open
 *     marketplace others can join today.
 *
 * The §9.3 Option-B payout basis is stated WITHOUT any airtime/ad-duration
 * fiction (mirrors the guard at speakApi.ts releasePayout).
 */
export const PUBLIC_LANE_LABELS = {
  /** M5 — a feed item is public-INTENT, never confirmed published. */
  intendedPublic:
    "A public remembrance — open to the people invited to add what they remember.",
  /** M3 — honest framing of who the working CTA serves today. */
  ctaOperatorOnly:
    "This opens your own public-intent remembrance. Open contribution by " +
    "anyone is described below — it isn't live yet.",
  /** M4 — explainer heading. */
  explainerHeading: "How public remembrances will work",
  /** M4 — step 1, the only present-ish framing, still about the future flow. */
  explainerStepFind:
    "Anyone will be able to find an open remembrance and add what they remember.",
  /** M4 — payout basis, §9.3 Option-B. Promoted to the shared `PAYOUT_COPY.basis`
   *  (SPR-04 M3) so the public lane and the operator's SpeakSettings payout
   *  section say the basis identically and cannot drift. Phrased to avoid the
   *  very strings the §9.3 guard forbids in rendered copy (an airtime/ad-duration
   *  framing): a share is earned by corroboration + sourcing quality only. */
  explainerPayoutBasis: PAYOUT_COPY.basis,
  /**
   * M4 — the OPEN-state copy for the G2/G3 explainer lines, rendered when a
   * LIVE `getEconomics` read reports the gate has cleared. Each describes a
   * STATE the system has reached — NO user-action verb (no enable/unlock/
   * activate), NO env-flag name — so the gate-honesty contract stays green
   * even though these live outside `gatePhraseStrings()` (they are not gate
   * phrases: a gate phrase is the FUTURE-tense "what opens it" sentence; these
   * are the present-tense "it is open" counterpart, read live from G2/G3).
   */
  publishingOpen:
    "Public sharing is open — remembrances can now be shared publicly.",
  payoutsOpen:
    "Contributor payouts are open — money can now route to contributors.",
  /** M4 — explainer step 2, distinct from the M2 lock panel's sentence so the
   *  same G7 sentence is not printed twice on screen. Points at the panel above
   *  rather than repeating it verbatim. */
  explainerStepOpenContribution:
    "Open contribution by anyone arrives after the ecosystem review — see the " +
    "note above; for now, contributions come through your invites.",
} as const;

export type PublicLaneLabelKey = keyof typeof PUBLIC_LANE_LABELS;

/**
 * Display labels for an invitee's lifecycle state — the ONE place the console
 * (modes/Speak/index.tsx) and the invite list (modes/Speak/Invites.tsx) read
 * the human word for a voice's status, so the two surfaces cannot drift.
 *
 * Keyed by the humanized `VoiceState` (speakApi's enum-edge already maps the
 * substrate strings → VoiceState via `VOICE_STATE`; this is the next hop,
 * VoiceState → display word — it does NOT re-derive that substrate map).
 *
 * These are plain status words, never gate phrases: they grant no agency and
 * name no flag, so they live OUTSIDE `gatePhraseStrings()` (they are not held
 * to the read-only-gate discipline) but inside `allRenderedPhrases()` (so the
 * env-flag-leak scan still covers them).
 */
export const VOICE_STATE_LABELS: Record<VoiceState, string> = {
  invited: "Invited",
  recording: "Recording…",
  shared: "Shared",
  declined: "Declined",
  unfinished: "Started",
};

/**
 * The Invites surface holds substrate-style status strings ("in_progress",
 * "completed", "incomplete") rather than the humanized VoiceState. This maps
 * each to the same display word as above — single-sourced through
 * VOICE_STATE_LABELS, so an invite row and a console row for the same lifecycle
 * stage always read identically. Mirrors speakApi's substrate→VoiceState
 * semantics (in_progress→recording, completed→shared, incomplete→unfinished)
 * without duplicating its runtime map.
 */
export type InviteStatus =
  | "invited"
  | "in_progress"
  | "completed"
  | "declined"
  | "incomplete";

const INVITE_STATUS_TO_VOICE_STATE: Record<InviteStatus, VoiceState> = {
  invited: "invited",
  in_progress: "recording",
  completed: "shared",
  declined: "declined",
  incomplete: "unfinished",
};

/** Human display word for an Invites-surface status string. */
export function inviteStatusLabel(status: InviteStatus): string {
  return VOICE_STATE_LABELS[INVITE_STATUS_TO_VOICE_STATE[status]];
}

/** Every rendered string this module exposes, flattened — the surface the
 *  gate-honesty contract test scans. Keeping it derived (not hand-maintained)
 *  means a new label/phrase is automatically covered by the test. */
export function allRenderedPhrases(): string[] {
  const out: string[] = [
    ...Object.values(LANE_LABELS),
    ...Object.values(AGREEMENT_WORDS),
    ...Object.values(VOICE_STATE_LABELS),
    ...Object.values(PUBLIC_LANE_LABELS),
    ...Object.values(PAYOUT_COPY),
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
