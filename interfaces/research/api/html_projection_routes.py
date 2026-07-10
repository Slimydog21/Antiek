"""Read-only HTTP transport for canonical, ready HTML projections."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import duckdb
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from services.html_projection.gate import ScriptViolation, assert_script_free
from substrate.contracts.html_projection import AnchorMapping, HtmlProjectionContract
from substrate.graph import default_db_path

MAX_HTML_BYTES = 25 * 1024 * 1024
MAX_ANCHOR_MAPPINGS = 100_000


class HtmlProjectionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    identity: dict[str, str]
    projection_id: str
    html_sha256: str
    html: str
    anchor_mappings: tuple[AnchorMapping, ...]


def make_html_projection_router(
    *,
    db_path: str | os.PathLike[str] | None = None,
    object_root: str | os.PathLike[str] | None = None,
) -> APIRouter:
    """Build the router; dependencies are injectable without global mutation."""
    database = Path(db_path) if db_path is not None else Path(default_db_path())
    configured_root = Path(object_root) if object_root is not None else None
    router = APIRouter(prefix="/html-projections", tags=["html-projections"])

    def load_rows(
        *, projection_id: str | None = None, document_id: str | None = None
    ) -> list[HtmlProjectionContract]:
        if not database.is_file():
            return []
        try:
            con = duckdb.connect(str(database), read_only=True)
            try:
                if projection_id is not None:
                    rows = con.execute(
                        "SELECT projection_json FROM html_projections WHERE projection_id = ?",
                        [projection_id],
                    ).fetchall()
                else:
                    rows = con.execute(
                        "SELECT projection_json FROM html_projections "
                        "WHERE json_extract_string(projection_json, '$.source_document_id') = ? "
                        "LIMIT 3",
                        [document_id],
                    ).fetchall()
            finally:
                con.close()
        except duckdb.Error:
            return []

        contracts: list[HtmlProjectionContract] = []
        for row in rows:
            try:
                contract = HtmlProjectionContract.model_validate_json(str(row[0]))
            except (TypeError, ValueError) as _exc:
                continue
            if contract.status != "ready":
                continue
            if document_id is None or contract.source_document_id == document_id:
                contracts.append(contract)
        return contracts

    def render(contract: HtmlProjectionContract) -> HtmlProjectionResponse:
        root = configured_root
        if root is None:
            env_root = os.environ.get("ANTIEK_HTML_OBJECT_ROOT", "").strip()
            root = Path(env_root) if env_root else None
        if root is None:
            raise HTTPException(status_code=503, detail="HTML projection storage unavailable")
        locator = contract.hosted_html_locator
        if locator is None or any(
            ord(character) < 32 or ord(character) == 127 for character in locator
        ):
            raise HTTPException(status_code=404, detail="HTML projection unavailable")
        if len(contract.anchor_mappings) > MAX_ANCHOR_MAPPINGS:
            raise HTTPException(status_code=404, detail="HTML projection unavailable")
        try:
            root = root.resolve(strict=True)
            if not root.is_dir() or root.is_symlink():
                raise OSError
            candidate = root / contract.hosted_html_locator  # contract validates relative key
            relative = candidate.relative_to(root)
            current = root
            for part in relative.parts:
                current = current / part
                info = current.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise OSError
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
            info = resolved.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_HTML_BYTES:
                raise OSError
            with resolved.open("rb") as handle:
                payload = handle.read(MAX_HTML_BYTES + 1)
            if len(payload) > MAX_HTML_BYTES:
                raise OSError
            if hashlib.sha256(payload).hexdigest() != contract.hosted_html_sha256:
                raise OSError
            html = payload.decode("utf-8", errors="strict")
            assert_script_free(html)
        except (OSError, UnicodeError, ValueError, ScriptViolation) as _exc:
            raise HTTPException(status_code=404, detail="HTML projection unavailable") from None
        return HtmlProjectionResponse(
            identity=contract.identity(),
            projection_id=contract.projection_id,
            html_sha256=contract.hosted_html_sha256,
            html=html,
            anchor_mappings=contract.anchor_mappings,
        )

    @router.get("/{projection_id}", response_model=HtmlProjectionResponse)
    def by_projection_id(projection_id: str) -> HtmlProjectionResponse:
        rows = load_rows(projection_id=projection_id)
        if not rows:
            raise HTTPException(status_code=404, detail="HTML projection not found")
        return render(rows[0])

    @router.get("/by-document/{document_id}", response_model=HtmlProjectionResponse)
    def by_document_id(document_id: str) -> HtmlProjectionResponse:
        rows = load_rows(document_id=document_id)
        if not rows:
            raise HTTPException(status_code=404, detail="HTML projection not found")
        if len(rows) != 1:
            raise HTTPException(status_code=409, detail="Multiple ready HTML projections")
        return render(rows[0])

    return router


__all__ = [
    "HtmlProjectionResponse",
    "MAX_ANCHOR_MAPPINGS",
    "MAX_HTML_BYTES",
    "make_html_projection_router",
]
