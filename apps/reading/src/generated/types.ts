// AUTO-GENERATED — DO NOT EDIT.
//
// Generated from substrate/schemas/events.py by tools/codegen/emit_types.py.
// Re-run after any schema change:   python tools/codegen/emit_types.py
// CI gate that fails on drift:      python tools/codegen/check_staleness.py
//
// The Pydantic models in substrate/schemas/events.py are the single source
// of truth. See docs/architecture_notes.md §11.1 (polyglot seam) for the
// discipline rule that keeps this file in sync.

export const ANTIEK_PARAM_VERSION = "0.2.0";
export const EVENT_SCHEMA_VERSION = 36;

// Stable action vocabulary. Values are persisted to the trajectory
// store and MUST match substrate.schemas.events.ActionType exactly.
export const ActionType = {
  PHASE_ENTER: "phase.enter",
  PHASE_EXIT: "phase.exit",
  PHASE_VERIFY: "phase.verify",
  ROLE_CALL_START: "role.call.start",
  ROLE_CALL_END: "role.call.end",
  ROLE_CALL_FAILED: "role.call.failed",
  ROLE_VALIDATION_FAILED: "role.validation.failed",
  ROLE_SELF_REPAIR_ATTEMPTED: "role.self_repair.attempted",
  SYNTHESIZE_REQUESTED: "synthesize.requested",
  SYNTHESIZE_DELIVERED: "synthesize.delivered",
  AUDIT_FINDING_EMITTED: "audit.finding_emitted",
  INVESTIGATION_START_REQUESTED: "investigation.start_requested",
  INVESTIGATION_COMPLETED: "investigation.completed",
  INVESTIGATION_FAILED: "investigation.failed",
  INVESTIGATION_SPAWNED_FROM: "investigation.spawned_from",
  INVESTIGATION_CHASE_HALTED: "investigation.chase_halted",
  CLAIM_ASSERTED_BY_OPERATOR: "claim.asserted_by_operator",
  PAGE_ATTRIBUTION_COMPUTED: "page.attribution.computed",
  DECOMPOSE_QUESTION_REQUESTED: "decompose.requested",
  DECOMPOSE_QUESTION_DELIVERED: "decompose.delivered",
  DECOMPOSER_PARAPHRASE_FLAGGED: "decomposer.paraphrase.flagged",
  DECOMPOSER_REGENERATED: "decomposer.regenerated",
  PARAMETER_EXTRACT_REQUESTED: "parameter_extract.requested",
  PARAMETER_EXTRACT_DELIVERED: "parameter_extract.delivered",
  EVIDENCE_RETRIEVE_REQUESTED: "evidence.retrieve.requested",
  EVIDENCE_RETRIEVE_DELIVERED: "evidence.retrieve.delivered",
  EVIDENCE_PACK_BUILT: "evidence.pack_built",
  CONNECTOR_REQUESTED: "connector.requested",
  CONNECTOR_DELIVERED: "connector.delivered",
  CROSS_DOMAIN_KEYWORDS_RESOLVED: "cross_domain.keywords_resolved",
  CROSS_DOMAIN_TRAVERSAL_RAN: "cross_domain.traversal_ran",
  CONSTRAINT_PREFLIGHT: "constraint.preflight",
  CONSTRAINT_VIOLATION_FOUND: "constraint.violation_found",
  CONSTRAINT_REVISION_TRIGGERED: "constraint.revision_triggered",
  CONSTRAINT_LOOP_RESOLVED: "constraint.loop_resolved",
  GRAPH_NODE_INSERTED: "graph.node.inserted",
  GRAPH_EDGE_INSERTED: "graph.edge.inserted",
  GRAPH_TIER_OVERRIDDEN: "graph.tier.overridden",
  GRAPH_SUPERSESSION_PROPOSED: "graph.supersession.proposed",
  GRAPH_STALENESS_FLAGGED: "graph.staleness.flagged",
  NODE_MERGE: "graph.node.merge",
  EMBED_MODEL_REGISTER: "graph.embed_model.register",
  TIER_REWRITE_BULK: "graph.tier.rewrite_bulk",
  SUPERSESSION_APPLY: "graph.supersession.apply",
  SUPERSESSION_DISMISS: "graph.supersession.dismiss",
  SUPERSESSION_COEXIST: "graph.supersession.coexist",
  STALENESS_RESOLVE: "graph.staleness.resolve",
  SYNTHESIS_ARCHIVED: "synthesis.archived",
  SUBSTRATE_MANIFEST_WRITTEN: "synthesis.substrate_manifest.written",
  MASTER_MD_WRITTEN: "synthesis.master_md_written",
  MASTER_MD_SKIPPED: "synthesis.master_md_skipped",
  SKILL_PATCH_GATE_DECIDED: "skill.patch_gate_decided",
  SKILL_PATCH_GATE_REVIEWED: "skill.patch_gate_reviewed",
  AUTO_PATCH_APPLIED: "skill.auto_patch_applied",
  AUTO_PATCH_SKIPPED: "skill.auto_patch_skipped",
  OUTCOME_RECORDED: "outcome.recorded",
  RUBRIC_SCORED: "rubric.scored",
  USER_ACCEPT_DELTA: "user.accept_delta",
  USER_REJECT_DELTA: "user.reject_delta",
  USER_MODIFY_DELTA: "user.modify_delta",
  PIPELINE_TERMINATED: "pipeline.terminated",
  KE_LLM_RESPONSE_FAILED: "knowledge_extraction.llm_response.failed",
  DISPATCH_CALL: "dispatch.call",
  CONTEXT_PACK_ASSEMBLED: "context_pack.assembled",
  KNOWLEDGE_REUSED: "knowledge.reused",
  REUSE_GATED: "reuse.gated",
  GRAPH_TIER_ASSIGNED: "graph.tier.assigned",
  DOCUMENT_LOADED: "document.loaded",
  DOCUMENT_REGION_SELECTED: "document.region_selected",
  DISTILLATION_REQUESTED: "distillation.requested",
  DISTILLATION_DELIVERED: "distillation.delivered",
  CLAIM_CHALLENGE_RAISED: "claim.challenge_raised",
  CLAIM_GROUNDING_CHECK_PASSED: "claim.grounding_check_passed",
  CLAIM_GROUNDING_CHECK_FAILED: "claim.grounding_check_failed",
  NOTE_EMERGED: "note.emerged",
  NOTE_REFINED: "note.refined",
  NOTE_COMPRESSED_DOC_WRITTEN: "note.compressed_doc_written",
  QUESTION_IDENTIFIED: "question.identified",
  QUESTION_ESCALATED_TO_RESEARCH: "question.escalated_to_research",
  QUESTION_RESOLVED_BY_DOC: "question.resolved_by_doc",
  CROSS_DOC_QUESTION_ANSWERED: "cross_doc.question_answered",
  USER_ACCEPT_DISTILLATION: "user.accept_distillation",
  USER_REJECT_DISTILLATION: "user.reject_distillation",
  USER_EDIT_DISTILLATION: "user.edit_distillation",
  ARTIFACT_GENERATED: "artifact.generated",
  ARTIFACT_INTERACTED: "artifact.interacted",
  RLM_BRIDGE_DECIDED: "rlm.bridge.decided",
  QUALITY_GATE_EVALUATED: "quality_gate.evaluated",
  CROSS_GRAPH_CITATION_RECORDED: "cross_graph.citation.recorded",
  REV_SHARE_DECIDED: "rev_share.decided",
  PREFERENCE_OBSERVATION_RECORDED: "preference.observation.recorded",
  SKILL_RULE_PROMOTED: "skill_rule.promoted",
  DISCOVERY_PROPOSED: "discovery.proposed",
  DISCOVERY_SELECTED: "discovery.selected",
  FETCH_FALLBACK_ESCALATED: "fetch.fallback.escalated",
  VERIFIER_LOOKUP: "verifier.lookup",
  FEDERATION_PARTNER_REGISTERED: "federation.partner.registered",
  FEDERATION_PARTNER_TRUSTED: "federation.partner.trusted",
  FEDERATION_PARTNER_REVOKED: "federation.partner.revoked",
  FEDERATION_OUTBOUND_CITATION_EMITTED: "federation.outbound_citation.emitted",
  FEDERATION_INBOUND_CITATION_ACCEPTED: "federation.inbound_citation.accepted",
  FEDERATION_INBOUND_CITATION_REFUSED: "federation.inbound_citation.refused",
  VISUAL_FRAME_IDENTIFIED: "visual.frame_identified",
  VISUAL_CLAIMS_EXTRACTED: "visual.claims_extracted",
  VISUAL_ROLE_FAILED: "visual.role_failed",
  AI_ACTION_APPLIED: "ai.action.applied",
  AI_ACTION_UNDONE: "ai.action.undone",
  DP_ROUTED: "dp.routed",
  OUTLINE_BLOCK_PLACED: "outline_block.placed",
  OUTLINE_BLOCK_MOVED: "outline_block.moved",
  OUTLINE_BLOCK_REMOVED: "outline_block.removed",
  BOOK_SERVABILITY_CHANGED: "book.servability_changed",
  BOOK_TAKEN_DOWN: "book.taken_down",
  EDIT_CAPTURED: "edit.captured",
  SECTION_DRAFT_GENERATED: "section.draft_generated",
  SEAM_RESEARCH_TO_READ: "seam.research_to_read",
  SEAM_READ_TO_RESEARCH: "seam.read_to_research",
  SEAM_READ_TO_WRITE: "seam.read_to_write",
  SEAM_WRITE_TO_READ: "seam.write_to_read",
  SEAM_SPEAK_TO_WRITE: "seam.speak_to_write",
  SEAM_SPEAK_TO_READ: "seam.speak_to_read",
  SEAM_WRITE_TO_SPEAK: "seam.write_to_speak",
  VOICE_CAPTURED: "voice.captured",
  BLOCK_POSITIONED: "block.positioned",
  MARGINALIA_NOTED: "marginalia.noted",
  SOURCE_READ: "source.read",
  READ_BOOK_ANSWERED: "read.book_answered",
  READ_BOOK_ANSWER_JUDGED: "read.book_answer_judged",
  READ_META_READING_GENERATED: "read.meta_reading.generated",
  DOCUMENT_FILED_INTO_INVESTIGATION: "document.filed_into_investigation",
  GROUNDEDNESS_SCORED: "groundedness.scored",
  GROUNDEDNESS_FAILED: "groundedness.failed",
  DOCUMENT_CONTENT_CLASS_DEFAULTED: "document.content_class_defaulted",
  WORKER_IDENTITY: "worker.identity",
} as const;
export type ActionType = typeof ActionType[keyof typeof ActionType];

export type ConfidenceLevel = "high" | "moderate" | "low" | "unknown";

export type ArtifactKind = "comparison_grid" | "knob_slider_exploration" | "claim_triage" | "model_parameter_explorer" | "other";

export type TierClassificationMethod = "document_type_lookup" | "keyword_fallback" | "default";

export type TierAdjustmentMethod = "regex" | "llm" | "none";

export type StalenessResolution = "refreshed" | "confirmed_stale" | "dismissed";

export type ThesisOutcomeStatus = "confirmed" | "partially_confirmed" | "disconfirmed" | "unresolved";

export type ExecutionRiskSeverity = "critical" | "high" | "moderate" | "low" | "none";

export type DecisionRecommendation = "proceed" | "pass" | "conditional";

export type ActualDecision = "proceed" | "pass" | "conditional" | "not_observed";

export type ProceedOutcome = "confirmed" | "partially_confirmed" | "disconfirmed" | "not_observed";

export type SubQuestionCategory = "market_sizing" | "defensibility" | "unit_economics" | "team_and_execution" | "regulatory_exposure" | "competitive_dynamics" | "customer_concentration" | "technology_risk" | "capital_intensity" | "exit_pathways";

export type EvidenceTypeRequired = "quantitative" | "qualitative" | "mixed";

export type EvidenceType = "direct" | "inferred" | "gap";

export type EvidenceConfidence = "high" | "moderate" | "low" | "insufficient";

export type MetricValueType = "scalar" | "range" | "categorical" | "null";

export type EvidenceStatus = "observed" | "imputed";

export type TraversalAlgorithm = "shortest_simple_path" | "top_n_shortest_paths" | "depth_first_limited" | "bfs_semantic_stop";

export type ThesisRiskSeverity = "critical" | "high" | "moderate" | "low";

export type SynthesisRecommendation = "proceed" | "pass" | "conditional" | "undetermined" | "insufficient_evidence";

export type AuditSeverity = "info" | "warning" | "critical";

export type DiscoveryProvider = "exa" | "parallel" | "operator";

export type DiscoveryDecision = "ingested" | "rejected_by_legal_gate" | "rejected_by_operator" | "fetch_failed";

export type ProvenanceSourceKind = "user" | "ai" | "system";

/**
 * Exact derived HTML citation admitted by the research launch boundary.
 */
export interface DerivedCitationSource {
  derived_asset_id: string;
  revision_id: string;
  content_sha256: string;
  generation: number;
  citation_id: string;
  chunk_ordinal: number;
  chunk_text_sha256: string;
  excerpt: string;
}

/**
 * Immutable collection binding carried by manifest-launched events.
 */
export interface EvidenceManifestCollectionRef {
  collection_id: string;
  version: number;
  collection_sha256: string;
  ordinal: number;
}

/**
 * Compact provenance; exact excerpts remain owned by collections.
 */
export interface EvidenceManifestProvenance {
  manifest_id: string;
  version: number;
  manifest_sha256: string;
  collections: EvidenceManifestCollectionRef[];
  collection_count: number;
  total_passage_count: number;
}

/**
 * One layer of an assembled context pack. Embedded inside
 * ``ContextPackAssembledPayload.layers``.
 */
export interface ContextLayer {
  kind: "session" | "long_term_skill" | "reuse" | "graph_evidence" | "style_guide" | "phase_metadata" | "param_version_stamp";
  source: string;
  tokens: number;
}

/**
 * A typed unit of distilled truth. Embedded inside
 * ``DistillationDeliveredPayload.claims`` and referenced by
 * challenge / grounding-check events via ``claim_id``.
 * 
 * Why structured: a distillation stored as opaque prose cannot have
 * its claims extracted to graph nodes, cannot be diffed, cannot be
 * trained on. See ``docs/architecture_notes.md`` §13.1 (Layer 1).
 */
export interface Claim {
  claim_id: string;
  text: string;
  confidence: "high" | "moderate" | "low" | "unknown";
  attribution_region_ids: string[];
  node_id?: string | null;
}

/**
 * One thesis_components[i] outcome — does the claim hold against
 * the observed ground truth?
 */
export interface ThesisOutcome {
  thesis_claim: string;
  outcome: "confirmed" | "partially_confirmed" | "disconfirmed" | "unresolved";
  evidence?: string;
  evidence_chunk_ids?: string[];
}

/**
 * One falsification_conditions[i] check — did the predicted
 * failure condition occur?
 */
export interface FalsificationOutcome {
  condition: string;
  occurred: boolean;
  evidence?: string;
}

/**
 * One execution_risks[i] check — did the risk manifest, and how
 * severely vs the agent's anticipated severity?
 */
export interface ExecutionRiskOutcome {
  risk: string;
  manifested: boolean;
  severity_actual: "critical" | "high" | "moderate" | "low" | "none";
  evidence?: string;
}

/**
 * Decision-outcome correlation. ``thesis_outcome_when_proceeded``
 * is the structured grade — replaces keyword-scanning the prose
 * field per Researchmaxx cohort.py.
 */
export interface DecisionAlignment {
  agent_implicit_recommendation: "proceed" | "pass" | "conditional";
  actual_decision: "proceed" | "pass" | "conditional" | "not_observed";
  decision_outcome_at_observation: string;
  thesis_outcome_when_proceeded?: "confirmed" | "partially_confirmed" | "disconfirmed" | "not_observed";
}

/**
 * One evidence-addressable sub-question produced by the
 * Decomposer. ``rationale`` must explain why the sub-question carries
 * independent analytical weight — a deletable rationale is a signal
 * the sub-question is performative (prompts/decomposer.md anti-pattern
 * #4).
 */
export interface SubQuestion {
  sub_question: string;
  category: "market_sizing" | "defensibility" | "unit_economics" | "team_and_execution" | "regulatory_exposure" | "competitive_dynamics" | "customer_concentration" | "technology_risk" | "capital_intensity" | "exit_pathways";
  rationale: string;
  evidence_type_required: "quantitative" | "qualitative" | "mixed";
}

/**
 * One retrieval keyword + optional synonyms. ``synonyms`` is
 * capped at 3 by the prompt; the field is forward-additive (longer
 * lists are NOT rejected here so historical traces with permissive
 * schemas still validate).
 */
export interface Keyword {
  term: string;
  synonyms?: string[];
}

/**
 * One flagged sub-question record. Mirrors the
 * ``ParaphraseFlag`` dataclass in ``roles/decomposer/paraphrase.py``
 * so the bridge can serialize check results into the trajectory
 * without an adapter.
 */
export interface ParaphraseFlagRecord {
  index: number;
  sub_question: string;
  cosine: number;
}

/**
 * One evidence-cited claim produced by the Evidence Retriever.
 * 
 * ``source_tier_min`` is optional — ``None`` is the spec sentinel for
 * "below the schema floor"; ``0`` is REJECTED (the upstream prompt's
 * explicit prohibition). Valid integer range is [1, 5].
 */
export interface SupportingClaim {
  claim: string;
  evidence_type: "direct" | "inferred" | "gap";
  chunk_ids?: string[];
  edge_ids?: string[];
  source_tier_min?: number | null;
  confidence: "high" | "moderate" | "low" | "insufficient";
  confidence_basis: string;
}

/**
 * One enumerated gap. Gaps are first-class output — the prompt
 * explicitly treats absent answers as information, not failure.
 */
export interface EvidentiaryGap {
  gap_description: string;
  additional_retrieval_suggested?: string | null;
}

/**
 * Structured value attached to a Parameter. ``value_type`` is the
 * discriminator; ``value`` and ``unit`` are present only for the
 * numeric / categorical shapes.
 * 
 * The upstream "JSON null vs literal-string 'null'" rule (parser
 * normalizes both to the literal ``"null"``) is enforced one layer
 * higher in ``roles/parameter_extractor/parser.py`` — by the time a
 * ``MetricValue`` reaches this Pydantic model, ``value_type`` is
 * always a Literal string.
 */
export interface MetricValue {
  value_type: "scalar" | "range" | "categorical" | "null";
  value?: unknown | null;
  unit?: string | null;
}

/**
 * One design-critical parameter extracted from the evidence.
 * Mirrors the role's output schema verbatim — ``source_chunk_ids``
 * is a required list (the cite-every-claim discipline).
 */
export interface Parameter {
  semantic_anchor: string;
  metric_value: MetricValue;
  qualitative_descriptor?: string | null;
  evidence_status: "observed" | "imputed";
  source_chunk_ids?: string[];
  constraint_strictness: "hard" | "soft" | "target";
}

/**
 * Pydantic mirror of the Sprint 4 day 3-4 ``Constraint`` dataclass.
 * 
 * Named ``ConstraintSpec`` (not ``Constraint``) to avoid naming
 * collision with the dataclass that's already exported from
 * ``middleware/constraint_check/constraints.py``. The bridge handler
 * converts ``Parameter`` → ``ConstraintSpec`` at emit time via
 * ``roles.parameter_extractor.parameters_to_constraints``; the
 * Day 3 constraint-loop machinery reads ``ConstraintSpec`` records
 * from the typed trajectory and reconstructs ``Constraint``
 * dataclasses on the read side.
 */
export interface ConstraintSpec {
  constraint_id: string;
  strictness: "hard" | "soft" | "target";
  kind: "numeric_range" | "must_include_term" | "must_attribute";
  description: string;
  config?: Record<string, unknown>;
}

/**
 * One pre-resolved keyword → graph node mapping. ``low_confidence``
 * is True when ``similarity < 0.80`` (the upstream threshold);
 * the role must mark these but never silently drop them.
 */
export interface KeywordMapping {
  keyword: string;
  matched_node_id?: string | null;
  matched_node_label?: string | null;
  matched_node_type?: string | null;
  similarity: number;
  low_confidence?: boolean;
}

/**
 * One (source_node_id, target_node_id) pair for the connector
 * bridge to traverse between. Optional ``source_keyword`` /
 * ``target_keyword`` are passed through for trajectory legibility.
 */
export interface SeedPair {
  source_node_id: string;
  target_node_id: string;
  source_keyword?: string | null;
  target_keyword?: string | null;
}

/**
 * One structured path produced by traversal. Mirrors the dict
 * shape ``substrate.graph.traverse._format_path`` returns, augmented
 * with ``node_labels`` + ``edge_ids`` for citation back to the
 * underlying graph.
 */
export interface GraphPath {
  path_nodes: string[];
  path_relations: string[];
  depth: number;
  avg_confidence: number;
  node_labels?: string[];
  edge_ids?: string[];
}

/**
 * One NL rendering of a structured path. ``source_path_index`` is
 * the offset into the ``paths`` list, so the Synthesizer can cite
 * the underlying graph path verbatim.
 */
export interface NaturalLanguageRelationship {
  text: string;
  source_path_index: number;
}

/**
 * One load-bearing claim in the thesis. Must cite either
 * ``supporting_chunk_ids`` (evidence-grounded) OR
 * ``supporting_path_indices`` (analogy-grounded via connector
 * paths) — the upstream's "provenance is structural" rule. The
 * parser enforces this disjunction; the Pydantic model carries the
 * fields but doesn't reject empty-both at the schema layer.
 * 
 * ``effective_source_tier`` is in [1, 5] OR ``None``. ``0`` is
 * forbidden (the upstream prompt's explicit prohibition; defended
 * by ``Field(ge=1, le=5)``).
 */
export interface ThesisComponent {
  claim: string;
  confidence: "high" | "moderate" | "low" | "unknown";
  supporting_chunk_ids?: string[];
  supporting_path_indices?: number[];
  confidence_basis?: string | null;
  effective_source_tier?: number | null;
  hedging_required?: boolean;
}

/**
 * One falsification condition. ``specific_observable`` is required
 * — the prompt's anti-pattern #1 is "vacuous falsification
 * conditions" and the parser-side check enforces a minimum length.
 */
export interface FalsificationCondition {
  condition: string;
  specific_observable: string;
  timeframe?: string | null;
}

/**
 * One execution risk. ``severity_if_manifested`` is the
 * four-value scale (no "none" — risks with no possible severity
 * aren't risks).
 */
export interface ExecutionRisk {
  risk: string;
  severity_if_manifested: "critical" | "high" | "moderate" | "low";
  leading_indicator?: string | null;
}

/**
 * One {constraint, justification} record. Emitted when the
 * synthesizer relaxes a soft constraint and the relaxation must be
 * explicitly defensible.
 */
export interface ViolationJustification {
  constraint: string;
  justification: string;
}

/**
 * The synthesizer's reported compliance against the
 * parameter_extractor's constraints. The constraint loop machinery
 * (Sprint 7 day 3) compares this against its own evaluation —
 * a synthesizer that claims ``hard_constraints_satisfied=True``
 * while the evaluator finds hard violations is caught at loop
 * time.
 */
export interface ConstraintCompliance {
  hard_constraints_satisfied: boolean;
  soft_constraints_violated?: string[];
  violations_justified?: ViolationJustification[];
}

/**
 * One deduplicated substrate path the thesis components drew on.
 * ``support_summary`` must be ≥20 characters — the upstream prompt's
 * explicit minimum so "supports the thesis" doesn't survive
 * validation.
 */
export interface ReasoningPathUsed {
  path_node_ids: string[];
  path_edge_ids?: string[];
  support_summary: string;
}

/**
 * One row of a `VerifierLookupPayload.results`. Mirrors the
 * cleaned-snippet shape Exa returns for `/search?text=true` (or
 * a `/contents` call). NOT promoted to substrate evidence — the
 * snippet is verifier-tier context only.
 */
export interface ExaLookupResult {
  url: string;
  title?: string | null;
  published_date?: string | null;
  text_snippet?: string | null;
  relevance_score?: number | null;
  provider_response_id?: string | null;
}

/**
 * One page-level citation in a saved meta-reading asset. It carries a
 * REFERENCE (chunk_id + the document + the resolved reader page), never the
 * source body — opening it re-derives the body through the §9.0 serve gate.
 * ``page_index`` is the 0-based reader page the chunk anchors to, or null when
 * ``section_path`` did not resolve to a ``Page N`` marker (then
 * ``page_resolved`` is False and the surface shows an honest "page not
 * pinpointed", never a fabricated page — rigor #1).
 */
export interface MetaReadingCitation {
  chunk_id: string;
  document_id: string;
  page_index?: number | null;
  page_resolved?: boolean;
}

export interface BookAnswerCitation {
  chunk_id: string;
  document_id: string;
  page_index?: number | null;
  page_resolved?: boolean;
  snippet: string;
}

/**
 * One per-claim entailment verdict. ``score`` is the claim's
 * groundedness in [0, 1]; ``supported`` is the binary verdict the
 * backend reached (score above its supported-threshold). ``cited_chunk_ids``
 * is the EXISTING claim→chunk provenance the verdict rests on — a claim
 * with no cited chunk cannot be grounded (``score`` floors at 0.0,
 * ``supported`` False), which is the truth-axis distinction from the
 * style rubric's citation_density (density counts citations but never
 * checks they SUPPORT the claim).
 */
export interface ClaimGroundednessVerdict {
  claim: string;
  score: number;
  supported: boolean;
  cited_chunk_ids?: string[];
  rationale?: string;
}

/**
 * Emitted by ``substrate/dispatch/`` on every LLM provider call.
 * 
 * The cost-tracking decorator populates these fields after the call
 * returns; the event is then written to the trajectory.
 * 
 * The five optional ``*_ext`` fields below carry the token-burn telemetry
 * antiek-yegge-execute SPR-01 specified as a *separate* ``token_burn`` event.
 * That was a substrate-fit defect against current main: ``DISPATCH_CALL`` is
 * already the canonical per-LLM-call token+cost event (``cost_view.py``:
 * "every cent comes off a DispatchCallPayload"), so a second event would fork
 * the convention. Instead the fields land here, default-None, so every
 * existing emitter and cost_view read stays byte-identical and SPR-05's
 * dashboards query the enriched DISPATCH_CALL rather than a duplicate.
 * Operator decision 2026-07-02 (extend, don't fork).
 */
export interface DispatchCallPayload {
  action_type: "dispatch.call";
  provider: string;
  model: string;
  tier: "flash" | "pro" | "synthesis" | "verify" | "local";
  target_role: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
  verification_required?: boolean;
  fallback_chain_index?: number;
  prompt_hash: string;
  finish_reason?: "stop" | "length" | "tool_use" | "content_filter" | "error" | null;
  context_pack_event_id?: string | null;
  cached_input_tokens?: number;
  task_id?: string | null;
  parent_run_id?: string | null;
  feature_label?: string | null;
  session_id?: string | null;
  nd_session_id?: string | null;
  nd_recommended_provider?: string | null;
  nd_recommended_model?: string | null;
  nd_tradeoff?: string | null;
  nd_decision_latency_ms?: number | null;
  nd_bypassed?: boolean;
  nd_bypass_reason?: string | null;
}

/**
 * Records the registration of a first-class worker by the worker registry
 * (antiek-yegge-execute SPR-04, not yet built). One event per spawn.
 * 
 * Added by SPR-01 (yegge-execute) on 2026-07-02. event_log stores the
 * ``worker_id`` string verbatim — UUID-v7 validity + sortability is SPR-04's
 * responsibility, not event_log's; this payload does not validate the id's
 * shape, only that it is non-empty. ``spawn_kind`` IS validated against the
 * closed set so a typo (e.g. "async") cannot land as an un-queryable string.
 */
export interface WorkerIdentityPayload {
  action_type: "worker.identity";
  worker_id: string;
  parent_worker_id?: string | null;
  role: string;
  session_id: string;
  spawn_kind: "subprocess" | "asyncio_task" | "thread" | "role_invocation" | "variant";
  expected_lifetime_s?: number | null;
  context_hash?: string | null;
}

/**
 * Emitted by ``substrate/context_pack/`` after each pack assembly.
 * 
 * Captures what the model actually saw at decision time — the layered
 * composition + budget reality. This is the queryable property that
 * backs §2.5's "what did the model actually see when it made this
 * decision" guarantee.
 */
export interface ContextPackAssembledPayload {
  action_type: "context_pack.assembled";
  target_role: string;
  target_tokens: number;
  actual_tokens: number;
  layers: ContextLayer[];
  budget_overrun: boolean;
  truncation_strategy_applied?: "head" | "tail" | "smart" | null;
}

/**
 * AFF SPR-06 — emitted once per investigation start by
 * ``substrate/context_pack/knowledge_reuse.py`` after the reuse layer is
 * assembled into the pack. The queryable provenance of the flywheel's reuse
 * decision: which prior knowledge units were injected, their REAL cosine
 * scores, why each retrieved unit was injected or dropped, where each came
 * from, and the ``CONTEXT_PACK_ASSEMBLED`` event this reuse rides on.
 * 
 * Field contract:
 * 
 * * ``reused_unit_ids`` / ``scores`` describe the INJECTED set only and are
 *   EQUAL-LENGTH, in pack (similarity-desc, id-tiebreak) order. ``scores`` are
 *   the real cosine similarities, never a floor (honesty, rigor #1).
 * * ``decisions`` / ``source_investigation_ids`` describe EVERY retrieved unit
 *   (injected + dropped), equal-length to each other. A ``decision`` is one of
 *   ``injected`` | ``dropped-not-servable`` | ``dropped-over-budget`` |
 *   ``dropped-low-relevance`` — the honest, distinct reason for the unit's fate.
 * * ``context_pack_event_id`` is the assembled pack's event id, so a reuse
 *   decision is joinable to exactly what the model saw.
 * 
 * An empty ``reused_unit_ids`` is valid and expected for a novel question or
 * an all-non-servable / all-over-budget retrieval — the event is STILL emitted
 * (reuse-of-nothing is recorded, not skipped).
 */
export interface KnowledgeReusedPayload {
  action_type: "knowledge.reused";
  reused_unit_ids: string[];
  scores: number[];
  decisions: string[];
  source_investigation_ids: string[];
  context_pack_event_id: string;
}

/**
 * AFF SPR-08 — emitted once per knowledge unit EXCLUDED from reuse by the
 * groundedness + §9.0 servability gate (``substrate/flywheel/reuse_gate.py``),
 * BEFORE any unit text reaches the context pack. An ADMITTED unit emits NO
 * reuse.gated event — absence of this event for a reused unit is the signal
 * that it cleared both conditions.
 * 
 * Why this exists (the honesty thesis): the flywheel reuses prior knowledge
 * into NEW investigations (SPR-06), so an ungrounded unit does not merely sit
 * in the graph — it seeds the next synthesis. Without this gate the loop
 * amplifies hallucination at the same rate it amplifies signal. The gate does
 * NOT make reuse "safe"; it excludes below-threshold + non-servable units and
 * logs every exclusion here.
 * 
 * Field contract:
 * 
 * * ``unit_id`` / ``source_investigation_id`` — the excluded unit and where it
 *   came from.
 * * ``groundedness_score`` — the unit's score from the shipped #27 lexical
 *   entailment scorer (``substrate/eval/groundedness``); ``None`` only when the
 *   unit's slot was unset AND the gate could not resolve its cited chunk text
 *   to re-score (an honest "unknown", which is itself below any threshold).
 * * ``scorer_id`` — which scorer produced the score (``groundedness-lexical-v1``),
 *   so the number is attributable + reproducible.
 * * ``threshold`` — ``REUSE_GROUNDEDNESS_THRESHOLD`` in force at the decision
 *   (carried on the event so an audit reads the exact bar, not today's value).
 * * ``reasons`` — every reason that applied: ``below-threshold`` and/or
 *   ``non-servable``. BOTH when both apply; never empty for an excluded unit.
 * * ``context_pack_event_id`` — the assembled pack this exclusion is scoped to,
 *   so the gate decision is joinable to exactly what the model did (not) see.
 */
export interface ReuseGatedPayload {
  action_type: "reuse.gated";
  unit_id: string;
  source_investigation_id: string;
  groundedness_score?: number | null;
  scorer_id: string;
  threshold: number;
  reasons: ("below-threshold" | "non-servable" | "non-owner-readable")[];
  context_pack_event_id?: string;
}

export interface DocumentLoadedPayload {
  action_type: "document.loaded";
  media_type: "pdf" | "pasted_text" | "url_extracted" | "markdown";
  content_hash: string;
  size_bytes: number;
  title?: string | null;
  page_count?: number | null;
  source_uri?: string | null;
}

export interface DocumentRegionSelectedPayload {
  action_type: "document.region_selected";
  region_id: string;
  page?: number | null;
  char_start: number;
  char_end: number;
  bbox?: [number, number, number, number] | null;
  text_excerpt: string;
}

export interface DistillationRequestedPayload {
  action_type: "distillation.requested";
  region_id?: string | null;
  user_prompt: string;
  target_token_count: number;
}

/**
 * Structured per architecture_notes §13.1 (Layer 1). The distillation
 * is a list of typed Claims plus a prose rendering. Storing only an HTML
 * or string blob would block claim extraction, diffing, and training.
 */
export interface DistillationDeliveredPayload {
  action_type: "distillation.delivered";
  request_event_id: string;
  claims: Claim[];
  rendered_text: string;
  rendered_text_hash: string;
  token_count: number;
}

/**
 * ``challenged_claim_id`` references a Claim from a prior
 * DistillationDelivered. None means the user challenged a claim that
 * isn't (yet) in the system — ``claim_text`` carries it verbatim.
 */
export interface ClaimChallengeRaisedPayload {
  action_type: "claim.challenge_raised";
  challenged_claim_id?: string | null;
  claim_text: string;
  anchor_region_id?: string | null;
  user_question: string;
}

export interface ClaimGroundingCheckPassedPayload {
  action_type: "claim.grounding_check_passed";
  claim_id?: string | null;
  claim_text: string;
  located_region_id: string;
  confidence: number;
}

export interface ClaimGroundingCheckFailedPayload {
  action_type: "claim.grounding_check_failed";
  claim_id?: string | null;
  claim_text: string;
  reason: "absent_from_source" | "paraphrased_not_stated" | "out_of_scope" | "ambiguous";
  searched_regions: string[];
}

export interface NoteEmergedPayload {
  action_type: "note.emerged";
  note_id: string;
  note_text: string;
  source_event_ids: string[];
  confidence?: "high" | "moderate" | "low" | "unknown";
  node_id?: string | null;
}

export interface NoteRefinedPayload {
  action_type: "note.refined";
  note_id: string;
  previous_text: string;
  new_text: string;
  refinement_reason: string;
}

export interface NoteCompressedDocWrittenPayload {
  action_type: "note.compressed_doc_written";
  output_path: string;
  note_count: number;
  byte_size: number;
}

export interface QuestionIdentifiedPayload {
  action_type: "question.identified";
  question_id: string;
  question_text: string;
  anchor_region_id?: string | null;
}

export interface QuestionEscalatedToResearchPayload {
  action_type: "question.escalated_to_research";
  question_id: string;
  child_investigation_id: string;
}

export interface QuestionResolvedByDocPayload {
  action_type: "question.resolved_by_doc";
  question_id: string;
  answer_note_id: string;
}

export interface CrossDocQuestionAnsweredPayload {
  action_type: "cross_doc.question_answered";
  question_id: string;
  question_document_id: string;
  answer_document_id: string;
  answer_note_id: string;
}

export interface UserAcceptDistillationPayload {
  action_type: "user.accept_distillation";
  distillation_event_id: string;
}

export interface UserRejectDistillationPayload {
  action_type: "user.reject_distillation";
  distillation_event_id: string;
  reason: string;
}

/**
 * The edited content is in the payload (mirrors NoteRefined). Hashes
 * are for integrity; trajectory replay needs the actual text.
 */
export interface UserEditDistillationPayload {
  action_type: "user.edit_distillation";
  distillation_event_id: string;
  edited_content: string;
  original_content_hash: string;
  edited_content_hash: string;
}

/**
 * Emitted when a role generates an interactive HTML exploration
 * artifact on disk. The HTML itself is opaque to the substrate; the
 * structured intent lives here. See architecture_notes §13.1 Layer 4.
 */
export interface ArtifactGeneratedPayload {
  action_type: "artifact.generated";
  artifact_id: string;
  artifact_kind: "comparison_grid" | "knob_slider_exploration" | "claim_triage" | "model_parameter_explorer" | "other";
  intent: string;
  generating_role: string;
  artifact_path: string;
  content_hash: string;
  size_bytes: number;
  source_event_ids: string[];
}

/**
 * Lifecycle event for an artifact (opened / closed / dismissed).
 * Substantive interactions inside the artifact emit their own typed
 * events (user.accept_distillation, claim.challenge_raised, etc.); this
 * event captures the lifecycle envelope only.
 */
export interface ArtifactInteractedPayload {
  action_type: "artifact.interacted";
  artifact_id: string;
  interaction_kind: "opened" | "closed" | "dismissed";
}

/**
 * Emitted once per document when the rule-based classifier assigns a
 * tier at ingestion. The asymmetric design (rule-based assignment;
 * LLM may only adjust DOWNWARD via TierOverriddenPayload) is preserved
 * from Researchmaxx per architecture_notes §4.
 */
export interface TierAssignedPayload {
  action_type: "graph.tier.assigned";
  document_id: string;
  document_type?: string | null;
  assigned_tier: number;
  classification_method: "document_type_lookup" | "keyword_fallback" | "default";
  keyword_matches?: string[];
}

/**
 * LLM-mediated downward adjustment after extraction. The asymmetry
 * is enforced by the middleware: ``adjusted_tier >= original_tier``
 * always (lower number = higher trust; the LLM can argue a source is
 * less reliable than the rules say, never more).
 */
export interface TierOverriddenPayload {
  action_type: "graph.tier.overridden";
  chunk_id: string;
  original_tier: number;
  adjusted_tier: number;
  adjustment_method: "regex" | "llm" | "none";
  hedging_signals: string[];
  reason: string;
}

/**
 * A global reclassification sweep. Not scoped to a single
 * investigation — the envelope's investigation_id is conventionally
 * ``substrate.constants.SYSTEM_INVESTIGATION_ID`` (``"system"``).
 */
export interface TierRewriteBulkPayload {
  action_type: "graph.tier.rewrite_bulk";
  total: number;
  updated: number;
  unchanged: number;
  by_tier: Record<number, number>;
}

/**
 * Emitted when the staleness scanner queues a flag for an edge whose
 * age exceeds the TTL for its claim_class. Flags are advisory — they
 * queue the entity for refresh in the next investigation that touches
 * it, not auto-invalidation.
 */
export interface StalenessFlaggedPayload {
  action_type: "graph.staleness.flagged";
  flag_id: string;
  edge_id: string;
  relation: string;
  claim_class: string;
  ttl_days: number;
  age_days: number;
}

/**
 * Emitted when a stale flag is resolved (refreshed / confirmed stale
 * / dismissed). ``entity_kind`` is currently always 'edge' — the
 * scanner only flags edges — but the Literal allows future expansion
 * without a schema bump if we add node-level flags.
 */
export interface StalenessResolvePayload {
  action_type: "graph.staleness.resolve";
  flag_id: string;
  entity_kind: "edge" | "node";
  entity_id: string;
  status: "refreshed" | "confirmed_stale" | "dismissed";
  notes?: string;
}

/**
 * Emitted by ``middleware/archive/`` when a synthesis is committed
 * to the syntheses table. The envelope's ``synthesis_id`` carries the
 * archived id; the payload carries the high-level metadata an
 * analytics consumer needs WITHOUT reading the full synthesis row.
 * 
 * Architecture_notes §4: archive is the only writer to the syntheses
 * table. This event is the canonical "synthesis exists now" signal
 * for downstream consumers (backtest, cohort, weekly_report).
 */
export interface SynthesisArchivedPayload {
  action_type: "synthesis.archived";
  target_question: string;
  synthesis_timestamp: string;
  status: "draft" | "passed" | "regressed" | "max_iterations_reached" | "escalated";
  implicit_recommendation: "proceed" | "pass" | "conditional" | "undetermined" | "insufficient_evidence";
  model_versions?: Record<string, string>;
  thesis_token_count?: number;
  has_constraint_check_result?: boolean;
}

/**
 * Emitted when the substrate manifest for an archived synthesis is
 * pinned (one row per (synthesis_id, entity_kind, entity_id) tuple in
 * the ``synthesis_substrate_manifest`` table). The envelope's
 * ``synthesis_id`` links back to the synthesis.
 */
export interface SubstrateManifestWrittenPayload {
  action_type: "synthesis.substrate_manifest.written";
  synthesis_timestamp: string;
  manifest_rows_written: number;
  counts_by_kind: Record<string, number>;
}

/**
 * Reviewer chose ``apply_supersession``: the old edge is closed
 * (``valid_until`` set) and linked to the new edge via
 * ``superseded_by``.
 */
export interface SupersessionApplyPayload {
  action_type: "graph.supersession.apply";
  candidate_id: string;
  old_edge_id: string;
  new_edge_id: string;
  new_valid_until: string;
  reviewer: string;
  review_notes?: string;
}

/**
 * Reviewer chose ``dismiss_new`` or ``dismiss_old``: one edge is
 * closed without superseding the other. ``target`` records which
 * side was dismissed.
 */
export interface SupersessionDismissPayload {
  action_type: "graph.supersession.dismiss";
  candidate_id: string;
  edge_id: string;
  target: "new" | "old";
  valid_until: string;
  reviewer: string;
  review_notes?: string;
}

/**
 * Reviewer chose ``coexist``: both edges remain active. The
 * candidate is marked reviewed but no edge mutation occurs.
 */
export interface SupersessionCoexistPayload {
  action_type: "graph.supersession.coexist";
  candidate_id: string;
  reviewer: string;
  review_notes?: string;
}

/**
 * Emitted by ``substrate/graph/ops.insert_node`` after a node row
 * is committed. The envelope's ``investigation_id`` carries scope;
 * the payload carries the identity + typing the node was admitted
 * under so a downstream consumer can reconstruct "what was in the
 * graph when this synthesis ran" without re-reading the row.
 */
export interface GraphNodeInsertedPayload {
  action_type: "graph.node.inserted";
  node_id: string;
  canonical_label: string;
  node_type: "entity" | "organization" | "person" | "property" | "metric" | "mechanism" | "claim" | "method" | "constraint" | "insight" | "question";
  graph_scope: "depth" | "cross_domain" | "constraint";
  has_embedding: boolean;
}

/**
 * Emitted by ``substrate/graph/ops.insert_edge`` after an edge row
 * is committed. Records the source/target/relation triple, the
 * source attribution (document + chunk + tier), and the extraction
 * confidence the extractor assigned at admission.
 */
export interface GraphEdgeInsertedPayload {
  action_type: "graph.edge.inserted";
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  relation: string;
  source_document_id?: string | null;
  chunk_id?: string | null;
  source_tier: number;
  extraction_confidence: number;
  graph_scope: "depth" | "cross_domain" | "constraint";
}

/**
 * Emitted when a constraint check identifies a violation. One
 * event per violation per iteration — a synthesis can produce many
 * of these inside a single constraint loop pass.
 */
export interface ConstraintViolationFoundPayload {
  action_type: "constraint.violation_found";
  constraint_id: string;
  strictness: "hard" | "soft" | "target";
  constraint_kind: "numeric_range" | "must_include_term" | "must_attribute";
  iteration: number;
  target_claim_id?: string | null;
  reason: string;
}

/**
 * Emitted when the constraint loop decides to re-invoke the
 * synthesizer because at least one HARD constraint is still violated
 * after the latest iteration. The triggering_constraint_ids list lets
 * a downstream cohort analysis correlate which constraint kinds
 * consume the most iterations.
 */
export interface ConstraintRevisionTriggeredPayload {
  action_type: "constraint.revision_triggered";
  iteration: number;
  triggering_constraint_ids: string[];
}

/**
 * Emitted exactly once per constraint loop, on termination. The
 * ``final_status`` mirrors the Researchmaxx terminal vocabulary so a
 * migrated cohort backtest stays compatible.
 */
export interface ConstraintLoopResolvedPayload {
  action_type: "constraint.loop_resolved";
  final_status: "single_pass" | "passed" | "regressed" | "max_iterations_reached" | "escalated" | "preflight_failed";
  total_iterations: number;
  final_violation_count: number;
}

/**
 * Emitted by ``middleware/outcomes/`` when an outcome row is
 * written against a previously-archived synthesis. The envelope's
 * ``synthesis_id`` carries the archived synthesis the outcome
 * grades against.
 */
export interface OutcomeRecordedPayload {
  action_type: "outcome.recorded";
  outcome_id: string;
  observer: string;
  thesis_outcomes?: ThesisOutcome[];
  falsification_outcomes?: FalsificationOutcome[];
  execution_risk_outcomes?: ExecutionRiskOutcome[];
  decision_alignment?: DecisionAlignment | null;
  notes?: string;
}

/**
 * Emitted by a verification skill (the constraint middleware's
 * deterministic-rubric + judged-rubric pairing per architecture_notes
 * §3.2). Captures both component scores plus the final aggregated
 * score so cohort analysis can correlate verification quality to
 * synthesizer outcomes.
 * 
 * All three score fields are in [0, 1] when set. Deterministic
 * component may be None when the rubric is purely judgmental;
 * judged component may be None when the rubric is purely
 * deterministic; final_score is always required.
 */
export interface RubricScoredPayload {
  action_type: "rubric.scored";
  rubric_id: string;
  target_claim_id?: string | null;
  deterministic_score?: number | null;
  judged_score?: number | null;
  final_score: number;
  notes?: string;
}

/**
 * Emitted NON-blocking on the live Phase-6 path (Foundation v2
 * SPR-02) alongside the SECONDARY form-axis ``rubric.scored``. The
 * truth-axis signal: for each load-bearing thesis claim, does the
 * EVIDENCE it cites ENTAIL the claim? ``groundedness_score`` is the
 * mean per-claim score over claims that carry chunk citations;
 * ``per_claim`` rides along for inspection. ``backend`` records which
 * entailment backend produced the verdicts (``lexical`` deterministic
 * default, ``nli`` deterministic gate-grade backend, or ``llm_judge``)
 * so a reader knows whether the number is reproducible.
 * ``scored_claims`` / ``total_claims`` make the coverage explicit
 * (analogy-only claims with no chunk citation are excluded from the
 * mean but counted in ``total_claims``).
 * 
 * Observability-only this sprint — it gates nothing until M5's
 * promote-to-gate criterion is met in a later sprint.
 */
export interface GroundednessScoredPayload {
  action_type: "groundedness.scored";
  scorer_id: string;
  backend: "lexical" | "nli" | "llm_judge";
  groundedness_score: number;
  scored_claims: number;
  total_claims: number;
  supported_threshold: number;
  per_claim?: ClaimGroundednessVerdict[];
  notes?: string;
}

/**
 * Emitted when the groundedness (or style-rubric) scorer raises on
 * the live Phase-6 path. This is the event that REPLACES the Phase-6
 * ``except Exception: pass`` swallow (Foundation v2 SPR-02): a scorer
 * crash must SURFACE, never silently drop the quality signal. The phase
 * stays non-blocking — the orchestrator logs + emits this and proceeds —
 * so "non-blocking" never again means "the signal disappeared".
 * 
 * ``stage`` says which scorer crashed (``groundedness`` or ``rubric``);
 * ``error_type`` + ``error`` carry the exception class + message for
 * triage.
 */
export interface GroundednessFailedPayload {
  action_type: "groundedness.failed";
  scorer_id: string;
  stage: "groundedness" | "rubric";
  error_type: string;
  error: string;
}

/**
 * Emitted when ``PhaseLog.enter(phase_id)`` is called. The
 * envelope's ``phase`` field carries the phase id; the payload
 * captures the per-enter breadcrumbs the orchestrator started
 * attaching for Phase 8 (knowledge extraction).
 */
export interface PhaseEnterPayload {
  action_type: "phase.enter";
  entered_at: string;
  note?: string | null;
  metadata_json?: string | null;
}

/**
 * Emitted when ``PhaseLog.exit(phase_id)`` is called. ``outputs_hash``
 * is the SHA-256 hash of the phase's output artifacts (paths +
 * contents), computed at exit time so re-runs are observable.
 */
export interface PhaseExitPayload {
  action_type: "phase.exit";
  exited_at: string;
  outputs_hash?: string | null;
}

/**
 * Emitted when ``PhaseLog.verify(phase_id, evidence=...)`` is called.
 * ``verification_evidence`` is freeform — a path, a query result, an
 * SHA-256, or a 1-line proof — stored verbatim so a reviewer can audit
 * why ``verify()`` was called. Load-bearing for Phase 8: without a
 * verify event the phase did not actually compound the knowledge graph.
 */
export interface PhaseVerifyPayload {
  action_type: "phase.verify";
  verified_at: string;
  verification_evidence: string;
}

/**
 * Emitted by upstream callers (heartbeat, kanban, interview
 * workflow) to request a Decomposer run. The bridge handler
 * subscribes to this action_type, dispatches the role, and emits
 * ``DECOMPOSE_QUESTION_DELIVERED`` when done.
 * 
 * ``context`` is optional domain framing — empty string when the
 * caller has nothing extra to say.
 */
export interface DecomposeQuestionRequestedPayload {
  action_type: "decompose.requested";
  question: string;
  context?: string;
}

/**
 * Emitted by the Decomposer bridge once a (possibly regenerated)
 * decomposition has been produced. Carries the structured output
 * plus the paraphrase-guard outcome — ``paraphrase_pass_count`` is
 * 1 for a clean first pass, 2 for a regenerated pass.
 */
export interface DecomposeQuestionDeliveredPayload {
  action_type: "decompose.delivered";
  decomposition: SubQuestion[];
  keywords: Keyword[];
  paraphrase_pass_count?: number;
  paraphrase_flagged_count_final?: number;
}

/**
 * Emitted when the paraphrase check on a Decomposer pass finds
 * one or more sub-questions whose embedding sits within cosine
 * similarity ≥ DECOMPOSER_PARAPHRASE_COSINE_MAX of the top-level
 * question. The bridge follows this with a regeneration pass.
 */
export interface DecomposerParaphraseFlaggedPayload {
  action_type: "decomposer.paraphrase.flagged";
  pass_index: number;
  n_sub_questions: number;
  flagged: ParaphraseFlagRecord[];
}

/**
 * Emitted exactly once when the Decomposer's regeneration pass
 * completes. ``still_flagged`` is True when the second pass also
 * produced paraphrases — the bridge still proceeds (one regen is the
 * upstream's hard cap) but surfaces the failure mode on the
 * trajectory.
 */
export interface DecomposerRegeneratedPayload {
  action_type: "decomposer.regenerated";
  flagged_after_regen: ParaphraseFlagRecord[];
  still_flagged: boolean;
}

/**
 * Emitted when ``synthesis_to_master.generate_master_md`` writes
 * a fresh MASTER.md. ``byte_count`` is the on-disk size after the
 * atomic write; ``topic_slug`` is the directory slug used (auto-
 * derived from the synthesis's target_question when no override
 * was passed).
 */
export interface MasterMdWrittenPayload {
  action_type: "synthesis.master_md_written";
  path: string;
  synthesis_id: string;
  byte_count: number;
  topic_slug?: string | null;
  param_version: string;
}

/**
 * Emitted when ``synthesis_to_master`` skips regeneration because
 * a MASTER.md with the same synthesis_id marker already exists.
 * ``reason`` is the closed enum string (currently always
 * ``idempotent_match``; left as a free string for forward additivity).
 */
export interface MasterMdSkippedPayload {
  action_type: "synthesis.master_md_skipped";
  path: string;
  synthesis_id: string;
  byte_count: number;
  topic_slug?: string | null;
  reason?: string;
}

/**
 * Emitted when the Phase-8 skill-patch gate evaluates a candidate.
 * Shadow mode records whether the same candidate would have been accepted
 * under enforcing mode, but still allows the write path to proceed. Enforcing
 * mode records the actual accept/reject decision before any skill writer
 * mutates files.
 */
export interface SkillPatchGateDecidedPayload {
  action_type: "skill.patch_gate_decided";
  synthesis_id: string;
  patch_id: string;
  mode: string;
  decision: string;
  would_accept: boolean;
  baseline_backtest_score: number;
  candidate_backtest_score: number;
  delta: number;
  epsilon_required: number;
  cohort_size: number;
  minimum_cohort_size: number;
  matched_domains?: string[];
  notes?: string;
  operator_reviewed?: boolean;
  operator_agreed?: boolean | null;
}

/**
 * Operator review of a prior Phase-8 gate decision.
 * The review states whether the operator believes the candidate patch should
 * have been accepted. Agreement is derived by comparing ``operator_accept``
 * with the linked decision's ``would_accept`` value.
 */
export interface SkillPatchGateReviewedPayload {
  action_type: "skill.patch_gate_reviewed";
  synthesis_id: string;
  patch_id: string;
  decision_event_id: string;
  reviewer: string;
  operator_accept: boolean;
  review_notes?: string;
}

/**
 * Emitted by ``skills/domain/auto_patch.patch_from_synthesis``
 * after a per-synthesis patch lands. ``patched`` / ``skipped`` /
 * ``errors`` mirror the upstream result dict shape so a backfill
 * operator CLI can render the same summary the legacy
 * skill_patcher prints.
 */
export interface AutoPatchAppliedPayload {
  action_type: "skill.auto_patch_applied";
  synthesis_id: string;
  matched_domains?: string[];
  patched?: string[];
  skipped?: string[];
  errors?: Record<string, string>[];
  status: string;
}

/**
 * Emitted when a synthesis matched a domain but its skill file
 * already carries the synthesis_id marker. Distinct from
 * ``MasterMdSkippedPayload`` because mechanical skill backfill is a
 * separate seam from MASTER.md regeneration — both surface independent
 * idempotency outcomes.
 */
export interface AutoPatchSkippedPayload {
  action_type: "skill.auto_patch_skipped";
  synthesis_id: string;
  domain: string;
  skill_path: string;
}

/**
 * Emitted by upstream callers (Decomposer downstream, manual
 * invocation, batch backfill) to request an Evidence Retriever
 * dispatch. The bridge subscribes to this action_type, dispatches
 * the role at the flash tier, and emits
 * ``EVIDENCE_RETRIEVE_DELIVERED`` when done.
 * 
 * ``chunks_block`` and ``subgraph_block`` are the **rendered**
 * context strings the bridge upstream produced from its retrieval
 * layer — they ride inside the request so the role's input is fully
 * reconstructable from the trajectory (no opaque DB lookup needed
 * at replay time).
 */
export interface EvidenceRetrieveRequestedPayload {
  action_type: "evidence.retrieve.requested";
  sub_question: string;
  category: "market_sizing" | "defensibility" | "unit_economics" | "team_and_execution" | "regulatory_exposure" | "competitive_dynamics" | "customer_concentration" | "technology_risk" | "capital_intensity" | "exit_pathways";
  evidence_type_required: "quantitative" | "qualitative" | "mixed";
  top_k?: number;
  chunks_block: string;
  subgraph_block: string;
}

/**
 * Emitted by the Evidence Retriever bridge once a parsed +
 * validated response lands. ``insufficient_evidence=True`` means
 * the role explicitly declined to answer; the downstream
 * constraint loop / synthesizer reads this flag before composing.
 */
export interface EvidenceRetrieveDeliveredPayload {
  action_type: "evidence.retrieve.delivered";
  sub_question: string;
  answer: string;
  supporting_claims?: SupportingClaim[];
  evidentiary_gaps?: EvidentiaryGap[];
  insufficient_evidence?: boolean;
}

/**
 * Emitted by upstream callers (orchestrator after evidence
 * retrieval finishes) to request a Parameter Extractor dispatch.
 * ``evidence_block`` is the pre-rendered JSON-stringified list of
 * Evidence Retriever outputs, one block per sub-question.
 */
export interface ParameterExtractRequestedPayload {
  action_type: "parameter_extract.requested";
  evidence_block: string;
}

/**
 * Emitted by the Parameter Extractor bridge once a parsed +
 * validated response lands.
 * 
 * Two fields:
 * - ``parameters`` — the role's literal output, preserved verbatim
 *   so RL trajectory mining can score the raw extraction.
 * - ``constraints`` — the derived ``ConstraintSpec`` list the Day 3
 *   constraint-loop machinery consumes. Conversion happens at
 *   bridge emit time so the loop reads typed input directly from
 *   the trajectory.
 */
export interface ParameterExtractDeliveredPayload {
  action_type: "parameter_extract.delivered";
  parameters?: Parameter[];
  constraints?: ConstraintSpec[];
}

/**
 * Emitted by upstream callers to request a Connector dispatch.
 * The bridge runs traversal against ``seed_pairs`` with the
 * requested ``algorithm`` (default top_n_shortest_paths) and the
 * per-pair top-N cap.
 */
export interface ConnectorRequestedPayload {
  action_type: "connector.requested";
  keyword_mappings?: KeywordMapping[];
  seed_pairs?: SeedPair[];
  algorithm?: "shortest_simple_path" | "top_n_shortest_paths" | "depth_first_limited" | "bfs_semantic_stop";
  max_paths_per_pair?: number;
}

/**
 * Emitted by the Connector bridge once a parsed + validated
 * response lands. Carries:
 * 
 * - ``keyword_mappings`` — role's confirmation / correction of the
 *   pre-resolved mappings; ``low_confidence`` flags preserved.
 * - ``selected_algorithm`` — role's algorithm choice (echoes what
 *   the bridge actually ran; lets the role correct in retrospect).
 * - ``paths`` — structured paths from traversal, passed through
 *   verbatim (the role MUST NOT edit them).
 * - ``natural_language_relationships`` — one per path, with
 *   ``source_path_index`` cite-back.
 */
export interface ConnectorDeliveredPayload {
  action_type: "connector.delivered";
  keyword_mappings?: KeywordMapping[];
  selected_algorithm: "shortest_simple_path" | "top_n_shortest_paths" | "depth_first_limited" | "bfs_semantic_stop";
  algorithm_rationale?: string | null;
  paths?: GraphPath[];
  natural_language_relationships?: NaturalLanguageRelationship[];
}

/**
 * Emitted by the orchestrator after the four upstream roles
 * (decomposer, evidence_retriever, parameter_extractor, connector)
 * have all delivered. Carries the five pre-rendered prompt blocks
 * verbatim so the role's input is fully reconstructable from the
 * trajectory.
 * 
 * Definition order note: this payload sits AFTER ``ConstraintSpec``
 * so its ``constraints: list[ConstraintSpec]`` field resolves at
 * annotation-read time. Codegen reads ``__annotations__`` directly
 * and can't resolve forward-string references.
 */
export interface SynthesizeRequestedPayload {
  action_type: "synthesize.requested";
  question: string;
  decomposition_block: string;
  evidence_block: string;
  parameters_block: string;
  substrate_block: string;
  constraints?: ConstraintSpec[];
}

/**
 * Emitted by the synthesizer bridge once a parsed + validated
 * thesis lands AND the constraint loop has terminated. Carries the
 * canonical thesis shape. The ``constraint_loop_status`` field is
 * the loop's terminal verdict (single_pass / passed / regressed /
 * max_iterations_reached). Iteration count is the number of
 * synthesizer dispatches inside the loop (1 = no revision).
 */
export interface SynthesizeDeliveredPayload {
  action_type: "synthesize.delivered";
  thesis_summary: string;
  implicit_recommendation: "proceed" | "pass" | "conditional" | "undetermined" | "insufficient_evidence";
  thesis_components?: ThesisComponent[];
  falsification_conditions?: FalsificationCondition[];
  execution_risks?: ExecutionRisk[];
  constraint_compliance: ConstraintCompliance;
  reasoning_paths_used?: ReasoningPathUsed[];
  conviction_level?: number | null;
  constraint_loop_status?: "single_pass" | "passed" | "regressed" | "max_iterations_reached" | "escalated" | "preflight_failed";
  constraint_loop_iterations?: number;
}

/**
 * One audit finding. Optional ``target_phase`` + ``target_path``
 * pinpoint the artifact the finding concerns; ``evidence`` is the
 * diagnostic string the operator reads when triaging.
 */
export interface AuditFindingPayload {
  action_type: "audit.finding_emitted";
  category: string;
  severity: "info" | "warning" | "critical";
  description: string;
  evidence: string;
  target_phase?: number | null;
  target_path?: string | null;
}

/**
 * Cold-question entry point. The orchestrator subscribes to this
 * action_type and spawns a per-investigation coroutine that walks
 * phases 1-9. ``topic_slug`` (if supplied) is used for the MASTER.md
 * output path; ``context`` is optional domain framing the
 * Decomposer reads.
 * 
 * Sprint 11 adds ``parent_investigation_id`` + ``spawn_context`` for
 * the web app's highlight-to-chase mechanic. Both are metadata-only;
 * the orchestrator doesn't change behavior based on them, but the
 * web app uses them to render the chase tree and ChaseSlideOver pulls
 * ``spawn_context`` as the highlighted-text-from-parent.
 */
export interface InvestigationStartRequestedPayload {
  action_type: "investigation.start_requested";
  question: string;
  context?: string;
  topic_slug?: string | null;
  max_sub_questions?: number;
  parent_investigation_id?: string | null;
  spawn_context?: string | null;
  derived_source?: DerivedCitationSource | null;
  derived_sources?: DerivedCitationSource[];
  evidence_manifest?: EvidenceManifestProvenance | null;
  chase_mode?: "off" | "depth" | "duration";
  chase_value?: number;
  chase_budget_usd?: number;
  research_tier?: "fast" | "deep" | null;
}

/**
 * Terminal lifecycle event when Loop 1 converged cleanly. Carries
 * the synthesis verdict + the constraint-loop verdict so a single
 * event suffices to report outcome to a dashboard.
 */
export interface InvestigationCompletedPayload {
  action_type: "investigation.completed";
  thesis_summary: string;
  implicit_recommendation: "proceed" | "pass" | "conditional" | "undetermined" | "insufficient_evidence";
  constraint_loop_status: "single_pass" | "passed" | "regressed" | "max_iterations_reached" | "escalated" | "preflight_failed";
  constraint_loop_iterations?: number;
  master_md_path?: string | null;
  domains_patched?: string[];
  total_phases_verified?: number;
}

/**
 * Terminal lifecycle event when Loop 1 aborted before
 * completion. ``phase`` identifies which phase failed; ``reason``
 * is the diagnostic string (postcondition failure message, exception
 * repr, etc.).
 */
export interface InvestigationFailedPayload {
  action_type: "investigation.failed";
  phase: number;
  reason: string;
  last_completed_phase?: number | null;
}

/**
 * Emitted when a new investigation is spawned from a parent's
 * synthesis via the web app's chase-this mechanic. Carries the
 * parent_investigation_id, the parent_event_id (typically the
 * parent's synthesis.delivered event), and the highlighted text the
 * operator was chasing.
 * 
 * The substrate doesn't act on this event; it's UI metadata. The
 * web app's useInvestigationTree hook reads these events to render
 * the chase tree (migrating off localStorage once the substrate
 * consumer is wired).
 */
export interface InvestigationSpawnedFromPayload {
  action_type: "investigation.spawned_from";
  parent_investigation_id: string;
  parent_event_id?: string | null;
  spawn_context?: string;
}

/**
 * Emitted when the orchestrator decides not to spawn a child
 * investigation despite chase_mode != "off". The reason field tells
 * the operator (and the UI) why the chase chain stopped here.
 * 
 * Sprint 12 — first interpretation of continuous mode. The full
 * daemon model (cross-investigation pollination) lands in Sprint
 * 14+ per master-product-spec section 7.3.
 */
export interface InvestigationChaseHaltedPayload {
  action_type: "investigation.chase_halted";
  reason: "depth_reached" | "duration_reached" | "budget_exceeded" | "no_open_questions" | "chase_disabled";
  depth_reached?: number;
  duration_seconds?: number;
  cost_total_usd?: number;
}

/**
 * Sprint 15 — emitted when the operator's edit to creative_writer's
 * output is promoted to a first-class graph claim. Master spec §10.4
 * Option B.
 * 
 * The original generated prose and the operator's edit are both
 * preserved so the audit trail captures the delta. ``claim_text`` is
 * canonically the operator's text; ``original_text`` is the
 * creative_writer output it replaced. ``source_tier`` defaults to 5
 * (unsupported) unless the operator manually attaches chunk
 * citations — at which point the substrate's grounder can verify it
 * and downgrade the tier.
 * 
 * ``node_id`` is the graph node row the claim was promoted to. The
 * web app uses this to surface the claim under its origin
 * deliverable + section in future search.
 */
export interface ClaimAssertedByOperatorPayload {
  action_type: "claim.asserted_by_operator";
  deliverable_id: string;
  section_id: string;
  claim_text: string;
  original_text?: string | null;
  node_id?: string | null;
  source_tier?: number;
  operator_id?: string;
  cited_chunk_ids?: string[];
}

/**
 * Sprint 16 — emitted per synthesis-attribution computation.
 * 
 * ``algorithm_shares`` is the full three-algorithm map; each value
 * is itself a ``{document_id: share}`` dict where shares sum to 1.0
 * (subject to float rounding). ``algorithm`` key is one of "A",
 * "B", "C" matching master spec §9.3.
 * 
 * Phase 1 (this sprint): telemetry only. No payouts triggered by
 * this event. The phase-2 payout job reads these events to decide
 * splits — but that pipeline isn't wired yet.
 */
export interface PageAttributionComputedPayload {
  action_type: "page.attribution.computed";
  synthesis_id: string;
  algorithm_shares?: Record<string, Record<string, number>>;
  claim_count?: number;
  document_count?: number;
}

/**
 * Emitted by the RLM bridge on every document-load when the bridge
 * weighs in (above-threshold → escalate or defer; below-threshold →
 * skipped). Per master-spec §11.6 + rlm_integration_spec.md RLM-1.
 * 
 * Carries the verdict + the ratification state at decision time so
 * operators reading the trajectory can reconstruct WHY a long doc
 * did or did not enter RLM mode at a given moment.
 */
export interface RLMBridgeDecidedPayload {
  action_type: "rlm.bridge.decided";
  document_id_ref: string;
  estimated_tokens: number;
  threshold_tokens: number;
  above_threshold: boolean;
  ratified: boolean;
  escalated: boolean;
  session_id?: string | null;
  reason: "below_threshold" | "deferred_pending_ratification" | "escalated_to_rlm";
}

/**
 * Quality-gate verdict for §13.9 public-graph promotion of a
 * notebook block. Carries the per-rubric pass/fail and the headline
 * accept decision; downstream gates aggregate these into operator-
 * visible counts on the Trust Center.
 */
export interface QualityGateEvaluatedPayload {
  action_type: "quality_gate.evaluated";
  target_kind: "notebook" | "synthesis_page" | "creator_note";
  target_id: string;
  accepted: boolean;
  verification_passed: boolean;
  voice_style_passed: boolean;
  source_tier_passed: boolean;
  em_dash_density: number;
  padding_phrase_count: number;
  sector_vocab_overlap: number;
  min_tier_cited: number;
  pct_tier_1_or_2: number;
  reasons?: string[];
}

/**
 * A citation from one user's investigation to another user's
 * public note. Per master-spec §13.9 Phase 3 federation. The
 * attribution pipeline reads these to route 70% of any attached ad
 * revenue to the referenced user.
 */
export interface CrossGraphCitationRecordedPayload {
  action_type: "cross_graph.citation.recorded";
  reference_id: string;
  referencing_user_id: string;
  referencing_investigation_id: string;
  referenced_user_id: string;
  referenced_note_id: string;
  federated_substrate_id?: string | null;
}

/**
 * One revenue-routing decision arising from an ad impression.
 * Mirrors ``substrate.ad_inventory.payout.RevShareDecision`` and is
 * emitted once per decision (creator/publisher/platform). The
 * daily-cap state is carried in ``capped_to_daily_limit`` so the
 * operator can audit §9.7 enforcement from the event log alone.
 */
export interface RevShareDecidedPayload {
  action_type: "rev_share.decided";
  decision_id: string;
  impression_id: string;
  kind: "creator" | "publisher" | "platform";
  recipient_ref: string;
  amount_usd_cents: number;
  document_id_ref?: string | null;
  requires_escrow?: boolean;
  capped_to_daily_limit?: boolean;
}

/**
 * Emitted by the DP-aware preference learning stream every time
 * a binary observation is randomized + recorded against a category's
 * ε budget. Per master-spec §16.2: per-observation ε spend is
 * recorded; the underlying TRUE value is never logged (local DP
 * guarantee).
 */
export interface PreferenceObservationRecordedPayload {
  action_type: "preference.observation.recorded";
  category: string;
  noisy_value: boolean;
  per_obs_epsilon: number;
  cumulative_epsilon_spent: number;
  category_budget: number;
  user_id: string;
}

/**
 * Emitted by ``substrate/multi_user/skill_writer.py`` when a
 * discovered skill rule clears the ``SkillRuleAccumulator`` promotion
 * gate and lands in the shared substrate's ``skill_rules`` table.
 * 
 * Carries the rule's content-addressed identifier, the cumulative DP
 * ε spent across all contributing users (capped at §16.2's 10.0),
 * the distinct-user count that triggered promotion, and the
 * confidence tier the writer assigned. Contributing user IDs ride as
 * a tuple so the attribution + audit paths can reconstruct
 * provenance.
 */
export interface SkillRulePromotedPayload {
  action_type: "skill_rule.promoted";
  rule_id: string;
  rule_text: string;
  rule_kind: string;
  domain: string;
  distinct_user_count: number;
  total_epsilon_consumed: number;
  confidence: "low" | "moderate" | "high";
  contributing_user_ids?: string[];
}

/**
 * A discovery-layer source (Wedge 1: Exa search) proposed a URL.
 * 
 * The URL has NOT been ingested; this event is the audit trail of
 * "what we considered." Promotion to ingestion is a separate event
 * (DiscoverySelectedPayload). Per spec §6.8: discovery does NOT
 * fetch, does NOT auto-ingest, does NOT bypass the legal gate.
 * 
 * ``discovery_id`` is the stable handle for a proposal. The wedge
 * mints it as ``"disc-{provider}-" + sha256(url+investigation_id)[:16]``.
 */
export interface DiscoveryProposedPayload {
  action_type: "discovery.proposed";
  discovery_id: string;
  provider: "exa" | "parallel" | "operator";
  query: string;
  url: string;
  title?: string | null;
  published_date?: string | null;
  author?: string | null;
  relevance_score?: number | null;
  suggested_tier: number;
  text_snippet_preview?: string | null;
  provider_response_id?: string | null;
  cost_usd_estimate?: number | null;
  provider_specific?: Record<string, unknown>;
}

/**
 * A previously-proposed discovery was promoted to ingestion (or
 * explicitly refused). Ties the discovery_id to the resulting
 * document_id when ingestion succeeded.
 * 
 * ``document_id`` is None when the decision is anything other than
 * ``"ingested"``. The legal-gate rejection path emits a Selected
 * event with ``decision="rejected_by_legal_gate"`` and a None
 * document_id so the audit trail records the refusal — the Sprint
 * 18 retrieval-time gate (master-spec §9) is enforced upstream of
 * this event, not by this event.
 * 
 * Per spec §6.9: this event only fires once per (discovery_id,
 * decision) pair. Re-promoting an already-ingested discovery is
 * idempotent at the URL adapter level (url_doc_id deduplicates);
 * the second Selected event is suppressed by the caller, not by
 * the payload schema.
 */
export interface DiscoverySelectedPayload {
  action_type: "discovery.selected";
  discovery_id: string;
  document_id?: string | null;
  decision: "ingested" | "rejected_by_legal_gate" | "rejected_by_operator" | "fetch_failed";
  rejection_reason?: string | null;
}

/**
 * Wedge 2 escalation event. Emitted by acquisition/urls/adapter.py
 * when the httpx primary fetch returned ``low_word_count`` and the
 * caller opted into a heavier fetcher (currently Browserbase).
 * 
 * Per spec §7.2: the URL adapter still owns DocumentLoadedPayload
 * emission; this event sits alongside, recording the escalation
 * itself. Per spec §7.4: this is escalation, NOT default — the
 * 1000-5000× cost ratio against httpx is the load-bearing reason
 * Browserbase is never the primary fetcher.
 * 
 * ``primary_word_count`` and ``fallback_word_count`` let the
 * trajectory show whether the escalation recovered usable content
 * (fallback > primary) or hit a paywall/captcha (fallback ≈ primary).
 */
export interface FetchFallbackEscalatedPayload {
  action_type: "fetch.fallback.escalated";
  url: string;
  primary_fetcher?: "httpx";
  primary_word_count: number;
  fallback_fetcher: "browserbase";
  fallback_word_count: number;
  escalation_reason: "low_word_count" | "operator_override" | "JS-detect";
  estimated_cost_usd: number;
}

/**
 * The verifier tier (or any caller) consulted Exa for external
 * claim corroboration. Spec §8. The snippets stay out of the
 * graph (spec §8.3).
 */
export interface VerifierLookupPayload {
  action_type: "verifier.lookup";
  tool?: "exa.search_contents";
  query: string;
  claim_text?: string | null;
  k_requested: number;
  results?: ExaLookupResult[];
  cost_usd_estimate: number;
}

/**
 * Emitted when an operator registers a partner substrate. State
 * lands at PENDING_HANDSHAKE; promotion to TRUSTED emits a separate
 * event. NEVER carries the shared_secret_hex — that field is excluded
 * from the audit surface by construction. The audit trail records
 * WHO can federate, not the secrets used.
 */
export interface FederationPartnerRegisteredPayload {
  action_type: "federation.partner.registered";
  partner_id: string;
  display_name: string;
  substrate_url: string;
  registered_at: string;
}

/**
 * Emitted when the operator promotes PENDING_HANDSHAKE → TRUSTED.
 * The transition is operator-driven; the event records the moment
 * cross-instance federation becomes possible for this partner.
 */
export interface FederationPartnerTrustedPayload {
  action_type: "federation.partner.trusted";
  partner_id: string;
  last_state_change_at: string;
  operator_notes?: string;
}

/**
 * Emitted when the operator revokes a partner. REVOKED is
 * terminal; subsequent federation operations refuse at the substrate
 * gate. The revocation_reason rides for operator triage.
 */
export interface FederationPartnerRevokedPayload {
  action_type: "federation.partner.revoked";
  partner_id: string;
  last_state_change_at: string;
  revocation_reason: string;
}

/**
 * Emitted when this substrate hands a citation to a partner
 * instance via ``federate_outbound_citation``. The audit shape
 * NEVER includes the signed_token (replay-attack surface) — the
 * reference_id and partner_id are sufficient for joining against
 * later inbound-accept events on the partner side.
 */
export interface FederationOutboundCitationEmittedPayload {
  action_type: "federation.outbound_citation.emitted";
  reference_id: string;
  partner_id: string;
  partner_substrate_url: string;
  referencing_user_id: string;
  referencing_investigation_id: string;
  referenced_user_id: string;
  referenced_note_id: string;
  revenue_routing_handle: string;
}

/**
 * Emitted when this substrate accepts an inbound citation from
 * a partner instance. The ``receiver_reference_id`` is this side's
 * locally-minted reference (distinct from the sender's).
 */
export interface FederationInboundCitationAcceptedPayload {
  action_type: "federation.inbound_citation.accepted";
  receiver_reference_id: string;
  partner_id: string;
  referencing_user_id: string;
  referencing_investigation_id: string;
  referenced_user_id: string;
  referenced_note_id: string;
  revenue_routing_handle: string;
  received_at: string;
}

/**
 * Emitted when this substrate refuses an inbound citation. The
 * typed ``rejection`` reason is one of the ``InboundRejection`` enum
 * values. ``detail`` is a short operator-readable string and MUST
 * NOT include the raw token or shared secret per the inbound
 * handler's no-leak contract.
 */
export interface FederationInboundCitationRefusedPayload {
  action_type: "federation.inbound_citation.refused";
  partner_id: string;
  rejection: "partner_not_allowed" | "partner_not_registered" | "partner_not_trusted" | "token_invalid" | "payload_malformed" | "replay_detected";
  detail?: string;
  received_at: string;
}

/**
 * Emitted when the substrate picks a frame for visual analysis.
 * ``frame_source`` is "still" for image documents, "video" for an
 * extracted video frame. ``frame_timestamp_ms`` is set only for
 * video sources; None for stills. The audit trail records WHAT the
 * role was asked to look at — the actual image bytes never appear
 * in payloads (they live in the document store).
 */
export interface VisualFrameIdentifiedPayload {
  action_type: "visual.frame_identified";
  document_id: string;
  frame_source: "still" | "video";
  page_or_frame_id: string;
  frame_timestamp_ms?: number | null;
  frame_width_px?: number | null;
  frame_height_px?: number | null;
}

/**
 * Emitted when the visual role returns a parsed ``VisualResult``.
 * The full claim text rides for downstream attribution; the bbox
 * is normalized [0, 1] coords. ``frame_summary`` is the role's one-
 * sentence summary.
 */
export interface VisualClaimsExtractedPayload {
  action_type: "visual.claims_extracted";
  document_id: string;
  page_or_frame_id: string;
  frame_summary: string;
  claim_count: number;
  high_confidence_count: number;
  uncited_observation_count: number;
}

/**
 * Emitted when the dispatch call to the visual role fails OR the
 * parser refuses the role's output. ``failure_kind`` discriminates;
 * ``detail`` is a short operator-readable string. NEVER includes
 * the raw model output (could leak unstructured prose) — the
 * parser's error class names land here instead.
 */
export interface VisualRoleFailedPayload {
  action_type: "visual.role_failed";
  document_id: string;
  page_or_frame_id: string;
  failure_kind: "dispatch_error" | "parse_validation" | "provider_unavailable";
  detail?: string;
}

/**
 * Emitted by the AI sidecar (Max-style ubiquitous AI per §5.5)
 * whenever the AI applies a UI-mutating action on behalf of the
 * operator. Carries enough state to invert the action:
 * 
 * - ``target_kind`` + ``target_id`` say what was changed.
 * - ``prev_state`` + ``next_state`` are opaque JSON snapshots the
 *   undo handler diffs to produce the inverse.
 * - ``operator_prompt`` is the natural-language ask that triggered
 *   the action — so the operator can read what they asked for.
 * 
 * The undo path replays the inverse: if ``ai.action.applied`` set
 * a notebook block from X to Y, the undo POST sets it back from Y
 * to X and emits ``ai.action.undone`` linking back via
 * ``inverted_event_id``.
 */
export interface AIActionAppliedPayload {
  action_type: "ai.action.applied";
  target_kind: "notebook_block" | "notebook" | "master_md_section" | "claim" | "watch_for_later_question" | "investigation_chase" | "ui_layout";
  target_id: string;
  operator_prompt: string;
  prev_state?: Record<string, unknown>;
  next_state?: Record<string, unknown>;
  prev_state_hash: string;
  summary?: string;
}

/**
 * Emitted when the operator clicks "undo" on the AI sidecar.
 * 
 * Links to the ``ai.action.applied`` event being inverted via
 * ``inverted_event_id``. The undo handler is responsible for
 * actually re-applying ``prev_state`` to the substrate; this event
 * just records that the operator chose to revert.
 */
export interface AIActionUndonePayload {
  action_type: "ai.action.undone";
  inverted_event_id: string;
  target_kind: "notebook_block" | "notebook" | "master_md_section" | "claim" | "watch_for_later_question" | "investigation_chase" | "ui_layout";
  target_id: string;
  reason?: "operator_undo" | "automated_rollback";
}

/**
 * Emitted by the DP shuffler whenever a telemetry signal passes
 * through randomized response (§13.3 + §16.2).
 * 
 * Records the surface, the configured ε, and whether the value was
 * flipped — *without* recording the original or flipped value
 * (that would defeat the point). The aggregator downstream consumes
 * only the noisy stream + the registered ε to debias.
 * 
 * The Trust Center reads the running sum of recorded ε per surface
 * per day to publish "X surfaces collect at total ε=Y today" per
 * §13.7.
 */
export interface DPRoutedPayload {
  action_type: "dp.routed";
  surface_name: string;
  epsilon: number;
  sensitivity: "low" | "medium" | "high" | "forbidden";
  was_flipped: boolean;
  stage?: "local_randomized" | "aggregated";
}

/**
 * A lego block placed into an outline section (substrate/write/).
 * 
 * provenance_kind discriminates how the block traces to a source of
 * truth — the invariant SPR-07 trace-to-source relies on:
 * 
 * - 'graph_node'    → ``node_id`` references an insight/question/claim
 *                     graph node; provenance resolves node → document
 *                     → chunks. ``content`` is null (the node is the
 *                     content of record).
 * - 'user_authored' → the operator wrote it directly. ``node_id`` is
 *                     null; ``content`` carries the text. No false
 *                     citation is ever attached.
 * - 'synthesized'   → produced by generation/synthesis from other
 *                     blocks. ``node_id`` null.
 * - 'brainstorm'    → emerged from a brainstorm session (SPR-05);
 *                     user-originated, ``node_id`` null, traces to the
 *                     session not an external document.
 */
export interface OutlineBlockPlacedPayload {
  action_type: "outline_block.placed";
  outline_block_id: string;
  deliverable_id: string;
  section_id: string;
  block_kind: "insight" | "open_question" | "operator_note" | "claim" | "user_authored" | "synthesized";
  provenance_kind: "graph_node" | "user_authored" | "synthesized" | "brainstorm";
  node_id?: string | null;
  block_index: number;
}

/**
 * A block reordered within a section or moved to a new section
 * (reparent). Records both endpoints so the authoring trajectory can
 * replay the composition edit deterministically.
 */
export interface OutlineBlockMovedPayload {
  action_type: "outline_block.moved";
  outline_block_id: string;
  from_section_id: string;
  to_section_id: string;
  from_index: number;
  to_index: number;
}

/**
 * A block removed from an outline. The underlying graph node is
 * untouched — removal is a composition edit, not a graph deletion.
 * Outlines and folders are views over nodes (the moat), so removing a
 * block never destroys provenance for any other reference.
 */
export interface OutlineBlockRemovedPayload {
  action_type: "outline_block.removed";
  outline_block_id: string;
  section_id: string;
}

/**
 * One structured before/after edit in the writing surface.
 * 
 * This is the granular replacement for the coarse
 * ``updateSectionProse`` capture (whole-section ``original_text`` vs
 * ``prose_text``). The editor (SPR-04) emits one of these per edit at
 * block / paragraph / sentence granularity, anchored to a stable
 * locator (``section_id`` + optional ``outline_block_id`` /
 * ``paragraph_index`` / ``sentence_index``) so the authoring trajectory
 * (SPR-02) and section/paragraph style prompts (SPR-06) both address
 * the same units.
 * 
 * ``reverted`` is the undo/redo coordination point: a reverted edit is
 * still captured (the chain of edits is the signal — like Cursor's
 * accept/edit loop) but is explicitly EXCLUDED from training signal so a
 * revert is never counted as an endorsement.
 * 
 * CAPTURE ≠ TRAINING. These events are written ungated. The reward is
 * computed post-unlock by ``rubric_verifier`` (itself gated); nothing
 * here computes a reward or invokes training.
 */
export interface EditCapturedPayload {
  action_type: "edit.captured";
  deliverable_id: string;
  section_id: string;
  outline_block_id?: string | null;
  granularity: "block" | "paragraph" | "sentence";
  edit_kind: "insert" | "delete" | "replace" | "reorder";
  paragraph_index?: number | null;
  sentence_index?: number | null;
  before_text?: string | null;
  after_text?: string | null;
  reverted?: boolean;
  session_id?: string | null;
}

/**
 * A section's draft was generated by ``creative_writer`` and its
 * per-paragraph provenance persisted (Write SPR-09).
 * 
 * The X-ray view (paragraph → driving blocks → chunks → documents)
 * depends on ``prose_provenance`` surviving the generating request.
 * ``creative_writer`` returns ``prose_provenance`` (paragraph_index →
 * [block_ids]) ephemerally; this event — emitted only after a live
 * generation succeeds AND the voice gate passes — makes the
 * paragraph→blocks link DURABLE in the graph alongside the
 * ``deliverable_sections.prose_text`` / ``prose_provenance`` row write.
 * 
 * The link is the §9 moat made auditable: a maintainer can reconstruct,
 * for any generated paragraph, which blocks drove it (and from there the
 * chunks/documents via ``substrate.write.provenance.resolve_provenance``).
 * This is a composition/audit event — the underlying blocks/nodes are
 * untouched (outlines are views over nodes, per the moat).
 * 
 * ``prose_provenance`` keys are STRINGS here (paragraph indices) because
 * JSON object keys are strings; the reader parses them back to ints. The
 * map values are the block_ids creative_writer cited per paragraph (the
 * node_id for a graph-node block, the outline_block_id for a
 * user-originated one — the same id the inline citation names).
 */
export interface SectionDraftGeneratedPayload {
  action_type: "section.draft_generated";
  section_id: string;
  deliverable_id: string;
  prose_provenance: Record<string, string[]>;
  paragraph_count: number;
  cited_block_ids: string[];
  all_claims_cited: boolean;
  unsupported_paragraph_count?: number;
  gate_score?: number | null;
}

/**
 * A book's full-text serving eligibility changed. Emitted by
 * ``substrate/books/`` whenever a content_class transition moves a book
 * across the servable / metadata-only line (e.g. a publisher claims an
 * account and a gated book flips to publisher_opted_in). The
 * from/to statuses are the DERIVED ServabilityStatus values (not the
 * raw content_class) so the audit reads in the gate's own vocabulary.
 * 
 * The ``document_id`` of the affected book rides the Event envelope
 * (``emit_typed(..., document_id=...)``), so it isn't duplicated here.
 */
export interface BookServabilityChangedPayload {
  action_type: "book.servability_changed";
  from_status: string;
  to_status: string;
  reason: string;
}

/**
 * A removal demand was honoured for a book (Read SPR-01 M4). Records
 * that the full text was purged from the materialized document body and
 * retrieval was restricted (content_class moved to the existing
 * restricted_pending_opt_in gate). ``purged_full_text`` is True when a
 * non-empty raw_text was nulled — distinguishing "took down a book we
 * were serving" from "took down a metadata-only stub". Pre-serve /
 * pre-payout takedown is the cheap defence (Bartz).
 */
export interface BookTakenDownPayload {
  action_type: "book.taken_down";
  reason: string;
  previous_content_class?: string | null;
  purged_full_text?: boolean;
}

/**
 * A third-party ingest landed personal_reading by deny-by-default (Personal-
 * Reading Lane SPR-01 M5). Emitted by ``substrate/graph/ops.py insert_document``
 * when a third-party ``document_type`` (web_article / video_transcript /
 * social_thread / newsletter_post) was inserted with ``content_class=None``: the
 * guard writes ``content_class='personal_reading'`` instead of NULL — closing
 * the §9.0 leak where a NULL content_class passed the public chunk-search gate
 * and reached the monetized read path.
 * 
 * Carries the ingest classification trail — ``document_type`` (which set
 * triggered the default) and the ``applied_content_class`` (always
 * 'personal_reading' today; recorded explicitly so a future positive-basis
 * default reads truthfully) — so the deny-by-default decision is
 * reconstructable by a lawyer, not just a maintainer. The ``document_id`` of the
 * classified row rides the Event envelope (``emit_typed(..., document_id=...)``).
 * NEVER carries ``raw_text`` (§9.0: events carry no body).
 */
export interface DocumentContentClassDefaultedPayload {
  action_type: "document.content_class_defaulted";
  document_type: string;
  applied_content_class: string;
}

/**
 * research → read. A researched insight surfaces in the reading corpus
 * (DRW SPR-01 node + Read corpus surface).
 */
export interface SeamResearchToReadPayload {
  entity_id: string;
  entity_kind?: "insight_node";
  provenance_ref: string;
  terminates?: true;
  action_type: "seam.research_to_read";
  from_workflow?: "research";
  to_workflow?: "read";
}

/**
 * read → research. A highlighted passage spins a focused investigation
 * (Read SPR-08 → DRW SPR-05 cascade planner seed).
 */
export interface SeamReadToResearchPayload {
  entity_id: string;
  entity_kind?: "document_region";
  provenance_ref: string;
  terminates?: true;
  action_type: "seam.read_to_research";
  from_workflow?: "read";
  to_workflow?: "research";
  document_id: string;
  launched_investigation_id?: string | null;
}

/**
 * read → write. An insight node is dragged into an outline section
 * (Write SPR-03). The block references the node (provenance_kind=graph_node);
 * it never inlines the insight text.
 */
export interface SeamReadToWritePayload {
  entity_id: string;
  entity_kind?: "insight_node";
  provenance_ref: string;
  terminates?: true;
  action_type: "seam.read_to_write";
  from_workflow?: "read";
  to_workflow?: "write";
  target_section_id: string;
}

/**
 * write → read. Trace a block to its source in the shared reading surface
 * (Write SPR-07), respecting Read's servability gate.
 */
export interface SeamWriteToReadPayload {
  entity_id: string;
  entity_kind?: "outline_block";
  provenance_ref: string;
  terminates?: true;
  action_type: "seam.write_to_read";
  from_workflow?: "write";
  to_workflow?: "read";
  source_document_id?: string | null;
  source_region_id?: string | null;
}

/**
 * speak → write. Author a biography from interview-attested claims
 * (Speak SPR-08). The seam carries the speak_claim id; Write maps it to a
 * synthesized block (claim_id as provenance link, not a new node).
 */
export interface SeamSpeakToWritePayload {
  entity_id: string;
  entity_kind?: "speak_claim";
  provenance_ref: string;
  terminates?: true;
  action_type: "seam.speak_to_write";
  from_workflow?: "speak";
  to_workflow?: "write";
  contributor_interview_ids?: string[];
}

/**
 * speak → read. A published biography is served back in the corpus
 * (Speak SPR-09). Registers as platform_authored + speak_derived — the
 * condition that routes it through the seam-#4 publish gate.
 */
export interface SeamSpeakToReadPayload {
  entity_id: string;
  entity_kind?: "servable_entry";
  provenance_ref: string;
  terminates?: true;
  action_type: "seam.speak_to_read";
  from_workflow?: "speak";
  to_workflow?: "read";
  publish_gate_passed?: boolean;
}

/**
 * write → speak. **PROVISIONAL.** Commission interviews from an outline
 * gap. Typed so the trajectory can carry it, but the seam is the weakest and
 * off the SPR-08 critical path; the receiving Speak side is unspecified.
 */
export interface SeamWriteToSpeakPayload {
  entity_id: string;
  entity_kind?: "question_node";
  provenance_ref: string;
  terminates?: true;
  action_type: "seam.write_to_speak";
  from_workflow?: "write";
  to_workflow?: "speak";
  outline_section_id?: string | null;
}

/**
 * A spoken capture, transcribed and persisted through the single-writer
 * funnel (Living Roadmap SPR-14 M1/M3). Emitted by the shared
 * ``useVoiceCapture`` hook after record → transcribe; downstream
 * distillation (``substrate/books/voice_note`` → ``note.emerged``) is
 * unchanged and consumes this capture by event id.
 * 
 * ``source_kind`` is fixed to ``"user"`` here and is the §9 load-bearing
 * field: a voice capture is human-authored, never model output. The schema
 * pins it to the literal ``"user"`` (not the open :data:`ProvenanceSourceKind`) so a
 * voice capture can NEVER be persisted as ``"ai"``/``"system"`` — the
 * no-conflation invariant is enforced by the type, not by convention.
 * 
 * The audio blob rides by *reference* (``audio_ref`` — the same field
 * ``saveVoiceNote`` carries), never inline and never a client side-store:
 * the blob persists wherever the reference points, the event carries only
 * the pointer + the transcript.
 * 
 * ``transcript`` may be empty: a silent recording must NOT be given a
 * hallucinated transcript (SPR-14 rigor #3). ``transcript_status``
 * distinguishes a genuine empty/silent capture ("empty") from an ordinary
 * one ("ok"), so a downstream consumer never mistakes "" for "transcription
 * failed". A failed transcription — or an over-cap long clip — is surfaced to
 * the user and NEVER persisted; there is no such event (so no truncated/
 * "bounded" status is ever emitted, hence it is not in the Literal).
 */
export interface VoiceCapturedPayload {
  action_type: "voice.captured";
  source_kind?: "user";
  transcript: string;
  transcript_status?: "ok" | "empty";
  language?: string | null;
  duration_seconds?: number;
  audio_ref?: string | null;
}

/**
 * A user-authored note created from a text selection via the shared
 * highlight → float-menu (Living Roadmap SPR-04 M2). The reader selects text
 * on any surface and chooses "Note"; the selection becomes a marginalia note
 * persisted through the single-writer funnel — never a client side-store.
 * 
 * ``source_kind`` is fixed to ``"user"`` and is the §9 load-bearing field,
 * identically to :class:`VoiceCapturedPayload`: a marginalia note is
 * human-authored, so it can NEVER be persisted as ``"ai"``/``"system"`` and
 * can never be conflated with a model reply in the one graph. (The
 * float-menu's OTHER actions — Dialogue / Search / Deep-research — produce
 * model/retrieval-sourced RESULTS, which are labelled by their own paths;
 * only this note is user-sourced.) The no-conflation invariant is enforced by
 * the type, not by convention.
 * 
 * Provenance (master-spec §9): the note chains claim→chunk→document like every
 * other claim. ``chunk_id`` is the chunk the selection lands in (when the host
 * can resolve it — a synthesis selection over a cited claim resolves a chunk;
 * a free-prose selection may not, so it is optional); the document id rides
 * the Event envelope (``document_id``). ``excerpt`` is the reader's OWN
 * selected text — what they highlighted — not retrieved body, so it carries no
 * §9.0-withheld-content risk (a reader reading their own selection). The §9.0
 * no-leak guard governs the float-menu's outbound SEARCH / DEEP-RESEARCH
 * payloads, not this note of one's own reading.
 */
export interface MarginaliaNotedPayload {
  action_type: "marginalia.noted";
  note_id: string;
  note_text: string;
  excerpt: string;
  source_kind?: "user";
  chunk_id?: string | null;
  derived_revision_id?: string | null;
  derived_content_sha256?: string | null;
  derived_generation?: number | null;
}

/**
 * Where an insight/open-question block sits on the DRW canvas (Living
 * Roadmap SPR-03 M2/M4). Emitted on drag-end by the Canvas component.
 * 
 * The canvas is a FREE 2D coordinate space — NOT the reading-physics
 * in-document layout-map (that anchors widgets to text; this places nodes
 * on a whiteboard). ``x``/``y`` are canvas-local pixels; the canvas
 * re-derives layout by replaying these events (latest event per
 * ``node_id`` wins), so the persisted event is the SINGLE source of truth
 * for position. A node with no event falls back to deterministic
 * auto-layout client-side; we never persist the auto-layout coordinates
 * (only an operator drag emits an event).
 * 
 * Why an event and not a client side-store? A canvas position is graph
 * *view-state* the operator wants to survive reload. The only sanctioned
 * DuckDB writer is the host funnel through ``runtime/db_lock``; a
 * localStorage side-store would be a second source of truth that can
 * diverge from the substrate. So position rides the SAME typed-event funnel
 * as every other state mutation — the §-single-writer reason, identical to
 * why VoiceCapturedPayload carries its audio by reference rather than a
 * side-store.
 * 
 * A canvas position is NOT a §9 provenance claim — it asserts nothing about
 * the world, only about pixels — so it carries no source/grounding fields;
 * the block's provenance still lives on its graph node (source_document_id).
 * 
 * ``region_id`` (+ optional human ``region_label``) carries M4 theme
 * grouping through the SAME event: a block dropped into a named region
 * records its region here rather than as a second event type or a side
 * store. ``None`` means "ungrouped".
 */
export interface BlockPositionPayload {
  action_type: "block.positioned";
  node_id: string;
  x: number;
  y: number;
  region_id?: string | null;
  region_label?: string | null;
}

/**
 * A reader dwelled on a source long enough to count as "read" (Living
 * Roadmap SPR-07 M4). It lights SiteSee's "read" citation tint, closing the
 * SPR-06 gap (``docs/decisions/spr-06-source-read-event-gap.md``): ``cited``
 * and ``saved`` were already substrate-derived; a per-source ``read`` signal
 * was not, so the tint shipped dormant.
 * 
 * WHY AN EVENT, NOT A CLIENT SIDE-STORE (PR-2 / PR-6, identical reasoning to
 * :class:`BlockPositionPayload`): a reader's read-history is substrate
 * view-state SiteSee resolves back from the log — the only sanctioned DuckDB
 * writer is the host funnel through ``runtime/db_lock``; a localStorage
 * side-store would be a second source of truth that can diverge. So it rides
 * the SAME single-writer typed-event funnel as every other state mutation.
 * 
 * EMITTED ONCE PER SOURCE PER READING SESSION (coalesced — the surface tracks
 * a per-session emitted-set, never a per-page emit), on a JUSTIFIED dwell
 * threshold (see the decision doc). It is a v1, reversible tint signal.
 * 
 * §9.0 — NO BODY. This event carries NO excerpt and no source text: only the
 * ``document_id`` (on the Event envelope), the ``chunk_id`` the read was
 * attributed to (the representative chunk SiteSee tints), and the dwell
 * EVIDENCE (``dwell_ms`` + ``page_count``) that justified the verdict — so a
 * maintainer can see WHY this counted as read. A withheld source's body never
 * rides this event because no body field exists (structurally impossible),
 * and the read of a withheld source is the reader's own dwell, not its
 * content.
 * 
 * NOT A §9 PROVENANCE CLAIM. It asserts the reader's OWN reading history
 * (like a "saved" signal), not a claim about the world, so it carries no
 * ``source_kind``/grounding fields (unlike VoiceCaptured / MarginaliaNoted,
 * which ARE user-authorship claims).
 */
export interface SourceReadPayload {
  action_type: "source.read";
  chunk_id?: string | null;
  dwell_ms?: number;
  page_count?: number;
}

/**
 * One durable talk-to-book output, including the real dispatch receipt.
 */
export interface ReadBookAnsweredPayload {
  action_type: "read.book_answered";
  owner_id: string;
  question: string;
  answer: string;
  citations?: BookAnswerCitation[];
  grounded: boolean;
  context_chunk_count: number;
  research_tier: "fast" | "deep";
  provider?: string | null;
  model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cached_input_tokens?: number | null;
  cache_creation_input_tokens?: number | null;
  cost_usd?: number | null;
  latency_ms?: number | null;
  dispatch_event_id?: string | null;
}

/**
 * The operator's append-only verdict on one captured book answer.
 */
export interface ReadBookAnswerJudgedPayload {
  action_type: "read.book_answer_judged";
  answer_id: string;
  owner_id: string;
  verdict: "good" | "bad";
  note?: string | null;
}

/**
 * A one-shot, READ-ONLY, page-cited synthesis over the reader's OWNED
 * corpus, saved as a re-openable Read asset (Read SPR-08 M4).
 * 
 * It is substrate truth (re-open / narrate / promote-on-explicit-action), so
 * it rides the single-writer funnel — not a client side-store (which would
 * diverge from the graph). The running talk-to-book chat is the opposite case
 * (ephemeral session view-state, sessionStorage).
 * 
 * §9.0 — the ``report`` is MODEL-generated synthesis grounded on owned
 * SERVABLE chunks; a withheld body never enters it because retrieval went
 * through the search gate (restricted content excluded). The ``citations``
 * carry references, never bodies. ``corpus_document_ids`` is the defensible
 * record of EXACTLY which owned docs were in scope — the proof this never
 * reached the open internet (internet-agnostic; if it had, it would be
 * Research, not Read).
 * 
 * PROPOSED boundary (operator decision 2, sign-off pending): built behind the
 * "proposed (sign-off pending)" banner, reversible to a ``soft`` corpus scope.
 * Promotion into Research is the EXISTING ``seam.read_to_research`` event on
 * explicit user action only — never auto, never a new silo.
 */
export interface ReadMetaReadingGeneratedPayload {
  action_type: "read.meta_reading.generated";
  asset_id: string;
  prompt: string;
  report: string;
  length_unit: "pages" | "minutes";
  length_amount: number;
  truncated?: boolean;
  corpus_scope?: "hard" | "soft";
  corpus_document_ids?: string[];
  citations?: MetaReadingCitation[];
}

/**
 * The reader EXPLICITLY accepted a suggestion to file a personal-space
 * document into a research project (Read SPR-13 M3).
 * 
 * THE INVARIANT (operator decision 1 + out-of-scope list): filing is NEVER
 * automatic. The personal space CONTINUOUSLY SUGGESTS a match
 * (``match_document_to_investigations`` ranks projects by the doc's similarity
 * to each project's question); the file only happens on an EXPLICIT user
 * accept that emits this event. Decline leaves the doc put (no event).
 * 
 * FILING IS A LINK, NOT A COPY. The ``/events/typed`` side-effect handler sets
 * ``documents.investigation_id`` THROUGH THE SINGLE-WRITER FUNNEL (the host
 * ``connect_write`` lock = ``runtime/db_lock``) — a direct ``UPDATE documents``
 * is FORBIDDEN (it would bypass the only-writer invariant). The §9 provenance
 * chain (claim→chunk→document→ip_holder_id) is untouched; ``ip_holder_id`` is
 * immutable on filing. 1:N — a document belongs to 0..1 investigation
 * (``documents.investigation_id``).
 * 
 * The match ``score`` + the project ``question`` are recorded so the filing
 * decision is RECONSTRUCTABLE (a maintainer can see why this doc landed in this
 * project) — never re-derived guesswork.
 */
export interface DocumentFiledIntoInvestigationPayload {
  action_type: "document.filed_into_investigation";
  filed_document_id: string;
  target_investigation_id: string;
  match_score?: number;
  target_question?: string;
}

/**
 * Discriminated union over every typed payload. TS narrowing on
 * ``payload.action_type`` selects the right variant.
 */
export type TypedPayload =
  | DispatchCallPayload
  | WorkerIdentityPayload
  | ContextPackAssembledPayload
  | KnowledgeReusedPayload
  | ReuseGatedPayload
  | DocumentLoadedPayload
  | DocumentRegionSelectedPayload
  | DistillationRequestedPayload
  | DistillationDeliveredPayload
  | ClaimChallengeRaisedPayload
  | ClaimGroundingCheckPassedPayload
  | ClaimGroundingCheckFailedPayload
  | NoteEmergedPayload
  | NoteRefinedPayload
  | NoteCompressedDocWrittenPayload
  | QuestionIdentifiedPayload
  | QuestionEscalatedToResearchPayload
  | QuestionResolvedByDocPayload
  | CrossDocQuestionAnsweredPayload
  | UserAcceptDistillationPayload
  | UserRejectDistillationPayload
  | UserEditDistillationPayload
  | ArtifactGeneratedPayload
  | ArtifactInteractedPayload
  | TierAssignedPayload
  | TierOverriddenPayload
  | TierRewriteBulkPayload
  | StalenessFlaggedPayload
  | StalenessResolvePayload
  | SynthesisArchivedPayload
  | SubstrateManifestWrittenPayload
  | SupersessionApplyPayload
  | SupersessionDismissPayload
  | SupersessionCoexistPayload
  | GraphNodeInsertedPayload
  | GraphEdgeInsertedPayload
  | ConstraintViolationFoundPayload
  | ConstraintRevisionTriggeredPayload
  | ConstraintLoopResolvedPayload
  | OutcomeRecordedPayload
  | RubricScoredPayload
  | GroundednessScoredPayload
  | GroundednessFailedPayload
  | PhaseEnterPayload
  | PhaseExitPayload
  | PhaseVerifyPayload
  | DecomposeQuestionRequestedPayload
  | DecomposeQuestionDeliveredPayload
  | DecomposerParaphraseFlaggedPayload
  | DecomposerRegeneratedPayload
  | MasterMdWrittenPayload
  | MasterMdSkippedPayload
  | SkillPatchGateDecidedPayload
  | SkillPatchGateReviewedPayload
  | AutoPatchAppliedPayload
  | AutoPatchSkippedPayload
  | EvidenceRetrieveRequestedPayload
  | EvidenceRetrieveDeliveredPayload
  | ParameterExtractRequestedPayload
  | ParameterExtractDeliveredPayload
  | ConnectorRequestedPayload
  | ConnectorDeliveredPayload
  | SynthesizeRequestedPayload
  | SynthesizeDeliveredPayload
  | AuditFindingPayload
  | InvestigationStartRequestedPayload
  | InvestigationCompletedPayload
  | InvestigationFailedPayload
  | InvestigationSpawnedFromPayload
  | InvestigationChaseHaltedPayload
  | ClaimAssertedByOperatorPayload
  | PageAttributionComputedPayload
  | RLMBridgeDecidedPayload
  | QualityGateEvaluatedPayload
  | CrossGraphCitationRecordedPayload
  | RevShareDecidedPayload
  | PreferenceObservationRecordedPayload
  | SkillRulePromotedPayload
  | DiscoveryProposedPayload
  | DiscoverySelectedPayload
  | FetchFallbackEscalatedPayload
  | VerifierLookupPayload
  | FederationPartnerRegisteredPayload
  | FederationPartnerTrustedPayload
  | FederationPartnerRevokedPayload
  | FederationOutboundCitationEmittedPayload
  | FederationInboundCitationAcceptedPayload
  | FederationInboundCitationRefusedPayload
  | VisualFrameIdentifiedPayload
  | VisualClaimsExtractedPayload
  | VisualRoleFailedPayload
  | AIActionAppliedPayload
  | AIActionUndonePayload
  | DPRoutedPayload
  | OutlineBlockPlacedPayload
  | OutlineBlockMovedPayload
  | OutlineBlockRemovedPayload
  | EditCapturedPayload
  | SectionDraftGeneratedPayload
  | BookServabilityChangedPayload
  | BookTakenDownPayload
  | DocumentContentClassDefaultedPayload
  | SeamResearchToReadPayload
  | SeamReadToResearchPayload
  | SeamReadToWritePayload
  | SeamWriteToReadPayload
  | SeamSpeakToWritePayload
  | SeamSpeakToReadPayload
  | SeamWriteToSpeakPayload
  | VoiceCapturedPayload
  | MarginaliaNotedPayload
  | BlockPositionPayload
  | SourceReadPayload
  | ReadBookAnsweredPayload
  | ReadBookAnswerJudgedPayload
  | ReadMetaReadingGeneratedPayload
  | DocumentFiledIntoInvestigationPayload;

/**
 * The envelope around a typed payload. Written one row per JSONL line
 * while live; sealed to Parquet at investigation completion.
 * 
 * The top-level ``action_type`` is redundant with ``payload.action_type``
 * but kept as a separate column for query efficiency — DuckDB filters on
 * action_type without parsing the payload JSON. The model_validator
 * asserts the two agree.
 */
export interface Event {
  event_id: string;
  investigation_id: string;
  synthesis_id?: string | null;
  phase?: number | null;
  role?: string | null;
  action_type: ActionType;
  payload: TypedPayload;
  parent_event_id?: string | null;
  policy_id?: string;
  param_version: string;
  schema_version?: number;
  emitted_at: string;
  document_id?: string | null;
}

export const TYPED_PAYLOAD_ACTION_TYPES: ReadonlySet<ActionType> = new Set<ActionType>([
  "ai.action.applied",
  "ai.action.undone",
  "artifact.generated",
  "artifact.interacted",
  "audit.finding_emitted",
  "block.positioned",
  "claim.asserted_by_operator",
  "claim.challenge_raised",
  "claim.grounding_check_failed",
  "claim.grounding_check_passed",
  "connector.delivered",
  "connector.requested",
  "constraint.loop_resolved",
  "constraint.revision_triggered",
  "constraint.violation_found",
  "context_pack.assembled",
  "cross_doc.question_answered",
  "cross_graph.citation.recorded",
  "decompose.delivered",
  "decompose.requested",
  "decomposer.paraphrase.flagged",
  "decomposer.regenerated",
  "discovery.proposed",
  "discovery.selected",
  "dispatch.call",
  "distillation.delivered",
  "distillation.requested",
  "document.content_class_defaulted",
  "document.filed_into_investigation",
  "document.loaded",
  "document.region_selected",
  "dp.routed",
  "edit.captured",
  "evidence.retrieve.delivered",
  "evidence.retrieve.requested",
  "federation.inbound_citation.accepted",
  "federation.inbound_citation.refused",
  "federation.outbound_citation.emitted",
  "federation.partner.registered",
  "federation.partner.revoked",
  "federation.partner.trusted",
  "fetch.fallback.escalated",
  "graph.edge.inserted",
  "graph.node.inserted",
  "graph.staleness.flagged",
  "graph.staleness.resolve",
  "graph.supersession.apply",
  "graph.supersession.coexist",
  "graph.supersession.dismiss",
  "graph.tier.assigned",
  "graph.tier.overridden",
  "graph.tier.rewrite_bulk",
  "groundedness.failed",
  "groundedness.scored",
  "investigation.chase_halted",
  "investigation.completed",
  "investigation.failed",
  "investigation.spawned_from",
  "investigation.start_requested",
  "knowledge.reused",
  "marginalia.noted",
  "note.compressed_doc_written",
  "note.emerged",
  "note.refined",
  "outcome.recorded",
  "outline_block.moved",
  "outline_block.placed",
  "outline_block.removed",
  "page.attribution.computed",
  "parameter_extract.delivered",
  "parameter_extract.requested",
  "phase.enter",
  "phase.exit",
  "phase.verify",
  "preference.observation.recorded",
  "quality_gate.evaluated",
  "question.escalated_to_research",
  "question.identified",
  "question.resolved_by_doc",
  "read.book_answer_judged",
  "read.book_answered",
  "read.meta_reading.generated",
  "reuse.gated",
  "rev_share.decided",
  "rlm.bridge.decided",
  "rubric.scored",
  "seam.read_to_research",
  "seam.read_to_write",
  "seam.research_to_read",
  "seam.speak_to_read",
  "seam.speak_to_write",
  "seam.write_to_read",
  "seam.write_to_speak",
  "section.draft_generated",
  "skill.auto_patch_applied",
  "skill.auto_patch_skipped",
  "skill.patch_gate_decided",
  "skill.patch_gate_reviewed",
  "skill_rule.promoted",
  "source.read",
  "synthesis.archived",
  "synthesis.master_md_skipped",
  "synthesis.master_md_written",
  "synthesis.substrate_manifest.written",
  "synthesize.delivered",
  "synthesize.requested",
  "user.accept_distillation",
  "user.edit_distillation",
  "user.reject_distillation",
  "verifier.lookup",
  "visual.claims_extracted",
  "visual.frame_identified",
  "visual.role_failed",
  "voice.captured",
  "worker.identity",
]);

export const WRESTLING_ACTION_TYPES: ReadonlySet<ActionType> = new Set<ActionType>([
  "claim.challenge_raised",
  "claim.grounding_check_failed",
  "claim.grounding_check_passed",
  "distillation.delivered",
  "distillation.requested",
  "document.loaded",
  "document.region_selected",
  "note.compressed_doc_written",
  "note.emerged",
  "note.refined",
  "question.escalated_to_research",
  "question.identified",
  "question.resolved_by_doc",
  "user.accept_distillation",
  "user.edit_distillation",
  "user.reject_distillation",
]);
