// AUTO-GENERATED — DO NOT EDIT.
//
// Generated from substrate/contracts/ by tools/codegen/emit_contracts.py.
// Re-run after any contract change:  python tools/codegen/emit_contracts.py
// CI gate that fails on drift:        python tools/codegen/check_staleness.py
//
// The Pydantic models in substrate/contracts/ are the single source of truth.
// These are the cross-workflow contracts the four products (Research/Read/
// Write/Speak) build against. The provisional ReaderSurfaceContract is a
// Python Protocol (behavior, not data) and is intentionally not emitted here.

export const CONTRACT_SCHEMA_VERSION = 3;

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

// PROVISIONAL — InterviewerResultContract's owning sprint has not pinned this shape; it may change.

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

// PROVISIONAL — ConsentContract's owning sprint has not pinned this shape; it may change.

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
