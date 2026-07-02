// AUTO-GENERATED — DO NOT EDIT.
//
// Generated from substrate/contracts/ and substrate/ad_inventory/frame_attention.py
// by tools/codegen/emit_contracts.py.
// Re-run after any contract change:  python tools/codegen/emit_contracts.py
// CI gate that fails on drift:        python tools/codegen/check_staleness.py
//
// The Pydantic models in substrate/contracts/ and the frame-attention
// dataclasses in substrate/ad_inventory/frame_attention.py are the single
// sources of truth. These are the cross-workflow contracts the four products
// (Research/Read/Write/Speak) build against. The provisional
// ReaderSurfaceContract is a Python Protocol (behavior, not data) and is
// intentionally not emitted here.

export const CONTRACT_SCHEMA_VERSION = 2;

// Frame-attention telemetry input contract. Source of truth:
// substrate/ad_inventory/frame_attention.py
export const FRAME_TELEMETRY_SCHEMA_VERSION = "frame-telemetry-v1";
export const VALID_LENSES = ["read", "research", "speak", "write"] as const;
export type Lens = (typeof VALID_LENSES)[number];

/**
 * One rendered layer of an assembled context pack: its kind, the source
 * that produced it, and whether it was truncated to fit the budget.
 */
export interface AssembledLayerContract {
  kind: "instruction" | "claim" | "insight" | "question" | "source" | "history" | "scratch";
  source: string;
  tokens: number;
  truncated?: boolean;
}

/**
 * A first-class ``insight`` graph node. ``node_id`` is content-addressed
 * and therefore stable: re-emitting the same insight resolves to the same
 * node, which is what lets one insight be *the same entity* across all four
 * workflows (the SPR-06 no-duplicate invariant rests on this).
 */
export interface InsightNodeContract {
  node_id: string;
  node_type?: "insight";
  text: string;
  investigation_id: string;
  graph_scope?: "depth";
  confidence?: "high" | "moderate" | "low" | "unknown";
  has_embedding?: boolean;
  supported_by?: string[];
}

/**
 * A first-class ``question`` graph node. ``asks_about`` targets any
 * substantive node or an insight; ``resolved_by`` targets the insight(s)
 * that answer it. SPR-07 gap-detection reads these to find unanswered
 * questions and contradictions.
 */
export interface QuestionNodeContract {
  node_id: string;
  node_type?: "question";
  text: string;
  investigation_id: string;
  graph_scope?: "depth";
  has_embedding?: boolean;
  asks_about?: string[];
  resolved_by?: string[];
  anchor_region_id?: string | null;
}

/**
 * One emerged insight from the note-taker. Field-for-field identical to
 * ``roles.note_taker.parser.ExtractedNote`` (the in-tree dataclass), so a
 * conformance check can verify the role's output satisfies this shape.
 */
export interface NoteTakerOutputContract {
  note_id: string;
  text: string;
  confidence: "high" | "moderate" | "low" | "unknown";
  source_event_ids: string[];
}

/**
 * The assembled context handed to a dispatch call: ordered layers within
 * a token budget. A consumer reads ``layers`` + ``total_tokens``; it does not
 * re-run assembly.
 */
export interface ContextPackContract {
  layers: AssembledLayerContract[];
  total_tokens: number;
  budget_tokens: number;
}

/**
 * A leaf composition unit in a deliverable outline. Either node-backed
 * (traces node → document → chunks) or user-originated (content set,
 * node_id null). The validator makes the no-orphan invariant part of the
 * contract, not just the implementation.
 */
export interface OutlineBlockContract {
  outline_block_id: string;
  section_id: string;
  block_kind: "insight" | "open_question" | "operator_note" | "claim" | "user_authored" | "synthesized";
  provenance_kind: "graph_node" | "user_authored" | "synthesized" | "brainstorm";
  node_id?: string | null;
  content?: string | null;
}

/**
 * A corpus entry as Read's serving layer sees it. ``servable`` (whether
 * full text is returned) is *derived* from ``content_class``; the contract
 * states the derivation so a consumer cannot route around deny-by-default.
 * ``speak_derived`` entries are servable only after Speak's publish gate
 * passes — Read must check, not assume.
 */
export interface ServableEntryContract {
  document_id: string;
  content_class: "public_domain" | "platform_authored" | "publisher_opted_in" | "source_declared_open" | "gated_metadata_only" | "taken_down";
  ip_holder_id?: string | null;
  taken_down?: boolean;
  provenance_class?: "operator_authored" | "speak_derived" | null;
  speak_publish_gate_passed?: boolean;
}

/**
 * One accrual line as the single escrow writer consumes it. A
 * ``share_fraction`` is present for contributor splits and ``None`` for
 * direct publisher-impression accrual. ``slop_gated`` lines accrue ``0`` —
 * slop does not earn (≤0.70 rubric).
 */
export interface AccrualContract {
  accrual_id: string;
  source: "publisher_impression" | "speak_contribution" | "frame_attention_second";
  ip_holder_id?: string | null;
  source_ref: string;
  amount_cents?: number;
  share_fraction?: number | null;
  slop_gated?: boolean;
  disbursable?: false;
}

/**
 * The output of one interview turn in the compounding interviewer.
 * ``corroboration`` tops out at ``multiply_attested`` — the contract has no
 * 'proven' value, by design.
 */
export interface InterviewerResultContract {
  interview_id: string;
  project_id: string;
  contributor_ip_holder_id?: string | null;
  extracted_claim_ids?: string[];
  corroboration?: "uncorroborated" | "multiply_attested";
}

/**
 * The consent + rights state a speak-derived document carries. Read's
 * servability check (seam #4) serves full text only when ``publish`` is in
 * ``scopes``, ``verified_before_publish`` is True, and ``taken_down`` is
 * False.
 */
export interface ConsentContract {
  interview_id: string;
  ip_holder_id?: string | null;
  scopes?: ("record" | "attribute" | "publish")[];
  verified_before_publish?: boolean;
  right_of_publicity_cleared?: boolean;
  taken_down?: boolean;
}

/**
 * One cell of the Speak economics matrix. ``contributor_split`` is the
 * fraction routed to contributors (0.70 for public); ``platform_margin`` is
 * the platform's take (0.10 public, 0.50 private-published).
 */
export interface EconomicsCellContract {
  visibility: "public" | "private_published";
  contributor_split: number;
  platform_margin: number;
}

/**
 * One IP asset's in-frame VISIBILITY for one second.
 *
 * Units / ranges (documented per rigor #5 — every feature's meaning is
 * auditable):
 *
 * * ``asset_id`` — the document/asset id (maps to ``documents.document_id``,
 *   which carries ``ip_holder_id`` and ``content_class``). The trace anchor.
 * * ``chunk_id`` — the specific chunk visible in frame, or ``None`` when the
 *   asset is in frame with no resolved chunk (a cover/title card). An asset
 *   with no chunk still earns (it is the ASSET that is monetized); the chunk
 *   is trace detail, not an eligibility input.
 * * ``content_class`` — the asset's classification AS REPORTED BY THE BACKEND
 *   lookup at aggregation time, fed to ``monetization_eligible``. The client
 *   MAY echo a hint but the backend NEVER trusts it; the authoritative value
 *   is resolved server-side. Carried here so the pure weighting function is
 *   self-contained and testable.
 * * ``viewport_area_fraction`` — fraction of the window viewport the asset
 *   occupied this second, in [0.0, 1.0]. 1.0 = filled the whole viewport.
 * * ``prominence`` — a position/salience signal in [0.0, 1.0]. 1.0 = center/
 *   foreground (eye-line); 0.0 = peripheral. The SPR-07 emitter derives it
 *   from on-screen geometry (center-weighting) the way ``reader_slots``
 *   models TOP/BOTTOM/LEFT/RIGHT position categoricals — but as a continuous
 *   prominence rather than a categorical, because the border wraps the frame.
 * * ``focused_dwell_ms`` — milliseconds of FOCUSED, foregrounded dwell this
 *   asset accrued this second, in [0, 1000]. Mirrors
 *   ``reader_impressions.focused_dwell_ms`` semantics: dwell while the tab is
 *   backgrounded/idle does NOT count and the client must not report it. ≥ 0.
 */
export interface FrameAttentionSample {
  asset_id: string;
  viewport_area_fraction: number;
  prominence: number;
  focused_dwell_ms: number;
  content_class?: string | null;
  chunk_id?: string | null;
}

/**
 * One second of one window: the active lens + the in-frame assets.
 *
 * ``second_index`` is the 0-based second offset within the window (second 0
 * is the first second the window was on screen). It is the per-second key the
 * accrual aggregation sums over; it never becomes a DB row on its own.
 */
export interface FrameSecond {
  second_index: number;
  lens: Lens;
  samples: FrameAttentionSample[];
}

/**
 * The compact per-window batch the SPR-07 emitter flushes (the unit the
 * backend consumes — NOT one row per second).
 *
 * ``ad_value_usd_cents`` is the window's TOTAL ad value for the seconds in
 * this batch, supplied as an INPUT (priced by SPR-10's auction — out of scope
 * here). It is apportioned per-second-equally across ``len(seconds)`` seconds
 * before per-asset weighting, so the window reconciles exactly (M6).
 *
 * ``schema_version`` is stamped so a batch flushed by an old emitter is
 * identifiable. ``window_id`` is the trace anchor for every accrual derived
 * from this batch.
 */
export interface WindowFrameBatch {
  window_id: string;
  seconds: FrameSecond[];
  ad_value_usd_cents: number;
  schema_version: string;
}
