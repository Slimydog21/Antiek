"""Universal-library ingestion HTTP API (SPR-03 / M1).

FastAPI route handlers for:

  POST /api/library/ingest             — submit a URL for ingestion
  GET  /api/library/ingest/{job_id}    — poll job status

The TypeScript client + types live in
``apps/reading/api/library/{ingest.ts, types.ts}``. The contract on the
two sides is hand-maintained per the polyglot-seam discipline (see
``docs/architecture_notes.md`` §11.1). The Pydantic models below are
the canonical source; any drift surfaces in SPR-06's typecheck.

Auth: requires logged-in user. The operator-auth middleware
(``interfaces/research/api/app.py`` §H4/H6) populates
``request.state.user_id``; this module reads from there and never
duplicates auth logic. Unauthenticated callers get 401 from the
middleware *before* this handler runs (when auth env vars are set).

Synchronous-fast path: when the URL is already a successful
ingestion in this same process (job cache hit), we return the
document_id immediately. Today the cache lives in the fetcher's
disk LRU — a cached fetch + a fresh extract is still ~hundreds of ms,
so the API always returns through the job machinery and lets the
client poll. The TS client's ``pollUntilTerminal`` handles this
uniformly.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Any, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

# Repo root for sibling imports.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from services.ingestion import jobs as jobs_mod  # noqa: E402
from services.ingestion import pipeline as pipeline_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Pydantic request / response models — canonical contract
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    """Request body for ``POST /api/library/ingest``."""

    url: str = Field(min_length=1, max_length=4096)
    user_id: str = Field(min_length=1, max_length=256)
    source_metadata: Optional[dict[str, Any]] = None


class IngestResponse(BaseModel):
    """Initial response for ``POST /api/library/ingest``."""

    job_id: str
    document_id: Optional[str] = None
    status: str  # pending | running | succeeded | failed
    content_type: Optional[str] = None
    error: Optional[str] = None
    paywalled: bool = False


class IngestJobResponse(BaseModel):
    """Full job row for ``GET /api/library/ingest/{job_id}``."""

    job_id: str
    url: str
    user_id: str
    investigation_id: str
    status: str
    content_type: Optional[str] = None
    document_id: Optional[str] = None
    error: Optional[str] = None
    error_detail: Optional[str] = None
    attempts: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


def _validate_url(url: str) -> str:
    """Return the validated URL or raise HTTPException 400.

    We do a lightweight check: must parse, must have an http/https
    scheme, must have a host. The fetcher's later layers (banned_until,
    robots.txt, throttle) handle the policy concerns; URL validation
    is just "is this a URL the fetcher can handle at all."
    """
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "malformed_url", "message": str(e)}},
        ) from e
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "unsupported_scheme",
                    "message": (
                        "Only http(s) URLs are supported. "
                        f"Got scheme={parsed.scheme!r}."
                    ),
                }
            },
        )
    if not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "missing_host",
                    "message": "URL must include a host.",
                }
            },
        )
    return url


def _resolve_user_id(request: Request, body_user_id: str) -> str:
    """Resolve the effective user_id. Prefer the auth middleware's
    resolution; fall back to the body for tests / dev where the
    middleware bypasses (existing pattern: when auth env vars are
    unset, request.state.user_id is ``__operator__``).

    If the body and middleware disagree AND auth is enforced, we
    trust the middleware. Body user_id is for tests + a future
    multi-user scenario where the operator ingests on behalf of
    another account."""
    from_state = getattr(request.state, "user_id", None)
    auth_method = getattr(request.state, "auth_method", "")
    if from_state and auth_method != "unauthenticated_local":
        return str(from_state)
    return body_user_id


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------


def _run_ingest_background(
    *,
    job_id: str,
    url: str,
    user_id: str,
    investigation_id: str,
    db_path: Optional[str],
) -> None:
    """Run the pipeline in a background thread so the API returns
    immediately. The pipeline is synchronous + IO-heavy — a thread
    is the right primitive for now. Async-redesign lands when we
    have an actual queue (Celery / RQ); the substrate doesn't need
    one yet."""
    try:
        pipeline_mod.ingest(
            url=url,
            user_id=user_id,
            investigation_id=investigation_id,
            job_id=job_id,
            db_path=db_path,
        )
    except Exception as exc:  # noqa: BLE001 — pipeline.ingest writes
        # its own failure rows; only logging here if it somehow raises.
        import traceback
        print(
            f"[ingest job {job_id}] background runner crashed: {exc!r}\n"
            f"{traceback.format_exc()}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def register_library_routes(
    app: FastAPI,
    *,
    db_path: Optional[str] = None,
    run_inline: bool = False,
) -> None:
    """Mount the universal-library routes onto ``app``.

    ``run_inline`` runs the pipeline synchronously in the request
    handler (used by tests so they can assert on the final state
    without polling). Production uses ``run_inline=False``: the
    pipeline runs in a daemon thread and the API returns immediately.
    """

    @app.post(
        "/api/library/ingest",
        response_model=IngestResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["library"],
    )
    async def post_library_ingest(  # noqa: F811 — FastAPI handler
        request: Request, body: IngestRequest,
    ) -> IngestResponse:
        url = _validate_url(body.url)
        user_id = _resolve_user_id(request, body.user_id)

        # Create the job up front so the client has something to poll
        # even if the background thread crashes.
        job = jobs_mod.create_job(
            url=url, user_id=user_id,
            metadata=body.source_metadata or {},
            db_path=db_path,
        )

        if run_inline:
            result = pipeline_mod.ingest(
                url=url, user_id=user_id,
                job_id=job.job_id,
                db_path=db_path,
            )
            return IngestResponse(
                job_id=result.job_id,
                document_id=result.document_id,
                status=result.status,
                content_type=result.content_type,
                error=result.error,
                paywalled=result.paywalled,
            )

        # Background path — return 202 + job_id immediately.
        t = threading.Thread(
            target=_run_ingest_background,
            kwargs={
                "job_id": job.job_id,
                "url": url,
                "user_id": user_id,
                "investigation_id": "__operator__",
                "db_path": db_path,
            },
            daemon=True,
            name=f"ingest-{job.job_id}",
        )
        t.start()
        return IngestResponse(
            job_id=job.job_id,
            document_id=None,
            status="pending",
            content_type=None,
            error=None,
        )

    @app.get(
        "/api/library/ingest/{job_id}",
        response_model=IngestJobResponse,
        tags=["library"],
    )
    async def get_library_ingest_job(job_id: str) -> IngestJobResponse:
        job = jobs_mod.get_job(job_id, db_path=db_path)
        if job is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "job_not_found", "message": job_id}},
            )
        return IngestJobResponse(
            job_id=job.job_id,
            url=job.url,
            user_id=job.user_id,
            investigation_id=job.investigation_id,
            status=job.status,
            content_type=job.content_type,
            document_id=job.document_id,
            error=job.error,
            error_detail=job.error_detail,
            attempts=job.attempts,
            created_at=job.created_at.isoformat() if job.created_at else None,
            updated_at=job.updated_at.isoformat() if job.updated_at else None,
            metadata=job.metadata,
        )


# Standalone router for callers that don't want to mount on the main
# Antiek app (e.g. a microservice deployment of just the ingestion
# surface).
def make_router(
    *,
    db_path: Optional[str] = None,
    run_inline: bool = False,
) -> APIRouter:
    """Return a router with the same two routes attached. Caller
    mounts it via ``app.include_router(router, prefix='/api')`` or
    similar."""
    router = APIRouter(tags=["library"])

    # We reuse register_library_routes by building a tiny throwaway
    # FastAPI shim and re-attaching the routes — DRY at the cost of
    # one extra import. Direct route registration on the router is
    # equally fine; this keeps the surface in one place.
    shim = FastAPI()
    register_library_routes(shim, db_path=db_path, run_inline=run_inline)
    for r in shim.routes:
        if getattr(r, "path", "").startswith("/api/library/ingest"):
            router.routes.append(r)
    return router
