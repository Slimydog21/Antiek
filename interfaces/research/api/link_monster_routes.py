"""Link Monster — REST surface.

The Monster's mouth on the wire:

- ``POST /links/monster`` — digest one URL (validate → classify →
  guard → ladder-extract → stew into the graph). Sync handler on
  purpose (threadpool, like krea_routes): blocking I/O never stalls
  the single-worker event loop (CLAUDE.md invariant 1).
- ``GET /links/monster/feed`` — the Monster Menu (recent digests).
- ``GET /links/monster/stats`` — what the Monster has eaten, in counts.
- ``GET /links/monster/{document_id}`` — one meal in full: digest
  packet + chunks + graph neighbors.

Error contract (mirrors krea_routes' honest-typed-failure idiom): every
failure is a typed JSON body with a machine-readable ``reason`` and the
correct status — 400 invalid URL, 422 SSRF-blocked, 429 rate-limited,
502 upstream unreachable — never a bare 500, never a hang. No keys are
ever accepted or emitted; the URL is never echoed beyond the normalized
final URL.

No auth is added here: the app-level operator surface owns identity
(mirrors krea/multimedia routes). Rate limiting is a per-process
sliding window on POST only.
"""

from __future__ import annotations

import threading
import time

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from acquisition.link_monster.fetchguard import UnsafeUrlError

# POST rate limit: N digests per minute per process. The Monster is a
# single-operator surface; the cap is anti-abuse scaffolding, not a
# product ceiling. Override via LINK_MONSTER_RATE_MAX (call-time read,
# like the krea knobs).
DEFAULT_RATE_MAX = 10
RATE_WINDOW_S = 60.0


class DigestRequest(BaseModel):
    """POST body for ``/links/monster``."""

    url: str = Field(..., min_length=1, max_length=4096)
    investigation_id: str | None = None


class _RateLimiter:
    """Sliding-window rate limiter (per-process, POST only)."""

    def __init__(self, max_per_window: int, window_s: float) -> None:
        self.max = max_per_window
        self.window = window_s
        self._lock = threading.Lock()
        self._stamps: list[float] = []

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._stamps = [s for s in self._stamps if now - s < self.window]
            if len(self._stamps) >= self.max:
                return False
            self._stamps.append(now)
            return True


def _max_per_window() -> int:
    import os

    try:
        return max(1, int(os.environ.get("LINK_MONSTER_RATE_MAX", DEFAULT_RATE_MAX)))
    except ValueError:
        return DEFAULT_RATE_MAX


def _error(reason: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"ok": False, "reason": reason, "message": message},
    )


def register_link_monster_routes(app: FastAPI) -> None:
    """Mount the Link Monster routes. One call from ``create_app``
    (mirrors ``register_krea_routes``). Rate-limiter + injectable
    httpx client live on app.state so tests get a fresh limiter and a
    MockTransport without monkeypatching module globals."""

    app.state.link_monster_limiter = _RateLimiter(_max_per_window(), RATE_WINDOW_S)

    @app.post("/links/monster", tags=["link-monster"])
    def monster_digest(req: DigestRequest) -> JSONResponse:
        """Digest one URL into the graph. Returns the digest packet +
        store summary. ``already_digested: true`` when this final URL
        was eaten before (idempotent — no duplicate rows/events)."""
        if not app.state.link_monster_limiter.allow():
            return _error("rate_limited", "slow down — the Monster is still chewing", 429)
        from acquisition.link_monster import digest_url, store_digest

        _started = time.monotonic()
        try:
            result = digest_url(req.url, client=getattr(app.state, "link_monster_http_client", None))
        except UnsafeUrlError as e:
            if e.reason.startswith(("bad_scheme", "empty_url", "no_host", "userinfo_forbidden")):
                return _error("invalid_url", str(e), 400)
            return _error("ssrf_blocked", f"refused to fetch {e.reason}", 422)
        except ValueError as e:
            return _error("invalid_url", str(e), 400)
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            return _error("upstream_error", f"{type(e).__name__}: {str(e)[:200]}", 502)
        except Exception as e:  # noqa: BLE001 — honest catch-all → typed 502
            return _error("digest_failed", f"{type(e).__name__}: {str(e)[:200]}", 502)

        try:
            store = store_digest(
                result.digest,
                investigation_id=req.investigation_id,
                duration_ms=int((time.monotonic() - _started) * 1000),
            )
        except Exception as e:  # noqa: BLE001
            return _error("store_failed", f"{type(e).__name__}: {str(e)[:200]}", 502)

        return JSONResponse(
            {
                "ok": True,
                "document_id": result.document_id,
                "already_digested": store.already_digested,
                "digest": result.digest.to_jsonable(),
                "store": {
                    "chunks_written": store.chunks_written,
                    "node_ids": store.node_ids,
                    "edge_ids": store.edge_ids,
                    "content_class": store.content_class,
                    "already_digested": store.already_digested,
                },
            }
        )

    @app.get("/links/monster/feed", tags=["link-monster"])
    def monster_feed(limit: int = Query(default=20, ge=1, le=100)) -> JSONResponse:
        """Monster Menu — recent digests, newest first."""
        from acquisition.link_monster import list_digests

        return JSONResponse({"ok": True, "items": list_digests(limit=limit)})

    @app.get("/links/monster/stats", tags=["link-monster"])
    def monster_stats() -> JSONResponse:
        """Counts: meals, snacks, chunks/nodes/edges contributed,
        per-platform breakdown."""
        from acquisition.link_monster.store import digest_stats

        return JSONResponse({"ok": True, **digest_stats()})

    @app.get("/links/monster/{document_id}", tags=["link-monster"])
    def monster_detail(document_id: str) -> JSONResponse:
        """One meal in full: digest packet + chunks + graph neighbors."""
        from acquisition.link_monster.store import get_digest

        detail = get_digest(document_id)
        if detail is None:
            return _error("not_found", "no such meal", 404)
        return JSONResponse({"ok": True, **detail})
