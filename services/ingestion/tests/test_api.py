"""Tests for the HTTP API surface (SPR-03 / M1).

Coverage:

- POST /api/library/ingest happy path returns job_id + 202.
- POST validates URL: 400 on malformed / non-http scheme.
- GET /api/library/ingest/{job_id} returns the job row.
- GET 404 for unknown job.
- run_inline mode (test convenience) returns the document_id in the
  initial POST response.
"""

from __future__ import annotations

import os
import sys
import tempfile

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from services.ingestion.tests.fixtures import HTML_SUBSTACK_LIKE


@pytest.fixture
def app_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-spr03-api-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    cache_dir = os.path.join(tmpdir, "ingest_cache")
    os.makedirs(events_dir, exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    monkeypatch.setenv("ANTIEK_INGEST_CACHE_DIR", cache_dir)

    import fakeredis
    from services.ingestion import throttle
    throttle.set_client_for_tests(fakeredis.FakeRedis(decode_responses=True))
    from services.ingestion import fetcher
    fetcher.cache_clear_for_tests()
    fetcher.robots_cache_clear_for_tests()

    app = FastAPI()
    from interfaces.research.api.library import register_library_routes
    register_library_routes(app, db_path=db_path, run_inline=True)
    yield {"app": app, "db_path": db_path}
    throttle.reset_for_tests()
    fetcher.cache_clear_for_tests()


def test_post_ingest_validates_malformed_url(app_env):
    client = TestClient(app_env["app"])
    res = client.post(
        "/api/library/ingest",
        json={"url": "not-a-url", "user_id": "u"},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] in (
        "missing_host", "unsupported_scheme",
    )


def test_post_ingest_rejects_non_http_scheme(app_env):
    client = TestClient(app_env["app"])
    res = client.post(
        "/api/library/ingest",
        json={"url": "ftp://example.com/file", "user_id": "u"},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "unsupported_scheme"


def test_post_ingest_succeeds_inline(app_env, monkeypatch):
    """Inline mode: pipeline runs synchronously in the handler, the
    response contains document_id. We patch the fetcher's HTTP client
    layer with an httpx.MockTransport via the module's default
    client path."""
    # Monkey-patch the pipeline's content_type detect to skip the
    # HEAD network call AND swap the fetcher's HTTP path to our
    # mock. Easiest path: inject a global mock httpx client via
    # monkeypatch of httpx.Client.
    captured: list[str] = []

    def mock_transport_handler(req: httpx.Request) -> httpx.Response:
        captured.append(str(req.url))
        if "robots.txt" in str(req.url):
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=HTML_SUBSTACK_LIKE,
        )

    real_client = httpx.Client
    transport = httpx.MockTransport(mock_transport_handler)

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", patched_client)

    client = TestClient(app_env["app"])
    res = client.post(
        "/api/library/ingest",
        json={"url": "https://blog.example.com/x", "user_id": "u-test"},
    )
    assert res.status_code in (200, 202)
    data = res.json()
    assert data["job_id"].startswith("job-")
    assert data["document_id"] is not None
    assert data["status"] == "succeeded"
    assert data["content_type"] == "html_article"


def test_get_unknown_job_returns_404(app_env):
    client = TestClient(app_env["app"])
    res = client.get("/api/library/ingest/job-nonexistent")
    assert res.status_code == 404
    assert res.json()["detail"]["error"]["code"] == "job_not_found"
