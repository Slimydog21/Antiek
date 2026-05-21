"""Per-theme notebook HTTP API (SPR-11 / M1-M5).

FastAPI route handlers for:

  GET    /api/themes                              — list themes for user
  POST   /api/themes                              — create a new theme
  GET    /api/themes/by-slug/{slug}               — load a theme by slug
  GET    /api/themes/{theme_id}                   — load a theme by id
  POST   /api/themes/{theme_id}/blocks/promote    — promote Tier-2 blocks
  PATCH  /api/themes/{theme_id}/blocks/reorder    — reorder
  DELETE /api/themes/blocks/{theme_block_id}      — remove association
  POST   /api/themes/blocks/{theme_block_id}/dismiss-stale
                                                  — dismiss stale placeholder
  GET    /api/themes/{theme_id}/export?format=... — export (.antiek / md / pdf)

The substrate side is ``services.notebooks.theme_persistence``.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from services.notebooks.theme_persistence import (  # noqa: E402
    ThemeBlockRecord,
    ThemeRecord,
    get_default_theme_persistence,
    save_theme_as_antiek,
)


# ─────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────


class ThemeBlockOut(BaseModel):
    theme_block_id: str
    theme_id: str
    block_type: str
    content_json: dict[str, Any]
    sort_order: float
    source_block_id: Optional[str] = None
    source_notebook_id: Optional[str] = None
    source_document_id: Optional[str] = None
    dismissed_at: Optional[str] = None
    created_at: Optional[str] = None
    is_stale: bool = False
    source_document_title: Optional[str] = None
    source_notebook_title: Optional[str] = None


class ThemeOut(BaseModel):
    theme_id: str
    user_id: str
    slug: str
    title: str
    cover_snippet: Optional[str] = None
    created_at: Optional[str] = None
    last_edited_at: Optional[str] = None
    blocks: list[ThemeBlockOut] = Field(default_factory=list)


class CreateThemeRequest(BaseModel):
    user_id: str = Field(default="__operator__")
    title: str = Field(min_length=1)
    cover_snippet: Optional[str] = None


class PromoteBlocksRequest(BaseModel):
    source_block_ids: list[str] = Field(min_length=1)


class ReorderRequest(BaseModel):
    ordered_theme_block_ids: list[str] = Field(min_length=1)


# ─────────────────────────────────────────────────────────────────────
# Serialisers
# ─────────────────────────────────────────────────────────────────────


def _iso(ts: Optional[datetime]) -> Optional[str]:
    return ts.isoformat() if ts else None


def _block_to_out(b: ThemeBlockRecord) -> ThemeBlockOut:
    return ThemeBlockOut(
        theme_block_id=b.theme_block_id,
        theme_id=b.theme_id,
        block_type=b.block_type,
        content_json=dict(b.content_json),
        sort_order=b.sort_order,
        source_block_id=b.source_block_id,
        source_notebook_id=b.source_notebook_id,
        source_document_id=b.source_document_id,
        dismissed_at=_iso(b.dismissed_at),
        created_at=_iso(b.created_at),
        is_stale=b.is_stale,
        source_document_title=b.source_document_title,
        source_notebook_title=b.source_notebook_title,
    )


def _theme_to_out(t: ThemeRecord) -> ThemeOut:
    return ThemeOut(
        theme_id=t.theme_id,
        user_id=t.user_id,
        slug=t.slug,
        title=t.title,
        cover_snippet=t.cover_snippet,
        created_at=_iso(t.created_at),
        last_edited_at=_iso(t.last_edited_at),
        blocks=[_block_to_out(b) for b in t.blocks],
    )


# ─────────────────────────────────────────────────────────────────────
# Route registration
# ─────────────────────────────────────────────────────────────────────


def register_theme_routes(
    app: FastAPI,
    *,
    db_path: Optional[str] = None,
) -> None:
    """Mount per-theme routes on ``app``."""

    _ = db_path  # Factory reads ANTIEK_DUCKDB_PATH from env.

    @app.get(
        "/api/themes",
        response_model=list[ThemeOut],
        tags=["themes"],
    )
    async def list_themes(
        user_id: str = Query(default="__operator__"),
        sort: str = Query(default="last_edited_desc"),
    ) -> list[ThemeOut]:
        persistence = get_default_theme_persistence()
        themes = persistence.list_themes(user_id=user_id, sort=sort)
        return [_theme_to_out(t) for t in themes]

    @app.post(
        "/api/themes",
        response_model=ThemeOut,
        status_code=status.HTTP_201_CREATED,
        tags=["themes"],
    )
    async def create_theme(body: CreateThemeRequest) -> ThemeOut:
        persistence = get_default_theme_persistence()
        record = persistence.get_or_create_theme(
            user_id=body.user_id, title=body.title,
        )
        return _theme_to_out(record)

    @app.get(
        "/api/themes/by-slug/{slug}",
        response_model=ThemeOut,
        tags=["themes"],
    )
    async def get_theme_by_slug(
        slug: str,
        user_id: str = Query(default="__operator__"),
    ) -> ThemeOut:
        persistence = get_default_theme_persistence()
        record = persistence.load_theme(user_id=user_id, slug=slug)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "theme_not_found", "message": slug}},
            )
        return _theme_to_out(record)

    @app.get(
        "/api/themes/{theme_id}",
        response_model=ThemeOut,
        tags=["themes"],
    )
    async def get_theme(theme_id: str) -> ThemeOut:
        persistence = get_default_theme_persistence()
        record = persistence.load_theme_by_id(theme_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "theme_not_found", "message": theme_id}},
            )
        return _theme_to_out(record)

    @app.post(
        "/api/themes/{theme_id}/blocks/promote",
        response_model=list[ThemeBlockOut],
        tags=["themes"],
    )
    async def promote_blocks(
        theme_id: str, body: PromoteBlocksRequest,
    ) -> list[ThemeBlockOut]:
        persistence = get_default_theme_persistence()
        try:
            blocks = persistence.promote_blocks(
                theme_id=theme_id,
                source_block_ids=body.source_block_ids,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "source_block_not_found", "message": str(exc)}},
            ) from exc
        return [_block_to_out(b) for b in blocks]

    @app.patch(
        "/api/themes/{theme_id}/blocks/reorder",
        response_model=list[ThemeBlockOut],
        tags=["themes"],
    )
    async def reorder(
        theme_id: str, body: ReorderRequest,
    ) -> list[ThemeBlockOut]:
        persistence = get_default_theme_persistence()
        blocks = persistence.reorder_blocks(
            theme_id=theme_id,
            ordered_theme_block_ids=body.ordered_theme_block_ids,
        )
        return [_block_to_out(b) for b in blocks]

    @app.delete(
        "/api/themes/blocks/{theme_block_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["themes"],
    )
    async def remove_block(theme_block_id: str) -> Response:
        persistence = get_default_theme_persistence()
        persistence.remove_block(theme_block_id=theme_block_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/themes/blocks/{theme_block_id}/dismiss-stale",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["themes"],
    )
    async def dismiss_stale(theme_block_id: str) -> Response:
        persistence = get_default_theme_persistence()
        persistence.dismiss_stale(theme_block_id=theme_block_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get(
        "/api/themes/{theme_id}/export",
        tags=["themes"],
    )
    async def export_theme(
        theme_id: str,
        format: str = Query(default="antiek"),
    ) -> Response:
        if format not in ("antiek", "markdown", "pdf"):
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "bad_format", "message": format}},
            )
        persistence = get_default_theme_persistence()
        record = persistence.load_theme_by_id(theme_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "theme_not_found", "message": theme_id}},
            )

        if format == "antiek":
            # Write through SPR-11's documented shim. The function
            # writes the file at out_path; we slurp + return.
            import tempfile, os as _os
            tmp = tempfile.NamedTemporaryFile(suffix=".antiek", delete=False)
            tmp.close()
            try:
                save_theme_as_antiek(theme=record, out_path=tmp.name)
                with open(tmp.name, "rb") as f:
                    data = f.read()
            finally:
                try:
                    _os.unlink(tmp.name)
                except OSError:
                    pass
            return Response(
                content=data,
                media_type="application/x-antiek",
                headers={
                    "Content-Disposition": f'attachment; filename="{record.slug}.antiek"',
                },
            )

        if format == "markdown":
            # Plain-text dump of ordered blocks. The full markdown
            # projector for theme_notebook content_class isn't wired
            # yet; render a simple heading + blockquote per block.
            lines = [f"# {record.title}\n"]
            for block in record.blocks:
                if block.is_stale:
                    lines.append(
                        f"> _(stale: source block was removed)_  \n"
                    )
                content = block.content_json
                text = (
                    content.get("text") if isinstance(content, dict) else None
                )
                if text:
                    lines.append(f"> {text}\n\n")
                else:
                    lines.append(
                        f"> _(block {block.theme_block_id} — type "
                        f"{block.block_type})_\n\n"
                    )
            return Response(
                content="\n".join(lines).encode("utf-8"),
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f'attachment; filename="{record.slug}.md"',
                },
            )

        # PDF — operator-decision deferral. The substrate has the
        # Sprint-15 PDF export pipeline somewhere but wiring per-theme
        # to it requires picking a renderer. Surface 501 explicitly.
        raise HTTPException(
            status_code=501,
            detail={
                "error": {
                    "code": "pdf_export_not_implemented",
                    "message": (
                        "PDF export for theme notebooks is not yet wired. "
                        "Operator can save as .antiek and convert "
                        "downstream until the wire lands."
                    ),
                },
            },
        )
