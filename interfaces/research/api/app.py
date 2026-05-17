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
from typing import Annotated, Optional

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
    correlation."""

    question: str = Field(..., min_length=3)
    context: str = ""
    topic_slug: Optional[str] = None
    max_sub_questions: int = Field(default=8, ge=1, le=20)
    investigation_id: Optional[str] = None


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
            cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
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
        from substrate.schemas import InvestigationStartRequestedPayload
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
