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
  POST /engagement/sessions/open
  POST /engagement/sessions/complete-flywheel
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.engagement_spine import (
    HighlightSelection,
    InMemoryEngagementStore,
    attach_source_references,
    assemble_research_context,
    hydrate_reference,
    merge_product_payload,
    merge_spawns_collective,
    spawn_from_highlight_with_references,
)
from substrate.engagement_spine.store import EngagementStore, FileEngagementStore
from substrate.floating_session import (
    complete_session_with_context_flywheel,
    open_from_highlight_with_references,
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
    global _engagement_store, _session_store
    base = root if root is not None else engagement_data_dir()
    if base is not None:
        base = Path(base)
        base.mkdir(parents=True, exist_ok=True)
        _engagement_store = FileEngagementStore(base / "engagement")
        _session_store = FileSessionStore(base / "sessions")
    else:
        _engagement_store = InMemoryEngagementStore()
        _session_store = InMemorySessionStore()


def _eng() -> EngagementStore:
    global _engagement_store
    if _engagement_store is None:
        reset_engagement_stores()
    assert _engagement_store is not None
    return _engagement_store


def _sess() -> SessionStore:
    global _session_store
    if _session_store is None:
        reset_engagement_stores()
    assert _session_store is not None
    return _session_store


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


# ── routes ───────────────────────────────────────────────────────────────


@engagement_router.post("/spawn-from-highlight")
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
        "view_format": "html",
    }


@engagement_router.post("/attach-refs")
def post_attach_refs(body: AttachRefsBody) -> dict[str, Any]:
    try:
        spawn, merged = attach_source_references(
            body.spawn_id, body.references, store=_eng()
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "spawn_id": spawn.spawn_id,
        "source_references": [r.to_dict() for r in merged],
        "view_format": "html",
    }


@engagement_router.post("/research-context")
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


@engagement_router.post("/collective")
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
    return out


@engagement_router.post("/merge")
def post_merge(body: MergeBody) -> dict[str, Any]:
    """Merge completed spawn outputs into parent or a draft-combined document.

    Default mode is ``draft_combined`` so operators can review before full
    parent merge. Calls shipped ``merge_product_payload`` / ``merge_spawn_outputs``.
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
    return payload


# Optional injectable publication body fetcher for hydrate-ref (tests / wired apps).
# Signature: (SourceReference) -> dict with title/body_text/abstract/canonical_url.
hydrate_fetch_publication: Any = None


@engagement_router.post("/hydrate-ref")
def post_hydrate_ref(body: HydrateRefBody) -> dict[str, Any]:
    """Land arxiv/substack/url as an HTML-first asset (offline-safe by default).

    Does not call live arxiv/substack network unless ``hydrate_fetch_publication``
    is set (tests / app wiring). PDF is never required.
    """
    try:
        asset = hydrate_reference(
            body.reference,
            store=_eng(),
            fetch_publication=hydrate_fetch_publication,
            include_html=body.include_html,
            attach_spawn_id=body.attach_spawn_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return asset.to_dict()


@engagement_router.post("/sessions/open")
def post_session_open(body: SessionOpenBody) -> dict[str, Any]:
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
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "session_id": session.session_id,
        "spawn_id": session.spawn_id,
        "investigation_id": session.investigation_id,
        "parent_asset_id": session.parent_asset_id,
        "selection_text": session.selection_text,
        "status": session.status,
        "view_mode": session.view_mode,
        "model_id": session.model_id,
        "goal": session.goal,
        "view_format": "html",
    }


@engagement_router.post("/sessions/complete-flywheel")
def post_session_complete_flywheel(body: SessionFlywheelBody) -> dict[str, Any]:
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
        usage = record_session_flywheel_usage(
            store=get_bench_usage_store(create_if_missing=True),
            twin_count=len(ctx.twin_units),
            ref_count=len(ctx.source_references),
            status=result.session.status,
            model_id=result.session.model_id,
            prompt_hint=body.output_text[:200],
        )
        out["usage_event"] = usage
    except Exception as exc:  # pragma: no cover — never fail flywheel on bench
        out["usage_event_error"] = str(exc)
    return out


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
    import hashlib

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
    import hashlib

    canon = " ".join(text.lower().split())
    digest = hashlib.sha256(f"question:{canon}".encode()).hexdigest()[:16]
    return f"question_{digest}"


def register_engagement_routes(app: FastAPI) -> None:
    app.include_router(engagement_router)


__all__ = [
    "engagement_router",
    "register_engagement_routes",
    "reset_engagement_stores",
]
