"""Engagement spine REST surface — research↔reading workstation.

Standalone APIRouter (same discipline as settings_budget / write_routes):
testable alone; included with one line.

Store backend:
  * ``ANTIEK_ENGAGEMENT_DIR`` set → durable ``FileEngagementStore`` +
    ``FileSessionStore`` under that directory (JSON files).
  * unset → process-local in-memory stores (tests / single-worker MVP).

Surfaces:
  POST /engagement/spawn-from-highlight
  POST /engagement/attach-refs
  POST /engagement/research-context
  POST /engagement/collective
  POST /engagement/merge
  POST /engagement/hydrate-ref
  POST /engagement/progress
  GET  /engagement/progress/{spawn_id}
  POST /engagement/evidence-pack
  GET  /engagement/twins/{asset_id}
  POST /engagement/twins
  POST /engagement/twins/promote-context
  POST /engagement/context-search
  POST /engagement/sessions/open
  POST /engagement/sessions/complete-flywheel
  GET  /engagement/sessions/asset/{parent_asset_id}
  GET  /engagement/sessions/{session_id}
  PUT  /engagement/sessions/{session_id}/view
  POST /engagement/sessions/context
  POST /engagement/sessions/collective
  POST /engagement/sessions/merge
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.engagement_spine import (
    HighlightSelection,
    InMemoryEngagementStore,
    assemble_research_context,
    attach_source_references,
    evidence_pack_payload,
    hydrate_reference,
    merge_product_payload,
    merge_spawns_collective,
    progress_payload,
    record_progress,
    record_twin_product,
    search_engagement_context,
    seed_default_pipeline,
    spawn_from_highlight_with_references,
    twin_promote_context_payload,
    twins_product_payload,
)
from substrate.engagement_spine.store import (
    EngagementStore,
    FileEngagementStore,
    document_revision_sha256,
    owned_document_id,
)
from substrate.floating_session import (
    compare_and_set_view_mode,
    complete_session_with_context_flywheel,
    get_session,
    list_sessions_for_asset,
    merge_sessions,
    open_from_highlight_with_references,
    project_session_html,
    session_context_html,
    session_research_context,
    sessions_collective_html,
    sessions_collective_research,
)
from substrate.floating_session.merge_receipt import (
    FileMergeReceiptStore,
    InMemoryMergeReceiptStore,
    MergeReceiptStore,
    merge_material_sha256,
    merge_receipt_id,
)
from substrate.floating_session.store import (
    FileSessionStore,
    InMemorySessionStore,
    SessionStore,
)

engagement_router = APIRouter(prefix="/engagement", tags=["engagement"])

# Lazily constructed stores. Tests call reset_engagement_stores().
_engagement_store: EngagementStore | None = None
_session_store: SessionStore | None = None
_merge_receipt_store: MergeReceiptStore | None = None
_bench_usage_store: Any = None


def get_bench_usage_store(*, create_if_missing: bool = True) -> Any:
    """Antiek-bench usage store shared with settings summary.

    Resolution (shipped ``resolve_usage_store``):
    * ``ANTIEK_BENCH_USAGE_DIR`` set → durable FileBenchStore (survives restart)
    * unset → process-local InMemoryBenchStore (default for tests/CI)

    When ``create_if_missing`` is False and no store was opened yet and no
    durable env is set, returns None.
    """
    global _bench_usage_store
    if _bench_usage_store is None:
        from substrate.antiek_bench import resolve_usage_store

        _bench_usage_store = resolve_usage_store(create_if_missing=create_if_missing)
    return _bench_usage_store


def reset_bench_usage_store(*, root: Path | str | None = None) -> Any:
    """Rebuild usage store (tests). Pass root for durable FileBenchStore."""
    global _bench_usage_store
    from substrate.antiek_bench import resolve_usage_store

    _bench_usage_store = resolve_usage_store(root=root, create_if_missing=True)
    return _bench_usage_store


def engagement_data_dir() -> Path | None:
    """Resolve durable root when ANTIEK_ENGAGEMENT_DIR is set."""
    raw = (os.environ.get("ANTIEK_ENGAGEMENT_DIR") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def reset_engagement_stores(*, root: Path | None = None) -> None:
    """Rebuild stores (tests + operator reset).

    If ``root`` is provided, use file stores at that path. Else honor
    ``ANTIEK_ENGAGEMENT_DIR``, else in-memory.
    """
    global _engagement_store, _merge_receipt_store, _session_store
    base = root if root is not None else engagement_data_dir()
    if base is not None:
        base = Path(base)
        base.mkdir(parents=True, exist_ok=True)
        _engagement_store = FileEngagementStore(base / "engagement")
        _session_store = FileSessionStore(base / "sessions")
        _merge_receipt_store = FileMergeReceiptStore(base / "merge_receipts")
    else:
        _engagement_store = InMemoryEngagementStore()
        _session_store = InMemorySessionStore()
        _merge_receipt_store = InMemoryMergeReceiptStore()


def _eng() -> EngagementStore:
    global _engagement_store
    if _engagement_store is None:
        reset_engagement_stores()
    assert _engagement_store is not None
    return _engagement_store


def get_engagement_store(*, create_if_missing: bool = True) -> EngagementStore:
    """Public accessor for other product routers (marketplace twin seed, etc.)."""
    if create_if_missing:
        return _eng()
    global _engagement_store
    if _engagement_store is None:
        raise RuntimeError("engagement store not initialized")
    return _engagement_store


def _sess() -> SessionStore:
    global _session_store
    if _session_store is None:
        reset_engagement_stores()
    assert _session_store is not None
    return _session_store


def _receipts() -> MergeReceiptStore:
    global _merge_receipt_store
    if _merge_receipt_store is None:
        reset_engagement_stores()
    assert _merge_receipt_store is not None
    return _merge_receipt_store


def _request_owner(request: Request) -> str:
    """Read middleware-authenticated identity; no implicit principal exists."""
    owner = str(getattr(request.state, "user_id", "") or "").strip()
    if not owner and os.environ.get("ANTIEK_ALLOW_UNAUTHENTICATED_LOCAL") == "1":
        owner = "__operator__"
    if not owner:
        raise HTTPException(status_code=401, detail="authenticated identity is unavailable")
    return owner


def _require_legacy_operator(request: Request) -> None:
    """Close legacy global engagement routes until their stores are owner-native."""
    if _request_owner(request) != "__operator__":
        raise HTTPException(status_code=403, detail="owner-scoped session route required")


# ── request / response models ────────────────────────────────────────────


class HighlightBody(BaseModel):
    asset_id: str
    selection_text: str
    region_id: str | None = None
    page: int | None = None
    goal_hint: str | None = None
    model_id: str | None = None
    references: list[str] = Field(default_factory=list)
    force_new: bool = False
    # Residual (ji): closed research tier for reserved spawn (fast|deep|wrestle).
    research_tier: Literal["fast", "deep", "wrestle"] | None = None


class AttachRefsBody(BaseModel):
    spawn_id: str
    references: list[str]


class ResearchContextBody(BaseModel):
    asset_id: str
    spawn_id: str | None = None
    query: str | None = None
    include_twin_promote: bool = True


class CollectiveBody(BaseModel):
    spawn_ids: list[str]
    query: str | None = None
    include_twin_promote: bool = True


class MergeBody(BaseModel):
    """Merge completed deep-research spawns into parent or draft-combined."""

    parent_asset_id: str = Field(min_length=1)
    spawn_ids: list[str] = Field(min_length=1)
    mode: Literal["into_parent", "draft_combined"] = "draft_combined"
    parent_title: str | None = None
    parent_body: str | None = None
    include_html: bool = True


class HydrateRefBody(BaseModel):
    """Hydrate arxiv/substack/url into an HTML-first engagement asset."""

    reference: str = Field(min_length=1)
    include_html: bool = True
    attach_spawn_id: str | None = None
    # Residual (bu): offline recursive note-taker seed (insight + question)
    seed_twins: bool = True


class ProgressRecordBody(BaseModel):
    spawn_id: str = Field(min_length=1)
    stage: Literal["plan", "gather", "synthesize", "cite", "complete", "failed"]
    message: str = ""
    include_html: bool = False


class ProgressSeedBody(BaseModel):
    spawn_id: str = Field(min_length=1)
    include_html: bool = True


class EvidencePackBody(BaseModel):
    asset_id: str = Field(min_length=1)
    spawn_id: str | None = None
    include_html: bool = True


class TwinRecordBody(BaseModel):
    asset_id: str = Field(min_length=1)
    kind: Literal["insight", "question"]
    text: str = Field(min_length=1)
    source_spawn_id: str | None = None
    investigation_id: str | None = None
    include_html: bool = True


class TwinPromoteContextBody(BaseModel):
    """Promote twin notes into depth-graph context units for research prompts.

    Residual (mq): optional ``kinds`` — ``insight`` and/or ``question`` —
    selective promote for recursive note-taker merge UX.
    Residual (mx): optional ``note_ids`` multi-select for per-note promote.
    """

    asset_id: str = Field(min_length=1)
    query: str | None = None
    investigation_id: str | None = None
    include_html: bool = True
    kinds: list[Literal["insight", "question"]] | None = None
    note_ids: list[str] | None = None


class ContextSearchBody(BaseModel):
    """Search twin notes + spawn source refs (offline intelligent search)."""

    query: str = Field(min_length=1)
    asset_id: str | None = None
    spawn_id: str | None = None
    include_html: bool = True
    limit: int = 50


class SessionOpenBody(HighlightBody):
    view_mode: Literal["floating", "full"] = "floating"


class SessionFlywheelBody(BaseModel):
    session_id: str
    output_text: str
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    query: str | None = None
    record_twins: bool = True
    include_twin_promote: bool = True


class _ClosedSessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SessionViewBody(_ClosedSessionBody):
    mode: Literal["floating", "full"]
    expected_mode: Literal["floating", "full"] | None = None


class SessionContextBody(_ClosedSessionBody):
    session_id: str = Field(pattern=r"^fsess_[0-9a-f]{16}$")
    query: str | None = Field(default=None, max_length=8_000)
    include_twin_preview: bool = False
    include_prompt_block: bool = False
    include_html: bool = True


class SessionsCollectiveBody(_ClosedSessionBody):
    session_ids: list[str] = Field(min_length=1, max_length=32)
    query: str | None = Field(default=None, max_length=8_000)
    include_twin_preview: bool = False
    allow_cross_asset: bool = False
    include_prompt_block: bool = False
    include_html: bool = True

    @model_validator(mode="after")
    def _canonical_sessions(self) -> SessionsCollectiveBody:
        if len(set(self.session_ids)) != len(self.session_ids) or any(
            not session_id.startswith("fsess_") or len(session_id) != 22
            for session_id in self.session_ids
        ):
            raise ValueError("session_ids must be unique canonical session identities")
        return self


class SessionsMergeBody(_ClosedSessionBody):
    parent_asset_id: str = Field(min_length=1, max_length=512)
    session_ids: list[str] = Field(min_length=1, max_length=32)
    mode: Literal["into_parent", "draft_combined"] = "draft_combined"
    confirm_parent_write: bool = False
    expected_parent_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    include_html: bool = True
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def _canonical_sessions(self) -> SessionsMergeBody:
        if len(set(self.session_ids)) != len(self.session_ids) or any(
            not session_id.startswith("fsess_") or len(session_id) != 22
            for session_id in self.session_ids
        ):
            raise ValueError("session_ids must be unique canonical session identities")
        return self


# ── routes ───────────────────────────────────────────────────────────────


@engagement_router.post("/spawn-from-highlight", dependencies=[Depends(_require_legacy_operator)])
def post_spawn_from_highlight(body: HighlightBody) -> dict[str, Any]:
    try:
        sel = HighlightSelection(
            asset_id=body.asset_id,
            selection_text=body.selection_text,
            region_id=body.region_id,
            page=body.page,
            goal_hint=body.goal_hint,
        )
        spawn = spawn_from_highlight_with_references(
            sel,
            store=_eng(),
            references=body.references,
            model_id=body.model_id,
            force_new=body.force_new,
            research_tier=body.research_tier,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "spawn_id": spawn.spawn_id,
        "investigation_id": spawn.investigation_id,
        "parent_asset_id": spawn.parent_asset_id,
        "goal": spawn.goal,
        "status": spawn.status,
        "model_id": spawn.model_id,
        "region_id": spawn.region_id,
        "source_references": list(spawn.source_references),
        "research_tier": getattr(spawn, "research_tier", None) or "deep",
        "view_format": "html",
    }


@engagement_router.post("/attach-refs", dependencies=[Depends(_require_legacy_operator)])
def post_attach_refs(body: AttachRefsBody) -> dict[str, Any]:
    try:
        spawn, merged = attach_source_references(body.spawn_id, body.references, store=_eng())
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "spawn_id": spawn.spawn_id,
        "source_references": [r.to_dict() for r in merged],
        # Residual (ko): reserved spawn research_tier for attach UI identity.
        "research_tier": getattr(spawn, "research_tier", None) or "deep",
        "view_format": "html",
    }


@engagement_router.post("/research-context", dependencies=[Depends(_require_legacy_operator)])
def post_research_context(body: ResearchContextBody) -> dict[str, Any]:
    try:
        pack = assemble_research_context(
            body.asset_id,
            store=_eng(),
            spawn_id=body.spawn_id,
            query=body.query,
            include_twin_promote=body.include_twin_promote,
            # Offline injectable default: skip real DuckDB promote when no twins
            # need graph write — promote hooks use real promote_* only if twin
            # notes exist; for empty twins pack is still valid.
            promote_insight_fn=_offline_promote_insight if body.include_twin_promote else None,
            promote_question_fn=_offline_promote_question if body.include_twin_promote else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    out = pack.to_dict()
    out["prompt_block"] = pack.prompt_block()
    return out


@engagement_router.post("/collective", dependencies=[Depends(_require_legacy_operator)])
def post_collective(body: CollectiveBody) -> dict[str, Any]:
    try:
        unit = merge_spawns_collective(
            body.spawn_ids,
            store=_eng(),
            query=body.query,
            include_twin_promote=body.include_twin_promote,
            promote_insight_fn=_offline_promote_insight if body.include_twin_promote else None,
            promote_question_fn=_offline_promote_question if body.include_twin_promote else None,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    out = unit.to_dict()
    out["prompt_block"] = unit.prompt_block()
    # Residual (oi): Antiek-bench usage for multi-spawn cohesive unit merge.
    try:
        from substrate.antiek_bench import record_collective_merge_usage

        usage = record_collective_merge_usage(
            store=get_bench_usage_store(create_if_missing=True),
            spawn_count=len(body.spawn_ids or []),
            research_tier=getattr(unit, "recommended_research_tier", None),
            prompt_hint=(body.query or unit.prompt_block() or "")[:200],
            mode="prompt_unit",
        )
        out["usage_event"] = usage
    except Exception as exc:  # pragma: no cover — never fail collective on bench
        out["usage_event_error"] = str(exc)
    return out


@engagement_router.post("/merge", dependencies=[Depends(_require_legacy_operator)])
def post_merge(body: MergeBody) -> dict[str, Any]:
    """Merge completed spawn outputs into parent or a draft-combined document.

    Default mode is ``draft_combined`` so operators can review before full
    parent merge. Calls shipped ``merge_product_payload`` / ``merge_spawn_outputs``.
    Residual (oi): records Antiek-bench collective_merge usage (best-effort).
    """
    try:
        payload = merge_product_payload(
            body.parent_asset_id,
            body.spawn_ids,
            store=_eng(),
            mode=body.mode,
            parent_title=body.parent_title,
            parent_body=body.parent_body,
            include_html=body.include_html,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # Residual (oi): document merge / written analysis → bench feed.
    try:
        from substrate.antiek_bench import record_collective_merge_usage

        rec_tier = None
        if isinstance(payload, dict):
            tiers = payload.get("research_tiers") or []
            # Prefer wrestle > deep > fast when multi-tier merge.
            for t in ("wrestle", "deep", "fast"):
                if t in tiers or payload.get("recommended_research_tier") == t:
                    rec_tier = t
                    break
            if rec_tier is None:
                rec_tier = payload.get("recommended_research_tier")
        usage = record_collective_merge_usage(
            store=get_bench_usage_store(create_if_missing=True),
            spawn_count=len(body.spawn_ids or []),
            research_tier=str(rec_tier) if rec_tier else None,
            prompt_hint=f"parent={body.parent_asset_id}",
            mode=str(body.mode or "draft_combined"),
        )
        if isinstance(payload, dict):
            payload["usage_event"] = usage
    except Exception as exc:  # pragma: no cover — never fail merge on bench
        if isinstance(payload, dict):
            payload["usage_event_error"] = str(exc)
    return payload


# Optional injectable publication body fetcher for hydrate-ref (tests / wired apps).
# Signature: (SourceReference) -> dict with title/body_text/abstract/canonical_url.
hydrate_fetch_publication: Any = None
# Optional arXiv fetch_by_id(arxiv_id) -> ArxivPaper|dict (never silent live default).
hydrate_arxiv_fetch_by_id: Any = None
# Optional Substack fetch_post(url) -> Post|dict (never silent live default).
hydrate_substack_fetch_post: Any = None

# Optional test/application injection seam. ``None`` deliberately means the
# canonical depth-graph writers; a deployment must not silently simulate a
# successful promotion.
twin_promote_insight_fn: Any = None
twin_promote_question_fn: Any = None


def hydrate_live_status_payload(
    *,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Residual (hq): honest offline-vs-live hydrate injector readiness report.

    Never enables network. Surfaces process injectors + env flag intent so
    Settings can show operators that arxiv/substack stay offline-honest by default.
    """
    from substrate.engagement_spine.hydrate_live_wiring import (
        ANTIEK_HYDRATE_LIVE_ARXIV_ENV,
        ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV,
        env_flag,
    )

    env = environ if environ is not None else dict(os.environ)
    arxiv_env = env_flag(ANTIEK_HYDRATE_LIVE_ARXIV_ENV, environ=env)
    substack_env = env_flag(ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV, environ=env)
    arxiv_injector = hydrate_arxiv_fetch_by_id is not None
    substack_injector = hydrate_substack_fetch_post is not None
    generic_injector = hydrate_fetch_publication is not None
    any_live = arxiv_injector or substack_injector or generic_injector
    offline_honest = not any_live
    notes: list[str] = []
    if offline_honest:
        notes.append("Hydrate default: offline-honest identity — no live body injectors installed.")
    else:
        notes.append(
            "At least one live hydrate injector is process-installed "
            "(still opt-in; not silent network from UI alone)."
        )
    if arxiv_env and not arxiv_injector:
        notes.append(
            f"{ANTIEK_HYDRATE_LIVE_ARXIV_ENV}=on but arxiv injector not installed "
            "(boot wiring may have failed or not run)."
        )
    if substack_env and not substack_injector:
        notes.append(
            f"{ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV}=on but substack injector not installed "
            "(factory required; refuse auto page scrape)."
        )
    return {
        "view_format": "html",
        "product_panel": "hydrate_live_status",
        "source": "engagement_spine.hydrate_live_wiring",
        "offline_honest": offline_honest,
        "any_live_injector": any_live,
        "arxiv": {
            "env_flag": ANTIEK_HYDRATE_LIVE_ARXIV_ENV,
            "env_enabled": arxiv_env,
            "injector_installed": arxiv_injector,
        },
        "substack": {
            "env_flag": ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV,
            "env_enabled": substack_env,
            "injector_installed": substack_injector,
        },
        "generic_fetch_publication_installed": generic_injector,
        "notes": notes,
        "html": (
            '<section data-view-format="html" data-product-panel="hydrate_live_status">'
            f"<p>offline_honest={str(offline_honest).lower()} · "
            f"arxiv_injector={str(arxiv_injector).lower()} · "
            f"substack_injector={str(substack_injector).lower()}</p>"
            "<ul>" + "".join(f"<li>{n}</li>" for n in notes) + "</ul></section>"
        ),
    }


@engagement_router.get("/hydrate-live-status", dependencies=[Depends(_require_legacy_operator)])
def get_hydrate_live_status() -> dict[str, Any]:
    """GET residual (hq): offline-vs-live hydrate injector readiness (HTML-first)."""
    return hydrate_live_status_payload()


def twin_seed_live_status_payload(
    *,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Residual (hs): offline-vs-live twin seed note_taker readiness report.

    Never enables network or installs injectors. Surfaces env dual-gate + whether
    a live seed fn is process-installed (Panels always force_offline seed).
    """
    from substrate.engagement_spine.twin import (
        ANTIEK_TWIN_SEED_LIVE_ENV,
        twin_seed_live_enabled,
        twin_seed_live_fn_installed,
    )
    from substrate.engagement_spine.twin_seed_live_wiring import (
        ANTIEK_TWIN_SEED_USE_DISPATCH_ENV,
        env_flag,
    )

    env = environ if environ is not None else dict(os.environ)
    live_env = (
        twin_seed_live_enabled()
        if environ is None
        else env_flag(ANTIEK_TWIN_SEED_LIVE_ENV, environ=env)
    )
    use_dispatch = env_flag(ANTIEK_TWIN_SEED_USE_DISPATCH_ENV, environ=env)
    injector_installed = twin_seed_live_fn_installed()
    offline_honest = not injector_installed
    notes: list[str] = []
    if offline_honest:
        notes.append(
            "Twin seed default: offline-honest identity stubs (UI panels force_offline=true)."
        )
    else:
        notes.append(
            "Live note_taker seed fn is process-installed "
            "(panels still force_offline unless callers opt out)."
        )
    if live_env and not use_dispatch and not injector_installed:
        notes.append(
            f"{ANTIEK_TWIN_SEED_LIVE_ENV}=on but "
            f"{ANTIEK_TWIN_SEED_USE_DISPATCH_ENV}=off — manual configure required."
        )
    if live_env and use_dispatch and not injector_installed:
        notes.append("Dual-gate on but live seed fn not installed (boot wiring may have failed).")
    return {
        "view_format": "html",
        "product_panel": "twin_seed_live_status",
        "source": "engagement_spine.twin_seed_live_wiring",
        "offline_honest": offline_honest,
        "live_env": live_env,
        "use_dispatch": use_dispatch,
        "injector_installed": injector_installed,
        "live_env_flag": ANTIEK_TWIN_SEED_LIVE_ENV,
        "use_dispatch_env_flag": ANTIEK_TWIN_SEED_USE_DISPATCH_ENV,
        "notes": notes,
        "html": (
            '<section data-view-format="html" data-product-panel="twin_seed_live_status">'
            f"<p>offline_honest={str(offline_honest).lower()} · "
            f"live_env={str(live_env).lower()} · "
            f"injector={str(injector_installed).lower()}</p>"
            "<ul>" + "".join(f"<li>{n}</li>" for n in notes) + "</ul></section>"
        ),
    }


@engagement_router.get("/twin-seed-live-status", dependencies=[Depends(_require_legacy_operator)])
def get_twin_seed_live_status() -> dict[str, Any]:
    """GET residual (hs): offline-vs-live twin seed readiness (HTML-first)."""
    return twin_seed_live_status_payload()


@engagement_router.post("/hydrate-ref", dependencies=[Depends(_require_legacy_operator)])
def post_hydrate_ref(body: HydrateRefBody) -> dict[str, Any]:
    """Land arxiv/substack/url as an HTML-first asset (offline-safe by default).

    Does not call live arxiv/substack network unless injectors are set:
    ``hydrate_fetch_publication``, ``hydrate_arxiv_fetch_by_id``,
    and/or ``hydrate_substack_fetch_post``. PDF is never required.
    """
    from substrate.engagement_spine import (
        arxiv_metadata_fetch_publication,
        compose_fetch_publication,
        substack_post_fetch_publication,
    )

    adapters: list[Any] = []
    if hydrate_fetch_publication is not None:
        adapters.append(hydrate_fetch_publication)
    if hydrate_arxiv_fetch_by_id is not None:
        adapters.append(arxiv_metadata_fetch_publication(fetch_by_id=hydrate_arxiv_fetch_by_id))
    if hydrate_substack_fetch_post is not None:
        adapters.append(substack_post_fetch_publication(fetch_post=hydrate_substack_fetch_post))
    fetcher = compose_fetch_publication(*adapters) if adapters else None
    try:
        asset = hydrate_reference(
            body.reference,
            store=_eng(),
            fetch_publication=fetcher,
            include_html=body.include_html,
            attach_spawn_id=body.attach_spawn_id,
            seed_twins=body.seed_twins,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return asset.to_dict()


@engagement_router.post("/progress", dependencies=[Depends(_require_legacy_operator)])
def post_progress(body: ProgressRecordBody) -> dict[str, Any]:
    """Append one plan/gather/synthesize/cite (or terminal) progress event."""
    try:
        ev = record_progress(
            body.spawn_id,
            body.stage,
            body.message,
            store=_eng(),
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    payload = progress_payload(body.spawn_id, store=_eng(), include_html=body.include_html)
    payload["recorded"] = ev.to_dict()
    return payload


@engagement_router.post("/progress/seed", dependencies=[Depends(_require_legacy_operator)])
def post_progress_seed(body: ProgressSeedBody) -> dict[str, Any]:
    """Seed default plan→gather→synthesize→cite skeleton for a spawn."""
    try:
        seed_default_pipeline(body.spawn_id, store=_eng())
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return progress_payload(body.spawn_id, store=_eng(), include_html=body.include_html)


@engagement_router.get("/progress/{spawn_id}", dependencies=[Depends(_require_legacy_operator)])
def get_progress(spawn_id: str, include_html: bool = False) -> dict[str, Any]:
    """Read progress events for a spawn (HTML-capable)."""
    if _eng().get_spawn(spawn_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown spawn_id: {spawn_id}")
    return progress_payload(spawn_id, store=_eng(), include_html=include_html)


@engagement_router.post("/evidence-pack", dependencies=[Depends(_require_legacy_operator)])
def post_evidence_pack(body: EvidencePackBody) -> dict[str, Any]:
    """HTML-first evidence pack from twin notes + spawn source refs."""
    try:
        return evidence_pack_payload(
            body.asset_id,
            store=_eng(),
            spawn_id=body.spawn_id,
            include_html=body.include_html,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@engagement_router.get("/twins/{asset_id}", dependencies=[Depends(_require_legacy_operator)])
def get_twins(
    asset_id: str,
    include_html: bool = False,
    spawn_id: str | None = None,
) -> dict[str, Any]:
    """List twin notes (insights/questions) for an information asset.

    Residual (le): optional ``spawn_id`` query surfaces reserved research_tier.
    """
    try:
        return twins_product_payload(
            asset_id,
            store=_eng(),
            include_html=include_html,
            spawn_id=spawn_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@engagement_router.post("/twins", dependencies=[Depends(_require_legacy_operator)])
def post_twins(body: TwinRecordBody) -> dict[str, Any]:
    """Record one twin insight or question (recursive note-taker product path)."""
    try:
        return record_twin_product(
            body.asset_id,
            store=_eng(),
            kind=body.kind,
            text=body.text,
            source_spawn_id=body.source_spawn_id,
            investigation_id=body.investigation_id,
            include_html=body.include_html,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class TwinSeedBody(BaseModel):
    """Offline (or env-gated live) twin seed for any asset (residual ch)."""

    asset_id: str = Field(min_length=1)
    title: str = ""
    body_text: str = ""
    source_spawn_id: str | None = None
    include_html: bool = True
    force_offline: bool = False
    # Residual (qy): twin_write seed provenance → Antiek-bench by_source.
    usage_source: str | None = None
    research_tier: str | None = None
    # Residual (acw): optional body honesty for recursive suite rewrite feed.
    # When omitted, inferred from non-empty body_text (title-only → false).
    has_body: bool | None = None


@engagement_router.post("/twins/seed", dependencies=[Depends(_require_legacy_operator)])
def post_twins_seed(body: TwinSeedBody) -> dict[str, Any]:
    """Seed insight + question twins for an asset (idempotent offline default)."""
    from substrate.engagement_spine import seed_twins_for_asset

    try:
        out = seed_twins_for_asset(
            body.asset_id,
            store=_eng(),
            title=body.title or body.asset_id,
            body_text=body.body_text,
            source_spawn_id=body.source_spawn_id,
            include_html=body.include_html,
            force_offline=body.force_offline,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Residual (qy/acw): DR session / terminal progress Write seeds → bench feed.
    if body.usage_source:
        try:
            from substrate.antiek_bench import (
                record_twin_write_seed_usage,
                resolve_usage_store,
            )

            # Residual (acw): explicit has_body or infer from body_text honesty.
            if body.has_body is not None:
                has_body = bool(body.has_body)
            else:
                has_body = bool(str(body.body_text or "").strip())
            usage_store = resolve_usage_store()
            if usage_store is None:
                raise RuntimeError("bench usage store unavailable")
            usage = record_twin_write_seed_usage(
                store=usage_store,
                seed_source=body.usage_source,
                prompt_hint=(body.title or body.asset_id or "")[:200],
                research_tier=body.research_tier,
                has_body=has_body,
            )
            if usage is not None:
                out["usage_event"] = usage
                out["usage_has_body"] = has_body
        except Exception as exc:  # noqa: BLE001 — offline-honest soft fail
            out["usage_event_error"] = str(exc)
    return out


@engagement_router.post("/twins/promote-context", dependencies=[Depends(_require_legacy_operator)])
def post_twins_promote_context(body: TwinPromoteContextBody) -> dict[str, Any]:
    """Promote asset twins into the depth graph and research context units.

    The substrate defaults are the canonical graph writers. Tests that need a
    pure projection exercise ``twin_promote_context_payload`` with explicit
    offline hooks; the product route must never report a simulated promotion.
    """
    try:
        return twin_promote_context_payload(
            body.asset_id,
            store=_eng(),
            query=body.query,
            investigation_id=body.investigation_id,
            promote_insight_fn=twin_promote_insight_fn,
            promote_question_fn=twin_promote_question_fn,
            include_html=body.include_html,
            kinds=body.kinds,
            note_ids=body.note_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@engagement_router.post("/context-search", dependencies=[Depends(_require_legacy_operator)])
def post_context_search(body: ContextSearchBody) -> dict[str, Any]:
    """Search twin substrate + source refs for research context assembly."""
    try:
        return search_engagement_context(
            store=_eng(),
            query=body.query,
            asset_id=body.asset_id,
            spawn_id=body.spawn_id,
            include_html=body.include_html,
            limit=body.limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _session_open_usage_source(goal_hint: str | None) -> str:
    """Residual (nw/asu): classify open source for Antiek-bench recursive rewrite.

    Twin chase launches stamp goal_hint with ``Twin chase on …`` (buildTwinChasePayload).
    Highlight-passage launches (ResearchThis / HostedHtml / Reading index) stamp
    goal_hint with ``highlighted passage`` → highlight_dr_launch (asq path).
    All other session opens use floating_deep_research.
    """
    g = (goal_hint or "").strip().lower()
    if g.startswith("twin chase"):
        return "twin_chase"
    # Residual (asu/asv): HTML reading/workstation highlight → float|full DR launch.
    # ResearchThis/HostedHtml: "highlighted passage"; HighlightToolbar: "highlighted synthesis".
    if "highlighted passage" in g or "highlighted synthesis" in g:
        return "highlight_dr_launch"
    return "floating_deep_research"


def _record_session_open_usage(
    *,
    research_tier: str | None,
    goal_hint: str | None,
    selection_text: str,
    model_id: str | None,
) -> dict[str, Any] | None:
    """Residual (nw): best-effort Antiek-bench usage on session open.

    Feeds recursive suite rewrite when operators launch floating DR or twin
    chase (highlight→float path). Never raises to callers. Uses shared
    get_bench_usage_store (parity flywheel / investigation_start).
    """
    from substrate.antiek_bench import (
        UsageEvent,
        record_usage_event,
        research_tier_to_task_class,
    )

    # Prefer explicit tier; session open defaults to deep when unset.
    task = research_tier_to_task_class(research_tier)
    if task is None:
        task = "synthesize"
    store = get_bench_usage_store(create_if_missing=True)
    if store is None:
        return None
    hint = ((goal_hint or "").strip() or (selection_text or "").strip())[:280]
    return record_usage_event(
        UsageEvent(
            task_class=task,
            outcome="worked",
            prompt_hint=hint,
            source=_session_open_usage_source(goal_hint),
            model_id=model_id,
        ),
        store=store,
    )


def _verified_session(session_id: str, owner_id: str):  # type: ignore[no-untyped-def]
    try:
        raw_session = _sess().get_session(session_id)
        if raw_session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if "owner_id" not in raw_session:
            raise HTTPException(
                status_code=409, detail="session ownership requires reconciliation"
            )
        if raw_session.get("owner_id") != owner_id:
            raise HTTPException(status_code=404, detail="session not found")
        session = get_session(session_id, session_store=_sess(), engagement_store=_eng())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid session identity") from exc
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    spawn = _eng().get_spawn(session.spawn_id)
    if spawn is None:
        raise HTTPException(status_code=409, detail="session provenance requires reconciliation")
    if (
        spawn.get("parent_asset_id") != session.parent_asset_id
        or spawn.get("investigation_id") != session.investigation_id
        or spawn.get("owner_id") != owner_id
    ):
        raise HTTPException(status_code=409, detail="session provenance requires reconciliation")
    return session


def _session_payload(session: Any, *, include_html: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "session_id": session.session_id,
        "parent_asset_id": session.parent_asset_id,
        "spawn_id": session.spawn_id,
        "investigation_id": session.investigation_id,
        "view_mode": session.view_mode,
        "selection_text": session.selection_text,
        "region_id": session.region_id,
        "model_id": session.model_id,
        "goal": session.goal,
        "status": session.status,
        "research_tier": session.research_tier,
        "view_format": "html",
        "owner_id": session.owner_id,
    }
    if include_html:
        rendered = project_session_html(
            session.session_id,
            session_store=_sess(),
            engagement_store=_eng(),
        )
        if len(rendered.encode("utf-8")) > 2_000_000:
            raise HTTPException(status_code=413, detail="session HTML exceeds response cap")
        out["html"] = rendered
    return out


def _parent_revision_sha256(parent_asset_id: str, owner_id: str) -> str:
    return document_revision_sha256(
        _eng().get_document(owned_document_id(owner_id, parent_asset_id))
    )


@engagement_router.post("/sessions/open")
def post_session_open(body: SessionOpenBody, request: Request) -> dict[str, Any]:
    owner_id = _request_owner(request)
    try:
        sel = HighlightSelection(
            asset_id=body.asset_id,
            selection_text=body.selection_text,
            region_id=body.region_id,
            page=body.page,
            goal_hint=body.goal_hint,
        )
        session = open_from_highlight_with_references(
            sel,
            engagement_store=_eng(),
            session_store=_sess(),
            references=body.references,
            model_id=body.model_id,
            view_mode=body.view_mode,
            force_new=body.force_new,
            research_tier=body.research_tier,
            owner_id=owner_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    resolved_tier = getattr(session, "research_tier", None) or "deep"
    out: dict[str, Any] = {
        "session_id": session.session_id,
        "spawn_id": session.spawn_id,
        "investigation_id": session.investigation_id,
        "parent_asset_id": session.parent_asset_id,
        "selection_text": session.selection_text,
        "status": session.status,
        "view_mode": session.view_mode,
        "model_id": session.model_id,
        "goal": session.goal,
        "research_tier": resolved_tier,
        "view_format": "html",
        "owner_id": session.owner_id,
    }
    # Residual (nw): Antiek-bench usage for floating DR + twin chase opens.
    try:
        usage = _record_session_open_usage(
            research_tier=resolved_tier,
            goal_hint=body.goal_hint,
            selection_text=body.selection_text or "",
            model_id=session.model_id,
        )
        if usage is not None:
            out["usage_event"] = usage
    except Exception as exc:  # pragma: no cover — never fail open on bench
        out["usage_event_error"] = str(exc)
    return out


@engagement_router.post("/sessions/complete-flywheel")
def post_session_complete_flywheel(body: SessionFlywheelBody, request: Request) -> dict[str, Any]:
    _verified_session(body.session_id, _request_owner(request))
    try:
        result = complete_session_with_context_flywheel(
            body.session_id,
            session_store=_sess(),
            engagement_store=_eng(),
            output_text=body.output_text,
            insights=body.insights,
            questions=body.questions,
            query=body.query,
            record_twins=body.record_twins,
            include_twin_promote=body.include_twin_promote,
            promote_insight_fn=_offline_promote_insight if body.include_twin_promote else None,
            promote_question_fn=_offline_promote_question if body.include_twin_promote else None,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    out = result.to_dict()
    # Feed Antiek-bench recursive rewrite with engagement outcomes (best-effort).
    try:
        from substrate.antiek_bench import record_session_flywheel_usage

        ctx = result.context
        # Residual (jt): session research_tier → Antiek-bench task_class
        # (wrestle sessions feed wrestle rewrite bucket, not distill heuristic).
        session_tier = getattr(result.session, "research_tier", None)
        usage = record_session_flywheel_usage(
            store=get_bench_usage_store(create_if_missing=True),
            twin_count=len(ctx.twin_units),
            ref_count=len(ctx.source_references),
            status=result.session.status,
            model_id=result.session.model_id,
            prompt_hint=body.output_text[:200],
            research_tier=session_tier,
        )
        out["usage_event"] = usage
        out["research_tier"] = session_tier or out.get("research_tier") or "deep"
    except Exception as exc:  # pragma: no cover — never fail flywheel on bench
        out["usage_event_error"] = str(exc)
    return out


@engagement_router.get("/sessions/asset/{parent_asset_id}")
def get_sessions_for_asset(
    parent_asset_id: str, request: Request, include_html: bool = False
) -> dict[str, Any]:
    owner_id = _request_owner(request)
    if not parent_asset_id.strip() or len(parent_asset_id) > 512 or ".." in parent_asset_id:
        raise HTTPException(status_code=400, detail="invalid parent asset identity")
    try:
        sessions = sorted(
            list_sessions_for_asset(parent_asset_id, session_store=_sess(), owner_id=owner_id),
            key=lambda row: row.session_id,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(
            status_code=409, detail="session index requires reconciliation"
        ) from exc
    verified = [_verified_session(row.session_id, owner_id) for row in sessions]
    return {
        "parent_asset_id": parent_asset_id,
        "sessions": [_session_payload(session, include_html=include_html) for session in verified],
        "count": len(verified),
        "view_format": "html",
    }


@engagement_router.get("/sessions/{session_id}")
def get_session_route(
    session_id: str, request: Request, include_html: bool = True
) -> dict[str, Any]:
    return _session_payload(
        _verified_session(session_id, _request_owner(request)),
        include_html=include_html,
    )


@engagement_router.put("/sessions/{session_id}/view")
def put_session_view(session_id: str, body: SessionViewBody, request: Request) -> dict[str, Any]:
    _verified_session(session_id, _request_owner(request))
    try:
        updated, applied = compare_and_set_view_mode(
            session_id,
            body.mode,
            expected_mode=body.expected_mode,
            session_store=_sess(),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="session view update failed") from exc
    if not applied:
        raise HTTPException(status_code=409, detail="session view changed concurrently")
    return _session_payload(updated, include_html=True)


@engagement_router.post("/sessions/context")
def post_session_context(body: SessionContextBody, request: Request) -> dict[str, Any]:
    _verified_session(body.session_id, _request_owner(request))
    try:
        pack = session_research_context(
            body.session_id,
            session_store=_sess(),
            engagement_store=_eng(),
            query=body.query,
            promote_insight_fn=(_offline_promote_insight if body.include_twin_preview else None),
            promote_question_fn=(_offline_promote_question if body.include_twin_preview else None),
            include_twin_promote=body.include_twin_preview,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="session context is invalid") from exc
    out = pack.to_dict()
    out["twin_context_mode"] = (
        "preview_non_mutating" if body.include_twin_preview else "not_requested"
    )
    if body.include_prompt_block:
        out["prompt_block"] = pack.prompt_block()
    if body.include_html:
        out["html"] = session_context_html(
            body.session_id,
            session_store=_sess(),
            engagement_store=_eng(),
            query=body.query,
            include_twin_promote=False,
        )
    return out


@engagement_router.post("/sessions/collective")
def post_sessions_collective(body: SessionsCollectiveBody, request: Request) -> dict[str, Any]:
    owner_id = _request_owner(request)
    sessions = [_verified_session(session_id, owner_id) for session_id in body.session_ids]
    assets = tuple(dict.fromkeys(session.parent_asset_id for session in sessions))
    if len(assets) > 1 and not body.allow_cross_asset:
        raise HTTPException(
            status_code=400,
            detail="cross-asset collective research requires explicit approval",
        )
    try:
        unit = sessions_collective_research(
            body.session_ids,
            session_store=_sess(),
            engagement_store=_eng(),
            query=body.query,
            promote_insight_fn=(_offline_promote_insight if body.include_twin_preview else None),
            promote_question_fn=(_offline_promote_question if body.include_twin_preview else None),
            include_twin_promote=body.include_twin_preview,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="collective session context is invalid"
        ) from exc
    out = unit.to_dict()
    out["source_session_ids"] = list(body.session_ids)
    out["twin_context_mode"] = (
        "preview_non_mutating" if body.include_twin_preview else "not_requested"
    )
    if body.include_prompt_block:
        out["prompt_block"] = unit.prompt_block()
    if body.include_html:
        out["html"] = sessions_collective_html(
            body.session_ids,
            session_store=_sess(),
            engagement_store=_eng(),
            query=body.query,
            include_twin_promote=False,
        )
    return out


@engagement_router.post("/sessions/merge")
def post_sessions_merge(body: SessionsMergeBody, request: Request) -> dict[str, Any]:
    owner_id = _request_owner(request)
    sessions = [_verified_session(session_id, owner_id) for session_id in body.session_ids]
    if any(session.parent_asset_id != body.parent_asset_id for session in sessions):
        raise HTTPException(status_code=400, detail="session merge cannot cross parent assets")
    if any(session.status != "complete" for session in sessions):
        raise HTTPException(status_code=400, detail="only completed sessions can merge")
    if body.mode == "into_parent" and (
        not body.confirm_parent_write
        or body.expected_parent_sha256 is None
        or body.idempotency_key is None
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "into-parent merge requires confirmation, parent revision, "
                "and idempotency key"
            ),
        )
    parent_before = _parent_revision_sha256(body.parent_asset_id, owner_id)
    receipt_id: str | None = None
    material_sha: str | None = None
    receipt_row: dict[str, Any] | None = None
    merged: dict[str, Any] = {}
    if body.mode == "into_parent":
        material = {
            "owner_id": owner_id,
            "parent_asset_id": body.parent_asset_id,
            "session_ids": list(body.session_ids),
            "mode": body.mode,
            "expected_parent_sha256": body.expected_parent_sha256,
        }
        material_sha = merge_material_sha256(material)
        receipt_id = merge_receipt_id(owner_id, body.idempotency_key or "")
        try:
            receipt_row, _created = _receipts().claim(
                {
                    "receipt_id": receipt_id,
                    "owner_id": owner_id,
                    "idempotency_key": body.idempotency_key,
                    "material_sha256": material_sha,
                    "expected_parent_sha256": body.expected_parent_sha256,
                    "state": "claimed",
                }
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="idempotency key conflicts") from exc

        if receipt_row.get("state") in ("prepared", "applied"):
            result_sha = str(receipt_row.get("result_sha256") or "")
            current_sha = _parent_revision_sha256(body.parent_asset_id, owner_id)
            if current_sha == result_sha:
                if receipt_row.get("state") == "prepared":
                    receipt_row = _receipts().settle(
                        receipt_id, material_sha, result_sha
                    )
                stored = receipt_row.get("result")
                if not isinstance(stored, dict):
                    raise HTTPException(
                        status_code=409, detail="merge receipt requires reconciliation"
                    )
                merged = dict(stored)
            elif current_sha != body.expected_parent_sha256:
                raise HTTPException(status_code=409, detail="parent changed after preview")
            else:
                merged = {}
        else:
            merged = {}

    def prepare_receipt(result: dict[str, Any]) -> None:
        if receipt_id is not None and material_sha is not None:
            _receipts().prepare(receipt_id, material_sha, result)

    try:
        if not merged:
            merged = merge_sessions(
                body.parent_asset_id,
                body.session_ids,
                session_store=_sess(),
                engagement_store=_eng(),
                mode=body.mode,
                expected_parent_sha256=(
                    body.expected_parent_sha256 if body.mode == "into_parent" else None
                ),
                owner_id=owner_id,
                before_write=prepare_receipt if body.mode == "into_parent" else None,
            )
    except (KeyError, ValueError) as exc:
        if (
            "revision conflicts" in str(exc)
            and receipt_id is not None
            and material_sha is not None
        ):
            replay, _ = _receipts().claim(receipt_row or {})
            result_sha = str(replay.get("result_sha256") or "")
            stored = replay.get("result")
            if (
                result_sha
                and _parent_revision_sha256(body.parent_asset_id, owner_id) == result_sha
                and isinstance(stored, dict)
            ):
                _receipts().settle(receipt_id, material_sha, result_sha)
                merged = dict(stored)
            else:
                raise HTTPException(status_code=409, detail="parent changed after preview") from exc
        else:
            raise HTTPException(status_code=400, detail="session merge is invalid") from exc
    if receipt_id is not None and material_sha is not None:
        _receipts().settle(receipt_id, material_sha, str(merged["document_sha256"]))
        merged["merge_receipt_id"] = receipt_id
        merged["merge_receipt_state"] = "applied"
    merged["view_format"] = "html"
    merged["draft_leaves_parent"] = body.mode == "draft_combined"
    merged["parent_revision_sha256"] = parent_before
    merged["result_parent_sha256"] = (
        merged["document_sha256"] if body.mode == "into_parent" else parent_before
    )
    if body.include_html:
        merged["html"] = project_session_html(
            body.session_ids[0],
            session_store=_sess(),
            engagement_store=_eng(),
            merge_result=merged,
        )
    return merged


# Offline content-addressed promote hooks so API tests never need DuckDB.
# Production can swap to real promote_* by mounting a different factory later.
def _offline_promote_insight(
    *,
    text: str,
    investigation_id: str,
    source_document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    embedding_provider: Any = None,
    con: Any = None,
    **kwargs: Any,
) -> str:

    canon = " ".join(text.lower().split())
    digest = hashlib.sha256(f"insight:{canon}".encode()).hexdigest()[:16]
    return f"insight_{digest}"


def _offline_promote_question(
    *,
    text: str,
    investigation_id: str,
    source_document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    embedding_provider: Any = None,
    con: Any = None,
    **kwargs: Any,
) -> str:

    canon = " ".join(text.lower().split())
    digest = hashlib.sha256(f"question:{canon}".encode()).hexdigest()[:16]
    return f"question_{digest}"


def register_engagement_routes(app: FastAPI) -> None:
    app.include_router(engagement_router)


__all__ = [
    "engagement_router",
    "register_engagement_routes",
    "reset_engagement_stores",
    "hydrate_live_status_payload",
    "twin_seed_live_status_payload",
]
