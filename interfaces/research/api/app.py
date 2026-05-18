"""FastAPI surface for the Antiek substrate.

The polyglot seam (architecture_notes §11). The Python substrate exposes:

- One typed WebSocket: ``/ws/events`` — live tail of the trajectory
  store, optionally filtered by ``investigation_id``.
- A small REST surface:
  - ``POST /events/typed`` — accepts the discriminated TypedPayload
    union, validates against the Pydantic schema, emits via emit_typed,
    broadcasts to subscribers, returns ``event_id``.
  - ``GET /trajectory/{investigation_id}`` — full ordered event list
    for an investigation (initial load for the reading UI).
  - ``GET /health`` — version + schema_version probe.

What this DOES NOT include (Sprint 1 scope):

- Graph queries — deferred until ``substrate/graph/`` migrates.
- Archived synthesis endpoints — deferred until ``middleware/archive/``
  migrates.
- Authentication / authorization — single-operator workstation for now;
  add when multi-tenant is on the table.
- Long-running streaming responses (LLM call streaming) — Sprint 2.

The TS reading surface at ``apps/reading/`` consumes this app via the
generated types in ``apps/reading/src/generated/types.ts`` (produced by
``tools/codegen/emit_types.py``).
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Annotated, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure package root on path for direct uvicorn invocation.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.constants import ANTIEK_PARAM_VERSION  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    EVENT_SCHEMA_VERSION,
    Event,
    TypedPayload,
    WRESTLING_ACTION_TYPES,
)

from .broadcast import EventBroadcaster  # noqa: E402


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class TypedEventEnvelope(BaseModel):
    """POST body for ``/events/typed``. The ``payload`` field uses the
    discriminated TypedPayload union — the ``action_type`` field on the
    payload tells Pydantic which variant to validate against."""

    investigation_id: str = Field(..., min_length=1)
    payload: TypedPayload
    document_id: Optional[str] = None
    synthesis_id: Optional[str] = None
    phase: Optional[int] = Field(default=None, ge=1, le=9)
    role: Optional[str] = None
    policy_id: Optional[str] = None
    parent_event_id: Optional[str] = None


class EmittedEventResponse(BaseModel):
    """Response from ``POST /events/typed`` and any future write endpoints."""

    event_id: str
    action_type: str


class HealthResponse(BaseModel):
    status: str
    param_version: str
    schema_version: int
    subscriber_count: int
    registered_providers: list[str] = Field(default_factory=list)


class InvestigationStartRequest(BaseModel):
    """POST body for ``/investigations``. Operator-facing cold-question
    entry point. ``investigation_id`` is auto-generated when omitted —
    use a stable id when retrying the same question for backtest
    correlation.

    Sprint 11: ``parent_investigation_id`` + ``spawn_context`` are
    optional metadata for the web app's highlight-to-chase mechanic.
    When supplied, the substrate emits an ``INVESTIGATION_SPAWNED_FROM``
    event recording the lineage."""

    question: str = Field(..., min_length=3)
    context: str = ""
    topic_slug: Optional[str] = None
    max_sub_questions: int = Field(default=8, ge=1, le=20)
    investigation_id: Optional[str] = None
    parent_investigation_id: Optional[str] = None
    spawn_context: Optional[str] = None


# ── Sprint 11 additions ────────────────────────────────────────────────


class ChunkResponse(BaseModel):
    """Response from ``GET /chunks/{chunk_id}``. Used by the web app's
    claim hover modal to surface the actual chunk text + source
    document title for any cited chunk_id."""

    chunk_id: str
    text: str
    section_path: Optional[str] = None
    token_count: int = 0
    document_id: str
    document_title: Optional[str] = None
    source_tier: int = Field(ge=1, le=5)


class InvestigationSummary(BaseModel):
    """One row in the ``GET /investigations`` list response. Carries
    the minimum the web app's sidebar needs to render a tree of past
    investigations."""

    investigation_id: str
    question: Optional[str] = None
    status: str  # "in_progress" | "completed" | "failed" | "not_found"
    started_at: Optional[str] = None  # ISO8601
    completed_at: Optional[str] = None  # ISO8601, terminal events only
    cost_usd_total: float = 0.0
    parent_investigation_id: Optional[str] = None


class InvestigationListResponse(BaseModel):
    count: int
    investigations: list[InvestigationSummary] = Field(default_factory=list)


# ── Sprint 12: ingest endpoint ─────────────────────────────────────


class IngestSourceRequest(BaseModel):
    """POST body for ``/sources/ingest``. The substrate auto-detects
    the source kind from the URL pattern unless ``kind`` is set
    explicitly. ``investigation_id`` binds the ingested content into
    a research project; pass the operator's current investigation_id
    when adding evidence to a specific run."""

    url: str = Field(..., min_length=8)
    kind: Optional[Literal["arxiv", "youtube", "podcast", "url"]] = None
    investigation_id: str = Field(default="__operator__", min_length=1)
    source_tier: Optional[int] = Field(default=None, ge=1, le=5)
    max_episodes: int = Field(default=10, ge=1, le=50)  # podcast feeds only


class IngestSourceResponse(BaseModel):
    """What ``POST /sources/ingest`` returns. ``status`` is one of:
    - ``ingested`` — document + chunks + nodes landed
    - ``skipped`` — document.loaded event fired but graph writes
      skipped (low_word_count, no_transcript, etc); ``skipped_reason``
      explains why
    - ``error`` — adapter raised; details in ``error_message``"""

    status: Literal["ingested", "skipped", "error"]
    detected_kind: str
    document_id: Optional[str] = None
    document_loaded_event_id: Optional[str] = None
    chunks_written: int = 0
    skipped_reason: Optional[str] = None
    error_message: Optional[str] = None
    title: Optional[str] = None
    # For podcast-feed bulk ingest: per-episode summaries
    episodes_processed: int = 0
    episodes_ingested: int = 0


class InvestigationStartResponse(BaseModel):
    """Response from ``POST /investigations`` — the cold-question
    handle the operator polls against ``GET /investigations/{id}``."""

    investigation_id: str
    status: str  # "started"
    start_event_id: str


class InvestigationStatusResponse(BaseModel):
    """Response from ``GET /investigations/{id}``. ``status`` is one of:

    - ``not_found`` — no events for this investigation_id at all
    - ``in_progress`` — start event present, no terminal event yet
    - ``completed`` — investigation.completed event present
    - ``failed`` — investigation.failed event present

    ``current_phase`` is the most recent phase the phase_log entered;
    ``last_delivered_action_type`` is the most recent ``*.delivered``
    or terminal event so the operator can see where the chain is in
    flight."""

    investigation_id: str
    status: str
    current_phase: Optional[int] = None
    last_delivered_action_type: Optional[str] = None
    terminal_payload: Optional[dict] = None


# ── Sprint 13: deliverables + voice notes ─────────────────────────────


class CreateDeliverableRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    deliverable_kind: Literal[
        "research_memo", "book_chapter", "biography_section",
        "investor_brief", "general_essay",
    ]
    investigation_root_id: Optional[str] = None


class DeliverableSummary(BaseModel):
    deliverable_id: str
    title: str
    deliverable_kind: str
    investigation_root_id: Optional[str]
    status: str
    created_at: Optional[str]
    updated_at: Optional[str]
    section_count: int = 0


class DeliverableListResponse(BaseModel):
    count: int
    deliverables: list[DeliverableSummary] = Field(default_factory=list)


class CreateSectionRequest(BaseModel):
    deliverable_id: str
    section_index: int = Field(..., ge=0)
    title: Optional[str] = None
    parent_section_id: Optional[str] = None


class AttachBlockRequest(BaseModel):
    section_id: str
    block_kind: Literal["insight", "open_question", "operator_note", "claim"]
    block_id: str
    block_index: int = Field(..., ge=0)


class SectionResponse(BaseModel):
    section_id: str
    deliverable_id: str
    parent_section_id: Optional[str]
    section_index: int
    title: Optional[str]
    prose_text: Optional[str]
    prose_provenance: Optional[dict]
    block_count: int = 0


class DeliverableDetailResponse(BaseModel):
    deliverable_id: str
    title: str
    deliverable_kind: str
    status: str
    sections: list[SectionResponse] = Field(default_factory=list)


class VoiceNoteIngestRequest(BaseModel):
    """Operator-facing endpoint accepts a pre-transcribed payload OR
    an audio file (multipart). The JSON shape here is for the
    transcript-only path; the audio path uses ``UploadFile``."""

    transcript: str = Field(..., min_length=1)
    investigation_id: str = Field(default="__operator__", min_length=1)
    title: Optional[str] = None
    duration_seconds: float = 0.0
    language: Optional[str] = None


class VoiceNoteIngestResponse(BaseModel):
    status: Literal["ingested", "skipped"]
    document_id: str
    document_loaded_event_id: Optional[str] = None
    chunks_written: int = 0
    skipped_reason: Optional[str] = None
    title: Optional[str] = None


# ---------------------------------------------------------------------------
# Source kind detection (Sprint 12)
# ---------------------------------------------------------------------------


def _detect_source_kind(
    url: str, explicit: Optional[str] = None,
) -> Optional[str]:
    """Auto-detect a source kind from the URL pattern. Operator can
    override via the ``kind`` field on the request. Returns the kind
    name or None if unrecognized (caller treats as URL fallback or
    errors)."""
    if explicit:
        return explicit
    u = url.lower().strip()
    if "arxiv.org" in u or "/abs/" in u:
        return "arxiv"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    # Podcast feeds: heuristic — RSS-ish URL OR explicit feed-like path.
    # The dashboard convention "podcasts.<host>/feed" + ".rss"
    # extensions cover most.
    if (
        u.endswith(".rss")
        or u.endswith(".xml")
        or "/rss" in u
        or "/feed" in u
        or u.endswith("/podcast")
    ):
        return "podcast"
    # Default: treat as a plain URL article (acquisition/urls).
    return "url"


def _extract_arxiv_id(url: str) -> Optional[str]:
    """Pull the arXiv id out of a URL like
    ``https://arxiv.org/abs/2402.03300`` (or variations)."""
    import re
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([A-Za-z0-9.\-]+)", url)
    if m:
        # Strip ``vN`` version suffix; the arXiv client handles
        # versioning internally.
        return m.group(1).split("v")[0]
    # Bare id (e.g. "2402.03300")
    if re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", url.strip()):
        return url.strip().split("v")[0]
    return None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    *,
    broadcaster: Optional[EventBroadcaster] = None,
    cors_origins: Optional[list[str]] = None,
    register_wrestling: bool = True,
    wrestling_db_path: Optional[str] = None,
    wrestling_embedder: Any = None,
    register_providers: bool = True,
) -> FastAPI:
    """Create the FastAPI app. Pass ``broadcaster`` for tests that want to
    inspect subscriber state; production calls ``create_app()`` and gets
    a fresh broadcaster.

    ``cors_origins`` controls CORS for browser-side dev. Defaults to
    localhost:5173 (Vite default) when None; override via the
    ``ANTIEK_CORS_ORIGINS`` env var (comma-separated). Pass an explicit
    list to disable CORS by passing ``[]`` (production behind a reverse
    proxy on the same origin shouldn't need it).

    ``register_wrestling`` wires the proto-note_taker handler that
    reacts to ``distillation.requested`` events by dispatching a
    synthesizer call and emitting ``distillation.delivered``. Tests
    that want to exercise the API without the handler firing can pass
    ``False``."""
    app = FastAPI(
        title="Antiek substrate API",
        version=ANTIEK_PARAM_VERSION,
        description=(
            "The Python side of the Antiek polyglot seam. Live event "
            "WebSocket + typed event POST + trajectory queries. "
            "See docs/architecture_notes.md §11."
        ),
    )

    # Resolve CORS origins. Vite's dev server runs at :5173 by default;
    # the operator can override via env for non-default ports or staging
    # hosts. WebSocket origin checks honor the same list.
    if cors_origins is None:
        env_val = os.environ.get("ANTIEK_CORS_ORIGINS", "").strip()
        if env_val:
            cors_origins = [o.strip() for o in env_val.split(",") if o.strip()]
        else:
            # Default allow-list:
            # - localhost:5173 + 127.0.0.1:5173: Vite dev server (Mode B
            #   wrestle UI; Mode A research workstation)
            # - https://app.antiek.ai: production web app (Sprint 11)
            cors_origins = [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "https://app.antiek.ai",
            ]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    bus = broadcaster if broadcaster is not None else EventBroadcaster()
    # Expose for tests and admin endpoints.
    app.state.broadcaster = bus

    # Wire concrete dispatch providers. Each adapter only registers if
    # its API-key env var is present; missing keys degrade gracefully
    # (the router's fallback chain takes over). Tests that exercise
    # dispatch via the in-process mock pass register_providers=False
    # so this startup pass doesn't see operator credentials.
    if register_providers:
        from substrate.dispatch.providers import register_default_providers
        app.state.registered_providers = register_default_providers(quiet=True)
    else:
        app.state.registered_providers = set()

    if register_wrestling:
        # Imported lazily so tests that don't touch wrestling don't pay
        # the dispatch / context_pack import cost.
        from .cross_doc import register_handlers as _register_cross_doc
        from .grounding import register_handlers as _register_grounding
        from .note_taking import register_handlers as _register_note_taking
        from .wrestling import register_handlers as _register_wrestling
        _register_wrestling(
            bus,
            db_path=wrestling_db_path,
            embedder=wrestling_embedder,
        )
        # The grounder shares the wrestling bridge's DB + embedder so a
        # single create_app call wires the full Loop 2 closed-loop:
        # region select → chunk inserted; claim challenged → chunk
        # searched + grounder dispatched.
        _register_grounding(
            bus,
            db_path=wrestling_db_path,
            embedder=wrestling_embedder,
        )
        # The note-taker triggers every Nth qualifying wrestling event
        # (distillation.delivered + claim.grounding_check_*). Closes
        # the loop on emergent-insight capture per architecture_notes §9.
        _register_note_taking(bus)
        # Cross-doc linking watches question.identified + note.emerged
        # and emits cross_doc.question_answered when an emerging note
        # answers an open question on a DIFFERENT document. The
        # operator's "question in doc A answered by wrestling doc B"
        # differentiator from Sprint 1.
        _register_cross_doc(bus, embedder=wrestling_embedder)
        # Decomposer role bridge (Sprint 6 day 1-2). Subscribes to
        # decompose.requested and emits decompose.delivered after a
        # paraphrase-guarded (one-regen-max) decomposer dispatch. Loop 1
        # starts here — the first orchestrate.py role extracted.
        from .decomposer import register_handlers as _register_decomposer
        _register_decomposer(bus, embedder=wrestling_embedder)
        # Evidence Retriever bridge (Sprint 7 day 1). Subscribes to
        # evidence.retrieve.requested → flash-tier dispatch → parse
        # closed-vocabulary response → emit Delivered. Second
        # orchestrate.py role bridge.
        from .evidence_retriever import (
            register_handlers as _register_evidence_retriever,
        )
        _register_evidence_retriever(bus)
        # Parameter Extractor bridge (Sprint 7 day 2). Subscribes to
        # parameter_extract.requested → flash-tier dispatch → parse
        # → convert parameters to ConstraintSpec records → emit
        # Delivered carrying both. The Day 3 constraint loop reads
        # ``constraints`` from the typed trajectory directly. Third
        # orchestrate.py role bridge.
        from .parameter_extractor import (
            register_handlers as _register_parameter_extractor,
        )
        _register_parameter_extractor(bus)
        # Connector bridge (Sprint 7 day 4). Subscribes to
        # connector.requested → runs substrate.graph.traverse against
        # seed pairs → dispatches Pro-tier role to confirm mappings +
        # render NL relationships → emits Delivered carrying both the
        # structured paths and their natural-language renderings.
        # Fourth orchestrate.py role bridge.
        from .connector import (
            register_handlers as _register_connector,
        )
        _register_connector(bus, db_path=wrestling_db_path)
        # Synthesizer bridge (Sprint 7 day 5 — closes Loop 1's role
        # chain). Subscribes to synthesize.requested → dispatches the
        # Synthesis-tier role → drives the Sprint 7 day 3 constraint
        # loop with re-invoke callable → emits Delivered with the
        # loop-converged thesis + the loop's terminal status. Last of
        # the four orchestrate.py role bridges.
        from .synthesizer import (
            register_handlers as _register_synthesizer,
        )
        _register_synthesizer(bus)
        # Loop 1 orchestrator (Sprint 8 day 3). Subscribes to
        # investigation.start_requested; drives the 9-phase sequence
        # using the 5 role bridges above + phase_runner +
        # skills.domain. Emits investigation.completed (or
        # investigation.failed) when the run terminates.
        from orchestration.loop_one import (
            register_handlers as _register_loop_one,
        )
        _register_loop_one(bus)

    # ── Health ──────────────────────────────────────────────────

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            param_version=ANTIEK_PARAM_VERSION,
            schema_version=EVENT_SCHEMA_VERSION,
            subscriber_count=bus.subscriber_count,
            registered_providers=sorted(
                getattr(app.state, "registered_providers", set())
            ),
        )

    # ── POST typed event ────────────────────────────────────────

    @app.post("/events/typed", response_model=EmittedEventResponse, status_code=201)
    async def post_typed_event(envelope: TypedEventEnvelope) -> EmittedEventResponse:
        # The wrestling-vs-non-wrestling document_id requirement is
        # enforced by the Event model_validator when we construct the
        # Event for broadcast — but the emit path validates the same
        # invariant and returns a ValidationError, which we surface as
        # a 422. Catch the obvious case early for a cleaner error.
        action_type = envelope.payload.action_type
        action_value = action_type.value if hasattr(action_type, "value") else str(action_type)
        if action_value in WRESTLING_ACTION_TYPES and not envelope.document_id:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"action_type {action_value!r} is a wrestling-loop event "
                    "and requires document_id on the envelope (architecture_notes §9.1)."
                ),
            )

        try:
            event_id = emit_typed(
                envelope.investigation_id,
                envelope.payload,
                parent_event_id=envelope.parent_event_id,
                synthesis_id=envelope.synthesis_id,
                phase=envelope.phase,
                role=envelope.role,
                policy_id=envelope.policy_id,
                document_id=envelope.document_id,
            )
        except Exception as exc:  # Pydantic ValidationError or write error
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if event_id is None:
            # Events disabled via env var — surface so the client knows
            # nothing was persisted. Distinct from a write failure.
            raise HTTPException(
                status_code=503,
                detail="Event log is disabled (ANTIEK_EVENTS_DISABLED is set).",
            )

        # Reconstruct the Event for broadcast. The trajectory store has
        # the persisted row; we read it back rather than fabricate the
        # envelope so the broadcast frame matches the on-disk shape
        # exactly (timestamp, derived fields, etc.).
        rows = trajectory(envelope.investigation_id)
        matching = next((r for r in rows if r.get("event_id") == event_id), None)
        if matching is not None:
            try:
                event = Event.model_validate(matching)
                await bus.broadcast(event)
            except Exception:  # pragma: no cover — diagnostic only
                # Don't fail the POST because the broadcast failed.
                pass

        return EmittedEventResponse(event_id=event_id, action_type=action_value)

    # ── GET trajectory ──────────────────────────────────────────

    @app.get("/trajectory/{investigation_id}")
    async def get_trajectory(
        investigation_id: str,
        limit: Annotated[Optional[int], Query(ge=1, le=10_000)] = None,
    ) -> dict:
        rows = trajectory(investigation_id)
        if limit is not None:
            rows = rows[-limit:]
        return {
            "investigation_id": investigation_id,
            "count": len(rows),
            "events": rows,
        }

    # ── Loop 1 entry point ─────────────────────────────────────
    # POST /investigations kicks off a cold question; GET
    # /investigations/{id} reports phase progression + terminal
    # verdict. The orchestrator subscribes to
    # investigation.start_requested and runs the 9-phase chain in
    # a detached task — POST returns immediately with the handle.

    @app.post(
        "/investigations",
        response_model=InvestigationStartResponse,
        status_code=202,  # accepted; orchestrator runs async
    )
    async def post_investigation(
        req: InvestigationStartRequest,
    ) -> InvestigationStartResponse:
        """Cold-question entry point. Emits
        ``INVESTIGATION_START_REQUESTED`` into the trajectory; the
        Loop 1 orchestrator subscribes to that action_type and
        spawns the per-investigation coroutine that drives phases
        1-9. Returns the investigation_id + start_event_id
        immediately so the caller can poll status."""
        # Lazy import — avoid pulling InvestigationStartRequestedPayload
        # at module import time so test setups that monkey-patch the
        # schema layer (drift tests) don't see a partially-initialized
        # module.
        from substrate.schemas import (
            InvestigationSpawnedFromPayload,
            InvestigationStartRequestedPayload,
        )
        import uuid as _uuid

        investigation_id = (
            req.investigation_id or f"inv-{_uuid.uuid4().hex[:12]}"
        )
        try:
            event_id = emit_typed(
                investigation_id,
                InvestigationStartRequestedPayload(
                    question=req.question,
                    context=req.context,
                    topic_slug=req.topic_slug,
                    max_sub_questions=req.max_sub_questions,
                    parent_investigation_id=req.parent_investigation_id,
                    spawn_context=req.spawn_context,
                ),
                role="operator",
                policy_id="operator-cli",
            )
        except Exception as exc:  # Pydantic ValidationError
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if event_id is None:
            raise HTTPException(
                status_code=503,
                detail="Event log is disabled (ANTIEK_EVENTS_DISABLED).",
            )

        # Sprint 11: emit the spawn-lineage event when parent provided.
        # Non-fatal if it fails; the start event already encodes the
        # lineage in its own payload.
        if req.parent_investigation_id:
            try:
                emit_typed(
                    investigation_id,
                    InvestigationSpawnedFromPayload(
                        parent_investigation_id=req.parent_investigation_id,
                        spawn_context=req.spawn_context or "",
                    ),
                    role="operator",
                    policy_id="operator-cli",
                    parent_event_id=event_id,
                )
            except Exception:  # pragma: no cover — diagnostic
                pass

        # Broadcast the start event so the orchestrator handler
        # subscribed to it spawns the per-investigation coroutine.
        for row in reversed(trajectory(investigation_id)):
            if row.get("event_id") == event_id:
                try:
                    event = Event.model_validate(row)
                    await bus.broadcast(event)
                except Exception:  # pragma: no cover — diagnostic
                    pass
                break

        return InvestigationStartResponse(
            investigation_id=investigation_id,
            status="started",
            start_event_id=event_id,
        )

    @app.get(
        "/investigations/{investigation_id}",
        response_model=InvestigationStatusResponse,
    )
    async def get_investigation_status(
        investigation_id: str,
    ) -> InvestigationStatusResponse:
        """Phase-progression + terminal-verdict summary for one
        investigation. Distinguishes ``not_found`` (no events at all)
        from ``in_progress`` (start event present, no terminal yet)
        from terminal states ``completed`` / ``failed``."""
        from substrate.schemas import ActionType

        rows = trajectory(investigation_id)
        if not rows:
            return InvestigationStatusResponse(
                investigation_id=investigation_id, status="not_found",
            )

        completed_action = ActionType.INVESTIGATION_COMPLETED.value
        failed_action = ActionType.INVESTIGATION_FAILED.value

        # Walk newest-first to find the latest phase, latest delivered,
        # and any terminal verdict.
        last_phase: Optional[int] = None
        last_delivered: Optional[str] = None
        terminal_row: Optional[dict] = None

        for r in reversed(rows):
            at = r.get("action_type")
            if terminal_row is None and at in (completed_action, failed_action):
                terminal_row = r
            if last_delivered is None and isinstance(at, str) and at.endswith(".delivered"):
                last_delivered = at
            if last_phase is None and r.get("phase") is not None:
                last_phase = int(r["phase"])
            if (
                terminal_row is not None
                and last_delivered is not None
                and last_phase is not None
            ):
                break

        if terminal_row is not None:
            status = (
                "completed"
                if terminal_row.get("action_type") == completed_action
                else "failed"
            )
            return InvestigationStatusResponse(
                investigation_id=investigation_id,
                status=status,
                current_phase=last_phase,
                last_delivered_action_type=last_delivered,
                terminal_payload=terminal_row.get("payload"),
            )

        return InvestigationStatusResponse(
            investigation_id=investigation_id,
            status="in_progress",
            current_phase=last_phase,
            last_delivered_action_type=last_delivered,
            terminal_payload=None,
        )

    # ── Sprint 11: list investigations + chunk fetch ───────────

    @app.get(
        "/investigations",
        response_model=InvestigationListResponse,
    )
    async def list_investigations(
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        status_filter: Annotated[
            Optional[str], Query(alias="status")
        ] = None,
    ) -> InvestigationListResponse:
        """List recent investigations. Walks the events directory to
        discover all unique investigation_ids, then summarizes each
        with its start question + terminal status + cost.

        Filter by ``status`` to narrow (one of: ``in_progress``,
        ``completed``, ``failed``). Default limit 50, sorted newest
        first."""
        import os as _os
        from substrate.event_log import default_events_dir
        from substrate.schemas import ActionType

        events_dir = default_events_dir()
        if not _os.path.isdir(events_dir):
            return InvestigationListResponse(count=0, investigations=[])

        completed_action = ActionType.INVESTIGATION_COMPLETED.value
        failed_action = ActionType.INVESTIGATION_FAILED.value
        start_action = ActionType.INVESTIGATION_START_REQUESTED.value

        summaries: list[InvestigationSummary] = []
        for filename in _os.listdir(events_dir):
            if not filename.startswith("inv-") or not filename.endswith(".jsonl"):
                continue
            inv_id = filename[:-len(".jsonl")]
            rows = trajectory(inv_id)
            if not rows:
                continue

            question: Optional[str] = None
            started_at: Optional[str] = None
            completed_at: Optional[str] = None
            cost_total = 0.0
            terminal_status = "in_progress"
            parent_inv_id: Optional[str] = None

            for r in rows:
                at = r.get("action_type")
                payload = r.get("payload") or {}
                if at == start_action and question is None:
                    question = payload.get("question")
                    started_at = r.get("emitted_at")
                    parent_inv_id = payload.get("parent_investigation_id")
                elif at == completed_action:
                    terminal_status = "completed"
                    completed_at = r.get("emitted_at")
                elif at == failed_action:
                    terminal_status = "failed"
                    completed_at = r.get("emitted_at")
                elif at == "dispatch.call":
                    try:
                        cost_total += float(payload.get("cost_usd", 0.0))
                    except (TypeError, ValueError):
                        pass

            if status_filter and terminal_status != status_filter:
                continue

            summaries.append(InvestigationSummary(
                investigation_id=inv_id,
                question=question,
                status=terminal_status,
                started_at=started_at,
                completed_at=completed_at,
                cost_usd_total=round(cost_total, 6),
                parent_investigation_id=parent_inv_id,
            ))

        # Sort newest-first by started_at (ISO8601 strings sort lexically).
        summaries.sort(
            key=lambda s: s.started_at or "",
            reverse=True,
        )
        summaries = summaries[:limit]
        return InvestigationListResponse(
            count=len(summaries), investigations=summaries,
        )

    @app.get(
        "/chunks/{chunk_id}",
        response_model=ChunkResponse,
    )
    async def get_chunk(chunk_id: str) -> ChunkResponse:
        """Read-only chunk fetch. Used by the web app's claim hover
        modal to surface the actual chunk text + source document
        title for any cited chunk_id."""
        import duckdb as _duckdb
        from substrate.graph import default_db_path

        db_path = default_db_path()
        try:
            con = _duckdb.connect(db_path, read_only=True)
        except _duckdb.IOException as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Graph DB unreachable: {exc}",
            ) from exc

        try:
            row = con.execute(
                """
                SELECT c.chunk_id, c.text, c.section_path, c.token_count,
                       c.document_id, d.title, d.source_tier
                FROM chunks c
                JOIN documents d ON c.document_id = d.document_id
                WHERE c.chunk_id = ?
                """,
                [chunk_id],
            ).fetchone()
        finally:
            con.close()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"chunk_id {chunk_id!r} not found",
            )

        return ChunkResponse(
            chunk_id=row[0],
            text=row[1] or "",
            section_path=row[2],
            token_count=int(row[3] or 0),
            document_id=row[4],
            document_title=row[5],
            source_tier=int(row[6]),
        )

    # ── Sprint 12: source ingest ─────────────────────────────────

    @app.post(
        "/sources/ingest",
        response_model=IngestSourceResponse,
        status_code=202,
    )
    async def post_ingest_source(
        req: IngestSourceRequest,
    ) -> IngestSourceResponse:
        """Ingest a URL into the substrate graph. Auto-detects source
        kind unless ``req.kind`` is set. Routes to the appropriate
        acquisition adapter (arxiv / youtube / podcast / url).

        Returns 202 immediately if the underlying adapter completes
        synchronously; podcast feeds with multiple episodes can take
        longer but are still synchronous within this handler. For
        very large feeds (>20 episodes) the client should pass
        ``max_episodes`` to cap latency."""
        detected = _detect_source_kind(req.url, req.kind)
        try:
            if detected == "arxiv":
                from acquisition.arxiv import ingest_paper as _ip
                from acquisition.arxiv import fetch_by_id as _fbi
                # Extract the arXiv id from the URL if needed
                arxiv_id = _extract_arxiv_id(req.url)
                if not arxiv_id:
                    raise ValueError(
                        "Could not extract arXiv id from URL"
                    )
                paper = _fbi(arxiv_id)
                if not paper:
                    raise ValueError(
                        f"arXiv paper {arxiv_id!r} not found"
                    )
                kwargs = {"investigation_id": req.investigation_id}
                if req.source_tier is not None:
                    kwargs["source_tier"] = req.source_tier
                r = _ip(paper, **kwargs)
                return IngestSourceResponse(
                    status="ingested" if r.chunks_written > 0 else "skipped",
                    detected_kind="arxiv",
                    document_id=r.document_id,
                    document_loaded_event_id=r.document_loaded_event_id,
                    chunks_written=r.chunks_written,
                    title=paper.title,
                )
            elif detected == "youtube":
                from acquisition.youtube import ingest_youtube
                kwargs = {"investigation_id": req.investigation_id}
                if req.source_tier is not None:
                    kwargs["source_tier"] = req.source_tier
                r = ingest_youtube(req.url, **kwargs)
                return IngestSourceResponse(
                    status=(
                        "ingested" if r.chunks_written > 0
                        else "skipped"
                    ),
                    detected_kind="youtube",
                    document_id=r.document_id,
                    document_loaded_event_id=r.document_loaded_event_id,
                    chunks_written=r.chunks_written,
                    skipped_reason=r.skipped_reason,
                    title=r.title,
                )
            elif detected == "podcast":
                from acquisition.podcasts import ingest_feed
                kwargs = {
                    "investigation_id": req.investigation_id,
                    "max_episodes": req.max_episodes,
                }
                if req.source_tier is not None:
                    kwargs["source_tier"] = req.source_tier
                results = ingest_feed(req.url, **kwargs)
                ingested = sum(1 for r in results if r.chunks_written > 0)
                total_chunks = sum(r.chunks_written for r in results)
                # Report the most recent ingested episode's title as
                # the response title (most useful operator signal).
                title = next(
                    (r.title for r in results if r.chunks_written > 0),
                    results[0].title if results else None,
                )
                return IngestSourceResponse(
                    status="ingested" if ingested > 0 else "skipped",
                    detected_kind="podcast",
                    chunks_written=total_chunks,
                    skipped_reason=(
                        None if ingested > 0 else "no_episodes_with_transcripts"
                    ),
                    title=title,
                    episodes_processed=len(results),
                    episodes_ingested=ingested,
                )
            elif detected == "url":
                from acquisition.urls import ingest_url
                kwargs = {"investigation_id": req.investigation_id}
                if req.source_tier is not None:
                    kwargs["source_tier"] = req.source_tier
                r = ingest_url(req.url, **kwargs)
                return IngestSourceResponse(
                    status=(
                        "ingested" if r.chunks_written > 0
                        else "skipped"
                    ),
                    detected_kind="url",
                    document_id=r.document_id,
                    document_loaded_event_id=r.document_loaded_event_id,
                    chunks_written=r.chunks_written,
                    skipped_reason=r.skipped_reason,
                    title=r.title,
                )
            else:
                raise ValueError(f"unsupported source kind: {detected!r}")
        except Exception as exc:
            return IngestSourceResponse(
                status="error",
                detected_kind=detected or "unknown",
                error_message=f"{type(exc).__name__}: {exc}",
            )

    # ── Sprint 13: deliverables (creation surface) ─────────────────

    def _resolve_db_path() -> str:
        from substrate.graph import default_db_path, ensure_initialized
        path = default_db_path()
        ensure_initialized(path)
        return path

    @app.post("/deliverables", response_model=DeliverableSummary, status_code=201)
    async def post_deliverable(req: CreateDeliverableRequest) -> DeliverableSummary:
        from runtime.db_lock import connect_write
        from substrate.graph.ops import insert_deliverable

        db = _resolve_db_path()
        with connect_write(db, purpose="deliverables/create") as con:
            did = insert_deliverable(
                con,
                title=req.title,
                deliverable_kind=req.deliverable_kind,
                investigation_root_id=req.investigation_root_id,
            )
            row = con.execute(
                "SELECT deliverable_id, title, deliverable_kind, "
                "investigation_root_id, status, "
                "strftime(created_at, '%Y-%m-%dT%H:%M:%S'), "
                "strftime(updated_at, '%Y-%m-%dT%H:%M:%S') "
                "FROM deliverables WHERE deliverable_id = ?", [did],
            ).fetchone()
        return DeliverableSummary(
            deliverable_id=row[0], title=row[1], deliverable_kind=row[2],
            investigation_root_id=row[3], status=row[4],
            created_at=row[5], updated_at=row[6], section_count=0,
        )

    @app.get("/deliverables", response_model=DeliverableListResponse)
    async def list_deliverables(limit: int = 50) -> DeliverableListResponse:
        import duckdb
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            rows = con.execute(
                "SELECT d.deliverable_id, d.title, d.deliverable_kind, "
                "d.investigation_root_id, d.status, "
                "strftime(d.created_at, '%Y-%m-%dT%H:%M:%S'), "
                "strftime(d.updated_at, '%Y-%m-%dT%H:%M:%S'), "
                "(SELECT COUNT(*) FROM deliverable_sections s "
                " WHERE s.deliverable_id = d.deliverable_id) "
                "FROM deliverables d ORDER BY d.created_at DESC LIMIT ?",
                [limit],
            ).fetchall()
        finally:
            con.close()
        return DeliverableListResponse(
            count=len(rows),
            deliverables=[
                DeliverableSummary(
                    deliverable_id=r[0], title=r[1], deliverable_kind=r[2],
                    investigation_root_id=r[3], status=r[4],
                    created_at=r[5], updated_at=r[6], section_count=r[7] or 0,
                ) for r in rows
            ],
        )

    @app.get("/deliverables/{deliverable_id}", response_model=DeliverableDetailResponse)
    async def get_deliverable(deliverable_id: str) -> DeliverableDetailResponse:
        import duckdb
        import json as _json
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            head = con.execute(
                "SELECT deliverable_id, title, deliverable_kind, status "
                "FROM deliverables WHERE deliverable_id = ?", [deliverable_id],
            ).fetchone()
            if head is None:
                raise HTTPException(status_code=404, detail="deliverable not found")
            sec_rows = con.execute(
                "SELECT s.section_id, s.deliverable_id, s.parent_section_id, "
                "s.section_index, s.title, s.prose_text, s.prose_provenance, "
                "(SELECT COUNT(*) FROM section_blocks sb WHERE sb.section_id = s.section_id) "
                "FROM deliverable_sections s WHERE s.deliverable_id = ? "
                "ORDER BY s.section_index ASC", [deliverable_id],
            ).fetchall()
        finally:
            con.close()
        sections = []
        for r in sec_rows:
            prov = None
            if r[6]:
                try:
                    prov = _json.loads(r[6])
                except (ValueError, TypeError):
                    prov = None
            sections.append(SectionResponse(
                section_id=r[0], deliverable_id=r[1],
                parent_section_id=r[2], section_index=r[3], title=r[4],
                prose_text=r[5], prose_provenance=prov,
                block_count=r[7] or 0,
            ))
        return DeliverableDetailResponse(
            deliverable_id=head[0], title=head[1],
            deliverable_kind=head[2], status=head[3], sections=sections,
        )

    @app.post("/sections", response_model=SectionResponse, status_code=201)
    async def post_section(req: CreateSectionRequest) -> SectionResponse:
        from runtime.db_lock import connect_write
        from substrate.graph.ops import insert_section

        db = _resolve_db_path()
        with connect_write(db, purpose="sections/create") as con:
            # Verify deliverable exists
            row = con.execute(
                "SELECT 1 FROM deliverables WHERE deliverable_id = ?",
                [req.deliverable_id],
            ).fetchone()
            if row is None:
                raise HTTPException(
                    status_code=404, detail="deliverable not found",
                )
            sid = insert_section(
                con,
                deliverable_id=req.deliverable_id,
                section_index=req.section_index,
                title=req.title,
                parent_section_id=req.parent_section_id,
            )
        return SectionResponse(
            section_id=sid, deliverable_id=req.deliverable_id,
            parent_section_id=req.parent_section_id,
            section_index=req.section_index, title=req.title,
            prose_text=None, prose_provenance=None, block_count=0,
        )

    @app.post("/sections/attach-block", status_code=202)
    async def post_attach_block(req: AttachBlockRequest) -> dict:
        from runtime.db_lock import connect_write
        from substrate.graph.ops import attach_block_to_section

        db = _resolve_db_path()
        with connect_write(db, purpose="sections/attach_block") as con:
            row = con.execute(
                "SELECT 1 FROM deliverable_sections WHERE section_id = ?",
                [req.section_id],
            ).fetchone()
            if row is None:
                raise HTTPException(
                    status_code=404, detail="section not found",
                )
            attach_block_to_section(
                con,
                section_id=req.section_id,
                block_kind=req.block_kind,
                block_id=req.block_id,
                block_index=req.block_index,
            )
        return {"status": "attached"}

    # ── Sprint 13: voice notes ─────────────────────────────────────

    @app.post(
        "/voice-notes/ingest",
        response_model=VoiceNoteIngestResponse,
        status_code=202,
    )
    async def post_voice_note(req: VoiceNoteIngestRequest) -> VoiceNoteIngestResponse:
        """Ingest a pre-transcribed voice note. The audio-upload path
        (multipart) is a Sprint-13-end stretch goal; for now the
        operator records client-side, transcribes client-side or
        via OpenAI directly, and posts the transcript."""
        from acquisition.voice import ingest_voice_note
        r = ingest_voice_note(
            req.transcript,
            investigation_id=req.investigation_id,
            title=req.title,
            duration_seconds=req.duration_seconds,
            language=req.language,
        )
        return VoiceNoteIngestResponse(
            status=(
                "ingested" if r.chunks_written > 0 else "skipped"
            ),
            document_id=r.document_id,
            document_loaded_event_id=r.document_loaded_event_id,
            chunks_written=r.chunks_written,
            skipped_reason=r.skipped_reason,
            title=r.title,
        )

    # ── WebSocket live tail ─────────────────────────────────────

    @app.websocket("/ws/events")
    async def ws_events(
        ws: WebSocket,
        investigation_id: Optional[str] = Query(default=None),
    ) -> None:
        await ws.accept()
        sub = await bus.subscribe(ws, investigation_id=investigation_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(sub.queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Keepalive — send a ping frame the client can ignore.
                    # FastAPI's WebSocket doesn't have ping built in for
                    # arbitrary clients, so send a no-op JSON object.
                    await ws.send_json({"type": "ping"})
                    continue
                await ws.send_json(event.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        finally:
            await bus.unsubscribe(sub)

    return app


# Default app instance for ``uvicorn interfaces.research.api.app:app``.
app = create_app()
