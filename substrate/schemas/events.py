"""Pydantic v2 schemas for the typed event log.

This module is the **schema source of truth** for the trajectory store.
Two consumers depend on it:

1. ``substrate/event_log/events.py`` — validates typed payloads at write
   time, reconstructs typed Events at read time.
2. ``tools/codegen/`` (week 2) — emits ``apps/reading/src/generated/
   types.ts`` from these models so the TS reading surface and the
   Python substrate share one definition.

Scope of this file:

- The ``ActionType`` string enum (moved here from
  ``substrate/event_log/events.py`` so the schemas package is at the
  bottom of the dependency stack; event_log re-exports for back-compat).
- The ``Event`` envelope.
- Payload variants for the 19 currently-schemaed action types:
  - ``DispatchCallPayload`` (week 1 dependency — cost-tracking emits)
  - ``ContextPackAssembledPayload`` (week 1 dependency — pack provenance)
  - 17 wrestling payloads (locked at substrate time per
    ``architecture_notes.md`` §9.1 so Loop 2 trajectories are typed
    from the first event written)
- A discriminated union over those 19 variants.
- A model validator enforcing that wrestling-loop events carry
  ``document_id`` on the envelope.

Out of scope (deferred per the operator's sequencing call):

- Loop 1 role-output payloads (decomposer → synthesizer). Their right
  shape will be learned from the ``orchestrate.py`` extraction in
  weeks 3–4 and added then. Until then the legacy
  ``log_event(action_type, payload=dict)`` path keeps writing them as
  free-form dict payloads.

Discipline: every new payload added here MUST bump
``EVENT_SCHEMA_VERSION``, document the change in the bump-log comment,
and ship its codegen output for the TS surface in the same commit.
Schema changes are load-bearing API changes (architecture_notes.md §7).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


# ---------------------------------------------------------------------------
# ActionType — stable string vocabulary
# ---------------------------------------------------------------------------


class ActionType(str, Enum):
    """Typed enum of every action emitted as an event. Values stored in
    Parquet — must remain stable across refactors. Add new variants at the
    end of the relevant section; never repurpose."""

    # ── Phase transitions (mirror of phase_log.py operations) ──
    PHASE_ENTER = "phase.enter"
    PHASE_EXIT = "phase.exit"
    PHASE_VERIFY = "phase.verify"

    # ── Five-role pipeline boundaries ──
    ROLE_CALL_START = "role.call.start"
    ROLE_CALL_END = "role.call.end"
    ROLE_CALL_FAILED = "role.call.failed"
    ROLE_VALIDATION_FAILED = "role.validation.failed"
    ROLE_SELF_REPAIR_ATTEMPTED = "role.self_repair.attempted"

    # ── Synthesizer ──
    SYNTHESIZE_REQUESTED = "synthesize.requested"
    SYNTHESIZE_DELIVERED = "synthesize.delivered"

    # ── Audit ──
    AUDIT_FINDING_EMITTED = "audit.finding_emitted"

    # ── Loop 1 orchestrator lifecycle ──
    INVESTIGATION_START_REQUESTED = "investigation.start_requested"
    INVESTIGATION_COMPLETED = "investigation.completed"
    INVESTIGATION_FAILED = "investigation.failed"
    # Sprint 11: web app highlight-to-chase mechanic emits this when a
    # child investigation is spawned from a parent's synthesis. Metadata
    # only — the substrate doesn't act on the parent/child relationship,
    # but the web app uses it to render the chase tree.
    INVESTIGATION_SPAWNED_FROM = "investigation.spawned_from"
    # Sprint 12: continuous chase mode — the orchestrator emits these
    # at the boundary between one chase iteration and the next.
    INVESTIGATION_CHASE_HALTED = "investigation.chase_halted"
    # Sprint 15: creation surface edit-back-into-graph (master spec
    # §10.4 Option B). When the operator edits generated prose, the
    # substrate optionally promotes the edit to a first-class claim
    # that future investigations can cite.
    CLAIM_ASSERTED_BY_OPERATOR = "claim.asserted_by_operator"
    # Sprint 16 partial: IP attribution telemetry (master spec §9.8
    # Phase 1). Emitted by substrate.attribution.compute for each
    # synthesis-attribution computation. Carries all three algorithm
    # share maps for the operator to validate against intuition before
    # any payouts go live.
    PAGE_ATTRIBUTION_COMPUTED = "page.attribution.computed"

    # ── Decomposer-specific ──
    DECOMPOSE_QUESTION_REQUESTED = "decompose.requested"
    DECOMPOSE_QUESTION_DELIVERED = "decompose.delivered"
    DECOMPOSER_PARAPHRASE_FLAGGED = "decomposer.paraphrase.flagged"
    DECOMPOSER_REGENERATED = "decomposer.regenerated"

    # ── Parameter extractor ──
    PARAMETER_EXTRACT_REQUESTED = "parameter_extract.requested"
    PARAMETER_EXTRACT_DELIVERED = "parameter_extract.delivered"

    # ── Evidence retriever ──
    EVIDENCE_RETRIEVE_REQUESTED = "evidence.retrieve.requested"
    EVIDENCE_RETRIEVE_DELIVERED = "evidence.retrieve.delivered"
    EVIDENCE_PACK_BUILT = "evidence.pack_built"

    # ── Cross-domain connector ──
    CONNECTOR_REQUESTED = "connector.requested"
    CONNECTOR_DELIVERED = "connector.delivered"
    CROSS_DOMAIN_KEYWORDS_RESOLVED = "cross_domain.keywords_resolved"
    CROSS_DOMAIN_TRAVERSAL_RAN = "cross_domain.traversal_ran"

    # ── Constraint middleware ──
    CONSTRAINT_PREFLIGHT = "constraint.preflight"
    CONSTRAINT_VIOLATION_FOUND = "constraint.violation_found"
    CONSTRAINT_REVISION_TRIGGERED = "constraint.revision_triggered"
    CONSTRAINT_LOOP_RESOLVED = "constraint.loop_resolved"

    # ── Graph substrate mutations ──
    GRAPH_NODE_INSERTED = "graph.node.inserted"
    GRAPH_EDGE_INSERTED = "graph.edge.inserted"
    GRAPH_TIER_OVERRIDDEN = "graph.tier.overridden"
    GRAPH_SUPERSESSION_PROPOSED = "graph.supersession.proposed"
    GRAPH_STALENESS_FLAGGED = "graph.staleness.flagged"
    NODE_MERGE = "graph.node.merge"
    EMBED_MODEL_REGISTER = "graph.embed_model.register"
    TIER_REWRITE_BULK = "graph.tier.rewrite_bulk"
    SUPERSESSION_APPLY = "graph.supersession.apply"
    SUPERSESSION_DISMISS = "graph.supersession.dismiss"
    SUPERSESSION_COEXIST = "graph.supersession.coexist"
    STALENESS_RESOLVE = "graph.staleness.resolve"

    # ── Archival ──
    SYNTHESIS_ARCHIVED = "synthesis.archived"
    SUBSTRATE_MANIFEST_WRITTEN = "synthesis.substrate_manifest.written"
    MASTER_MD_WRITTEN = "synthesis.master_md_written"
    MASTER_MD_SKIPPED = "synthesis.master_md_skipped"

    # ── Phase-7→8 mechanical skill patcher (skills/domain/auto_patch) ──
    AUTO_PATCH_APPLIED = "skill.auto_patch_applied"
    AUTO_PATCH_SKIPPED = "skill.auto_patch_skipped"

    # ── Outcome capture (deferred ground truth) ──
    OUTCOME_RECORDED = "outcome.recorded"

    # ── Rubric scoring ──
    RUBRIC_SCORED = "rubric.scored"

    # ── Workstation user interactions (legacy, kept for back-compat
    #    with Researchmaxx exports) ──
    USER_ACCEPT_DELTA = "user.accept_delta"
    USER_REJECT_DELTA = "user.reject_delta"
    USER_MODIFY_DELTA = "user.modify_delta"

    # ── Pipeline lifecycle / termination ──
    PIPELINE_TERMINATED = "pipeline.terminated"

    # ── Phase 8 / knowledge_extraction ──
    KE_LLM_RESPONSE_FAILED = "knowledge_extraction.llm_response.failed"

    # ── Dispatch + context pack ──
    DISPATCH_CALL = "dispatch.call"
    CONTEXT_PACK_ASSEMBLED = "context_pack.assembled"

    # ── Middleware: source_tier ──
    # GRAPH_TIER_ASSIGNED — rule-based assignment at ingestion (one per document).
    # GRAPH_TIER_OVERRIDDEN / TIER_REWRITE_BULK already declared above; their
    # payloads are typed in the middleware section of this file.
    GRAPH_TIER_ASSIGNED = "graph.tier.assigned"

    # ── Wrestling loop (architecture_notes §9.1) ──
    DOCUMENT_LOADED = "document.loaded"
    DOCUMENT_REGION_SELECTED = "document.region_selected"
    DISTILLATION_REQUESTED = "distillation.requested"
    DISTILLATION_DELIVERED = "distillation.delivered"
    CLAIM_CHALLENGE_RAISED = "claim.challenge_raised"
    CLAIM_GROUNDING_CHECK_PASSED = "claim.grounding_check_passed"
    CLAIM_GROUNDING_CHECK_FAILED = "claim.grounding_check_failed"
    NOTE_EMERGED = "note.emerged"
    NOTE_REFINED = "note.refined"
    NOTE_COMPRESSED_DOC_WRITTEN = "note.compressed_doc_written"
    QUESTION_IDENTIFIED = "question.identified"
    QUESTION_ESCALATED_TO_RESEARCH = "question.escalated_to_research"
    QUESTION_RESOLVED_BY_DOC = "question.resolved_by_doc"
    CROSS_DOC_QUESTION_ANSWERED = "cross_doc.question_answered"
    USER_ACCEPT_DISTILLATION = "user.accept_distillation"
    USER_REJECT_DISTILLATION = "user.reject_distillation"
    USER_EDIT_DISTILLATION = "user.edit_distillation"

    # ── Exploration artifacts (architecture_notes §13.1, Layer 4) ──
    # Structured intent in the log; HTML rendering on disk at
    # ~/.antiek/artifacts/<hash>.html. Interactions inside the artifact
    # emit specific typed events (user.accept_distillation, etc.);
    # artifact.interacted captures lifecycle only (opened/closed/dismissed).
    ARTIFACT_GENERATED = "artifact.generated"
    ARTIFACT_INTERACTED = "artifact.interacted"

    # ── Sprint 17-30+ additions (master-spec §11.6 + §13.5 + §13.7
    #    + §13.9). Bumped EVENT_SCHEMA_VERSION accordingly when this
    #    block landed.
    # RLM bridge decision (orchestration/rlm/bridge.py) — emitted by
    # wrestling.document_loaded when the bridge decides escalate/defer.
    RLM_BRIDGE_DECIDED = "rlm.bridge.decided"
    # Quality-gate verdict for §13.9 public-graph promotion.
    QUALITY_GATE_EVALUATED = "quality_gate.evaluated"
    # Cross-graph citation recorded (substrate/cross_graph/federation.py).
    CROSS_GRAPH_CITATION_RECORDED = "cross_graph.citation.recorded"
    # PayoutRouter decisions — one event per RevShareDecision emitted
    # by substrate/ad_inventory/event_subscription.py.
    REV_SHARE_DECIDED = "rev_share.decided"
    # DP-aware preference learning (substrate/dp_shuffler/preference_learning.py).
    PREFERENCE_OBSERVATION_RECORDED = "preference.observation.recorded"
    # Skill-rule promotion to the shared substrate (substrate/multi_user/skill_writer.py).
    SKILL_RULE_PROMOTED = "skill_rule.promoted"

    # ── Sprint 18 — Exa/Browserbase substrate-only precursor ──────────
    # Spec: docs/integration_exa_browserbase.md §18.3.
    # Discovery layer: discovery.proposed records "we considered this URL";
    # discovery.selected ties a prior discovery_id to the resulting
    # document_id (or to a refusal — rejected_by_legal_gate, etc.).
    # NOT a graph-write event; the URL adapter still owns DocumentLoaded.
    DISCOVERY_PROPOSED = "discovery.proposed"
    DISCOVERY_SELECTED = "discovery.selected"
    # Ingestion-layer escalation: emitted by acquisition/urls/adapter.py
    # when the httpx primary fetch returned low_word_count and the
    # caller opted into a heavier fetcher (currently Browserbase).
    FETCH_FALLBACK_ESCALATED = "fetch.fallback.escalated"


# Schema version stamped into every emitted row. Bump when any payload
# shape changes or when a new action_type is added to the typed union.
#
# v1: initial Researchmaxx vocabulary.
# v2: NODE_MERGE, EMBED_MODEL_REGISTER, TIER_REWRITE_BULK, SUPERSESSION_*,
#     STALENESS_RESOLVE, SUBSTRATE_MANIFEST_WRITTEN.
# v3: Antiek migration — wrestling-loop vocabulary added; DISPATCH_CALL and
#     CONTEXT_PACK_ASSEMBLED added; 19 typed payloads introduced via
#     discriminated union. 2026-05-16.
# v4: Sprint 17-30+ — RLM bridge decisions, quality-gate verdicts,
#     cross-graph citations, payout decisions, preference observations.
#     2026-05-19.
# v5: Sprint 30+ skill-rule promotion — dedicated payload replaces the
#     v4 placeholder that reused cross_graph.citation.recorded for
#     skill-writer audit events. 2026-05-19.
# v6: Sprint 18 Exa/Browserbase substrate-only precursor — DISCOVERY_PROPOSED,
#     DISCOVERY_SELECTED, FETCH_FALLBACK_ESCALATED action types and their
#     payloads. Discovery layer is upstream of the URL adapter; ingestion
#     escalation event records when httpx's low_word_count skip path was
#     re-fetched via Browserbase. The wedges themselves (Sprint 18-19) emit
#     these; this precursor only types them.
#     docs/integration_exa_browserbase.md §18.3. 2026-05-21.
EVENT_SCHEMA_VERSION: int = 6

# Deterministic code paths (graph ops, SQL, embedding math) are themselves
# a "policy" but a stable code-defined one. LLM call events override this
# with their model_id (per ``policy_id`` discipline in
# architecture_notes.md).
DEFAULT_POLICY_ID: str = "orchestrator-deterministic"


# ---------------------------------------------------------------------------
# Payload variants
#
# Each payload model carries an ``action_type`` Literal that serves as the
# discriminator. Defaults are set so payload constructors don't need to
# repeat the discriminator value at every call site.
# ---------------------------------------------------------------------------


class _PayloadBase(BaseModel):
    """Marker base for typed payloads. ``extra='forbid'`` is deliberate —
    a typo in a payload field should fail loudly, not silently land as an
    extra column that breaks codegen.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# ── Dispatch + context pack ─────────────────────────────────────────


class DispatchCallPayload(_PayloadBase):
    """Emitted by ``substrate/dispatch/`` on every LLM provider call.

    The cost-tracking decorator populates these fields after the call
    returns; the event is then written to the trajectory.
    """

    action_type: Literal[ActionType.DISPATCH_CALL] = ActionType.DISPATCH_CALL
    provider: str
    model: str
    tier: Literal["flash", "pro", "synthesis", "verify", "local"]
    target_role: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    latency_ms: int = Field(ge=0)
    verification_required: bool = False
    fallback_chain_index: int = Field(ge=0, default=0)
    prompt_hash: str
    finish_reason: Optional[
        Literal["stop", "length", "tool_use", "content_filter", "error"]
    ] = None
    context_pack_event_id: Optional[str] = None


class ContextLayer(BaseModel):
    """One layer of an assembled context pack. Embedded inside
    ``ContextPackAssembledPayload.layers``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "session", "long_term_skill", "graph_evidence",
        "phase_metadata", "param_version_stamp",
    ]
    source: str
    tokens: int = Field(ge=0)


# ── Claim — the structured unit of a distillation ────────────────────


# Mirrors ``substrate.constants.CONFIDENCE_LEVELS``. Hard-coded as a
# Literal so the schema is self-contained (codegen doesn't need to chase
# a tuple import). Keep in sync with constants.py manually; the test
# suite asserts equivalence in ``test_events_schema``.
ConfidenceLevel = Literal["high", "moderate", "low", "unknown"]


class Claim(BaseModel):
    """A typed unit of distilled truth. Embedded inside
    ``DistillationDeliveredPayload.claims`` and referenced by
    challenge / grounding-check events via ``claim_id``.

    Why structured: a distillation stored as opaque prose cannot have
    its claims extracted to graph nodes, cannot be diffed, cannot be
    trained on. See ``docs/architecture_notes.md`` §13.1 (Layer 1).
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str  # stable identifier; referenced by later wrestling events
    text: str  # the claim, in verbatim natural language
    confidence: ConfidenceLevel
    attribution_region_ids: list[str]  # source regions that ground this claim
    node_id: Optional[str] = None  # set when promoted to a graph node


class ContextPackAssembledPayload(_PayloadBase):
    """Emitted by ``substrate/context_pack/`` after each pack assembly.

    Captures what the model actually saw at decision time — the layered
    composition + budget reality. This is the queryable property that
    backs §2.5's "what did the model actually see when it made this
    decision" guarantee.
    """

    action_type: Literal[ActionType.CONTEXT_PACK_ASSEMBLED] = ActionType.CONTEXT_PACK_ASSEMBLED
    target_role: str
    target_tokens: int = Field(ge=0)
    actual_tokens: int = Field(ge=0)
    layers: list[ContextLayer]
    budget_overrun: bool
    truncation_strategy_applied: Optional[Literal["head", "tail", "smart"]] = None


# ── Wrestling — document surface ─────────────────────────────────────


class DocumentLoadedPayload(_PayloadBase):
    action_type: Literal[ActionType.DOCUMENT_LOADED] = ActionType.DOCUMENT_LOADED
    media_type: Literal["pdf", "pasted_text", "url_extracted", "markdown"]
    content_hash: str
    size_bytes: int = Field(ge=0)
    title: Optional[str] = None
    page_count: Optional[int] = Field(default=None, ge=0)  # None for pasted text
    source_uri: Optional[str] = None  # file:// for local, https:// for fetched; None for pasted text


class DocumentRegionSelectedPayload(_PayloadBase):
    action_type: Literal[ActionType.DOCUMENT_REGION_SELECTED] = ActionType.DOCUMENT_REGION_SELECTED
    region_id: str
    page: Optional[int] = Field(default=None, ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    bbox: Optional[tuple[float, float, float, float]] = None
    text_excerpt: str  # truncated by the surface; substrate doesn't truncate again


# ── Wrestling — distillation ─────────────────────────────────────────


class DistillationRequestedPayload(_PayloadBase):
    action_type: Literal[ActionType.DISTILLATION_REQUESTED] = ActionType.DISTILLATION_REQUESTED
    region_id: Optional[str] = None  # None = whole-document distillation
    user_prompt: str
    target_token_count: int = Field(ge=0)


class DistillationDeliveredPayload(_PayloadBase):
    """Structured per architecture_notes §13.1 (Layer 1). The distillation
    is a list of typed Claims plus a prose rendering. Storing only an HTML
    or string blob would block claim extraction, diffing, and training."""

    action_type: Literal[ActionType.DISTILLATION_DELIVERED] = ActionType.DISTILLATION_DELIVERED
    request_event_id: str  # parent — the matching distillation.requested
    claims: list[Claim]
    rendered_text: str  # the prose rendering shown to the user
    rendered_text_hash: str  # SHA-256 of rendered_text for dedup/integrity
    token_count: int = Field(ge=0)


# ── Wrestling — claim challenge / grounding ──────────────────────────


class ClaimChallengeRaisedPayload(_PayloadBase):
    """``challenged_claim_id`` references a Claim from a prior
    DistillationDelivered. None means the user challenged a claim that
    isn't (yet) in the system — ``claim_text`` carries it verbatim."""

    action_type: Literal[ActionType.CLAIM_CHALLENGE_RAISED] = ActionType.CLAIM_CHALLENGE_RAISED
    challenged_claim_id: Optional[str] = None
    claim_text: str
    anchor_region_id: Optional[str] = None
    user_question: str


class ClaimGroundingCheckPassedPayload(_PayloadBase):
    action_type: Literal[ActionType.CLAIM_GROUNDING_CHECK_PASSED] = ActionType.CLAIM_GROUNDING_CHECK_PASSED
    claim_id: Optional[str] = None  # None for externally-supplied claims
    claim_text: str
    located_region_id: str
    confidence: float = Field(ge=0.0, le=1.0)


class ClaimGroundingCheckFailedPayload(_PayloadBase):
    action_type: Literal[ActionType.CLAIM_GROUNDING_CHECK_FAILED] = ActionType.CLAIM_GROUNDING_CHECK_FAILED
    claim_id: Optional[str] = None  # None for externally-supplied claims
    claim_text: str
    reason: Literal["absent_from_source", "paraphrased_not_stated", "out_of_scope", "ambiguous"]
    searched_regions: list[str]


# ── Wrestling — emergent notes ───────────────────────────────────────


class NoteEmergedPayload(_PayloadBase):
    action_type: Literal[ActionType.NOTE_EMERGED] = ActionType.NOTE_EMERGED
    note_id: str
    note_text: str
    source_event_ids: list[str]
    # Sprint 5 day 1-2 addition. The note-taker parses a confidence
    # value but pre-S5 the bridge dropped it on the floor. Defaulted
    # to "unknown" so existing emitted events (none on disk yet, but
    # forward-compat regardless) deserialize cleanly.
    confidence: ConfidenceLevel = "unknown"
    node_id: Optional[str] = None  # set when the note is also mirrored to the graph


class NoteRefinedPayload(_PayloadBase):
    action_type: Literal[ActionType.NOTE_REFINED] = ActionType.NOTE_REFINED
    note_id: str
    previous_text: str
    new_text: str
    refinement_reason: str


class NoteCompressedDocWrittenPayload(_PayloadBase):
    action_type: Literal[ActionType.NOTE_COMPRESSED_DOC_WRITTEN] = ActionType.NOTE_COMPRESSED_DOC_WRITTEN
    output_path: str
    note_count: int = Field(ge=0)
    byte_size: int = Field(ge=0)


# ── Wrestling — questions ────────────────────────────────────────────


class QuestionIdentifiedPayload(_PayloadBase):
    action_type: Literal[ActionType.QUESTION_IDENTIFIED] = ActionType.QUESTION_IDENTIFIED
    question_id: str
    question_text: str
    anchor_region_id: Optional[str] = None


class QuestionEscalatedToResearchPayload(_PayloadBase):
    action_type: Literal[ActionType.QUESTION_ESCALATED_TO_RESEARCH] = ActionType.QUESTION_ESCALATED_TO_RESEARCH
    question_id: str
    child_investigation_id: str


class QuestionResolvedByDocPayload(_PayloadBase):
    action_type: Literal[ActionType.QUESTION_RESOLVED_BY_DOC] = ActionType.QUESTION_RESOLVED_BY_DOC
    question_id: str
    answer_note_id: str


# ── Wrestling — cross-document linkage ───────────────────────────────


class CrossDocQuestionAnsweredPayload(_PayloadBase):
    action_type: Literal[ActionType.CROSS_DOC_QUESTION_ANSWERED] = ActionType.CROSS_DOC_QUESTION_ANSWERED
    question_id: str
    question_document_id: str
    answer_document_id: str
    answer_note_id: str


# ── Wrestling — RL signal capture ────────────────────────────────────


class UserAcceptDistillationPayload(_PayloadBase):
    action_type: Literal[ActionType.USER_ACCEPT_DISTILLATION] = ActionType.USER_ACCEPT_DISTILLATION
    distillation_event_id: str


class UserRejectDistillationPayload(_PayloadBase):
    action_type: Literal[ActionType.USER_REJECT_DISTILLATION] = ActionType.USER_REJECT_DISTILLATION
    distillation_event_id: str
    reason: str


class UserEditDistillationPayload(_PayloadBase):
    """The edited content is in the payload (mirrors NoteRefined). Hashes
    are for integrity; trajectory replay needs the actual text."""

    action_type: Literal[ActionType.USER_EDIT_DISTILLATION] = ActionType.USER_EDIT_DISTILLATION
    distillation_event_id: str
    edited_content: str  # the post-edit text shown by the surface
    original_content_hash: str
    edited_content_hash: str


# ── Exploration artifacts (architecture_notes §13.1, Layer 4) ────────


# The set of artifact kinds is intentionally narrow. Extend only when an
# emerging pattern justifies it; adding a Literal value requires a
# schema version bump if it changes the discriminator's value space.
ArtifactKind = Literal[
    "comparison_grid",          # N candidate distillations / framings side-by-side
    "knob_slider_exploration",  # parameter-space exploration of competing claims
    "claim_triage",             # Linear-style triage of emergent questions or claims
    "model_parameter_explorer", # knob-and-slider over a model's parameters
    "other",                    # escape hatch — must be replaced with a named kind once the pattern stabilizes
]


class ArtifactGeneratedPayload(_PayloadBase):
    """Emitted when a role generates an interactive HTML exploration
    artifact on disk. The HTML itself is opaque to the substrate; the
    structured intent lives here. See architecture_notes §13.1 Layer 4.
    """

    action_type: Literal[ActionType.ARTIFACT_GENERATED] = ActionType.ARTIFACT_GENERATED
    artifact_id: str
    artifact_kind: ArtifactKind
    intent: str  # human-readable: why was this generated
    generating_role: str  # one of constants.ROLES
    artifact_path: str  # on-disk path, e.g. ~/.antiek/artifacts/<hash>.html
    content_hash: str  # SHA-256 of the rendered HTML — integrity + dedup
    size_bytes: int = Field(ge=0)
    source_event_ids: list[str]  # events whose state motivated the artifact


class ArtifactInteractedPayload(_PayloadBase):
    """Lifecycle event for an artifact (opened / closed / dismissed).
    Substantive interactions inside the artifact emit their own typed
    events (user.accept_distillation, claim.challenge_raised, etc.); this
    event captures the lifecycle envelope only."""

    action_type: Literal[ActionType.ARTIFACT_INTERACTED] = ActionType.ARTIFACT_INTERACTED
    artifact_id: str
    interaction_kind: Literal["opened", "closed", "dismissed"]


# ── Middleware: source_tier (architecture_notes §4) ──────────────────


# Methods the tier-classifier may use. ``document_type_lookup`` is the
# fast path (deterministic catalogue); ``keyword_fallback`` is the
# defensible-but-fuzzy substring path; ``default`` is the conservative
# tier-4 fallback when no signal is available.
TierClassificationMethod = Literal[
    "document_type_lookup", "keyword_fallback", "default",
]

# Methods the per-chunk hedging downgrade may use.
TierAdjustmentMethod = Literal["regex", "llm", "none"]


class TierAssignedPayload(_PayloadBase):
    """Emitted once per document when the rule-based classifier assigns a
    tier at ingestion. The asymmetric design (rule-based assignment;
    LLM may only adjust DOWNWARD via TierOverriddenPayload) is preserved
    from Researchmaxx per architecture_notes §4.
    """

    action_type: Literal[ActionType.GRAPH_TIER_ASSIGNED] = ActionType.GRAPH_TIER_ASSIGNED
    document_id: str
    document_type: Optional[str]  # the input that drove the rule
    assigned_tier: int = Field(ge=1, le=5)
    classification_method: TierClassificationMethod
    # Filled only when classification_method == "keyword_fallback".
    # Empty list when the deterministic catalogue produced the answer.
    keyword_matches: list[str] = Field(default_factory=list)


class TierOverriddenPayload(_PayloadBase):
    """LLM-mediated downward adjustment after extraction. The asymmetry
    is enforced by the middleware: ``adjusted_tier >= original_tier``
    always (lower number = higher trust; the LLM can argue a source is
    less reliable than the rules say, never more)."""

    action_type: Literal[ActionType.GRAPH_TIER_OVERRIDDEN] = ActionType.GRAPH_TIER_OVERRIDDEN
    chunk_id: str
    original_tier: int = Field(ge=1, le=5)
    adjusted_tier: int = Field(ge=1, le=5)
    adjustment_method: TierAdjustmentMethod
    hedging_signals: list[str]  # signal_type strings from the regex catalogue
    reason: str


class TierRewriteBulkPayload(_PayloadBase):
    """A global reclassification sweep. Not scoped to a single
    investigation — the envelope's investigation_id is conventionally
    ``substrate.constants.SYSTEM_INVESTIGATION_ID`` (``"system"``)."""

    action_type: Literal[ActionType.TIER_REWRITE_BULK] = ActionType.TIER_REWRITE_BULK
    total: int = Field(ge=0)
    updated: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    # Tier (1–5) → count of documents at that tier post-sweep.
    by_tier: dict[int, int]


# ── Middleware: temporal / staleness (architecture_notes §4) ─────────


# Resolution outcomes for a stale flag.
StalenessResolution = Literal["refreshed", "confirmed_stale", "dismissed"]


class StalenessFlaggedPayload(_PayloadBase):
    """Emitted when the staleness scanner queues a flag for an edge whose
    age exceeds the TTL for its claim_class. Flags are advisory — they
    queue the entity for refresh in the next investigation that touches
    it, not auto-invalidation."""

    action_type: Literal[ActionType.GRAPH_STALENESS_FLAGGED] = ActionType.GRAPH_STALENESS_FLAGGED
    flag_id: str
    edge_id: str
    relation: str  # the graph relation that drove claim_class classification
    # One of ``substrate.constants.STALENESS_TTL_DAYS`` keys.
    claim_class: str
    ttl_days: int = Field(ge=0)
    age_days: int = Field(ge=0)


class StalenessResolvePayload(_PayloadBase):
    """Emitted when a stale flag is resolved (refreshed / confirmed stale
    / dismissed). ``entity_kind`` is currently always 'edge' — the
    scanner only flags edges — but the Literal allows future expansion
    without a schema bump if we add node-level flags."""

    action_type: Literal[ActionType.STALENESS_RESOLVE] = ActionType.STALENESS_RESOLVE
    flag_id: str
    entity_kind: Literal["edge", "node"]
    entity_id: str
    status: StalenessResolution
    notes: str = ""


# ── Middleware: archive (architecture_notes §4) ──────────────────────


# Synthesis lifecycle status. Mirrors the ``syntheses.status`` column
# values used by Researchmaxx's archive pipeline.
SynthesisStatus = Literal[
    "draft",
    "passed",
    "regressed",
    "max_iterations_reached",
    "escalated",
]

# The Synthesizer's implicit recommendation. Stratified the same way
# Researchmaxx uses for backtest cohorts.
#
# ``insufficient_evidence`` was added in Sprint 7 day 5 — the upstream
# synthesizer prompt's preferred terminology for "evidence does not
# support a defensible thesis." ``undetermined`` is kept for backward
# compat with the older archive rows; new pipelines emit
# ``insufficient_evidence``.
SynthesisRecommendation = Literal[
    "proceed",
    "pass",
    "conditional",
    "undetermined",
    "insufficient_evidence",
]


class SynthesisArchivedPayload(_PayloadBase):
    """Emitted by ``middleware/archive/`` when a synthesis is committed
    to the syntheses table. The envelope's ``synthesis_id`` carries the
    archived id; the payload carries the high-level metadata an
    analytics consumer needs WITHOUT reading the full synthesis row.

    Architecture_notes §4: archive is the only writer to the syntheses
    table. This event is the canonical "synthesis exists now" signal
    for downstream consumers (backtest, cohort, weekly_report)."""

    action_type: Literal[ActionType.SYNTHESIS_ARCHIVED] = ActionType.SYNTHESIS_ARCHIVED
    target_question: str
    synthesis_timestamp: datetime
    status: SynthesisStatus
    implicit_recommendation: SynthesisRecommendation
    # role → "<model>/<prompt_version>" — same shape Antiek uses for
    # policy_id stamping on dispatch.call events. Lets a backtest
    # cohort segment by the role-to-model mapping at archive time.
    model_versions: dict[str, str] = Field(default_factory=dict)
    thesis_token_count: int = Field(ge=0, default=0)
    has_constraint_check_result: bool = False


class SubstrateManifestWrittenPayload(_PayloadBase):
    """Emitted when the substrate manifest for an archived synthesis is
    pinned (one row per (synthesis_id, entity_kind, entity_id) tuple in
    the ``synthesis_substrate_manifest`` table). The envelope's
    ``synthesis_id`` links back to the synthesis."""

    action_type: Literal[ActionType.SUBSTRATE_MANIFEST_WRITTEN] = ActionType.SUBSTRATE_MANIFEST_WRITTEN
    synthesis_timestamp: datetime
    manifest_rows_written: int = Field(ge=0)
    # entity_kind ('document' | 'chunk' | 'node' | 'edge') → count.
    # Counts are pre-INSERT-OR-IGNORE (the input cardinality the
    # pipeline asked to pin), not post-dedupe row count. Matches the
    # Researchmaxx semantics for trajectory analytics.
    counts_by_kind: dict[str, int]


# ── Middleware: supersession (architecture_notes §4) ─────────────────


# Which side of the contradiction was dismissed.
SupersessionTarget = Literal["new", "old"]


class SupersessionApplyPayload(_PayloadBase):
    """Reviewer chose ``apply_supersession``: the old edge is closed
    (``valid_until`` set) and linked to the new edge via
    ``superseded_by``."""

    action_type: Literal[ActionType.SUPERSESSION_APPLY] = ActionType.SUPERSESSION_APPLY
    candidate_id: str
    old_edge_id: str
    new_edge_id: str
    new_valid_until: datetime
    reviewer: str
    review_notes: str = ""


class SupersessionDismissPayload(_PayloadBase):
    """Reviewer chose ``dismiss_new`` or ``dismiss_old``: one edge is
    closed without superseding the other. ``target`` records which
    side was dismissed."""

    action_type: Literal[ActionType.SUPERSESSION_DISMISS] = ActionType.SUPERSESSION_DISMISS
    candidate_id: str
    edge_id: str
    target: SupersessionTarget
    valid_until: datetime
    reviewer: str
    review_notes: str = ""


class SupersessionCoexistPayload(_PayloadBase):
    """Reviewer chose ``coexist``: both edges remain active. The
    candidate is marked reviewed but no edge mutation occurs."""

    action_type: Literal[ActionType.SUPERSESSION_COEXIST] = ActionType.SUPERSESSION_COEXIST
    candidate_id: str
    reviewer: str
    review_notes: str = ""


# ── Substrate: graph (architecture_notes §2.5) ───────────────────────


# Closed node-type taxonomy. Matches the v2 Researchmaxx schema; the
# CHECK constraint on ``nodes.node_type`` in substrate/graph/schema.py
# rejects anything not in this set, so the schema-level and DB-level
# enforcement agree.
NodeType = Literal[
    "entity",
    "organization",
    "person",
    "property",
    "metric",
    "mechanism",
    "claim",
    "method",
    "constraint",
]

# Closed graph_scope taxonomy. Determines which traversal algorithms
# and search filters consider a node/edge.
GraphScope = Literal["depth", "cross_domain", "constraint"]


class GraphNodeInsertedPayload(_PayloadBase):
    """Emitted by ``substrate/graph/ops.insert_node`` after a node row
    is committed. The envelope's ``investigation_id`` carries scope;
    the payload carries the identity + typing the node was admitted
    under so a downstream consumer can reconstruct "what was in the
    graph when this synthesis ran" without re-reading the row."""

    action_type: Literal[ActionType.GRAPH_NODE_INSERTED] = ActionType.GRAPH_NODE_INSERTED
    node_id: str
    canonical_label: str
    node_type: NodeType
    graph_scope: GraphScope
    has_embedding: bool


class GraphEdgeInsertedPayload(_PayloadBase):
    """Emitted by ``substrate/graph/ops.insert_edge`` after an edge row
    is committed. Records the source/target/relation triple, the
    source attribution (document + chunk + tier), and the extraction
    confidence the extractor assigned at admission."""

    action_type: Literal[ActionType.GRAPH_EDGE_INSERTED] = ActionType.GRAPH_EDGE_INSERTED
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation: str
    source_document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    source_tier: int = Field(ge=1, le=5)
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    graph_scope: GraphScope


# ── Middleware: constraint_check (architecture_notes §4) ─────────────


# Constraint strictness — mirrors ``substrate.constants.CONSTRAINT_STRICTNESS``.
# Hard constraints must be satisfied or the constraint loop re-invokes the
# synthesizer; soft constraints are recorded in metadata but don't trigger
# revision; target constraints carry a distance metric for the operator.
ConstraintStrictness = Literal["hard", "soft", "target"]

# Closed kind taxonomy for v1 constraint checking. The migration starts
# narrow on purpose — quantitative range + qualitative term presence +
# attribution. Researchmaxx's lost 2,000-LOC implementation had many
# more; we add kinds here as the synthesizer extraction surfaces them.
ConstraintKind = Literal[
    "numeric_range",
    "must_include_term",
    "must_attribute",
]

# Terminal status of the constraint loop. Mirrors the Researchmaxx
# vocabulary verbatim so a migrated trajectory's status filters
# (``status NOT IN ('passed', 'single_pass')``) still work unchanged.
ConstraintLoopStatus = Literal[
    "single_pass",            # no constraints applied; one-shot through
    "passed",                 # iterated until all hard constraints satisfied
    "regressed",              # violations got worse across iterations
    "max_iterations_reached", # burned the 3-iteration budget without clearing
    "escalated",              # preflight conflict — constraints contradictory
    "preflight_failed",       # constraints contradictory before any iteration
]


class ConstraintViolationFoundPayload(_PayloadBase):
    """Emitted when a constraint check identifies a violation. One
    event per violation per iteration — a synthesis can produce many
    of these inside a single constraint loop pass."""

    action_type: Literal[ActionType.CONSTRAINT_VIOLATION_FOUND] = ActionType.CONSTRAINT_VIOLATION_FOUND
    constraint_id: str
    strictness: ConstraintStrictness
    constraint_kind: ConstraintKind
    iteration: int = Field(ge=0)
    target_claim_id: Optional[str] = None
    reason: str


class ConstraintRevisionTriggeredPayload(_PayloadBase):
    """Emitted when the constraint loop decides to re-invoke the
    synthesizer because at least one HARD constraint is still violated
    after the latest iteration. The triggering_constraint_ids list lets
    a downstream cohort analysis correlate which constraint kinds
    consume the most iterations."""

    action_type: Literal[ActionType.CONSTRAINT_REVISION_TRIGGERED] = ActionType.CONSTRAINT_REVISION_TRIGGERED
    iteration: int = Field(ge=0)
    triggering_constraint_ids: list[str]


class ConstraintLoopResolvedPayload(_PayloadBase):
    """Emitted exactly once per constraint loop, on termination. The
    ``final_status`` mirrors the Researchmaxx terminal vocabulary so a
    migrated cohort backtest stays compatible."""

    action_type: Literal[ActionType.CONSTRAINT_LOOP_RESOLVED] = ActionType.CONSTRAINT_LOOP_RESOLVED
    final_status: ConstraintLoopStatus
    total_iterations: int = Field(ge=0)
    final_violation_count: int = Field(ge=0)


# ── Middleware: outcomes + cohort + backtest (Sprint 5 day 2-3) ──────


# Outcome literal vocabularies — mirror Researchmaxx outcomes.py +
# cohort.py wording verbatim so migrated backtest queries work
# unchanged once the on-disk outcomes table lands.
ThesisOutcomeStatus = Literal[
    "confirmed", "partially_confirmed", "disconfirmed", "unresolved",
]
ExecutionRiskSeverity = Literal[
    "critical", "high", "moderate", "low", "none",
]
DecisionRecommendation = Literal["proceed", "pass", "conditional"]
ActualDecision = Literal["proceed", "pass", "conditional", "not_observed"]
ProceedOutcome = Literal[
    "confirmed", "partially_confirmed", "disconfirmed", "not_observed",
]


class ThesisOutcome(BaseModel):
    """One thesis_components[i] outcome — does the claim hold against
    the observed ground truth?"""

    model_config = ConfigDict(extra="forbid")

    thesis_claim: str
    outcome: ThesisOutcomeStatus
    evidence: str = ""
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class FalsificationOutcome(BaseModel):
    """One falsification_conditions[i] check — did the predicted
    failure condition occur?"""

    model_config = ConfigDict(extra="forbid")

    condition: str
    occurred: bool
    evidence: str = ""


class ExecutionRiskOutcome(BaseModel):
    """One execution_risks[i] check — did the risk manifest, and how
    severely vs the agent's anticipated severity?"""

    model_config = ConfigDict(extra="forbid")

    risk: str
    manifested: bool
    severity_actual: ExecutionRiskSeverity
    evidence: str = ""


class DecisionAlignment(BaseModel):
    """Decision-outcome correlation. ``thesis_outcome_when_proceeded``
    is the structured grade — replaces keyword-scanning the prose
    field per Researchmaxx cohort.py."""

    model_config = ConfigDict(extra="forbid")

    agent_implicit_recommendation: DecisionRecommendation
    actual_decision: ActualDecision
    decision_outcome_at_observation: str
    thesis_outcome_when_proceeded: ProceedOutcome = "not_observed"


class OutcomeRecordedPayload(_PayloadBase):
    """Emitted by ``middleware/outcomes/`` when an outcome row is
    written against a previously-archived synthesis. The envelope's
    ``synthesis_id`` carries the archived synthesis the outcome
    grades against."""

    action_type: Literal[ActionType.OUTCOME_RECORDED] = ActionType.OUTCOME_RECORDED
    outcome_id: str
    observer: str
    thesis_outcomes: list[ThesisOutcome] = Field(default_factory=list)
    falsification_outcomes: list[FalsificationOutcome] = Field(default_factory=list)
    execution_risk_outcomes: list[ExecutionRiskOutcome] = Field(default_factory=list)
    decision_alignment: Optional[DecisionAlignment] = None
    notes: str = ""


class RubricScoredPayload(_PayloadBase):
    """Emitted by a verification skill (the constraint middleware's
    deterministic-rubric + judged-rubric pairing per architecture_notes
    §3.2). Captures both component scores plus the final aggregated
    score so cohort analysis can correlate verification quality to
    synthesizer outcomes.

    All three score fields are in [0, 1] when set. Deterministic
    component may be None when the rubric is purely judgmental;
    judged component may be None when the rubric is purely
    deterministic; final_score is always required."""

    action_type: Literal[ActionType.RUBRIC_SCORED] = ActionType.RUBRIC_SCORED
    rubric_id: str
    target_claim_id: Optional[str] = None
    deterministic_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    judged_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
    notes: str = ""


# ---------------------------------------------------------------------------
# Decomposer payloads (Sprint 6 day 1-2 — first orchestrate.py role
# extraction). The four typed payloads here type the decomposer's
# inputs (DECOMPOSE_QUESTION_REQUESTED), output
# (DECOMPOSE_QUESTION_DELIVERED), and paraphrase-guard telemetry
# (DECOMPOSER_PARAPHRASE_FLAGGED + DECOMPOSER_REGENERATED).
# ---------------------------------------------------------------------------


# Closed taxonomies — mirror prompts/decomposer.md verbatim so the
# parser and the schema agree on what counts as a valid emission. Drift
# is caught by ``tests/test_roles_decomposer.py``.
SubQuestionCategory = Literal[
    "market_sizing",
    "defensibility",
    "unit_economics",
    "team_and_execution",
    "regulatory_exposure",
    "competitive_dynamics",
    "customer_concentration",
    "technology_risk",
    "capital_intensity",
    "exit_pathways",
]

EvidenceTypeRequired = Literal["quantitative", "qualitative", "mixed"]


class SubQuestion(BaseModel):
    """One evidence-addressable sub-question produced by the
    Decomposer. ``rationale`` must explain why the sub-question carries
    independent analytical weight — a deletable rationale is a signal
    the sub-question is performative (prompts/decomposer.md anti-pattern
    #4)."""

    model_config = ConfigDict(extra="forbid")

    sub_question: str
    category: SubQuestionCategory
    rationale: str
    evidence_type_required: EvidenceTypeRequired


class Keyword(BaseModel):
    """One retrieval keyword + optional synonyms. ``synonyms`` is
    capped at 3 by the prompt; the field is forward-additive (longer
    lists are NOT rejected here so historical traces with permissive
    schemas still validate)."""

    model_config = ConfigDict(extra="forbid")

    term: str
    synonyms: list[str] = Field(default_factory=list)


class ParaphraseFlagRecord(BaseModel):
    """One flagged sub-question record. Mirrors the
    ``ParaphraseFlag`` dataclass in ``roles/decomposer/paraphrase.py``
    so the bridge can serialize check results into the trajectory
    without an adapter."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    sub_question: str
    cosine: float = Field(ge=0.0, le=1.0)


class DecomposeQuestionRequestedPayload(_PayloadBase):
    """Emitted by upstream callers (heartbeat, kanban, interview
    workflow) to request a Decomposer run. The bridge handler
    subscribes to this action_type, dispatches the role, and emits
    ``DECOMPOSE_QUESTION_DELIVERED`` when done.

    ``context`` is optional domain framing — empty string when the
    caller has nothing extra to say."""

    action_type: Literal[ActionType.DECOMPOSE_QUESTION_REQUESTED] = (
        ActionType.DECOMPOSE_QUESTION_REQUESTED
    )
    question: str
    context: str = ""


class DecomposeQuestionDeliveredPayload(_PayloadBase):
    """Emitted by the Decomposer bridge once a (possibly regenerated)
    decomposition has been produced. Carries the structured output
    plus the paraphrase-guard outcome — ``paraphrase_pass_count`` is
    1 for a clean first pass, 2 for a regenerated pass."""

    action_type: Literal[ActionType.DECOMPOSE_QUESTION_DELIVERED] = (
        ActionType.DECOMPOSE_QUESTION_DELIVERED
    )
    decomposition: list[SubQuestion]
    keywords: list[Keyword]
    paraphrase_pass_count: int = Field(default=1, ge=1, le=2)
    paraphrase_flagged_count_final: int = Field(default=0, ge=0)


class DecomposerParaphraseFlaggedPayload(_PayloadBase):
    """Emitted when the paraphrase check on a Decomposer pass finds
    one or more sub-questions whose embedding sits within cosine
    similarity ≥ DECOMPOSER_PARAPHRASE_COSINE_MAX of the top-level
    question. The bridge follows this with a regeneration pass."""

    action_type: Literal[ActionType.DECOMPOSER_PARAPHRASE_FLAGGED] = (
        ActionType.DECOMPOSER_PARAPHRASE_FLAGGED
    )
    pass_index: int = Field(ge=1, le=2)
    n_sub_questions: int = Field(ge=0)
    flagged: list[ParaphraseFlagRecord]


class DecomposerRegeneratedPayload(_PayloadBase):
    """Emitted exactly once when the Decomposer's regeneration pass
    completes. ``still_flagged`` is True when the second pass also
    produced paraphrases — the bridge still proceeds (one regen is the
    upstream's hard cap) but surfaces the failure mode on the
    trajectory."""

    action_type: Literal[ActionType.DECOMPOSER_REGENERATED] = (
        ActionType.DECOMPOSER_REGENERATED
    )
    flagged_after_regen: list[ParaphraseFlagRecord]
    still_flagged: bool


# ---------------------------------------------------------------------------
# Connector payloads (Sprint 7 day 4 — cross-domain traversal role).
# The request carries the seed pairs to traverse + the pre-resolved
# keyword mappings; the bridge runs ``substrate.graph.traverse``
# against the seeds and renders the prompt blocks. The Delivered
# payload mirrors the role's full output verbatim — keyword mapping
# confirmations, the algorithm choice, the structured paths
# (pass-through), and the natural-language renderings that the
# Synthesizer (Day 5) will cite.
# ---------------------------------------------------------------------------


TraversalAlgorithm = Literal[
    "shortest_simple_path",
    "top_n_shortest_paths",
    "depth_first_limited",
    "bfs_semantic_stop",
]


class KeywordMapping(BaseModel):
    """One pre-resolved keyword → graph node mapping. ``low_confidence``
    is True when ``similarity < 0.80`` (the upstream threshold);
    the role must mark these but never silently drop them."""

    model_config = ConfigDict(extra="forbid")

    keyword: str
    matched_node_id: Optional[str] = None
    matched_node_label: Optional[str] = None
    matched_node_type: Optional[str] = None
    similarity: float = Field(ge=0.0, le=1.0)
    low_confidence: bool = False


class SeedPair(BaseModel):
    """One (source_node_id, target_node_id) pair for the connector
    bridge to traverse between. Optional ``source_keyword`` /
    ``target_keyword`` are passed through for trajectory legibility."""

    model_config = ConfigDict(extra="forbid")

    source_node_id: str
    target_node_id: str
    source_keyword: Optional[str] = None
    target_keyword: Optional[str] = None


class GraphPath(BaseModel):
    """One structured path produced by traversal. Mirrors the dict
    shape ``substrate.graph.traverse._format_path`` returns, augmented
    with ``node_labels`` + ``edge_ids`` for citation back to the
    underlying graph."""

    model_config = ConfigDict(extra="forbid")

    path_nodes: list[str]
    path_relations: list[str]
    depth: int = Field(ge=0)
    avg_confidence: float = Field(ge=0.0, le=1.0)
    node_labels: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)


class NaturalLanguageRelationship(BaseModel):
    """One NL rendering of a structured path. ``source_path_index`` is
    the offset into the ``paths`` list, so the Synthesizer can cite
    the underlying graph path verbatim."""

    model_config = ConfigDict(extra="forbid")

    text: str
    source_path_index: int = Field(ge=0)


class ConnectorRequestedPayload(_PayloadBase):
    """Emitted by upstream callers to request a Connector dispatch.
    The bridge runs traversal against ``seed_pairs`` with the
    requested ``algorithm`` (default top_n_shortest_paths) and the
    per-pair top-N cap."""

    action_type: Literal[ActionType.CONNECTOR_REQUESTED] = ActionType.CONNECTOR_REQUESTED
    keyword_mappings: list[KeywordMapping] = Field(default_factory=list)
    seed_pairs: list[SeedPair] = Field(default_factory=list)
    algorithm: TraversalAlgorithm = "top_n_shortest_paths"
    max_paths_per_pair: int = Field(default=5, ge=1, le=50)


class ConnectorDeliveredPayload(_PayloadBase):
    """Emitted by the Connector bridge once a parsed + validated
    response lands. Carries:

    - ``keyword_mappings`` — role's confirmation / correction of the
      pre-resolved mappings; ``low_confidence`` flags preserved.
    - ``selected_algorithm`` — role's algorithm choice (echoes what
      the bridge actually ran; lets the role correct in retrospect).
    - ``paths`` — structured paths from traversal, passed through
      verbatim (the role MUST NOT edit them).
    - ``natural_language_relationships`` — one per path, with
      ``source_path_index`` cite-back."""

    action_type: Literal[ActionType.CONNECTOR_DELIVERED] = ActionType.CONNECTOR_DELIVERED
    keyword_mappings: list[KeywordMapping] = Field(default_factory=list)
    selected_algorithm: TraversalAlgorithm
    algorithm_rationale: Optional[str] = None
    paths: list[GraphPath] = Field(default_factory=list)
    natural_language_relationships: list[NaturalLanguageRelationship] = Field(
        default_factory=list,
    )


# ---------------------------------------------------------------------------
# Synthesizer payloads (Sprint 7 day 5 — last and largest of the four
# orchestrate.py role extractions). The Delivered payload is the
# canonical thesis shape — it's what middleware/archive will write to
# the syntheses table and what the constraint loop iterates against.
#
# Closed vocabularies match prompts/synthesizer.md verbatim. Drift
# between these Literals and the parser's frozenset enforcement is
# caught by tests.
# ---------------------------------------------------------------------------


# Synthesizer's execution-risk severity has four values — distinct
# from ``ExecutionRiskSeverity`` (which carries an extra ``"none"``
# value used by the outcomes-table observation shape; a risk with
# "none" severity is a thesis-time error but a valid post-hoc
# outcome). Keep the names different so drift is loud.
ThesisRiskSeverity = Literal["critical", "high", "moderate", "low"]


class ThesisComponent(BaseModel):
    """One load-bearing claim in the thesis. Must cite either
    ``supporting_chunk_ids`` (evidence-grounded) OR
    ``supporting_path_indices`` (analogy-grounded via connector
    paths) — the upstream's "provenance is structural" rule. The
    parser enforces this disjunction; the Pydantic model carries the
    fields but doesn't reject empty-both at the schema layer.

    ``effective_source_tier`` is in [1, 5] OR ``None``. ``0`` is
    forbidden (the upstream prompt's explicit prohibition; defended
    by ``Field(ge=1, le=5)``)."""

    model_config = ConfigDict(extra="forbid")

    claim: str
    confidence: ConfidenceLevel
    supporting_chunk_ids: list[str] = Field(default_factory=list)
    supporting_path_indices: list[int] = Field(default_factory=list)
    confidence_basis: Optional[str] = None
    effective_source_tier: Optional[int] = Field(default=None, ge=1, le=5)
    hedging_required: bool = False


class FalsificationCondition(BaseModel):
    """One falsification condition. ``specific_observable`` is required
    — the prompt's anti-pattern #1 is "vacuous falsification
    conditions" and the parser-side check enforces a minimum length."""

    model_config = ConfigDict(extra="forbid")

    condition: str
    specific_observable: str
    timeframe: Optional[str] = None


class ExecutionRisk(BaseModel):
    """One execution risk. ``severity_if_manifested`` is the
    four-value scale (no "none" — risks with no possible severity
    aren't risks)."""

    model_config = ConfigDict(extra="forbid")

    risk: str
    severity_if_manifested: ThesisRiskSeverity
    leading_indicator: Optional[str] = None


class ViolationJustification(BaseModel):
    """One {constraint, justification} record. Emitted when the
    synthesizer relaxes a soft constraint and the relaxation must be
    explicitly defensible."""

    model_config = ConfigDict(extra="forbid")

    constraint: str
    justification: str


class ConstraintCompliance(BaseModel):
    """The synthesizer's reported compliance against the
    parameter_extractor's constraints. The constraint loop machinery
    (Sprint 7 day 3) compares this against its own evaluation —
    a synthesizer that claims ``hard_constraints_satisfied=True``
    while the evaluator finds hard violations is caught at loop
    time."""

    model_config = ConfigDict(extra="forbid")

    hard_constraints_satisfied: bool
    soft_constraints_violated: list[str] = Field(default_factory=list)
    violations_justified: list[ViolationJustification] = Field(default_factory=list)


class ReasoningPathUsed(BaseModel):
    """One deduplicated substrate path the thesis components drew on.
    ``support_summary`` must be ≥20 characters — the upstream prompt's
    explicit minimum so "supports the thesis" doesn't survive
    validation."""

    model_config = ConfigDict(extra="forbid")

    path_node_ids: list[str]
    path_edge_ids: list[str] = Field(default_factory=list)
    support_summary: str = Field(min_length=20)


class SynthesizeDeliveredPayload(_PayloadBase):
    """Emitted by the synthesizer bridge once a parsed + validated
    thesis lands AND the constraint loop has terminated. Carries the
    canonical thesis shape. The ``constraint_loop_status`` field is
    the loop's terminal verdict (single_pass / passed / regressed /
    max_iterations_reached). Iteration count is the number of
    synthesizer dispatches inside the loop (1 = no revision)."""

    action_type: Literal[ActionType.SYNTHESIZE_DELIVERED] = ActionType.SYNTHESIZE_DELIVERED
    thesis_summary: str
    implicit_recommendation: SynthesisRecommendation
    thesis_components: list[ThesisComponent] = Field(default_factory=list)
    falsification_conditions: list[FalsificationCondition] = Field(default_factory=list)
    execution_risks: list[ExecutionRisk] = Field(default_factory=list)
    constraint_compliance: ConstraintCompliance
    reasoning_paths_used: list[ReasoningPathUsed] = Field(default_factory=list)
    conviction_level: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    # Loop-machinery surface lifted onto the Delivered payload so
    # downstream consumers (archive, cohort) don't have to read both
    # this event AND CONSTRAINT_LOOP_RESOLVED to know the synthesis
    # converged.
    constraint_loop_status: ConstraintLoopStatus = "single_pass"
    constraint_loop_iterations: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Audit findings (Sprint 8 day 2 — orchestration/audit/).
#
# Emitted by audit functions when a structural gap is detected on the
# phase log, skill files, or trajectory. ``severity`` lets dashboards
# filter critical-only; ``category`` is a freeform short tag (e.g.
# "missing_phase", "unverified_phase", "skill_stagnation").
# ---------------------------------------------------------------------------


AuditSeverity = Literal["info", "warning", "critical"]


class AuditFindingPayload(_PayloadBase):
    """One audit finding. Optional ``target_phase`` + ``target_path``
    pinpoint the artifact the finding concerns; ``evidence`` is the
    diagnostic string the operator reads when triaging."""

    action_type: Literal[ActionType.AUDIT_FINDING_EMITTED] = ActionType.AUDIT_FINDING_EMITTED
    category: str
    severity: AuditSeverity
    description: str
    evidence: str
    target_phase: Optional[int] = Field(default=None, ge=1, le=9)
    target_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Loop 1 orchestrator lifecycle payloads (Sprint 8 day 3).
#
# These payloads frame the whole investigation. ``Start`` is what an
# operator (REST endpoint, CLI, scheduled job) posts to kick off a
# cold question; the orchestrator drives the 9-phase sequence and
# emits ``Completed`` (or ``Failed``) when the run terminates. Both
# terminal events carry the verdict + a pointer to the canonical
# artifact (MASTER.md path) so dashboards don't need to re-query the
# trajectory to learn what happened.
# ---------------------------------------------------------------------------


class InvestigationStartRequestedPayload(_PayloadBase):
    """Cold-question entry point. The orchestrator subscribes to this
    action_type and spawns a per-investigation coroutine that walks
    phases 1-9. ``topic_slug`` (if supplied) is used for the MASTER.md
    output path; ``context`` is optional domain framing the
    Decomposer reads.

    Sprint 11 adds ``parent_investigation_id`` + ``spawn_context`` for
    the web app's highlight-to-chase mechanic. Both are metadata-only;
    the orchestrator doesn't change behavior based on them, but the
    web app uses them to render the chase tree and ChaseSlideOver pulls
    ``spawn_context`` as the highlighted-text-from-parent."""

    action_type: Literal[ActionType.INVESTIGATION_START_REQUESTED] = (
        ActionType.INVESTIGATION_START_REQUESTED
    )
    question: str
    context: str = ""
    topic_slug: Optional[str] = None
    # Cap on parallel evidence_retrieve dispatches (one per sub-question
    # from the Decomposer). The orchestrator clamps to this max; the
    # actual count is min(decomposition_length, max_sub_questions).
    max_sub_questions: int = Field(default=8, ge=1, le=20)
    # Sprint 11: parent investigation lineage for chase-spawned children.
    parent_investigation_id: Optional[str] = None
    spawn_context: Optional[str] = None  # highlighted text from parent's synthesis
    # Sprint 12: continuous chase mode. When chase_mode != "off", the
    # orchestrator re-enters phase 1 with the strongest open question
    # from current evidentiary_gaps as a new spawned sub-investigation
    # until the stop condition is met. Defaults to single-shot.
    chase_mode: Literal["off", "depth", "duration"] = "off"
    chase_value: int = Field(default=0, ge=0)
    # Hard budget cap in USD across the chase tree. Defaults to $2.
    chase_budget_usd: float = Field(default=2.0, ge=0.0)


class InvestigationChaseHaltedPayload(_PayloadBase):
    """Emitted when the orchestrator decides not to spawn a child
    investigation despite chase_mode != "off". The reason field tells
    the operator (and the UI) why the chase chain stopped here.

    Sprint 12 — first interpretation of continuous mode. The full
    daemon model (cross-investigation pollination) lands in Sprint
    14+ per master-product-spec section 7.3."""

    action_type: Literal[ActionType.INVESTIGATION_CHASE_HALTED] = (
        ActionType.INVESTIGATION_CHASE_HALTED
    )
    reason: Literal[
        "depth_reached",
        "duration_reached",
        "budget_exceeded",
        "no_open_questions",
        "chase_disabled",
    ]
    depth_reached: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    cost_total_usd: float = Field(default=0.0, ge=0.0)


class InvestigationSpawnedFromPayload(_PayloadBase):
    """Emitted when a new investigation is spawned from a parent's
    synthesis via the web app's chase-this mechanic. Carries the
    parent_investigation_id, the parent_event_id (typically the
    parent's synthesis.delivered event), and the highlighted text the
    operator was chasing.

    The substrate doesn't act on this event; it's UI metadata. The
    web app's useInvestigationTree hook reads these events to render
    the chase tree (migrating off localStorage once the substrate
    consumer is wired)."""

    action_type: Literal[ActionType.INVESTIGATION_SPAWNED_FROM] = (
        ActionType.INVESTIGATION_SPAWNED_FROM
    )
    parent_investigation_id: str
    parent_event_id: Optional[str] = None
    spawn_context: str = ""


class PageAttributionComputedPayload(_PayloadBase):
    """Sprint 16 — emitted per synthesis-attribution computation.

    ``algorithm_shares`` is the full three-algorithm map; each value
    is itself a ``{document_id: share}`` dict where shares sum to 1.0
    (subject to float rounding). ``algorithm`` key is one of "A",
    "B", "C" matching master spec §9.3.

    Phase 1 (this sprint): telemetry only. No payouts triggered by
    this event. The phase-2 payout job reads these events to decide
    splits — but that pipeline isn't wired yet."""

    action_type: Literal[ActionType.PAGE_ATTRIBUTION_COMPUTED] = (
        ActionType.PAGE_ATTRIBUTION_COMPUTED
    )
    synthesis_id: str
    algorithm_shares: dict[str, dict[str, float]] = Field(default_factory=dict)
    claim_count: int = Field(default=0, ge=0)
    document_count: int = Field(default=0, ge=0)


class ClaimAssertedByOperatorPayload(_PayloadBase):
    """Sprint 15 — emitted when the operator's edit to creative_writer's
    output is promoted to a first-class graph claim. Master spec §10.4
    Option B.

    The original generated prose and the operator's edit are both
    preserved so the audit trail captures the delta. ``claim_text`` is
    canonically the operator's text; ``original_text`` is the
    creative_writer output it replaced. ``source_tier`` defaults to 5
    (unsupported) unless the operator manually attaches chunk
    citations — at which point the substrate's grounder can verify it
    and downgrade the tier.

    ``node_id`` is the graph node row the claim was promoted to. The
    web app uses this to surface the claim under its origin
    deliverable + section in future search."""

    action_type: Literal[ActionType.CLAIM_ASSERTED_BY_OPERATOR] = (
        ActionType.CLAIM_ASSERTED_BY_OPERATOR
    )
    deliverable_id: str
    section_id: str
    claim_text: str
    original_text: Optional[str] = None
    node_id: Optional[str] = None
    source_tier: int = Field(default=5, ge=1, le=5)
    operator_id: str = "__operator__"
    cited_chunk_ids: list[str] = Field(default_factory=list)


class InvestigationCompletedPayload(_PayloadBase):
    """Terminal lifecycle event when Loop 1 converged cleanly. Carries
    the synthesis verdict + the constraint-loop verdict so a single
    event suffices to report outcome to a dashboard."""

    action_type: Literal[ActionType.INVESTIGATION_COMPLETED] = (
        ActionType.INVESTIGATION_COMPLETED
    )
    thesis_summary: str
    implicit_recommendation: SynthesisRecommendation
    constraint_loop_status: ConstraintLoopStatus
    constraint_loop_iterations: int = Field(default=1, ge=1)
    master_md_path: Optional[str] = None
    domains_patched: list[str] = Field(default_factory=list)
    total_phases_verified: int = Field(default=0, ge=0, le=9)


class InvestigationFailedPayload(_PayloadBase):
    """Terminal lifecycle event when Loop 1 aborted before
    completion. ``phase`` identifies which phase failed; ``reason``
    is the diagnostic string (postcondition failure message, exception
    repr, etc.)."""

    action_type: Literal[ActionType.INVESTIGATION_FAILED] = (
        ActionType.INVESTIGATION_FAILED
    )
    phase: int = Field(ge=1, le=9)
    reason: str
    last_completed_phase: Optional[int] = Field(default=None, ge=1, le=9)


# ---------------------------------------------------------------------------
# Parameter Extractor payloads (Sprint 7 day 2 — third orchestrate.py
# role bridge). The Delivered payload carries BOTH the raw parameters
# (the role's literal output, preserved for the trajectory) AND the
# derived ConstraintSpec list (the shape the Sprint 4 day 3-4
# constraint-loop machinery consumes). The Day 3 constraint-loop
# wiring reads ``constraints`` from this payload directly — no
# adapter layer between role output and loop input.
# ---------------------------------------------------------------------------


MetricValueType = Literal["scalar", "range", "categorical", "null"]
EvidenceStatus = Literal["observed", "imputed"]


class MetricValue(BaseModel):
    """Structured value attached to a Parameter. ``value_type`` is the
    discriminator; ``value`` and ``unit`` are present only for the
    numeric / categorical shapes.

    The upstream "JSON null vs literal-string 'null'" rule (parser
    normalizes both to the literal ``"null"``) is enforced one layer
    higher in ``roles/parameter_extractor/parser.py`` — by the time a
    ``MetricValue`` reaches this Pydantic model, ``value_type`` is
    always a Literal string."""

    model_config = ConfigDict(extra="forbid")

    value_type: MetricValueType
    # value is heterogeneous: number | list[number] | string | list[string]
    # | None. The role-side parser narrows + validates by ``value_type``;
    # the typed payload keeps ``Any`` so the trajectory round-trips
    # losslessly.
    value: Optional[Any] = None
    # ``unit`` MUST be either a non-empty string OR null/absent. The
    # upstream prompt forbids the empty-string sentinel — parser-side
    # check raises before we get here.
    unit: Optional[str] = None


class Parameter(BaseModel):
    """One design-critical parameter extracted from the evidence.
    Mirrors the role's output schema verbatim — ``source_chunk_ids``
    is a required list (the cite-every-claim discipline)."""

    model_config = ConfigDict(extra="forbid")

    semantic_anchor: str
    metric_value: MetricValue
    qualitative_descriptor: Optional[str] = None
    evidence_status: EvidenceStatus
    source_chunk_ids: list[str] = Field(default_factory=list)
    constraint_strictness: ConstraintStrictness


class ConstraintSpec(BaseModel):
    """Pydantic mirror of the Sprint 4 day 3-4 ``Constraint`` dataclass.

    Named ``ConstraintSpec`` (not ``Constraint``) to avoid naming
    collision with the dataclass that's already exported from
    ``middleware/constraint_check/constraints.py``. The bridge handler
    converts ``Parameter`` → ``ConstraintSpec`` at emit time via
    ``roles.parameter_extractor.parameters_to_constraints``; the
    Day 3 constraint-loop machinery reads ``ConstraintSpec`` records
    from the typed trajectory and reconstructs ``Constraint``
    dataclasses on the read side."""

    model_config = ConfigDict(extra="forbid")

    constraint_id: str
    strictness: ConstraintStrictness
    kind: ConstraintKind
    description: str
    config: dict[str, Any] = Field(default_factory=dict)


class SynthesizeRequestedPayload(_PayloadBase):
    """Emitted by the orchestrator after the four upstream roles
    (decomposer, evidence_retriever, parameter_extractor, connector)
    have all delivered. Carries the five pre-rendered prompt blocks
    verbatim so the role's input is fully reconstructable from the
    trajectory.

    Definition order note: this payload sits AFTER ``ConstraintSpec``
    so its ``constraints: list[ConstraintSpec]`` field resolves at
    annotation-read time. Codegen reads ``__annotations__`` directly
    and can't resolve forward-string references.
    """

    action_type: Literal[ActionType.SYNTHESIZE_REQUESTED] = ActionType.SYNTHESIZE_REQUESTED
    question: str
    decomposition_block: str
    evidence_block: str
    parameters_block: str
    substrate_block: str
    # Pre-derived ConstraintSpec list — the constraint loop reads
    # these directly to gate the synthesizer's output. Empty list ⇒
    # ``single_pass`` loop terminus.
    constraints: list[ConstraintSpec] = Field(default_factory=list)


class ParameterExtractRequestedPayload(_PayloadBase):
    """Emitted by upstream callers (orchestrator after evidence
    retrieval finishes) to request a Parameter Extractor dispatch.
    ``evidence_block`` is the pre-rendered JSON-stringified list of
    Evidence Retriever outputs, one block per sub-question."""

    action_type: Literal[ActionType.PARAMETER_EXTRACT_REQUESTED] = (
        ActionType.PARAMETER_EXTRACT_REQUESTED
    )
    evidence_block: str


class ParameterExtractDeliveredPayload(_PayloadBase):
    """Emitted by the Parameter Extractor bridge once a parsed +
    validated response lands.

    Two fields:
    - ``parameters`` — the role's literal output, preserved verbatim
      so RL trajectory mining can score the raw extraction.
    - ``constraints`` — the derived ``ConstraintSpec`` list the Day 3
      constraint-loop machinery consumes. Conversion happens at
      bridge emit time so the loop reads typed input directly from
      the trajectory.
    """

    action_type: Literal[ActionType.PARAMETER_EXTRACT_DELIVERED] = (
        ActionType.PARAMETER_EXTRACT_DELIVERED
    )
    parameters: list[Parameter] = Field(default_factory=list)
    constraints: list[ConstraintSpec] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Evidence Retriever payloads (Sprint 7 day 1 — second orchestrate.py
# role bridge). Closed taxonomies mirror
# ``roles/evidence_retriever/parser.py`` verbatim; drift between them
# is caught by ``tests/test_roles_evidence_retriever_extraction.py``.
# ---------------------------------------------------------------------------


EvidenceType = Literal["direct", "inferred", "gap"]
EvidenceConfidence = Literal["high", "moderate", "low", "insufficient"]


class SupportingClaim(BaseModel):
    """One evidence-cited claim produced by the Evidence Retriever.

    ``source_tier_min`` is optional — ``None`` is the spec sentinel for
    "below the schema floor"; ``0`` is REJECTED (the upstream prompt's
    explicit prohibition). Valid integer range is [1, 5]."""

    model_config = ConfigDict(extra="forbid")

    claim: str
    evidence_type: EvidenceType
    chunk_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    source_tier_min: Optional[int] = Field(default=None, ge=1, le=5)
    confidence: EvidenceConfidence
    confidence_basis: str


class EvidentiaryGap(BaseModel):
    """One enumerated gap. Gaps are first-class output — the prompt
    explicitly treats absent answers as information, not failure."""

    model_config = ConfigDict(extra="forbid")

    gap_description: str
    additional_retrieval_suggested: Optional[str] = None


class EvidenceRetrieveRequestedPayload(_PayloadBase):
    """Emitted by upstream callers (Decomposer downstream, manual
    invocation, batch backfill) to request an Evidence Retriever
    dispatch. The bridge subscribes to this action_type, dispatches
    the role at the flash tier, and emits
    ``EVIDENCE_RETRIEVE_DELIVERED`` when done.

    ``chunks_block`` and ``subgraph_block`` are the **rendered**
    context strings the bridge upstream produced from its retrieval
    layer — they ride inside the request so the role's input is fully
    reconstructable from the trajectory (no opaque DB lookup needed
    at replay time)."""

    action_type: Literal[ActionType.EVIDENCE_RETRIEVE_REQUESTED] = (
        ActionType.EVIDENCE_RETRIEVE_REQUESTED
    )
    sub_question: str
    category: SubQuestionCategory
    evidence_type_required: EvidenceTypeRequired
    top_k: int = Field(default=5, ge=0)
    chunks_block: str
    subgraph_block: str


class EvidenceRetrieveDeliveredPayload(_PayloadBase):
    """Emitted by the Evidence Retriever bridge once a parsed +
    validated response lands. ``insufficient_evidence=True`` means
    the role explicitly declined to answer; the downstream
    constraint loop / synthesizer reads this flag before composing."""

    action_type: Literal[ActionType.EVIDENCE_RETRIEVE_DELIVERED] = (
        ActionType.EVIDENCE_RETRIEVE_DELIVERED
    )
    sub_question: str
    answer: str
    supporting_claims: list[SupportingClaim] = Field(default_factory=list)
    evidentiary_gaps: list[EvidentiaryGap] = Field(default_factory=list)
    insufficient_evidence: bool = False


# ---------------------------------------------------------------------------
# Domain-skill artifacts (Sprint 6 day 4-5)
#
# Four payloads that close the Phase 6→7→8 archival/distillation seam:
# MASTER.md write/skip telemetry from synthesis_to_master, and
# auto-patch (mechanical skill backfill) apply/skip from
# skills/domain/auto_patch.
# ---------------------------------------------------------------------------


class MasterMdWrittenPayload(_PayloadBase):
    """Emitted when ``synthesis_to_master.generate_master_md`` writes
    a fresh MASTER.md. ``byte_count`` is the on-disk size after the
    atomic write; ``topic_slug`` is the directory slug used (auto-
    derived from the synthesis's target_question when no override
    was passed)."""

    action_type: Literal[ActionType.MASTER_MD_WRITTEN] = ActionType.MASTER_MD_WRITTEN
    path: str
    synthesis_id: str
    byte_count: int = Field(ge=0)
    topic_slug: Optional[str] = None
    param_version: str


class MasterMdSkippedPayload(_PayloadBase):
    """Emitted when ``synthesis_to_master`` skips regeneration because
    a MASTER.md with the same synthesis_id marker already exists.
    ``reason`` is the closed enum string (currently always
    ``idempotent_match``; left as a free string for forward additivity)."""

    action_type: Literal[ActionType.MASTER_MD_SKIPPED] = ActionType.MASTER_MD_SKIPPED
    path: str
    synthesis_id: str
    byte_count: int = Field(ge=0)
    topic_slug: Optional[str] = None
    reason: str = "idempotent_match"


class AutoPatchAppliedPayload(_PayloadBase):
    """Emitted by ``skills/domain/auto_patch.patch_from_synthesis``
    after a per-synthesis patch lands. ``patched`` / ``skipped`` /
    ``errors`` mirror the upstream result dict shape so a backfill
    operator CLI can render the same summary the legacy
    skill_patcher prints."""

    action_type: Literal[ActionType.AUTO_PATCH_APPLIED] = ActionType.AUTO_PATCH_APPLIED
    synthesis_id: str
    matched_domains: list[str] = Field(default_factory=list)
    patched: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    # ``{"domain": "<name>", "error": "<repr>"}`` per-failure record.
    # Typed as ``dict[str, str]`` so codegen can emit a Record alias
    # — the upstream call site stringifies the exception via ``repr``.
    errors: list[dict[str, str]] = Field(default_factory=list)
    status: str  # patched | already_patched | failed | partial | no_match


class AutoPatchSkippedPayload(_PayloadBase):
    """Emitted when a synthesis matched a domain but its skill file
    already carries the synthesis_id marker. Distinct from
    ``MasterMdSkippedPayload`` because mechanical skill backfill is a
    separate seam from MASTER.md regeneration — both surface independent
    idempotency outcomes."""

    action_type: Literal[ActionType.AUTO_PATCH_SKIPPED] = ActionType.AUTO_PATCH_SKIPPED
    synthesis_id: str
    domain: str
    skill_path: str


# ---------------------------------------------------------------------------
# Phase log payloads (orchestration/phase_log/)
# ---------------------------------------------------------------------------


class PhaseEnterPayload(_PayloadBase):
    """Emitted when ``PhaseLog.enter(phase_id)`` is called. The
    envelope's ``phase`` field carries the phase id; the payload
    captures the per-enter breadcrumbs the orchestrator started
    attaching for Phase 8 (knowledge extraction)."""

    action_type: Literal[ActionType.PHASE_ENTER] = ActionType.PHASE_ENTER
    entered_at: str
    note: Optional[str] = None
    metadata_json: Optional[str] = None


class PhaseExitPayload(_PayloadBase):
    """Emitted when ``PhaseLog.exit(phase_id)`` is called. ``outputs_hash``
    is the SHA-256 hash of the phase's output artifacts (paths +
    contents), computed at exit time so re-runs are observable."""

    action_type: Literal[ActionType.PHASE_EXIT] = ActionType.PHASE_EXIT
    exited_at: str
    outputs_hash: Optional[str] = None


class PhaseVerifyPayload(_PayloadBase):
    """Emitted when ``PhaseLog.verify(phase_id, evidence=...)`` is called.
    ``verification_evidence`` is freeform — a path, a query result, an
    SHA-256, or a 1-line proof — stored verbatim so a reviewer can audit
    why ``verify()`` was called. Load-bearing for Phase 8: without a
    verify event the phase did not actually compound the knowledge graph."""

    action_type: Literal[ActionType.PHASE_VERIFY] = ActionType.PHASE_VERIFY
    verified_at: str
    verification_evidence: str


# ---------------------------------------------------------------------------
# Sprint 17-30+ additions (master-spec §11.6 + §13.5 + §13.7 + §13.9)
# ---------------------------------------------------------------------------


class RLMBridgeDecidedPayload(_PayloadBase):
    """Emitted by the RLM bridge on every document-load when the bridge
    weighs in (above-threshold → escalate or defer; below-threshold →
    skipped). Per master-spec §11.6 + rlm_integration_spec.md RLM-1.

    Carries the verdict + the ratification state at decision time so
    operators reading the trajectory can reconstruct WHY a long doc
    did or did not enter RLM mode at a given moment.
    """

    action_type: Literal[ActionType.RLM_BRIDGE_DECIDED] = ActionType.RLM_BRIDGE_DECIDED
    document_id_ref: str
    estimated_tokens: int = Field(ge=0)
    threshold_tokens: int = Field(ge=0)
    above_threshold: bool
    ratified: bool
    escalated: bool
    session_id: Optional[str] = None
    reason: Literal[
        "below_threshold",
        "deferred_pending_ratification",
        "escalated_to_rlm",
    ]


class QualityGateEvaluatedPayload(_PayloadBase):
    """Quality-gate verdict for §13.9 public-graph promotion of a
    notebook block. Carries the per-rubric pass/fail and the headline
    accept decision; downstream gates aggregate these into operator-
    visible counts on the Trust Center.
    """

    action_type: Literal[ActionType.QUALITY_GATE_EVALUATED] = (
        ActionType.QUALITY_GATE_EVALUATED
    )
    target_kind: Literal["notebook", "synthesis_page", "creator_note"]
    target_id: str
    accepted: bool
    verification_passed: bool
    voice_style_passed: bool
    source_tier_passed: bool
    em_dash_density: float = Field(ge=0.0)
    padding_phrase_count: int = Field(ge=0)
    sector_vocab_overlap: float = Field(ge=0.0, le=1.0)
    min_tier_cited: int = Field(ge=1, le=5)
    pct_tier_1_or_2: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class CrossGraphCitationRecordedPayload(_PayloadBase):
    """A citation from one user's investigation to another user's
    public note. Per master-spec §13.9 Phase 3 federation. The
    attribution pipeline reads these to route 70% of any attached ad
    revenue to the referenced user.
    """

    action_type: Literal[ActionType.CROSS_GRAPH_CITATION_RECORDED] = (
        ActionType.CROSS_GRAPH_CITATION_RECORDED
    )
    reference_id: str
    referencing_user_id: str
    referencing_investigation_id: str
    referenced_user_id: str
    referenced_note_id: str
    federated_substrate_id: Optional[str] = None


class RevShareDecidedPayload(_PayloadBase):
    """One revenue-routing decision arising from an ad impression.
    Mirrors ``substrate.ad_inventory.payout.RevShareDecision`` and is
    emitted once per decision (creator/publisher/platform). The
    daily-cap state is carried in ``capped_to_daily_limit`` so the
    operator can audit §9.7 enforcement from the event log alone.
    """

    action_type: Literal[ActionType.REV_SHARE_DECIDED] = ActionType.REV_SHARE_DECIDED
    decision_id: str
    impression_id: str
    kind: Literal["creator", "publisher", "platform"]
    recipient_ref: str
    amount_usd_cents: int = Field(ge=0)
    document_id_ref: Optional[str] = None
    requires_escrow: bool = False
    capped_to_daily_limit: bool = False


class SkillRulePromotedPayload(_PayloadBase):
    """Emitted by ``substrate/multi_user/skill_writer.py`` when a
    discovered skill rule clears the ``SkillRuleAccumulator`` promotion
    gate and lands in the shared substrate's ``skill_rules`` table.

    Carries the rule's content-addressed identifier, the cumulative DP
    ε spent across all contributing users (capped at §16.2's 10.0),
    the distinct-user count that triggered promotion, and the
    confidence tier the writer assigned. Contributing user IDs ride as
    a tuple so the attribution + audit paths can reconstruct
    provenance.
    """

    action_type: Literal[ActionType.SKILL_RULE_PROMOTED] = (
        ActionType.SKILL_RULE_PROMOTED
    )
    rule_id: str
    rule_text: str
    rule_kind: str
    domain: str
    distinct_user_count: int = Field(ge=1)
    total_epsilon_consumed: float = Field(ge=0.0, le=10.0)
    confidence: Literal["low", "moderate", "high"]
    contributing_user_ids: list[str] = Field(default_factory=list)


class PreferenceObservationRecordedPayload(_PayloadBase):
    """Emitted by the DP-aware preference learning stream every time
    a binary observation is randomized + recorded against a category's
    ε budget. Per master-spec §16.2: per-observation ε spend is
    recorded; the underlying TRUE value is never logged (local DP
    guarantee).
    """

    action_type: Literal[ActionType.PREFERENCE_OBSERVATION_RECORDED] = (
        ActionType.PREFERENCE_OBSERVATION_RECORDED
    )
    category: str
    noisy_value: bool
    per_obs_epsilon: float = Field(gt=0.0)
    cumulative_epsilon_spent: float = Field(ge=0.0)
    category_budget: float = Field(ge=0.0)
    user_id: str


# ── Sprint 18 — Exa/Browserbase substrate-only precursor ────────────
#
# Wedge 1 (discovery layer) and Wedge 2 (ingestion escalation) emit
# these. The wedges themselves are Sprint 18-19 work; this precursor
# only types the events so the wedge PRs land typed from day one.
# Spec: docs/integration_exa_browserbase.md §6.3, §7.3, §18.3.
#
# Discovery events are NOT graph-write events — they record what the
# discovery layer considered (proposed) and what the operator chose
# to promote (selected). The graph-write event (DocumentLoadedPayload)
# is still emitted exclusively by acquisition/urls/adapter.ingest_url.


DiscoveryProvider = Literal["exa", "operator"]
# Future providers (serpapi, tavily, perplexity, brave) extend the
# union here, not in payload fields. Keeping the discriminator narrow
# means a new provider is a one-line schema change rather than a
# free-form string.


DiscoveryDecision = Literal[
    "ingested",
    "rejected_by_legal_gate",
    "rejected_by_operator",
    "fetch_failed",
]


class DiscoveryProposedPayload(_PayloadBase):
    """A discovery-layer source (Wedge 1: Exa search) proposed a URL.

    The URL has NOT been ingested; this event is the audit trail of
    "what we considered." Promotion to ingestion is a separate event
    (DiscoverySelectedPayload). Per spec §6.8: discovery does NOT
    fetch, does NOT auto-ingest, does NOT bypass the legal gate.

    ``discovery_id`` is the stable handle for a proposal. The wedge
    mints it as ``"disc-{provider}-" + sha256(url+investigation_id)[:16]``.
    """

    action_type: Literal[ActionType.DISCOVERY_PROPOSED] = ActionType.DISCOVERY_PROPOSED
    discovery_id: str
    provider: DiscoveryProvider
    # The query that produced this proposal. For findSimilar-style
    # discovery, this is the originating URL.
    query: str
    url: str
    title: Optional[str] = None
    # ISO-8601 if the provider returned it; None otherwise. Not parsed
    # to datetime — providers diverge on format and we'd rather log
    # what was received than silently normalize.
    published_date: Optional[str] = None
    author: Optional[str] = None
    # Provider-supplied score. Opaque per spec §14.3 — recorded but
    # NOT used for ingestion gating. The operator decides what to
    # promote; the score is just one signal.
    relevance_score: Optional[float] = None
    # Heuristic suggestion from acquisition/search/exa/adapter.py
    # (research domain → 2, news allowlist → 3, default → 4). The
    # operator can override at ingestion time; this is a suggestion,
    # not an authority.
    suggested_tier: int = Field(ge=1, le=4)
    # Truncated preview of the provider's text snippet (≤300 chars).
    # NOT the substrate's grounding evidence — that requires ingestion
    # via acquisition/urls/adapter.ingest_url.
    text_snippet_preview: Optional[str] = Field(default=None, max_length=300)
    # Provider's own request id, for audit cross-reference.
    provider_response_id: Optional[str] = None
    # Per-call cost estimate in USD. Captured per spec §6.7 so
    # weekly_report.py can aggregate discovery-layer spend separately
    # from dispatch spend.
    cost_usd_estimate: Optional[float] = Field(default=None, ge=0.0)


class DiscoverySelectedPayload(_PayloadBase):
    """A previously-proposed discovery was promoted to ingestion (or
    explicitly refused). Ties the discovery_id to the resulting
    document_id when ingestion succeeded.

    ``document_id`` is None when the decision is anything other than
    ``"ingested"``. The legal-gate rejection path emits a Selected
    event with ``decision="rejected_by_legal_gate"`` and a None
    document_id so the audit trail records the refusal — the Sprint
    18 retrieval-time gate (master-spec §9) is enforced upstream of
    this event, not by this event.

    Per spec §6.9: this event only fires once per (discovery_id,
    decision) pair. Re-promoting an already-ingested discovery is
    idempotent at the URL adapter level (url_doc_id deduplicates);
    the second Selected event is suppressed by the caller, not by
    the payload schema.
    """

    action_type: Literal[ActionType.DISCOVERY_SELECTED] = ActionType.DISCOVERY_SELECTED
    discovery_id: str
    document_id: Optional[str] = None
    decision: DiscoveryDecision
    # Free-text detail when decision != "ingested". Required only by
    # convention; the schema allows None so an "ingested" event
    # doesn't carry dead weight.
    rejection_reason: Optional[str] = None


class FetchFallbackEscalatedPayload(_PayloadBase):
    """Wedge 2 escalation event. Emitted by acquisition/urls/adapter.py
    when the httpx primary fetch returned ``low_word_count`` and the
    caller opted into a heavier fetcher (currently Browserbase).

    Per spec §7.2: the URL adapter still owns DocumentLoadedPayload
    emission; this event sits alongside, recording the escalation
    itself. Per spec §7.4: this is escalation, NOT default — the
    1000-5000× cost ratio against httpx is the load-bearing reason
    Browserbase is never the primary fetcher.

    ``primary_word_count`` and ``fallback_word_count`` let the
    trajectory show whether the escalation recovered usable content
    (fallback > primary) or hit a paywall/captcha (fallback ≈ primary).
    """

    action_type: Literal[ActionType.FETCH_FALLBACK_ESCALATED] = (
        ActionType.FETCH_FALLBACK_ESCALATED
    )
    url: str
    primary_fetcher: Literal["httpx"] = "httpx"
    primary_word_count: int = Field(ge=0)
    fallback_fetcher: Literal["browserbase"]
    fallback_word_count: int = Field(ge=0)
    escalation_reason: Literal[
        "low_word_count",
        "operator_override",
        "js_detect",
    ]
    # Per-session cost estimate in USD. Captured so the weekly report
    # can flag runaway escalation early (the per-page cost is 50-5000×
    # an httpx fetch — see spec §13.1).
    estimated_cost_usd: float = Field(ge=0.0)


# ---------------------------------------------------------------------------
# Discriminated union over typed payloads
# ---------------------------------------------------------------------------


TypedPayload = Annotated[
    Union[
        DispatchCallPayload,
        ContextPackAssembledPayload,
        DocumentLoadedPayload,
        DocumentRegionSelectedPayload,
        DistillationRequestedPayload,
        DistillationDeliveredPayload,
        ClaimChallengeRaisedPayload,
        ClaimGroundingCheckPassedPayload,
        ClaimGroundingCheckFailedPayload,
        NoteEmergedPayload,
        NoteRefinedPayload,
        NoteCompressedDocWrittenPayload,
        QuestionIdentifiedPayload,
        QuestionEscalatedToResearchPayload,
        QuestionResolvedByDocPayload,
        CrossDocQuestionAnsweredPayload,
        UserAcceptDistillationPayload,
        UserRejectDistillationPayload,
        UserEditDistillationPayload,
        ArtifactGeneratedPayload,
        ArtifactInteractedPayload,
        TierAssignedPayload,
        TierOverriddenPayload,
        TierRewriteBulkPayload,
        StalenessFlaggedPayload,
        StalenessResolvePayload,
        SynthesisArchivedPayload,
        SubstrateManifestWrittenPayload,
        SupersessionApplyPayload,
        SupersessionDismissPayload,
        SupersessionCoexistPayload,
        GraphNodeInsertedPayload,
        GraphEdgeInsertedPayload,
        ConstraintViolationFoundPayload,
        ConstraintRevisionTriggeredPayload,
        ConstraintLoopResolvedPayload,
        OutcomeRecordedPayload,
        RubricScoredPayload,
        PhaseEnterPayload,
        PhaseExitPayload,
        PhaseVerifyPayload,
        DecomposeQuestionRequestedPayload,
        DecomposeQuestionDeliveredPayload,
        DecomposerParaphraseFlaggedPayload,
        DecomposerRegeneratedPayload,
        MasterMdWrittenPayload,
        MasterMdSkippedPayload,
        AutoPatchAppliedPayload,
        AutoPatchSkippedPayload,
        EvidenceRetrieveRequestedPayload,
        EvidenceRetrieveDeliveredPayload,
        ParameterExtractRequestedPayload,
        ParameterExtractDeliveredPayload,
        ConnectorRequestedPayload,
        ConnectorDeliveredPayload,
        SynthesizeRequestedPayload,
        SynthesizeDeliveredPayload,
        AuditFindingPayload,
        InvestigationStartRequestedPayload,
        InvestigationCompletedPayload,
        InvestigationFailedPayload,
        InvestigationSpawnedFromPayload,
        InvestigationChaseHaltedPayload,
        ClaimAssertedByOperatorPayload,
        PageAttributionComputedPayload,
        RLMBridgeDecidedPayload,
        QualityGateEvaluatedPayload,
        CrossGraphCitationRecordedPayload,
        RevShareDecidedPayload,
        PreferenceObservationRecordedPayload,
        SkillRulePromotedPayload,
        DiscoveryProposedPayload,
        DiscoverySelectedPayload,
        FetchFallbackEscalatedPayload,
    ],
    Field(discriminator="action_type"),
]


# Action types currently covered by the typed union. Read-side
# reconstruction switches on this set: typed if member, dict otherwise.
TYPED_PAYLOAD_ACTION_TYPES: frozenset[str] = frozenset({
    ActionType.DISPATCH_CALL.value,
    ActionType.CONTEXT_PACK_ASSEMBLED.value,
    ActionType.DOCUMENT_LOADED.value,
    ActionType.DOCUMENT_REGION_SELECTED.value,
    ActionType.DISTILLATION_REQUESTED.value,
    ActionType.DISTILLATION_DELIVERED.value,
    ActionType.CLAIM_CHALLENGE_RAISED.value,
    ActionType.CLAIM_GROUNDING_CHECK_PASSED.value,
    ActionType.CLAIM_GROUNDING_CHECK_FAILED.value,
    ActionType.NOTE_EMERGED.value,
    ActionType.NOTE_REFINED.value,
    ActionType.NOTE_COMPRESSED_DOC_WRITTEN.value,
    ActionType.QUESTION_IDENTIFIED.value,
    ActionType.QUESTION_ESCALATED_TO_RESEARCH.value,
    ActionType.QUESTION_RESOLVED_BY_DOC.value,
    ActionType.CROSS_DOC_QUESTION_ANSWERED.value,
    ActionType.USER_ACCEPT_DISTILLATION.value,
    ActionType.USER_REJECT_DISTILLATION.value,
    ActionType.USER_EDIT_DISTILLATION.value,
    ActionType.ARTIFACT_GENERATED.value,
    ActionType.ARTIFACT_INTERACTED.value,
    ActionType.GRAPH_TIER_ASSIGNED.value,
    ActionType.GRAPH_TIER_OVERRIDDEN.value,
    ActionType.TIER_REWRITE_BULK.value,
    ActionType.GRAPH_STALENESS_FLAGGED.value,
    ActionType.STALENESS_RESOLVE.value,
    ActionType.SYNTHESIS_ARCHIVED.value,
    ActionType.SUBSTRATE_MANIFEST_WRITTEN.value,
    ActionType.SUPERSESSION_APPLY.value,
    ActionType.SUPERSESSION_DISMISS.value,
    ActionType.SUPERSESSION_COEXIST.value,
    ActionType.GRAPH_NODE_INSERTED.value,
    ActionType.GRAPH_EDGE_INSERTED.value,
    ActionType.CONSTRAINT_VIOLATION_FOUND.value,
    ActionType.CONSTRAINT_REVISION_TRIGGERED.value,
    ActionType.CONSTRAINT_LOOP_RESOLVED.value,
    ActionType.OUTCOME_RECORDED.value,
    ActionType.RUBRIC_SCORED.value,
    ActionType.PHASE_ENTER.value,
    ActionType.PHASE_EXIT.value,
    ActionType.PHASE_VERIFY.value,
    ActionType.DECOMPOSE_QUESTION_REQUESTED.value,
    ActionType.DECOMPOSE_QUESTION_DELIVERED.value,
    ActionType.DECOMPOSER_PARAPHRASE_FLAGGED.value,
    ActionType.DECOMPOSER_REGENERATED.value,
    ActionType.MASTER_MD_WRITTEN.value,
    ActionType.MASTER_MD_SKIPPED.value,
    ActionType.AUTO_PATCH_APPLIED.value,
    ActionType.AUTO_PATCH_SKIPPED.value,
    ActionType.EVIDENCE_RETRIEVE_REQUESTED.value,
    ActionType.EVIDENCE_RETRIEVE_DELIVERED.value,
    ActionType.PARAMETER_EXTRACT_REQUESTED.value,
    ActionType.PARAMETER_EXTRACT_DELIVERED.value,
    ActionType.CONNECTOR_REQUESTED.value,
    ActionType.CONNECTOR_DELIVERED.value,
    ActionType.SYNTHESIZE_REQUESTED.value,
    ActionType.SYNTHESIZE_DELIVERED.value,
    ActionType.AUDIT_FINDING_EMITTED.value,
    ActionType.INVESTIGATION_START_REQUESTED.value,
    ActionType.INVESTIGATION_COMPLETED.value,
    ActionType.INVESTIGATION_FAILED.value,
    ActionType.INVESTIGATION_SPAWNED_FROM.value,
    ActionType.INVESTIGATION_CHASE_HALTED.value,
    ActionType.CLAIM_ASSERTED_BY_OPERATOR.value,
    ActionType.PAGE_ATTRIBUTION_COMPUTED.value,
    ActionType.RLM_BRIDGE_DECIDED.value,
    ActionType.QUALITY_GATE_EVALUATED.value,
    ActionType.CROSS_GRAPH_CITATION_RECORDED.value,
    ActionType.REV_SHARE_DECIDED.value,
    ActionType.PREFERENCE_OBSERVATION_RECORDED.value,
    ActionType.SKILL_RULE_PROMOTED.value,
    # Sprint 18 — Exa/Browserbase substrate-only precursor.
    ActionType.DISCOVERY_PROPOSED.value,
    ActionType.DISCOVERY_SELECTED.value,
    ActionType.FETCH_FALLBACK_ESCALATED.value,
})


# Wrestling action types that REQUIRE document_id on the Event envelope.
# Enforced by the Event model_validator below.
WRESTLING_ACTION_TYPES: frozenset[str] = frozenset({
    ActionType.DOCUMENT_LOADED.value,
    ActionType.DOCUMENT_REGION_SELECTED.value,
    ActionType.DISTILLATION_REQUESTED.value,
    ActionType.DISTILLATION_DELIVERED.value,
    ActionType.CLAIM_CHALLENGE_RAISED.value,
    ActionType.CLAIM_GROUNDING_CHECK_PASSED.value,
    ActionType.CLAIM_GROUNDING_CHECK_FAILED.value,
    ActionType.NOTE_EMERGED.value,
    ActionType.NOTE_REFINED.value,
    ActionType.NOTE_COMPRESSED_DOC_WRITTEN.value,
    ActionType.QUESTION_IDENTIFIED.value,
    ActionType.QUESTION_ESCALATED_TO_RESEARCH.value,
    ActionType.QUESTION_RESOLVED_BY_DOC.value,
    ActionType.USER_ACCEPT_DISTILLATION.value,
    ActionType.USER_REJECT_DISTILLATION.value,
    ActionType.USER_EDIT_DISTILLATION.value,
    # CROSS_DOC_QUESTION_ANSWERED is NOT in this set — it spans two
    # documents, both of which live in the payload. The envelope's
    # document_id is left null for this variant.
})


# ---------------------------------------------------------------------------
# Event envelope
# ---------------------------------------------------------------------------


class Event(BaseModel):
    """The envelope around a typed payload. Written one row per JSONL line
    while live; sealed to Parquet at investigation completion.

    The top-level ``action_type`` is redundant with ``payload.action_type``
    but kept as a separate column for query efficiency — DuckDB filters on
    action_type without parsing the payload JSON. The model_validator
    asserts the two agree.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    event_id: str
    investigation_id: str
    synthesis_id: Optional[str] = None
    phase: Optional[int] = Field(default=None, ge=1, le=9)
    role: Optional[str] = None
    action_type: ActionType
    payload: TypedPayload
    parent_event_id: Optional[str] = None
    policy_id: str = DEFAULT_POLICY_ID
    param_version: str
    schema_version: int = EVENT_SCHEMA_VERSION
    emitted_at: datetime
    document_id: Optional[str] = None

    @model_validator(mode="after")
    def _check_action_type_matches_payload(self) -> "Event":
        # Compare against the string value rather than the enum member so
        # the check works whether action_type was passed as the enum or as
        # the underlying string (use_enum_values=True converts to str on
        # serialization but Pydantic stores the enum during validation).
        top = self.action_type.value if isinstance(self.action_type, ActionType) else str(self.action_type)
        pl = self.payload.action_type
        pl_str = pl.value if isinstance(pl, ActionType) else str(pl)
        if top != pl_str:
            raise ValueError(
                f"Event.action_type ({top!r}) does not match payload.action_type ({pl_str!r}). "
                "The envelope's action_type must equal the payload variant's discriminator."
            )
        return self

    @model_validator(mode="after")
    def _check_wrestling_requires_document_id(self) -> "Event":
        at = self.action_type.value if isinstance(self.action_type, ActionType) else str(self.action_type)
        if at in WRESTLING_ACTION_TYPES and not self.document_id:
            raise ValueError(
                f"Event with action_type {at!r} is a wrestling-loop event and requires "
                "document_id on the envelope. (architecture_notes.md §9.1)"
            )
        return self

    @field_serializer("emitted_at")
    def _serialize_emitted_at(self, v: datetime) -> str:
        # Match the legacy log_event format: ISO 8601 with 'Z' suffix.
        # Naive datetimes are treated as UTC (matches the legacy behavior).
        if v.tzinfo is None:
            return v.isoformat() + "Z"
        return v.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = [
    "ActionType",
    "EVENT_SCHEMA_VERSION",
    "DEFAULT_POLICY_ID",
    "TYPED_PAYLOAD_ACTION_TYPES",
    "WRESTLING_ACTION_TYPES",
    "TypedPayload",
    "Event",
    "ContextLayer",
    "Claim",
    "ConfidenceLevel",
    "ArtifactKind",
    # Dispatch + context pack
    "DispatchCallPayload",
    "ContextPackAssembledPayload",
    # Wrestling
    "DocumentLoadedPayload",
    "DocumentRegionSelectedPayload",
    "DistillationRequestedPayload",
    "DistillationDeliveredPayload",
    "ClaimChallengeRaisedPayload",
    "ClaimGroundingCheckPassedPayload",
    "ClaimGroundingCheckFailedPayload",
    "NoteEmergedPayload",
    "NoteRefinedPayload",
    "NoteCompressedDocWrittenPayload",
    "QuestionIdentifiedPayload",
    "QuestionEscalatedToResearchPayload",
    "QuestionResolvedByDocPayload",
    "CrossDocQuestionAnsweredPayload",
    "UserAcceptDistillationPayload",
    "UserRejectDistillationPayload",
    "UserEditDistillationPayload",
    # Artifacts (Layer 4)
    "ArtifactGeneratedPayload",
    "ArtifactInteractedPayload",
    # Middleware: source_tier
    "TierClassificationMethod",
    "TierAdjustmentMethod",
    "TierAssignedPayload",
    "TierOverriddenPayload",
    "TierRewriteBulkPayload",
    # Middleware: temporal
    "StalenessResolution",
    "StalenessFlaggedPayload",
    "StalenessResolvePayload",
    # Middleware: archive
    "SynthesisStatus",
    "SynthesisRecommendation",
    "SynthesisArchivedPayload",
    "SubstrateManifestWrittenPayload",
    # Middleware: supersession
    "SupersessionTarget",
    "SupersessionApplyPayload",
    "SupersessionDismissPayload",
    "SupersessionCoexistPayload",
    # Substrate: graph
    "NodeType",
    "GraphScope",
    "GraphNodeInsertedPayload",
    "GraphEdgeInsertedPayload",
    # Middleware: constraint_check
    "ConstraintStrictness",
    "ConstraintKind",
    "ConstraintLoopStatus",
    "ConstraintViolationFoundPayload",
    "ConstraintRevisionTriggeredPayload",
    "ConstraintLoopResolvedPayload",
    # Middleware: outcomes + cohort + backtest
    "ThesisOutcomeStatus",
    "ExecutionRiskSeverity",
    "DecisionRecommendation",
    "ActualDecision",
    "ProceedOutcome",
    "ThesisOutcome",
    "FalsificationOutcome",
    "ExecutionRiskOutcome",
    "DecisionAlignment",
    "OutcomeRecordedPayload",
    "RubricScoredPayload",
    # Orchestration: phase_log
    "PhaseEnterPayload",
    "PhaseExitPayload",
    "PhaseVerifyPayload",
    # Roles: decomposer
    "SubQuestionCategory",
    "EvidenceTypeRequired",
    "SubQuestion",
    "Keyword",
    "ParaphraseFlagRecord",
    "DecomposeQuestionRequestedPayload",
    "DecomposeQuestionDeliveredPayload",
    "DecomposerParaphraseFlaggedPayload",
    "DecomposerRegeneratedPayload",
    # Skills: domain (MASTER.md + auto-patch)
    "MasterMdWrittenPayload",
    "MasterMdSkippedPayload",
    "AutoPatchAppliedPayload",
    "AutoPatchSkippedPayload",
    # Roles: evidence_retriever
    "EvidenceType",
    "EvidenceConfidence",
    "SupportingClaim",
    "EvidentiaryGap",
    "EvidenceRetrieveRequestedPayload",
    "EvidenceRetrieveDeliveredPayload",
    # Roles: parameter_extractor
    "MetricValueType",
    "EvidenceStatus",
    "MetricValue",
    "Parameter",
    "ConstraintSpec",
    "ParameterExtractRequestedPayload",
    "ParameterExtractDeliveredPayload",
    # Roles: connector
    "TraversalAlgorithm",
    "KeywordMapping",
    "SeedPair",
    "GraphPath",
    "NaturalLanguageRelationship",
    "ConnectorRequestedPayload",
    "ConnectorDeliveredPayload",
    # Roles: synthesizer
    "ThesisRiskSeverity",
    "ThesisComponent",
    "FalsificationCondition",
    "ExecutionRisk",
    "ViolationJustification",
    "ConstraintCompliance",
    "ReasoningPathUsed",
    "SynthesizeRequestedPayload",
    "SynthesizeDeliveredPayload",
    # Audit
    "AuditSeverity",
    "AuditFindingPayload",
    # Loop 1 lifecycle
    "InvestigationStartRequestedPayload",
    "InvestigationCompletedPayload",
    "InvestigationFailedPayload",
    "InvestigationSpawnedFromPayload",
    "InvestigationChaseHaltedPayload",
    "ClaimAssertedByOperatorPayload",
    "PageAttributionComputedPayload",
    # Sprint 17-30+ additions (v4 schema bump)
    "RLMBridgeDecidedPayload",
    "QualityGateEvaluatedPayload",
    "CrossGraphCitationRecordedPayload",
    "RevShareDecidedPayload",
    "PreferenceObservationRecordedPayload",
    # Sprint 30+ addition (v5 schema bump)
    "SkillRulePromotedPayload",
    # Sprint 18 — Exa/Browserbase substrate-only precursor (v6 schema bump)
    "DiscoveryProvider",
    "DiscoveryDecision",
    "DiscoveryProposedPayload",
    "DiscoverySelectedPayload",
    "FetchFallbackEscalatedPayload",
]
