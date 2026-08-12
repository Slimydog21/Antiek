"""Owner-scoped, replay-safe candidate search for connected research tools."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from acquisition.twitter.api_client import XApiError
from acquisition.youtube.data_api import YouTubeApiError, YouTubeQuotaExhausted
from runtime.connectors.quota_meter import QuotaExhausted
from runtime.connectors.registry import ToolConnectionUnavailable, resolve_tool_connection

router = APIRouter(prefix="/research/tools", tags=["research-tools"])
_PRIVATE = "private, no-store"
_OP_PATTERN = r"^[A-Za-z0-9_-]{16,128}$"


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(pattern=_OP_PATTERN)
    vendor: Literal["youtube", "x"]
    query: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=10, ge=1, le=25)

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be blank")
        return normalized


class SearchCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(max_length=256)
    title_or_text: str = Field(max_length=4_000)
    url: str = Field(max_length=2_048)
    published_at: str | None = Field(default=None, max_length=64)
    author: str | None = Field(default=None, max_length=512)


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str
    vendor: Literal["youtube", "x"]
    status: Literal["completed", "replayed"]
    candidates: list[SearchCandidate]


class _PublicError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def _owner(request: Request) -> str:
    owner = getattr(request.state, "user_id", None)
    method = getattr(request.state, "auth_method", None)
    if not isinstance(owner, str) or not owner.strip() or len(owner) > 256:
        raise _PublicError(401, "authenticated user identity required")
    if method != "antiek_session_cookie" or owner == "__operator__":
        raise _PublicError(401, "authenticated user identity required")
    return owner.strip()


def _journal_path() -> Path:
    configured = os.environ.get("ANTIEK_TOOL_SEARCH_JOURNAL")
    if configured:
        return Path(configured)
    root = Path(os.environ.get("ANTIEK_HOME", os.path.expanduser("~/.antiek")))
    return root / "settings" / "research_tool_search.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _journal_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = path.parent.stat(follow_symlinks=False)
    if not stat.S_ISDIR(parent.st_mode) or stat.S_IMODE(parent.st_mode) != 0o700:
        raise RuntimeError("tool search journal unavailable")
    if path.exists() and path.is_symlink():
        raise RuntimeError("tool search journal unavailable")
    con = sqlite3.connect(path, timeout=10, isolation_level=None)
    os.chmod(path, 0o600)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    con.execute("CREATE TABLE IF NOT EXISTS searches ("
                "owner TEXT NOT NULL, operation_id TEXT NOT NULL, digest TEXT NOT NULL, "
                "vendor TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('claimed','sent','completed','unknown')), "
                "response_json TEXT, updated_at_ms INTEGER NOT NULL, "
                "PRIMARY KEY(owner, operation_id))")
    return con


def _digest(body: SearchRequest) -> str:
    canonical = json.dumps(body.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _claim(owner: str, body: SearchRequest) -> SearchResponse | None:
    digest = _digest(body)
    should_wait = False
    with _connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT digest,state,response_json FROM searches WHERE owner=? AND operation_id=?",
            (owner, body.operation_id),
        ).fetchone()
        if row:
            if row[0] != digest:
                raise _PublicError(409, "operation conflicts with an earlier request")
            if row[1] == "completed" and isinstance(row[2], str):
                saved = SearchResponse.model_validate_json(row[2])
                return saved.model_copy(update={"status": "replayed"})
            if row[1] == "unknown":
                raise _PublicError(409, "operation outcome is unresolved")
            should_wait = True
        else:
            con.execute(
                "INSERT INTO searches VALUES (?,?,?,?,?,?,?)",
                (owner, body.operation_id, digest, body.vendor, "claimed", None, int(time.time() * 1000)),
            )
    if should_wait:
        return _wait_for_result(owner, body.operation_id, digest)
    return None


def _wait_for_result(owner: str, operation_id: str, digest: str) -> SearchResponse:
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        time.sleep(0.02)
        with _connect() as con:
            row = con.execute(
                "SELECT digest,state,response_json FROM searches WHERE owner=? AND operation_id=?",
                (owner, operation_id),
            ).fetchone()
        if row is None or row[0] != digest:
            break
        if row[1] == "completed" and isinstance(row[2], str):
            saved = SearchResponse.model_validate_json(row[2])
            return saved.model_copy(update={"status": "replayed"})
        if row[1] == "unknown":
            break
    raise _PublicError(409, "operation outcome is unresolved")


def _complete(owner: str, result: SearchResponse) -> None:
    encoded = result.model_dump_json()
    with _connect() as con:
        changed = con.execute(
            "UPDATE searches SET state='completed',response_json=?,updated_at_ms=? "
            "WHERE owner=? AND operation_id=? AND state='sent'",
            (encoded, int(time.time() * 1000), owner, result.operation_id),
        ).rowcount
        if changed != 1:
            raise RuntimeError("tool search journal unavailable")


def _unknown(owner: str, operation_id: str) -> None:
    with _connect() as con:
        con.execute(
            "UPDATE searches SET state='unknown',updated_at_ms=? "
            "WHERE owner=? AND operation_id=? AND state='sent'",
            (int(time.time() * 1000), owner, operation_id),
        )


def _release(owner: str, operation_id: str) -> None:
    with _connect() as con:
        con.execute(
            "DELETE FROM searches WHERE owner=? AND operation_id=? AND state='claimed'",
            (owner, operation_id),
        )


def _mark_sent(owner: str, operation_id: str) -> None:
    with _connect() as con:
        changed = con.execute(
            "UPDATE searches SET state='sent',updated_at_ms=? "
            "WHERE owner=? AND operation_id=? AND state='claimed'",
            (int(time.time() * 1000), owner, operation_id),
        ).rowcount
        if changed != 1:
            raise RuntimeError("tool search journal unavailable")


def _youtube(rows: object) -> list[SearchCandidate]:
    out: list[SearchCandidate] = []
    for row in rows if isinstance(rows, list) else []:
        external_id = str(getattr(row, "video_id", ""))[:256]
        kind = str(getattr(row, "kind", "video"))
        if not external_id:
            continue
        if kind == "channel":
            url = f"https://www.youtube.com/channel/{external_id}"
        elif kind == "playlist":
            url = f"https://www.youtube.com/playlist?list={external_id}"
        else:
            url = f"https://www.youtube.com/watch?v={external_id}"
        out.append(SearchCandidate(
            external_id=external_id,
            title_or_text=str(getattr(row, "title", ""))[:4_000],
            url=url,
            published_at=(str(getattr(row, "published_at", ""))[:64] or None) if getattr(row, "published_at", None) else None,
            author=str(getattr(row, "channel_title", ""))[:512] or None,
        ))
    return out


def _x(rows: object) -> list[SearchCandidate]:
    out: list[SearchCandidate] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        external_id = str(row.get("tweet_id", ""))[:256]
        if not external_id:
            continue
        author = str(row.get("author_handle", ""))[:512]
        out.append(SearchCandidate(
            external_id=external_id,
            title_or_text=str(row.get("text", ""))[:4_000],
            url=f"https://x.com/{author or 'i'}/status/{external_id}",
            published_at=(str(row.get("created_at"))[:64] if row.get("created_at") else None),
            author=author or None,
        ))
    return out


@router.post("/search", response_model=SearchResponse)
async def search_tools(request: Request, response: Response) -> SearchResponse:
    owner = _owner(request)
    response.headers["Cache-Control"] = _PRIVATE
    try:
        declared = request.headers.get("content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > 4_096):
            raise ValueError
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 4_096:
                raise ValueError
            raw.extend(chunk)
        parsed = json.loads(raw)
        body = SearchRequest.model_validate(parsed)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, TypeError):
        raise _PublicError(422, "tool search request is invalid") from None
    try:
        replay = _claim(owner, body)
        if replay is not None:
            return replay
        connector = resolve_tool_connection(owner, body.vendor)
        _mark_sent(owner, body.operation_id)
        if body.vendor == "youtube":
            candidates = _youtube(connector.search(body.query, max_results=body.max_results))
        else:
            candidates = _x(connector.recent_search(body.query, max_results=body.max_results))
        result = SearchResponse(
            operation_id=body.operation_id,
            vendor=body.vendor,
            status="completed",
            candidates=candidates[: body.max_results],
        )
        _complete(owner, result)
        return result
    except _PublicError:
        raise
    except (QuotaExhausted, YouTubeQuotaExhausted):
        _unknown(owner, body.operation_id)
        raise _PublicError(429, "tool quota is exhausted") from None
    except ToolConnectionUnavailable:
        _release(owner, body.operation_id)
        raise _PublicError(503, "tool search is unavailable") from None
    except (YouTubeApiError, XApiError, OSError, RuntimeError):
        _unknown(owner, body.operation_id)
        raise _PublicError(503, "tool search is unavailable") from None
    finally:
        close = locals().get("connector")
        if close is not None and hasattr(close, "close"):
            close.close()


def register_research_tool_search_routes(app: FastAPI) -> None:
    @app.exception_handler(_PublicError)
    async def _private_error(_request: Request, exc: _PublicError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"detail": exc.detail},
            headers={"Cache-Control": _PRIVATE},
        )

    app.include_router(router)


__all__ = ["register_research_tool_search_routes"]
