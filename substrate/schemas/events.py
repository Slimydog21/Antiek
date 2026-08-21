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
- Payload variants for the 20 currently-schemaed action types:
  - ``DispatchCallPayload`` (week 1 dependency — cost-tracking emits)
  - ``ContextPackAssembledPayload`` (week 1 dependency — pack provenance)
  - 17 wrestling payloads (locked at substrate time per
    ``architecture_notes.md`` §9.1 so Loop 2 trajectories are typed
    from the first event written)
  - ``BlockPositionPayload`` (Living Roadmap SPR-03 — DRW block-canvas
    position persistence as a typed event, single-writer funnel)
- A discriminated union over those 20 variants.
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

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

# ---------------------------------------------------------------------------
# ActionType — stable string vocabulary
# ---------------------------------------------------------------------------


class ActionType(str, Enum):  # noqa: UP042 - preserve established schema enum API.
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
    SKILL_PATCH_GATE_DECIDED = "skill.patch_gate_decided"
    SKILL_PATCH_GATE_REVIEWED = "skill.patch_gate_reviewed"
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
    # AFF SPR-06 — the flywheel's reuse half. Emitted once per investigation
    # start, recording which prior knowledge units were retrieved + injected
    # into the context pack (and which were dropped, and why).
    KNOWLEDGE_REUSED = "knowledge.reused"
    # AFF SPR-08 — the trust gate on reuse. Emitted ONCE per knowledge unit
    # EXCLUDED from reuse by the groundedness/servability gate (an admitted
    # unit emits no REUSE_GATED event). It records the unit's groundedness
    # score, the threshold in force, and the reason(s) it was excluded
    # (below-threshold and/or non-servable) so the loop can prove it does not
    # re-seed ungrounded or non-servable units into the next synthesis.
    REUSE_GATED = "reuse.gated"

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
    ARTIFACT_COMMENT_CREATED = "artifact.comment.created"
    FEEDBACK_THREAD_RESOLVED = "feedback.thread.resolved"
    AGENT_WORK_TRANSITIONED = "agent.work.transitioned"
    ARTIFACT_FEEDBACK_REPLIED = "artifact.feedback.replied"

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

    # ── Wedge 3 (Exa /contents corroboration, PHASE 2 client-side
    #    primitive). Recorded when the verifier tier (or any caller)
    #    consulted Exa for claim corroboration. NOT a graph-write
    #    event — the substrate-grounding invariant still requires
    #    every claim to trace to a chunk in an ingested document.
    #    Spec docs/integration_exa_browserbase.md §8.
    VERIFIER_LOOKUP = "verifier.lookup"

    # ── Sprint 30+ thread 1 — Federation audit trail (master-spec §13.9 +
    #    §13.7). Every partner-state transition + every cross-instance
    #    citation flow lands in the event log so the operator can audit
    #    federation posture from the trajectory alone. Inbound refusals
    #    are first-class events with a typed reason — silent drops are
    #    impossible.
    FEDERATION_PARTNER_REGISTERED = "federation.partner.registered"
    FEDERATION_PARTNER_TRUSTED = "federation.partner.trusted"
    FEDERATION_PARTNER_REVOKED = "federation.partner.revoked"
    FEDERATION_OUTBOUND_CITATION_EMITTED = "federation.outbound_citation.emitted"
    FEDERATION_INBOUND_CITATION_ACCEPTED = "federation.inbound_citation.accepted"
    FEDERATION_INBOUND_CITATION_REFUSED = "federation.inbound_citation.refused"

    # ── Sprint 30+ thread 4 — Visual role audit trail. The 13th
    #    substrate role; frame-level claim extraction. Three typed
    #    events: frame_identified (upstream selected a frame to
    #    process), claims_extracted (role produced VisualResult),
    #    role_failed (dispatch failed or parser refused output).
    VISUAL_FRAME_IDENTIFIED = "visual.frame_identified"
    VISUAL_CLAIMS_EXTRACTED = "visual.claims_extracted"
    VISUAL_ROLE_FAILED = "visual.role_failed"

    # ── PostHog Wedge 4 — Max-style AI sidecar audit trail (§5.5).
    #    Every AI-driven UI mutation emits ai.action.applied with
    #    enough payload to invert (target_kind + target_id + prev_state
    #    + next_state). The undo button reads the most recent applied
    #    event for the operator's session and emits ai.action.undone
    #    when the inverse is replayed via the substrate.
    AI_ACTION_APPLIED = "ai.action.applied"
    AI_ACTION_UNDONE = "ai.action.undone"

    # ── DP shuffler production routing audit trail (§13.3 +
    #    §16.2). Every telemetry signal that passes through the
    #    shuffler emits dp.routed so the Trust Center can publish a
    #    verifiable per-surface ε budget under §13.7.
    DP_ROUTED = "dp.routed"

    # ── Write workflow — outline composition (Write SPR-01). The
    #    OutlineBlock composition layer (substrate/write/) records every
    #    lego-block placement / move / removal in an outline so the
    #    authoring trajectory (Write SPR-02) can reconstruct the
    #    block-selection steps that precede a draft. These are
    #    composition edits over deliverable_sections — NOT graph-write
    #    events; the underlying insight/question/claim node is untouched
    #    (outlines and folders are views over nodes, per the spec moat).
    OUTLINE_BLOCK_PLACED = "outline_block.placed"
    OUTLINE_BLOCK_MOVED = "outline_block.moved"
    OUTLINE_BLOCK_REMOVED = "outline_block.removed"

    # ── Read workflow — servable-corpus legal gate (Read SPR-01;
    #    master-spec §9.0 / §9.10). Every change to a book's serving
    #    eligibility is an auditable event so a future maintainer (or
    #    counsel) can reconstruct exactly when and why a book was or
    #    wasn't served — the decision most needing to survive scrutiny.
    #    book.servability_changed records a content_class transition
    #    (e.g. gated → publisher_opted_in); book.taken_down records a
    #    removal demand being honoured (full text purged, retrieval
    #    restricted). These are gate-state events over documents +
    #    book_assets, NOT graph-write events.
    BOOK_SERVABILITY_CHANGED = "book.servability_changed"
    BOOK_TAKEN_DOWN = "book.taken_down"

    # ── Write workflow — edit capture (Write SPR-02). The editing-as-
    #    data thesis: the first draft is cheap, the real writing is the
    #    edit, and those last-mile edits are the highest-value signal —
    #    both for prompt-level style conditioning (SPR-09) now and for
    #    the GATED Loop-3 RL/SFT track later. edit.captured records one
    #    structured before/after edit at block/paragraph/sentence
    #    granularity. CAPTURE ≠ TRAINING: these events are written
    #    ungated; the training-bound harvest is hard-gated by
    #    unlock_gate (G8) and the reward stays None until post-unlock.
    EDIT_CAPTURED = "edit.captured"

    # ── Write workflow — draft provenance persistence (Write SPR-09). The
    #    X-ray view (paragraph → driving blocks) needs prose_provenance to
    #    survive the request that generated it. creative_writer returns a
    #    paragraph_index → [block_ids] map ephemerally; this event makes it
    #    durable. It is emitted ONLY after a live generation succeeds AND the
    #    voice gate passes, paired in the same single-writer context with the
    #    existing update_section_prose table write (mirrors patch_section_prose,
    #    Sprint 15). The link from generated paragraph → its blocks (then
    #    chunks → documents via resolve_provenance) thus EXISTS in the graph —
    #    a persisted event + a persisted row — not just on screen (§9 moat).
    #    This is a composition/audit event over deliverable_sections, NOT a
    #    graph-write: the underlying blocks/nodes are untouched.
    SECTION_DRAFT_GENERATED = "section.draft_generated"

    # ── Cross-workflow seams (antiek-unified SPR-03). Each typed seam
    #    handoff (substrate/seams/contracts.py) emits one of these when it
    #    fires. They carry the entity id + kind + provenance ref + the
    #    terminating-handoff marker — NEVER a copy of the entity. Six
    #    committed + one provisional (write→speak). These are handoff-audit
    #    events: they record that a workflow handed an entity (by reference)
    #    to another workflow; the underlying graph node / claim / document is
    #    untouched (the seam moves the reference, the products own the
    #    entity). No seam event carries a successor — the absence of any
    #    next-handoff field is the no-auto-loop invariant.
    SEAM_RESEARCH_TO_READ = "seam.research_to_read"
    SEAM_READ_TO_RESEARCH = "seam.read_to_research"
    SEAM_READ_TO_WRITE = "seam.read_to_write"
    SEAM_WRITE_TO_READ = "seam.write_to_read"
    SEAM_SPEAK_TO_WRITE = "seam.speak_to_write"
    SEAM_SPEAK_TO_READ = "seam.speak_to_read"
    # Provisional — write→speak. Typed so the trajectory can carry it if the
    # operator exercises it, but the seam is off the SPR-08 critical path.
    SEAM_WRITE_TO_SPEAK = "seam.write_to_speak"

    # ── Voice infrastructure (Living Roadmap SPR-14). The shared
    #    capture+transcribe hook (apps/reading/src/hooks/useVoiceCapture.ts)
    #    persists each spoken capture as ONE typed event through the
    #    single-writer funnel — the audio blob rides by reference
    #    (``audio_ref``), never a client side-store. The defining field is
    #    ``source_kind="user"``: voice-IN is ALWAYS human-authored and is the
    #    §9 reason it can never be conflated with model output. This is the
    #    capture-provenance event; downstream distillation
    #    (substrate/books/voice_note → note.emerged) is unchanged.
    VOICE_CAPTURED = "voice.captured"

    # ── Block-canvas position persistence (Living Roadmap SPR-03). The DRW
    #    "organism" canvas renders insight/question graph nodes as draggable
    #    blocks; each drag-end appends ONE block.positioned event recording the
    #    node's (x, y) in the canvas's free 2D coordinate space, scoped to the
    #    investigation by the Event envelope. This is pure view-state, NOT a §9
    #    claim — it rides the SAME single-writer typed-event funnel as every
    #    other state mutation because the frontend has no other sanctioned
    #    writer (a localStorage side-store would diverge from the graph). The
    #    canvas re-derives positions by replaying these events (latest per
    #    node_id wins); the optional region_id carries M4 theme grouping.
    BLOCK_POSITIONED = "block.positioned"

    # ── Highlight → float-menu NOTE (Living Roadmap SPR-04 M2). A reader
    #    selects text on ANY surface (Research synthesis, a DRW block detail,
    #    later a book/draft) and chooses "Note" in the shared float-menu; the
    #    selection becomes a user-authored marginalia note. It rides the SAME
    #    single-writer funnel as every other state mutation. Like voice.captured
    #    it is a §9 provenance-LOAD-BEARING event: source_kind is pinned to the
    #    literal "user" (a marginalia note is human-authored, NEVER model output)
    #    so it can never be conflated with a model reply node in the one graph.
    #    It carries the selection's provenance (document_id on the envelope +
    #    the chunk_id where the selection lands) so the note chains
    #    claim→chunk→document like every other claim. The excerpt is the user's
    #    OWN selected text (what they highlighted), not retrieved body — so it is
    #    not a §9.0-withheld-content concern (the reader is reading their own
    #    selection); the no-leak guard governs the SEARCH/DEEP-RESEARCH outbound
    #    payloads, not this note of one's own reading.
    MARGINALIA_NOTED = "marginalia.noted"

    # ── Source read → SiteSee "read" tint (Living Roadmap SPR-07 M4). When a
    #    reader DWELLS on a source long enough to count as "read" (the
    #    dwell-threshold rule is justified in
    #    docs/decisions/spr-06-source-read-event-gap.md), the reading surface
    #    emits ONE source.read event per source per reading session through the
    #    single-writer funnel — the SAME funnel as every other state mutation,
    #    so SiteSee's per-source read history is substrate-derived (PR-2/PR-6),
    #    never a client side-store. It is the net-new signal the SPR-06 gap doc
    #    filed: cited/saved were already substrate-derived, "read" was not. The
    #    event carries NO body (§9.0): only the document_id (on the Event
    #    envelope) + the chunk the read was attributed to + the dwell evidence
    #    that justified the "read" verdict (so a maintainer can see WHY this
    #    counted as read). It is NOT a §9 provenance claim about the world — it
    #    asserts the reader's own reading history, like a "saved" signal — so it
    #    carries no source_kind/grounding fields. SiteSee READS the resolved
    #    history; it emits nothing and opens no writer of its own.
    SOURCE_READ = "source.read"
    READ_BOOK_ANSWERED = "read.book_answered"
    READ_BOOK_ANSWER_JUDGED = "read.book_answer_judged"

    # ── Meta-reading deliverable (Living Roadmap SPR-08 M4). A one-shot,
    #    READ-ONLY, page-cited synthesis over the reader's OWNED corpus, saved
    #    as a re-openable Read asset. WHY AN EVENT, NOT A CLIENT SIDE-STORE:
    #    the deliverable is substrate truth — it must survive reload, be
    #    re-opened, narrated, and (only on explicit user action) promoted into
    #    a Research investigation via the existing seam.read_to_research event.
    #    A sessionStorage copy would be a second source of truth that diverges
    #    from the graph; so it rides the SAME single-writer typed-event funnel
    #    as every other state mutation (NOT the running talk-to-book thread,
    #    which IS ephemeral session view-state — that stays in sessionStorage,
    #    the usePosition precedent). It records the report PROSE (model-
    #    generated synthesis grounded on owned servable chunks — a §9.0 withheld
    #    body never enters it because retrieval went through the search gate),
    #    the length-box, the corpus scope (hard|soft) + the exact owned
    #    document ids in scope (the defensible record that it never reached the
    #    open internet), and the page-cited chunk references. It is built behind
    #    the "proposed (sign-off pending)" banner — the PROPOSED Research↔Read
    #    boundary, reversible to soft. specs/antiek-living-roadmap/ SPR-08.
    READ_META_READING_GENERATED = "read.meta_reading.generated"

    # ── Filing a personal-space doc INTO a research project (Living Roadmap
    #    SPR-13 M3). The reader's personal space CONTINUOUSLY SUGGESTS filing a
    #    created deliverable / saved read into a semantically-matching research
    #    project; on EXPLICIT accept (never auto), the surface emits this event.
    #    Filing is a LINK, not a copy: the handler sets documents.investigation_id
    #    THROUGH THE SINGLE-WRITER FUNNEL (the /events/typed side-effect handler →
    #    runtime/db_lock connect_write) — a direct ``UPDATE documents`` is
    #    forbidden (it would bypass the only-writer invariant). The §9 chain
    #    (claim→chunk→document→ip_holder_id) stays intact; ip_holder_id is
    #    untouched (immutable on filing). 1:N — a document belongs to 0..1
    #    investigation (documents.investigation_id). specs SPR-13.
    DOCUMENT_FILED_INTO_INVESTIGATION = "document.filed_into_investigation"

    # ── Foundation v2 SPR-02 — groundedness eval (truth axis) + the
    #    failure event that replaces the Phase-6 except-pass swallow.
    #    groundedness.scored is the per-synthesis claim-entailment signal
    #    emitted NON-blocking alongside rubric.scored (which stays as the
    #    SECONDARY form-axis signal). groundedness.failed surfaces a scorer
    #    crash on the live path so the signal can never silently vanish:
    #    "non-blocking" means the loop continues, NOT that the signal
    #    disappears. Validate-first — neither event gates a merge this
    #    sprint; the promote-to-gate criterion lives in
    #    substrate/eval/groundedness/PROMOTE_TO_GATE.md.
    GROUNDEDNESS_SCORED = "groundedness.scored"
    GROUNDEDNESS_FAILED = "groundedness.failed"

    # ── Personal-Reading Lane SPR-01 — deny-by-default ingest classification.
    #    Emitted when insert_document defaults a third-party document_type
    #    (web_article / video_transcript / social_thread / newsletter_post) with
    #    a NULL content_class to personal_reading — the owner-readable /
    #    public-non-servable / non-attributable / non-trainable lane. Records
    #    document_id + document_type + the applied content_class so the
    #    deny-by-default decision is reconstructable (a third-party body never
    #    landed NULL-that-serves on the public gate). NEVER carries raw_text
    #    (§9.0: events carry no body).
    DOCUMENT_CONTENT_CLASS_DEFAULTED = "document.content_class_defaulted"
    # antiek-yegge-execute SPR-01 — worker registration by the future worker
    # registry (SPR-04). One event per first-class worker spawn; see
    # WorkerIdentityPayload. Distinct from investigation.spawned_from (which
    # records a child investigation chasing a parent's open question).
    WORKER_IDENTITY = "worker.identity"
    # ── Link Monster (link ingestion surface) ──
    #    Emitted once per digest attempt (meal, snack, or leftover) with the
    #    artifact counts + platform + outcome, so the trajectory shows what
    #    the Monster ate without carrying the body (§9.0: events carry no
    #    body — raw text lives in the documents row).
    LINK_MONSTER_DIGESTED = "link.monster.digested"

    # ── Own Your Mind P0 — served-impression audit (L8/L15, §5 of the
    #    P0 brief). Emitted by the reading/research surfaces on render:
    #    WHAT was shown, in which ranked position, under which ranking
    #    version. Audit-only in P0 — NO consumer trains on it (no
    #    position-bias self-training); the event exists so the "what was
    #    displayed" half of the transparency promise is reconstructable
    #    from the trajectory alone.
    SURFACE_SERVED_IMPRESSION = "surface.served_impression"


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
# v7: Wedge 3 (Exa /contents verifier-tier corroboration) client-side
#     primitive — VERIFIER_LOOKUP event + ExaLookupResult + VerifierLookupPayload.
#     docs/integration_exa_browserbase.md §8. 2026-05-21.
# v8: Sprint 30+ thread 1 — federation audit trail. 6 typed events for
#     partner state transitions + cross-instance citation flow.
#     master-spec §13.9 + §13.7 audit. 2026-05-21.
# v9: Exa-spec §14.7 forward-compat — DiscoveryProposedPayload gains a
#     `provider_specific: dict[str, Any]` overflow bag so SerpAPI /
#     Tavily / Perplexity can add provider-shaped fields without
#     bumping the schema again. The top-level fields stay provider-
#     agnostic. 2026-05-22.
# v10: Sprint 30+ thread 4 — visual role audit trail. 3 typed events
#     (frame_identified / claims_extracted / role_failed) so the
#     visual dispatch path participates in §13.7 audit identically
#     to the other twelve roles. 2026-05-22.
# v11: PostHog Wedge 4 — AI sidecar undoable actions per §5.5. Two
#     typed events (ai.action.applied + ai.action.undone) carrying
#     prev_state + next_state JSON snapshots so the undo handler can
#     replay the inverse via the substrate. Closes the Wedge 4
#     acceptance bar. 2026-05-22.
# v12: DP shuffler production routing audit per §13.3 + §13.7. One
#     typed event (dp.routed) emitted whenever telemetry passes
#     through randomized response. Records surface + ε + whether
#     flipped, never the original value. Trust Center reads the
#     daily running ε sum from this stream. 2026-05-22.
# v13: Write workflow SPR-01 — OutlineBlock composition layer audit
#     trail. Three typed events (outline_block.placed / .moved /
#     .removed) record lego-block composition edits over
#     deliverable_sections, each carrying the provenance_kind
#     discriminator (graph_node | user_authored | synthesized |
#     brainstorm) so the authoring trajectory can replay block
#     selection and a maintainer can confirm no orphan-prose path.
#     specs/write/ SPR-01. 2026-05-25.
# v14: Read workflow SPR-01 — servable-corpus legal-gate audit trail.
#     Two typed events (book.servability_changed + book.taken_down)
#     record every transition of a book's full-text serving eligibility,
#     each carrying the from/to servability status + the reason, so the
#     deny-by-default gate's decisions are reconstructable from the
#     trajectory alone. specs/read/ SPR-01. 2026-05-25.
# v15: Write workflow SPR-02 — edit capture. One typed event
#     (edit.captured) records a structured before/after edit at
#     block/paragraph/sentence granularity with a stable locator + a
#     reverted flag (undo/redo coordination — reverts are captured but
#     excluded from training signal). The training-bound harvest is
#     hard-gated by unlock_gate (G8); these capture events are ungated
#     and the reward stays None until post-unlock. specs/write/ SPR-02.
#     2026-05-25.
# v16: antiek-unified SPR-03 — cross-workflow seam handoff audit trail.
#     Seven typed events (seam.research_to_read / read_to_research /
#     read_to_write / write_to_read / speak_to_write / speak_to_read +
#     provisional seam.write_to_speak) record one cross-workflow handoff
#     each, carrying the entity id + entity_kind + provenance_ref + the
#     terminating-handoff marker so the flywheel is reconstructable from
#     the trajectory. Handoff-audit events over existing entities — NOT
#     graph-write events; the seam moves a reference, never a copy.
#     specs/antiek-unified/ SPR-03. 2026-05-25.
# v17: Living Roadmap SPR-14 — voice infrastructure (shared voice-in
#     capture). One typed event (voice.captured) records a spoken capture
#     transcribed via the live /voice/transcribe (Whisper today; MiMo-V2.5-ASR
#     is the intended future backend behind the SAME route — a backend swap,
#     no new event). It carries the transcript + audio_ref + the SHARED
#     provenance discriminator source_kind ("user" | "ai" | "system"); a
#     voice capture is ALWAYS source_kind="user" (human-authored), the §9
#     reason voice-in can never be conflated with model output. The audio
#     blob persists by reference through the single-writer typed-event
#     funnel — no client side-store. specs/antiek-living-roadmap/ SPR-14.
#     2026-05-27.
# v18: Living Roadmap SPR-03 — block-canvas position persistence. One typed
#     event (block.positioned) records where the operator dragged an
#     insight/question block on the DRW "organism" canvas: node_id + (x, y)
#     in the canvas's free 2D coordinate space, scoped to the investigation
#     via the Event envelope's investigation_id. A canvas position is pure
#     view-state, NOT a §9 provenance claim — it is persisted through the
#     SAME single-writer typed-event funnel as every other state mutation
#     precisely because the frontend has no other sanctioned writer (a
#     client side-store would be a second source of truth that can diverge).
#     The canvas re-derives positions by replaying these events (latest per
#     node_id wins); a node with no event falls back to deterministic
#     auto-layout. The optional ``region_id`` + ``region_label`` carry M4
#     theme-grouping (a block dropped into a named region) through the SAME
#     event — no second event type, no side store. specs/antiek-living-roadmap/
#     SPR-03. 2026-05-28.
# v19: Living Roadmap SPR-04 — highlight → float-menu NOTE. One typed event
#     (marginalia.noted) records a user-authored note created by selecting text
#     on any surface and choosing "Note" in the shared float-menu. It carries
#     the note text + the selection excerpt + the selection's provenance
#     (chunk_id; document_id rides the Event envelope) + the SHARED provenance
#     discriminator source_kind pinned to the literal "user" — a marginalia note
#     is human-authored, the §9 reason it can never be conflated with a model
#     reply (the float-menu's Dialogue/Search/Deep-research RESULTS are
#     model/retrieval-sourced; only this note is user-sourced). The note rides
#     the SAME single-writer typed-event funnel as every other state mutation —
#     no client side-store. specs/antiek-living-roadmap/ SPR-04. 2026-05-28.
# v20: Living Roadmap SPR-07 — source.read → SiteSee "read" tint. One typed
#     event (source.read) records that a reader DWELLED on a source long enough
#     to count as "read" (the dwell threshold + its justification live in
#     docs/decisions/spr-06-source-read-event-gap.md). It closes the SPR-06 gap:
#     cited/saved were already substrate-derived, the per-source "read" signal
#     was not — so SiteSee's "read" tint shipped dormant. The event carries NO
#     body (§9.0) — only the document_id (Event envelope) + the chunk the read
#     was attributed to + the dwell evidence (dwell_ms + page_count) that
#     justified the verdict. It is the reader's OWN reading history (like a
#     "saved" signal), NOT a §9 provenance claim about the world, so it carries
#     no source_kind/grounding fields. Emitted ONCE per source per reading
#     session through the single-writer funnel (no side store); SiteSee reads
#     the resolved history and emits nothing itself. specs/antiek-living-roadmap/
#     SPR-07. 2026-05-28.
# v21: Living Roadmap SPR-08 — meta-reading deliverable. One typed event
#     (read.meta_reading.generated) persists a one-shot, READ-ONLY, page-cited
#     synthesis over the reader's OWNED corpus as a re-openable Read asset. It
#     rides the single-writer funnel (NOT a client side-store) because the
#     deliverable is substrate truth — it must survive reload, be re-opened /
#     narrated, and (only on explicit user action) be promoted into Research via
#     the EXISTING seam.read_to_research event (never a new silo, never auto).
#     The running talk-to-book chat thread is NOT an event — it is ephemeral
#     session view-state (sessionStorage, the usePosition precedent). The event
#     records the report prose (model-generated synthesis grounded on owned
#     servable chunks — a §9.0 withheld body never enters it because retrieval
#     went through the search gate), the length-box (the hard pages/minutes
#     budget the asset was built to), the corpus scope (hard|soft) + the exact
#     owned document ids in scope (the defensible record it never reached the
#     open internet — internet-agnostic), and page-cited chunk references. Built
#     behind the "proposed (sign-off pending)" banner: the PROPOSED Research↔Read
#     boundary, reversible to soft. specs/antiek-living-roadmap/ SPR-08.
#     2026-05-28.
# v22: Living Roadmap SPR-13 — filing a personal-space doc INTO a research
#     project. One typed event (document.filed_into_investigation) records that
#     the reader EXPLICITLY accepted a suggestion to file a created deliverable /
#     saved read into a semantically-matching research project. Filing is a
#     LINK, not a copy: the /events/typed side-effect handler sets
#     documents.investigation_id THROUGH THE SINGLE-WRITER FUNNEL (runtime/db_lock
#     connect_write) — a direct ``UPDATE documents`` is forbidden (it would
#     bypass the only-writer invariant). The §9 provenance chain
#     (claim→chunk→document→ip_holder_id) stays intact and ip_holder_id is
#     untouched (immutable on filing). NEVER auto: the event fires only on an
#     explicit user accept; the suggestion (substrate/books/personal_space.py
#     match_document_to_investigations) only ranks. 1:N — a document belongs to
#     0..1 investigation (documents.investigation_id, 1:N FK). The match score +
#     question are recorded on the event so the filing decision is reconstructable
#     (why this doc landed here). specs/antiek-living-roadmap/ SPR-13. 2026-05-28.
# v23: Foundation v2 SPR-02 — groundedness eval (truth axis). Two typed
#     events: groundedness.scored carries the per-synthesis claim-entailment
#     score (mean per-claim groundedness over the EXISTING claim→chunk
#     provenance) + the per-claim verdicts, emitted NON-blocking on the
#     live Phase-6 path alongside the (now explicitly SECONDARY, form-axis)
#     rubric.scored; groundedness.failed surfaces a scorer crash so the
#     signal can never silently vanish — it REPLACES the Phase-6
#     except-pass swallow ("never block on rubric"), which dropped the
#     signal on any crash. Non-blocking means the loop continues, not that
#     the signal disappears. Validate-first: neither event is merge-blocking
#     this sprint (the promote-to-gate criterion is written + dated in
#     substrate/eval/groundedness/PROMOTE_TO_GATE.md, the flip happens
#     later). specs/antiek-foundation-v2/ SPR-02. 2026-05-29.
# v25: AFF SPR-06 — the flywheel's reuse half. ONE typed event,
#     knowledge.reused, emitted exactly once per investigation start: it
#     records which prior knowledge units were retrieved (ranked by similarity
#     to the new investigation's question), which were INJECTED into the role's
#     context pack, their real cosine scores, the per-unit decision reason
#     (injected / dropped-not-servable / dropped-over-budget /
#     dropped-low-relevance), the originating investigation ids, and the
#     CONTEXT_PACK_ASSEMBLED event id it carries (so the reuse decision is
#     queryable from the pack provenance). reused_unit_ids + scores describe the
#     INJECTED set (equal-length, pack order); decisions +
#     source_investigation_ids cover EVERY retrieved unit's fate. An empty
#     reused_unit_ids is a first-class outcome (novel question / all-non-servable
#     / all-over-budget) — reuse-of-nothing is recorded, never skipped. SPR-06
#     filters on §9.0 servability + token budget ONLY; the groundedness/trust
#     gate is SPR-08, dedup is SPR-07, the compounding benchmark is SPR-09.
#     specs/antiek-flywheel-foundation/ SPR-06. 2026-05-31.
# v26: AFF SPR-08 — the trust gate on reuse. ONE new typed event, reuse.gated,
#     emitted once per knowledge unit EXCLUDED from reuse by the groundedness +
#     §9.0 servability gate (substrate/flywheel/reuse_gate.py). It records the
#     unit's groundedness score (composed from the shipped #27 lexical
#     entailment scorer — substrate/eval/groundedness), the scorer_id, the
#     threshold in force (REUSE_GROUNDEDNESS_THRESHOLD, default anchored to the
#     scorer's DEFAULT_SUPPORTED_THRESHOLD=0.5), and the reason(s) it was
#     excluded — below-threshold and/or non-servable — BOTH when both apply.
#     An ADMITTED unit emits NO reuse.gated event. This closes the flywheel
#     amplification leak: SPR-06 reuses prior knowledge into NEW investigations,
#     so an ungrounded/non-servable unit does not just sit in the graph, it
#     seeds the next synthesis; the gate excludes it before any unit text
#     reaches the pack. Composes the existing scorer + the §9.0 servability
#     answer recorded on the unit at deposit (deny-by-default, read not
#     re-derived). specs/antiek-flywheel-foundation/ SPR-08. 2026-06.
# --- merged: reuse.gated (SPR-08, above) and document.content_class_defaulted
#     (Personal-Reading Lane, below) were each independently bumped to v26
#     over base v25 on separate branches; folded together here the union
#     schema version is 27 (two distinct +1 events over v25). ---
# --- merged: the line above (knowledge.reused) shipped on main as v25; the
#     block below (document.content_class_defaulted) is the Personal-Reading
#     Lane event folded in here, so the union schema version is 26 (two
#     independent +1 bumps over base v24). ---
# v26: Personal-Reading Lane SPR-01 — deny-by-default ingest classification.
#     One typed event (document.content_class_defaulted) records that
#     insert_document defaulted a third-party document_type (web_article /
#     video_transcript / social_thread / newsletter_post) with a NULL
#     content_class to personal_reading — the fourth rights state
#     (owner-readable, public-non-servable, non-attributable, non-trainable).
#     The event closes the §9.0 leak where a NULL content_class passed the
#     public chunk-search gate and was reachable on the monetized read path:
#     fresh third-party ingests now land personal_reading at the write side and
#     are excluded from the public serve / search / attribution / training paths
#     at the read side. The payload carries document_id + document_type + the
#     applied content_class ONLY — NEVER raw_text (§9.0: events carry no body).
#     specs/antiek-personal-lane/ SPR-01. 2026-05-31.
# v27: antiek-yegge-execute SPR-01 — worker-identity + token-burn telemetry.
#     (a) ONE new typed event (worker.identity) records the registration of a
#     first-class worker (subprocess / asyncio_task / thread / role_invocation /
#     variant) by a future worker registry (SPR-04); it carries worker_id +
#     parent_worker_id + role + spawn_kind + an optional context_hash for
#     cache/variant tracking. event_log stores the worker_id string verbatim
#     (UUID-v7 validity is SPR-04's job, not event_log's).
#     (b) token_burn is NOT a new event type — it would duplicate the canonical
#     DISPATCH_CALL payload (cost_view.py: "every cent comes off a
#     DispatchCallPayload"). Instead DISPATCH_CALL gains FIVE optional fields
#     (cached_input_tokens, task_id, parent_run_id, feature_label, session_id)
#     default-None so every existing emitter + cost_view read stays byte-
#     identical; SPR-05 dashboards query the enriched DISPATCH_CALL rather than
#     a forked second per-call event. Operator decision 2026-07-02 (extend,
#     don't fork). specs/antiek-yegge-execute/ SPR-01. 2026-07-02.
# v29: DiscoveryProvider gains "parallel". The DRL parallel-gather adapter
#     (acquisition/search/parallel/, merged via the Exa+Parallel seam) already
#     constructs DiscoveryProposedPayload(provider="parallel") at runtime;
#     pydantic validates Literals, so the old two-member Literal made every
#     parallel-discovery emit a guaranteed ValidationError (latent — the lane
#     is inert until a Parallel key is configured). Widening is backward-
#     compatible: all stored events remain valid. Caught by mypy --strict
#     (declared-bar) during the 2026-07-02 restore merge. 2026-07-02.
# v30: Phase-8 gate decisions become first-class calibration evidence. The
#     auto-patch path now emits skill.patch_gate_decided before writer effects
#     so shadow-mode would-accept/reject decisions and enforcing rejections can
#     be counted without inferring from skill.auto_patch_applied.
# v31: Phase-8 operator reviews become immutable events linked to a prior
#     skill.patch_gate_decided event. Calibration status can now compute
#     operator-reviewed count and agreement without mutating old trajectory rows.
# v32: Talk-to-book outputs and their operator judgments become immutable,
#     owner-scoped events. The answer event carries the actual dispatch receipt;
#     the judgment links it without mutating the original output.
# v33: NotDiamond Wave 1 SPR-02 — DISPATCH_CALL gains seven additive nd_*
#     attribution fields so later advisory-routing hooks can join an ND
#     recommendation to the dispatch outcome. No migration runner exists or is
#     needed for the JSONL/Parquet event log: all fields are nullable/defaulted,
#     and historical rows validate by schema-on-read defaults. ND remains
#     advisory only; dispatch is still the authoritative router.
# v34: Account-memory S2a — graph node events admit the new ``memory`` node
#     type and graph edge events carry nullable ``owner_user_id`` so the typed
#     event remains reconstructable with the owner-scoped edge row.
# v35: Own Your Mind P0 §5 — surface.served_impression, the one new event
#     type of the P0 batch. Records what the reading/research surfaces SHOWED
#     (surface, item_kind, item_id, ranked_position, ranked_version,
#     timestamp, user_id) so "what was displayed" is auditable from the
#     trajectory alone (L8/L15). AUDIT-ONLY in P0: no consumer trains on it —
#     there is deliberately no position-bias self-training path. Emitted by
#     the surfaces on render, never by the substrate. docs/own-your-mind/
#     10-p0-implementation-brief.md §5. 2026-08-12.
# v36: Link Monster — new ``link.monster.digested`` action type + payload
#     recording one link digest attempt (url, final_url, platform,
#     document_id, outcome meal|snack|leftover, artifact counts, title,
#     author). Body-bearing fields are counts only — never the body
#     itself (§9.0). Backward-compatible: purely additive. 2026-08-13.
# v37: Version-bound artifact feedback — comment creation and canonical
#     agent-work transitions. Payloads carry identities and hashes, never
#     private comment text or transport secrets. Purely additive. 2026-08-21.
# v38: Agent feedback reply audit projection. The canonical private reply
#     remains in DuckDB; the event carries only identity and digest.
# v39: Operator feedback-thread resolution becomes an immutable audit event.
EVENT_SCHEMA_VERSION: int = 39

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

    The five optional ``*_ext`` fields below carry the token-burn telemetry
    antiek-yegge-execute SPR-01 specified as a *separate* ``token_burn`` event.
    That was a substrate-fit defect against current main: ``DISPATCH_CALL`` is
    already the canonical per-LLM-call token+cost event (``cost_view.py``:
    "every cent comes off a DispatchCallPayload"), so a second event would fork
    the convention. Instead the fields land here, default-None, so every
    existing emitter and cost_view read stays byte-identical and SPR-05's
    dashboards query the enriched DISPATCH_CALL rather than a duplicate.
    Operator decision 2026-07-02 (extend, don't fork).
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
    finish_reason: Literal["stop", "length", "tool_use", "content_filter", "error"] | None = None
    context_pack_event_id: str | None = None
    # ── token-burn telemetry (antiek-yegge-execute SPR-01, added 2026-07-02) ──
    # All optional + default-None/0 so existing emitters (router.py, base.py,
    # remote_exec cost) and cost_view reads are byte-unchanged. Populated only
    # by the SPR-05 token-burn middleware when it ships; absent (None/0) before.
    cached_input_tokens: int = Field(default=0, ge=0)
    task_id: str | None = None
    parent_run_id: str | None = None
    feature_label: str | None = None
    session_id: str | None = None
    # ── NotDiamond advisory-routing attribution (ANT-ND Wave 1 SPR-02) ──
    # Written by substrate.dispatch.nd_attribution staging when SPR-03's hook
    # ships; read by observability/training waves. Optional/defaulted so pre-v32
    # rows and non-ND dispatches validate unchanged. ND is never authoritative.
    nd_session_id: str | None = None
    nd_recommended_provider: str | None = None
    nd_recommended_model: str | None = None
    nd_tradeoff: str | None = None
    nd_decision_latency_ms: int | None = Field(default=None, ge=0)
    nd_bypassed: bool = False
    nd_bypass_reason: str | None = None


class WorkerIdentityPayload(_PayloadBase):
    """Records the registration of a first-class worker by the worker registry
    (antiek-yegge-execute SPR-04, not yet built). One event per spawn.

    Added by SPR-01 (yegge-execute) on 2026-07-02. event_log stores the
    ``worker_id`` string verbatim — UUID-v7 validity + sortability is SPR-04's
    responsibility, not event_log's; this payload does not validate the id's
    shape, only that it is non-empty. ``spawn_kind`` IS validated against the
    closed set so a typo (e.g. "async") cannot land as an un-queryable string.
    """

    action_type: Literal[ActionType.WORKER_IDENTITY] = ActionType.WORKER_IDENTITY
    worker_id: str
    parent_worker_id: str | None = None
    role: str
    session_id: str
    spawn_kind: Literal["subprocess", "asyncio_task", "thread", "role_invocation", "variant"]
    expected_lifetime_s: int | None = Field(default=None, ge=0)
    context_hash: str | None = None


class ContextLayer(BaseModel):
    """One layer of an assembled context pack. Embedded inside
    ``ContextPackAssembledPayload.layers``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "session",
        "working_memory",
        "long_term_skill",
        "reuse",
        "graph_evidence",
        "style_guide",
        "phase_metadata",
        "param_version_stamp",
    ]
    source: str
    tokens: int = Field(ge=0)


# ── Claim — the structured unit of a distillation ────────────────────


# Mirrors ``substrate.constants.CONFIDENCE_LEVELS``. Hard-coded as a
# Literal so the schema is self-contained (codegen doesn't need to chase
# a tuple import). Keep in sync with constants.py manually; the test
# suite asserts equivalence in ``test_events_schema``.
ConfidenceLevel = Literal["high", "moderate", "low", "unknown"]

# The SHARED provenance discriminator (Living Roadmap SPR-14 M3 / master-spec
# §9). One vocabulary, deliberately NOT voice-specific, so every authored-vs-
# generated distinction across the graph uses the same three values:
#   "user"   — human-authored (voice-IN capture, a typed note, an operator edit)
#   "ai"     — model-generated (a synthesized artifact; TTS narration of model
#              text is labeled "ai" by the voice-OUT half — SPR-14 M2/M3)
#   "system" — machine / non-authored (a deterministic pipeline emission)
# It is a §9 violation to ever store voice-IN as anything other than "user":
# conflating human speech with model output corrupts the provenance chain that
# claim→chunk→document→ip_holder_id depends on. The other builder's TTS-out
# labeling references the value "ai"; keep this list as the single source.
ProvenanceSourceKind = Literal["user", "ai", "system"]


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
    node_id: str | None = None  # set when promoted to a graph node


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
    truncation_strategy_applied: Literal["head", "tail", "smart"] | None = None


class KnowledgeReusedPayload(_PayloadBase):
    """AFF SPR-06 — emitted once per investigation start by
    ``substrate/context_pack/knowledge_reuse.py`` after the reuse layer is
    assembled into the pack. The queryable provenance of the flywheel's reuse
    decision: which prior knowledge units were injected, their REAL cosine
    scores, why each retrieved unit was injected or dropped, where each came
    from, and the ``CONTEXT_PACK_ASSEMBLED`` event this reuse rides on.

    Field contract:

    * ``reused_unit_ids`` / ``scores`` describe the INJECTED set only and are
      EQUAL-LENGTH, in pack (similarity-desc, id-tiebreak) order. ``scores`` are
      the real cosine similarities, never a floor (honesty, rigor #1).
    * ``decisions`` / ``source_investigation_ids`` describe EVERY retrieved unit
      (injected + dropped), equal-length to each other. A ``decision`` is one of
      ``injected`` | ``dropped-not-servable`` | ``dropped-over-budget`` |
      ``dropped-low-relevance`` — the honest, distinct reason for the unit's fate.
    * ``context_pack_event_id`` is the assembled pack's event id, so a reuse
      decision is joinable to exactly what the model saw.

    An empty ``reused_unit_ids`` is valid and expected for a novel question or
    an all-non-servable / all-over-budget retrieval — the event is STILL emitted
    (reuse-of-nothing is recorded, not skipped)."""

    action_type: Literal[ActionType.KNOWLEDGE_REUSED] = ActionType.KNOWLEDGE_REUSED
    reused_unit_ids: list[str]
    scores: list[float]
    decisions: list[str]
    source_investigation_ids: list[str]
    context_pack_event_id: str


# The reasons a unit can be EXCLUDED from reuse by the SPR-08 trust gate. A
# single excluded unit may carry BOTH (a non-servable unit that is also below
# threshold). The two are INDEPENDENT conditions; the event lists every reason
# that applied so a reader can tell a trust failure from a §9.0 refusal.
ReuseGateReason = Literal["below-threshold", "non-servable", "non-owner-readable"]


class ReuseGatedPayload(_PayloadBase):
    """AFF SPR-08 — emitted once per knowledge unit EXCLUDED from reuse by the
    groundedness + §9.0 servability gate (``substrate/flywheel/reuse_gate.py``),
    BEFORE any unit text reaches the context pack. An ADMITTED unit emits NO
    reuse.gated event — absence of this event for a reused unit is the signal
    that it cleared both conditions.

    Why this exists (the honesty thesis): the flywheel reuses prior knowledge
    into NEW investigations (SPR-06), so an ungrounded unit does not merely sit
    in the graph — it seeds the next synthesis. Without this gate the loop
    amplifies hallucination at the same rate it amplifies signal. The gate does
    NOT make reuse "safe"; it excludes below-threshold + non-servable units and
    logs every exclusion here.

    Field contract:

    * ``unit_id`` / ``source_investigation_id`` — the excluded unit and where it
      came from.
    * ``groundedness_score`` — the unit's score from the shipped #27 lexical
      entailment scorer (``substrate/eval/groundedness``); ``None`` only when the
      unit's slot was unset AND the gate could not resolve its cited chunk text
      to re-score (an honest "unknown", which is itself below any threshold).
    * ``scorer_id`` — which scorer produced the score (``groundedness-lexical-v1``),
      so the number is attributable + reproducible.
    * ``threshold`` — ``REUSE_GROUNDEDNESS_THRESHOLD`` in force at the decision
      (carried on the event so an audit reads the exact bar, not today's value).
    * ``reasons`` — every reason that applied: ``below-threshold`` and/or
      ``non-servable``. BOTH when both apply; never empty for an excluded unit.
    * ``context_pack_event_id`` — the assembled pack this exclusion is scoped to,
      so the gate decision is joinable to exactly what the model did (not) see."""

    action_type: Literal[ActionType.REUSE_GATED] = ActionType.REUSE_GATED
    unit_id: str
    source_investigation_id: str
    groundedness_score: float | None = Field(default=None, ge=0.0, le=1.0)
    scorer_id: str
    threshold: float = Field(ge=0.0, le=1.0)
    reasons: list[ReuseGateReason]
    context_pack_event_id: str = ""


# ── Wrestling — document surface ─────────────────────────────────────


class DocumentLoadedPayload(_PayloadBase):
    action_type: Literal[ActionType.DOCUMENT_LOADED] = ActionType.DOCUMENT_LOADED
    media_type: Literal["pdf", "pasted_text", "url_extracted", "markdown", "html"]
    content_hash: str
    size_bytes: int = Field(ge=0)
    title: str | None = None
    page_count: int | None = Field(default=None, ge=0)  # None for pasted text
    source_uri: str | None = None  # file:// for local, https:// for fetched; None for pasted text


class DocumentRegionSelectedPayload(_PayloadBase):
    action_type: Literal[ActionType.DOCUMENT_REGION_SELECTED] = ActionType.DOCUMENT_REGION_SELECTED
    region_id: str
    page: int | None = Field(default=None, ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    bbox: tuple[float, float, float, float] | None = None
    text_excerpt: str  # truncated by the surface; substrate doesn't truncate again


# ── Wrestling — distillation ─────────────────────────────────────────


class DistillationRequestedPayload(_PayloadBase):
    action_type: Literal[ActionType.DISTILLATION_REQUESTED] = ActionType.DISTILLATION_REQUESTED
    region_id: str | None = None  # None = whole-document distillation
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
    challenged_claim_id: str | None = None
    claim_text: str
    anchor_region_id: str | None = None
    user_question: str


class ClaimGroundingCheckPassedPayload(_PayloadBase):
    action_type: Literal[ActionType.CLAIM_GROUNDING_CHECK_PASSED] = (
        ActionType.CLAIM_GROUNDING_CHECK_PASSED
    )
    claim_id: str | None = None  # None for externally-supplied claims
    claim_text: str
    located_region_id: str
    confidence: float = Field(ge=0.0, le=1.0)


class ClaimGroundingCheckFailedPayload(_PayloadBase):
    action_type: Literal[ActionType.CLAIM_GROUNDING_CHECK_FAILED] = (
        ActionType.CLAIM_GROUNDING_CHECK_FAILED
    )
    claim_id: str | None = None  # None for externally-supplied claims
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
    node_id: str | None = None  # set when the note is also mirrored to the graph


class NoteRefinedPayload(_PayloadBase):
    action_type: Literal[ActionType.NOTE_REFINED] = ActionType.NOTE_REFINED
    note_id: str
    previous_text: str
    new_text: str
    refinement_reason: str


class NoteCompressedDocWrittenPayload(_PayloadBase):
    action_type: Literal[ActionType.NOTE_COMPRESSED_DOC_WRITTEN] = (
        ActionType.NOTE_COMPRESSED_DOC_WRITTEN
    )
    output_path: str
    note_count: int = Field(ge=0)
    byte_size: int = Field(ge=0)


# ── Wrestling — questions ────────────────────────────────────────────


class QuestionIdentifiedPayload(_PayloadBase):
    action_type: Literal[ActionType.QUESTION_IDENTIFIED] = ActionType.QUESTION_IDENTIFIED
    question_id: str
    question_text: str
    anchor_region_id: str | None = None


class QuestionEscalatedToResearchPayload(_PayloadBase):
    action_type: Literal[ActionType.QUESTION_ESCALATED_TO_RESEARCH] = (
        ActionType.QUESTION_ESCALATED_TO_RESEARCH
    )
    question_id: str
    child_investigation_id: str


class QuestionResolvedByDocPayload(_PayloadBase):
    action_type: Literal[ActionType.QUESTION_RESOLVED_BY_DOC] = ActionType.QUESTION_RESOLVED_BY_DOC
    question_id: str
    answer_note_id: str


# ── Wrestling — cross-document linkage ───────────────────────────────


class CrossDocQuestionAnsweredPayload(_PayloadBase):
    action_type: Literal[ActionType.CROSS_DOC_QUESTION_ANSWERED] = (
        ActionType.CROSS_DOC_QUESTION_ANSWERED
    )
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
    "comparison_grid",  # N candidate distillations / framings side-by-side
    "knob_slider_exploration",  # parameter-space exploration of competing claims
    "claim_triage",  # Linear-style triage of emergent questions or claims
    "model_parameter_explorer",  # knob-and-slider over a model's parameters
    "other",  # escape hatch — must be replaced with a named kind once the pattern stabilizes
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


class ArtifactCommentCreatedPayload(_PayloadBase):
    """Audit projection of one canonical, immutable-version comment."""

    action_type: Literal[ActionType.ARTIFACT_COMMENT_CREATED] = ActionType.ARTIFACT_COMMENT_CREATED
    thread_id: str
    item_id: str
    artifact_id: str
    artifact_version: int = Field(gt=0)
    artifact_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    anchor_node_id: str
    body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FeedbackThreadResolvedPayload(_PayloadBase):
    """Audit projection of an operator resolving a feedback thread."""

    action_type: Literal[ActionType.FEEDBACK_THREAD_RESOLVED] = (
        ActionType.FEEDBACK_THREAD_RESOLVED
    )
    thread_id: str
    artifact_id: str
    artifact_version: int = Field(gt=0)
    reason: Literal["operator_resolved"] = "operator_resolved"


class AgentWorkTransitionedPayload(_PayloadBase):
    """Audit projection of a canonical agent-work state transition."""

    action_type: Literal[ActionType.AGENT_WORK_TRANSITIONED] = ActionType.AGENT_WORK_TRANSITIONED
    work_id: str
    thread_id: str
    before_state: str | None
    after_state: str
    attempt_no: int = Field(ge=0)
    reason: str


class ArtifactFeedbackRepliedPayload(_PayloadBase):
    """Audit projection of one canonical agent reply."""

    action_type: Literal[ActionType.ARTIFACT_FEEDBACK_REPLIED] = (
        ActionType.ARTIFACT_FEEDBACK_REPLIED
    )
    work_id: str
    thread_id: str
    reply_item_id: str
    attempt_no: int = Field(gt=0)
    reply_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


# ── Middleware: source_tier (architecture_notes §4) ──────────────────


# Methods the tier-classifier may use. ``document_type_lookup`` is the
# fast path (deterministic catalogue); ``keyword_fallback`` is the
# defensible-but-fuzzy substring path; ``default`` is the conservative
# tier-4 fallback when no signal is available.
TierClassificationMethod = Literal[
    "document_type_lookup",
    "keyword_fallback",
    "default",
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
    document_type: str | None  # the input that drove the rule
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

    action_type: Literal[ActionType.SUBSTRATE_MANIFEST_WRITTEN] = (
        ActionType.SUBSTRATE_MANIFEST_WRITTEN
    )
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
#
# ``insight`` + ``question`` (DRW SPR-01) are the two atomic units of
# distilled truth, promoted from the ``note.emerged`` / ``question.identified``
# events to first-class graph nodes. They are listed here in lock-step with
# the DB CHECK after the migrate_v9_insight_question rebuild
# (substrate/graph/migrate_v9_insight_question.py): both layers must carry
# the same set or insert_node's payload validation diverges from the DB.
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
    "insight",
    "question",
    "memory",
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
    source_document_id: str | None = None
    chunk_id: str | None = None
    source_tier: int = Field(ge=1, le=5)
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    graph_scope: GraphScope
    owner_user_id: str | None = None


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
    "single_pass",  # no constraints applied; one-shot through
    "passed",  # iterated until all hard constraints satisfied
    "regressed",  # violations got worse across iterations
    "max_iterations_reached",  # burned the 3-iteration budget without clearing
    "escalated",  # preflight conflict — constraints contradictory
    "preflight_failed",  # constraints contradictory before any iteration
]


class ConstraintViolationFoundPayload(_PayloadBase):
    """Emitted when a constraint check identifies a violation. One
    event per violation per iteration — a synthesis can produce many
    of these inside a single constraint loop pass."""

    action_type: Literal[ActionType.CONSTRAINT_VIOLATION_FOUND] = (
        ActionType.CONSTRAINT_VIOLATION_FOUND
    )
    constraint_id: str
    strictness: ConstraintStrictness
    constraint_kind: ConstraintKind
    iteration: int = Field(ge=0)
    target_claim_id: str | None = None
    reason: str


class ConstraintRevisionTriggeredPayload(_PayloadBase):
    """Emitted when the constraint loop decides to re-invoke the
    synthesizer because at least one HARD constraint is still violated
    after the latest iteration. The triggering_constraint_ids list lets
    a downstream cohort analysis correlate which constraint kinds
    consume the most iterations."""

    action_type: Literal[ActionType.CONSTRAINT_REVISION_TRIGGERED] = (
        ActionType.CONSTRAINT_REVISION_TRIGGERED
    )
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
    "confirmed",
    "partially_confirmed",
    "disconfirmed",
    "unresolved",
]
ExecutionRiskSeverity = Literal[
    "critical",
    "high",
    "moderate",
    "low",
    "none",
]
DecisionRecommendation = Literal["proceed", "pass", "conditional"]
ActualDecision = Literal["proceed", "pass", "conditional", "not_observed"]
ProceedOutcome = Literal[
    "confirmed",
    "partially_confirmed",
    "disconfirmed",
    "not_observed",
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
    decision_alignment: DecisionAlignment | None = None
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
    target_claim_id: str | None = None
    deterministic_score: float | None = Field(default=None, ge=0.0, le=1.0)
    judged_score: float | None = Field(default=None, ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
    notes: str = ""


# Foundation v2 SPR-02 — groundedness (claim-entailment, truth axis).


class ClaimGroundednessVerdict(BaseModel):
    """One per-claim entailment verdict. ``score`` is the claim's
    groundedness in [0, 1]; ``supported`` is the binary verdict the
    backend reached (score above its supported-threshold). ``cited_chunk_ids``
    is the EXISTING claim→chunk provenance the verdict rests on — a claim
    with no cited chunk cannot be grounded (``score`` floors at 0.0,
    ``supported`` False), which is the truth-axis distinction from the
    style rubric's citation_density (density counts citations but never
    checks they SUPPORT the claim)."""

    model_config = ConfigDict(extra="forbid")

    claim: str
    score: float = Field(ge=0.0, le=1.0)
    supported: bool
    cited_chunk_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class GroundednessScoredPayload(_PayloadBase):
    """Emitted NON-blocking on the live Phase-6 path (Foundation v2
    SPR-02) alongside the SECONDARY form-axis ``rubric.scored``. The
    truth-axis signal: for each load-bearing thesis claim, does the
    EVIDENCE it cites ENTAIL the claim? ``groundedness_score`` is the
    mean per-claim score over claims that carry chunk citations;
    ``per_claim`` rides along for inspection. ``backend`` records which
    entailment backend produced the verdicts (``lexical`` deterministic
    default, ``nli`` deterministic gate-grade backend, or ``llm_judge``)
    so a reader knows whether the number is reproducible.
    ``scored_claims`` / ``total_claims`` make the coverage explicit
    (analogy-only claims with no chunk citation are excluded from the
    mean but counted in ``total_claims``).

    Observability-only this sprint — it gates nothing until M5's
    promote-to-gate criterion is met in a later sprint."""

    action_type: Literal[ActionType.GROUNDEDNESS_SCORED] = ActionType.GROUNDEDNESS_SCORED
    scorer_id: str
    backend: Literal["lexical", "nli", "llm_judge"]
    groundedness_score: float = Field(ge=0.0, le=1.0)
    scored_claims: int = Field(ge=0)
    total_claims: int = Field(ge=0)
    supported_threshold: float = Field(ge=0.0, le=1.0)
    per_claim: list[ClaimGroundednessVerdict] = Field(default_factory=list)
    notes: str = ""


class GroundednessFailedPayload(_PayloadBase):
    """Emitted when the groundedness (or style-rubric) scorer raises on
    the live Phase-6 path. This is the event that REPLACES the Phase-6
    ``except Exception: pass`` swallow (Foundation v2 SPR-02): a scorer
    crash must SURFACE, never silently drop the quality signal. The phase
    stays non-blocking — the orchestrator logs + emits this and proceeds —
    so "non-blocking" never again means "the signal disappeared".

    ``stage`` says which scorer crashed (``groundedness`` or ``rubric``);
    ``error_type`` + ``error`` carry the exception class + message for
    triage."""

    action_type: Literal[ActionType.GROUNDEDNESS_FAILED] = ActionType.GROUNDEDNESS_FAILED
    scorer_id: str
    stage: Literal["groundedness", "rubric"]
    error_type: str
    error: str


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

    action_type: Literal[ActionType.DECOMPOSER_REGENERATED] = ActionType.DECOMPOSER_REGENERATED
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
    matched_node_id: str | None = None
    matched_node_label: str | None = None
    matched_node_type: str | None = None
    similarity: float = Field(ge=0.0, le=1.0)
    low_confidence: bool = False


class SeedPair(BaseModel):
    """One (source_node_id, target_node_id) pair for the connector
    bridge to traverse between. Optional ``source_keyword`` /
    ``target_keyword`` are passed through for trajectory legibility."""

    model_config = ConfigDict(extra="forbid")

    source_node_id: str
    target_node_id: str
    source_keyword: str | None = None
    target_keyword: str | None = None


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
    algorithm_rationale: str | None = None
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
    confidence_basis: str | None = None
    effective_source_tier: int | None = Field(default=None, ge=1, le=5)
    hedging_required: bool = False


class FalsificationCondition(BaseModel):
    """One falsification condition. ``specific_observable`` is required
    — the prompt's anti-pattern #1 is "vacuous falsification
    conditions" and the parser-side check enforces a minimum length."""

    model_config = ConfigDict(extra="forbid")

    condition: str
    specific_observable: str
    timeframe: str | None = None


class ExecutionRisk(BaseModel):
    """One execution risk. ``severity_if_manifested`` is the
    four-value scale (no "none" — risks with no possible severity
    aren't risks)."""

    model_config = ConfigDict(extra="forbid")

    risk: str
    severity_if_manifested: ThesisRiskSeverity
    leading_indicator: str | None = None


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
    conviction_level: float | None = Field(default=None, ge=0.0, le=1.0)
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
    target_phase: int | None = Field(default=None, ge=1, le=9)
    target_path: str | None = None


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
    topic_slug: str | None = None
    # Cap on parallel evidence_retrieve dispatches (one per sub-question
    # from the Decomposer). The orchestrator clamps to this max; the
    # actual count is min(decomposition_length, max_sub_questions).
    max_sub_questions: int = Field(default=8, ge=1, le=20)
    # Sprint 11: parent investigation lineage for chase-spawned children.
    parent_investigation_id: str | None = None
    spawn_context: str | None = None  # highlighted text from parent's synthesis
    # Sprint 12: continuous chase mode. When chase_mode != "off", the
    # orchestrator re-enters phase 1 with the strongest open question
    # from current evidentiary_gaps as a new spawned sub-investigation
    # until the stop condition is met. Defaults to single-shot.
    chase_mode: Literal["off", "depth", "duration"] = "off"
    chase_value: int = Field(default=0, ge=0)
    # Hard budget cap in USD across the chase tree. Defaults to $2.
    chase_budget_usd: float = Field(default=2.0, ge=0.0)
    # SPR-01 (Living Roadmap) M3 + SPR-01 (Foundation) §14.4: the curated
    # fast/deep research tier the operator chose at the research entry.
    # CLOSED set — its only legal values are the members of
    # substrate.dispatch.research_tier.RESEARCH_TIERS ("fast" → MiMo V2.5
    # Pro, "deep" → DeepSeek V4 Pro). Recorded ON the start event so the
    # chosen tier is queryable after the fact (which provider was preferred
    # for this investigation's RESEARCH lane). The tier→provider resolution
    # lives in ONE place — substrate/dispatch/research_tier.py — never
    # duplicated here.
    #
    # WHY Optional[str] = None (NOT the old default "deep"): the persisted
    # value must distinguish an operator-EXPLICIT tier choice from "nothing
    # was chosen, the system applied its default." When this field defaulted
    # to "deep", a schema-default investigation was byte-indistinguishable
    # from an operator who deliberately asked for the deep lane — and the
    # synthesizer's override (interfaces/research/api/synthesizer.py:
    # _research_tier_override) consumed that default-"deep" to silently
    # re-route the §14.4-pinned Opus synthesizer onto DeepSeek the instant
    # DEEPSEEK_API_KEY was set. None == "no explicit choice recorded → the
    # research lane resolves the default (DEFAULT_RESEARCH_TIER, still
    # "deep"); the synthesizer keeps its config pin." A non-null value ==
    # "the operator explicitly chose this lane." DEFAULT_RESEARCH_TIER's
    # meaning for the research-runner lane is UNCHANGED — see
    # substrate/dispatch/research_tier.py.
    research_tier: Literal["fast", "deep"] | None = None
    owner_user_id: str | None = None
    owner_operation_id: str | None = None
    owner_model_choices: dict[str, dict[str, str]] | None = None
    owner_launch_digest: str | None = None
    owner_launch_version: int | None = Field(default=None, ge=1)


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
    parent_event_id: str | None = None
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
    original_text: str | None = None
    node_id: str | None = None
    source_tier: int = Field(default=5, ge=1, le=5)
    operator_id: str = "__operator__"
    cited_chunk_ids: list[str] = Field(default_factory=list)


class InvestigationCompletedPayload(_PayloadBase):
    """Terminal lifecycle event when Loop 1 converged cleanly. Carries
    the synthesis verdict + the constraint-loop verdict so a single
    event suffices to report outcome to a dashboard."""

    action_type: Literal[ActionType.INVESTIGATION_COMPLETED] = ActionType.INVESTIGATION_COMPLETED
    thesis_summary: str
    implicit_recommendation: SynthesisRecommendation
    constraint_loop_status: ConstraintLoopStatus
    constraint_loop_iterations: int = Field(default=1, ge=1)
    master_md_path: str | None = None
    domains_patched: list[str] = Field(default_factory=list)
    total_phases_verified: int = Field(default=0, ge=0, le=9)


class InvestigationFailedPayload(_PayloadBase):
    """Terminal lifecycle event when Loop 1 aborted before
    completion. ``phase`` identifies which phase failed; ``reason``
    is the diagnostic string (postcondition failure message, exception
    repr, etc.)."""

    action_type: Literal[ActionType.INVESTIGATION_FAILED] = ActionType.INVESTIGATION_FAILED
    phase: int = Field(ge=1, le=9)
    reason: str
    last_completed_phase: int | None = Field(default=None, ge=1, le=9)


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
    value: Any | None = None
    # ``unit`` MUST be either a non-empty string OR null/absent. The
    # upstream prompt forbids the empty-string sentinel — parser-side
    # check raises before we get here.
    unit: str | None = None


class Parameter(BaseModel):
    """One design-critical parameter extracted from the evidence.
    Mirrors the role's output schema verbatim — ``source_chunk_ids``
    is a required list (the cite-every-claim discipline)."""

    model_config = ConfigDict(extra="forbid")

    semantic_anchor: str
    metric_value: MetricValue
    qualitative_descriptor: str | None = None
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
    source_tier_min: int | None = Field(default=None, ge=1, le=5)
    confidence: EvidenceConfidence
    confidence_basis: str


class EvidentiaryGap(BaseModel):
    """One enumerated gap. Gaps are first-class output — the prompt
    explicitly treats absent answers as information, not failure."""

    model_config = ConfigDict(extra="forbid")

    gap_description: str
    additional_retrieval_suggested: str | None = None


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
    owner_semantic_call_id: str | None = None


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
    topic_slug: str | None = None
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
    topic_slug: str | None = None
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


class SkillPatchGateDecidedPayload(_PayloadBase):
    """Emitted when the Phase-8 skill-patch gate evaluates a candidate.
    Shadow mode records whether the same candidate would have been accepted
    under enforcing mode, but still allows the write path to proceed. Enforcing
    mode records the actual accept/reject decision before any skill writer
    mutates files.
    """

    action_type: Literal[ActionType.SKILL_PATCH_GATE_DECIDED] = ActionType.SKILL_PATCH_GATE_DECIDED
    synthesis_id: str
    patch_id: str
    mode: str
    decision: str
    would_accept: bool
    baseline_backtest_score: float
    candidate_backtest_score: float
    delta: float
    epsilon_required: float
    cohort_size: int = Field(ge=0)
    minimum_cohort_size: int = Field(ge=1)
    matched_domains: list[str] = Field(default_factory=list)
    notes: str = ""
    operator_reviewed: bool = False
    operator_agreed: bool | None = None


class SkillPatchGateReviewedPayload(_PayloadBase):
    """Operator review of a prior Phase-8 gate decision.
    The review states whether the operator believes the candidate patch should
    have been accepted. Agreement is derived by comparing ``operator_accept``
    with the linked decision's ``would_accept`` value.
    """

    action_type: Literal[ActionType.SKILL_PATCH_GATE_REVIEWED] = (
        ActionType.SKILL_PATCH_GATE_REVIEWED
    )
    synthesis_id: str
    patch_id: str
    decision_event_id: str
    reviewer: str
    operator_accept: bool
    review_notes: str = ""


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
    note: str | None = None
    metadata_json: str | None = None


class PhaseExitPayload(_PayloadBase):
    """Emitted when ``PhaseLog.exit(phase_id)`` is called. ``outputs_hash``
    is the SHA-256 hash of the phase's output artifacts (paths +
    contents), computed at exit time so re-runs are observable."""

    action_type: Literal[ActionType.PHASE_EXIT] = ActionType.PHASE_EXIT
    exited_at: str
    outputs_hash: str | None = None


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
    session_id: str | None = None
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

    action_type: Literal[ActionType.QUALITY_GATE_EVALUATED] = ActionType.QUALITY_GATE_EVALUATED
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
    federated_substrate_id: str | None = None


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
    document_id_ref: str | None = None
    requires_escrow: bool = False
    capped_to_daily_limit: bool = False


# ── Sprint 30+ thread 1 federation events (master-spec §13.7 audit) ──


class FederationPartnerRegisteredPayload(_PayloadBase):
    """Emitted when an operator registers a partner substrate. State
    lands at PENDING_HANDSHAKE; promotion to TRUSTED emits a separate
    event. NEVER carries the shared_secret_hex — that field is excluded
    from the audit surface by construction. The audit trail records
    WHO can federate, not the secrets used."""

    action_type: Literal[ActionType.FEDERATION_PARTNER_REGISTERED] = (
        ActionType.FEDERATION_PARTNER_REGISTERED
    )
    partner_id: str
    display_name: str
    substrate_url: str
    registered_at: str


class FederationPartnerTrustedPayload(_PayloadBase):
    """Emitted when the operator promotes PENDING_HANDSHAKE → TRUSTED.
    The transition is operator-driven; the event records the moment
    cross-instance federation becomes possible for this partner."""

    action_type: Literal[ActionType.FEDERATION_PARTNER_TRUSTED] = (
        ActionType.FEDERATION_PARTNER_TRUSTED
    )
    partner_id: str
    last_state_change_at: str
    operator_notes: str = ""


class FederationPartnerRevokedPayload(_PayloadBase):
    """Emitted when the operator revokes a partner. REVOKED is
    terminal; subsequent federation operations refuse at the substrate
    gate. The revocation_reason rides for operator triage."""

    action_type: Literal[ActionType.FEDERATION_PARTNER_REVOKED] = (
        ActionType.FEDERATION_PARTNER_REVOKED
    )
    partner_id: str
    last_state_change_at: str
    revocation_reason: str


class FederationOutboundCitationEmittedPayload(_PayloadBase):
    """Emitted when this substrate hands a citation to a partner
    instance via ``federate_outbound_citation``. The audit shape
    NEVER includes the signed_token (replay-attack surface) — the
    reference_id and partner_id are sufficient for joining against
    later inbound-accept events on the partner side."""

    action_type: Literal[ActionType.FEDERATION_OUTBOUND_CITATION_EMITTED] = (
        ActionType.FEDERATION_OUTBOUND_CITATION_EMITTED
    )
    reference_id: str
    partner_id: str
    partner_substrate_url: str
    referencing_user_id: str
    referencing_investigation_id: str
    referenced_user_id: str
    referenced_note_id: str
    revenue_routing_handle: str


class FederationInboundCitationAcceptedPayload(_PayloadBase):
    """Emitted when this substrate accepts an inbound citation from
    a partner instance. The ``receiver_reference_id`` is this side's
    locally-minted reference (distinct from the sender's)."""

    action_type: Literal[ActionType.FEDERATION_INBOUND_CITATION_ACCEPTED] = (
        ActionType.FEDERATION_INBOUND_CITATION_ACCEPTED
    )
    receiver_reference_id: str
    partner_id: str
    referencing_user_id: str
    referencing_investigation_id: str
    referenced_user_id: str
    referenced_note_id: str
    revenue_routing_handle: str
    received_at: str


class FederationInboundCitationRefusedPayload(_PayloadBase):
    """Emitted when this substrate refuses an inbound citation. The
    typed ``rejection`` reason is one of the ``InboundRejection`` enum
    values. ``detail`` is a short operator-readable string and MUST
    NOT include the raw token or shared secret per the inbound
    handler's no-leak contract."""

    action_type: Literal[ActionType.FEDERATION_INBOUND_CITATION_REFUSED] = (
        ActionType.FEDERATION_INBOUND_CITATION_REFUSED
    )
    partner_id: str
    rejection: Literal[
        "partner_not_allowed",
        "partner_not_registered",
        "partner_not_trusted",
        "token_invalid",
        "payload_malformed",
        "replay_detected",
    ]
    detail: str = ""
    received_at: str


# ── Sprint 30+ thread 4 — Visual role audit trail (master-spec §13.7) ──


class VisualFrameIdentifiedPayload(_PayloadBase):
    """Emitted when the substrate picks a frame for visual analysis.
    ``frame_source`` is "still" for image documents, "video" for an
    extracted video frame. ``frame_timestamp_ms`` is set only for
    video sources; None for stills. The audit trail records WHAT the
    role was asked to look at — the actual image bytes never appear
    in payloads (they live in the document store)."""

    action_type: Literal[ActionType.VISUAL_FRAME_IDENTIFIED] = ActionType.VISUAL_FRAME_IDENTIFIED
    document_id: str
    frame_source: Literal["still", "video"]
    page_or_frame_id: str
    frame_timestamp_ms: int | None = None
    frame_width_px: int | None = None
    frame_height_px: int | None = None


class VisualClaimsExtractedPayload(_PayloadBase):
    """Emitted when the visual role returns a parsed ``VisualResult``.
    The full claim text rides for downstream attribution; the bbox
    is normalized [0, 1] coords. ``frame_summary`` is the role's one-
    sentence summary."""

    action_type: Literal[ActionType.VISUAL_CLAIMS_EXTRACTED] = ActionType.VISUAL_CLAIMS_EXTRACTED
    document_id: str
    page_or_frame_id: str
    frame_summary: str
    claim_count: int = Field(ge=0)
    high_confidence_count: int = Field(ge=0)
    uncited_observation_count: int = Field(ge=0)


class VisualRoleFailedPayload(_PayloadBase):
    """Emitted when the dispatch call to the visual role fails OR the
    parser refuses the role's output. ``failure_kind`` discriminates;
    ``detail`` is a short operator-readable string. NEVER includes
    the raw model output (could leak unstructured prose) — the
    parser's error class names land here instead."""

    action_type: Literal[ActionType.VISUAL_ROLE_FAILED] = ActionType.VISUAL_ROLE_FAILED
    document_id: str
    page_or_frame_id: str
    failure_kind: Literal[
        "dispatch_error",
        "parse_validation",
        "provider_unavailable",
    ]
    detail: str = ""


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

    action_type: Literal[ActionType.SKILL_RULE_PROMOTED] = ActionType.SKILL_RULE_PROMOTED
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


DiscoveryProvider = Literal["exa", "parallel", "operator"]
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
    title: str | None = None
    # ISO-8601 if the provider returned it; None otherwise. Not parsed
    # to datetime — providers diverge on format and we'd rather log
    # what was received than silently normalize.
    published_date: str | None = None
    author: str | None = None
    # Provider-supplied score. Opaque per spec §14.3 — recorded but
    # NOT used for ingestion gating. The operator decides what to
    # promote; the score is just one signal.
    relevance_score: float | None = None
    # Heuristic suggestion from acquisition/search/exa/adapter.py
    # (research domain → 2, news allowlist → 3, default → 4). The
    # operator can override at ingestion time; this is a suggestion,
    # not an authority.
    suggested_tier: int = Field(ge=1, le=4)
    # Truncated preview of the provider's text snippet (≤300 chars).
    # NOT the substrate's grounding evidence — that requires ingestion
    # via acquisition/urls/adapter.ingest_url.
    text_snippet_preview: str | None = Field(default=None, max_length=300)
    # Provider's own request id, for audit cross-reference.
    # **Deprecated as a top-level field per spec §14.7** — kept for
    # backward compat with v6-v8 events; new emitters should write
    # this under ``provider_specific["response_id"]`` instead. Read
    # paths consult both (top-level shadows the dict if both present).
    provider_response_id: str | None = None
    # Per-call cost estimate in USD. Captured per spec §6.7 so
    # weekly_report.py can aggregate discovery-layer spend separately
    # from dispatch spend.
    cost_usd_estimate: float | None = Field(default=None, ge=0.0)
    # Provider-specific overflow bag per spec §14.7. Each provider
    # writes its provider-shaped fields here (Exa's `autopromptString`,
    # SerpAPI's `position`, Tavily's `score_components`, etc.). The
    # top-level fields above stay provider-agnostic — adding a new
    # provider doesn't require a schema bump.
    provider_specific: dict[str, Any] = Field(default_factory=dict)


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
    document_id: str | None = None
    decision: DiscoveryDecision
    # Free-text detail when decision != "ingested". Required only by
    # convention; the schema allows None so an "ingested" event
    # doesn't carry dead weight.
    rejection_reason: str | None = None


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

    action_type: Literal[ActionType.FETCH_FALLBACK_ESCALATED] = ActionType.FETCH_FALLBACK_ESCALATED
    url: str
    primary_fetcher: Literal["httpx"] = "httpx"
    primary_word_count: int = Field(ge=0)
    fallback_fetcher: Literal["browserbase"]
    fallback_word_count: int = Field(ge=0)
    escalation_reason: Literal[
        "low_word_count",
        "operator_override",
        "JS-detect",
    ]
    # Per-session cost estimate in USD. Captured so the weekly report
    # can flag runaway escalation early (the per-page cost is 50-5000×
    # an httpx fetch — see spec §13.1).
    estimated_cost_usd: float = Field(ge=0.0)


# ── Wedge 3 — Exa /contents verifier-tier corroboration (PHASE 2 primitive) ──


class ExaLookupResult(BaseModel):
    """One row of a `VerifierLookupPayload.results`. Mirrors the
    cleaned-snippet shape Exa returns for `/search?text=true` (or
    a `/contents` call). NOT promoted to substrate evidence — the
    snippet is verifier-tier context only."""

    model_config = ConfigDict(extra="forbid")

    url: str
    title: str | None = None
    published_date: str | None = None
    text_snippet: str | None = Field(default=None, max_length=2000)
    relevance_score: float | None = None
    provider_response_id: str | None = None


class VerifierLookupPayload(_PayloadBase):
    """The verifier tier (or any caller) consulted Exa for external
    claim corroboration. Spec §8. The snippets stay out of the
    graph (spec §8.3)."""

    action_type: Literal[ActionType.VERIFIER_LOOKUP] = ActionType.VERIFIER_LOOKUP
    tool: Literal["exa.search_contents"] = "exa.search_contents"
    query: str
    claim_text: str | None = None
    k_requested: int = Field(ge=1, le=20)
    results: list[ExaLookupResult] = Field(default_factory=list)
    cost_usd_estimate: float = Field(ge=0.0)


class AIActionAppliedPayload(_PayloadBase):
    """Emitted by the AI sidecar (Max-style ubiquitous AI per §5.5)
    whenever the AI applies a UI-mutating action on behalf of the
    operator. Carries enough state to invert the action:

    - ``target_kind`` + ``target_id`` say what was changed.
    - ``prev_state`` + ``next_state`` are opaque JSON snapshots the
      undo handler diffs to produce the inverse.
    - ``operator_prompt`` is the natural-language ask that triggered
      the action — so the operator can read what they asked for.

    The undo path replays the inverse: if ``ai.action.applied`` set
    a notebook block from X to Y, the undo POST sets it back from Y
    to X and emits ``ai.action.undone`` linking back via
    ``inverted_event_id``.
    """

    action_type: Literal[ActionType.AI_ACTION_APPLIED] = ActionType.AI_ACTION_APPLIED
    target_kind: Literal[
        "notebook_block",
        "notebook",
        "master_md_section",
        "claim",
        "watch_for_later_question",
        "investigation_chase",
        "ui_layout",
    ]
    target_id: str
    operator_prompt: str = Field(min_length=1, max_length=2000)
    prev_state: dict[str, Any] = Field(default_factory=dict)
    next_state: dict[str, Any] = Field(default_factory=dict)
    # SHA-256 of (target_kind + target_id + prev_state JSON) — gives
    # the undo handler a cheap optimistic-concurrency check so two
    # rapid AI actions on the same target can't accidentally overwrite
    # each other on undo.
    prev_state_hash: str
    summary: str = Field(default="", max_length=500)


class AIActionUndonePayload(_PayloadBase):
    """Emitted when the operator clicks "undo" on the AI sidecar.

    Links to the ``ai.action.applied`` event being inverted via
    ``inverted_event_id``. The undo handler is responsible for
    actually re-applying ``prev_state`` to the substrate; this event
    just records that the operator chose to revert.
    """

    action_type: Literal[ActionType.AI_ACTION_UNDONE] = ActionType.AI_ACTION_UNDONE
    inverted_event_id: str
    target_kind: Literal[
        "notebook_block",
        "notebook",
        "master_md_section",
        "claim",
        "watch_for_later_question",
        "investigation_chase",
        "ui_layout",
    ]
    target_id: str
    reason: Literal["operator_undo", "automated_rollback"] = "operator_undo"


class DPRoutedPayload(_PayloadBase):
    """Emitted by the DP shuffler whenever a telemetry signal passes
    through randomized response (§13.3 + §16.2).

    Records the surface, the configured ε, and whether the value was
    flipped — *without* recording the original or flipped value
    (that would defeat the point). The aggregator downstream consumes
    only the noisy stream + the registered ε to debias.

    The Trust Center reads the running sum of recorded ε per surface
    per day to publish "X surfaces collect at total ε=Y today" per
    §13.7.
    """

    action_type: Literal[ActionType.DP_ROUTED] = ActionType.DP_ROUTED
    surface_name: str
    epsilon: float = Field(ge=0.0, le=10.0)
    sensitivity: Literal["low", "medium", "high", "forbidden"]
    # Whether the value was randomized-flipped from its true value.
    # NOT the value itself — only whether RR fired the noise coin.
    # Distinguishes a "value not flipped" from a "value not observed";
    # the aggregator uses this to debias correctly.
    was_flipped: bool
    # The shuffler step the event is from: "local_randomized" (a
    # single user contribution) vs "aggregated" (the debiased final
    # estimate). The audit trail captures both.
    stage: Literal["local_randomized", "aggregated"] = "local_randomized"


# ── Write workflow — outline composition (Write SPR-01) ─────────────
#
# The OutlineBlock is the "lego block" composition primitive: a unit of
# meaning placed in an outline section. Its provenance is the moat — a
# block either references an insight/question/claim graph node
# (provenance resolvable to a source document) or is explicitly marked
# user-originated. There is NO third option: a block never carries a
# fabricated citation to a source it did not come from.
#
# block_kind extends (does not replace) the section_blocks vocabulary
# ('insight' | 'open_question' | 'operator_note' | 'claim') with two
# Write-native kinds: 'user_authored' (operator wrote it) and
# 'synthesized' (produced by generation). provenance_kind is the
# orthogonal trace discriminator — block_kind says *what* it is,
# provenance_kind says *how it traces to truth*.


class OutlineBlockPlacedPayload(_PayloadBase):
    """A lego block placed into an outline section (substrate/write/).

    provenance_kind discriminates how the block traces to a source of
    truth — the invariant SPR-07 trace-to-source relies on:

    - 'graph_node'    → ``node_id`` references an insight/question/claim
                        graph node; provenance resolves node → document
                        → chunks. ``content`` is null (the node is the
                        content of record).
    - 'user_authored' → the operator wrote it directly. ``node_id`` is
                        null; ``content`` carries the text. No false
                        citation is ever attached.
    - 'synthesized'   → produced by generation/synthesis from other
                        blocks. ``node_id`` null.
    - 'brainstorm'    → emerged from a brainstorm session (SPR-05);
                        user-originated, ``node_id`` null, traces to the
                        session not an external document.
    """

    action_type: Literal[ActionType.OUTLINE_BLOCK_PLACED] = ActionType.OUTLINE_BLOCK_PLACED
    outline_block_id: str
    deliverable_id: str
    section_id: str
    block_kind: Literal[
        "insight",
        "open_question",
        "operator_note",
        "claim",
        "user_authored",
        "synthesized",
    ]
    provenance_kind: Literal["graph_node", "user_authored", "synthesized", "brainstorm"]
    node_id: str | None = None
    block_index: int


class OutlineBlockMovedPayload(_PayloadBase):
    """A block reordered within a section or moved to a new section
    (reparent). Records both endpoints so the authoring trajectory can
    replay the composition edit deterministically."""

    action_type: Literal[ActionType.OUTLINE_BLOCK_MOVED] = ActionType.OUTLINE_BLOCK_MOVED
    outline_block_id: str
    from_section_id: str
    to_section_id: str
    from_index: int
    to_index: int


class OutlineBlockRemovedPayload(_PayloadBase):
    """A block removed from an outline. The underlying graph node is
    untouched — removal is a composition edit, not a graph deletion.
    Outlines and folders are views over nodes (the moat), so removing a
    block never destroys provenance for any other reference."""

    action_type: Literal[ActionType.OUTLINE_BLOCK_REMOVED] = ActionType.OUTLINE_BLOCK_REMOVED
    outline_block_id: str
    section_id: str


# ── Read workflow — servable-corpus legal gate (Read SPR-01) ─────────


class BookServabilityChangedPayload(_PayloadBase):
    """A book's full-text serving eligibility changed. Emitted by
    ``substrate/books/`` whenever a content_class transition moves a book
    across the servable / metadata-only line (e.g. a publisher claims an
    account and a gated book flips to publisher_opted_in). The
    from/to statuses are the DERIVED ServabilityStatus values (not the
    raw content_class) so the audit reads in the gate's own vocabulary.

    The ``document_id`` of the affected book rides the Event envelope
    (``emit_typed(..., document_id=...)``), so it isn't duplicated here."""

    action_type: Literal[ActionType.BOOK_SERVABILITY_CHANGED] = ActionType.BOOK_SERVABILITY_CHANGED
    from_status: str
    to_status: str
    reason: str


class BookTakenDownPayload(_PayloadBase):
    """A removal demand was honoured for a book (Read SPR-01 M4). Records
    that the full text was purged from the materialized document body and
    retrieval was restricted (content_class moved to the existing
    restricted_pending_opt_in gate). ``purged_full_text`` is True when a
    non-empty raw_text was nulled — distinguishing "took down a book we
    were serving" from "took down a metadata-only stub". Pre-serve /
    pre-payout takedown is the cheap defence (Bartz)."""

    action_type: Literal[ActionType.BOOK_TAKEN_DOWN] = ActionType.BOOK_TAKEN_DOWN
    reason: str
    previous_content_class: str | None = None
    purged_full_text: bool = False


class DocumentContentClassDefaultedPayload(_PayloadBase):
    """A third-party ingest landed personal_reading by deny-by-default (Personal-
    Reading Lane SPR-01 M5). Emitted by ``substrate/graph/ops.py insert_document``
    when a third-party ``document_type`` (web_article / video_transcript /
    social_thread / newsletter_post) was inserted with ``content_class=None``: the
    guard writes ``content_class='personal_reading'`` instead of NULL — closing
    the §9.0 leak where a NULL content_class passed the public chunk-search gate
    and reached the monetized read path.

    Carries the ingest classification trail — ``document_type`` (which set
    triggered the default) and the ``applied_content_class`` (always
    'personal_reading' today; recorded explicitly so a future positive-basis
    default reads truthfully) — so the deny-by-default decision is
    reconstructable by a lawyer, not just a maintainer. The ``document_id`` of the
    classified row rides the Event envelope (``emit_typed(..., document_id=...)``).
    NEVER carries ``raw_text`` (§9.0: events carry no body)."""

    action_type: Literal[ActionType.DOCUMENT_CONTENT_CLASS_DEFAULTED] = (
        ActionType.DOCUMENT_CONTENT_CLASS_DEFAULTED
    )
    document_type: str
    applied_content_class: str


# ── Write workflow — edit capture (Write SPR-02) ────────────────────


class EditCapturedPayload(_PayloadBase):
    """One structured before/after edit in the writing surface.

    This is the granular replacement for the coarse
    ``updateSectionProse`` capture (whole-section ``original_text`` vs
    ``prose_text``). The editor (SPR-04) emits one of these per edit at
    block / paragraph / sentence granularity, anchored to a stable
    locator (``section_id`` + optional ``outline_block_id`` /
    ``paragraph_index`` / ``sentence_index``) so the authoring trajectory
    (SPR-02) and section/paragraph style prompts (SPR-06) both address
    the same units.

    ``reverted`` is the undo/redo coordination point: a reverted edit is
    still captured (the chain of edits is the signal — like Cursor's
    accept/edit loop) but is explicitly EXCLUDED from training signal so a
    revert is never counted as an endorsement.

    CAPTURE ≠ TRAINING. These events are written ungated. The reward is
    computed post-unlock by ``rubric_verifier`` (itself gated); nothing
    here computes a reward or invokes training.
    """

    action_type: Literal[ActionType.EDIT_CAPTURED] = ActionType.EDIT_CAPTURED
    deliverable_id: str
    section_id: str
    outline_block_id: str | None = None
    granularity: Literal["block", "paragraph", "sentence"]
    edit_kind: Literal["insert", "delete", "replace", "reorder"]
    # Stable intra-section locator (SPR-04 produces these).
    paragraph_index: int | None = None
    sentence_index: int | None = None
    before_text: str | None = None
    after_text: str | None = None
    # Whether this edit was subsequently reverted (undo). Captured for
    # completeness; excluded from training signal.
    reverted: bool = False
    # Opaque editing-session id so multi-session trajectories stitch.
    session_id: str | None = None


# ── Write workflow — draft provenance persistence (Write SPR-09) ─────


class SectionDraftGeneratedPayload(_PayloadBase):
    """A section's draft was generated by ``creative_writer`` and its
    per-paragraph provenance persisted (Write SPR-09).

    The X-ray view (paragraph → driving blocks → chunks → documents)
    depends on ``prose_provenance`` surviving the generating request.
    ``creative_writer`` returns ``prose_provenance`` (paragraph_index →
    [block_ids]) ephemerally; this event — emitted only after a live
    generation succeeds AND the voice gate passes — makes the
    paragraph→blocks link DURABLE in the graph alongside the
    ``deliverable_sections.prose_text`` / ``prose_provenance`` row write.

    The link is the §9 moat made auditable: a maintainer can reconstruct,
    for any generated paragraph, which blocks drove it (and from there the
    chunks/documents via ``substrate.write.provenance.resolve_provenance``).
    This is a composition/audit event — the underlying blocks/nodes are
    untouched (outlines are views over nodes, per the moat).

    ``prose_provenance`` keys are STRINGS here (paragraph indices) because
    JSON object keys are strings; the reader parses them back to ints. The
    map values are the block_ids creative_writer cited per paragraph (the
    node_id for a graph-node block, the outline_block_id for a
    user-originated one — the same id the inline citation names)."""

    action_type: Literal[ActionType.SECTION_DRAFT_GENERATED] = ActionType.SECTION_DRAFT_GENERATED
    section_id: str
    deliverable_id: str
    # paragraph_index (as a string key) → list of driving block_ids.
    prose_provenance: dict[str, list[str]]
    paragraph_count: int
    # The distinct blocks cited across all paragraphs (deduped, sorted).
    cited_block_ids: list[str]
    # Did every substantive paragraph cite at least one attached block?
    all_claims_cited: bool
    # How many paragraphs were flagged unsupported (surfaced, never asserted).
    unsupported_paragraph_count: int = 0
    # The §5.5 voice gate score the prose passed at.
    gate_score: float | None = None


# ── Cross-workflow seams (antiek-unified SPR-03) ─────────────────────
#
# One payload per seam. Every seam payload carries the same four
# load-bearing fields — the entity reference (entity_id + entity_kind),
# the provenance reference, and the terminating-handoff marker — plus the
# (fixed) from/to workflow direction. They mirror substrate/seams/contracts.py;
# a copied entity would show up here as inlined content, and there is no
# content field on any of these payloads by design (the seam carries a
# reference, never a copy). No payload has a successor field — the absence is
# the no-auto-loop invariant.


class _SeamPayloadBase(_PayloadBase):
    """Shared shape of every seam handoff event. The entity travels by id +
    kind; ``provenance_ref`` is the originating event/region/source id; there
    is deliberately no field that inlines the entity's content (a copy) or
    names a successor handoff (an auto-loop)."""

    entity_id: str
    entity_kind: Literal[
        "insight_node",
        "question_node",
        "outline_block",
        "document_region",
        "servable_entry",
        "speak_claim",
    ]
    provenance_ref: str
    # Fixed True — a seam event is a single terminating handoff.
    terminates: Literal[True] = True


class SeamResearchToReadPayload(_SeamPayloadBase):
    """research → read. A researched insight surfaces in the reading corpus
    (DRW SPR-01 node + Read corpus surface)."""

    action_type: Literal[ActionType.SEAM_RESEARCH_TO_READ] = ActionType.SEAM_RESEARCH_TO_READ
    from_workflow: Literal["research"] = "research"
    to_workflow: Literal["read"] = "read"
    entity_kind: Literal["insight_node"] = "insight_node"


class SeamReadToResearchPayload(_SeamPayloadBase):
    """read → research. A highlighted passage spins a focused investigation
    (Read SPR-08 → DRW SPR-05 cascade planner seed)."""

    action_type: Literal[ActionType.SEAM_READ_TO_RESEARCH] = ActionType.SEAM_READ_TO_RESEARCH
    from_workflow: Literal["read"] = "read"
    to_workflow: Literal["research"] = "research"
    entity_kind: Literal["document_region"] = "document_region"
    document_id: str
    # Result pointer set by the receiving side — the launched session. NOT a
    # successor-handoff field; it names what this seam launched.
    launched_investigation_id: str | None = None


class SeamReadToWritePayload(_SeamPayloadBase):
    """read → write. An insight node is dragged into an outline section
    (Write SPR-03). The block references the node (provenance_kind=graph_node);
    it never inlines the insight text."""

    action_type: Literal[ActionType.SEAM_READ_TO_WRITE] = ActionType.SEAM_READ_TO_WRITE
    from_workflow: Literal["read"] = "read"
    to_workflow: Literal["write"] = "write"
    entity_kind: Literal["insight_node"] = "insight_node"
    target_section_id: str


class SeamWriteToReadPayload(_SeamPayloadBase):
    """write → read. Trace a block to its source in the shared reading surface
    (Write SPR-07), respecting Read's servability gate."""

    action_type: Literal[ActionType.SEAM_WRITE_TO_READ] = ActionType.SEAM_WRITE_TO_READ
    from_workflow: Literal["write"] = "write"
    to_workflow: Literal["read"] = "read"
    entity_kind: Literal["outline_block"] = "outline_block"
    source_document_id: str | None = None
    source_region_id: str | None = None


class SeamSpeakToWritePayload(_SeamPayloadBase):
    """speak → write. Author a biography from interview-attested claims
    (Speak SPR-08). The seam carries the speak_claim id; Write maps it to a
    synthesized block (claim_id as provenance link, not a new node)."""

    action_type: Literal[ActionType.SEAM_SPEAK_TO_WRITE] = ActionType.SEAM_SPEAK_TO_WRITE
    from_workflow: Literal["speak"] = "speak"
    to_workflow: Literal["write"] = "write"
    entity_kind: Literal["speak_claim"] = "speak_claim"
    contributor_interview_ids: list[str] = Field(default_factory=list)


class SeamSpeakToReadPayload(_SeamPayloadBase):
    """speak → read. A published biography is served back in the corpus
    (Speak SPR-09). Registers as platform_authored + speak_derived — the
    condition that routes it through the seam-#4 publish gate."""

    action_type: Literal[ActionType.SEAM_SPEAK_TO_READ] = ActionType.SEAM_SPEAK_TO_READ
    from_workflow: Literal["speak"] = "speak"
    to_workflow: Literal["read"] = "read"
    entity_kind: Literal["servable_entry"] = "servable_entry"
    publish_gate_passed: bool = False


class SeamWriteToSpeakPayload(_SeamPayloadBase):
    """write → speak. **PROVISIONAL.** Commission interviews from an outline
    gap. Typed so the trajectory can carry it, but the seam is the weakest and
    off the SPR-08 critical path; the receiving Speak side is unspecified."""

    action_type: Literal[ActionType.SEAM_WRITE_TO_SPEAK] = ActionType.SEAM_WRITE_TO_SPEAK
    from_workflow: Literal["write"] = "write"
    to_workflow: Literal["speak"] = "speak"
    entity_kind: Literal["question_node"] = "question_node"
    outline_section_id: str | None = None


# ── Voice infrastructure — shared voice-in capture (SPR-14) ──────────


class VoiceCapturedPayload(_PayloadBase):
    """A spoken capture, transcribed and persisted through the single-writer
    funnel (Living Roadmap SPR-14 M1/M3). Emitted by the shared
    ``useVoiceCapture`` hook after record → transcribe; downstream
    distillation (``substrate/books/voice_note`` → ``note.emerged``) is
    unchanged and consumes this capture by event id.

    ``source_kind`` is fixed to ``"user"`` here and is the §9 load-bearing
    field: a voice capture is human-authored, never model output. The schema
    pins it to the literal ``"user"`` (not the open :data:`ProvenanceSourceKind`) so a
    voice capture can NEVER be persisted as ``"ai"``/``"system"`` — the
    no-conflation invariant is enforced by the type, not by convention.

    The audio blob rides by *reference* (``audio_ref`` — the same field
    ``saveVoiceNote`` carries), never inline and never a client side-store:
    the blob persists wherever the reference points, the event carries only
    the pointer + the transcript.

    ``transcript`` may be empty: a silent recording must NOT be given a
    hallucinated transcript (SPR-14 rigor #3). ``transcript_status``
    distinguishes a genuine empty/silent capture ("empty") from an ordinary
    one ("ok"), so a downstream consumer never mistakes "" for "transcription
    failed". A failed transcription — or an over-cap long clip — is surfaced to
    the user and NEVER persisted; there is no such event (so no truncated/
    "bounded" status is ever emitted, hence it is not in the Literal)."""

    action_type: Literal[ActionType.VOICE_CAPTURED] = ActionType.VOICE_CAPTURED
    # The §9 provenance label — pinned to "user" (a capture is human speech).
    source_kind: Literal["user"] = "user"
    transcript: str  # may be "" for a silent capture — never a hallucination
    transcript_status: Literal["ok", "empty"] = "ok"
    language: str | None = None
    duration_seconds: float = Field(ge=0.0, default=0.0)
    # Reference to the persisted audio blob (e.g. an object key / URL). The
    # blob is NOT inlined here; this is the pointer the typed-event funnel
    # carries so there is no client-side side store.
    audio_ref: str | None = None


class MarginaliaNotedPayload(_PayloadBase):
    """A user-authored note created from a text selection via the shared
    highlight → float-menu (Living Roadmap SPR-04 M2). The reader selects text
    on any surface and chooses "Note"; the selection becomes a marginalia note
    persisted through the single-writer funnel — never a client side-store.

    ``source_kind`` is fixed to ``"user"`` and is the §9 load-bearing field,
    identically to :class:`VoiceCapturedPayload`: a marginalia note is
    human-authored, so it can NEVER be persisted as ``"ai"``/``"system"`` and
    can never be conflated with a model reply in the one graph. (The
    float-menu's OTHER actions — Dialogue / Search / Deep-research — produce
    model/retrieval-sourced RESULTS, which are labelled by their own paths;
    only this note is user-sourced.) The no-conflation invariant is enforced by
    the type, not by convention.

    Provenance (master-spec §9): the note chains claim→chunk→document like every
    other claim. ``chunk_id`` is the chunk the selection lands in (when the host
    can resolve it — a synthesis selection over a cited claim resolves a chunk;
    a free-prose selection may not, so it is optional); the document id rides
    the Event envelope (``document_id``). ``excerpt`` is the reader's OWN
    selected text — what they highlighted — not retrieved body, so it carries no
    §9.0-withheld-content risk (a reader reading their own selection). The §9.0
    no-leak guard governs the float-menu's outbound SEARCH / DEEP-RESEARCH
    payloads, not this note of one's own reading."""

    action_type: Literal[ActionType.MARGINALIA_NOTED] = ActionType.MARGINALIA_NOTED
    note_id: str
    note_text: str
    # The user's selected text (what they highlighted) — their own words on the
    # page, the anchor the note hangs off. Not retrieved body; see class docs.
    excerpt: str
    # The §9 provenance label — pinned to "user" (a marginalia note is the
    # reader's own authorship), the no-conflation invariant from the type.
    source_kind: Literal["user"] = "user"
    # The chunk the selection lands in, when the host resolves one (a synthesis
    # selection over a cited claim resolves a chunk; a free-prose selection may
    # not). Null is honest "no chunk resolved", never invented.
    chunk_id: str | None = None


# ── Block-canvas position persistence — DRW "organism" view (SPR-03) ──


class BlockPositionPayload(_PayloadBase):
    """Where an insight/open-question block sits on the DRW canvas (Living
    Roadmap SPR-03 M2/M4). Emitted on drag-end by the Canvas component.

    The canvas is a FREE 2D coordinate space — NOT the reading-physics
    in-document layout-map (that anchors widgets to text; this places nodes
    on a whiteboard). ``x``/``y`` are canvas-local pixels; the canvas
    re-derives layout by replaying these events (latest event per
    ``node_id`` wins), so the persisted event is the SINGLE source of truth
    for position. A node with no event falls back to deterministic
    auto-layout client-side; we never persist the auto-layout coordinates
    (only an operator drag emits an event).

    Why an event and not a client side-store? A canvas position is graph
    *view-state* the operator wants to survive reload. The only sanctioned
    DuckDB writer is the host funnel through ``runtime/db_lock``; a
    localStorage side-store would be a second source of truth that can
    diverge from the substrate. So position rides the SAME typed-event funnel
    as every other state mutation — the §-single-writer reason, identical to
    why VoiceCapturedPayload carries its audio by reference rather than a
    side-store.

    A canvas position is NOT a §9 provenance claim — it asserts nothing about
    the world, only about pixels — so it carries no source/grounding fields;
    the block's provenance still lives on its graph node (source_document_id).

    ``region_id`` (+ optional human ``region_label``) carries M4 theme
    grouping through the SAME event: a block dropped into a named region
    records its region here rather than as a second event type or a side
    store. ``None`` means "ungrouped"."""

    action_type: Literal[ActionType.BLOCK_POSITIONED] = ActionType.BLOCK_POSITIONED
    # The graph node (insight or question) this position belongs to. Opaque
    # handle echoed from the distill surface; never rendered as a label.
    node_id: str
    # Canvas-local coordinates (free 2D space, not the reading-physics map).
    x: float
    y: float
    # M4 theme grouping — the region this block was dropped into (None =
    # ungrouped). Persisted on the SAME event so grouping needs no side store.
    region_id: str | None = None
    # Human-facing region name, when the operator named the region. Opaque
    # otherwise; never required.
    region_label: str | None = None


# ── Reader dogfood output + operator judgment ─────────────────────────


class BookAnswerCitation(_PayloadBase):
    chunk_id: str
    document_id: str
    page_index: int | None = Field(default=None, ge=0)
    page_resolved: bool = False
    snippet: str = Field(max_length=241)


class ReadBookAnsweredPayload(_PayloadBase):
    """One durable talk-to-book output, including the real dispatch receipt."""

    action_type: Literal[ActionType.READ_BOOK_ANSWERED] = ActionType.READ_BOOK_ANSWERED
    owner_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1)
    citations: list[BookAnswerCitation] = Field(default_factory=list)
    grounded: bool
    context_chunk_count: int = Field(ge=0)
    research_tier: Literal["fast", "deep"]
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    cache_creation_input_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    latency_ms: int | None = Field(default=None, ge=0)
    dispatch_event_id: str | None = None

    @model_validator(mode="after")
    def _grounded_answer_has_dispatch_receipt(self) -> ReadBookAnsweredPayload:
        receipt = (
            self.provider,
            self.model,
            self.input_tokens,
            self.output_tokens,
            self.cost_usd,
            self.latency_ms,
        )
        if self.grounded and any(value is None for value in receipt):
            raise ValueError("a grounded book answer requires a dispatch receipt")
        if not self.grounded and any(value is not None for value in receipt):
            raise ValueError("an ungrounded no-model answer cannot claim dispatch telemetry")
        return self


class ReadBookAnswerJudgedPayload(_PayloadBase):
    """The operator's append-only verdict on one captured book answer."""

    action_type: Literal[ActionType.READ_BOOK_ANSWER_JUDGED] = ActionType.READ_BOOK_ANSWER_JUDGED
    answer_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    verdict: Literal["good", "bad"]
    note: str | None = Field(default=None, max_length=2000)


# ── Source read → SiteSee "read" tint (SPR-07 M4) ──────────────────────


class SourceReadPayload(_PayloadBase):
    """A reader dwelled on a source long enough to count as "read" (Living
    Roadmap SPR-07 M4). It lights SiteSee's "read" citation tint, closing the
    SPR-06 gap (``docs/decisions/spr-06-source-read-event-gap.md``): ``cited``
    and ``saved`` were already substrate-derived; a per-source ``read`` signal
    was not, so the tint shipped dormant.

    WHY AN EVENT, NOT A CLIENT SIDE-STORE (PR-2 / PR-6, identical reasoning to
    :class:`BlockPositionPayload`): a reader's read-history is substrate
    view-state SiteSee resolves back from the log — the only sanctioned DuckDB
    writer is the host funnel through ``runtime/db_lock``; a localStorage
    side-store would be a second source of truth that can diverge. So it rides
    the SAME single-writer typed-event funnel as every other state mutation.

    EMITTED ONCE PER SOURCE PER READING SESSION (coalesced — the surface tracks
    a per-session emitted-set, never a per-page emit), on a JUSTIFIED dwell
    threshold (see the decision doc). It is a v1, reversible tint signal.

    §9.0 — NO BODY. This event carries NO excerpt and no source text: only the
    ``document_id`` (on the Event envelope), the ``chunk_id`` the read was
    attributed to (the representative chunk SiteSee tints), and the dwell
    EVIDENCE (``dwell_ms`` + ``page_count``) that justified the verdict — so a
    maintainer can see WHY this counted as read. A withheld source's body never
    rides this event because no body field exists (structurally impossible),
    and the read of a withheld source is the reader's own dwell, not its
    content.

    NOT A §9 PROVENANCE CLAIM. It asserts the reader's OWN reading history
    (like a "saved" signal), not a claim about the world, so it carries no
    ``source_kind``/grounding fields (unlike VoiceCaptured / MarginaliaNoted,
    which ARE user-authorship claims)."""

    action_type: Literal[ActionType.SOURCE_READ] = ActionType.SOURCE_READ
    # The chunk the read was attributed to — the representative chunk SiteSee
    # anchors its "read" tint to (PR-4 semantic anchor). The document id rides
    # the Event envelope. Null is honest "no chunk resolved", never invented.
    chunk_id: str | None = None
    # The dwell EVIDENCE that justified the "read" verdict (the decision doc's
    # threshold). Recorded so the verdict is reconstructable from the event
    # alone — never the body, only the measurement.
    dwell_ms: int = Field(ge=0, default=0)
    # How many distinct pages the reader dwelled on this session before the
    # threshold tripped (the other half of the justification — a single glance
    # at one page is not a "read").
    page_count: int = Field(ge=0, default=0)


# ── Meta-reading deliverable → re-openable Read asset (SPR-08 M4) ──────────


class MetaReadingCitation(_PayloadBase):
    """One page-level citation in a saved meta-reading asset. It carries a
    REFERENCE (chunk_id + the document + the resolved reader page), never the
    source body — opening it re-derives the body through the §9.0 serve gate.
    ``page_index`` is the 0-based reader page the chunk anchors to, or null when
    ``section_path`` did not resolve to a ``Page N`` marker (then
    ``page_resolved`` is False and the surface shows an honest "page not
    pinpointed", never a fabricated page — rigor #1)."""

    chunk_id: str
    document_id: str
    page_index: int | None = None
    page_resolved: bool = False


class ReadMetaReadingGeneratedPayload(_PayloadBase):
    """A one-shot, READ-ONLY, page-cited synthesis over the reader's OWNED
    corpus, saved as a re-openable Read asset (Read SPR-08 M4).

    It is substrate truth (re-open / narrate / promote-on-explicit-action), so
    it rides the single-writer funnel — not a client side-store (which would
    diverge from the graph). The running talk-to-book chat is the opposite case
    (ephemeral session view-state, sessionStorage).

    §9.0 — the ``report`` is MODEL-generated synthesis grounded on owned
    SERVABLE chunks; a withheld body never enters it because retrieval went
    through the search gate (restricted content excluded). The ``citations``
    carry references, never bodies. ``corpus_document_ids`` is the defensible
    record of EXACTLY which owned docs were in scope — the proof this never
    reached the open internet (internet-agnostic; if it had, it would be
    Research, not Read).

    PROPOSED boundary (operator decision 2, sign-off pending): built behind the
    "proposed (sign-off pending)" banner, reversible to a ``soft`` corpus scope.
    Promotion into Research is the EXISTING ``seam.read_to_research`` event on
    explicit user action only — never auto, never a new silo."""

    action_type: Literal[ActionType.READ_META_READING_GENERATED] = (
        ActionType.READ_META_READING_GENERATED
    )
    asset_id: str
    # The reader's ask the synthesis answered (user-sourced prompt).
    prompt: str
    # The model-generated synthesis prose, already bounded to the length-box
    # (built-to-size, not post-trimmed). Read-only — never edited in place.
    report: str
    # The hard length-box the asset was built to (operator decision 3).
    length_unit: Literal["pages", "minutes"]
    length_amount: int = Field(ge=1)
    # True when the synthesis overran the budget and was cut to fit — labelled,
    # never silently clipped (rigor #1).
    truncated: bool = False
    # The corpus scope: "hard" (the proposed boundary — owned servable docs,
    # optionally an explicit pick) or "soft" (the rollback when sign-off is
    # withheld — the whole owned readable corpus). NEITHER reaches the internet.
    corpus_scope: Literal["hard", "soft"] = "hard"
    # EXACTLY the owned document ids the synthesis drew on — the internet-
    # agnostic record. An empty list is an honest "owned corpus was empty".
    corpus_document_ids: list[str] = Field(default_factory=list)
    # Page-cited references back into the SPR-07 reader.
    citations: list[MetaReadingCitation] = Field(default_factory=list)


class DocumentFiledIntoInvestigationPayload(_PayloadBase):
    """The reader EXPLICITLY accepted a suggestion to file a personal-space
    document into a research project (Read SPR-13 M3).

    THE INVARIANT (operator decision 1 + out-of-scope list): filing is NEVER
    automatic. The personal space CONTINUOUSLY SUGGESTS a match
    (``match_document_to_investigations`` ranks projects by the doc's similarity
    to each project's question); the file only happens on an EXPLICIT user
    accept that emits this event. Decline leaves the doc put (no event).

    FILING IS A LINK, NOT A COPY. The ``/events/typed`` side-effect handler sets
    ``documents.investigation_id`` THROUGH THE SINGLE-WRITER FUNNEL (the host
    ``connect_write`` lock = ``runtime/db_lock``) — a direct ``UPDATE documents``
    is FORBIDDEN (it would bypass the only-writer invariant). The §9 provenance
    chain (claim→chunk→document→ip_holder_id) is untouched; ``ip_holder_id`` is
    immutable on filing. 1:N — a document belongs to 0..1 investigation
    (``documents.investigation_id``).

    The match ``score`` + the project ``question`` are recorded so the filing
    decision is RECONSTRUCTABLE (a maintainer can see why this doc landed in this
    project) — never re-derived guesswork."""

    action_type: Literal[ActionType.DOCUMENT_FILED_INTO_INVESTIGATION] = (
        ActionType.DOCUMENT_FILED_INTO_INVESTIGATION
    )
    # The document being filed. The handler sets ITS investigation_id; the
    # document_id also rides the Event envelope (this field is the canonical
    # subject the handler acts on, independent of the envelope's optional id).
    filed_document_id: str
    # The project the reader chose (the suggestion's top match, or the one they
    # picked among >1 candidate). The handler writes THIS as the doc's
    # investigation_id. The Event envelope's investigation_id is the same value.
    target_investigation_id: str
    # The match evidence — why this doc was suggested here (reconstructable).
    match_score: float = Field(default=0.0, ge=0.0, le=1.0)
    target_question: str = ""


class LinkMonsterDigestedPayload(_PayloadBase):
    """Recorded once per Link Monster digest attempt. ``outcome`` is
    meal (body extracted), snack (metadata only), or leftover (failed —
    not yet emitted in v1; failures are typed API responses). Counts
    only — never the body (§9.0)."""

    action_type: Literal[ActionType.LINK_MONSTER_DIGESTED] = ActionType.LINK_MONSTER_DIGESTED
    url: str
    final_url: str
    platform: str  # youtube | x | instagram | tiktok | substack | generic
    document_id: str
    outcome: str  # meal | snack | leftover
    artifacts: dict[str, int] = Field(default_factory=dict)
    title: str | None = None
    author: str | None = None
    duration_ms: int = Field(default=0, ge=0)


# ── Own Your Mind P0 §5 — served-impression audit (v35 schema bump) ────────


class SurfaceServedImpressionPayload(_PayloadBase):
    """What the reading/research surfaces SHOWED on one render (Own Your
    Mind P0 §5; L8/L15).

    Emitted by the surfaces (not the substrate) whenever a ranked item is
    displayed, so the "what was shown" half of the transparency promise is
    reconstructable from the trajectory alone: the item, the ranked position
    it held, and the ranking version that produced that position.

    AUDIT-ONLY in P0. There is deliberately NO consumer that trains on this
    event: recording what was served must not create a position-bias
    self-training loop (the P0 brief's explicit constraint). A future
    consumer needs its own decision record before it may read this stream.

    ``ranked_position`` is the 0-based index of the item in the ranked list
    as displayed (0 = first). ``ranked_version`` names the ranking
    algorithm/config version that produced the order (e.g. the param
    version string), so a later change in what the user saw is attributable
    to a version boundary. ``timestamp`` is when the item was served —
    display time, not item creation time. ``user_id`` scopes the record to
    the account that saw it (multi-user readiness, mirroring the graph's
    owner_user_id columns).
    """

    action_type: Literal[ActionType.SURFACE_SERVED_IMPRESSION] = (
        ActionType.SURFACE_SERVED_IMPRESSION
    )
    # Which surface rendered the item (e.g. "research_workstation.ranked_list",
    # "personal_space.recommendations"). Free-form surface label; the surface
    # owns the vocabulary.
    surface: str
    # What kind of item was shown (e.g. "document", "chunk", "node", "claim",
    # "synthesis", "note"). Free-form kind label; the emitting surface owns it.
    item_kind: str
    # The item's canonical id in its own substrate table (document_id /
    # chunk_id / node_id / synthesis_id ...).
    item_id: str
    # 0-based position in the ranked list as displayed.
    ranked_position: int = Field(ge=0)
    # Version of the ranking algorithm/config that produced the order.
    ranked_version: str
    # When the item was served (display time, not item creation time).
    timestamp: datetime
    # The account that saw the item.
    user_id: str


# ---------------------------------------------------------------------------
# Discriminated union over typed payloads
# ---------------------------------------------------------------------------


_TypedPayloadBase = Annotated[
    DispatchCallPayload
    | WorkerIdentityPayload
    | LinkMonsterDigestedPayload
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
    | BookServabilityChangedPayload
    | BookTakenDownPayload
    | DocumentContentClassDefaultedPayload
    | EditCapturedPayload
    | SectionDraftGeneratedPayload
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
    | DocumentFiledIntoInvestigationPayload
    | SurfaceServedImpressionPayload,
    Field(discriminator="action_type"),
]

# Keep the legacy union readable while appending the Phase 2 feedback variants.
# ``get_args(...)[0]`` unwraps the union from its discriminator annotation so
# Pydantic sees one flat discriminated union at the Event boundary.
TypedPayload = Annotated[
    get_args(_TypedPayloadBase)[0]
    | ArtifactCommentCreatedPayload
    | FeedbackThreadResolvedPayload
    | AgentWorkTransitionedPayload
    | ArtifactFeedbackRepliedPayload,
    Field(discriminator="action_type"),
]


# Action types currently covered by the typed union. Read-side
# reconstruction switches on this set: typed if member, dict otherwise.
TYPED_PAYLOAD_ACTION_TYPES: frozenset[str] = frozenset(
    {
        ActionType.DISPATCH_CALL.value,
        # antiek-yegge-execute SPR-01 — worker registration (future registry, SPR-04).
        ActionType.WORKER_IDENTITY.value,
        # Link Monster — one digest attempt per link (meal/snack/leftover).
        ActionType.LINK_MONSTER_DIGESTED.value,
        ActionType.CONTEXT_PACK_ASSEMBLED.value,
        # AFF SPR-06 — flywheel reuse half.
        ActionType.KNOWLEDGE_REUSED.value,
        # AFF SPR-08 — trust gate on reuse (one event per excluded unit).
        ActionType.REUSE_GATED.value,
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
        ActionType.ARTIFACT_COMMENT_CREATED.value,
        ActionType.FEEDBACK_THREAD_RESOLVED.value,
        ActionType.AGENT_WORK_TRANSITIONED.value,
        ActionType.ARTIFACT_FEEDBACK_REPLIED.value,
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
        # Foundation v2 SPR-02 — groundedness eval (truth axis) + the failure
        # event that replaces the Phase-6 except-pass swallow.
        ActionType.GROUNDEDNESS_SCORED.value,
        ActionType.GROUNDEDNESS_FAILED.value,
        ActionType.PHASE_ENTER.value,
        ActionType.PHASE_EXIT.value,
        ActionType.PHASE_VERIFY.value,
        ActionType.DECOMPOSE_QUESTION_REQUESTED.value,
        ActionType.DECOMPOSE_QUESTION_DELIVERED.value,
        ActionType.DECOMPOSER_PARAPHRASE_FLAGGED.value,
        ActionType.DECOMPOSER_REGENERATED.value,
        ActionType.MASTER_MD_WRITTEN.value,
        ActionType.MASTER_MD_SKIPPED.value,
        ActionType.SKILL_PATCH_GATE_DECIDED.value,
        ActionType.SKILL_PATCH_GATE_REVIEWED.value,
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
        # Wedge 3 — verifier-tier external corroboration primitive.
        ActionType.VERIFIER_LOOKUP.value,
        # Sprint 30+ thread 1 — federation audit trail.
        ActionType.FEDERATION_PARTNER_REGISTERED.value,
        ActionType.FEDERATION_PARTNER_TRUSTED.value,
        ActionType.FEDERATION_PARTNER_REVOKED.value,
        ActionType.FEDERATION_OUTBOUND_CITATION_EMITTED.value,
        ActionType.FEDERATION_INBOUND_CITATION_ACCEPTED.value,
        ActionType.FEDERATION_INBOUND_CITATION_REFUSED.value,
        # Sprint 30+ thread 4 — visual role audit trail.
        ActionType.VISUAL_FRAME_IDENTIFIED.value,
        ActionType.VISUAL_CLAIMS_EXTRACTED.value,
        ActionType.VISUAL_ROLE_FAILED.value,
        # PostHog Wedge 4 — AI sidecar undoable actions.
        ActionType.AI_ACTION_APPLIED.value,
        ActionType.AI_ACTION_UNDONE.value,
        # DP shuffler production routing.
        ActionType.DP_ROUTED.value,
        # Write workflow SPR-01 — outline composition audit trail.
        ActionType.OUTLINE_BLOCK_PLACED.value,
        ActionType.OUTLINE_BLOCK_MOVED.value,
        ActionType.OUTLINE_BLOCK_REMOVED.value,
        # Read workflow SPR-01 — servable-corpus legal gate (v14 schema bump).
        ActionType.BOOK_SERVABILITY_CHANGED.value,
        ActionType.BOOK_TAKEN_DOWN.value,
        # Write workflow SPR-02 — edit capture.
        ActionType.EDIT_CAPTURED.value,
        # Write workflow SPR-09 — draft provenance persistence (X-ray).
        ActionType.SECTION_DRAFT_GENERATED.value,
        # Personal-Reading Lane SPR-01 — deny-by-default ingest classification.
        ActionType.DOCUMENT_CONTENT_CLASS_DEFAULTED.value,
        # antiek-unified SPR-03 — cross-workflow seam handoffs.
        ActionType.SEAM_RESEARCH_TO_READ.value,
        ActionType.SEAM_READ_TO_RESEARCH.value,
        ActionType.SEAM_READ_TO_WRITE.value,
        ActionType.SEAM_WRITE_TO_READ.value,
        ActionType.SEAM_SPEAK_TO_WRITE.value,
        ActionType.SEAM_SPEAK_TO_READ.value,
        ActionType.SEAM_WRITE_TO_SPEAK.value,
        # Living Roadmap SPR-14 — voice-in capture provenance.
        ActionType.VOICE_CAPTURED.value,
        # Living Roadmap SPR-04 — highlight → float-menu user NOTE provenance.
        ActionType.MARGINALIA_NOTED.value,
        # Living Roadmap SPR-03 — block-canvas position persistence.
        ActionType.BLOCK_POSITIONED.value,
        # Living Roadmap SPR-07 — source.read → SiteSee "read" tint.
        ActionType.SOURCE_READ.value,
        ActionType.READ_BOOK_ANSWERED.value,
        ActionType.READ_BOOK_ANSWER_JUDGED.value,
        # Living Roadmap SPR-08 — meta-reading deliverable → re-openable Read asset.
        ActionType.READ_META_READING_GENERATED.value,
        # Living Roadmap SPR-13 — file a personal-space doc INTO a research project.
        ActionType.DOCUMENT_FILED_INTO_INVESTIGATION.value,
        # Own Your Mind P0 §5 — served-impression audit (v35 schema bump).
        ActionType.SURFACE_SERVED_IMPRESSION.value,
    }
)


# Wrestling action types that REQUIRE document_id on the Event envelope.
# Enforced by the Event model_validator below.
WRESTLING_ACTION_TYPES: frozenset[str] = frozenset(
    {
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
    }
)


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
    synthesis_id: str | None = None
    phase: int | None = Field(default=None, ge=1, le=9)
    role: str | None = None
    action_type: ActionType
    payload: TypedPayload
    parent_event_id: str | None = None
    policy_id: str = DEFAULT_POLICY_ID
    param_version: str
    schema_version: int = EVENT_SCHEMA_VERSION
    emitted_at: datetime
    document_id: str | None = None

    @model_validator(mode="after")
    def _check_action_type_matches_payload(self) -> Event:
        # Compare against the string value rather than the enum member so
        # the check works whether action_type was passed as the enum or as
        # the underlying string (use_enum_values=True converts to str on
        # serialization but Pydantic stores the enum during validation).
        top = (
            self.action_type.value
            if isinstance(self.action_type, ActionType)
            else str(self.action_type)
        )
        pl = self.payload.action_type
        pl_str = pl.value if isinstance(pl, ActionType) else str(pl)
        if top != pl_str:
            raise ValueError(
                f"Event.action_type ({top!r}) does not match payload.action_type ({pl_str!r}). "
                "The envelope's action_type must equal the payload variant's discriminator."
            )
        return self

    @model_validator(mode="after")
    def _check_wrestling_requires_document_id(self) -> Event:
        at = (
            self.action_type.value
            if isinstance(self.action_type, ActionType)
            else str(self.action_type)
        )
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
        return v.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
    # AFF SPR-06 — flywheel reuse half
    "KnowledgeReusedPayload",
    # AFF SPR-08 — trust gate on reuse
    "ReuseGatedPayload",
    "ReuseGateReason",
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
    "ArtifactCommentCreatedPayload",
    "FeedbackThreadResolvedPayload",
    "AgentWorkTransitionedPayload",
    "ArtifactFeedbackRepliedPayload",
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
    "SkillPatchGateDecidedPayload",
    "SkillPatchGateReviewedPayload",
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
    # Wedge 3 — verifier-tier corroboration primitive (v7 schema bump)
    "ExaLookupResult",
    "VerifierLookupPayload",
    # Sprint 30+ thread 1 — federation audit trail (v8 schema bump)
    "FederationPartnerRegisteredPayload",
    "FederationPartnerTrustedPayload",
    "FederationPartnerRevokedPayload",
    "FederationOutboundCitationEmittedPayload",
    "FederationInboundCitationAcceptedPayload",
    "FederationInboundCitationRefusedPayload",
    # Sprint 30+ thread 4 — visual role audit (v10 schema bump)
    "VisualFrameIdentifiedPayload",
    "VisualClaimsExtractedPayload",
    "VisualRoleFailedPayload",
    # PostHog Wedge 4 — AI sidecar undoable actions (§5.5)
    "AIActionAppliedPayload",
    "AIActionUndonePayload",
    # DP shuffler production routing audit (§13.3 + §13.7)
    "DPRoutedPayload",
    # Write workflow SPR-01 — outline composition (v13 schema bump)
    "OutlineBlockPlacedPayload",
    "OutlineBlockMovedPayload",
    "OutlineBlockRemovedPayload",
    # Read workflow SPR-01 — servable-corpus legal gate (v14 schema bump)
    "BookServabilityChangedPayload",
    "BookTakenDownPayload",
    # Personal-Reading Lane SPR-01 — deny-by-default ingest classification (v25)
    "DocumentContentClassDefaultedPayload",
    # Write workflow SPR-02 — edit capture (v15 schema bump)
    "EditCapturedPayload",
    # Write workflow SPR-09 — draft provenance persistence (v23 schema bump)
    "SectionDraftGeneratedPayload",
    # Voice infrastructure SPR-14 — shared provenance vocab + voice-in capture
    "ProvenanceSourceKind",
    "VoiceCapturedPayload",
    # Highlight → float-menu user NOTE SPR-04 (v19 schema bump)
    "MarginaliaNotedPayload",
    # Block-canvas position persistence SPR-03 (v18 schema bump)
    "BlockPositionPayload",
    # Source read → SiteSee "read" tint SPR-07 (v20 schema bump)
    "SourceReadPayload",
    "BookAnswerCitation",
    "ReadBookAnsweredPayload",
    "ReadBookAnswerJudgedPayload",
    # Meta-reading deliverable → re-openable Read asset SPR-08 (v21 schema bump)
    "MetaReadingCitation",
    "ReadMetaReadingGeneratedPayload",
    # Filing a personal-space doc into a research project SPR-13 (v22 bump)
    "DocumentFiledIntoInvestigationPayload",
    # Own Your Mind P0 — served-impression audit (v35 schema bump)
    "SurfaceServedImpressionPayload",
]
