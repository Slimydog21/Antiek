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
from runtime.connectors.base import RateSpec
from runtime.connectors.quota_meter import QuotaMeter
from runtime.connectors.rate_governor import VendorRateGovernor
from runtime.connectors.x_twitter import XTwitterConnector
from runtime.connectors.youtube import YouTubeDataConnector


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
# End-to-end over the connectors the route actually resolves.
#
# The fakes above model a connector that already returns parsed rows, which is
# why a route calling a method no connector defines still passed CI. These
# drive the real ``runtime.connectors`` classes over ``httpx.MockTransport``
# (no network), so a rename or a return-shape change breaks the test.
# ---------------------------------------------------------------------------

_TEST_KEY_BYTES = b"0" * nacl.secret.SecretBox.KEY_SIZE
_X_BEARER = "x-valid-bearer-token-0123456789abcdef"
_YT_KEY = "AIza" + "a" * 24

# One realistic ``GET /2/tweets/search/recent`` page: the tweet objects carry
# ``id``/``author_id``, and the handle lives in the ``includes.users``
# expansion, never inline on the tweet.
_X_SEARCH_PAGE = {
    "data": [
        {
            "id": "1799999999999999999",
            "text": "New fusion first-wall materials paper is worth your afternoon.",
            "author_id": "44196397",
            "created_at": "2026-08-12T09:30:00.000Z",
            "conversation_id": "1799999999999999999",
        },
        {
            "id": "1799999999999999998",
            "text": "Second hit.",
            "author_id": "44196397",
            "created_at": "2026-08-12T09:31:00.000Z",
            "conversation_id": "1799999999999999998",
        },
    ],
    "includes": {
        "users": [{"id": "44196397", "username": "labnotes", "name": "Lab Notes"}]
    },
    "meta": {"result_count": 2, "newest_id": "1799999999999999999"},
}

# One realistic ``GET /youtube/v3/search`` page: the id is nested under
# ``id.videoId`` keyed by ``id.kind``, and the human fields live under
# ``snippet``.
_YT_SEARCH_PAGE = {
    "kind": "youtube#searchListResponse",
    "pageInfo": {"totalResults": 1, "resultsPerPage": 1},
    "items": [
        {
            "kind": "youtube#searchResult",
            "id": {"kind": "youtube#video", "videoId": "dQw4w9WgXcQ"},
            "snippet": {
                "publishedAt": "2026-07-01T12:00:00Z",
                "channelId": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
                "title": "Fusion first-wall materials, explained",
                "description": "A walkthrough of the tungsten armour trade space.",
                "channelTitle": "Lab Notes",
            },
        }
    ],
}

_YT_QUOTA_403 = {
    "error": {
        "code": 403,
        "message": "The request cannot be completed because you have exceeded your quota.",
        "errors": [
            {
                "domain": "youtube.quota",
                "reason": "quotaExceeded",
                "message": "The request cannot be completed because you have exceeded your quota.",
            }
        ],
    }
}


def _x_connector(handler, tmp_path, name: str = "x") -> XTwitterConnector:
    """A real X connector with a live-shaped key, pinned to a mock transport."""
    state = tmp_path / f"gov-{name}"
    state.mkdir(parents=True, exist_ok=True)
    conn = XTwitterConnector(
        artifact_path=str(tmp_path / f"cred-{name}.enc"),
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        governor=VendorRateGovernor(
            "x", RateSpec(max_calls=25, window_s=900.0), state_dir=str(state)
        ),
    )
    conn.attach_key(_X_BEARER)
    return conn


def _youtube_connector(handler, tmp_path, name: str = "yt") -> YouTubeDataConnector:
    """A real YouTube connector on its own quota day (one meter per name)."""
    conn = YouTubeDataConnector(
        artifact_path=str(tmp_path / f"cred-{name}.enc"),
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        meter=QuotaMeter("youtube", state_dir=str(tmp_path / f"quota-{name}"), reset_tz="UTC"),
    )
    conn.attach_key(_YT_KEY)
    return conn


def _app(monkeypatch, tmp_path, resolver, *, owner: str = "owner-a") -> TestClient:
    monkeypatch.setenv("ANTIEK_TOOL_SEARCH_JOURNAL", str(tmp_path / "journal.sqlite3"))
    monkeypatch.setattr(subject, "resolve_tool_connection", resolver)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user_id = owner
        request.state.auth_method = "antiek_session_cookie"
        return await call_next(request)

    subject.register_research_tool_search_routes(app)
    return TestClient(app)


def test_x_search_yields_candidates_through_the_real_connector(monkeypatch, tmp_path):
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/2/tweets/search/recent"
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=_X_SEARCH_PAGE)

    connector = _x_connector(handler, tmp_path)
    client = _app(monkeypatch, tmp_path, lambda *_a, **_k: connector)
    response = client.post("/research/tools/search", json={
        "operation_id": "search_operation_x01",
        "vendor": "x",
        "query": "fusion materials",
        "max_results": 5,
    })

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candidates"] == [
        {
            "external_id": "1799999999999999999",
            "title_or_text": "New fusion first-wall materials paper is worth your afternoon.",
            "url": "https://x.com/labnotes/status/1799999999999999999",
            "published_at": "2026-08-12T09:30:00.000Z",
            "author": "labnotes",
        },
        {
            "external_id": "1799999999999999998",
            "title_or_text": "Second hit.",
            "url": "https://x.com/labnotes/status/1799999999999999998",
            "published_at": "2026-08-12T09:31:00.000Z",
            "author": "labnotes",
        },
    ]
    assert seen[0]["query"] == "fusion materials"
    assert seen[0]["max_results"] == "5"


def test_youtube_search_yields_candidates_for_the_quota_it_spends(monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/youtube/v3/search"
        return httpx.Response(200, json=_YT_SEARCH_PAGE)

    connector = _youtube_connector(handler, tmp_path)
    client = _app(monkeypatch, tmp_path, lambda *_a, **_k: connector)
    response = client.post("/research/tools/search", json={
        "operation_id": "search_operation_yt01",
        "vendor": "youtube",
        "query": "fusion materials",
        "max_results": 5,
    })

    assert response.status_code == 200, response.text
    assert response.json()["candidates"] == [{
        "external_id": "dQw4w9WgXcQ",
        "title_or_text": "Fusion first-wall materials, explained",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "published_at": "2026-07-01T12:00:00Z",
        "author": "Lab Notes",
    }]
    # The 100 units search.list costs were really spent; a call that spends
    # them and returns nothing is the silent failure this pins.
    assert connector.quota_remaining().remaining == 10_000 - 100


def test_vendor_quota_403_leaves_the_operation_retriable(monkeypatch, tmp_path):
    """A 403 ``quotaExceeded`` must not burn the operation_id.

    The vendor refused and produced nothing; the condition clears on its own
    at the next quota reset. The second attempt here reuses the SAME
    operation_id against a connector on a fresh quota day — the reset the user
    waited for — and must run for real instead of answering 409 from a
    poisoned journal row.
    """
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json=_YT_QUOTA_403)

    def serve(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_YT_SEARCH_PAGE)

    connectors = [
        _youtube_connector(refuse, tmp_path, name="day1"),
        _youtube_connector(serve, tmp_path, name="day2"),
    ]
    client = _app(monkeypatch, tmp_path, lambda *_a, **_k: connectors.pop(0))
    body = {
        "operation_id": "search_operation_yt02",
        "vendor": "youtube",
        "query": "fusion materials",
        "max_results": 5,
    }

    refused = client.post("/research/tools/search", json=body)
    assert refused.status_code == 429, refused.text

    after_reset = client.post("/research/tools/search", json=body)
    assert after_reset.status_code == 200, after_reset.text
    assert after_reset.json()["status"] == "completed"
    assert after_reset.json()["candidates"][0]["external_id"] == "dQw4w9WgXcQ"


def test_local_quota_refusal_leaves_the_operation_retriable(monkeypatch, tmp_path):
    """The meter refusing before any send is retriable for the same reason.

    ``check_and_reserve`` raises before a request is built, so the vendor never
    saw the operation at all. Burning the journal row there strands an
    operation nothing ever performed.
    """
    def serve(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_YT_SEARCH_PAGE)

    exhausted = _youtube_connector(serve, tmp_path, name="dry")
    exhausted.meter.mark_exhausted()
    fresh = _youtube_connector(serve, tmp_path, name="wet")
    connectors = [exhausted, fresh]
    client = _app(monkeypatch, tmp_path, lambda *_a, **_k: connectors.pop(0))
    body = {
        "operation_id": "search_operation_yt03",
        "vendor": "youtube",
        "query": "fusion materials",
        "max_results": 5,
    }

    refused = client.post("/research/tools/search", json=body)
    assert refused.status_code == 429, refused.text

    after_reset = client.post("/research/tools/search", json=body)
    assert after_reset.status_code == 200, after_reset.text
    assert after_reset.json()["candidates"][0]["external_id"] == "dQw4w9WgXcQ"


def test_rate_limited_x_search_leaves_the_operation_retriable(monkeypatch, tmp_path):
    """A 429 and the ban sentinel it writes both release the operation_id.

    X answers the first send 429, and the governor records a ``banned_until``
    from it, so the second attempt raises ``VendorBanned`` before any send —
    two different exception types on one user-visible condition. Both mean the
    vendor performed no search, so both must answer 429 and leave the row
    unclaimed; marking either one ``unknown`` would stand the operation_id
    behind a 409 long after the window reopened. The third attempt is that
    reopening, and it must run for real.
    """
    sends = 0

    def refuse(request: httpx.Request) -> httpx.Response:
        nonlocal sends
        sends += 1
        return httpx.Response(429, json={"title": "Too Many Requests"}, headers={"retry-after": "900"})

    def serve(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_X_SEARCH_PAGE)

    limited = _x_connector(refuse, tmp_path, name="limited")
    reopened = _x_connector(serve, tmp_path, name="reopened")
    connectors = [limited, limited, reopened]
    client = _app(monkeypatch, tmp_path, lambda *_a, **_k: connectors.pop(0))
    body = {
        "operation_id": "search_operation_x02",
        "vendor": "x",
        "query": "fusion materials",
        "max_results": 5,
    }

    first = client.post("/research/tools/search", json=body)
    assert first.status_code == 429, first.text
    assert first.json()["detail"] == "tool search is rate limited"

    banned = client.post("/research/tools/search", json=body)
    assert banned.status_code == 429, banned.text
    # The governor refused before building a request, so X was never asked twice.
    assert sends == 1

    after_window = client.post("/research/tools/search", json=body)
    assert after_window.status_code == 200, after_window.text
    assert after_window.json()["status"] == "completed"
    assert after_window.json()["candidates"][0]["external_id"] == "1799999999999999999"


# ── SPR-04 task 5: POST /research/tools/ingest ─────────────────────────────
#
# A connected-tool candidate is ingested with the owner's own key: the route
# fetches the single item through the resolved connector (stubbed here at the
# HTTP layer) and hands it to the EXISTING acquisition adapter with
# content_class=personal_reading. The adapters are recorders so no graph is
# opened; what these tests pin is what the route passes them.

import sqlite3  # noqa: E402

from acquisition.twitter.adapter import IngestTwitterResult, TwitterThread  # noqa: E402
from acquisition.youtube.adapter import IngestYouTubeResult  # noqa: E402
from substrate.constants import PERSONAL_READING_CONTENT_CLASS  # noqa: E402

_VIDEO_ID = "dQw4w9WgXcQ"
_TWEET_ID = "1790000000000000001"


def _videos_handler(calls: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/youtube/v3/videos"
        calls.append(request.url.params["id"])
        return httpx.Response(200, json={"items": [{
            "id": request.url.params["id"],
            "snippet": {
                "title": "Solid-state battery lecture",
                "channelTitle": "Materials Lab",
                "description": "A long description.",
                "publishedAt": "2026-08-12T00:00:00Z",
            },
            "contentDetails": {"duration": "PT45M"},
        }]})
    return handler


def _tweet_handler(calls: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={
            "data": {"id": _TWEET_ID, "text": "Worth reading", "author_id": "7",
                     "created_at": "2026-08-12T10:00:00.000Z", "conversation_id": _TWEET_ID},
            "includes": {"users": [{"id": "7", "username": "labnotes", "verified": False}]},
        })
    return handler


class _Recorder:
    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result(*args, **kwargs) if callable(self.result) else self.result


def _no_captions(monkeypatch) -> None:
    import acquisition.youtube.client as yt_client

    monkeypatch.setattr(yt_client, "_fetch_transcript", lambda _vid: ([], "missing"))
    yt_client.reset_youtube_fetch_counter()


def _youtube_recorder() -> _Recorder:
    return _Recorder(lambda _url, **kw: IngestYouTubeResult(
        document_id=f"doc-yt-{kw['video'].video_id}",
        video_id=kw["video"].video_id,
        chunks_written=3,
        title=kw["video"].title,
        content_class=kw.get("content_class"),
    ))


def _ingest_rows(tmp_path, operation_id: str) -> int:
    with sqlite3.connect(tmp_path / "journal.sqlite3") as con:
        return int(con.execute(
            "SELECT COUNT(*) FROM ingests WHERE operation_id=?", (operation_id,)
        ).fetchone()[0])


def test_tools_ingest_replays_one_document_id_per_operation_id(monkeypatch, tmp_path):
    _no_captions(monkeypatch)
    fetched: list[str] = []
    connector = _youtube_connector(_videos_handler(fetched), tmp_path)
    resolved: list[tuple] = []

    def resolver(*args, **_kwargs):
        resolved.append(args)
        return connector

    adapter = _youtube_recorder()
    monkeypatch.setattr(subject, "ingest_youtube", adapter)
    client = _app(monkeypatch, tmp_path, resolver)
    body = {"operation_id": "ingest_operation_001", "vendor": "youtube", "external_id": _VIDEO_ID}

    first = client.post("/research/tools/ingest", json=body)
    second = client.post("/research/tools/ingest", json=body)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["status"] == "completed"
    assert second.json()["status"] == "replayed"
    assert first.json()["document_id"] == second.json()["document_id"] == f"doc-yt-{_VIDEO_ID}"
    assert first.json()["ingest_status"] == "ingested"
    assert first.headers["cache-control"] == "private, no-store"
    # One vendor fetch, one adapter call, one journal row: the replay bought nothing.
    assert fetched == [_VIDEO_ID]
    assert len(adapter.calls) == 1
    assert resolved == [("owner-a", "youtube")]
    assert _ingest_rows(tmp_path, "ingest_operation_001") == 1
    # The metadata the adapter ingested came through the owner's key.
    video = adapter.calls[0][1]["video"]
    assert video.title == "Solid-state battery lecture"
    assert video.channel == "Materials Lab"
    assert video.duration_seconds == 2700


def test_tools_ingest_attaches_personal_reading_content_class(monkeypatch, tmp_path):
    # YouTube: the owner's key fetches the video, the adapter gets the class.
    _no_captions(monkeypatch)
    yt_adapter = _youtube_recorder()
    monkeypatch.setattr(subject, "ingest_youtube", yt_adapter)
    yt_client = _app(
        monkeypatch, tmp_path,
        lambda *_a, **_k: _youtube_connector(_videos_handler([]), tmp_path, "yt-class"),
    )
    yt = yt_client.post("/research/tools/ingest", json={
        "operation_id": "ingest_operation_yt1", "vendor": "youtube", "external_id": _VIDEO_ID,
    })
    assert yt.status_code == 200, yt.text
    kwargs = yt_adapter.calls[0][1]
    # .get, not [...]: a dropped argument must fail on the VALUE (None), not a KeyError.
    assert kwargs.get("content_class") == "personal_reading"
    assert kwargs.get("content_class") == PERSONAL_READING_CONTENT_CLASS
    assert kwargs["source_tier"] == 4
    assert yt.json()["content_class"] == "personal_reading"

    # X: the owner's bearer fetches the post, the thread adapter gets the class.
    x_adapter = _Recorder(lambda thread, **_kw: IngestTwitterResult(
        document_id="doc-x-0123456789abcdef", chunks_written=1, title="Worth reading",
    ))
    monkeypatch.setattr(subject, "ingest_twitter_thread", x_adapter)
    x_fetched: list[str] = []
    x_client = _app(
        monkeypatch, tmp_path,
        lambda *_a, **_k: _x_connector(_tweet_handler(x_fetched), tmp_path, "x-class"),
    )
    x = x_client.post("/research/tools/ingest", json={
        "operation_id": "ingest_operation_x01", "vendor": "x", "external_id": _TWEET_ID,
    })
    assert x.status_code == 200, x.text
    (thread,), x_kwargs = x_adapter.calls[0]
    # .get, not [...]: a dropped argument must fail on the VALUE (None), not a KeyError.
    assert x_kwargs.get("content_class") == "personal_reading"
    assert x_kwargs.get("content_class") == PERSONAL_READING_CONTENT_CLASS
    assert x_kwargs["source_tier"] == 4
    assert isinstance(thread, TwitterThread)
    assert thread.root_tweet_id == _TWEET_ID
    assert thread.author_handle == "labnotes"
    assert thread.tweets[0].text == "Worth reading"
    assert x_fetched == [f"/2/tweets/{_TWEET_ID}"]


def test_tools_ingest_rejects_malformed_external_id_without_echo(monkeypatch, tmp_path):
    def resolver(*_a, **_k):
        raise AssertionError("the resolver must not be reached")

    client = _app(monkeypatch, tmp_path, resolver)
    for vendor, bad in (("youtube", "PRIVATE-MARKER"), ("x", "PRIVATE-MARKER")):
        response = client.post("/research/tools/ingest", json={
            "operation_id": "ingest_operation_bad", "vendor": vendor, "external_id": bad,
        })
        assert response.status_code == 422
        assert "PRIVATE-MARKER" not in response.text


def test_tools_ingest_not_found_releases_the_operation(monkeypatch, tmp_path):
    _no_captions(monkeypatch)
    sends: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sends.append(request.url.params["id"])
        return httpx.Response(200, json={"items": []})

    adapter = _youtube_recorder()
    monkeypatch.setattr(subject, "ingest_youtube", adapter)
    client = _app(
        monkeypatch, tmp_path,
        lambda *_a, **_k: _youtube_connector(handler, tmp_path, "yt-missing"),
    )
    body = {"operation_id": "ingest_operation_404", "vendor": "youtube", "external_id": _VIDEO_ID}
    first = client.post("/research/tools/ingest", json=body)
    retry = client.post("/research/tools/ingest", json=body)
    assert first.status_code == 404
    assert retry.status_code == 404
    assert _VIDEO_ID not in first.text
    assert sends == [_VIDEO_ID, _VIDEO_ID]  # released, so the retry reached the vendor
    assert adapter.calls == []


def test_tools_ingest_adapter_failure_is_unresolved_not_retried(monkeypatch, tmp_path):
    _no_captions(monkeypatch)
    fetched: list[str] = []

    def failing(*_a, **_k):
        raise ValueError("graph write failed")

    monkeypatch.setattr(subject, "ingest_youtube", _Recorder(failing))
    client = _app(
        monkeypatch, tmp_path,
        lambda *_a, **_k: _youtube_connector(_videos_handler(fetched), tmp_path, "yt-fail"),
    )
    body = {"operation_id": "ingest_operation_err", "vendor": "youtube", "external_id": _VIDEO_ID}
    first = client.post("/research/tools/ingest", json=body)
    again = client.post("/research/tools/ingest", json=body)
    assert first.status_code == 503
    assert "graph write failed" not in first.text
    assert again.status_code == 409  # a paid fetch with an unknown outcome is not re-sent
    assert fetched == [_VIDEO_ID]
