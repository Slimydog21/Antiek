"""
Tests for SPR-09 agent-loved API surface (envelope + idempotency + discovery).

Three concerns:

  1. ``envelope.py`` — closed ERROR_CODES set, ResponseEnvelope shape,
     EnvelopedHTTPException → JSONResponse conversion.
  2. ``idempotency.py`` — cache semantics, TTL, replay behavior,
     missing-header rejection.
  3. ``discovery.py`` — /.well-known/mcp.json + /discovery endpoints
     return the expected shape against a minimal FastAPI app.

Layout: flat under tests/ matching the repo convention. File prefixed
``test_yegge_`` to keep SPR-09 tests grouped without folder nesting.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fastapi import FastAPI, Header, Request
from fastapi.testclient import TestClient

from interfaces.research.api.discovery import router as discovery_router
from interfaces.research.api.envelope import (
    ERROR_CODES,
    EnvelopedHTTPException,
    ErrorEnvelope,
    ResponseEnvelope,
    install_exception_handler,
)
from interfaces.research.api.idempotency import (
    CachedResponse,
    IdempotencyCache,
    record_completion,
    require_idempotency_key,
    reset_default_cache_for_tests,
)


# ---------------------------------------------------------------------------
# envelope.py — ResponseEnvelope shape + ERROR_CODES enforcement
# ---------------------------------------------------------------------------


def test_response_envelope_success_shape():
    env = ResponseEnvelope.success(data={"thing": 42})
    assert env.ok is True
    assert env.data == {"thing": 42}
    assert env.error is None


def test_response_envelope_failure_shape():
    env = ResponseEnvelope.failure(
        code="NOT_FOUND", message="thing 'abc' not found",
        details={"id": "abc"},
    )
    assert env.ok is False
    assert env.data is None
    assert env.error is not None
    assert env.error.code == "NOT_FOUND"
    assert env.error.details == {"id": "abc"}


def test_error_envelope_rejects_unknown_code():
    with pytest.raises(ValueError, match="not in ERROR_CODES"):
        ErrorEnvelope(code="MADE_UP_CODE", message="...")


def test_enveloped_http_exception_rejects_unknown_code():
    with pytest.raises(ValueError, match="not in ERROR_CODES"):
        EnvelopedHTTPException(code="MADE_UP", message="...")


def test_error_codes_set_is_closed():
    # If a new code is added to the canon, this test surfaces the
    # change at code review (the test value below has to be updated
    # deliberately — preventing silent expansion).
    expected = {
        "INVALID_INPUT", "NOT_FOUND", "RATE_LIMIT", "UNAUTHORIZED",
        "FORBIDDEN", "CONFLICT", "INTERNAL_ERROR", "BUDGET_EXCEEDED",
        "IDEMPOTENCY_KEY_REQUIRED", "IDEMPOTENCY_REPLAY",
        "UPSTREAM_UNAVAILABLE",
    }
    assert set(ERROR_CODES) == expected, (
        "ERROR_CODES changed. If this is intentional, update both the "
        "constant in envelope.py and this test together."
    )


# ---------------------------------------------------------------------------
# install_exception_handler — exception → JSONResponse renderer
# ---------------------------------------------------------------------------


def _build_app_with_envelope() -> FastAPI:
    app = FastAPI()
    install_exception_handler(app)

    @app.get("/ok")
    async def ok() -> ResponseEnvelope[dict]:
        return ResponseEnvelope.success(data={"hi": "there"})

    @app.get("/missing")
    async def missing() -> ResponseEnvelope[dict]:
        raise EnvelopedHTTPException(
            code="NOT_FOUND", message="nope", status_code=404,
            details={"hint": "try a different id"},
        )

    return app


def test_envelope_renders_success_shape_on_2xx():
    # Agents check ``ok`` first, then read ``data``. ``error`` may
    # serialize as null in the success case — that's fine and agent
    # callers ignore it; we assert the agent-meaningful fields.
    client = TestClient(_build_app_with_envelope())
    r = client.get("/ok")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"] == {"hi": "there"}
    # error may be null or absent; both are valid in the success shape
    assert body.get("error") is None


def test_envelope_renders_failure_shape_on_raise():
    client = TestClient(_build_app_with_envelope())
    r = client.get("/missing")
    assert r.status_code == 404
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["details"] == {"hint": "try a different id"}


# ---------------------------------------------------------------------------
# idempotency.py — cache + dependency + record_completion
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_idempotency_cache():
    # Each test starts with a fresh cache singleton.
    reset_default_cache_for_tests()
    yield
    reset_default_cache_for_tests()


@pytest.mark.asyncio
async def test_idempotency_missing_header_raises_required():
    with pytest.raises(EnvelopedHTTPException) as exc_info:
        await require_idempotency_key("POST /thing", None)
    assert exc_info.value.code == "IDEMPOTENCY_KEY_REQUIRED"
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_idempotency_first_request_returns_key():
    key = await require_idempotency_key("POST /thing", "abc-123")
    assert key == "abc-123"


@pytest.mark.asyncio
async def test_idempotency_replay_after_record_completion():
    key = "abc-123"
    # First request — caller records completion.
    await require_idempotency_key("POST /thing", key)
    await record_completion(
        "POST /thing", key,
        status_code=201, body={"ok": True, "data": {"id": "t1"}},
    )
    # Second request with same key — should raise IDEMPOTENCY_REPLAY
    # and the details carry the prior response.
    with pytest.raises(EnvelopedHTTPException) as exc_info:
        await require_idempotency_key("POST /thing", key)
    assert exc_info.value.code == "IDEMPOTENCY_REPLAY"
    assert exc_info.value.details is not None
    assert exc_info.value.details["previous_status_code"] == 201
    assert exc_info.value.details["previous_body"]["data"]["id"] == "t1"


@pytest.mark.asyncio
async def test_idempotency_ttl_expires_correctly():
    cache = IdempotencyCache(ttl_seconds=1, max_entries=100)
    await cache.put(
        "POST /thing", "key",
        CachedResponse(
            status_code=200, body={"x": 1},
            stored_at_monotonic=time.monotonic() - 5,  # already-expired
            stored_at_wall=time.time() - 5,
        ),
    )
    # Should miss because stored_at is 5s old vs 1s ttl
    assert await cache.get("POST /thing", "key") is None


@pytest.mark.asyncio
async def test_idempotency_per_route_isolation():
    """Same key on different routes must NOT collide — routes are
    independent namespaces by design."""
    await require_idempotency_key("POST /a", "same-key")
    await record_completion("POST /a", "same-key",
                            status_code=200, body={"route": "a"})
    # Different route, same key — must NOT replay
    key = await require_idempotency_key("POST /b", "same-key")
    assert key == "same-key"


@pytest.mark.asyncio
async def test_idempotency_fifo_eviction_at_capacity():
    cache = IdempotencyCache(ttl_seconds=3600, max_entries=2)
    for i, k in enumerate(["k1", "k2", "k3"]):
        await cache.put(
            "POST /thing", k,
            CachedResponse(
                status_code=200, body={"i": i},
                stored_at_monotonic=time.monotonic(),
                stored_at_wall=time.time(),
            ),
        )
    # k1 should be evicted; k2 and k3 remain.
    assert await cache.get("POST /thing", "k1") is None
    assert await cache.get("POST /thing", "k2") is not None
    assert await cache.get("POST /thing", "k3") is not None
    assert cache.size() == 2


# ---------------------------------------------------------------------------
# discovery.py — /.well-known/mcp.json + /discovery against a real app
# ---------------------------------------------------------------------------


def _build_app_with_discovery() -> FastAPI:
    app = FastAPI()
    install_exception_handler(app)
    app.include_router(discovery_router)

    @app.get("/example", summary="example endpoint for discovery test")
    async def example() -> ResponseEnvelope[dict]:
        return ResponseEnvelope.success(data={})

    @app.post("/example")
    async def example_post() -> ResponseEnvelope[dict]:
        return ResponseEnvelope.success(data={})

    return app


def test_discovery_summary_lists_three_surfaces():
    client = TestClient(_build_app_with_discovery())
    r = client.get("/discovery")
    assert r.status_code == 200
    body = r.json()
    assert body["openapi"].endswith("/openapi.json")
    assert body["mcp_manifest"].endswith("/.well-known/mcp.json")
    assert "envelope_convention" in body
    assert "idempotency" in body


def test_mcp_manifest_lists_app_routes():
    client = TestClient(_build_app_with_discovery())
    r = client.get("/.well-known/mcp.json")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "antiek-research"
    assert isinstance(body["tools"], list)
    # /example should appear; /openapi.json shouldn't (it's filtered out
    # — agents that want it follow openapi_url).
    paths = {t["path"] for t in body["tools"]}
    assert "/example" in paths
    assert "/openapi.json" not in paths


def test_openapi_is_auto_exposed():
    """Confirm FastAPI auto-exposes /openapi.json — the SPR-09 contract
    explicitly relies on this. If FastAPI ever changes the default we
    want to know."""
    client = TestClient(_build_app_with_discovery())
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert "openapi" in spec
    assert "paths" in spec
    assert "/example" in spec["paths"]
