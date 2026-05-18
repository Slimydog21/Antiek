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
    kind: Optional[Literal["arxiv", "youtube", "podcast", "twitter", "url"]] = None
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


# ── Sprint 14: twitter thread ingest + block search + reorder ─────────


class TwitterTweetPayload(BaseModel):
    """One tweet within a captured thread (extension payload)."""

    tweet_id: str = Field(..., min_length=1)
    text: str = Field(default="", max_length=10_000)
    author_handle: str = Field(default="", max_length=64)
    author_verified: bool = False
    posted_at: Optional[str] = None  # ISO 8601
    reply_to: Optional[str] = None
    quote_of: Optional[str] = None
    media_urls: list[str] = Field(default_factory=list)


class TwitterThreadIngestRequest(BaseModel):
    """Browser-extension POST shape for capturing an X thread."""

    thread_url: str = Field(..., min_length=10)
    root_tweet_id: str = Field(..., min_length=1)
    author_handle: str = Field(..., min_length=1, max_length=64)
    tweets: list[TwitterTweetPayload] = Field(..., min_length=1)
    investigation_id: str = Field(default="__operator__", min_length=1)


class TwitterThreadIngestResponse(BaseModel):
    status: Literal["ingested", "skipped"]
    document_id: str
    document_loaded_event_id: Optional[str] = None
    chunks_written: int = 0
    skipped_reason: Optional[str] = None
    title: Optional[str] = None


class BlockSearchHit(BaseModel):
    """One hit from the creation-surface block palette search."""

    block_id: str
    block_kind: Literal["insight", "open_question", "operator_note", "claim"]
    label: str
    body: str
    source_tier: Optional[int] = None
    document_title: Optional[str] = None


class BlockSearchResponse(BaseModel):
    count: int
    hits: list[BlockSearchHit] = Field(default_factory=list)


class ReorderBlockRequest(BaseModel):
    """Move a block within / between sections (Mode C drag-drop)."""

    section_id: str = Field(..., min_length=1)
    block_kind: Literal["insight", "open_question", "operator_note", "claim"]
    block_id: str = Field(..., min_length=1)
    new_section_id: Optional[str] = None  # if None, reorder within section
    new_block_index: int = Field(..., ge=0)


# ── Sprint 15: edit-back-into-graph + export ──────────────────────────


class UpdateSectionProseRequest(BaseModel):
    """PATCH a section's prose. When ``promote_to_graph`` is true, the
    edited prose is also written as a new operator-asserted claim
    node + CLAIM_ASSERTED_BY_OPERATOR event."""

    prose_text: str = Field(..., min_length=1)
    original_text: Optional[str] = None  # what creative_writer produced
    promote_to_graph: bool = False
    cited_chunk_ids: list[str] = Field(default_factory=list)
    investigation_id: str = Field(default="__operator__", min_length=1)


class UpdateSectionProseResponse(BaseModel):
    status: Literal["saved", "saved_and_promoted"]
    section_id: str
    claim_node_id: Optional[str] = None
    claim_event_id: Optional[str] = None


class ExportFormat(BaseModel):
    """Query-side echo of the chosen format. Used in JSON responses for
    /deliverables/{id}/export when the operator wants the raw content
    delivered as JSON."""

    format: Literal["markdown", "html", "json"]
    content: str
    filename: str


# ── Sprint H3: observability ──────────────────────────────────────────


class ProviderRatioBreakdown(BaseModel):
    provider: str
    success_count: int = 0
    error_count: int = 0
    total: int = 0


class ProviderRatioResponse(BaseModel):
    """Operator-facing provider ratio for the last N minutes. Used by
    the bridge-health alerting cron to detect silent Hermes-primary
    failures that the OpenRouter fallback is hiding."""

    window_minutes: int
    total_dispatches: int
    by_provider: list[ProviderRatioBreakdown] = Field(default_factory=list)
    hermes_success_fraction: float = 0.0
    openrouter_fraction: float = 0.0
    alert_recommended: bool = False
    alert_reason: Optional[str] = None


# ── Sprint 16 partial: IP attribution telemetry ───────────────────────


class AttributionAlgorithmShares(BaseModel):
    algorithm: Literal["A", "B", "C"]
    shares: dict[str, float] = Field(default_factory=dict)
    document_titles: dict[str, str] = Field(default_factory=dict)
    document_count: int = 0
    claim_count: int = 0


class AttributionReportResponse(BaseModel):
    synthesis_id: str
    target_question: str
    option_a: AttributionAlgorithmShares
    option_b: AttributionAlgorithmShares
    option_c: AttributionAlgorithmShares


# ── Sprint 16: interview projects + interviews ────────────────────────


class CreateInterviewProjectRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    topic_description: Optional[str] = Field(default=None, max_length=4000)
    deliverable_id: Optional[str] = None
    must_cover: list[str] = Field(default_factory=list)
    framing: Optional[str] = Field(default=None, max_length=4000)


class InterviewProjectSummary(BaseModel):
    project_id: str
    title: str
    topic_description: Optional[str]
    deliverable_id: Optional[str]
    must_cover: list[str] = Field(default_factory=list)
    framing: Optional[str] = None
    interview_count: int = 0
    completed_count: int = 0
    created_at: Optional[str] = None


class InviteInterviewRequest(BaseModel):
    project_id: str
    informant_handle: Optional[str] = Field(default=None, max_length=200)
    informant_email: Optional[str] = Field(default=None, max_length=320)


class InterviewSummary(BaseModel):
    interview_id: str
    project_id: str
    informant_handle: Optional[str]
    informant_email: Optional[str]
    status: Literal[
        "invited", "in_progress", "completed", "declined", "incomplete",
    ]
    invited_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    turn_count: int = 0


class InterviewTurnPayload(BaseModel):
    role: Literal["interviewer", "informant"]
    text: str
    ts: Optional[str] = None


class InterviewDetailResponse(BaseModel):
    interview_id: str
    project_id: str
    project_title: str
    topic_description: Optional[str]
    framing: Optional[str]
    must_cover: list[str]
    status: str
    consent_recorded: bool
    transcript: list[InterviewTurnPayload] = Field(default_factory=list)


class InterviewTurnRequest(BaseModel):
    role: Literal["interviewer", "informant"]
    text: str = Field(..., min_length=1, max_length=20_000)


class InterviewTurnResponse(BaseModel):
    interview_id: str
    turn_count: int
    status: str


class CompleteInterviewRequest(BaseModel):
    transcript_document_id: Optional[str] = None


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
    if "twitter.com" in u or "x.com" in u or "://t.co" in u:
        return "twitter"
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
            # - https://antiek.ai: production web app (canonical apex,
            #   2026-05-18 migration from app.antiek.ai)
            #
            # The app.antiek.ai deprecation alias was removed from this
            # list after the operator deleted the custom domain on the
            # Cloudflare Pages project (2026-05-18). No reachable client
            # should be sending requests from that origin anymore.
            cors_origins = [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "https://antiek.ai",
            ]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ── H4 + H4.5: operator auth middleware ──
    # TWO complementary auth paths, both opt-in via env vars:
    #
    # (1) Cloudflare Access (browser users) — when
    #     ANTIEK_OPERATOR_EMAIL is set, requests carrying a
    #     ``Cf-Access-Authenticated-User-Email`` header that matches
    #     the env value pass. Cloudflare Access injects this header
    #     on requests originating from the operator's authenticated
    #     browser session.
    #
    # (2) Bearer token (machine callers) — when
    #     ANTIEK_OPERATOR_TOKEN is set, requests carrying
    #     ``Authorization: Bearer <token>`` matching the env pass.
    #     This is for probes (smoke runs, health checks), ops
    #     scripts, and any non-browser client.
    #
    # When BOTH env vars are unset, enforcement is bypassed and the
    # API is open (existing tests + local dev unchanged). When one
    # is set, requests must pass that path or be rejected. When
    # both are set, either path suffices.
    #
    # Why both:
    # - Cloudflare Access alone leaves the substrate unauth'd for
    #   ops scripts / health probes / CI smokes. Cloudflare Access
    #   service tokens exist but are heavier than a static bearer
    #   for a single-operator deployment.
    # - Bearer alone forces the token into the web app's JS bundle
    #   (where it's visible to anyone with view-source — not
    #   actually private). Routing browser auth through Cloudflare
    #   Access is the architecturally correct path.
    #
    # Multi-tenant trajectory (Sprint 19+): replace the
    # ANTIEK_OPERATOR_EMAIL match with an email-to-tenant-ID lookup
    # and add per-tenant bearer tokens. Same middleware shape;
    # additive change.
    #
    # SECURITY NOTE: ``Cf-Access-Authenticated-User-Email`` is a
    # plain header. A direct caller to the Hetzner IP (bypassing
    # Cloudflare) could spoof it. This is mitigated by:
    # (a) Caddy origin restriction to Cloudflare edge IPs (H4.6
    #     follow-on; not yet implemented).
    # (b) The bearer path provides credential-based auth that
    #     can't be spoofed by header injection.
    # Until (a) lands, treat this as defense-in-depth, not the
    # sole gate.
    _OPERATOR_AUTH_OPEN_PATHS: set[str] = {"/health"}
    _OPERATOR_TOKEN_ENV = "ANTIEK_OPERATOR_TOKEN"
    _OPERATOR_EMAIL_ENV = "ANTIEK_OPERATOR_EMAIL"
    _CF_ACCESS_EMAIL_HEADER = "Cf-Access-Authenticated-User-Email"

    @app.middleware("http")
    async def _operator_auth_middleware(request, call_next):
        expected_token = os.environ.get(_OPERATOR_TOKEN_ENV, "").strip()
        expected_email = os.environ.get(_OPERATOR_EMAIL_ENV, "").strip().lower()
        if not expected_token and not expected_email:
            # Enforcement disabled. Existing tests + local dev
            # work unchanged.
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path in _OPERATOR_AUTH_OPEN_PATHS:
            return await call_next(request)

        # Path 1: Cloudflare Access email header
        if expected_email:
            cf_email = request.headers.get(
                _CF_ACCESS_EMAIL_HEADER, "",
            ).strip().lower()
            if cf_email and cf_email == expected_email:
                return await call_next(request)

        # Path 2: Bearer token
        if expected_token:
            auth = request.headers.get("Authorization", "")
            scheme, _, token = auth.partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                import secrets as _secrets
                if _secrets.compare_digest(token.strip(), expected_token):
                    return await call_next(request)

        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": (
                        "Authentication required. Either Cloudflare "
                        "Access (browser) or "
                        "Authorization: Bearer <token> (machine)."
                    ),
                    "code": "operator_auth_required",
                }
            },
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
            elif detected == "twitter":
                # The URL alone is insufficient for X — the auth wall
                # blocks direct fetch. Tell the operator to use the
                # browser extension's POST /sources/twitter endpoint
                # instead. This keeps /sources/ingest honest about
                # what it can synchronously do.
                return IngestSourceResponse(
                    status="error",
                    detected_kind="twitter",
                    error_message=(
                        "X threads cannot be ingested by URL alone "
                        "(auth wall). Use the browser extension at "
                        "apps/x-extension/ which POSTs to "
                        "/sources/twitter with the captured thread."
                    ),
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

    # ── Sprint 14: block search + reorder + twitter ─────────────────

    @app.get("/blocks/search", response_model=BlockSearchResponse)
    async def block_search(
        q: str = Query(default="", max_length=200),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> BlockSearchResponse:
        """Search the operator's graph for insight/claim/note blocks to
        drag into a deliverable section. Mode C palette uses this.

        Sprint 14 implementation: ILIKE over nodes.canonical_label +
        metadata. Sprint 15 swaps in cosine search via the embedding
        column so semantic matches surface."""
        import duckdb
        db = _resolve_db_path()
        like = f"%{q}%" if q.strip() else "%"
        con = duckdb.connect(db, read_only=True)
        try:
            rows = con.execute(
                "SELECT n.node_id, n.canonical_label, n.node_type, "
                "       n.metadata, d.title, d.source_tier "
                "FROM nodes n "
                "LEFT JOIN chunks c ON ("
                "    CAST(json_extract_string(n.metadata, '$.chunk_id') AS VARCHAR) = c.chunk_id"
                ") "
                "LEFT JOIN documents d ON c.document_id = d.document_id "
                "WHERE n.canonical_label ILIKE ? "
                "ORDER BY n.created_at DESC LIMIT ?",
                [like, limit],
            ).fetchall()
        finally:
            con.close()
        hits: list[BlockSearchHit] = []
        for r in rows:
            hits.append(BlockSearchHit(
                block_id=r[0],
                block_kind="insight",  # all node rows surface as 'insight' here
                label=r[1] or "(no label)",
                body=r[1] or "",
                source_tier=r[5],
                document_title=r[4],
            ))
        return BlockSearchResponse(count=len(hits), hits=hits)

    @app.post("/sections/reorder-block", status_code=202)
    async def post_reorder_block(req: ReorderBlockRequest) -> dict:
        """Move a block within a section, or to a new section.

        Implementation note: section_blocks has a composite PK
        ``(section_id, block_kind, block_id)``. Moving to a new
        section requires DELETE + INSERT under the same lock."""
        from runtime.db_lock import connect_write
        db = _resolve_db_path()
        target_section = req.new_section_id or req.section_id
        with connect_write(db, purpose="sections/reorder") as con:
            # Validate target section exists
            row = con.execute(
                "SELECT 1 FROM deliverable_sections WHERE section_id = ?",
                [target_section],
            ).fetchone()
            if row is None:
                raise HTTPException(
                    status_code=404, detail="target section not found",
                )
            # If moving across sections, DELETE old + INSERT new
            if (
                req.new_section_id is not None
                and req.new_section_id != req.section_id
            ):
                con.execute(
                    "DELETE FROM section_blocks WHERE section_id = ? "
                    "AND block_kind = ? AND block_id = ?",
                    [req.section_id, req.block_kind, req.block_id],
                )
                con.execute(
                    "INSERT INTO section_blocks "
                    "(section_id, block_kind, block_id, block_index) "
                    "VALUES (?, ?, ?, ?)",
                    [target_section, req.block_kind, req.block_id,
                     int(req.new_block_index)],
                )
            else:
                # In-section reorder: just bump the index
                con.execute(
                    "UPDATE section_blocks SET block_index = ? "
                    "WHERE section_id = ? AND block_kind = ? AND block_id = ?",
                    [int(req.new_block_index), req.section_id,
                     req.block_kind, req.block_id],
                )
        return {"status": "reordered"}

    @app.post(
        "/sources/twitter",
        response_model=TwitterThreadIngestResponse,
        status_code=202,
    )
    async def post_twitter_thread(
        req: TwitterThreadIngestRequest,
    ) -> TwitterThreadIngestResponse:
        """Ingest a captured X thread. The browser extension at
        ``apps/x-extension/`` POSTs to this endpoint with the DOM-
        extracted thread content."""
        from acquisition.twitter import ingest_thread_payload
        payload = req.model_dump()
        investigation_id = payload.pop("investigation_id")
        r = ingest_thread_payload(payload, investigation_id=investigation_id)
        return TwitterThreadIngestResponse(
            status=(
                "ingested" if r.chunks_written > 0 else "skipped"
            ),
            document_id=r.document_id,
            document_loaded_event_id=r.document_loaded_event_id,
            chunks_written=r.chunks_written,
            skipped_reason=r.skipped_reason,
            title=r.title,
        )

    # ── Sprint 15: section prose update + promote-to-graph ─────────

    @app.patch(
        "/sections/{section_id}/prose",
        response_model=UpdateSectionProseResponse,
        status_code=202,
    )
    async def patch_section_prose(
        section_id: str, req: UpdateSectionProseRequest,
    ) -> UpdateSectionProseResponse:
        """Save edited prose for a section. Optionally promote the edit
        to a first-class operator-asserted claim in the graph (master
        spec §10.4 Option B)."""
        from runtime.db_lock import connect_write
        from substrate.event_log import emit_typed
        from substrate.graph.ops import insert_node, update_section_prose
        from substrate.schemas import ClaimAssertedByOperatorPayload

        db = _resolve_db_path()
        with connect_write(db, purpose="sections/prose_update") as con:
            row = con.execute(
                "SELECT deliverable_id FROM deliverable_sections "
                "WHERE section_id = ?", [section_id],
            ).fetchone()
            if row is None:
                raise HTTPException(
                    status_code=404, detail="section not found",
                )
            deliverable_id = row[0]
            update_section_prose(
                con, section_id=section_id, prose_text=req.prose_text,
            )
            claim_node_id: Optional[str] = None
            if req.promote_to_graph:
                # Use the section title + first line of the prose as
                # the claim's canonical label (keeps it indexable).
                label = req.prose_text.strip().splitlines()[0]
                if len(label) > 160:
                    label = label[:159] + "…"
                claim_node_id = insert_node(
                    con,
                    canonical_label=label,
                    node_type="claim",
                    graph_scope="cross_domain",
                    investigation_id=req.investigation_id,
                    metadata={
                        "source": "operator_asserted",
                        "deliverable_id": deliverable_id,
                        "section_id": section_id,
                        "policy_id": f"operator/{deliverable_id}",
                        "cited_chunk_ids": req.cited_chunk_ids,
                    },
                    on_conflict="ignore",
                )

        claim_event_id: Optional[str] = None
        if req.promote_to_graph and claim_node_id is not None:
            # Source tier: default 5 (unsupported) unless the operator
            # explicitly attached chunk citations. Even with citations
            # we keep it at tier 5 until the grounder verifies — the
            # grounder demotes the tier on success.
            payload = ClaimAssertedByOperatorPayload(
                deliverable_id=deliverable_id,
                section_id=section_id,
                claim_text=req.prose_text,
                original_text=req.original_text,
                node_id=claim_node_id,
                source_tier=5,
                cited_chunk_ids=req.cited_chunk_ids,
            )
            claim_event_id = emit_typed(
                req.investigation_id, payload,
                role="creation_surface",
                policy_id=f"operator/{deliverable_id}",
            )
            return UpdateSectionProseResponse(
                status="saved_and_promoted",
                section_id=section_id,
                claim_node_id=claim_node_id,
                claim_event_id=claim_event_id,
            )
        return UpdateSectionProseResponse(
            status="saved", section_id=section_id,
        )

    @app.get("/deliverables/{deliverable_id}/export")
    async def export_deliverable(
        deliverable_id: str,
        format: str = Query(default="markdown"),
    ) -> ExportFormat:
        """Export a deliverable as Markdown, HTML, or a structured JSON
        bundle. Returns the content inline (the caller can save it via
        the Blob API in the browser). The substrate keeps no
        notion of "rendered files" — every export is a fresh derivation
        from the section rows."""
        if format not in ("markdown", "html", "json"):
            raise HTTPException(
                status_code=422,
                detail=f"format must be markdown|html|json, got {format!r}",
            )
        import duckdb
        import json as _json
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            head = con.execute(
                "SELECT title, deliverable_kind FROM deliverables "
                "WHERE deliverable_id = ?", [deliverable_id],
            ).fetchone()
            if head is None:
                raise HTTPException(
                    status_code=404, detail="deliverable not found",
                )
            secs = con.execute(
                "SELECT section_index, title, prose_text "
                "FROM deliverable_sections WHERE deliverable_id = ? "
                "ORDER BY section_index ASC", [deliverable_id],
            ).fetchall()
        finally:
            con.close()
        title = head[0]
        kind = head[1]
        if format == "markdown":
            lines = [f"# {title}", "", f"_{kind}_", ""]
            for idx, sec_title, prose in secs:
                lines.append(f"## {sec_title or f'Section {idx + 1}'}")
                lines.append("")
                lines.append((prose or "_(no prose yet)_").strip())
                lines.append("")
            content = "\n".join(lines)
            return ExportFormat(
                format="markdown", content=content,
                filename=f"{deliverable_id}.md",
            )
        if format == "html":
            esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            parts = [
                "<!doctype html>",
                f"<html><head><meta charset='utf-8'><title>{esc(title)}</title></head><body>",
                f"<h1>{esc(title)}</h1>",
                f"<p><em>{esc(kind)}</em></p>",
            ]
            for idx, sec_title, prose in secs:
                heading = sec_title or f"Section {idx + 1}"
                parts.append(f"<h2>{esc(heading)}</h2>")
                if prose:
                    for para in prose.split("\n\n"):
                        parts.append(f"<p>{esc(para)}</p>")
                else:
                    parts.append("<p><em>(no prose yet)</em></p>")
            parts.append("</body></html>")
            content = "\n".join(parts)
            return ExportFormat(
                format="html", content=content,
                filename=f"{deliverable_id}.html",
            )
        # format == "json"
        bundle = {
            "deliverable_id": deliverable_id,
            "title": title,
            "deliverable_kind": kind,
            "sections": [
                {
                    "section_index": idx,
                    "title": sec_title,
                    "prose_text": prose,
                }
                for idx, sec_title, prose in secs
            ],
        }
        return ExportFormat(
            format="json", content=_json.dumps(bundle, indent=2),
            filename=f"{deliverable_id}.json",
        )

    # ── Sprint H3: observability ───────────────────────────────────

    @app.get("/ops/provider-ratio", response_model=ProviderRatioResponse)
    async def get_provider_ratio(
        window_minutes: int = Query(default=15, ge=1, le=1440),
        openrouter_alert_threshold: float = Query(default=0.10, ge=0.0, le=1.0),
    ) -> ProviderRatioResponse:
        """Aggregate dispatch.call events in the last ``window_minutes``
        and surface per-provider success/error counts. An alerting cron
        polls this endpoint and routes to a webhook when
        ``alert_recommended=True`` — typical signal that the bridge has
        gone silent and OpenRouter is silently carrying inference."""
        import os as _os
        import json as _json
        from datetime import datetime, timezone, timedelta
        from substrate.event_log import default_events_dir

        events_dir = default_events_dir()
        if not _os.path.isdir(events_dir):
            return ProviderRatioResponse(
                window_minutes=window_minutes, total_dispatches=0,
            )
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

        per_provider: dict[str, dict[str, int]] = {}
        total = 0
        for filename in _os.listdir(events_dir):
            if not filename.endswith(".jsonl"):
                continue
            path = _os.path.join(events_dir, filename)
            try:
                stat_mtime = datetime.fromtimestamp(
                    _os.path.getmtime(path), tz=timezone.utc,
                )
            except OSError:
                continue
            # Skip files entirely older than the cutoff window — saves
            # an open() on the long tail of historical investigations.
            if stat_mtime < cutoff:
                continue
            try:
                with open(path, "r") as fp:
                    for line in fp:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = _json.loads(line)
                        except _json.JSONDecodeError:
                            continue
                        if ev.get("action_type") != "dispatch.call":
                            continue
                        ts_str = ev.get("created_at") or ev.get("ts")
                        if ts_str:
                            try:
                                ts = datetime.fromisoformat(
                                    ts_str.replace("Z", "+00:00")
                                )
                                if ts.tzinfo is None:
                                    ts = ts.replace(tzinfo=timezone.utc)
                                if ts < cutoff:
                                    continue
                            except (ValueError, TypeError):
                                pass
                        payload = ev.get("payload") or {}
                        provider = str(payload.get("provider") or "unknown")
                        finish = str(payload.get("finish_reason") or "")
                        bucket = per_provider.setdefault(
                            provider, {"success": 0, "error": 0},
                        )
                        if finish == "error":
                            bucket["error"] += 1
                        else:
                            bucket["success"] += 1
                        total += 1
            except OSError:
                continue

        breakdown = []
        for provider in sorted(per_provider):
            b = per_provider[provider]
            breakdown.append(ProviderRatioBreakdown(
                provider=provider,
                success_count=b["success"],
                error_count=b["error"],
                total=b["success"] + b["error"],
            ))

        hermes_b = per_provider.get("hermes", {"success": 0, "error": 0})
        or_b = per_provider.get("openrouter", {"success": 0, "error": 0})
        hermes_success = hermes_b["success"]
        openrouter_total = or_b["success"] + or_b["error"]

        hermes_success_fraction = (
            hermes_success / total if total > 0 else 0.0
        )
        openrouter_fraction = (
            openrouter_total / total if total > 0 else 0.0
        )

        alert = False
        reason: Optional[str] = None
        # Two trigger shapes the operator cares about:
        # 1. Heavy openrouter usage (bridge silently failing) — primary
        #    signal that Hermes-primary has dropped out.
        # 2. NO recent dispatches at all when there should have been —
        #    can't distinguish "operator inactive" from "substrate
        #    silently broken" without a baseline; leave that to the
        #    bridge-health probe.
        if total > 0 and openrouter_fraction > openrouter_alert_threshold:
            alert = True
            reason = (
                f"openrouter handled {openrouter_fraction:.0%} of "
                f"{total} dispatches in the last {window_minutes}m "
                f"(threshold {openrouter_alert_threshold:.0%}). "
                f"Hermes-primary is likely silently failing."
            )

        return ProviderRatioResponse(
            window_minutes=window_minutes,
            total_dispatches=total,
            by_provider=breakdown,
            hermes_success_fraction=hermes_success_fraction,
            openrouter_fraction=openrouter_fraction,
            alert_recommended=alert,
            alert_reason=reason,
        )

    # ── Sprint 16 partial: attribution telemetry ───────────────────

    @app.get(
        "/attribution/synthesis/{synthesis_id}",
        response_model=AttributionReportResponse,
    )
    async def get_attribution_report(
        synthesis_id: str,
        emit_event: bool = Query(default=False),
    ) -> AttributionReportResponse:
        """Compute attribution shares for a synthesis under all three
        algorithms (master spec §9.3). Phase 1 = telemetry only; no
        payouts attached to the result. When ``emit_event=true``, the
        compute pipeline also writes a ``page.attribution.computed``
        event to the log so the operator can replay the computation
        history later."""
        from substrate.attribution import compute_attribution_for_synthesis
        try:
            r = compute_attribution_for_synthesis(
                synthesis_id, emit_event=emit_event,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

        def _to_resp(algo, result) -> AttributionAlgorithmShares:
            return AttributionAlgorithmShares(
                algorithm=algo,
                shares=dict(result.shares),
                document_titles=dict(result.document_titles),
                document_count=result.document_count,
                claim_count=result.claim_count,
            )

        return AttributionReportResponse(
            synthesis_id=r.synthesis_id,
            target_question=r.target_question,
            option_a=_to_resp("A", r.option_a),
            option_b=_to_resp("B", r.option_b),
            option_c=_to_resp("C", r.option_c),
        )

    # ── Sprint 16: interview projects + interviews ─────────────────

    @app.post(
        "/interview-projects",
        response_model=InterviewProjectSummary,
        status_code=201,
    )
    async def post_interview_project(
        req: CreateInterviewProjectRequest,
    ) -> InterviewProjectSummary:
        from runtime.db_lock import connect_write
        from substrate.graph.ops import insert_interview_project
        import json as _json

        db = _resolve_db_path()
        guide = {
            "must_cover": req.must_cover,
            "framing": req.framing or "",
        }
        with connect_write(db, purpose="interview_projects/create") as con:
            pid = insert_interview_project(
                con,
                title=req.title,
                topic_description=req.topic_description,
                deliverable_id=req.deliverable_id,
                interview_guide=guide,
            )
            row = con.execute(
                "SELECT title, topic_description, deliverable_id, "
                "strftime(created_at, '%Y-%m-%dT%H:%M:%S') "
                "FROM interview_projects WHERE project_id = ?", [pid],
            ).fetchone()
        return InterviewProjectSummary(
            project_id=pid, title=row[0], topic_description=row[1],
            deliverable_id=row[2], must_cover=req.must_cover,
            framing=req.framing, created_at=row[3],
        )

    @app.get(
        "/interview-projects",
        response_model=list[InterviewProjectSummary],
    )
    async def list_interview_projects() -> list[InterviewProjectSummary]:
        import duckdb
        import json as _json
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            rows = con.execute(
                "SELECT p.project_id, p.title, p.topic_description, "
                "p.deliverable_id, p.interview_guide, "
                "strftime(p.created_at, '%Y-%m-%dT%H:%M:%S'), "
                "(SELECT COUNT(*) FROM interviews i WHERE i.project_id = p.project_id), "
                "(SELECT COUNT(*) FROM interviews i WHERE i.project_id = p.project_id AND i.status = 'completed') "
                "FROM interview_projects p ORDER BY p.created_at DESC",
            ).fetchall()
        finally:
            con.close()
        out: list[InterviewProjectSummary] = []
        for r in rows:
            guide = {}
            if r[4]:
                try:
                    guide = _json.loads(r[4])
                except (ValueError, TypeError):
                    guide = {}
            out.append(InterviewProjectSummary(
                project_id=r[0], title=r[1], topic_description=r[2],
                deliverable_id=r[3],
                must_cover=list(guide.get("must_cover") or []),
                framing=guide.get("framing"),
                created_at=r[5],
                interview_count=int(r[6] or 0),
                completed_count=int(r[7] or 0),
            ))
        return out

    @app.post(
        "/interviews",
        response_model=InterviewSummary,
        status_code=201,
    )
    async def post_invite_interview(req: InviteInterviewRequest) -> InterviewSummary:
        from runtime.db_lock import connect_write
        from substrate.graph.ops import insert_interview

        db = _resolve_db_path()
        with connect_write(db, purpose="interviews/invite") as con:
            project_row = con.execute(
                "SELECT 1 FROM interview_projects WHERE project_id = ?",
                [req.project_id],
            ).fetchone()
            if project_row is None:
                raise HTTPException(
                    status_code=404, detail="interview project not found",
                )
            iid = insert_interview(
                con,
                project_id=req.project_id,
                informant_handle=req.informant_handle,
                informant_email=req.informant_email,
            )
            row = con.execute(
                "SELECT informant_handle, informant_email, status, "
                "strftime(invited_at, '%Y-%m-%dT%H:%M:%S') "
                "FROM interviews WHERE interview_id = ?", [iid],
            ).fetchone()
        return InterviewSummary(
            interview_id=iid, project_id=req.project_id,
            informant_handle=row[0], informant_email=row[1],
            status=row[2], invited_at=row[3], turn_count=0,
        )

    @app.get(
        "/interviews/{interview_id}",
        response_model=InterviewDetailResponse,
    )
    async def get_interview(interview_id: str) -> InterviewDetailResponse:
        import duckdb
        import json as _json
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            row = con.execute(
                "SELECT i.interview_id, i.project_id, i.status, "
                "i.consent_recorded, i.transcript_turns, "
                "p.title, p.topic_description, p.interview_guide "
                "FROM interviews i "
                "JOIN interview_projects p ON i.project_id = p.project_id "
                "WHERE i.interview_id = ?", [interview_id],
            ).fetchone()
        finally:
            con.close()
        if row is None:
            raise HTTPException(status_code=404, detail="interview not found")
        guide = {}
        if row[7]:
            try:
                guide = _json.loads(row[7])
            except (ValueError, TypeError):
                pass
        turns = []
        if row[4]:
            try:
                raw_turns = _json.loads(row[4])
                turns = [
                    InterviewTurnPayload(**t) for t in raw_turns if isinstance(t, dict)
                ]
            except (ValueError, TypeError):
                turns = []
        return InterviewDetailResponse(
            interview_id=row[0], project_id=row[1],
            project_title=row[5], topic_description=row[6],
            framing=guide.get("framing"),
            must_cover=list(guide.get("must_cover") or []),
            status=row[2],
            consent_recorded=bool(row[3]),
            transcript=turns,
        )

    @app.post(
        "/interviews/{interview_id}/turn",
        response_model=InterviewTurnResponse,
        status_code=202,
    )
    async def post_interview_turn(
        interview_id: str, req: InterviewTurnRequest,
    ) -> InterviewTurnResponse:
        from runtime.db_lock import connect_write
        from substrate.graph.ops import append_interview_turn

        db = _resolve_db_path()
        with connect_write(db, purpose="interviews/turn") as con:
            try:
                count = append_interview_turn(
                    con,
                    interview_id=interview_id,
                    role=req.role,
                    text=req.text,
                )
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc))
            (status,) = con.execute(
                "SELECT status FROM interviews WHERE interview_id = ?",
                [interview_id],
            ).fetchone()
        return InterviewTurnResponse(
            interview_id=interview_id, turn_count=count, status=status,
        )

    @app.post(
        "/interviews/{interview_id}/complete",
        response_model=InterviewSummary,
        status_code=202,
    )
    async def post_complete_interview(
        interview_id: str, req: CompleteInterviewRequest,
    ) -> InterviewSummary:
        from runtime.db_lock import connect_write
        from substrate.graph.ops import complete_interview

        db = _resolve_db_path()
        with connect_write(db, purpose="interviews/complete") as con:
            row = con.execute(
                "SELECT 1 FROM interviews WHERE interview_id = ?",
                [interview_id],
            ).fetchone()
            if row is None:
                raise HTTPException(
                    status_code=404, detail="interview not found",
                )
            complete_interview(
                con,
                interview_id=interview_id,
                transcript_document_id=req.transcript_document_id,
            )
            r = con.execute(
                "SELECT project_id, informant_handle, informant_email, "
                "status, strftime(invited_at, '%Y-%m-%dT%H:%M:%S'), "
                "strftime(started_at, '%Y-%m-%dT%H:%M:%S'), "
                "strftime(completed_at, '%Y-%m-%dT%H:%M:%S'), "
                "transcript_turns "
                "FROM interviews WHERE interview_id = ?", [interview_id],
            ).fetchone()
        import json as _json
        turn_count = 0
        if r[7]:
            try:
                turn_count = len(_json.loads(r[7]))
            except (ValueError, TypeError):
                turn_count = 0
        return InterviewSummary(
            interview_id=interview_id, project_id=r[0],
            informant_handle=r[1], informant_email=r[2], status=r[3],
            invited_at=r[4], started_at=r[5], completed_at=r[6],
            turn_count=turn_count,
        )

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
