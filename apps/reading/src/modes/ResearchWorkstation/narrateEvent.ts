// narrateEvent — the translation layer (SPR-02 M1).
//
// One pure function maps a substrate event to a plain-language line a
// non-technical reader understands, or to nothing (events that are noise to
// a human). It is the single place where the engine's vocabulary
// (action_type, phase numbers, role names, dispatch internals) becomes the
// user's vocabulary ("looking for evidence", "found a source", "writing the
// answer"). The thinking stream renders only what this returns; nothing
// raw reaches the default view.
//
// Three discipline rules a maintainer must keep, in priority order:
//
//   1. COVERAGE. Every action_type in the generated catalogue
//      (generated/types.ts ActionType) MUST have a row in NARRATION below —
//      either a narration or an explicit `null` (suppress). A missing row is
//      a coverage gap that narrateEvent.test.ts fails on. When the schema
//      adds an action_type, codegen regenerates the catalogue and the test
//      goes red until you add its row here. That is the gate working.
//
//   2. HONESTY (rigor #1). A line claims only what the event asserts. A
//      retrieval that returned is "Looking through the sources", NOT "Found
//      a strong source" — strength is a claim the retrieval event does not
//      make. Where a line summarizes a payload (counts, a sub-question), it
//      reads what the payload actually carries; where a row smooths several
//      events into one beat, that is noted in the handoff, not hidden here.
//
//   3. NO VOCABULARY LEAK. A narration never contains a phase number, an
//      action_type, "dispatch", "synthesizer", "chunk", or a raw id. Those
//      are correct in the log (behind the raw-activity toggle) and wrong in
//      the thinking stream.
//
// The function is pure (event in → Narration | null out) and crashes on
// nothing: an action_type with no row (only possible if the catalogue and
// this map drift between a codegen run and this file) narrates generically
// and logs, rather than throwing inside a render.

import type { Event } from "../../generated/types";
import { ActionType } from "../../generated/types";

/** The tone shapes how a line reads in the stream — not a severity, a register.
 *  `step` is ongoing work; `finding` is something the research learned;
 *  `caution` is a gap or a self-correction; `milestone` is a lifecycle beat. */
export type NarrationTone = "step" | "finding" | "caution" | "milestone";

export interface Narration {
  line: string;
  tone: NarrationTone;
}

type ActionTypeValue = (typeof ActionType)[keyof typeof ActionType];

/** A narration is either a fixed beat or a function of the event payload
 *  (when the line reads a count or a quoted fragment). `null` suppresses. */
type NarrationRule =
  | Narration
  | null
  | ((event: Event) => Narration | null);

// A small helper so payload reads stay terse and total — a missing or
// mistyped field degrades to the fixed beat, never throws.
function payload(event: Event): Record<string, unknown> {
  const p = event.payload as unknown;
  return p && typeof p === "object" ? (p as Record<string, unknown>) : {};
}

function asString(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

// ── The map ──────────────────────────────────────────────────────────────
//
// Keyed by the ActionType *value* (the wire string) so a row sits next to
// the catalogue entry it covers. Grouped by the run's natural arc:
// orientation → evidence → connection → synthesis → lifecycle, then the
// large suppressed tail (substrate mechanics no reader needs to watch).

const NARRATION: Record<ActionTypeValue, NarrationRule> = {
  // ── Lifecycle the reader should feel ──
  [ActionType.INVESTIGATION_START_REQUESTED]: (e) => {
    const q = asString(payload(e).question);
    return {
      line: q ? `Starting on your question: ${q}` : "Starting your research",
      tone: "milestone",
    };
  },
  [ActionType.INVESTIGATION_COMPLETED]: { line: "Finished — the answer is ready", tone: "milestone" },
  [ActionType.INVESTIGATION_FAILED]: { line: "Couldn’t finish this research", tone: "caution" },
  [ActionType.INVESTIGATION_CHASE_HALTED]: { line: "Paused following this thread further", tone: "caution" },
  [ActionType.INVESTIGATION_SPAWNED_FROM]: { line: "Following up on a thread from an earlier research", tone: "milestone" },
  [ActionType.PIPELINE_TERMINATED]: { line: "Stopped this research", tone: "milestone" },

  // ── Orientation + breaking the question down ──
  [ActionType.DECOMPOSE_QUESTION_REQUESTED]: { line: "Breaking your question into parts", tone: "step" },
  [ActionType.DECOMPOSE_QUESTION_DELIVERED]: (e) => {
    const subs = payload(e).decomposition;
    const n = Array.isArray(subs) ? subs.length : 0;
    return {
      line: n ? `Broke it into ${plural(n, "angle", "angles")} to look into` : "Worked out what to look into",
      tone: "finding",
    };
  },
  // The paraphrase guard caught a weak split and asked for a better one —
  // a self-correction worth showing as a small caution, not the raw flag.
  [ActionType.DECOMPOSER_PARAPHRASE_FLAGGED]: { line: "Noticed the parts overlapped — rethinking them", tone: "caution" },
  [ActionType.DECOMPOSER_REGENERATED]: { line: "Reworked the angles", tone: "step" },

  // ── Looking for evidence ──
  [ActionType.EVIDENCE_RETRIEVE_REQUESTED]: (e) => {
    const sq = asString(payload(e).sub_question);
    return { line: sq ? `Looking for evidence on: ${sq}` : "Looking for evidence", tone: "step" };
  },
  [ActionType.EVIDENCE_RETRIEVE_DELIVERED]: (e) => {
    const p = payload(e);
    // The event asserts what came back — claims found and gaps left. It does
    // NOT assert the source is "strong"; we say what it actually carries.
    const claims = Array.isArray(p.supporting_claims) ? p.supporting_claims.length : 0;
    const gaps = Array.isArray(p.evidentiary_gaps) ? p.evidentiary_gaps.length : 0;
    if (p.insufficient_evidence === true || (claims === 0 && gaps > 0)) {
      return { line: "The sources came up short here", tone: "caution" };
    }
    if (claims === 0) return { line: "Read through the sources", tone: "step" };
    const tail = gaps > 0 ? `, with ${plural(gaps, "open question", "open questions")} left` : "";
    return { line: `Found ${plural(claims, "supporting point", "supporting points")}${tail}`, tone: "finding" };
  },
  [ActionType.EVIDENCE_PACK_BUILT]: { line: "Gathered the evidence together", tone: "step" },

  // ── Connecting ideas across domains ──
  [ActionType.CONNECTOR_REQUESTED]: { line: "Looking for connections across the ideas", tone: "step" },
  [ActionType.CONNECTOR_DELIVERED]: (e) => {
    const paths = payload(e).paths;
    const n = Array.isArray(paths) ? paths.length : 0;
    return {
      line: n ? `Connected ${plural(n, "idea", "ideas")} across the sources` : "Looked for cross-cutting connections",
      tone: n ? "finding" : "step",
    };
  },

  // ── Weighing the answer + constraints (the "weighing a counter-argument" beat) ──
  [ActionType.SYNTHESIZE_REQUESTED]: { line: "Weighing the evidence to form an answer", tone: "step" },
  [ActionType.SYNTHESIZE_DELIVERED]: { line: "Drafted the answer", tone: "finding" },
  [ActionType.CONSTRAINT_VIOLATION_FOUND]: { line: "Caught a place the answer didn’t hold up", tone: "caution" },
  [ActionType.CONSTRAINT_REVISION_TRIGGERED]: { line: "Reworking the answer to fix that", tone: "step" },
  [ActionType.CONSTRAINT_LOOP_RESOLVED]: (e) => {
    const status = asString(payload(e).final_status);
    if (status === "regressed" || status === "max_iterations_reached" || status === "escalated") {
      return { line: "Couldn’t fully reconcile the answer with every requirement", tone: "caution" };
    }
    return { line: "Settled the answer against your requirements", tone: "finding" };
  },

  // ── Writing it up ──
  [ActionType.MASTER_MD_WRITTEN]: { line: "Writing the answer", tone: "milestone" },
  [ActionType.SYNTHESIS_ARCHIVED]: { line: "Saved the answer", tone: "step" },

  // ── Open questions the reader benefits from seeing surface ──
  [ActionType.QUESTION_IDENTIFIED]: (e) => {
    const q = asString(payload(e).question_text);
    return { line: q ? `Noted an open question: ${q}` : "Noted an open question", tone: "finding" };
  },
  [ActionType.QUESTION_ESCALATED_TO_RESEARCH]: { line: "Spinning up a deeper look at an open question", tone: "milestone" },

  // ── Phase 8 self-improvement — a quiet milestone ──
  [ActionType.SKILL_PATCH_GATE_DECIDED]: null,
  [ActionType.SKILL_PATCH_GATE_REVIEWED]: null,
  [ActionType.AUTO_PATCH_APPLIED]: { line: "Updated what it learned for next time", tone: "step" },

  // ── A self-repair attempt on a flaky role call — show the recovery, not the mechanism ──
  [ActionType.ROLE_SELF_REPAIR_ATTEMPTED]: { line: "Hit a snag and retried", tone: "caution" },
  [ActionType.ROLE_VALIDATION_FAILED]: { line: "A step came back malformed — retrying", tone: "caution" },
  [ActionType.KE_LLM_RESPONSE_FAILED]: { line: "A step didn’t return cleanly — retrying", tone: "caution" },

  // ── Suppressed: substrate mechanics, costing, and per-step plumbing the
  //    reader does not need to watch tick by tick. These are still in the log
  //    behind the raw-activity toggle; suppressing them here is the whole
  //    point of the glass-box (a narration, not a log dump). ──
  [ActionType.PHASE_ENTER]: null,
  [ActionType.PHASE_EXIT]: null,
  [ActionType.PHASE_VERIFY]: null,
  [ActionType.ROLE_CALL_START]: null,
  [ActionType.ROLE_CALL_END]: null,
  [ActionType.ROLE_CALL_FAILED]: null, // the human-facing recovery is ROLE_SELF_REPAIR_ATTEMPTED / VALIDATION_FAILED
  [ActionType.AUDIT_FINDING_EMITTED]: null,
  [ActionType.PAGE_ATTRIBUTION_COMPUTED]: null,
  [ActionType.KNOWLEDGE_REUSED]: null, // SPR-06 emits it to the event log (for the SPR-09 benchmark); the reader-facing "reused N prior insights" surface is SPR-10's job, not a feed line here
  [ActionType.REUSE_GATED]: null, // SPR-08 emits it per unit EXCLUDED from reuse (below-threshold / non-servable) for the audit trail + SPR-09 benchmark; not a reader-facing feed line
  [ActionType.DOCUMENT_CONTENT_CLASS_DEFAULTED]: null, // Personal-Reading Lane SPR-01: a write-side rights-classification default (a third-party ingest landing personal_reading). Substrate bookkeeping the reader never watches — the §9.0 audit trail lives in the event log, not the thinking stream.
  [ActionType.PARAMETER_EXTRACT_REQUESTED]: null, // folded into the synthesize beat
  [ActionType.PARAMETER_EXTRACT_DELIVERED]: null,
  [ActionType.CROSS_DOMAIN_KEYWORDS_RESOLVED]: null,
  [ActionType.CROSS_DOMAIN_TRAVERSAL_RAN]: null,
  [ActionType.CONSTRAINT_PREFLIGHT]: null,
  [ActionType.GRAPH_NODE_INSERTED]: null,
  [ActionType.GRAPH_EDGE_INSERTED]: null,
  [ActionType.GRAPH_TIER_OVERRIDDEN]: null,
  [ActionType.GRAPH_SUPERSESSION_PROPOSED]: null,
  [ActionType.GRAPH_STALENESS_FLAGGED]: null,
  [ActionType.NODE_MERGE]: null,
  [ActionType.EMBED_MODEL_REGISTER]: null,
  [ActionType.TIER_REWRITE_BULK]: null,
  [ActionType.SUPERSESSION_APPLY]: null,
  [ActionType.SUPERSESSION_DISMISS]: null,
  [ActionType.SUPERSESSION_COEXIST]: null,
  [ActionType.STALENESS_RESOLVE]: null,
  [ActionType.SUBSTRATE_MANIFEST_WRITTEN]: null,
  [ActionType.MASTER_MD_SKIPPED]: null,
  [ActionType.AUTO_PATCH_SKIPPED]: null,
  [ActionType.OUTCOME_RECORDED]: null,
  [ActionType.RUBRIC_SCORED]: null,
  [ActionType.USER_ACCEPT_DELTA]: null,
  [ActionType.USER_REJECT_DELTA]: null,
  [ActionType.USER_MODIFY_DELTA]: null,
  [ActionType.DISPATCH_CALL]: null, // the cost meter aggregates these; never a line
  [ActionType.CONTEXT_PACK_ASSEMBLED]: null,
  [ActionType.GRAPH_TIER_ASSIGNED]: null,
  [ActionType.QUESTION_RESOLVED_BY_DOC]: null,
  [ActionType.CROSS_DOC_QUESTION_ANSWERED]: null,
  [ActionType.CLAIM_ASSERTED_BY_OPERATOR]: null,

  // ── Wrestling-loop, exploration, RLM, federation, visual, write, read,
  //    speak, DP, seam, and AI-sidecar events: these belong to other
  //    workflows' surfaces, not the Research thinking stream. They can ride
  //    the same per-investigation log on a shared id, so they are catalogued
  //    here as explicit suppressions — present and accounted for, never a
  //    fall-through. (A future sprint that surfaces one of these in Research
  //    moves its row up to a narration; the gate makes that an additive,
  //    visible edit.) ──
  [ActionType.DOCUMENT_LOADED]: null,
  [ActionType.DOCUMENT_REGION_SELECTED]: null,
  [ActionType.DISTILLATION_REQUESTED]: null,
  [ActionType.DISTILLATION_DELIVERED]: null,
  [ActionType.CLAIM_CHALLENGE_RAISED]: null,
  [ActionType.CLAIM_GROUNDING_CHECK_PASSED]: null,
  [ActionType.CLAIM_GROUNDING_CHECK_FAILED]: null,
  [ActionType.NOTE_EMERGED]: null,
  [ActionType.NOTE_REFINED]: null,
  [ActionType.NOTE_COMPRESSED_DOC_WRITTEN]: null,
  [ActionType.USER_ACCEPT_DISTILLATION]: null,
  [ActionType.USER_REJECT_DISTILLATION]: null,
  [ActionType.USER_EDIT_DISTILLATION]: null,
  [ActionType.ARTIFACT_GENERATED]: null,
  [ActionType.ARTIFACT_INTERACTED]: null,
  [ActionType.RLM_BRIDGE_DECIDED]: null,
  [ActionType.QUALITY_GATE_EVALUATED]: null,
  [ActionType.CROSS_GRAPH_CITATION_RECORDED]: null,
  [ActionType.REV_SHARE_DECIDED]: null,
  [ActionType.PREFERENCE_OBSERVATION_RECORDED]: null,
  [ActionType.SKILL_RULE_PROMOTED]: null,
  [ActionType.DISCOVERY_PROPOSED]: null,
  [ActionType.DISCOVERY_SELECTED]: null,
  [ActionType.FETCH_FALLBACK_ESCALATED]: null,
  [ActionType.VERIFIER_LOOKUP]: null,
  [ActionType.FEDERATION_PARTNER_REGISTERED]: null,
  [ActionType.FEDERATION_PARTNER_TRUSTED]: null,
  [ActionType.FEDERATION_PARTNER_REVOKED]: null,
  [ActionType.FEDERATION_OUTBOUND_CITATION_EMITTED]: null,
  [ActionType.FEDERATION_INBOUND_CITATION_ACCEPTED]: null,
  [ActionType.FEDERATION_INBOUND_CITATION_REFUSED]: null,
  [ActionType.VISUAL_FRAME_IDENTIFIED]: null,
  [ActionType.VISUAL_CLAIMS_EXTRACTED]: null,
  [ActionType.VISUAL_ROLE_FAILED]: null,
  [ActionType.AI_ACTION_APPLIED]: null,
  [ActionType.AI_ACTION_UNDONE]: null,
  [ActionType.DP_ROUTED]: null,
  [ActionType.OUTLINE_BLOCK_PLACED]: null,
  [ActionType.OUTLINE_BLOCK_MOVED]: null,
  [ActionType.OUTLINE_BLOCK_REMOVED]: null,
  [ActionType.BOOK_SERVABILITY_CHANGED]: null,
  [ActionType.BOOK_TAKEN_DOWN]: null,
  [ActionType.EDIT_CAPTURED]: null,
  // Write SPR-09 — draft provenance persistence (X-ray); not narrated in the
  // research timeline (it is a Write-surface composition event).
  [ActionType.SECTION_DRAFT_GENERATED]: null,
  [ActionType.SEAM_RESEARCH_TO_READ]: null,
  [ActionType.SEAM_READ_TO_RESEARCH]: null,
  [ActionType.SEAM_READ_TO_WRITE]: null,
  [ActionType.SEAM_WRITE_TO_READ]: null,
  [ActionType.SEAM_SPEAK_TO_WRITE]: null,
  [ActionType.SEAM_SPEAK_TO_READ]: null,
  [ActionType.SEAM_WRITE_TO_SPEAK]: null,
  // SPR-14 — voice-in capture provenance; not narrated in the thinking stream.
  [ActionType.VOICE_CAPTURED]: null,
  // SPR-04 — a highlight → float-menu user note is reader marginalia, not
  // research progress; never narrated in the thinking stream.
  [ActionType.MARGINALIA_NOTED]: null,
  // SPR-03 — block-canvas position is pure view-state (where a block sits on
  // the organism canvas); never narrated as research progress.
  [ActionType.BLOCK_POSITIONED]: null,
  // SPR-07 — source.read is the reader's own reading history (lights SiteSee's
  // "read" tint on the Read surface); not a Research thinking-stream beat.
  [ActionType.SOURCE_READ]: null,
  [ActionType.READ_BOOK_ANSWERED]: null,
  [ActionType.READ_BOOK_ANSWER_JUDGED]: null,
  // SPR-08 — a saved meta-reading deliverable is a Read asset (a re-openable
  // synthesis over the owned corpus); it is not a Research thinking-stream beat.
  [ActionType.READ_META_READING_GENERATED]: null,
  // SPR-13 — filing a personal-space doc into a project is a Read-side curation
  // action (the reader accepting a suggestion); not a Research thinking-stream
  // beat. The doc joins the project's substrate, but the narration belongs to
  // the personal space, not the investigation's progress stream.
  [ActionType.DOCUMENT_FILED_INTO_INVESTIGATION]: null,
  // SPR-02 — claim-groundedness (truth-axis) quality signals. Observability-
  // only this sprint and sibling to the suppressed RUBRIC_SCORED form-axis
  // signal: the engine's per-synthesis quality telemetry, not a reader-facing
  // research beat. Suppressed here (still in the log behind the raw-activity
  // toggle); a future sprint that surfaces a quality cue in the stream moves
  // these rows up to a narration — an additive, visible edit the gate enforces.
  [ActionType.GROUNDEDNESS_SCORED]: null,
  [ActionType.GROUNDEDNESS_FAILED]: null,
  // yegge SPR-01 — worker registration by the future worker registry (SPR-04).
  // Substrate-infrastructure telemetry, not a reader-facing research beat; a
  // worker spawn is engine plumbing the reader never needs narrated. Suppressed
  // here (still in the log behind the raw-activity toggle); if a later sprint
  // surfaces worker activity in the stream it moves up to a narration — an
  // additive, visible edit the coverage gate enforces.
  [ActionType.WORKER_IDENTITY]: null,

  // ── Link Monster — what the front door just ate ──
  [ActionType.LINK_MONSTER_DIGESTED]: (e) => {
    const p = payload(e);
    const title = asString(p.title);
    const what = title ? `“${title.slice(0, 60)}”` : "a link";
    if (p.outcome === "meal") {
      return { line: `The Monster ate ${what} and stewed it into the graph`, tone: "milestone" };
    }
    return { line: `The Monster nibbled ${what} — metadata only`, tone: "step" };
  },

  // Own Your Mind P0 (docs/own-your-mind/10-p0-implementation-brief.md §5) —
  // the served-impression audit event ("what was shown", decoupled from
  // training). Audit-only telemetry of the surface's own rendering, not a
  // Research thinking-stream beat; suppressed here (still in the log behind
  // the raw-activity toggle). No consumer trains on it in P0.
  [ActionType.SURFACE_SERVED_IMPRESSION]: null,

  // Canonical artifact-feedback audit. The reader sees these transitions in
  // the adjacent feedback docket, so duplicating them in the research run
  // narration would add noise without new information.
  [ActionType.ARTIFACT_COMMENT_CREATED]: null,
  [ActionType.AGENT_WORK_TRANSITIONED]: null,
  [ActionType.ARTIFACT_FEEDBACK_REPLIED]: null,

};

/** The safe generic line for an action_type with no row — only reachable if
 *  the catalogue and the map drift (a codegen ran without this file being
 *  updated). The coverage test makes that a red build; at runtime we degrade
 *  to a non-leaking beat and log, rather than crash a render. */
const GENERIC: Narration = { line: "Working…", tone: "step" };

/**
 * Translate one event to a plain-language line, or `null` to suppress it.
 *
 * Pure and total. An unmapped action_type returns the generic line and logs
 * a one-time-ish console warning (it will repeat per offending type, which is
 * the right loudness for a drift bug).
 */
export function narrateEvent(event: Event): Narration | null {
  const rule = NARRATION[event.action_type as ActionTypeValue];
  if (rule === undefined) {
    // Drift between the generated catalogue and this map. Don't throw inside
    // a render; surface it and keep the stream readable.
    // eslint-disable-next-line no-console
    console.warn(
      `narrateEvent: no narration row for action_type ${String(event.action_type)} — ` +
        `add it to narrateEvent.ts (the coverage gate should have caught this).`,
    );
    return GENERIC;
  }
  if (rule === null) return null;
  if (typeof rule === "function") return rule(event);
  return rule;
}

/** Exposed for the coverage test: the set of action_type values that have an
 *  explicit row (narration or suppress). The test asserts this equals the
 *  generated catalogue exactly — no missing rows, no stale rows. */
export function narratedActionTypes(): ReadonlySet<string> {
  return new Set(Object.keys(NARRATION));
}
