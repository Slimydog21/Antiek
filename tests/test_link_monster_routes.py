"""Link Monster — REST routes tests.

Exercises the four routes through TestClient with a MockTransport-backed
httpx client injected on app.state (no network) and a tmp substrate DB.
The SSRF DNS check is bypassed for the fake public host; the guard's own
behavior is covered in test_link_monster_fetchguard.py.
"""

from __future__ import annotations

import os
import tempfile

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import interfaces.research.api.link_monster_routes as lm

_ARTICLE_HTML = b"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>T</title>
<meta property="og:title" content="Route Title">
<meta property="og:site_name" content="Route Site">
</head><body><article>
<p>This is a substantive article body for the route test with enough words
to clear the chunker minimum and become a meal rather than a snack. It
talks about graphs, monsters, and provenance with real sentences.</p>
</article></body></html>"""


@pytest.fixture
def app_and_client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-lm-routes-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    def _safe(hostname: str) -> bool:
        return hostname == "public.example.com"

    monkeypatch.setattr("acquisition.link_monster.fetchguard._host_is_safe", _safe)
    monkeypatch.setenv("LINK_MONSTER_RATE_MAX", "100")

    app = FastAPI()
    lm.register_link_monster_routes(app)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "public.example.com":
            return httpx.Response(
                200, content=_ARTICLE_HTML,
                headers={"content-type": "text/html; charset=utf-8"},
            )
        if req.url.host == "publish.twitter.com":
            return httpx.Response(404)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, timeout=5.0)
    app.state.link_monster_http_client = client
    tc = TestClient(app)
    yield app, tc, db_path
    client.close()


def test_post_digest_meal(app_and_client):
    app, tc, db_path = app_and_client
    resp = tc.post("/links/monster", json={"url": "https://public.example.com/post/1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["digest"]["platform"] == "generic"
    assert body["digest"]["outcome"] == "meal"
    assert body["digest"]["title"] == "Route Title"
    assert body["store"]["chunks_written"] >= 1
    assert body["store"]["content_class"] == "personal_reading"
    doc_id = body["document_id"]

    # dedup on re-ingest
    resp2 = tc.post("/links/monster", json={"url": "https://public.example.com/post/1"})
    assert resp2.status_code == 200
    assert resp2.json()["already_digested"] is True

    # feed shows it
    feed = tc.get("/links/monster/feed?limit=5")
    assert feed.status_code == 200
    assert feed.json()["items"][0]["document_id"] == doc_id

    # detail resolves
    det = tc.get(f"/links/monster/{doc_id}")
    assert det.status_code == 200
    assert det.json()["chunks"]

    # stats reflect it
    stats = tc.get("/links/monster/stats")
    assert stats.status_code == 200
    assert stats.json()["meals"] == 1
    assert stats.json()["by_platform"].get("generic") == 1
    assert stats.json()["chunks"] >= 1  # counts key off document ids, not outcomes


def test_post_invalid_url(app_and_client):
    app, tc, db_path = app_and_client
    resp = tc.post("/links/monster", json={"url": "file:///etc/passwd"})
    assert resp.status_code == 400
    assert resp.json()["ok"] is False
    assert resp.json()["reason"] == "invalid_url"


def test_post_ssrf_blocked(app_and_client):
    app, tc, db_path = app_and_client
    resp = tc.post("/links/monster", json={"url": "http://127.0.0.1:8001/health"})
    assert resp.status_code == 422
    assert resp.json()["reason"] == "ssrf_blocked"


def test_detail_not_found(app_and_client):
    app, tc, db_path = app_and_client
    resp = tc.get("/links/monster/nope")
    assert resp.status_code == 404
    assert resp.json()["reason"] == "not_found"


def test_rate_limiter_blocks(app_and_client, monkeypatch):
    app, tc, db_path = app_and_client
    monkeypatch.setenv("LINK_MONSTER_RATE_MAX", "2")
    app.state.link_monster_limiter = lm._RateLimiter(2, 60.0)
    for _ in range(2):
        r = tc.post("/links/monster", json={"url": "https://public.example.com/a"})
        assert r.status_code == 200
    r3 = tc.post("/links/monster", json={"url": "https://public.example.com/b"})
    assert r3.status_code == 429
    assert r3.json()["reason"] == "rate_limited"
