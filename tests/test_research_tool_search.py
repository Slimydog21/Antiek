from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from acquisition.twitter.api_client import XApiError
from interfaces.research.api import research_tool_search as subject


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
