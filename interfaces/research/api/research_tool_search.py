"""Owner-scoped, replay-safe search and ingest for connected research tools.

``POST /research/tools/search`` returns candidates found with the caller's own
connected YouTube or X credential. ``POST /research/tools/ingest`` takes one of
those candidates into the graph: it fetches that single item with the same
owner's key and hands it to the existing acquisition adapter with
``content_class=PERSONAL_READING_CONTENT_CLASS``, so the rights class is
attached at the moment of the BYOT fetch. Neither route opens DuckDB; the
adapter is the only graph path. Both are idempotent on ``operation_id``
through one sqlite replay journal, a store separate from the graph.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import stat
import time
from pathlib import Path
from typing import Literal, Protocol

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from acquisition.twitter.adapter import (
    DEFAULT_TWITTER_SOURCE_TIER,
    IngestTwitterResult,
    ingest_twitter_thread,
)
from acquisition.twitter.api_client import XApiError, to_thread
from acquisition.youtube.adapter import (
    DEFAULT_YOUTUBE_SOURCE_TIER,
    IngestYouTubeResult,
    ingest_youtube,
)
from acquisition.youtube.client import YouTubeRateCapExceeded, fetch_with_data_api
from acquisition.youtube.data_api import YouTubeApiError
from acquisition.youtube.data_api import YouTubeQuotaExhausted as AcquisitionQuotaExhausted
from interfaces.research.api.account_memory_identity import (
    FORBIDDEN_OWNERS,
    OPERATOR_STORAGE_SENTINEL,
    derive_owner_from_verified_email,
)
from runtime.connectors.quota_meter import QuotaExhausted
from runtime.connectors.rate_governor import VendorBanned
from runtime.connectors.registry import ToolConnectionUnavailable, resolve_tool_connection
from runtime.connectors.youtube import YouTubeQuotaExhausted as VendorQuotaExhausted
from substrate.constants import PERSONAL_READING_CONTENT_CLASS

router = APIRouter(prefix="/research/tools", tags=["research-tools"])
_PRIVATE = "private, no-store"
_OP_PATTERN = r"^[A-Za-z0-9_-]{16,128}$"
_BODY_LIMIT = 4_096
# The id shapes each vendor's single-item fetch accepts. Checked in the route
# so a malformed id is a 422 that never reaches the resolver or the vendor.
_EXTERNAL_ID = {
    "youtube": re.compile(r"^[A-Za-z0-9_-]{11}$"),
    "x": re.compile(r"^[0-9]{1,19}$"),
}


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


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(pattern=_OP_PATTERN)
    vendor: Literal["youtube", "x"]
    external_id: str = Field(min_length=1, max_length=64)
    investigation_id: str = Field(default="__operator__", min_length=1, max_length=256)


class IngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str
    vendor: Literal["youtube", "x"]
    external_id: str
    status: Literal["completed", "replayed"]
    ingest_status: Literal["ingested", "skipped"]
    document_id: str
    chunks_written: int
    skipped_reason: str | None
    title: str | None
    content_class: str
    source_tier: int


_Table = Literal["searches", "ingests"]
_TABLES: tuple[_Table, ...] = ("searches", "ingests")


class _PublicError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def _owner(request: Request) -> str:
    """Resolve the person whose connected-tool credential this search may spend.

    This refused ``__operator__`` unconditionally, which is the user_id every production
    login mints — so every connected-tool search answered 401 and no stored credential
    could ever be used. Storing one worked (``settings_tool_connections._owner`` refuses
    the sentinel only for the machine auth methods), which is why the chassis looked
    wired end to end while nothing downstream of it was reachable: the X and YouTube
    defects behind this gate had never been reached to be noticed.

    Resolve through the same shared derivation as account memory and BYOT dispatch, so
    one person is one owner across their memory, their spend and their tools. A
    session-cookie request has already had its address verified and allowlist-checked by
    the auth middleware; ``derive_owner_from_verified_email`` returns None when there is
    no address, so this still fails closed rather than inventing an owner.
    """
    owner = getattr(request.state, "user_id", None)
    method = getattr(request.state, "auth_method", None)
    if not isinstance(owner, str) or not owner.strip() or len(owner) > 256:
        raise _PublicError(401, "authenticated user identity required")
    if method != "antiek_session_cookie":
        raise _PublicError(401, "authenticated user identity required")

    normalized = owner.strip()
    if normalized.casefold() not in FORBIDDEN_OWNERS:
        return normalized
    if normalized.casefold() != OPERATOR_STORAGE_SENTINEL:
        raise _PublicError(401, "authenticated user identity required")

    derived = derive_owner_from_verified_email(
        getattr(request.state, "user_email", None)
    )
    if derived is None:
        raise _PublicError(401, "authenticated user identity required")
    return derived


class ClosableToolConnector(Protocol):
    def close(self) -> None: ...


def connected_tool_for_request(
    request: Request, vendor: Literal["youtube", "x"]
) -> ClosableToolConnector | None:
    """The caller's own connected ``vendor`` connector, or None.

    Uses the one owner derivation the tool lane spends under (``_owner``), so
    a surface outside this router cannot key a credential differently from
    search and ingest. None when there is no signed-in person (machine auth,
    local unauthenticated dev) or no connection for that vendor; the caller
    then keeps its uncredentialed path. The caller must close the connector.
    """
    try:
        connector: ClosableToolConnector = resolve_tool_connection(_owner(request), vendor)
    except (_PublicError, ToolConnectionUnavailable):
        return None
    return connector


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
    # One layout per table: searches journal candidate lookups, ingests
    # journal single-item fetch-and-ingest. The names come from _TABLES, never
    # from a request.
    for table in _TABLES:
        con.execute(f"CREATE TABLE IF NOT EXISTS {table} ("
                    "owner TEXT NOT NULL, operation_id TEXT NOT NULL, digest TEXT NOT NULL, "
                    "vendor TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('claimed','sent','completed','unknown')), "
                    "response_json TEXT, updated_at_ms INTEGER NOT NULL, "
                    "PRIMARY KEY(owner, operation_id))")
    return con


def _table(table: _Table) -> _Table:
    if table not in _TABLES:
        raise RuntimeError("tool search journal unavailable")
    return table


def _digest(body: SearchRequest | IngestRequest) -> str:
    canonical = json.dumps(body.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _claim[ResponseT: (SearchResponse, IngestResponse)](
    owner: str,
    body: SearchRequest | IngestRequest,
    *,
    table: _Table,
    model: type[ResponseT],
) -> ResponseT | None:
    name = _table(table)
    digest = _digest(body)
    should_wait = False
    with _connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            f"SELECT digest,state,response_json FROM {name} WHERE owner=? AND operation_id=?",
            (owner, body.operation_id),
        ).fetchone()
        if row:
            if row[0] != digest:
                raise _PublicError(409, "operation conflicts with an earlier request")
            if row[1] == "completed" and isinstance(row[2], str):
                saved = model.model_validate_json(row[2])
                return saved.model_copy(update={"status": "replayed"})
            if row[1] == "unknown":
                raise _PublicError(409, "operation outcome is unresolved")
            should_wait = True
        else:
            con.execute(
                f"INSERT INTO {name} VALUES (?,?,?,?,?,?,?)",
                (owner, body.operation_id, digest, body.vendor, "claimed", None, int(time.time() * 1000)),
            )
    if should_wait:
        return _wait_for_result(owner, body.operation_id, digest, table=name, model=model)
    return None


def _wait_for_result[ResponseT: (SearchResponse, IngestResponse)](
    owner: str,
    operation_id: str,
    digest: str,
    *,
    table: _Table,
    model: type[ResponseT],
) -> ResponseT:
    name = _table(table)
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        time.sleep(0.02)
        with _connect() as con:
            row = con.execute(
                f"SELECT digest,state,response_json FROM {name} WHERE owner=? AND operation_id=?",
                (owner, operation_id),
            ).fetchone()
        if row is None or row[0] != digest:
            break
        if row[1] == "completed" and isinstance(row[2], str):
            saved = model.model_validate_json(row[2])
            return saved.model_copy(update={"status": "replayed"})
        if row[1] == "unknown":
            break
    raise _PublicError(409, "operation outcome is unresolved")


def _complete(owner: str, result: SearchResponse | IngestResponse, *, table: _Table) -> None:
    name = _table(table)
    encoded = result.model_dump_json()
    with _connect() as con:
        changed = con.execute(
            f"UPDATE {name} SET state='completed',response_json=?,updated_at_ms=? "
            "WHERE owner=? AND operation_id=? AND state='sent'",
            (encoded, int(time.time() * 1000), owner, result.operation_id),
        ).rowcount
        if changed != 1:
            raise RuntimeError("tool search journal unavailable")


def _unknown(owner: str, operation_id: str, *, table: _Table = "searches") -> None:
    name = _table(table)
    with _connect() as con:
        con.execute(
            f"UPDATE {name} SET state='unknown',updated_at_ms=? "
            "WHERE owner=? AND operation_id=? AND state='sent'",
            (int(time.time() * 1000), owner, operation_id),
        )


def _release(owner: str, operation_id: str, *, table: _Table = "searches") -> None:
    """Return an operation_id to unclaimed after a refusal that produced nothing.

    Two states qualify. ``claimed`` is the connection refusing before any
    send. ``sent`` is the vendor refusing a search it never performed — a
    daily quota that is out, a rate window that has not reopened. A search is
    a read, so in both cases nothing exists at the vendor to reconcile and the
    outcome is not ambiguous; marking the row ``unknown`` would strand the
    operation_id behind a 409 forever, long after the condition that caused it
    had cleared.
    """
    name = _table(table)
    with _connect() as con:
        con.execute(
            f"DELETE FROM {name} WHERE owner=? AND operation_id=? "
            "AND state IN ('claimed','sent')",
            (owner, operation_id),
        )


def _mark_sent(owner: str, operation_id: str, *, table: _Table = "searches") -> None:
    name = _table(table)
    with _connect() as con:
        changed = con.execute(
            f"UPDATE {name} SET state='sent',updated_at_ms=? "
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


def _clears_on_its_own(exc: BaseException) -> bool:
    """True when a refusal lifts on the vendor's clock rather than the user's.

    A 429 and a governor ban sentinel both say come back later, and the search
    they refused bought nothing. Everything else keeps the terminal mark: a
    transport error or an unparseable body leaves the outcome genuinely
    ambiguous, and a rejected credential needs the user before any retry can
    succeed.
    """
    if isinstance(exc, VendorBanned):
        return True
    return getattr(exc, "status_code", None) == 429


async def _bounded_json(request: Request) -> object:
    """The request body as JSON, refusing anything over ``_BODY_LIMIT`` bytes.

    Raises ValueError (or a JSON/Unicode error) for the caller to turn into a
    value-free 422.
    """
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > _BODY_LIMIT):
        raise ValueError
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > _BODY_LIMIT:
            raise ValueError
        raw.extend(chunk)
    return json.loads(raw)


@router.post("/search", response_model=SearchResponse)
async def search_tools(request: Request, response: Response) -> SearchResponse:
    owner = _owner(request)
    response.headers["Cache-Control"] = _PRIVATE
    try:
        body = SearchRequest.model_validate(await _bounded_json(request))
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, TypeError):
        raise _PublicError(422, "tool search request is invalid") from None
    try:
        replay = _claim(owner, body, table="searches", model=SearchResponse)
        if replay is not None:
            return replay
        connector = resolve_tool_connection(owner, body.vendor)
        _mark_sent(owner, body.operation_id)
        if body.vendor == "youtube":
            candidates = _youtube(connector.search(body.query, max_results=body.max_results))
        else:
            candidates = _x(connector.search_tweets(body.query, max_results=body.max_results))
        result = SearchResponse(
            operation_id=body.operation_id,
            vendor=body.vendor,
            status="completed",
            candidates=candidates[: body.max_results],
        )
        _complete(owner, result, table="searches")
        return result
    except _PublicError:
        raise
    except (QuotaExhausted, AcquisitionQuotaExhausted, VendorQuotaExhausted):
        _release(owner, body.operation_id)
        raise _PublicError(429, "tool quota is exhausted") from None
    except ToolConnectionUnavailable:
        _release(owner, body.operation_id)
        raise _PublicError(503, "tool search is unavailable") from None
    except (YouTubeApiError, XApiError, OSError, RuntimeError) as exc:
        if _clears_on_its_own(exc):
            _release(owner, body.operation_id)
            raise _PublicError(429, "tool search is rate limited") from None
        _unknown(owner, body.operation_id)
        raise _PublicError(503, "tool search is unavailable") from None
    finally:
        close = locals().get("connector")
        if close is not None and hasattr(close, "close"):
            close.close()


def _fetch_and_ingest(connector: object, body: IngestRequest) -> IngestResponse:
    """Fetch one item with the owner's own key and hand it to the adapter.

    The adapter call is the only graph path; this function opens nothing. The
    rights class is passed explicitly, as the named constant, so a BYOT fetch
    can never land in the graph without one (corpus_audit forbids a literal
    at the call site).
    """
    result: IngestYouTubeResult | IngestTwitterResult
    if body.vendor == "youtube":
        video = fetch_with_data_api(connector, body.external_id)
        source_tier = DEFAULT_YOUTUBE_SOURCE_TIER
        result = ingest_youtube(
            video.watch_url,
            video=video,
            investigation_id=body.investigation_id,
            content_class=PERSONAL_READING_CONTENT_CLASS,
            source_tier=source_tier,
        )
    else:
        record = connector.get_tweet(body.external_id)  # type: ignore[attr-defined]
        handle = str(record.get("author_handle") or "") or "i"
        thread = to_thread(
            [record],
            thread_url=f"https://x.com/{handle}/status/{body.external_id}",
            root_tweet_id=body.external_id,
            author_handle=handle,
        )
        source_tier = DEFAULT_TWITTER_SOURCE_TIER
        result = ingest_twitter_thread(
            thread,
            investigation_id=body.investigation_id,
            content_class=PERSONAL_READING_CONTENT_CLASS,
            source_tier=source_tier,
        )
    return IngestResponse(
        operation_id=body.operation_id,
        vendor=body.vendor,
        external_id=body.external_id,
        status="completed",
        ingest_status="ingested" if result.chunks_written > 0 else "skipped",
        document_id=result.document_id,
        chunks_written=int(result.chunks_written),
        skipped_reason=result.skipped_reason,
        title=result.title,
        content_class=PERSONAL_READING_CONTENT_CLASS,
        source_tier=source_tier,
    )


class _AdapterFailed(Exception):
    """An unexpected failure inside fetch-and-ingest, after the operation was sent.

    Most often the adapter failing after a paid fetch; also anything the fetch
    step raises that is not a known vendor refusal. Either way the outcome is
    not known to be nothing, so the operation is marked unknown, not released.
    """


@router.post("/ingest", response_model=IngestResponse)
async def ingest_tool_candidate(request: Request, response: Response) -> IngestResponse:
    """Ingest one connected-tool candidate with the caller's own credential.

    Replays on ``operation_id``: the same body posted again returns the saved
    response with ``status="replayed"`` and makes no vendor call and no
    adapter call. A refusal that bought nothing (quota, rate, not found, no
    connection) releases the operation_id for a retry; a failure whose
    outcome is ambiguous (transport error mid-fetch, adapter failure after a
    paid fetch) marks it unknown, and it answers 409 until someone looks.
    """
    owner = _owner(request)
    response.headers["Cache-Control"] = _PRIVATE
    try:
        body = IngestRequest.model_validate(await _bounded_json(request))
        if not _EXTERNAL_ID[body.vendor].match(body.external_id):
            raise ValueError
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, TypeError):
        raise _PublicError(422, "tool ingest request is invalid") from None
    connector: object | None = None
    try:
        replay = _claim(owner, body, table="ingests", model=IngestResponse)
        if replay is not None:
            return replay
        connector = resolve_tool_connection(owner, body.vendor)
        _mark_sent(owner, body.operation_id, table="ingests")
        try:
            # Off the loop: the vendor fetch, the embedding and the adapter's
            # write-lock wait would otherwise stall every request on a
            # --workers 1 server (the no_indirect_write_in_async rule; the
            # adapter sits in another module, so the lint cannot see it here).
            result = await asyncio.to_thread(_fetch_and_ingest, connector, body)
        except (
            _PublicError, QuotaExhausted, AcquisitionQuotaExhausted, VendorQuotaExhausted,
            YouTubeRateCapExceeded, YouTubeApiError, XApiError, OSError, RuntimeError,
        ):
            raise
        except Exception as exc:
            raise _AdapterFailed from exc
        _complete(owner, result, table="ingests")
        return result
    except _PublicError:
        raise
    except (QuotaExhausted, AcquisitionQuotaExhausted, VendorQuotaExhausted):
        _release(owner, body.operation_id, table="ingests")
        raise _PublicError(429, "tool quota is exhausted") from None
    except ToolConnectionUnavailable:
        _release(owner, body.operation_id, table="ingests")
        raise _PublicError(503, "tool ingest is unavailable") from None
    except YouTubeRateCapExceeded:
        _release(owner, body.operation_id, table="ingests")
        raise _PublicError(429, "tool ingest is rate limited") from None
    except (YouTubeApiError, XApiError, OSError, RuntimeError) as exc:
        if _clears_on_its_own(exc):
            _release(owner, body.operation_id, table="ingests")
            raise _PublicError(429, "tool ingest is rate limited") from None
        if getattr(exc, "status_code", None) == 404:
            _release(owner, body.operation_id, table="ingests")
            raise _PublicError(404, "tool item was not found") from None
        _unknown(owner, body.operation_id, table="ingests")
        raise _PublicError(503, "tool ingest is unavailable") from None
    except _AdapterFailed:
        _unknown(owner, body.operation_id, table="ingests")
        raise _PublicError(503, "tool ingest is unavailable") from None
    finally:
        if connector is not None and hasattr(connector, "close"):
            connector.close()


def register_research_tool_search_routes(app: FastAPI) -> None:
    @app.exception_handler(_PublicError)
    async def _private_error(_request: Request, exc: _PublicError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"detail": exc.detail},
            headers={"Cache-Control": _PRIVATE},
        )

    app.include_router(router)


__all__ = [
    "ClosableToolConnector",
    "connected_tool_for_request",
    "register_research_tool_search_routes",
]
