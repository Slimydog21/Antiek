"""Trimmed research↔reading engagement API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.engagement_spine import (
    HighlightSelection,
    InMemoryEngagementStore,
    merge_product_payload,
    record_twin_product,
    twins_product_payload,
)
from substrate.engagement_spine.store import EngagementStore, FileEngagementStore
from substrate.floating_session import open_from_highlight
from substrate.floating_session.store import FileSessionStore, InMemorySessionStore, SessionStore

engagement_router = APIRouter(prefix="/engagement", tags=["engagement"])
_engagement_store: EngagementStore | None = None
_session_store: SessionStore | None = None


def engagement_data_dir() -> Path | None:
    raw = (os.environ.get("ANTIEK_ENGAGEMENT_DIR") or "").strip()
    return Path(raw).expanduser() if raw else None


def reset_engagement_stores(*, root: Path | None = None) -> None:
    global _engagement_store, _session_store
    base = root if root is not None else engagement_data_dir()
    if base is None:
        _engagement_store = InMemoryEngagementStore()
        _session_store = InMemorySessionStore()
        return
    base.mkdir(parents=True, exist_ok=True)
    _engagement_store = FileEngagementStore(base / "engagement")
    _session_store = FileSessionStore(base / "sessions")


def _eng() -> EngagementStore:
    global _engagement_store
    if _engagement_store is None:
        reset_engagement_stores()
    if _engagement_store is None:
        raise RuntimeError("engagement store initialization failed")
    return _engagement_store


def _sess() -> SessionStore:
    global _session_store
    if _session_store is None:
        reset_engagement_stores()
    if _session_store is None:
        raise RuntimeError("session store initialization failed")
    return _session_store


class SessionOpenBody(BaseModel):
    asset_id: str = Field(min_length=1)
    selection_text: str = Field(min_length=1)
    region_id: str | None = None
    page: int | None = None
    goal_hint: str | None = None
    model_id: str | None = None
    force_new: bool = False
    view_mode: Literal["floating", "full"] = "floating"


class TwinRecordBody(BaseModel):
    asset_id: str = Field(min_length=1)
    kind: Literal["insight", "question"]
    text: str = Field(min_length=1)
    source_spawn_id: str | None = None
    investigation_id: str | None = None
    include_html: bool = True


class MergeBody(BaseModel):
    parent_asset_id: str = Field(min_length=1)
    spawn_ids: list[str] = Field(min_length=1)
    mode: Literal["into_parent", "draft_combined"] = "draft_combined"
    parent_title: str | None = None
    parent_body: str | None = None
    include_html: bool = True


@engagement_router.post("/sessions/open")
def post_session_open(body: SessionOpenBody) -> dict[str, Any]:
    try:
        session = open_from_highlight(
            HighlightSelection(
                asset_id=body.asset_id,
                selection_text=body.selection_text,
                region_id=body.region_id,
                page=body.page,
                goal_hint=body.goal_hint,
            ),
            engagement_store=_eng(),
            session_store=_sess(),
            model_id=body.model_id,
            view_mode=body.view_mode,
            force_new=body.force_new,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "session_id": session.session_id,
        "spawn_id": session.spawn_id,
        "investigation_id": session.investigation_id,
        "parent_asset_id": session.parent_asset_id,
        "selection_text": session.selection_text,
        "status": session.status,
        "view_mode": session.view_mode,
        "model_id": session.model_id,
        "region_id": session.region_id,
        "goal": session.goal,
        "view_format": "html",
    }


@engagement_router.get("/twins/{asset_id}")
def get_twins(asset_id: str, include_html: bool = True) -> dict[str, Any]:
    try:
        return twins_product_payload(asset_id, store=_eng(), include_html=include_html)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@engagement_router.post("/twins")
def post_twins(body: TwinRecordBody) -> dict[str, Any]:
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@engagement_router.post("/merge")
def post_merge(body: MergeBody) -> dict[str, Any]:
    try:
        return merge_product_payload(
            body.parent_asset_id,
            body.spawn_ids,
            store=_eng(),
            mode=body.mode,
            parent_title=body.parent_title,
            parent_body=body.parent_body,
            include_html=body.include_html,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def register_engagement_routes(app: FastAPI) -> None:
    app.include_router(engagement_router)


__all__ = ["engagement_router", "register_engagement_routes", "reset_engagement_stores"]
