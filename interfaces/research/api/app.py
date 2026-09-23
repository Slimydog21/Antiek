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
import contextlib
import hashlib
import json
import os
import sys
import threading
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated, Any, Literal

if TYPE_CHECKING:
    from orchestration.cascade_session import CascadeSession
    from orchestration.session_evidence_pack import SessionEvidencePack
    from substrate.attribution.compute import AttributionResult
    from substrate.auth import SessionClaims
    from substrate.billing.aggregator import BillingAggregate
    from substrate.ip_holders import IpHolder
    from substrate.notebooks import Notebook

from fastapi import (
    Body,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError

# Ensure package root on path for direct uvicorn invocation.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from roles.thought_partner import (  # noqa: E402
    THOUGHT_PARTNER_SYSTEM_PROMPT,
    compose_thought_partner_prompt,
    parse_thought_partner_response,
)
from substrate.constants import ANTIEK_PARAM_VERSION  # noqa: E402
from substrate.dispatch import ProviderError, dispatch  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.graph import default_db_path  # noqa: E402
from substrate.graph.health import DuckDBHealth, probe_duckdb_health  # noqa: E402
from substrate.schemas import (  # noqa: E402
    EVENT_SCHEMA_VERSION,
    WRESTLING_ACTION_TYPES,
    DispatchCallPayload,
    Event,
    TypedPayload,
)

from .account_memory_context import account_memory_context  # noqa: E402
from .broadcast import EventBroadcaster  # noqa: E402
from .operator_allowlist import operator_allowlist_from_env  # noqa: E402

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class TypedEventEnvelope(BaseModel):
    """POST body for ``/events/typed``. The ``payload`` field uses the
    discriminated TypedPayload union — the ``action_type`` field on the
    payload tells Pydantic which variant to validate against."""

    investigation_id: str = Field(..., min_length=1)
    payload: TypedPayload
    document_id: str | None = None
    synthesis_id: str | None = None
    phase: int | None = Field(default=None, ge=1, le=9)
    role: str | None = None
    policy_id: str | None = None
    parent_event_id: str | None = None


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
    # DRW honest-failure: True when at least one dispatch provider registered.
    providers_ready: bool = False
    # Which gather backend the DRW cascade would build: "stub" (no real
    # retrieval), "exa" (live Exa Wedge-1), "contained" (execution backend),
    # or "conflict" (mutually exclusive flags — _gather_loop raises). Prod
    # had no outside signal for this: ansible renders ANTIEK_DRW_GATHER
    # EMPTY, which resolves to the stub, so a deploy could do no retrieval
    # while the smoke runbook read green.
    drw_gather_mode: str = "unknown"
    # SPR-07 (antiek-foundation-v2): the commit SHA the running process was
    # built from, so the prod-parity check (tools/prod_parity/check.py) can
    # assert deployed-SHA == main-SHA. Sourced (in order) from the
    # ANTIEK_BUILD_SHA env the deploy stamps, a git rev-parse of the local
    # checkout for local dev, then the literal "unknown". See
    # ``_resolve_build_sha`` below.
    build_sha: str = "unknown"
    # SPR-11 (antiek-flywheel-foundation): is the research-DEPTH flywheel
    # ALIVE on this process? True iff (a) the personal graph DB opens
    # read-only AND (b) the event log reports >= 1 ``knowledge.reused``
    # event — i.e. at least one investigation has retrieved + reused a
    # prior knowledge unit, the observable signature of compounding. The
    # prod-parity check (tools/prod_parity/check.py) reads this so a
    # deployed-but-DEAD flywheel reds the deploy assert, not just a stale
    # SHA or an empty provider registry. ``knowledge_reuse_count`` is the
    # raw count behind the boolean (0 when the flywheel is not yet live).
    # Resolved by ``_probe_flywheel`` on the FIRST /health request and then
    # memoized (deferred from construction so importing this module doesn't
    # scan the event log — see create_app). NEVER raises: any failure
    # resolves to False/0, mirroring ``_resolve_build_sha``'s swallow-to-
    # "unknown". Default False so /health is honest on a box that has never
    # compounded (and before the first probe).
    flywheel_ready: bool = False
    knowledge_reuse_count: int = 0
    # TurboPuffer SERVABLE hybrid (dogfood) — honest, never faked.
    # hybrid_ready requires env+key+active pointer; production_default_mount
    # stays False until deliberately flipped in a future decision.
    turbopuffer_servable_enabled: bool = False
    turbopuffer_shadow_enabled: bool = False
    turbopuffer_api_key_present: bool = False
    turbopuffer_active_pointer: bool = False
    turbopuffer_pointer_context_ok: bool | None = None
    turbopuffer_hybrid_ready: bool = False
    turbopuffer_resolved_kind: str = "brute_force"
    turbopuffer_indexed_row_count: int | None = None
    turbopuffer_content_hash: str | None = None
    # bool | None, not bool: None means the probe could not determine it.
    # These were `bool = True`, so a FAILED probe still reported both as
    # satisfied — two claims asserted exactly when nothing had checked them.
    turbopuffer_duckdb_is_sot: bool | None = None
    turbopuffer_thought_partner_hybrid_wired: bool | None = None
    turbopuffer_production_default_mount: bool = False
    # GF-7: startup read-only health snapshot for the graph DuckDB file.
    # This is intentionally separate from ``status`` so /health can keep
    # responding while surfacing DB corruption/missing-schema/missing-file states.
    duckdb_ready: bool = False
    duckdb_status: str = "unknown"
    duckdb_schema_present: bool = False
    duckdb_database_size_ok: bool = False
    duckdb_integrity_check: str = "not_run"
    duckdb_wal_present: bool = False
    duckdb_wal_bytes: int = 0
    duckdb_error: str | None = None


def _resolve_build_sha() -> str:
    """Resolve the commit SHA the running process was built from.

    SPR-07 (antiek-foundation-v2). Resolution order, first hit wins:

    1. ``ANTIEK_BUILD_SHA`` env — stamped by the deploy (Ansible exports
       the just-pulled ``git_pull.after`` into the service environment).
       This is the authoritative source on prod.
    2. ``git rev-parse HEAD`` of the local checkout — for local dev where
       no deploy stamped the env. Best-effort; swallows any failure
       (no git on PATH, not a checkout) and falls through.
    3. The literal ``"unknown"`` — last resort, so /health never raises.

    Called once at startup (the value is immutable for a process), so the
    git subprocess cost is paid at most once per boot, not per request.
    """
    env_sha = os.environ.get("ANTIEK_BUILD_SHA", "").strip()
    if env_sha:
        return env_sha
    try:
        import subprocess

        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_PKG_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        # No git, not a checkout, or it timed out — fall through to
        # "unknown" rather than failing the whole startup over a SHA.
        pass
    return "unknown"


def _probe_flywheel() -> tuple[bool, int]:
    """Probe whether the research-DEPTH flywheel is ALIVE on this process.

    SPR-11 (antiek-flywheel-foundation). Returns ``(flywheel_ready,
    knowledge_reuse_count)``. The flywheel is "ready" iff BOTH hold:

    1. The personal graph DB opens read-only (``connect_read`` over
       ``default_db_path()``) — the retrieval substrate is reachable.
    2. The event log reports >= 1 ``knowledge.reused`` event — at least
       one investigation has retrieved + reused a prior knowledge unit,
       the observable signature of compounding (the ``knowledge.reused``
       event in ``substrate/schemas/events.py``).

    This is the CHEAP, READ-ONLY liveness signal the prod-parity check
    reads (``flywheel_ready`` on /health): a deployed-but-dead flywheel
    must red the deploy assert, not silently pass.

    Like ``_resolve_build_sha``, this NEVER raises — a missing/locked DB,
    an unreadable events dir, or any other failure resolves to
    ``(False, 0)``. A read-only ``connect_read`` cannot create the file,
    so a fresh box (no graph yet) yields ``(False, 0)`` rather than
    crashing /health. Resolved on the first /health request and memoized (the
    count is a snapshot, not a live counter), so the event-log scan is paid at
    most once — and never merely by importing this module.
    """
    try:
        from runtime.db_lock import connect_read
        from substrate.event_log import action_counts
        from substrate.graph import default_db_path

        # (1) Retrieval substrate reachable: the graph DB opens read-only.
        # connect_read raises on a nonexistent path (read-only cannot
        # create the file), so a box with no graph yet → not ready.
        con = connect_read(default_db_path())
        con.close()

        # (2) >= 1 observable knowledge.reused event. action_counts with no
        # investigation_id scans every trajectory in the default events
        # dir; we sum the knowledge.reused row. An unreadable/empty dir
        # returns [] → count 0 → not ready.
        reused = 0
        for row in action_counts(events_dir=None):
            if row.get("action_type") == "knowledge.reused":
                reused = int(row.get("count", 0) or 0)
                break
        return (reused >= 1, reused)
    except Exception:
        # Any failure (missing/locked DB, unreadable events dir, import
        # error) → the flywheel is not provably live. Resolve to
        # (False, 0) rather than failing the whole /health over a probe,
        # mirroring _resolve_build_sha's swallow-to-"unknown".
        return (False, 0)


def _probe_turbopuffer() -> dict[str, Any]:
    """Cheap TurboPuffer dogfood snapshot for /health (no vendor network)."""
    try:
        from substrate.graph import default_db_path
        from substrate.graph.retrieval_adapters.turbopuffer import (
            probe_turbopuffer_health,
        )

        return probe_turbopuffer_health(db_path=default_db_path())
    except Exception as exc:
        return {
            "servable_enabled": False,
            "shadow_enabled": False,
            "api_key_present": False,
            "active_pointer_file": False,
            "active_pointer_context_ok": None,
            "hybrid_ready": False,
            "resolved_kind": "brute_force",
            "indexed_row_count": None,
            "content_hash": None,
            # Probe unavailable → unknown, not "yes". See the same reasoning
            # in substrate/graph/retrieval_adapters/turbopuffer.py.
            "duckdb_is_sot": None,
            "thought_partner_hybrid_wired": None,
            "production_default_mount": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _probe_graph_duckdb() -> DuckDBHealth:
    """Startup graph DB health probe.

    Unlike the flywheel event-log scan, this is bounded to a single read-only
    DuckDB open plus metadata queries, so it is paid eagerly at app construction.
    It never raises; failures are represented in the returned snapshot.
    """
    try:
        return probe_duckdb_health(default_db_path())
    except Exception as exc:
        return DuckDBHealth(
            ready=False,
            status="probe_exception",
            db_path=os.path.abspath(os.path.expanduser(default_db_path())),
            error=f"{type(exc).__name__}: {exc}",
        )


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
    topic_slug: str | None = None
    max_sub_questions: int = Field(default=8, ge=1, le=20)
    investigation_id: str | None = None
    parent_investigation_id: str | None = None
    spawn_context: str | None = None
    # SPR-01 M3: curated fast/deep research tier from the research entry.
    # CLOSED set; recorded on the start event so the chosen tier is
    # queryable. "fast" → MiMo V2.5 Pro, "deep" → DeepSeek V4 Pro (the
    # tier→provider map lives in substrate/dispatch/research_tier.py).
    #
    # §14.4 measurement-window scoping (default is None, NOT "deep"): the
    # persisted tier is consumed by exactly ONE dispatch role — the
    # synthesizer (`_research_tier_override`) — and the §14.4 window pins the
    # synthesizer to openrouter/claude-opus-4.7 (config.yaml) to gather the
    # Opus-primary syntheses the Sprint-20 verdict needs. A schema-default
    # "deep" would persist on EVERY run and, once DEEPSEEK_API_KEY is set,
    # silently displace that Opus primary with deepseek — corrupting the
    # measurement. So we persist a tier only when the operator EXPLICITLY
    # picks one; None means "no override → use the config-pinned primary".
    # The research-dispatch default of "deep" is unchanged — it is applied at
    # the consumption point via normalize_research_tier(None) → "deep" where a
    # concrete tier is actually needed; only the synthesizer-displacing
    # override is gated on an explicit choice. Reconsider-if: once the §14.4
    # window closes (Sprint 20 verdict landed), the operator may restore a
    # "deep" default if deep-synthesizer routing is then desired.
    research_tier: Literal["fast", "deep"] | None = None
    # Metadata-only source-pack intent from the research entry. Recording this
    # does not launch retrieval or connector calls; runner/source-pack execution
    # must still be explicitly wired through the approved research path.
    source_policy: list[
        Literal["arxiv", "substack", "web", "operator_corpus"]
    ] = Field(default_factory=list)
    # Parsed manually: validation errors must never reflect provider/model values.
    model_choice: object | None = None
    operation_id: object | None = None


# ── Sprint 11 additions ────────────────────────────────────────────────


class ChunkResponse(BaseModel):
    """Response from ``GET /chunks/{chunk_id}``. Used by the web app's
    claim hover modal + SPR-04's named-source render to surface the
    chunk text + source document title for any cited chunk_id.

    ``servable`` carries the §9.0 retrieval-gate verdict to the surface
    so the reader's "open this source" affordance and the data layer
    cannot disagree. The gate applied here is the SAME one
    ``substrate/graph/search.py`` applies to chunk retrieval on a
    non-privileged path: content in the canonical non-privileged denylist
    (``restricted_pending_opt_in`` + ``personal_reading`` via
    ``retrieval_gate``) or under a takedown is withheld; a NULL /
    legacy research chunk passes (grandfathered) exactly as it does in
    chunk search — this is the operator reading their own research
    chunks, not the public "Spotify for books" full-text serve path
    (which is the stricter allowlist in ``substrate/books/serve.py``).
    When ``servable`` is False, ``text`` is withheld (empty string) — a
    restricted source's body never leaves this endpoint, even on a
    direct API call — but the named-source label (title) still resolves
    so the reader sees an honest "not available to open" state rather
    than a blank citation."""

    chunk_id: str
    text: str
    section_path: str | None = None
    token_count: int = 0
    document_id: str
    document_title: str | None = None
    source_tier: int = Field(ge=1, le=5)
    # §9.0: whether this source may be opened on the reading surface.
    # False ⇒ ``text`` is withheld and the surface shows "not available
    # to open". Derived from content_class + takedown, never stored.
    servable: bool = True
    # SPR-10 M1 — "whose work grounds this": the document's IP holder's
    # display name (e.g. "MIT Press"), or null when no owner is resolved
    # (honest "unknown owner", never invented). §9.0: a NON-servable
    # (restricted / taken-down) source does NOT expose its owner — the
    # protected attribution stays withheld with the body. The lifecycle
    # word (pre_onboarded … claimed) rides alongside so the surface frames
    # escrow as opt-in-only (§9.10), never "money waiting" against an
    # unconsenting rights holder.
    ip_holder_name: str | None = None
    ip_holder_status: str | None = None
    # A presentation label for WHY a source is withheld
    # ("restricted" | "taken_down"); null when servable. Lets the surface
    # distinguish the two without re-deriving the gate.
    servability: str | None = None


class InvestigationSummary(BaseModel):
    """One row in the ``GET /investigations`` list response. Carries
    the minimum the web app's sidebar needs to render a tree of past
    investigations."""

    investigation_id: str
    question: str | None = None
    status: str  # "in_progress" | "completed" | "failed" | "not_found"
    started_at: str | None = None  # ISO8601
    completed_at: str | None = None  # ISO8601, terminal events only
    cost_usd_total: float = 0.0
    parent_investigation_id: str | None = None
    # SPR-09 (the compounding flywheel): True when this research was spawned by
    # the §7 continuous daemon (its start event carried the daemon's
    # ``spawn_policy_id``), False for an operator-launched one. The surface
    # translates this into the "found by the loop" badge — the raw policy_id is
    # never sent to the client, only this honest boolean.
    spawned_by_daemon: bool = False


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
    kind: Literal[
        "arxiv", "youtube", "podcast", "twitter", "substack", "url", "inbox"
    ] | None = None
    investigation_id: str = Field(default="__operator__", min_length=1)
    source_tier: int | None = Field(default=None, ge=1, le=5)
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
    document_id: str | None = None
    document_loaded_event_id: str | None = None
    chunks_written: int = 0
    skipped_reason: str | None = None
    error_message: str | None = None
    title: str | None = None
    # For podcast-feed bulk ingest: per-episode summaries
    episodes_processed: int = 0
    episodes_ingested: int = 0


class InvestigationStartResponse(BaseModel):
    """Response from ``POST /investigations`` — the cold-question
    handle the operator polls against ``GET /investigations/{id}``."""

    investigation_id: str
    status: str  # "started"
    start_event_id: str
    operation_id: str | None = None
    owner_model_status: str | None = None
    # ACU soft-warn when near/over managed compute capacity. Null when
    # enforcement=off or within budget. Never invents dollars.
    capacity_warning: dict[str, object] | None = None


class RubricScore(BaseModel):
    """The §14.4 inline-rubric verdict for a synthesis, surfaced so the
    reading surface can flag an answer that may need another pass.

    SPR-11 M3: this is READ from the persisted ``rubric.scored`` event
    the orchestrator emits after Phase 6 — it is NOT recomputed here, and
    the scorer's algorithm is untouched. ``composite`` is the headline
    score in [0, 1] (the event's ``final_score``); the four sub-scores
    ride along when the persisted ``notes`` encode them (the scorer writes
    ``voice=… conviction=… citation_density=… constraint=…``), and are
    null when the note is a free-form one (e.g. the insufficient-evidence
    floor). ``notes`` carries the scorer's own note verbatim.

    When a synthesis has no persisted rubric event, the field carrying
    this model is null — the surface shows no score rather than a
    fabricated one (rigor #1)."""

    composite: float = Field(ge=0.0, le=1.0)
    voice_style: float | None = Field(default=None, ge=0.0, le=1.0)
    conviction: float | None = Field(default=None, ge=0.0, le=1.0)
    citation_density: float | None = Field(default=None, ge=0.0, le=1.0)
    constraint_compliance: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: str = ""


class InvestigationStatusResponse(BaseModel):
    """Response from ``GET /investigations/{id}``. ``status`` is one of:

    - ``not_found`` — no events for this investigation_id at all
    - ``in_progress`` — start event present, no terminal event yet
    - ``completed`` — investigation.completed event present
    - ``failed`` — investigation.failed event present

    ``current_phase`` is the most recent phase the phase_log entered;
    ``last_delivered_action_type`` is the most recent ``*.delivered``
    or terminal event so the operator can see where the chain is in
    flight.

    ``rubric_score`` (SPR-11 M3) is the §14.4 inline-rubric verdict for
    this investigation's synthesis, READ from the persisted
    ``rubric.scored`` event — null when the synthesis has no scored event
    (honest absent, never a fabricated number)."""

    investigation_id: str
    status: str
    current_phase: int | None = None
    last_delivered_action_type: str | None = None
    terminal_payload: dict[str, Any] | None = None
    rubric_score: RubricScore | None = None
    # SPR-01 M3: the curated fast/deep research tier recorded on this
    # investigation's start event ("fast" → MiMo V2.5 Pro, "deep" →
    # DeepSeek V4 Pro). READ from the persisted start payload — this is
    # the "chosen tier is queryable after the fact" acceptance. Null when
    # the start event has no tier (legacy / daemon-spawned runs predate
    # the field); the surface treats null as the default, never fabricates.
    research_tier: str | None = None
    # Source-pack intent recorded on the start event. Empty for legacy runs
    # and for requests that did not choose a source pack; never recomputed.
    source_policy: list[str] = Field(default_factory=list)


# ── Sprint 13: deliverables + voice notes ─────────────────────────────


class CreateDeliverableRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    deliverable_kind: Literal[
        "research_memo", "book_chapter", "biography_section",
        "investor_brief", "general_essay",
    ]
    investigation_root_id: str | None = None


class DeliverableSummary(BaseModel):
    deliverable_id: str
    title: str
    deliverable_kind: str
    investigation_root_id: str | None
    status: str
    created_at: str | None
    updated_at: str | None
    section_count: int = 0


class DeliverableListResponse(BaseModel):
    count: int
    deliverables: list[DeliverableSummary] = Field(default_factory=list)


class CreateSectionRequest(BaseModel):
    deliverable_id: str
    section_index: int = Field(..., ge=0)
    title: str | None = None
    parent_section_id: str | None = None


class AttachBlockRequest(BaseModel):
    section_id: str
    block_kind: Literal["insight", "open_question", "operator_note", "claim"]
    block_id: str
    block_index: int = Field(..., ge=0)


class SectionResponse(BaseModel):
    section_id: str
    deliverable_id: str
    parent_section_id: str | None
    section_index: int
    title: str | None
    prose_text: str | None
    prose_provenance: dict[str, Any] | None
    block_count: int = 0


class DeliverableDetailResponse(BaseModel):
    deliverable_id: str
    title: str
    deliverable_kind: str
    status: str
    # SPR-09 M1: the piece↔research link, surfaced on the detail so the Write
    # header can show the active connection and the canvas can import the
    # linked research's blocks. Reading it back here is how M1 verifies the
    # link EXISTS (not a UI claim) — see docs/decisions/spr-09-*.md (D-1).
    investigation_root_id: str | None = None
    sections: list[SectionResponse] = Field(default_factory=list)


class VoiceNoteIngestRequest(BaseModel):
    """Operator-facing endpoint accepts a pre-transcribed payload OR
    an audio file (multipart). The JSON shape here is for the
    transcript-only path; the audio path uses ``UploadFile``."""

    transcript: str = Field(..., min_length=1)
    investigation_id: str = Field(default="__operator__", min_length=1)
    title: str | None = None
    duration_seconds: float = 0.0
    language: str | None = None


class VoiceNoteIngestResponse(BaseModel):
    status: Literal["ingested", "skipped"]
    document_id: str
    document_loaded_event_id: str | None = None
    chunks_written: int = 0
    skipped_reason: str | None = None
    title: str | None = None


# ── Sprint 14: twitter thread ingest + block search + reorder ─────────


class TwitterTweetPayload(BaseModel):
    """One tweet within a captured thread (extension payload)."""

    tweet_id: str = Field(..., min_length=1)
    text: str = Field(default="", max_length=10_000)
    author_handle: str = Field(default="", max_length=64)
    author_verified: bool = False
    posted_at: str | None = None  # ISO 8601
    reply_to: str | None = None
    quote_of: str | None = None
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
    document_loaded_event_id: str | None = None
    chunks_written: int = 0
    skipped_reason: str | None = None
    title: str | None = None


class BlockSearchHit(BaseModel):
    """One hit from the creation-surface block palette search."""

    block_id: str
    block_kind: Literal["insight", "open_question", "operator_note", "claim"]
    label: str
    body: str
    source_tier: int | None = None
    document_title: str | None = None


class BlockSearchResponse(BaseModel):
    count: int
    hits: list[BlockSearchHit] = Field(default_factory=list)


class ReorderBlockRequest(BaseModel):
    """Move a block within / between sections (Mode C drag-drop)."""

    section_id: str = Field(..., min_length=1)
    block_kind: Literal["insight", "open_question", "operator_note", "claim"]
    block_id: str = Field(..., min_length=1)
    new_section_id: str | None = None  # if None, reorder within section
    new_block_index: int = Field(..., ge=0)


# ── Sprint 15: edit-back-into-graph + export ──────────────────────────


class UpdateSectionProseRequest(BaseModel):
    """PATCH a section's prose. When ``promote_to_graph`` is true, the
    edited prose is also written as a new operator-asserted claim
    node + CLAIM_ASSERTED_BY_OPERATOR event."""

    prose_text: str = Field(..., min_length=1)
    original_text: str | None = None  # what creative_writer produced
    promote_to_graph: bool = False
    cited_chunk_ids: list[str] = Field(default_factory=list)
    investigation_id: str = Field(default="__operator__", min_length=1)


class UpdateSectionProseResponse(BaseModel):
    status: Literal["saved", "saved_and_promoted"]
    section_id: str
    claim_node_id: str | None = None
    claim_event_id: str | None = None


class ExportFormat(BaseModel):
    """Query-side echo of the chosen format. Used in JSON responses for
    /deliverables/{id}/export when the operator wants the raw content
    delivered as JSON.

    Binary formats (``pdf``, ``epub``) ship as base64-encoded strings
    in ``content`` with ``content_encoding="base64"``. Text formats
    (``markdown``, ``html``, ``json``, ``substack``) use the default
    ``content_encoding="text"``. The TS client checks ``content_encoding``
    before constructing a Blob for download.

    Sprint 15 §3.4 binds these six formats: PDF + EPUB are the
    operator-deliverable formats; Substack is the publishing-target
    markdown variant per §8.5.
    """

    format: Literal["markdown", "html", "json", "pdf", "epub", "substack"]
    content: str
    filename: str
    content_encoding: Literal["text", "base64"] = "text"


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
    alert_reason: str | None = None
    # An alarm must be able to say "I could not measure". Without these two,
    # a dead sensor and a quiet system are the SAME payload
    # (total_dispatches=0, alert_recommended=false) and the cron reads silence
    # as health.
    evidence_readable: bool = True
    unreadable_event_files: int = 0


# ── Sprint 16 partial: IP attribution telemetry ───────────────────────


class AttributionAlgorithmShares(BaseModel):
    algorithm: Literal["A", "B", "C"]
    shares: dict[str, float] = Field(default_factory=dict)
    document_titles: dict[str, str] = Field(default_factory=dict)
    document_count: int = 0
    claim_count: int = 0
    # SPR-10 M1 — the provenance chain's last link: document_id → ip_holder_id
    # (or null = unknown owner, never invented). document_ip_holder_status maps
    # an ip_holder_id → its lifecycle word (pre_onboarded … claimed), so the
    # surface can frame escrow as opt-in-only (§9.10). A restricted source never
    # appears here at all — the §9.0 gate excludes it upstream in compute.py.
    document_ip_holders: dict[str, str | None] = Field(default_factory=dict)
    document_ip_holder_status: dict[str, str] = Field(default_factory=dict)


class AttributionReportResponse(BaseModel):
    synthesis_id: str
    target_question: str
    option_a: AttributionAlgorithmShares
    option_b: AttributionAlgorithmShares
    option_c: AttributionAlgorithmShares


# ── Sprint 16: interview projects + interviews ────────────────────────


class CreateInterviewProjectRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    topic_description: str | None = Field(default=None, max_length=4000)
    deliverable_id: str | None = None
    must_cover: list[str] = Field(default_factory=list)
    framing: str | None = Field(default=None, max_length=4000)


class InterviewProjectSummary(BaseModel):
    project_id: str
    title: str
    topic_description: str | None
    deliverable_id: str | None
    must_cover: list[str] = Field(default_factory=list)
    framing: str | None = None
    interview_count: int = 0
    completed_count: int = 0
    created_at: str | None = None


class InviteInterviewRequest(BaseModel):
    project_id: str
    informant_handle: str | None = Field(default=None, max_length=200)
    informant_email: str | None = Field(default=None, max_length=320)


class InterviewSummary(BaseModel):
    interview_id: str
    project_id: str
    informant_handle: str | None
    informant_email: str | None
    status: Literal[
        "invited", "in_progress", "completed", "declined", "incomplete",
    ]
    invited_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    turn_count: int = 0


class InterviewTurnPayload(BaseModel):
    role: Literal["interviewer", "informant"]
    text: str
    ts: str | None = None


class InterviewDetailResponse(BaseModel):
    interview_id: str
    project_id: str
    project_title: str
    topic_description: str | None
    framing: str | None
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
    transcript_document_id: str | None = None


# ---------------------------------------------------------------------------
# Source kind detection (Sprint 12)
# ---------------------------------------------------------------------------


def _detect_source_kind(
    url: str, explicit: str | None = None,
) -> str | None:
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
    if "substack.com" in u:
        return "substack"
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


def _rubric_score_from_trajectory(rows: list[dict[str, Any]]) -> RubricScore | None:
    """READ the §14.4 inline-rubric verdict from a trajectory (SPR-11 M3).

    Walks newest-first for the most recent ``rubric.scored`` event and
    reconstructs a ``RubricScore`` from its persisted payload. This does
    NOT recompute the score and does NOT touch the scorer's algorithm —
    it only reads what ``orchestration/loop_one/orchestrator.py`` already
    emitted via ``middleware.outcomes.emit_rubric_scored`` after Phase 6.

    The persisted payload carries ``final_score`` (the composite) and a
    ``notes`` string. The synthesis rubric writes the four sub-scores into
    that note as ``voice=… conviction=… citation_density=… constraint=…``
    (see the orchestrator's emit call); we parse them back out when
    present so the surface can offer the optional breakdown. When the note
    is free-form (e.g. the insufficient-evidence floor message) the
    sub-scores stay null — honest, never invented.

    Returns ``None`` when the trajectory has no ``rubric.scored`` event,
    so the caller leaves the response field null (no fabricated score)."""
    import re

    for r in reversed(rows):
        payload = r.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("action_type") != "rubric.scored":
            continue
        final = payload.get("final_score")
        if not isinstance(final, (int, float)):
            # A rubric.scored event must carry final_score; a malformed
            # one is treated as no score rather than a guessed value.
            continue
        notes = payload.get("notes")
        notes_str = notes if isinstance(notes, str) else ""

        def _sub(key: str, notes_str: str = notes_str) -> float | None:
            m = re.search(rf"\b{re.escape(key)}=([01](?:\.\d+)?)", notes_str)
            if not m:
                return None
            try:
                v = float(m.group(1))
            except ValueError:
                return None
            return v if 0.0 <= v <= 1.0 else None

        composite = max(0.0, min(1.0, float(final)))
        return RubricScore(
            composite=composite,
            voice_style=_sub("voice"),
            conviction=_sub("conviction"),
            citation_density=_sub("citation_density"),
            constraint_compliance=_sub("constraint"),
            notes=notes_str,
        )
    return None


def _extract_arxiv_id(url: str) -> str | None:
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
# Request models for endpoints registered inside ``create_app``.
#
# These are intentionally module-scope (not nested inside ``create_app``)
# because FastAPI/Pydantic v2's request-body resolver inspects type
# annotations via ``typing.get_type_hints`` which uses the function's
# ``__globals__`` namespace — locally-scoped classes resolve as
# ForwardRefs and trigger ``PydanticUserError: TypeAdapter ... not fully
# defined`` on POST.
# ---------------------------------------------------------------------------


class PublisherCreateRequest(BaseModel):
    display_name: str
    legal_contact_email: str | None = None
    metadata: dict[str, Any] = {}


class NotebookCreateRequest(BaseModel):
    title: str
    investigation_id: str | None = None
    document_id: str | None = None
    content_class: str = "user_owned"


class NotebookAppendBlockRequest(BaseModel):
    block_type: str
    content: dict[str, Any]
    ref_id: str | None = None


class NotebookReorderBlocksRequest(BaseModel):
    """Reorder a notebook's blocks. ``ordered_block_ids`` must be a
    complete permutation of the notebook's current block IDs."""

    ordered_block_ids: list[str]


class NotebookPutContentRequest(BaseModel):
    """Atomic-replace endpoint for the TipTap editor (§4.2 Wedge 2
    notebook surface). Takes the full TipTap ProseMirror document
    JSON; the substrate decomposes it into ``notebook_blocks`` rows.

    Used by the autosave path in the editor; replaces the prior
    localStorage-only persistence.
    """

    doc: dict[str, Any]


class NotebookContentResponse(BaseModel):
    """SPR-01 hydration response for ``GET /notebooks/{id}/content``.

    The editor loads this on mount to seed its document from the
    substrate (rather than from localStorage only) so a fresh browser
    never starts empty over persisted blocks. ``doc`` is the composed
    TipTap ProseMirror document, the exact inverse of the ``PUT`` that
    decomposes it into ``notebook_blocks`` rows."""

    notebook_id: str
    doc: dict[str, Any]


class AIUndoRequest(BaseModel):
    """``POST /ai/undo`` body (§5.5 Wedge 4). The AI sidecar records
    both ids when it emits ``ai.action.applied`` so the undo button
    has both available without an extra lookup."""

    event_id: str
    investigation_id: str


class NotebookUpdateBlockRequest(BaseModel):
    """Edit one block in place. ``block_type`` is intentionally
    immutable here; the UI re-creates blocks rather than re-typing.

    ``content`` (when present) fully replaces ``content_json``.
    ``ref_id`` semantics:
      - present + non-null → set
      - omitted → leave alone
      - ``clear_ref_id=True`` → NULL the column
    """

    content: dict[str, Any] | None = None
    ref_id: str | None = None
    clear_ref_id: bool = False


class QualityGateEvaluationRequest(BaseModel):
    text_content: str
    cited_chunk_tiers: list[int]
    corpus_sector_terms: list[str] = []
    rubric_score: float
    # Optional: when both are present, the endpoint emits the typed
    # ``quality_gate.evaluated`` event so the audit log captures the
    # verdict. Generic ad-hoc evaluations (no target identified) skip
    # event emission to avoid polluting the trajectory.
    target_id: str | None = None
    target_kind: str | None = None  # "notebook" | "synthesis_page" | "creator_note"


class AskExpertsRequest(BaseModel):
    topic_query: str
    investigation_id: str | None = None
    limit: int = 5


class DeletionRequestBody(BaseModel):
    """User-initiated 'delete everything' request (master-spec §13.3).

    The substrate commits to a 30-day SLA from request to completion;
    a 7-day cancellation window lets the user un-request before the
    delete fires."""

    reason: str | None = None


class FederationConfigUpdateRequest(BaseModel):
    """Update the substrate-wide federation config (master-spec
    §13.9 Phase 3). All fields are required so PUTs are explicit
    about the full posture (no partial-replace ambiguity)."""

    allowed_partner_substrates: list[str]
    require_opt_in_for_outbound_citations: bool
    require_attribution_for_outbound_citations: bool


class Loop3ChecklistUpdateRequest(BaseModel):
    """Update one Loop 3 unlock criterion (master-spec §14.2 + §13.7).

    Per the binding gate: criteria-met ≠ training-authorized. Updating
    a criterion here does NOT flip ANTIEK_LOOP3_UNLOCKED — the env
    flip remains the operator's explicit final action."""

    criterion: str  # one of Loop3UnlockCriterion values
    met: bool
    note: str = ""


def _compose_autocomplete_prompt(*, prefix: str, document_context: str | None) -> str:
    """Compose the flash-tier inline-autocomplete prompt (CK-3). The model
    returns ONLY the continuation of ``prefix`` — no preamble, matching the
    voice/vocabulary of the surrounding text. ``document_context`` is the
    client-sent open-doc context (the cursor's neighborhood); retrieval-
    augmented completion (CK-1-style grounding) is a follow-up."""
    context_block = (
        f"DOCUMENT CONTEXT:
{document_context}

" if document_context else ""
    )
    return (
        "You are an inline autocomplete for Antiek's writing surface. "
        "Complete the text after the cursor. Return ONLY the continuation "
        "— no preamble, no quotation marks, no explanation. Match the voice "
        "and vocabulary of the surrounding text.

"
        f"{context_block}"
        f"TEXT BEFORE CURSOR:
{prefix}

"
        "CONTINUATION:"
    )


class CompleteRequest(BaseModel):
    """Inline autocomplete request (CK-3 — the signature Cursor
    writing-flow affordance). The client sends the text around the cursor;
    the substrate dispatches the ``autocomplete`` role on the flash tier
    (GLM-5.2, thinking disabled — fast, direct completions) and returns
    the continuation. Module-level (not nested in create_app) so FastAPI
    can resolve the ``Body(...)`` annotation under PEP 563 string
    annotations — same placement as ``ThoughtPartnerRequest``.

    All client-controlled fields are BOUNDED (the operator-auth gate is
    global, but defense-in-depth caps the cost/latency blast radius of any
    single call): ``max_tokens`` to the inline-completion budget and
    ``document_context`` to a generous cursor-neighborhood cap, so a caller
    cannot amplify cost via an unbounded generation or a multi-MB prompt."""

    prefix: str = Field(..., min_length=1)
    document_context: str | None = Field(default=None, max_length=8000)
    max_tokens: int = Field(default=128, ge=1, le=512)


class CompleteResponse(BaseModel):
    text: str


class ContextItem(BaseModel):
    """One @-mention item for the context picker (CK-4). ``kind`` is the
    closed enum of pickable types; ``id`` is the graph / stable id."""

    kind: Literal["doc", "insight"]
    id: str = Field(..., min_length=1)


class ComposeContextRequest(BaseModel):
    """Context-picker composition request (CK-4 — @doc @insight @investigation
    @note). The client ships the operator's @-selected items; the substrate
    composes a §9.0-aware ``system_context`` string. The retrieval gate is
    SERVER-DERIVED (CWE-862): the effective policy is resolved from
    authenticated request state in the endpoint, NEVER trusted from this body.
    ``max_length`` caps the item count (cost/latency blast radius)."""

    items: list[ContextItem] = Field(..., min_length=1, max_length=20)


class ComposeContextResponse(BaseModel):
    """Composed context: ``system_context`` is the model-facing string;
    ``withheld`` lists item ids whose content the §9.0 gate withheld
    (personal_reading / restricted on the non-owner path); ``missing`` lists
    ids that resolved to no record."""

    system_context: str
    withheld: list[str]
    missing: list[str]


def _compose_context(
    items: list[ContextItem], *, owner: bool,
) -> ComposeContextResponse:
    """Compose a §9.0-aware system_context from @-selected items (CK-4).

    For each item the content is fetched read-only:
      - ``doc`` → ``serve_full_text_guarded(con, id, owner=owner)``: the
        serving-boundary guard (content_class gate AND the independent
        arXiv license-tier cross-check). ``full_text`` is populated only for
        servable docs, or (owner path) personal_reading docs; a personal_reading
        / gated doc on the non-owner path has ``full_text=None`` → WITHHELD.
        A T3 rights-drift @doc raises → WITHHELD (a non-T1 body never enters
        the model context). personal_reading is withholdable: it reaches the
        context ONLY on the owner branch (the rigor gate).
        the book-serve path uses. ``full_text`` is populated only for
        servable docs, or (owner path) personal_reading docs; a
        personal_reading / gated doc on the non-owner path has
        ``full_text=None`` → WITHHELD. personal_reading is withholdable: it
        reaches the context ONLY on the owner branch (the rigor gate).
      - ``insight`` → the node's ``canonical_label`` (operator-authored,
        not §9.0-gated third-party content).

    Degraded posture, never raises: connect_read on a fresh/absent graph
    yields all-missing; a §9.0 T3 rights-drift @doc is caught → withheld. The
    caller always gets a well-formed response.
    Read-only (connect_read) — the corpus is never mutated (§16 single-writer)."""
    from runtime.db_lock import connect_read
    from substrate.books.serve_guard import serve_full_text_guarded
    from substrate.graph import default_db_path
    from substrate.rights import T3BodyServeError

    blocks: list[str] = []
    withheld: list[str] = []
    missing: list[str] = []
    try:
        with connect_read(default_db_path()) as con:
            for item in items:
                if item.kind == "doc":
                    # Route through the serving-boundary guard (never the
                    # raw gate) so the license-tier cross-check fires too —
                    # a non-T1 arXiv body never enters the model's
                    # system_context, even on the owner path. A T3 drift
                    # raises T3BodyServeError → the doc is withheld
                    # (degraded posture; never propagates to the caller).
                    try:
                        result = serve_full_text_guarded(
                            con, item.id, owner=owner,
                        )
                    except T3BodyServeError:
                        withheld.append(item.id)
                        continue
                    if result.full_text:
                        head = f"@doc {result.title or item.id}"
                        blocks.append(f"{head}
{result.full_text}")
                    elif result.found:
                        withheld.append(item.id)
                    else:
                        missing.append(item.id)
                else:  # insight — operator-authored node text
                    row = con.execute(
                        "SELECT canonical_label FROM nodes WHERE node_id = ?",
                        [item.id],
                    ).fetchone()
                    if row and row[0]:
                        blocks.append(f"@insight {item.id}
{row[0]}")
                    else:
                        missing.append(item.id)
    except Exception:
        # Absent graph: every item is missing — honest, well-formed response.
        missing = [item.id for item in items]
    return ComposeContextResponse(
        system_context="

".join(blocks),
        withheld=withheld,
        missing=missing,
    )


class ThoughtPartnerTurn(BaseModel):
    """One prior TP turn (client session thread)."""

    question: str
    answer: str


class ThoughtPartnerRequest(BaseModel):
    """Thought-partner invocation (master-spec §4.5 + §11.7).

    Multi-turn: optional history carries prior completed turns from the
    client session thread (Surface E / AISidecar).

    AISidecar posts a free-form prompt; the substrate retrieves the most
    relevant passages from the operator's knowledge graph (CK-1 grounding),
    runs the ``thought_partner`` role through the dispatch tier with that
    context, and returns the model text unchanged alongside the parser-
    derived response shape.

    The §9.0 retrieval-time gate is SERVER-DERIVED and fail-closed
    (CWE-862): the effective ``policy_tag`` is NEVER read from the request
    body — a caller must not be able to select a privileged policy. It is
    resolved by ``_owner_read_policy_tag`` (the same hardened gate the
    owner-read book endpoints use), which grants ``operator_only`` (the
    owner's full private library) only on a positively authenticated,
    single-operator request and fails closed to ``attribution_eligible``
    (excludes restricted + personal_reading content) otherwise.

    `system_context` (UI-redesign S8 WP-8.4) is the serialised workspace
    state the operator's client ships so the model can reference what panels
    are currently visible. The substrate threads this verbatim into the
    model context. Any ``@@actions`` block in the model response is parsed
    and dispatched client-side by AISidecar, never extracted on the
    substrate."""

    prompt: str
    investigation_id: str | None = None
    system_context: str | None = None
    history: list[ThoughtPartnerTurn] = Field(default_factory=list)


def _retrieve_thought_partner_context(
    prompt: str, policy_tag: str, *, top_k: int = 8,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Retrieve library notes for Thought Partner + honesty status.

    Returns ``(selected_notes, retrieval_status, degraded_reason)``.
    Status mirrors ``TurbopufferSubstrate.query`` / DuckDB search honesty:
    ``servable`` / ``shadow`` / ``degraded — brute_force`` /
    ``duckdb — non_servable_policy`` / ``duckdb — brute_force_kind`` /
    ``empty — graph_unavailable``. Never invents hybrid success.

    §9.0-gated by ``policy_tag``. Read-only. Degraded posture, never raises.
    When ``ANTIEK_TURBOPUFFER_SERVABLE`` + key resolve hybrid kind
    ``turbopuffer``, uses SERVABLE hybrid (same gate as cascade/flywheel).
    Non-``attribution_eligible`` stays DuckDB SoT inside the adapter.
    """
    from runtime.db_lock import connect_read
    from substrate.graph import default_db_path
    from substrate.graph.retrieval_substrate import (
        make_substrate_from_con,
        resolve_reuse_substrate_kind,
    )
    from substrate.graph.search import SentenceTransformerEmbedding, search

    try:
        db_path = default_db_path()
        with connect_read(db_path) as con:
            model = SentenceTransformerEmbedding()
            kind = resolve_reuse_substrate_kind()
            if kind == "turbopuffer":
                sub = make_substrate_from_con(
                    "turbopuffer", con, model=model, db_path=db_path,
                )
                retrieved = sub.query(
                    prompt, top_k=top_k, policy_tag=policy_tag,
                )
            else:
                retrieved = {
                    **search(
                        con, prompt, model=model, top_k=top_k, policy_tag=policy_tag,
                    ),
                    "status": "duckdb — brute_force_kind",
                }
    except Exception:
        return [], "empty — graph_unavailable", "connect_read_or_embed_failed"
    status = retrieved.get("status")
    if not isinstance(status, str) or not status:
        status = "unknown"
    degraded = retrieved.get("degraded_reason")
    degraded_s = degraded if isinstance(degraded, str) else None
    notes: list[dict[str, Any]] = []
    for hit in retrieved.get("results", []):
        doc_id = hit.get("document_id")
        notes.append({
            "note_id": hit.get("chunk_id"),
            "note_text": hit.get("chunk_text", ""),
            "source_event_ids": [doc_id] if doc_id else [],
            "confidence": float(hit.get("similarity") or 0.0),
        })
    return notes, status, degraded_s


class CrossGraphCitationRequest(BaseModel):
    """Record a citation from one user's investigation to another
    user's public note (master-spec §13.9 Phase 3 federation)."""

    referencing_user_id: str
    referencing_investigation_id: str
    referenced_user_id: str
    referenced_note_id: str
    federated_substrate_id: str | None = None


class OutcomeRecordRequest(BaseModel):
    """Operator-graded synthesis outcome (§13.8 + Phase 8 input).

    Per master-spec §13.8: outcomes are first-class signals that feed
    the skill-growth Phase 8 gate. The operator records validation,
    retraction, or neutral observation; downstream gates aggregate
    these into accept/reject verdicts on candidate skill patches."""

    synthesis_id: str
    observer: str = "__operator__"
    thesis_outcomes: list[dict[str, Any]] = []
    falsification_outcomes: list[dict[str, Any]] = []
    execution_risk_outcomes: list[dict[str, Any]] = []
    decision_alignment: dict[str, Any] | None = None
    notes: str | None = None


class AttributionComputeRequest(BaseModel):
    page_id: str
    chunk_to_document: dict[str, str]
    chunk_to_claim_confidence: dict[str, float] = {}
    document_to_source_tier: dict[str, int] = {}
    algorithm: str = "option_b"
    chunk_to_claim_id: dict[str, str] = {}
    claim_load_bearing_scores: dict[str, float] = {}


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


class PublisherClaimRequest(BaseModel):
    """Body of ``POST /publishers/{ip_holder_id}/claim``.

    Module level, NOT nested inside ``create_app``. This module sets
    ``from __future__ import annotations`` (line 29), so every annotation is a
    string that Pydantic resolves against MODULE globals when it builds the
    request-body TypeAdapter. A class defined in the factory's local scope is
    not in those globals, so the reference never resolves and
    ``app.openapi()`` raises PydanticUserError -- taking the whole schema
    down, not just this route.

    The 32 sibling models that stay local are fine because they are only ever
    passed as ``response_model=X``, which hands Pydantic the class OBJECT
    rather than a name to look up. Only a PARAMETER annotation goes through
    string resolution, and this was the only one.
    """

    stripe_connect_account_id: str | None = None


def create_app(
    *,
    broadcaster: EventBroadcaster | None = None,
    cors_origins: list[str] | None = None,
    register_wrestling: bool = True,
    wrestling_db_path: str | None = None,
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
            # - https://www.antiek.ai: Cloudflare Pages serves the same
            #   bundle on www; the login surface (and WebAuthn, which
            #   verifies the exact origin) must work there too.
            #
            # The app.antiek.ai deprecation alias was removed from this
            # list after the operator deleted the custom domain on the
            # Cloudflare Pages project (2026-05-18). No reachable client
            # should be sending requests from that origin anymore.
            cors_origins = [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "https://antiek.ai",
                "https://www.antiek.ai",
            ]
    if cors_origins:
        # H6 magic-link auth: ``credentials=True`` is required for the
        # browser to carry the ANTIEK_SESSION cookie cross-origin from
        # the Pages frontend to api.antiek.ai. Pair with explicit
        # origins (no wildcard); the cookie itself is HttpOnly +
        # Secure + SameSite=Lax + Domain=.antiek.ai in production.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ── H4 + H4.5 + H6: operator auth middleware ──
    # THREE complementary auth paths, all opt-in via env vars:
    #
    # (1) Antiek-issued session cookie (PostHog-style owned auth) —
    #     ANTIEK_SESSION cookie minted at /auth/callback after a
    #     magic-link click. Replaces Cloudflare Access at the auth
    #     layer; CF Tunnel still handles TLS + DNS.
    #
    # (2) Cloudflare Access service token (machine via CF) —
    #     CF-Access-Client-Id + CF-Access-Client-Secret match env.
    #
    # (3) Bearer token (machine callers) — when
    #     ANTIEK_OPERATOR_TOKEN is set, requests carrying
    #     ``Authorization: Bearer <token>`` matching the env pass.
    #     For probes (smoke runs, health checks), ops scripts, any
    #     non-browser client.
    #
    # When no operator token, email allowlist, or service-token client
    # ID is configured, enforcement is bypassed for local development.
    # Otherwise the request must satisfy one complete credential path.
    #
    # ANTIEK_OPERATOR_EMAIL remains the allowlist for signed Antiek
    # session claims. An injected Cloudflare email header is not an
    # authentication path: the origin has no cryptographic proof that
    # Access produced it.
    # Paths the auth middleware never blocks. /health is the
    # ops probe; /auth/request + /auth/callback are the magic-link
    # endpoints that MUST be reachable by a logged-out browser
    # (otherwise the user can never log in to log in).
    _OPERATOR_AUTH_OPEN_PATHS: set[str] = {
        "/health",
        "/auth/request",
        "/auth/callback",
        "/auth/claim",
        "/auth/passkey/status",
        "/auth/passkey/login/options",
        "/auth/passkey/login/verify",
        # Temporary agent / computer-use access (Codex + Hermes
        # computer-use): a logged-out browser must reach the dev-login
        # bootstrap to acquire its session, same as /auth/callback. The
        # route itself 404s unless ANTIEK_DEV_LOGIN_TOKEN is set, so this
        # is inert on any box that hasn't opted in. See auth.py.
        "/auth/dev-login",
        # MCP rug-pull defense per §13.8 — the well-known manifest is
        # public by design so any MCP client can verify the tool
        # hashes without an account.
        "/.well-known/mcp-tools.json",
        # Machine-to-machine multimedia gateway verifies its own fixed bearer.
        "/multimedia/tts-gateway/synthesize",
        # Speak public browse (Anti-Ek Speak): read-only feed +
        # opportunities for logged-out visitors. Sibling to
        # /speak/invite/ (token door). Open-contribute is a
        # separate POST path match below (G7 mint).
        "/speak/feed",
        "/speak/opportunities",
    }
    _OPERATOR_TOKEN_ENV = "ANTIEK_OPERATOR_TOKEN"
    _OPERATOR_EMAIL_ENV = "ANTIEK_OPERATOR_EMAIL"
    _OPERATOR_SERVICE_TOKEN_CLIENT_ID_ENV = "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID"
    _OPERATOR_SERVICE_TOKEN_CLIENT_SECRET_ENV = "CF_ACCESS_CLIENT_SECRET"
    _CF_ACCESS_CLIENT_ID_HEADER = "Cf-Access-Client-Id"
    _CF_ACCESS_CLIENT_SECRET_HEADER = "Cf-Access-Client-Secret"
    _SESSION_COOKIE_NAME = "ANTIEK_SESSION"

    @app.middleware("http")
    async def _operator_auth_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        expected_token = os.environ.get(_OPERATOR_TOKEN_ENV, "").strip()
        operator_emails = operator_allowlist_from_env(_OPERATOR_EMAIL_ENV)
        expected_st_client_id = os.environ.get(
            _OPERATOR_SERVICE_TOKEN_CLIENT_ID_ENV, "",
        ).strip().lower()
        expected_st_client_secret = os.environ.get(
            _OPERATOR_SERVICE_TOKEN_CLIENT_SECRET_ENV, "",
        ).strip()
        if request.url.path == "/multimedia/tts-gateway/synthesize":
            declared_length = request.headers.get("Content-Length")
            try:
                bounded = declared_length is not None and 1 <= int(declared_length) <= 512 * 1024
            except ValueError:
                bounded = False
            if not bounded:
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=413,
                    content={"detail": "TTS gateway request body is invalid"},
                )
        if not expected_token and not operator_emails and not expected_st_client_id:
            # Enforcement disabled. Existing tests + local dev
            # work unchanged. The request still acquires a default
            # operator identity on request.state so endpoints have a
            # uniform handle to user_id / scopes.
            from substrate.multi_user.auth import operator_claims as _oc
            claims = _oc()
            request.state.user_id = claims.user_id
            request.state.scopes = frozenset(claims.scopes)
            request.state.auth_method = "unauthenticated_local"
            # Namespace Option A: single-operator local/tests derive the owner
            # from the configured allowlist address (first entry).
            if claims.email is None:
                _op = os.environ.get("ANTIEK_OPERATOR_EMAIL", "").split(",")[0].strip()
                # Local/tests often have no allowlist env; fall back to a
                # stable single-operator address so derivation still works.
                request.state.user_email = _op or "operator@localhost"
            else:
                request.state.user_email = claims.email
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path in _OPERATOR_AUTH_OPEN_PATHS:
            return await call_next(request)
        # The outbound Herdr bridge has a narrower credential namespace and
        # scope model than operator auth. Let only its explicit scheme reach
        # the /internal/agent-work router, where authenticate_bridge validates
        # the credential hash, logical worker, and per-command scope. Requests
        # without this scheme remain protected by the global operator gate.
        if request.url.path.startswith("/internal/agent-work/"):
            bridge_scheme, _, _ = request.headers.get("Authorization", "").partition(" ")
            if bridge_scheme == "AntiekBridge":
                return await call_next(request)
        # Speak invitee surface (specs/speak/): a subject's friend/family
        # is a SOURCE, not an operator account. Their invite link's TOKEN
        # is the credential — the /speak/invite/ endpoints verify it and
        # operate only on the matching interview — so the operator-auth
        # middleware lets the prefix through. See
        # interfaces/research/api/speak_routes.py + docs/decisions/speak_workflow.md.
        if request.url.path.startswith("/speak/invite/"):
            return await call_next(request)
        # G7 open contribution: POST /speak/projects/{id}/open-contribute
        # Self-serve mint for will_be_public only (handler enforces).
        _p = request.url.path
        if (
            request.method == "POST"
            and _p.startswith("/speak/projects/")
            and _p.endswith("/open-contribute")
            and _p.count("/") == 4
        ):
            return await call_next(request)
        # Read-only public Speak browse (logged-out). Exact paths also
        # listed in _OPERATOR_AUTH_OPEN_PATHS; keep both in sync.
        if request.url.path in ("/speak/feed", "/speak/opportunities"):
            return await call_next(request)

        # Once a path validates the caller, populate request.state with
        # the canonical identity so endpoints can read user_id + scopes
        # without re-running auth logic. Per master-spec §13.3: identity
        # resolution happens HERE, in the middleware — endpoints trust
        # request.state. (Endpoint-side calls back into operator_claims()
        # are still safe; they fall through to the static operator
        # identity when state is absent.)
        def _attach_operator(
            req: Request,
            *,
            method: str,
            email: str | None = None,
            user_id: str | None = None,
        ) -> None:
            from substrate.multi_user.auth import operator_claims as _oc

            claims = _oc()
            req.state.user_id = user_id or claims.user_id
            req.state.scopes = frozenset(claims.scopes)
            req.state.auth_method = method
            req.state.user_email = email

        # Path 1: Antiek-issued session cookie (magic-link login).
        # PostHog-style owned-auth path.
        # Allowlist enforcement against the expected email blocks
        # stale cookies after an allowlist change.
        if os.environ.get("ANTIEK_AUTH_SECRET", "").strip():
            session_value = request.cookies.get(_SESSION_COOKIE_NAME, "")
            if session_value:
                cookie_claims: SessionClaims | None
                try:
                    from substrate.auth import verify_session_cookie
                    cookie_claims = verify_session_cookie(session_value)
                except Exception:  # noqa: BLE001 — invalid cookie falls through
                    cookie_claims = None
                if cookie_claims is not None:
                    cookie_email = cookie_claims.email.strip().lower()
                    if not operator_emails or cookie_email in operator_emails:
                        _attach_operator(
                            request,
                            method="antiek_session_cookie",
                            email=cookie_claims.email,
                            user_id=cookie_claims.user_id,
                        )
                        return await call_next(request)

        # Path 2: Cloudflare Access — Service Token (machine callers)
        # Validate the complete credential at the application boundary.
        # The origin cannot infer that a caller traversed an Access policy
        # merely from a client-controlled identifier header.
        if expected_st_client_id and expected_st_client_secret:
            import secrets as _secrets

            cf_client_id = request.headers.get(
                _CF_ACCESS_CLIENT_ID_HEADER, "",
            ).strip().lower()
            cf_client_secret = request.headers.get(
                _CF_ACCESS_CLIENT_SECRET_HEADER, "",
            ).strip()
            if (
                cf_client_id == expected_st_client_id
                and _secrets.compare_digest(
                    cf_client_secret, expected_st_client_secret,
                )
            ):
                _attach_operator(request, method="cloudflare_service_token")
                return await call_next(request)

        # Path 3: Bearer token (legacy + backstop for direct-to-origin
        # callers that aren't going through Cloudflare Access)
        if expected_token:
            auth = request.headers.get("Authorization", "")
            scheme, _, token = auth.partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                import secrets as _secrets
                if _secrets.compare_digest(token.strip(), expected_token):
                    _attach_operator(request, method="bearer_token")
                    return await call_next(request)

        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": (
                        "Authentication required. One of: Antiek session "
                        "cookie (sign in via /login), Cloudflare Access "
                        "browser session, Cloudflare Access service "
                        "token, or Authorization: Bearer <operator-token>."
                    ),
                    "code": "operator_auth_required",
                }
            },
        )

    # ── Magic-link auth routes (PostHog-style owned login surface) ──
    # Mounted unconditionally so /auth/request + /auth/callback are
    # reachable; the routes themselves no-op when the operator email
    # allowlist is empty, so this is safe on local dev too.
    from .auth import register_auth_routes
    register_auth_routes(app)

    # Phase 3 substrate surfaces — Sprint 23-24 advertiser onboarding +
    # Sprint 30+ thread 1 federation. Substrate primitives live in
    # substrate/ad_inventory/ and substrate/cross_graph/; these routers
    # are the thin HTTP adapters that make them reachable from the
    # AdvertiserConsole + CreatorPayouts UI surfaces and from operator
    # CLIs. Per master-spec §13.7 audit: every state transition is
    # persisted as an append-only row in the substrate's DuckDB.
    from .advertisers import register_advertiser_routes
    register_advertiser_routes(app)
    from .federation import register_federation_routes
    register_federation_routes(app)
    # antiek-unified SPR-05 — read-only coordination surface (gate ledger +
    # 45-sprint roadmap). A VIEW over docs/operator_gate_actions.md + the five
    # specs' rosters + SPR-01's dependency DAG; GET-only, no gate-write path.
    from .coordination import register_coordination_routes
    register_coordination_routes(app)
    # Sprint 23-24 phase 1+2 — ad-impression emission + targeted
    # inventory select. Substrate primitives live in
    # substrate/ad_inventory/{ad_bidding,intent_targeting,payout}.
    from .ad_impressions import register_ad_impression_routes
    register_ad_impression_routes(app)
    # Sprint 23-24 phase 4 — creator payouts dashboard data source.
    from .creator_payouts import register_creator_payouts_routes
    register_creator_payouts_routes(app)
    # Sprint 23-24 phase 5 — advertiser campaign performance.
    from .campaigns import register_campaign_routes
    register_campaign_routes(app)
    # Read SPR-01 — servable-corpus query API. The Library (SPR-02) +
    # Reader (SPR-03) consume this; the full-text endpoint routes through
    # the deny-by-default gate in substrate/books/serve.py.
    from .books import register_book_routes
    register_book_routes(app)
    # Doc→HTML S1 — reader-HTML serve route: GET /sources/{document_id}/reader-html.
    # Serves the URL reader snapshot as content_format="html" ONLY when the
    # sidecar body is exact-version trusted-sanitized (fail-closed gate in
    # substrate/reader_html/store.py); otherwise degrades to text/markdown.
    from .reader_html_routes import register_reader_html_routes
    register_reader_html_routes(app)
    # Doc→HTML S4 — POST /sources/upload: ingests an UPLOADED document (PDF /
    # HTML / Markdown / text) and stores it as sanitized reader-HTML through the
    # same version-provenance sidecar. Sniffs magic bytes first; EPUB / PK-zip
    # is refused with a typed 409 (the authorized book-acquisition ceremony owns
    # that lane). Never stores raw uploaded HTML — storage goes only through
    # store_reader_html, which sanitizes inside the write.
    from .upload_routes import register_upload_routes
    register_upload_routes(app)
    # Doc→HTML S-D2H — POST /ingest/asset: document asset ingestion pipeline.
    # Accepts multipart file OR source_url; converts via anydoc→docling,
    # renders canonical HTML, stores sidecar + provenance, writes memory hook.
    # Fair-use gate refuses known non-fair-use sources.
    from .doc_ingest_routes import register_doc_ingest_routes
    register_doc_ingest_routes(app)
    # Book acquisition — authorized, bytes-only EPUB port into the
    # personal-reading corpus.  Requires a dedicated signing key
    # (ANTIEK_BOOK_ACQUISITION_SIGNING_KEY) that is NEVER the
    # JWT/session key; fail-closed when absent or too short.  Mounted
    # alongside the reader routes so both routers share the same
    # /book-acquisition prefix and auth posture.
    _BOOK_ACQUISITION_KEY_ENV = "ANTIEK_BOOK_ACQUISITION_SIGNING_KEY"
    _book_acq_key_raw = os.environ.get(_BOOK_ACQUISITION_KEY_ENV, "").strip()
    if _book_acq_key_raw:
        _book_acq_key = _book_acq_key_raw.encode("utf-8")
        if len(_book_acq_key) < 32:
            raise RuntimeError(
                f"{_BOOK_ACQUISITION_KEY_ENV} must be at least 32 bytes "
                f"(got {len(_book_acq_key)}); fail-closed"
            )
        _book_acq_db = default_db_path()
        from .book_acquisition_read_routes import (
            create_book_acquisition_read_router,
        )
        from .book_acquisition_routes import create_book_acquisition_router

        app.include_router(
            create_book_acquisition_router(
                db_path=_book_acq_db,
                signing_key=_book_acq_key,
            )
        )
        app.include_router(
            create_book_acquisition_read_router(
                db_path=_book_acq_db, signing_key=_book_acq_key,
            )
        )
    # Mountain Shell SPR-02 — Krea image-generation proxy. Holds the
    # KREA_API_TOKEN server-side (the browser never sees it) and brokers
    # scene-art generation under a daily budget + rate limit + kill-switch
    # + TTL cache. With NO key it returns a typed 503 "disabled" signal
    # (never a 500); SPR-04's living background renders a deterministic
    # placeholder on that signal. Touches no DuckDB / db_lock.
    from .krea_routes import register_krea_routes
    register_krea_routes(app)
    # Multimedia SPR-09 — dry-run asset persistence/read-model API. No live
    # provider spend; routes call deterministic planner/audio/video/steering/
    # hardening seams and persist JSON-backed asset records.
    from .multimedia_routes import register_multimedia_routes
    register_multimedia_routes(app)
    # Link Monster — paste-any-URL digestion surface. Classification →
    # SSRF guard → extraction ladder (oEmbed/OG/DOM/platform) → graph
    # stew (documents/chunks/nodes/edges/rights) + typed event.
    # docs/specs/link-monster-spec.md. Reads/writes the same single-
    # writer DuckDB via runtime.db_lock; no new runtime, no new keys.
    from .link_monster_routes import register_link_monster_routes
    register_link_monster_routes(app)
    # Settings SPR-01 — model inventory + operator budget readout + prompt
    # cost projection (honest nulls when pricing/spend unknown).
    from .settings_budget import register_settings_budget_routes
    register_settings_budget_routes(app)
    # Midnight-oil SPR-06 — no-spend preflight for autonomous research swarms:
    # time box, approved ceiling, route policy, source policy, and HTML/twin-note
    # artifact obligations. Does not launch agents or reserve budget.
    from .midnight_oil_routes import register_midnight_oil_routes
    register_midnight_oil_routes(app)
    # OYM P1 §5 — visible tiers (write half): user-settable chunk tier
    # overrides (POST /settings/tier-overrides) + per-chunk override
    # history (GET /settings/tier-overrides?chunk_id=...).
    from .settings_tiers import register_settings_tiers_routes
    register_settings_tiers_routes(app)
    # AI Role Lineup — operator model-selection vertical (general formation
    # + advanced tactics board). Registry-only: stores operator intent, no
    # implicit dispatch-tier mutation (mirrors settings_models_admin).
    from .settings_lineup import register_settings_lineup_routes
    register_settings_lineup_routes(app)
    # OYM P1 §2 — privacy toggles wired to the telemetry-preferences
    # store (the store's first API consumer; see settings_privacy.py).
    from .settings_privacy import register_settings_privacy_routes
    register_settings_privacy_routes(app)
    from .settings_compute_capacity import register_settings_compute_capacity_routes
    register_settings_compute_capacity_routes(app)
    from .research_tool_search import register_research_tool_search_routes
    register_research_tool_search_routes(app)
    # Own Your Mind P0 — trust wedge. Read-only provenance explain surfaces
    # (D1: /claims/{id}/explain, /syntheses/{id}/explain, /docs/{id}/explain),
    # the decision-surface objective card (C1a: /ops/objective-card), and the
    # event-schema signal inventory (L15: /ops/signal-inventory). All GET-only;
    # docs/own-your-mind/10-p0-implementation-brief.md §1/§3/§4.
    from .explain_routes import register_explain_routes
    register_explain_routes(app)
    from .ops_objective import register_ops_objective_routes
    register_ops_objective_routes(app)
    from .ops_signal_inventory import register_ops_signal_inventory_routes
    register_ops_signal_inventory_routes(app)
    # Model-decision composer Slice B — one advisory decision + exact
    # server-owned cost projection from the same Settings budget snapshot.
    from .composer_projection_routes import register_composer_projection_routes
    register_composer_projection_routes(app)
    # Read SPR-09 — library catalog (paginated/filtered/searched view over the
    # SAME servable-corpus read path; §9.0 keeps gated bodies out of payloads).
    from .library import register_library_routes
    register_library_routes(app)
    from .twin_notes_routes import register_twin_notes_routes
    register_twin_notes_routes(app)
    # HPRJ SPR-05 — synthesis-artifact export: GET /api/syntheses/{id}/artifact.html.
    # Rights filter lives in the adapter (reuses SERVABLE_CONTENT_CLASSES); the
    # route wires the in-path zero-script gate + 403-with-reason on refusal.
    from .synthesis_artifact import register_synthesis_artifact_routes
    register_synthesis_artifact_routes(app)
    # HPRJ SPR-06 — notebook-artifact export: GET /api/notebooks/{id}/artifact
    # (?format=html|antiek|antiek_html). Rights filter in adapt_notebook_for_export.
    from .notebook_artifact import register_notebook_artifact_routes
    register_notebook_artifact_routes(app)
    from .prompt_telemetry import register_prompt_telemetry_routes
    register_prompt_telemetry_routes(app)
    # HPRJ SPR-06 — deliverable (Write surface) export: GET /api/deliverables/{id}/artifact
    from .deliverable_artifact import register_deliverable_artifact_routes
    register_deliverable_artifact_routes(app)
    # Read SPR-09 — ad-border surfaces: per-window frame-attention telemetry
    # (composes the SPR-05 accrual engine + the one escrow seam; accrues, never
    # disburses) + reader slot fill (house fill is the zero-buyer default).
    from .ad_routes import register_ad_routes
    register_ad_routes(app)
    # Read SPR-07 — text-to-speech for voice replies in the conversational
    # rabbit hole. Gated on the operator OpenAI key (503 without one).
    from .speech import register_speech_routes
    register_speech_routes(app)
    # Read SPR-06 — reader voice-note capture: transcribe + distill (the
    # corrected-transcript guard + note-taker dispatch).
    from .read_voice import register_read_voice_routes
    register_read_voice_routes(app)

    bus = broadcaster if broadcaster is not None else EventBroadcaster()
    # Expose for tests and admin endpoints.
    app.state.broadcaster = bus

    # Wire concrete dispatch providers. Each adapter only registers if
    # its API-key env var is present; missing keys degrade gracefully
    # (the router's fallback chain takes over). Tests that exercise
    # dispatch via the in-process mock pass register_providers=False
    # so this startup pass doesn't see operator credentials.
    if register_providers:
        from interfaces.research.api.boot_providers import (
            load_dispatch_env_files,
            log_zero_providers_warning_if_needed,
        )
        from substrate.dispatch.providers import register_default_providers

        # Auto-load platform/.env (and ANTIEK_ENV_FILE) so Mini restarts
        # without a manual `source` still register deepseek/xiaomi/…
        load_dispatch_env_files()
        app.state.registered_providers = register_default_providers(quiet=True)
        log_zero_providers_warning_if_needed(app.state.registered_providers)
    else:
        app.state.registered_providers = set()

    # SPR-07 (antiek-foundation-v2): stamp the build SHA once at startup so
    # /health can report the commit the running process was built from. The
    # prod-parity check asserts this equals the tip of main; see
    # tools/prod_parity/check.py and tools/prod_parity/README.md.
    app.state.build_sha = _resolve_build_sha()

    # GF-7: read-only graph DuckDB startup health snapshot. This does not
    # initialize/create the DB; missing/corrupt/unreadable states are exposed
    # in /health rather than crashing app construction.
    app.state.duckdb_health = _probe_graph_duckdb()
    app.state.turbopuffer_health = _probe_turbopuffer()

    # SPR-11: flywheel-liveness snapshot (read-only, never raises), reported on
    # /health so prod-parity can red a deployed-but-dead flywheel. DEFERRED to
    # the first /health request (memoized via app.state._flywheel_probed) rather
    # than run here at construction: _probe_flywheel scans every event file in
    # the default events dir, so probing at construction made *importing* this
    # module pay a full event-log scan — and this module builds `app` at module
    # scope (`app = create_app()`), which every API test imports, so a populated
    # ~/.antiek turned a bare import into a ~6-minute hang. The cost is still
    # paid at most once; /health is hit immediately in prod, so the snapshot
    # lands just as promptly there. build_sha stays eager (it is cheap).
    app.state._flywheel_probed = False
    app.state.flywheel_ready = False
    app.state.knowledge_reuse_count = 0

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
        # The broadcaster owns the detached Loop One tasks; retain only the
        # in-process app registry needed to revalidate credential authority.
        bus._owner_model_app = app
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
        _loop_coordinator = _register_loop_one(bus)
        # ANT-DRL-06: Path A convergence — DRW gather then Loop 1 tail.
        from interfaces.research.api.cascade_routes import (
            set_synthesis_tail_runner,
        )

        async def _run_cascade_synthesis_tail(
            session: CascadeSession,
            pack: SessionEvidencePack,
        ) -> None:
            await session.run_synthesis_tail(
                pack, broadcaster=bus, coordinator=_loop_coordinator,
            )

        set_synthesis_tail_runner(_run_cascade_synthesis_tail)

    # ── Health ──────────────────────────────────────────────────

    from interfaces.research.api.cascade_routes import (
        resolved_gather_mode as _resolved_gather_mode,
    )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        # Deferred flywheel probe (see create_app): never block /health on the
        # event-log scan or any DuckDB write path. Kick a background to_thread
        # once; return last-known (default False/0) until it finishes. DuckDB
        # fields always come from the startup-cached app.state.duckdb_health
        # snapshot — /health must stay responsive under agent-work lease load.
        import time as _time

        _now = _time.monotonic()
        _probed = getattr(app.state, "_flywheel_probed", False)
        _ready = getattr(app.state, "flywheel_ready", False)
        _last = float(getattr(app.state, "_flywheel_probe_mono", 0.0) or 0.0)
        # Re-probe when never probed, OR when still false after cooldown — so an
        # honest seed (knowledge.reused landed) can flip /health without waiting
        # for a process restart. Once true, keep the memoized snapshot.
        _cooldown_s = 30.0
        _should = (not _probed) or (not _ready and (_now - _last) >= _cooldown_s)
        if _should and not getattr(app.state, "_flywheel_probe_started", False):
            app.state._flywheel_probe_started = True
            app.state._flywheel_probe_mono = _now

            async def _flywheel_bg() -> None:
                try:
                    ready, count = await asyncio.to_thread(_probe_flywheel)
                    app.state.flywheel_ready = ready
                    app.state.knowledge_reuse_count = count
                finally:
                    app.state._flywheel_probed = True
                    app.state._flywheel_probe_started = False

            # Keep a reference on app.state: an unreferenced create_task can
            # be GC'd mid-run, and the handle lets tests/shutdown await the
            # probe deterministically instead of polling.
            app.state._flywheel_probe_task = asyncio.create_task(_flywheel_bg())
        duckdb_health = app.state.duckdb_health
        registered_providers = {
            str(provider)
            for provider in getattr(app.state, "registered_providers", set())
        }
        from .settings_budget import route_ready_provider_ids

        route_ready_providers = route_ready_provider_ids(registered_providers)
        return HealthResponse(
            drw_gather_mode=_resolved_gather_mode(),
            status="ok",
            param_version=ANTIEK_PARAM_VERSION,
            schema_version=EVENT_SCHEMA_VERSION,
            subscriber_count=bus.subscriber_count,
            registered_providers=sorted(registered_providers),
            providers_ready=bool(route_ready_providers),
            build_sha=getattr(app.state, "build_sha", "unknown"),
            flywheel_ready=getattr(app.state, "flywheel_ready", False),
            knowledge_reuse_count=getattr(app.state, "knowledge_reuse_count", 0),
            turbopuffer_servable_enabled=bool(
                (getattr(app.state, "turbopuffer_health", {}) or {}).get(
                    "servable_enabled"
                )
            ),
            turbopuffer_shadow_enabled=bool(
                (getattr(app.state, "turbopuffer_health", {}) or {}).get(
                    "shadow_enabled"
                )
            ),
            turbopuffer_api_key_present=bool(
                (getattr(app.state, "turbopuffer_health", {}) or {}).get(
                    "api_key_present"
                )
            ),
            turbopuffer_active_pointer=bool(
                (getattr(app.state, "turbopuffer_health", {}) or {}).get(
                    "active_pointer_file"
                )
            ),
            turbopuffer_pointer_context_ok=(
                (getattr(app.state, "turbopuffer_health", {}) or {}).get(
                    "active_pointer_context_ok"
                )
            ),
            turbopuffer_hybrid_ready=bool(
                (getattr(app.state, "turbopuffer_health", {}) or {}).get(
                    "hybrid_ready"
                )
            ),
            turbopuffer_resolved_kind=str(
                (getattr(app.state, "turbopuffer_health", {}) or {}).get(
                    "resolved_kind", "brute_force"
                )
            ),
            turbopuffer_indexed_row_count=(
                (getattr(app.state, "turbopuffer_health", {}) or {}).get(
                    "indexed_row_count"
                )
            ),
            turbopuffer_content_hash=(
                (getattr(app.state, "turbopuffer_health", {}) or {}).get(
                    "content_hash"
                )
            ),
            # No bool() and no True default: both would launder "unknown"
            # into a definite answer. A missing key means the probe never ran,
            # which is exactly as unknown as a probe that raised.
            turbopuffer_duckdb_is_sot=(
                (getattr(app.state, "turbopuffer_health", {}) or {}).get(
                    "duckdb_is_sot"
                )
            ),
            turbopuffer_thought_partner_hybrid_wired=(
                (getattr(app.state, "turbopuffer_health", {}) or {}).get(
                    "thought_partner_hybrid_wired"
                )
            ),
            turbopuffer_production_default_mount=bool(
                (getattr(app.state, "turbopuffer_health", {}) or {}).get(
                    "production_default_mount", False
                )
            ),
            duckdb_ready=duckdb_health.ready,
            duckdb_status=duckdb_health.status,
            duckdb_schema_present=duckdb_health.schema_present,
            duckdb_database_size_ok=duckdb_health.database_size_ok,
            duckdb_integrity_check=duckdb_health.integrity_check,
            duckdb_wal_present=duckdb_health.wal_present,
            duckdb_wal_bytes=duckdb_health.wal_bytes,
            duckdb_error=duckdb_health.error,
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

            # Read SPR-07 M3 — an in-book FloatMenu NOTE (marginalia.noted)
            # becomes a USER-AUTHORED per-book insight node in the one graph,
            # so a later block_search returns it. Promotion is the single
            # host-side mutation, serialized through db_lock (single-writer
            # holds). Best-effort: the note is already durably on the log and
            # the backfill is the safety net, so a promotion hiccup must NOT
            # fail the note's persistence. §9: source_kind="user" is carried
            # onto the node (promote_from_marginalia_event), never conflated
            # with a model-emerged insight.
            if action_value == "marginalia.noted":
                try:
                    from substrate.graph.insight_question import (
                        promote_from_marginalia_event,
                    )

                    promote_from_marginalia_event(matching, enabled=True)
                except Exception:  # pragma: no cover — best-effort, backfill covers
                    pass

            # Read SPR-13 M3 — filing a personal-space doc INTO a research
            # project. The reader EXPLICITLY accepted a suggestion (the suggest
            # path NEVER auto-files; this event only exists because the user
            # clicked accept). Filing is a LINK, not a copy: we set the doc's
            # investigation_id THROUGH THE SINGLE-WRITER FUNNEL (connect_write =
            # runtime/db_lock) — a direct `UPDATE documents` outside this lock is
            # forbidden (it would bypass the only-writer invariant). The §9 chain
            # (claim→chunk→document→ip_holder_id) is untouched and ip_holder_id is
            # NOT written (immutable on filing). Unlike marginalia (best-effort —
            # the note is already durable + a backfill covers it), the filing
            # write IS the point of the event: if it fails we surface a 503 so the
            # client doesn't think a doc was filed when it wasn't (no silent
            # divergence between the log and the documents table).
            if action_value == "document.filed_into_investigation":
                from runtime.db_lock import connect_write
                from substrate.graph import default_db_path

                payload = matching.get("payload") or {}
                filed_doc = payload.get("filed_document_id")
                target_inv = payload.get("target_investigation_id")
                if not filed_doc or not target_inv:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "document.filed_into_investigation requires "
                            "filed_document_id + target_investigation_id."
                        ),
                    )
                def _sync() -> None:
                    with connect_write(
                        default_db_path(), purpose="api:file_document"
                    ) as con:
                        existing = con.execute(
                            "SELECT document_id FROM documents WHERE document_id = ?",
                            [filed_doc],
                        ).fetchone()
                        if existing is None:
                            raise HTTPException(
                                status_code=404,
                                detail=f"document {filed_doc!r} not found; nothing filed.",
                            )
                        # 1:N — set the doc's single investigation home. ip_holder_id
                        # + the chunk/claim chain are NOT touched (link, not copy).
                        con.execute(
                            "UPDATE documents SET investigation_id = ? "
                            "WHERE document_id = ?",
                            [target_inv, filed_doc],
                        )

                try:
                    # flock wait off the uvicorn loop (#3111 to_thread class).
                    await asyncio.to_thread(_sync)
                except HTTPException:
                    raise
                except Exception as exc:  # the write IS the point — surface it
                    raise HTTPException(
                        status_code=503,
                        detail=f"filing write failed: {exc}",
                    ) from exc

        return EmittedEventResponse(event_id=event_id, action_type=action_value)

    # ── GET trajectory ──────────────────────────────────────────

    @app.post("/ai/undo", response_model=EmittedEventResponse)
    async def post_ai_undo(req: AIUndoRequest = Body(...)) -> EmittedEventResponse:
        """Undo a previously-applied AI sidecar action (§5.5 Wedge 4).

        Looks up the ``ai.action.applied`` event in the trajectory
        for the given investigation, re-applies ``prev_state`` to
        the substrate via the per-kind inverse handler, and emits
        ``ai.action.undone`` linking back. Substrate restore + audit
        event live inside a single ``connect_write`` lock.
        """
        from runtime.db_lock import connect_write
        from substrate.ai_actions import AIActionError, undo_ai_action
        from substrate.graph import default_db_path

        rows = trajectory(req.investigation_id)
        applied_event = next(
            (r for r in rows if r.get("event_id") == req.event_id),
            None,
        )

        if applied_event is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "applied_event_not_found",
                    "message": (
                        f"no ai.action.applied event found with id "
                        f"{req.event_id!r} in investigation "
                        f"{req.investigation_id!r}"
                    ),
                },
            )

        payload = applied_event.get("payload") or {}
        if payload.get("action_type") != "ai.action.applied":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "wrong_action_type",
                    "message": (
                        f"event {req.event_id} is action_type "
                        f"{payload.get('action_type')!r}; only "
                        "ai.action.applied events can be undone."
                    ),
                },
            )

        db_path = default_db_path()

        def _sync() -> str:
            with connect_write(db_path, purpose="api:ai_undo") as con:
                return undo_ai_action(
                    con,
                    applied_event=applied_event,
                )

        try:
            # flock wait off the uvicorn loop (#3111 to_thread class).
            undone_event_id = await asyncio.to_thread(_sync)
        except AIActionError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "undo_failed", "message": str(exc)},
            ) from exc

        # Surface the new event_id; downstream broadcast happens on
        # the next /trajectory poll or /ws/events tick.
        return EmittedEventResponse(
            event_id=undone_event_id,
            action_type="ai.action.undone",
        )

    @app.get("/.well-known/mcp-tools.json", tags=["mcp"])
    async def mcp_well_known_manifest() -> dict[str, Any]:
        """Antiek Memory MCP server tool manifest (§13.8 rug-pull
        defense). Clients fetch this from
        ``https://api.antiek.ai/.well-known/mcp-tools.json`` and
        verify each tool's description hash matches the hash in
        tools/list responses. Drift treated as fatal session-
        termination per Invariant Labs disclosure precedent.
        """
        from tools.antiek_memory.server import CANONICAL_TOOLS
        from tools.antiek_memory.signing import render_well_known_manifest

        return render_well_known_manifest(CANONICAL_TOOLS)

    @app.get("/trajectory/{investigation_id}")
    async def get_trajectory(
        investigation_id: str,
        limit: Annotated[int | None, Query(ge=1, le=10_000)] = None,
    ) -> dict[str, Any]:
        rows = trajectory(investigation_id)
        if limit is not None:
            rows = rows[-limit:]
        return {
            "investigation_id": investigation_id,
            "count": len(rows),
            "events": rows,
        }

    def _iter_event_log_investigation_ids() -> list[str]:
        from substrate.event_log import default_events_dir

        events_dir = default_events_dir()
        if not os.path.isdir(events_dir):
            return []
        seen: set[str] = set()
        ids: list[str] = []
        for filename in sorted(os.listdir(events_dir)):
            if filename.endswith(".parquet"):
                investigation_id = filename[: -len(".parquet")]
            elif filename.endswith(".jsonl"):
                investigation_id = filename[: -len(".jsonl")]
            else:
                continue
            if investigation_id in seen:
                continue
            seen.add(investigation_id)
            ids.append(investigation_id)
        return ids

    def _parse_event_emitted_at(row: dict[str, Any]) -> datetime | None:
        raw = row.get("emitted_at") or row.get("created_at") or row.get("ts")
        if not raw:
            return None
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if ts.tzinfo is None:
            return ts.replace(tzinfo=UTC)
        return ts.astimezone(UTC)

    @app.get("/trajectory")
    async def get_trajectory_collection(
        limit: Annotated[int, Query(ge=1, le=10_000)] = 50,
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for investigation_id in _iter_event_log_investigation_ids():
            for row in trajectory(investigation_id):
                if "investigation_id" not in row:
                    row = {**row, "investigation_id": investigation_id}
                rows.append(row)
        rows.sort(
            key=lambda row: _parse_event_emitted_at(row) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        rows = rows[:limit]
        return {"count": len(rows), "events": rows}

    # ── Loop 1 entry point ─────────────────────────────────────
    # POST /investigations kicks off a cold question; GET
    # /investigations/{id} reports phase progression + terminal
    # verdict. The orchestrator subscribes to
    # investigation.start_requested and runs the 9-phase chain in
    # a detached task — POST returns immediately with the handle.

    @app.post(
        "/investigations",
        response_model=InvestigationStartResponse,
        response_model_exclude_none=True,
        status_code=202,  # accepted; orchestrator runs async
    )
    async def post_investigation(
        req: InvestigationStartRequest,
        request: Request,
        response: Response,
    ) -> InvestigationStartResponse:
        """Cold-question entry point. Emits
        ``INVESTIGATION_START_REQUESTED`` into the trajectory; the
        Loop 1 orchestrator subscribes to that action_type and
        spawns the per-investigation coroutine that drives phases
        1-9. Returns the investigation_id + start_event_id
        immediately so the caller can poll status."""
        from .compute_capacity_gate import (
            attach_capacity_warn_header,
            commit_start_acu,
            run_capacity_precheck,
            warning_body,
        )

        # Antiek-hosted ACU gate (1 ACU / start). Hard refuse only when
        # ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT=hard and used >= limit.
        capacity_gate = run_capacity_precheck(request)
        # Lazy import — avoid pulling InvestigationStartRequestedPayload
        # at module import time so test setups that monkey-patch the
        # schema layer (drift tests) don't see a partially-initialized
        # module.
        import uuid as _uuid

        from substrate.schemas import (
            InvestigationSpawnedFromPayload,
            InvestigationStartRequestedPayload,
        )

        owner_user_id: str | None = None
        parsed_choices: dict[str, dict[str, str]] | None = None
        operation_id: str | None = None
        if (req.model_choice is None) != (req.operation_id is None):
            raise HTTPException(status_code=422, detail="model_selection_invalid")
        launch_digest: str | None = None
        if req.model_choice is not None:
            from .owner_byot_dispatch import (
                OwnerByotDispatchUnavailable,
                authenticated_distinct_owner,
            )
            from .research_owner_dispatch import PAID_LOOP_ONE_ROLES
            from .settings_models_admin import UserModelChoice
            if (not isinstance(req.operation_id, str) or not req.operation_id.strip()
                    or len(req.operation_id) > 128):
                raise HTTPException(status_code=422, detail="model_selection_invalid")
            try:
                owner_user_id = authenticated_distinct_owner(request)
                selected = UserModelChoice.model_validate(req.model_choice).model_dump(mode="json")
                parsed_choices = {role: selected for role in PAID_LOOP_ONE_ROLES}
            except (ValidationError, OwnerByotDispatchUnavailable, KeyError, TypeError):
                raise HTTPException(status_code=422, detail="model_selection_invalid") from None
            operation_id = req.operation_id.strip()
            # Owner-paid launches are roots and always single-shot. Cascade
            # and chase remain separate, explicitly launched operations.
            if req.parent_investigation_id is not None or req.spawn_context is not None:
                raise HTTPException(status_code=422, detail="owner_model_root_required")
            launch_digest = hashlib.sha256(json.dumps({
                "question": req.question, "context": req.context,
                "topic_slug": req.topic_slug, "max_sub_questions": req.max_sub_questions,
                "parent_investigation_id": req.parent_investigation_id,
                "spawn_context": req.spawn_context, "research_tier": req.research_tier,
                "model_choice": selected,
            }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

        canonical_owner_id = (
            "inv-" + hashlib.sha256(f"owner-launch:{operation_id}".encode()).hexdigest()[:12]
            if operation_id is not None else None
        )
        if canonical_owner_id is not None and req.investigation_id not in (None, canonical_owner_id):
            raise HTTPException(status_code=409, detail="owner_model_operation_conflict")
        investigation_id = req.investigation_id or canonical_owner_id or f"inv-{_uuid.uuid4().hex[:12]}"
        replay_event_id: str | None = None
        if operation_id is not None:
            from .research_owner_dispatch import OwnerLaunchConflict, claim_owner_launch
            try:
                investigation_id, claim_replay, owner_start_event_id = claim_owner_launch(
                    operation_id=operation_id, owner_user_id=owner_user_id or "",
                    launch_digest=launch_digest or "", investigation_id=investigation_id,
                )
            except OwnerLaunchConflict:
                raise HTTPException(status_code=409, detail="owner_model_operation_conflict") from None
            # Exact replays are decided by the durable claim row (same
            # operation_id + launch_digest under the authority flock), NOT by
            # scanning the event log: a concurrent twin's start event may not
            # be visible on disk yet, and racing that read made identical
            # concurrent requests intermittently 409 (CI flake
            # test_exact_concurrent_owner_requests_are_one_event_and_one_response).
            # The start event id is deterministic from the claim, so a replay
            # returns it directly.
            if claim_replay:
                replay_event_id = owner_start_event_id
            else:
                prior = trajectory(investigation_id)
                for row in prior:
                    payload = row.get("payload")
                    if row.get("action_type") == "investigation.start_requested" and isinstance(payload, dict):
                        if (payload.get("owner_user_id") == owner_user_id
                                and payload.get("owner_operation_id") == operation_id
                                and payload.get("owner_launch_digest") == launch_digest):
                            replay_event_id = str(row["event_id"])
                            break
                        raise HTTPException(status_code=409, detail="owner_model_operation_conflict")
        try:
            event_id = replay_event_id or emit_typed(
                investigation_id,
                InvestigationStartRequestedPayload(
                    question=req.question,
                    context=req.context,
                    topic_slug=req.topic_slug,
                    max_sub_questions=req.max_sub_questions,
                    parent_investigation_id=req.parent_investigation_id,
                    spawn_context=req.spawn_context,
                    # SPR-01 M3: record the chosen research tier on the
                    # start event (queryable after the fact). The payload
                    # field is the same CLOSED set.
                    research_tier=req.research_tier,

                    source_policy=req.source_policy,
                    owner_user_id=owner_user_id,
                    owner_operation_id=operation_id,
                    owner_model_choices=parsed_choices,
                    owner_launch_digest=launch_digest,
                    owner_launch_version=1 if operation_id is not None else None,
                ),
                role="operator",
                policy_id="operator-cli",
                event_id=owner_start_event_id if operation_id is not None else None,
                idempotent=operation_id is not None,
                strict_write=operation_id is not None,
            )
        except ValidationError:
            raise HTTPException(status_code=422, detail="model_selection_invalid") from None
        except Exception:
            if operation_id is not None:
                raise HTTPException(status_code=503, detail="owner_model_start_pending") from None
            raise

        if event_id is None:
            raise HTTPException(
                status_code=503,
                detail="Event log is disabled (ANTIEK_EVENTS_DISABLED).",
            )

        if operation_id is not None:
            from .research_owner_dispatch import advance_owner_launch, owner_launch_state
            if not claim_replay and owner_launch_state(operation_id) == "claimed":
                # Only the fresh claim advances the state machine. A concurrent
                # exact replay must not CAS "claimed" -> "appended": two twins
                # that both observe "claimed" and both advance produce a
                # spurious 409 on the loser (CI flake
                # test_exact_concurrent_owner_requests_are_one_event_and_one_response).
                # The replay answer is the deterministic start event id.
                advance_owner_launch(operation_id, "claimed", "appended")

        # Sprint 11: emit the spawn-lineage event when parent provided.
        # Non-fatal if it fails; the start event already encodes the
        # lineage in its own payload.
        if req.parent_investigation_id:
            with contextlib.suppress(Exception):  # pragma: no cover — diagnostic
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

        # Broadcast only a fresh or append-only launch. Once the durable
        # journal says broadcast, an exact HTTP replay must not start a second
        # paid run.
        should_broadcast = operation_id is None
        if operation_id is not None:
            from .research_owner_dispatch import claim_owner_broadcast
            should_broadcast = claim_owner_broadcast(operation_id)
        # Broadcast the start event so the orchestrator handler
        # subscribed to it spawns the per-investigation coroutine.
        for row in reversed(trajectory(investigation_id)) if should_broadcast else ():
            if row.get("event_id") == event_id:
                try:
                    event = Event.model_validate(row)
                    await bus.broadcast(event)
                    if operation_id is not None:
                        advance_owner_launch(operation_id, "broadcasting", "broadcast")
                except Exception:
                    if operation_id is not None:
                        advance_owner_launch(operation_id, "broadcasting", "appended")
                        raise HTTPException(status_code=503, detail="owner_model_start_pending") from None
                break

        # Meter 1 ACU for this start (idempotent on investigation_id).
        post_gate = commit_start_acu(
            request,
            investigation_id=investigation_id,
            reason="post_investigations",
        )
        warn_gate = post_gate if post_gate.verdict == "soft_warn" else capacity_gate
        attach_capacity_warn_header(response, warn_gate)

        return InvestigationStartResponse(
            investigation_id=investigation_id,
            status="started",
            start_event_id=event_id,
            operation_id=operation_id,
            # Credentials, live rates, budget envelope, and dispatch authority
            # freeze at each role's execution seam. The start endpoint only
            # durably queues the launch, so do not call this "accepted".
            owner_model_status=("replayed" if replay_event_id is not None else "queued")
            if operation_id is not None else None,
            capacity_warning=warning_body(warn_gate),
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
        last_phase: int | None = None
        last_delivered: str | None = None
        terminal_row: dict[str, Any] | None = None

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

        # SPR-11 M3: surface the §14.4 inline-rubric verdict, READ from the
        # persisted rubric.scored event (never recomputed). Null when the
        # synthesis has no scored event — the surface shows no score rather
        # than a fabricated one.
        rubric_score = _rubric_score_from_trajectory(rows)

        # SPR-01 M3: READ the chosen research tier off the start event's
        # persisted payload (the "queryable after the fact" acceptance).
        # The start event is the first INVESTIGATION_START_REQUESTED row;
        # walk oldest-first and stop at the first match. Null when absent
        # (legacy/daemon runs predate the field) — never fabricated.
        start_action = ActionType.INVESTIGATION_START_REQUESTED.value
        research_tier: str | None = None
        source_policy: list[str] = []
        for r in rows:
            if r.get("action_type") == start_action:
                payload = r.get("payload")
                if isinstance(payload, dict):
                    rt = payload.get("research_tier")
                    if isinstance(rt, str):
                        research_tier = rt
                    sp = payload.get("source_policy")
                    if isinstance(sp, list):
                        source_policy = [x for x in sp if isinstance(x, str)]
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
                rubric_score=rubric_score,
                research_tier=research_tier,
                source_policy=source_policy,
            )

        return InvestigationStatusResponse(
            investigation_id=investigation_id,
            status="in_progress",
            current_phase=last_phase,
            last_delivered_action_type=last_delivered,
            terminal_payload=None,
            rubric_score=rubric_score,
            research_tier=research_tier,
            source_policy=source_policy,
        )

    # ── Sprint 11: list investigations + chunk fetch ───────────

    @app.get(
        "/investigations",
        response_model=InvestigationListResponse,
    )
    async def list_investigations(
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        status_filter: Annotated[
            str | None, Query(alias="status")
        ] = None,
    ) -> InvestigationListResponse:
        """List recent investigations. Walks the events directory to
        discover all unique investigation_ids, then summarizes each
        with its start question + terminal status + cost.

        Includes researches launched as a cascade fan-out (SPR-05): the
        session parent (``session-…``) and its ``…-leaf-N`` children are
        NOT ``inv-`` prefixed, but they are real researches the monitor
        ("launch N at once") must show — so discovery accepts any
        ``*.jsonl`` whose trajectory is an investigation (carries a
        start-requested, spawned-from, or terminal lifecycle event),
        not just the ``inv-`` shape. A cascade leaf records its session
        parent via ``investigation.spawned_from`` (not the start payload),
        so the grouping link is read from that event too, and its
        question is the leaf's ``sub_question``.

        Status honesty (SPR-05 B2/MINOR): a budget-halted chase
        (``investigation.chase_halted``) is terminal — ``stopped`` — to
        match ``cascade_session.reconstruct_session``; it must never read
        as "working"/running forever. A research finished via stop/cancel
        carries ``outcome`` in its completion payload, surfaced as
        ``stopped`` so the operator sees an honest end state rather than
        "done".

        Filter by ``status`` to narrow (one of: ``in_progress``,
        ``completed``, ``failed``, ``stopped``). Default limit 50, sorted
        newest first."""
        import os as _os

        from orchestration.continuous.suggestions import policy_is_daemon
        from substrate.event_log import default_events_dir
        from substrate.schemas import ActionType

        events_dir = default_events_dir()
        if not _os.path.isdir(events_dir):
            return InvestigationListResponse(count=0, investigations=[])

        completed_action = ActionType.INVESTIGATION_COMPLETED.value
        failed_action = ActionType.INVESTIGATION_FAILED.value
        halted_action = ActionType.INVESTIGATION_CHASE_HALTED.value
        start_action = ActionType.INVESTIGATION_START_REQUESTED.value
        spawned_action = ActionType.INVESTIGATION_SPAWNED_FROM.value
        # The lifecycle markers that identify a trajectory as a research
        # (as opposed to, e.g., a session-only or non-investigation log).
        # A cascade session file carries only ``cascade.launched`` and is
        # surfaced as the grouping parent so its leaves nest under it.
        investigation_markers = {
            start_action, spawned_action, completed_action,
            failed_action, halted_action, "cascade.launched",
        }

        summaries: list[InvestigationSummary] = []
        # Session-container ids (a cascade.launched file with no research
        # lifecycle of its own): the grouping parent. Its honest status is the
        # aggregate of its leaves (working iff a leaf still works), derived in a
        # post-pass once every row is known — never a bare "working" forever.
        session_containers: set[str] = set()
        for filename in _os.listdir(events_dir):
            if not filename.endswith(".jsonl"):
                continue
            inv_id = filename[:-len(".jsonl")]
            rows = trajectory(inv_id)
            if not rows:
                continue
            # A non-inv- file is only a research if its trajectory says so;
            # this keeps unrelated logs out of the list while admitting the
            # cascade session/leaf ids the monitor must show.
            if not inv_id.startswith("inv-") and not any(
                r.get("action_type") in investigation_markers for r in rows
            ):
                continue

            question: str | None = None
            started_at: str | None = None
            completed_at: str | None = None
            cost_total = 0.0
            terminal_status = "in_progress"
            parent_inv_id: str | None = None
            # A pure session container has cascade.launched but never starts or
            # terminates a research of its own.
            saw_launched = False
            saw_own_lifecycle = False
            # SPR-09: was this research spawned by the §7 daemon? True iff its
            # start/spawned event carried the daemon's spawn policy_id. The raw
            # policy_id is read here and translated to a boolean — never sent
            # to the client.
            spawned_by_daemon = False

            for r in rows:
                at = r.get("action_type")
                payload = r.get("payload") or {}
                if at in (start_action, spawned_action) and policy_is_daemon(r.get("policy_id")):
                    spawned_by_daemon = True
                if at in (start_action, spawned_action, completed_action,
                          failed_action, halted_action):
                    saw_own_lifecycle = True
                if at == "cascade.launched":
                    saw_launched = True
                if at == start_action and question is None:
                    # A standalone research carries its question + parent here;
                    # a cascade leaf carries only ``sub_question`` (its parent
                    # link rides on the separate spawned_from event below).
                    question = payload.get("question") or payload.get("sub_question")
                    started_at = r.get("emitted_at")
                    if payload.get("parent_investigation_id"):
                        parent_inv_id = payload.get("parent_investigation_id")
                elif at == spawned_action:
                    # The cascade/chase parent link (cascade leaves record it
                    # here, not in the start payload). Also seeds the question
                    # + a start time for a leaf whose start_requested lacked one.
                    parent_inv_id = payload.get("parent_investigation_id") or parent_inv_id
                    if question is None:
                        question = payload.get("sub_question")
                    if started_at is None:
                        started_at = r.get("emitted_at")
                elif at == "cascade.launched" and started_at is None:
                    # The session parent's own row: no start_requested, so take
                    # its launch time so the group sorts by real freshness.
                    started_at = r.get("emitted_at")
                elif at == completed_action:
                    # Stop/cancel finishes through completed with an explicit
                    # ``outcome`` — surface it honestly as ``stopped`` rather
                    # than "done" (the M1 vocabulary lists them as distinct).
                    if payload.get("outcome") in ("stopped", "cancelled"):
                        terminal_status = "stopped"
                    else:
                        terminal_status = "completed"
                    completed_at = r.get("emitted_at")
                elif at == failed_action:
                    terminal_status = "failed"
                    completed_at = r.get("emitted_at")
                elif at == halted_action:
                    # Budget-halted: terminal (matches reconstruct_session's
                    # BUDGET_HALTED), shown as stopped — never running forever.
                    terminal_status = "stopped"
                    completed_at = r.get("emitted_at")
                elif at == "dispatch.call":
                    with contextlib.suppress(TypeError, ValueError):
                        cost_total += float(payload.get("cost_usd", 0.0))

            if saw_launched and not saw_own_lifecycle:
                session_containers.add(inv_id)

            summaries.append(InvestigationSummary(
                investigation_id=inv_id,
                question=question,
                status=terminal_status,
                started_at=started_at,
                completed_at=completed_at,
                cost_usd_total=round(cost_total, 6),
                parent_investigation_id=parent_inv_id,
                spawned_by_daemon=spawned_by_daemon,
            ))

        # Derive each session container's status from its leaves (the same
        # all-terminal logic cascade_session.reconstruct_session uses): working
        # while any leaf works; needs-attention if any leaf failed; else done.
        # So a session whose fan-out finished never reads "working" forever.
        if session_containers:
            children: dict[str, list[str]] = {}
            for s in summaries:
                if s.parent_investigation_id in session_containers:
                    children.setdefault(s.parent_investigation_id, []).append(s.status)
            for s in summaries:
                if s.investigation_id not in session_containers:
                    continue
                leaf_states = children.get(s.investigation_id, [])
                if any(st == "in_progress" for st in leaf_states):
                    s.status = "in_progress"
                elif any(st == "failed" for st in leaf_states):
                    s.status = "failed"
                elif leaf_states:
                    # All leaves terminal: done if any completed, else stopped
                    # (every leaf stopped/halted → the session is stopped).
                    s.status = "completed" if any(
                        st == "completed" for st in leaf_states) else "stopped"
                # No leaves discovered yet (race just after launch): leave the
                # honest "in_progress" the loop set.

        if status_filter:
            summaries = [s for s in summaries if s.status == status_filter]

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
        modal + SPR-04's named-source render to surface the chunk text +
        source document title for any cited chunk_id.

        §9.0 retrieval gate: a chunk whose source is on the canonical
        non-privileged denylist (``retrieval_gate`` union:
        ``restricted_pending_opt_in`` + ``personal_reading``) or under a
        takedown has its body WITHHELD here, at the query layer — the
        same gate ``substrate/graph/search.py`` applies to chunk
        retrieval — so a frontend that calls this directly still cannot
        pull body text out of a restricted source. A NULL / legacy
        research chunk passes (grandfathered), matching chunk search; the
        stricter book full-text allowlist lives in
        ``substrate/books/serve.py`` and governs the public serve path,
        not this reading-surface preview. The named-source label (title)
        still resolves so the reader sees an honest "not available to
        open" state, never a blank citation. The verdict rides as
        ``servable`` / ``servability`` so the surface need not re-derive
        it."""
        import duckdb as _duckdb

        from runtime.db_lock import connect_read
        from substrate.graph import default_db_path
        from substrate.graph.retrieval_gate import is_chunk_body_withheld

        db_path = default_db_path()
        try:
            # connect_read, not raw duckdb.connect(read_only=True).
            # db_lock.py:921 says so in as many words, and the reason is not
            # style: DuckDB REFUSES a read-only handle when this process
            # already holds the same file read-write, which under
            # `--workers 1` is the normal state. The raw call raises
            # ConnectionException — NOT the IOException caught below — so it
            # escaped as a 500. connect_read catches that exact conflict and
            # falls back to a read-oriented read-write handle.
            #
            # Found by running tools/reachability/probes/usability_keystone.py,
            # a five-leg journey probe that exists in the tree and that no
            # workflow runs. Every per-brick test passed; the journey did not.
            con = connect_read(db_path)
        except _duckdb.IOException as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Graph DB unreachable: {exc}",
            ) from exc

        try:
            # LEFT JOIN book_assets so a takedown override is honoured even
            # for a chunk of a public-domain book (taken_down wins over
            # content_class in the projection). A document with no
            # book_assets row coalesces to taken_down=False.
            row = con.execute(
                """
                SELECT c.chunk_id, c.text, c.section_path, c.token_count,
                       c.document_id, d.title, d.source_tier,
                       d.content_class,
                       COALESCE(b.taken_down, FALSE) AS taken_down,
                       h.display_name, h.status
                FROM chunks c
                JOIN documents d ON c.document_id = d.document_id
                LEFT JOIN book_assets b ON d.document_id = b.document_id
                LEFT JOIN ip_holders h ON d.ip_holder_id = h.ip_holder_id
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

        content_class = row[7]
        taken_down = bool(row[8])
        # Takedown wins over everything; otherwise delegate to the single
        # canonical helper (RG-04 forbids reimplementing the denylist here).
        # NULL/unknown fails closed (SR-07), consistent with the search path.
        withheld, label = is_chunk_body_withheld(content_class, taken_down=taken_down)
        if withheld:
            servable, label = False, label
        else:
            servable, label = True, None

        return ChunkResponse(
            chunk_id=row[0],
            # Withhold the body for a non-servable source. The whole point
            # of the gate living here is that withholding is not a UI
            # courtesy — the bytes do not leave the endpoint.
            text=(row[1] or "") if servable else "",
            section_path=row[2],
            token_count=int(row[3] or 0),
            document_id=row[4],
            document_title=row[5],
            source_tier=int(row[6]),
            servable=servable,
            # §9.0: the IP-holder name is protected attribution — surface it
            # ONLY for a servable source. A restricted / taken-down source
            # withholds its owner exactly as it withholds its body, so a
            # reader can't infer "whose work" from a source we may not serve.
            ip_holder_name=(row[9] if servable else None),
            ip_holder_status=(row[10] if servable else None),
            servability=label,
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
                from acquisition.arxiv import fetch_by_id as _fbi
                from acquisition.arxiv import ingest_paper as _ip
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
                arxiv_kwargs: dict[str, Any] = {
                    "investigation_id": req.investigation_id
                }
                if req.source_tier is not None:
                    arxiv_kwargs["source_tier"] = req.source_tier
                arxiv_r = _ip(paper, **arxiv_kwargs)
                return IngestSourceResponse(
                    status=(
                        "ingested" if arxiv_r.chunks_written > 0 else "skipped"
                    ),
                    detected_kind="arxiv",
                    document_id=arxiv_r.document_id,
                    document_loaded_event_id=arxiv_r.document_loaded_event_id,
                    chunks_written=arxiv_r.chunks_written,
                    title=paper.title,
                )
            if detected == "youtube":
                from acquisition.youtube import ingest_youtube
                yt_kwargs: dict[str, Any] = {
                    "investigation_id": req.investigation_id
                }
                if req.source_tier is not None:
                    yt_kwargs["source_tier"] = req.source_tier
                yt_r = ingest_youtube(req.url, **yt_kwargs)
                return IngestSourceResponse(
                    status=(
                        "ingested" if yt_r.chunks_written > 0
                        else "skipped"
                    ),
                    detected_kind="youtube",
                    document_id=yt_r.document_id,
                    document_loaded_event_id=yt_r.document_loaded_event_id,
                    chunks_written=yt_r.chunks_written,
                    skipped_reason=yt_r.skipped_reason,
                    title=yt_r.title,
                )
            if detected == "podcast":
                from acquisition.podcasts import ingest_feed
                podcast_kwargs: dict[str, Any] = {
                    "investigation_id": req.investigation_id,
                    "max_episodes": req.max_episodes,
                }
                if req.source_tier is not None:
                    podcast_kwargs["source_tier"] = req.source_tier
                results = ingest_feed(req.url, **podcast_kwargs)
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
            if detected == "substack":
                from acquisition.substack import ingest_publication_feed

                feed_url = req.url.rstrip("/")
                if "/feed" not in feed_url.lower():
                    feed_url = f"{feed_url}/feed"
                substack_kwargs: dict[str, Any] = {
                    "investigation_id": req.investigation_id,
                    "max_posts": req.max_episodes,
                }
                if req.source_tier is not None:
                    substack_kwargs["source_tier"] = req.source_tier
                summary = ingest_publication_feed(feed_url, **substack_kwargs)
                chunks_written = sum(r.chunks_written for r in summary.results)
                first_result = next(
                    (r for r in summary.results if r.status == "ingested"),
                    summary.results[0] if summary.results else None,
                )
                return IngestSourceResponse(
                    status="ingested" if summary.ingested > 0 else "skipped",
                    detected_kind="substack",
                    document_id=first_result.document_id if first_result else None,
                    document_loaded_event_id=(
                        first_result.document_loaded_event_id if first_result else None
                    ),
                    chunks_written=chunks_written,
                    skipped_reason=None if summary.ingested > 0 else "no_public_posts_ingested",
                    title=summary.publication_title,
                    episodes_processed=len(summary.results),
                    episodes_ingested=summary.ingested,
                )
            if detected == "twitter":
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
            if detected == "inbox":
                # Local-file reading inbox (DOGFOOD SPR-01). ``req.url`` is a
                # server-side absolute path to a *.txt article dump (the
                # operator's ~/research/inbox/<date>/ stream). The operator
                # declares ``kind=inbox`` explicitly -- there is no URL
                # auto-detection for a local path (a heuristic would be fragile).
                path = os.path.expanduser(req.url)
                if not os.path.isfile(path):
                    raise ValueError(
                        f"inbox path is not a readable file: {req.url!r}"
                    )
                from acquisition.inbox.ingest import ingest_inbox_file
                inbox_kwargs: dict[str, Any] = {
                    "investigation_id": req.investigation_id,
                }
                if req.source_tier is not None:
                    inbox_kwargs["source_tier"] = req.source_tier
                inbox_r = ingest_inbox_file(path, **inbox_kwargs)
                return IngestSourceResponse(
                    # inbox_r.status is `str`; narrow to the response Literal so
                    # the type stays exact (mirrors the arxiv/youtube branches).
                    status=("ingested" if inbox_r.status == "ingested" else "skipped"),
                    detected_kind="inbox",
                    document_id=inbox_r.document_id,
                    chunks_written=inbox_r.chunks_written,
                    title=os.path.splitext(os.path.basename(path))[0],
                )
            if detected == "url":
                from acquisition.urls import ingest_url
                url_kwargs: dict[str, Any] = {
                    "investigation_id": req.investigation_id
                }
                if req.source_tier is not None:
                    url_kwargs["source_tier"] = req.source_tier
                url_r = ingest_url(req.url, **url_kwargs)
                return IngestSourceResponse(
                    status=(
                        "ingested" if url_r.chunks_written > 0
                        else "skipped"
                    ),
                    detected_kind="url",
                    document_id=url_r.document_id,
                    document_loaded_event_id=url_r.document_loaded_event_id,
                    chunks_written=url_r.chunks_written,
                    skipped_reason=url_r.skipped_reason,
                    title=url_r.title,
                )
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

        def _sync() -> Any:
            with connect_write(db, purpose="deliverables/create") as con:
                did = insert_deliverable(
                    con,
                    title=req.title,
                    deliverable_kind=req.deliverable_kind,
                    investigation_root_id=req.investigation_root_id,
                )
                return con.execute(
                    "SELECT deliverable_id, title, deliverable_kind, "
                    "investigation_root_id, status, "
                    "strftime(created_at, '%Y-%m-%dT%H:%M:%S'), "
                    "strftime(updated_at, '%Y-%m-%dT%H:%M:%S') "
                    "FROM deliverables WHERE deliverable_id = ?", [did],
                ).fetchone()

        # flock wait off the uvicorn loop (#3111 to_thread class).
        row = await asyncio.to_thread(_sync)
        return DeliverableSummary(
            deliverable_id=row[0], title=row[1], deliverable_kind=row[2],
            investigation_root_id=row[3], status=row[4],
            created_at=row[5], updated_at=row[6], section_count=0,
        )

    @app.get("/deliverables", response_model=DeliverableListResponse)
    async def list_deliverables(limit: int = 50) -> DeliverableListResponse:

        from runtime.db_lock import connect_read
        db = _resolve_db_path()
        con = connect_read(db)
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
        import json as _json

        from runtime.db_lock import connect_read
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            head = con.execute(
                "SELECT deliverable_id, title, deliverable_kind, status, "
                "investigation_root_id "
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
            deliverable_kind=head[2], status=head[3],
            investigation_root_id=head[4], sections=sections,
        )

    @app.post("/sections", response_model=SectionResponse, status_code=201)
    async def post_section(req: CreateSectionRequest) -> SectionResponse:
        from runtime.db_lock import connect_write
        from substrate.graph.ops import insert_section

        db = _resolve_db_path()

        def _sync() -> str:
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
                return insert_section(
                    con,
                    deliverable_id=req.deliverable_id,
                    section_index=req.section_index,
                    title=req.title,
                    parent_section_id=req.parent_section_id,
                )

        # flock wait off the uvicorn loop (#3111 to_thread class).
        sid = await asyncio.to_thread(_sync)
        return SectionResponse(
            section_id=sid, deliverable_id=req.deliverable_id,
            parent_section_id=req.parent_section_id,
            section_index=req.section_index, title=req.title,
            prose_text=None, prose_provenance=None, block_count=0,
        )

    @app.post("/sections/attach-block", status_code=202)
    async def post_attach_block(req: AttachBlockRequest) -> dict[str, Any]:
        from runtime.db_lock import connect_write
        from substrate.graph.ops import attach_block_to_section

        db = _resolve_db_path()

        def _sync() -> None:
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

        # flock wait off the uvicorn loop (#3111 to_thread class).
        await asyncio.to_thread(_sync)
        return {"status": "attached"}

    # ── Sprint 14: block search + reorder + twitter ─────────────────

    @app.get("/blocks/search", response_model=BlockSearchResponse)
    async def block_search(
        q: str = Query(default="", max_length=200),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> BlockSearchResponse:
        from runtime.db_lock import connect_read
        """Search the operator's graph for insight/claim/note blocks to
        drag into a deliverable section. Mode C palette uses this.

        Sprint 14 implementation: ILIKE over nodes.canonical_label +
        metadata. Sprint 15 swaps in cosine search via the embedding
        column so semantic matches surface."""

        db = _resolve_db_path()
        like = f"%{q}%" if q.strip() else "%"
        con = connect_read(db)
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
    async def post_reorder_block(req: ReorderBlockRequest) -> dict[str, Any]:
        """Move a block within a section, or to a new section.

        Implementation note: section_blocks has a composite PK
        ``(section_id, block_kind, block_id)``. Moving to a new
        section requires DELETE + INSERT under the same lock."""
        import duckdb

        from runtime.db_lock import connect_write

        db = _resolve_db_path()
        target_section = req.new_section_id or req.section_id

        def _sync() -> None:
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
                # If moving across sections, DELETE old + INSERT new.
                # The write lock gives mutual exclusion, not atomicity:
                # DuckDB autocommits each statement, so a failing INSERT
                # (composite-PK collision) left the DELETE durable. Wrap the
                # pair in an explicit transaction.
                if (
                    req.new_section_id is not None
                    and req.new_section_id != req.section_id
                ):
                    try:
                        with con.transaction():
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
                    except duckdb.ConstraintException as exc:
                        # Already attached to the target; the rollback keeps
                        # the source attachment. Say so instead of a bare 500.
                        raise HTTPException(
                            status_code=409,
                            detail="block already attached to the target section",
                        ) from exc
                else:
                    # In-section reorder: just bump the index
                    con.execute(
                        "UPDATE section_blocks SET block_index = ? "
                        "WHERE section_id = ? AND block_kind = ? AND block_id = ?",
                        [int(req.new_block_index), req.section_id,
                         req.block_kind, req.block_id],
                    )

        # flock wait off the uvicorn loop (#3111 to_thread class).
        await asyncio.to_thread(_sync)
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
        from substrate.graph.ops import content_addressed_id, insert_node, update_section_prose
        from substrate.schemas import ClaimAssertedByOperatorPayload, GraphNodeInsertedPayload
        from substrate.write.event_outbox import (
            build_typed_envelope,
            dispatch_pending_best_effort,
            enqueue_event,
            eventful_transaction,
        )

        db = _resolve_db_path()

        def _sync() -> tuple[str | None, str | None]:
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
                claim_node_id: str | None = None
                claim_event_id: str | None = None
                with eventful_transaction(con, req.investigation_id):
                    update_section_prose(
                        con, section_id=section_id, prose_text=req.prose_text,
                    )
                    if req.promote_to_graph:
                        label = req.prose_text.strip().splitlines()[0]
                        if len(label) > 160:
                            label = label[:159] + "…"
                        claim_node_id = content_addressed_id(
                            "node", f"{label}|claim|cross_domain"
                        )
                        node_existed = con.execute(
                            "SELECT 1 FROM nodes WHERE node_id=?", [claim_node_id]
                        ).fetchone() is not None
                        insert_node(
                            con, canonical_label=label, node_type="claim",
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
                            node_id=claim_node_id, emit_event=False,
                        )
                        if not node_existed:
                            node_event = build_typed_envelope(
                                req.investigation_id,
                                GraphNodeInsertedPayload(
                                    node_id=claim_node_id, canonical_label=label,
                                    node_type="claim", graph_scope="cross_domain",
                                    has_embedding=False,
                                ), role="connector",
                            )
                            enqueue_event(
                                con, operation_id=f"graph.node:{node_event.event_id}",
                                aggregate_kind="graph_node", aggregate_id=claim_node_id,
                                event=node_event,
                            )
                        claim_event = build_typed_envelope(
                            req.investigation_id,
                            ClaimAssertedByOperatorPayload(
                                deliverable_id=deliverable_id,
                                section_id=section_id,
                                claim_text=req.prose_text,
                                original_text=req.original_text,
                                node_id=claim_node_id,
                                source_tier=5,
                                cited_chunk_ids=req.cited_chunk_ids,
                            ),
                            role="creation_surface",
                            policy_id=f"operator/{deliverable_id}",
                        )
                        claim_event_id = enqueue_event(
                            con, operation_id=f"claim.asserted:{claim_event.event_id}",
                            aggregate_kind="deliverable_section", aggregate_id=section_id,
                            event=claim_event,
                        )
                if req.promote_to_graph:
                    dispatch_pending_best_effort(con, req.investigation_id)
            return claim_node_id, claim_event_id

        # flock wait off the uvicorn loop (#3111 to_thread class).
        claim_node_id, claim_event_id = await asyncio.to_thread(_sync)

        if req.promote_to_graph and claim_node_id is not None:
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
        from runtime.db_lock import connect_read
        """Export a deliverable as Markdown, HTML, or a structured JSON
        bundle. Returns the content inline (the caller can save it via
        the Blob API in the browser). The substrate keeps no
        notion of "rendered files" — every export is a fresh derivation
        from the section rows."""
        SUPPORTED = ("markdown", "html", "json", "pdf", "epub", "substack")
        if format not in SUPPORTED:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"format must be one of {'|'.join(SUPPORTED)}, "
                    f"got {format!r}"
                ),
            )
        import json as _json

        from substrate.write.deliverable_sources import (
            resolve_deliverable_sources,
        )
        db = _resolve_db_path()
        con = connect_read(db)
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
            # GPW SPR-04: the sellable artifact must carry its attribution. The
            # substrate stores prose_provenance (paragraph_index → block_ids,
            # what get_deliverable already returns for the X-ray), but the
            # export stripped it. Fetch a SELF-CONTAINED per-section row for the
            # JSON export — each row carries its OWN prose_provenance, so there
            # is NO cross-section keying (``section_index`` is NOT unique per
            # deliverable: only ``section_id`` is, and several callers hardcode
            # index 0, so a map keyed by index would misattribute). The shared
            # ``secs`` 3-tuple every other format branch unpacks is untouched.
            # NULL provenance stays None (never fabricated).
            json_secs = con.execute(
                "SELECT section_index, title, prose_text, prose_provenance "
                "FROM deliverable_sections WHERE deliverable_id = ? "
                "ORDER BY section_index ASC", [deliverable_id],
            ).fetchall()
            # GPW SPR-04 STRETCH: resolve the section provenance to the TITLES
            # of the documents that ground this deliverable, and render them as
            # a Sources section in the human-readable exports (the JSON bundle
            # already carries the raw per-section provenance map). §9.0-gated:
            # personal_reading / restricted documents are never named; a
            # withheld source is indistinguishable from no source at all, so a
            # public/monetized export cannot hint one exists. Resolved on THIS
            # read_only connection; no second handle, single-writer untouched.
            sources = resolve_deliverable_sources(con, deliverable_id)
        finally:
            con.close()

        def _decode_provenance(raw: Any) -> Any:
            if not raw:
                return None
            try:
                return _json.loads(raw)
            except (ValueError, TypeError):
                return None
        title = head[0]
        kind = head[1]
        if format == "markdown":
            lines = [f"# {title}", "", f"_{kind}_", ""]
            for idx, sec_title, prose in secs:
                lines.append(f"## {sec_title or f'Section {idx + 1}'}")
                lines.append("")
                lines.append((prose or "_(no prose yet)_").strip())
                lines.append("")
            if sources:
                lines.append("## Sources")
                lines.append("")
                for src in sources:
                    # Collapse internal whitespace so a title with a stray
                    # newline can't break the list item onto its own line.
                    lines.append(f"- {' '.join(src.split())}")
                lines.append("")
            content = "
".join(lines)
            return ExportFormat(
                format="markdown", content=content,
                filename=f"{deliverable_id}.md",
            )
        if format == "substack":
            # Substack-flavored markdown variant per §8.5. Substack's
            # import flow injects its own H1 from the post title field,
            # so we OMIT the leading `# {title}` line that the standard
            # markdown export emits. We also preserve em-dashes
            # verbatim (Substack's editor renders them correctly) and
            # use ``> `` blockquote for the deliverable kind label so
            # Substack's reader UI distinguishes metadata from prose.
            lines = [f"> _{kind}_", ""]
            for idx, sec_title, prose in secs:
                lines.append(f"## {sec_title or f'Section {idx + 1}'}")
                lines.append("")
                lines.append((prose or "_(no prose yet)_").strip())
                lines.append("")
            if sources:
                lines.append("## Sources")
                lines.append("")
                for src in sources:
                    lines.append(f"- {' '.join(src.split())}")
                lines.append("")
            content = "
".join(lines)
            return ExportFormat(
                format="substack", content=content,
                filename=f"{deliverable_id}.substack.md",
            )
        if format == "html":
            def esc(s: str | None) -> str:
                return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
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
                    for para in prose.split("

"):
                        parts.append(f"<p>{esc(para)}</p>")
                else:
                    parts.append("<p><em>(no prose yet)</em></p>")
            if sources:
                parts.append("<h2>Sources</h2>")
                parts.append("<ul>")
                for src in sources:
                    parts.append(f"<li>{esc(src)}</li>")
                parts.append("</ul>")
            parts.append("</body></html>")
            content = "
".join(parts)
            return ExportFormat(
                format="html", content=content,
                filename=f"{deliverable_id}.html",
            )
        if format == "pdf":
            # Sprint 15 §3.4 PDF export. Renders the HTML produced by
            # the ``html`` branch through xhtml2pdf (pure-Python; pulls
            # reportlab + Pillow). Base64-encodes the bytes so the
            # JSON response shape stays uniform with the other formats.
            #
            # If xhtml2pdf isn't installed the endpoint returns 503
            # rather than crashing on import — operator installs via
            # ``pip install -e '.[export]'`` and retries.
            try:
                # optional 'export' extra; not installed in the lint env
                from xhtml2pdf import (  # type: ignore[import-not-found, import-untyped, unused-ignore]
                    pisa,
                )
except ImportError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"backtest module unavailable: {exc!r}",
            ) from exc

        try:
            with connect_read(default_db_path()) as con:
                report = backtest(con, synthesis_id)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"synthesis not archived: {exc!r}",
            ) from exc
        except Exception as exc:
            # Most likely: synthesis_id doesn't exist in archives.
            raise HTTPException(
                status_code=404,
                detail=f"backtest unavailable for {synthesis_id!r}: {exc!r}",
            ) from exc

        return BacktestReportResponse(
            synthesis_id=report.synthesis_id,
            synthesis_timestamp=str(report.synthesis_timestamp),
            target_question=report.target_question,
            status=report.status,
            implicit_recommendation=report.implicit_recommendation,
            substrate_manifest_counts=dict(report.substrate_manifest_counts),
            added_edges_since=report.added_edges_since,
            superseded_edges_since=report.superseded_edges_since,
            cited_edges_now_superseded_count=report.load_bearing_edges_invalidated,
            chunks_retired_downward_count=report.cited_chunks_demoted,
            outcomes_recorded=report.outcomes_recorded,
            cited_edges_now_superseded=[
                dataclasses.asdict(e) for e in report.cited_edges_now_superseded
            ],
            chunks_retired_downward=[
                dataclasses.asdict(c) for c in report.chunks_retired_downward
            ],
            outcomes=list(report.outcomes),
        )

    # ── Sprint 30+ deletion-request endpoints (§13.3) ──
    class DeletionRequestResponse(BaseModel):
        request_id: str
        user_id: str
        status: str
        requested_at: str
        updated_at: str
        reason: str | None
        cancellation_window_days: int = 7
        deletion_sla_days: int = 30

    class DeletionRequestListResponse(BaseModel):
        requests: list[DeletionRequestResponse]

    def _deletion_request_row_to_response(
        row: Any,
    ) -> DeletionRequestResponse:
        return DeletionRequestResponse(
            request_id=row[0],
            user_id=row[1],
            status=row[2],
            requested_at=(
                row[3].isoformat() if hasattr(row[3], "isoformat")
                else str(row[3])
            ),
            updated_at=(
                row[4].isoformat() if hasattr(row[4], "isoformat")
                else str(row[4])
            ),
            reason=row[5],
        )

    @app.post(
        "/trust-center/deletion-requests",
        response_model=DeletionRequestResponse,
        status_code=201,
    )
    async def post_deletion_request(
        request: Request,
        req: DeletionRequestBody = Body(...),
    ) -> DeletionRequestResponse:
        """Schedule a user's 'delete everything' request. Per master-
        spec §13.3: 30-day SLA, 7-day cancellation window. Identity
        comes from the auth middleware via request.state."""
        import uuid as _uuid

        from runtime.db_lock import connect_write
        from substrate.graph import default_db_path

        user_id = getattr(request.state, "user_id", None) or "__operator__"
        request_id = f"del-{_uuid.uuid4().hex[:12]}"

        def _sync() -> Any:
            with connect_write(
                default_db_path(), purpose="api:deletion_request",
            ) as con:
                con.execute(
                    """
                    INSERT INTO deletion_requests (
                        request_id, user_id, status, reason
                    ) VALUES (?, ?, 'pending', ?)
                    """,
                    [request_id, user_id, req.reason],
                )
                return con.execute(
                    "SELECT request_id, user_id, status, requested_at, "
                    "updated_at, reason FROM deletion_requests WHERE request_id = ?",
                    [request_id],
                ).fetchone()

        # flock wait off the uvicorn loop (#3111 to_thread class).
        row = await asyncio.to_thread(_sync)
        return _deletion_request_row_to_response(row)

    @app.get(
        "/trust-center/deletion-requests",
        response_model=DeletionRequestListResponse,
    )
    async def list_deletion_requests(
        request: Request,
    ) -> DeletionRequestListResponse:
        """List the calling user's deletion requests, newest first.
        Strict per-user scope: a user only sees their own requests."""
        from runtime.db_lock import connect_read
        from substrate.graph import default_db_path

        user_id = getattr(request.state, "user_id", None) or "__operator__"
        try:
            with connect_read(default_db_path()) as con:
                rows = con.execute(
                    "SELECT request_id, user_id, status, requested_at, "
                    "updated_at, reason FROM deletion_requests "
                    "WHERE user_id = ? ORDER BY requested_at DESC",
                    [user_id],
                ).fetchall()
        except Exception:
            rows = []
        return DeletionRequestListResponse(
            requests=[
                _deletion_request_row_to_response(r) for r in rows
            ],
        )

    @app.post(
        "/trust-center/deletion-requests/{request_id}/cancel",
        response_model=DeletionRequestResponse,
    )
    async def cancel_deletion_request(
        request_id: str, request: Request,
    ) -> DeletionRequestResponse:
        """Cancel a pending deletion request. Only the originating
        user can cancel their own request, and only while it's
        still in the pending state."""
        from runtime.db_lock import connect_write
        from substrate.graph import default_db_path

        user_id = getattr(request.state, "user_id", None) or "__operator__"

        def _sync() -> Any:
            with connect_write(
                default_db_path(), purpose="api:cancel_deletion",
            ) as con:
                row = con.execute(
                    "SELECT request_id, user_id, status FROM deletion_requests "
                    "WHERE request_id = ?",
                    [request_id],
                ).fetchone()
                if row is None:
                    raise HTTPException(
                        status_code=404, detail="deletion request not found",
                    )
                if row[1] != user_id:
                    raise HTTPException(
                        status_code=403,
                        detail="only the originating user can cancel",
                    )
                if row[2] != "pending":
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "wrong_status",
                            "message": (
                                f"cannot cancel — current status is "
                                f"{row[2]!r}; cancellation only valid in "
                                "the 'pending' state"
                            ),
                        },
                    )
                con.execute(
                    """
                    UPDATE deletion_requests
                    SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                    WHERE request_id = ?
                    """,
                    [request_id],
                )
                return con.execute(
                    "SELECT request_id, user_id, status, requested_at, "
                    "updated_at, reason FROM deletion_requests "
                    "WHERE request_id = ?",
                    [request_id],
                ).fetchone()

        # flock wait off the uvicorn loop (#3111 to_thread class).
        updated = await asyncio.to_thread(_sync)
        return _deletion_request_row_to_response(updated)

    # ── Sprint 30+ substrate stats summary (§13.7 audit) ──
    class SubstrateStatsResponse(BaseModel):
        counts: dict[str, int]
        warnings: list[str]

    @app.get(
        "/stats",
        response_model=SubstrateStatsResponse,
    )
    async def get_substrate_stats() -> SubstrateStatsResponse:
        """Operator-facing summary of substrate cardinality across
        every load-bearing table. Per master-spec §13.7 audit: this
        is the 'what does the substrate look like right now' surface
        operators reach for before grading outcomes or running the
        Phase 8 gate."""
        from runtime.db_lock import connect_read
        from substrate.graph import default_db_path

        # Tables to summarize. Each entry maps the response key →
        # the SQL table. Missing tables are skipped (the substrate
        # may not have provisioned them yet on a fresh install).
        TABLES = [
            ("investigations", "syntheses"),
            ("documents", "documents"),
            ("chunks", "chunks"),
            ("nodes", "nodes"),
            ("edges", "edges"),
            ("outcomes", "outcomes"),
            ("notebooks", "notebooks"),
            ("notebook_blocks", "notebook_blocks"),
            ("ip_holders", "ip_holders"),
            ("skill_rules", "skill_rules"),
            ("payout_transfers", "payout_transfers"),
            ("deletion_requests", "deletion_requests"),
            ("interview_projects", "interview_projects"),
            ("interviews", "interviews"),
        ]

        counts: dict[str, int] = {}
        warnings: list[str] = []
        try:
            with connect_read(default_db_path()) as con:
                for key, table in TABLES:
                    try:
                        row = con.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()
                        counts[key] = int(row[0]) if row else 0
                    except Exception:
                        # Table missing — substrate is partially
                        # provisioned (legit for fresh deployments).
                        warnings.append(f"table {table!r} not present")
                        counts[key] = 0
        except Exception as exc:
            warnings.append(f"stats partially unavailable: {exc!r}")

        return SubstrateStatsResponse(
            counts=counts,
            warnings=warnings,
        )

    # ── Sprint 30+ documents listing (§4.1) ──
    class DocumentSummary(BaseModel):
        document_id: str
        title: str | None
        source_uri: str | None
        document_type: str | None
        source_tier: int
        investigation_id: str | None
        content_class: str | None
        ip_holder_id: str | None

    class DocumentListResponse(BaseModel):
        documents: list[DocumentSummary]

    @app.get(
        "/documents",
        response_model=DocumentListResponse,
    )
    async def list_documents(
        source_tier: int | None = Query(default=None, ge=1, le=5),
        investigation_id: str | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=2000),
    ) -> DocumentListResponse:
        """List documents in the substrate. Filterable by source_tier
        and investigation_id. Per §13.3 retrieval-time gates the
        listing inherits the substrate's gating posture."""
        from runtime.db_lock import connect_read
        from substrate.graph import default_db_path

        clauses: list[str] = []
        params: list[Any] = []
        if source_tier is not None:
            clauses.append("source_tier = ?")
            params.append(source_tier)
        if investigation_id is not None:
            clauses.append("investigation_id = ?")
            params.append(investigation_id)
        where = ""
        if clauses:
            where = " WHERE " + " AND ".join(clauses)
        sql = (
            "SELECT document_id, title, source_uri, document_type, "
            "source_tier, investigation_id, content_class, ip_holder_id "
            "FROM documents" + where +
            " ORDER BY document_id DESC LIMIT ?"
        )
        params.append(limit)
        try:
            with connect_read(default_db_path()) as con:
                rows = con.execute(sql, params).fetchall()
        except Exception:
            rows = []
        out: list[DocumentSummary] = []
        for r in rows:
            out.append(DocumentSummary(
                document_id=r[0],
                title=r[1],
                source_uri=r[2],
                document_type=r[3],
                source_tier=int(r[4]),
                investigation_id=r[5],
                content_class=r[6],
                ip_holder_id=r[7],
            ))
        return DocumentListResponse(documents=out)

    # ── Sprint 30+ shared-substrate skill rule listing (§13.2) ──
    class SkillRuleResponse(BaseModel):
        rule_id: str
        rule_text: str
        rule_kind: str
        domain: str
        epsilon_budget_consumed: float
        source_user_count: int
        confidence: str
        extracted_at: str | None = None

    class SkillRuleListResponse(BaseModel):
        rules: list[SkillRuleResponse]

    @app.get(
        "/skill-rules/{rule_id}",
        response_model=SkillRuleResponse,
    )
    async def get_skill_rule(rule_id: str) -> SkillRuleResponse:
        """Point-fetch one rule by id. Returns 404 if the rule_id
        doesn't exist in the shared substrate."""
        from runtime.db_lock import connect_read
        from substrate.graph import default_db_path

        try:
            with connect_read(default_db_path()) as con:
                row = con.execute(
                    "SELECT rule_id, rule_text, rule_kind, domain, "
                    "epsilon_budget_consumed, source_user_count, confidence, "
                    "extracted_at "
                    "FROM skill_rules WHERE rule_id = ?",
                    [rule_id],
                ).fetchone()
        except Exception:
            row = None
        if row is None:
            raise HTTPException(status_code=404, detail="skill rule not found")
        return SkillRuleResponse(
            rule_id=row[0],
            rule_text=row[1],
            rule_kind=row[2],
            domain=row[3],
            epsilon_budget_consumed=float(row[4]),
            source_user_count=int(row[5]),
            confidence=row[6],
            extracted_at=(
                row[7].isoformat() if row[7] is not None and hasattr(row[7], "isoformat")
                else (str(row[7]) if row[7] is not None else None)
            ),
        )

    @app.get(
        "/skill-rules",
        response_model=SkillRuleListResponse,
    )
    async def list_skill_rules(
        domain: str | None = Query(default=None),
        confidence: str | None = Query(default=None),
        q: str | None = Query(default=None, max_length=500),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> SkillRuleListResponse:
        """List promoted skill rules from the shared substrate. Per
        master-spec §13.2: these are the cross-user discovered rules
        the accumulator + writer landed. The endpoint reads the
        ``skill_rules`` table maintained by
        ``substrate/multi_user/skill_propagation.py``."""
        from runtime.db_lock import connect_read
        from substrate.graph import default_db_path

        # Build the WHERE clause from optional filters.
        clauses: list[str] = []
        params: list[Any] = []
        if domain is not None:
            clauses.append("domain = ?")
            params.append(domain)
        if confidence is not None:
            clauses.append("confidence = ?")
            params.append(confidence)
        if q is not None and q.strip():
            # Case-insensitive substring search on rule_text.
            clauses.append("LOWER(rule_text) LIKE LOWER(?)")
            params.append(f"%{q.strip()}%")
        where = ""
        if clauses:
            where = " WHERE " + " AND ".join(clauses)
        sql = (
            "SELECT rule_id, rule_text, rule_kind, domain, "
            "epsilon_budget_consumed, source_user_count, confidence, "
            "extracted_at "
            "FROM skill_rules"
            + where
            + " ORDER BY extracted_at DESC LIMIT ?"
        )
        params.append(limit)

        rules: list[SkillRuleResponse] = []
        try:
            with connect_read(default_db_path()) as con:
                rows = con.execute(sql, params).fetchall()
            for r in rows:
                rules.append(SkillRuleResponse(
                    rule_id=r[0],
                    rule_text=r[1],
                    rule_kind=r[2],
                    domain=r[3],
                    epsilon_budget_consumed=float(r[4]),
                    source_user_count=int(r[5]),
                    confidence=r[6],
                    extracted_at=(
                        r[7].isoformat() if r[7] is not None and hasattr(r[7], "isoformat")
                        else (str(r[7]) if r[7] is not None else None)
                    ),
                ))
        except Exception:
            # The skill_rules table is created lazily by the writer.
            # An empty/missing table is a normal pre-promotion state;
            # return an empty list rather than 500.
            rules = []

        return SkillRuleListResponse(rules=rules)

    # ── Sprint 19 Trust Center publication endpoint (§13.7) ──
    class TrustCenterPublication(BaseModel):
        differential_privacy_epsilon_budgets: dict[str, float]
        deletion_sla_days: int
        substrate_controls: list[str]
        compliance_frameworks: list[str]
        loop_3_unlock_status: dict[str, bool]
        website_ads: dict[str, Any]
        speak_economics: dict[str, Any]

    @app.get(
        "/trust-center",
        response_model=TrustCenterPublication,
    )
    async def trust_center() -> TrustCenterPublication:
        """Public-facing Trust Center surface. Per master-spec §13.7:
        published privacy architecture description, DP parameters,
        deletion SLA, incident-response process. Loop 3 unlock state
        reads from the persistent checklist (§14.2)."""
        from runtime.db_lock import connect_read
        from substrate.graph import default_db_path
        from substrate.loop_3.checklist_store import snapshot

        try:
            with connect_read(default_db_path()) as con:
                snap = snapshot(con)
            loop_3_status = snap.criteria
        except Exception:
            # If the DB isn't reachable, default to all-False — never
            # publish an over-claim about unlock state.
            loop_3_status = {
                "trajectory_volume": False,
                "sft_readiness": False,
                "validated_reward": False,
                "open_weight_justification": False,
                "eval_headroom": False,
            }

        from substrate.ad_inventory.rank0_honesty import website_ads_honesty
        from substrate.speak.g2_synquery_honesty import g2_synquery_honesty

        return TrustCenterPublication(
            differential_privacy_epsilon_budgets={
                "skill_invocation_frequency": 2.0,
                "source_tier_preference_signals": 1.0,
                "query_content_telemetry": 0.0,  # not collected
            },
            deletion_sla_days=30,
            substrate_controls=[
                "encryption at rest (per-graph keys via KMS)",
                "access logging (append-only)",
                "change management (CI gates on schema)",
                "vulnerability scanning (Dependabot/Snyk)",
                "backup testing (quarterly restore drill)",
                "retrieval-time policy_tag gating (§9.0)",
            ],
            compliance_frameworks=[
                "GDPR Article 13/14 transparency",
                "CCPA notice + opt-out",
                "engineering-grade differential privacy (ε ≤ 10 hard cap)",
                "SOC 2 Type II — deferred (not required for consumer Phase 1)",
            ],
            loop_3_unlock_status=loop_3_status,
            website_ads=website_ads_honesty(),
            speak_economics=g2_synquery_honesty(),
        )

    # ── Speak workflow (specs/speak/) — the fourth workflow's REST
    #    surface. Kept in its own module (interfaces/research/api/
    #    speak_routes.py) so this hot factory stays mergeable; included
    #    here with one line. The router carries no auth (the global
    #    operator-auth middleware above covers it). See
    #    docs/decisions/speak_workflow.md.
    from interfaces.research.api.speak_routes import speak_router
    app.include_router(speak_router)

    # Cross-workflow thread navigation (antiek-unified SPR-06). Read-only:
    # GET /thread/{node_id} reconstructs an entity's cross-workflow trajectory
    # from the SPR-03 seam events. A VIEW over existing nodes/edges + seam
    # events — it writes nothing and adds no node/edge type. Powers the
    # ThreadBreadcrumb + ThreadJump in apps/reading/src/shell/. See
    # substrate/seams/thread.py.
    from interfaces.research.api.thread import make_router as make_thread_router
    app.include_router(make_thread_router())

    # Write workflow REST surface (specs/write/). Net-new router, same
    # one-line inclusion discipline as speak_routes so this hot factory
    # stays mergeable. Wires substrate/write + substrate/edit to HTTP.
    from interfaces.research.api.write_routes import write_router
    app.include_router(write_router)

    # Deep Research Workspace transport (specs/deep-research-workspace/
    # SPR-06). The cascade plan/launch/session-stream/steer/cost surface the
    # SPR-09 glass-box monitor consumes — same one-line inclusion discipline.
    # Wires the SPR-05 planner + SPR-02 runner + SPR-06 CascadeSession to HTTP.
    from interfaces.research.api.cascade_routes import cascade_router
    app.include_router(cascade_router)

    # Distill surface (specs/product-depth/ SPR-03). Reads the shipped
    # insight/question graph nodes for a research and drives the shipped
    # living-note challenge path — same one-line inclusion discipline. The
    # only graph write (a challenge) serializes through runtime/db_lock
    # inside roles.note_taker.living_note; this router adds no second writer.
    from interfaces.research.api.distill_routes import distill_router
    app.include_router(distill_router)

    # ResearchArtifact HTML transport (ANT-AHT SPR-AHT-06). Export, outline
    # blocks, and agent-note import — same one-line inclusion discipline.
    from interfaces.research.api.artifact_routes import artifact_router
    app.include_router(artifact_router)

    from interfaces.research.api.feedback_routes import feedback_router
    app.include_router(feedback_router)

    from interfaces.research.api.agent_work_routes import agent_work_router
    app.include_router(agent_work_router)

    # Full-graph export bundle (own-your-mind P1 §6, read half). GET
    # /export/my-graph streams a zip of the DuckDB EXPORT snapshot + the
    # event-log parquets/jsonl + manifest.json. Read-only: never opens the
    # source graph for write (see export_routes module docstring for the
    # flock rationale). Same one-line inclusion discipline.
    from interfaces.research.api.export_routes import register_export_routes
    register_export_routes(app)

    # Supersession review surface (GF-5/GF-6 activation). Turns detected
    # contradictions into a review queue — the other half of the detection
    # wired in processing/extraction/extract.py. Same one-line inclusion
    # discipline; carries no per-handler auth (global middleware gates the
    # operator workstation, matching write_routes).
    from interfaces.research.api.supersession_routes import supersession_router
    app.include_router(supersession_router)

    # Style wheel HTTP surface (spec §5.5 S2) — GET/POST /styles (fork
    # management, per-user persistence), DELETE /styles/{name}, and
    # GET /artifacts/{id}/render (deterministic restyle, no model call).
    # Same one-line inclusion discipline; the auth middleware attaches the
    # caller's user_id and the routes key forks by it.
    from interfaces.research.api.style_routes import style_router
    app.include_router(style_router)

    from interfaces.research.api.account_memory_routes import account_memory_router
    app.include_router(account_memory_router)

    def _recover_knowledge_event_projector() -> None:
        import threading

        # Kill switch for the event-projector recovery worker.
        #
        # INCIDENT 2026-08-13: on the production box the worker churns at
        # ~100% CPU with all three projector tables (frontiers/events/
        # receipts) empty while write_log accrues ~2 rows per 0.5s pass
        # (130,887 frontier-snapshot rows accumulated). The per-event
        # transactions fail in-process (the same DuckDB config-conflict
        # family as the frame_telemetry 500s) and the retry loop never
        # converges; the constant checkpointing re-fragments the DuckDB
        # file (~2 MB/min) and re-wedges the API. The projector has
        # delivered nothing since at least 2026-08-13 03:00Z (backup
        # counts: 0/0/0), so disabling the worker loses no function.
        # Set ANTIEK_DISABLE_EVENT_PROJECTOR_RECOVERY=1 to disable;
        # unset + redeploy to re-enable once the root cause (in-process
        # mixed-config connections) is fixed.
        if os.environ.get("ANTIEK_DISABLE_EVENT_PROJECTOR_RECOVERY", "").strip() == "1":
            return

        # Recovery is a startup reader/consumer, not a migration owner. Route
        # handlers retain their legacy lazy-init seam for now; this worker must
        # wait for deployment to provide the complete schema.
        from substrate.graph import default_db_path

        db_path = default_db_path()
        stop_recovery = threading.Event()
        app.state.knowledge_event_recovery_stop = stop_recovery
        app.state.knowledge_event_recovery = {
            "status": "catching_up",
            "catching_up": True,
        }

        def run_recovery() -> None:
            from runtime.db_lock import write_handoff_requested
            from substrate.event_log import PhysicalTrajectoryError
            from substrate.graph.knowledge_event_projector import (
                EventConsumerCorruption,
                recover,
            )
            from substrate.graph.schema import SchemaCorruptionError

            transient_failures = 0
            while not stop_recovery.is_set():
                try:
                    # A signalled foreground/deploy writer owns admission.
                    # Do not enter another recovery transaction until every
                    # live waiter has either acquired or withdrawn its token.
                    if write_handoff_requested(db_path):
                        stop_recovery.wait(0.05)
                        continue
                    report = recover(
                        db_path=db_path,
                        candidate_limit=100,
                        wall_time_s=0.5,
                        should_stop=stop_recovery.is_set,
                    )
                    transient_failures = 0
                    app.state.knowledge_event_recovery = {
                        "status": "catching_up" if report.catching_up else "current",
                        **report.as_dict(),
                    }
                    if not report.catching_up:
                        # Other processes may append after startup. The durable
                        # consumer remains a low-frequency poller so delivery
                        # does not depend on an in-process broadcaster wake-up.
                        if stop_recovery.wait(0.5):
                            break
                        continue
                    # A production-sized DuckDB can make even a bounded page
                    # expensive. Yield longer only when another process has
                    # actually reported contention; uncontended catch-up keeps
                    # its existing throughput.
                    if write_handoff_requested(db_path):
                        stop_recovery.wait(0.5)
                    else:
                        stop_recovery.wait(0.05)
                except (
                    EventConsumerCorruption,
                    PhysicalTrajectoryError,
                    SchemaCorruptionError,
                ) as exc:
                    app.state.knowledge_event_recovery = {
                        "status": "error",
                        "catching_up": True,
                        "terminal": True,
                        "error_class": type(exc).__name__,
                    }
                    print(
                        f"Knowledge event projection recovery stopped: {exc!r}",
                        file=sys.stderr,
                    )
                    break
                except Exception as exc:
                    transient_failures += 1
                    delay = min(0.05 * (2 ** (transient_failures - 1)), 0.5)
                    app.state.knowledge_event_recovery = {
                        "status": "retrying",
                        "catching_up": True,
                        "terminal": False,
                        "error_class": type(exc).__name__,
                        "retry_count": transient_failures,
                        "retry_in_s": delay,
                    }
                    if stop_recovery.wait(delay):
                        break

        worker = threading.Thread(
            target=run_recovery,
            name="knowledge-event-recovery",
            daemon=True,
        )
        app.state.knowledge_event_recovery_worker = worker
        worker.start()

    def _stop_knowledge_event_projector() -> None:
        stop = getattr(app.state, "knowledge_event_recovery_stop", None)
        worker = getattr(app.state, "knowledge_event_recovery_worker", None)
        if stop is not None:
            stop.set()
        if worker is not None:
            # Providers are outside our cancellation boundary. Give an active
            # graph transaction a bounded grace period; DuckDB commits it
            # atomically or rolls it back when systemd terminates the process.
            # Recovery re-checks the stop signal after every provider call, so
            # a blocked provider cannot begin a new mutation after shutdown.
            worker.join(timeout=1.0)
            if worker.is_alive():
                app.state.knowledge_event_recovery = {
                    "status": "stopping",
                    "catching_up": True,
                    "worker_alive": True,
                }

    def _recover_note_taker_replay() -> None:
        from substrate.graph import default_db_path

        from .note_taking import start_replay_recovery

        stop = threading.Event()
        app.state.note_taker_recovery_stop = stop
        app.state.note_taker_recovery_worker = start_replay_recovery(
            db_path=default_db_path(),
            stop_event=stop,
        )

    def _stop_note_taker_replay() -> None:
        stop = getattr(app.state, "note_taker_recovery_stop", None)
        worker = getattr(app.state, "note_taker_recovery_worker", None)
        if stop is not None:
            stop.set()
        if worker is not None:
            worker.join(timeout=1.0)


    def _recover_stranded_dispatch() -> None:
        from .stranded_dispatch_recovery import start_stranded_dispatch_recovery

        stop = threading.Event()
        app.state.stranded_dispatch_recovery_stop = stop
        app.state.stranded_dispatch_recovery_worker = start_stranded_dispatch_recovery(
            stop_event=stop,
        )

    def _stop_stranded_dispatch() -> None:
        stop = getattr(app.state, "stranded_dispatch_recovery_stop", None)
        worker = getattr(app.state, "stranded_dispatch_recovery_worker", None)
        if stop is not None:
            stop.set()
        if worker is not None:
            worker.join(timeout=1.0)


    app.router.on_startup.append(_recover_knowledge_event_projector)
    app.router.on_startup.append(_recover_note_taker_replay)
    app.router.on_startup.append(_recover_stranded_dispatch)
    app.router.on_shutdown.append(_stop_knowledge_event_projector)
    app.router.on_shutdown.append(_stop_note_taker_replay)
    app.router.on_shutdown.append(_stop_stranded_dispatch)
    return app


# Default app instance for ``uvicorn interfaces.research.api.app:app``.
app = create_app()
