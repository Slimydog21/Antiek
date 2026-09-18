from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx
import nacl.secret
from fastapi import FastAPI
from fastapi.testclient import TestClient

from acquisition.twitter.api_client import XApiError
from interfaces.research.api import research_tool_search as subject
from runtime.connectors.registry import connect_tool
from runtime.connectors.registry import resolve_tool_connection as real_resolve_tool_connection


@dataclass
class _YouTubeRow:
    video_id: str = "vid-1"
    kind: str = "video"
    title: str = "A useful result"
    published_at: str = "2026-08-12T00:00:00Z"
    channel_title: str = "Researcher"


class _Connector:
    calls = 0

    def search(self, query: str, *, max_results: int):
        assert query == "fusion materials"
        assert max_results == 5
        type(self).calls += 1
        return [_YouTubeRow()]

    def close(self) -> None:
        pass


def _client(monkeypatch, tmp_path, *, owner: str = "owner-a") -> TestClient:
    monkeypatch.setenv("ANTIEK_TOOL_SEARCH_JOURNAL", str(tmp_path / "journal.sqlite3"))
    monkeypatch.setattr(subject, "resolve_tool_connection", lambda *_args, **_kwargs: _Connector())
    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user_id = owner
        request.state.auth_method = "antiek_session_cookie"
        return await call_next(request)

    subject.register_research_tool_search_routes(app)
    return TestClient(app)


def test_owner_search_replays_without_second_vendor_send(monkeypatch, tmp_path):
    _Connector.calls = 0
    client = _client(monkeypatch, tmp_path)
    body = {
        "operation_id": "search_operation_001",
        "vendor": "youtube",
        "query": "fusion materials",
        "max_results": 5,
    }
    first = client.post("/research/tools/search", json=body)
    replay = client.post("/research/tools/search", json=body)
    assert first.status_code == 200
    assert first.json() == {
        "operation_id": "search_operation_001",
        "vendor": "youtube",
        "status": "completed",
        "candidates": [{
            "external_id": "vid-1",
            "title_or_text": "A useful result",
            "url": "https://www.youtube.com/watch?v=vid-1",
            "published_at": "2026-08-12T00:00:00Z",
            "author": "Researcher",
        }],
    }
    assert replay.status_code == 200
    assert replay.json()["status"] == "replayed"
    assert _Connector.calls == 1


def test_mutated_operation_conflicts_without_query_echo(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    original = {
        "operation_id": "search_operation_001",
        "vendor": "youtube",
        "query": "fusion materials",
        "max_results": 5,
    }
    assert client.post("/research/tools/search", json=original).status_code == 200
    changed = dict(original, query="PRIVATE MARKER")
    response = client.post("/research/tools/search", json=changed)
    assert response.status_code == 409
    assert "PRIVATE MARKER" not in response.text


def test_shared_operator_identity_is_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, owner="__operator__")
    response = client.post("/research/tools/search", json={
        "operation_id": "search_operation_001",
        "vendor": "youtube",
        "query": "fusion materials",
        "max_results": 5,
    })
    assert response.status_code == 401


def test_concurrent_duplicate_waits_and_sends_once(monkeypatch, tmp_path):
    _Connector.calls = 0
    barrier = threading.Barrier(2)

    class SlowConnector(_Connector):
        def search(self, query: str, *, max_results: int):
            type(self).calls += 1
            barrier.wait(timeout=2)
            return [_YouTubeRow()]

    monkeypatch.setenv("ANTIEK_TOOL_SEARCH_JOURNAL", str(tmp_path / "journal.sqlite3"))
    monkeypatch.setattr(subject, "resolve_tool_connection", lambda *_args, **_kwargs: SlowConnector())
    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user_id = "owner-a"
        request.state.auth_method = "antiek_session_cookie"
        return await call_next(request)

    subject.register_research_tool_search_routes(app)
    body = {"operation_id": "search_operation_001", "vendor": "youtube", "query": "q", "max_results": 5}
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(client.post, "/research/tools/search", json=body)
        barrier.wait(timeout=2)
        second = client.post("/research/tools/search", json=body)
        first = future.result(timeout=3)
    assert sorted([first.status_code, second.status_code]) == [200, 200]
    assert {first.json()["status"], second.json()["status"]} == {"completed", "replayed"}
    assert SlowConnector.calls == 1


def test_malformed_vendor_response_is_unknown_and_never_retried(monkeypatch, tmp_path):
    sends = 0

    class BrokenConnector(_Connector):
        def search(self, query: str, *, max_results: int):
            nonlocal sends
            sends += 1
            raise XApiError("X API returned an invalid response")

    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(subject, "resolve_tool_connection", lambda *_args, **_kwargs: BrokenConnector())
    body = {"operation_id": "search_operation_001", "vendor": "youtube", "query": "q", "max_results": 5}
    first = client.post("/research/tools/search", json=body)
    replay = client.post("/research/tools/search", json=body)
    assert first.status_code == 503
    assert replay.status_code == 409
    assert sends == 1


def test_private_value_free_errors_never_cache_or_echo_query(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    marker = "PRIVATE-QUERY-" + "x" * 600
    invalid = client.post("/research/tools/search", json={
        "operation_id": "search_operation_001", "vendor": "youtube", "query": marker, "max_results": 5,
    })
    assert invalid.status_code == 422
    assert invalid.headers["cache-control"] == "private, no-store"
    assert marker not in invalid.text

    class BrokenConnector(_Connector):
        def search(self, query: str, *, max_results: int):
            raise XApiError("X API returned an invalid response")

    monkeypatch.setattr(subject, "resolve_tool_connection", lambda *_args, **_kwargs: BrokenConnector())
    unavailable = client.post("/research/tools/search", json={
        "operation_id": "search_operation_002", "vendor": "youtube", "query": "private", "max_results": 5,
    })
    assert unavailable.status_code == 503
    assert unavailable.headers["cache-control"] == "private, no-store"
    conflict = client.post("/research/tools/search", json={
        "operation_id": "search_operation_002", "vendor": "youtube", "query": "private", "max_results": 5,
    })
    assert conflict.status_code == 409
    assert conflict.headers["cache-control"] == "private, no-store"


# ---------------------------------------------------------------------------
# The vendor paths, driven through the REAL connectors over MockTransport.
#
# The fakes above stand in for a resolved connector's RETURN shape; these tests
# resolve through the real registry instead, so a connector that stops
# answering the call the route makes (a rename, a re-shaped return) fails here
# rather than in production. No network: each connector gets an httpx client
# over MockTransport plus a temp-dir governor / quota meter.
# ---------------------------------------------------------------------------

_X_BEARER = "x-valid-bearer-token-0123456789abcdef"
_YT_KEY = "AIza" + "a" * 24
_TEST_KEY_BYTES = b"0" * nacl.secret.SecretBox.KEY_SIZE

_YT_VIDEO_ITEM = {
    "kind": "youtube#searchResult",
    "etag": "e1",
    "id": {"kind": "youtube#video", "videoId": "dQw4w9WgXcQ"},
    "snippet": {
        "publishedAt": "2026-08-14T17:00:00Z",
        "channelId": "UC_lab",
        "title": "Solid-state batteries, explained",
        "description": "A lecture on sulfide electrolytes.",
        "channelTitle": "Battery Lab",
        "thumbnails": {"default": {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg"}},
    },
}


def _vendor_send(monkeypatch, tmp_path, vendor: str, handler, *, owner: str = "owner-a"):
    """A TestClient whose route resolves the REAL connector for ``vendor``.

    The registry seam is wrapped rather than replaced: ``resolve_tool_connection``
    runs for real (so the vendor → connector map is exercised) with the test's
    transport and a temp state dir injected. One fresh connector per call, so a
    test can model a quota reset or a reopened rate window by moving
    ``state["dir"]`` between attempts.
    """
    monkeypatch.setenv("ANTIEK_TOOL_SEARCH_JOURNAL", str(tmp_path / "journal.sqlite3"))
    monkeypatch.setenv("ANTIEK_TOOL_CONNECTIONS_PATH", str(tmp_path / "connections.json"))
    artifact = str(tmp_path / "credentials.enc")
    connect_tool(
        owner,
        vendor,
        _X_BEARER if vendor == "x" else _YT_KEY,
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
    )
    state: dict = {"dir": str(tmp_path / "meter"), "connectors": []}

    def resolve(owner_user_id, vendor_name, **kwargs):
        connector = real_resolve_tool_connection(
            owner_user_id,
            vendor_name,
            artifact_path=artifact,
            key_bytes=_TEST_KEY_BYTES,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            state_dir=state["dir"],
            **kwargs,
        )
        state["connectors"].append(connector)
        return connector

    monkeypatch.setattr(subject, "resolve_tool_connection", resolve)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user_id = owner
        request.state.auth_method = "antiek_session_cookie"
        return await call_next(request)

    subject.register_research_tool_search_routes(app)
    return TestClient(app), state


def test_x_search_returns_candidates_from_a_real_connector(monkeypatch, tmp_path):
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={
            "data": [
                {"id": "1812345678901234567", "text": "Grid storage pilot results",
                 "author_id": "42", "created_at": "2026-08-30T11:02:00.000Z",
                 "conversation_id": "1812345678901234567"},
                {"id": "1812345678901234568", "text": "Second result",
                 "author_id": "43", "created_at": "2026-08-29T09:00:00.000Z"},
            ],
            "includes": {"users": [
                {"id": "42", "username": "gridwatcher", "verified": True},
                {"id": "43", "username": "cellchem"},
            ]},
        })

    client, _state = _vendor_send(monkeypatch, tmp_path, "x", handler)
    response = client.post("/research/tools/search", json={
        "operation_id": "x_operation_0001", "vendor": "x",
        "query": "grid storage", "max_results": 10,
    })

    assert response.status_code == 200, response.text
    assert response.json()["candidates"] == [
        {"external_id": "1812345678901234567",
         "title_or_text": "Grid storage pilot results",
         "url": "https://x.com/gridwatcher/status/1812345678901234567",
         "published_at": "2026-08-30T11:02:00.000Z",
         "author": "gridwatcher"},
        {"external_id": "1812345678901234568",
         "title_or_text": "Second result",
         "url": "https://x.com/cellchem/status/1812345678901234568",
         "published_at": "2026-08-29T09:00:00.000Z",
         "author": "cellchem"},
    ]
    assert [request.url.path for request in sent] == ["/2/tweets/search/recent"]
    assert sent[0].url.params["query"] == "grid storage"
    # The bearer rides the Authorization header only.
    assert sent[0].headers["authorization"] == f"Bearer {_X_BEARER}"
    assert _X_BEARER not in str(sent[0].url)


def test_youtube_search_spends_quota_and_returns_candidates(monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/youtube/v3/search"
        assert request.url.params["q"] == "solid state batteries"
        return httpx.Response(200, json={
            "kind": "youtube#searchListResponse",
            "etag": "etag-1",
            "regionCode": "US",
            "pageInfo": {"totalResults": 2, "resultsPerPage": 2},
            "items": [
                _YT_VIDEO_ITEM,
                {"kind": "youtube#searchResult", "etag": "e2",
                 "id": {"kind": "youtube#channel", "channelId": "UC_lab"},
                 "snippet": {"publishedAt": "2026-07-02T08:30:00Z", "channelId": "UC_lab",
                             "title": "Battery Lab", "description": "Channel.",
                             "channelTitle": "Battery Lab"}},
            ],
        })

    client, state = _vendor_send(monkeypatch, tmp_path, "youtube", handler)
    response = client.post("/research/tools/search", json={
        "operation_id": "yt_operation_0001", "vendor": "youtube",
        "query": "solid state batteries", "max_results": 10,
    })

    assert response.status_code == 200, response.text
    assert response.json()["candidates"] == [
        {"external_id": "dQw4w9WgXcQ",
         "title_or_text": "Solid-state batteries, explained",
         "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
         "published_at": "2026-08-14T17:00:00Z",
         "author": "Battery Lab"},
        {"external_id": "UC_lab",
         "title_or_text": "Battery Lab",
         "url": "https://www.youtube.com/channel/UC_lab",
         "published_at": "2026-07-02T08:30:00Z",
         "author": "Battery Lab"},
    ]
    # These two rows are what the 100-unit search.list reservation bought.
    assert state["connectors"][0].quota_remaining().remaining == 10_000 - 100


def test_vendor_quota_403_does_not_poison_the_operation_id(monkeypatch, tmp_path):
    sends = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        sends["n"] += 1
        if sends["n"] == 1:
            return httpx.Response(403, json={"error": {
                "code": 403,
                "message": "Quota exceeded",
                "errors": [{
                    "domain": "youtube.quota",
                    "reason": "quotaExceeded",
                    "message": "The request cannot be completed because you have "
                               "exceeded your quota.",
                }],
            }})
        return httpx.Response(200, json={"items": [_YT_VIDEO_ITEM]})

    client, state = _vendor_send(monkeypatch, tmp_path, "youtube", handler)
    body = {"operation_id": "yt_operation_0002", "vendor": "youtube",
            "query": "solid state batteries", "max_results": 10}

    exhausted = client.post("/research/tools/search", json=body)
    assert exhausted.status_code == 429, exhausted.text

    # Same vendor-day: the meter refuses locally, without a second vendor send —
    # and still without burning the operation.
    still_exhausted = client.post("/research/tools/search", json=body)
    assert still_exhausted.status_code == 429, still_exhausted.text

    # Quota reset (a fresh meter). The same operation_id must now run for real
    # instead of answering 409 from a poisoned journal entry.
    state["dir"] = str(tmp_path / "meter_after_reset")
    after_reset = client.post("/research/tools/search", json=body)
    assert after_reset.status_code == 200, after_reset.text
    assert after_reset.json()["status"] == "completed"
    assert len(after_reset.json()["candidates"]) == 1
    assert sends["n"] == 2


def test_x_rate_limit_releases_the_operation_id(monkeypatch, tmp_path):
    sends = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        sends["n"] += 1
        if sends["n"] == 1:
            return httpx.Response(
                429,
                json={"title": "Too Many Requests", "detail": "Rate limit exceeded"},
                headers={"Retry-After": "900"},
            )
        return httpx.Response(200, json={
            "data": [{"id": "1812345678901234569", "text": "Back online",
                      "author_id": "42", "created_at": "2026-09-01T10:00:00.000Z"}],
            "includes": {"users": [{"id": "42", "username": "gridwatcher"}]},
        })

    client, state = _vendor_send(monkeypatch, tmp_path, "x", handler)
    body = {"operation_id": "x_operation_0002", "vendor": "x",
            "query": "grid storage", "max_results": 10}

    limited = client.post("/research/tools/search", json=body)
    assert limited.status_code == 429, limited.text

    # Inside the governor's ban window: refused before the send, still retriable.
    banned = client.post("/research/tools/search", json=body)
    assert banned.status_code == 429, banned.text

    # The window reopens (a fresh governor). Same operation_id, real send.
    state["dir"] = str(tmp_path / "gov_after_window")
    after_window = client.post("/research/tools/search", json=body)
    assert after_window.status_code == 200, after_window.text
    assert after_window.json()["candidates"][0]["external_id"] == "1812345678901234569"
    assert sends["n"] == 2
