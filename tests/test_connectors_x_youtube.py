"""Tests for runtime-level X + YouTube connectors (BYO-tools v1).

Coverage:
  (a) Key validation via mocked httpx — X ``/2/users/me`` and YouTube
      ``/youtube/v3/videos`` succeed on 200 and raise on non-200.
  (b) Search wrappers — X ``/tweets/search/recent`` and YouTube ``/search``
      return parsed items.
  (c) Rate governor / quota meter flow — X routes through the governor;
      YouTube reserves + releases quota units.
  (d) Registry round-trip — connect_tool → resolve_tool_connection returns the
      new runtime connector classes with the right vendor + cred_id.
  (e) Secret hygiene — no plaintext key in repr, error messages, or URL.

All offline: byok artifact/key-file redirected to tmp, httpx over
``MockTransport`` (no network).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import nacl.secret
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.connectors.registry import (  # noqa: E402
    connect_tool,
    disconnect_tool,
    list_tool_connections,
    resolve_tool_connection,
)
from runtime.connectors.x_twitter import (  # noqa: E402
    SEARCH_MAX_RESULTS,
    X_POST_READ_USD,
    XTwitterConnector,
    XTwitterError,
    XTwitterKeyRequired,
    estimated_search_cost_usd,
)
from runtime.connectors.youtube import (  # noqa: E402
    YouTubeDataConnector,
    YouTubeError,
    YouTubeKeyRequired,
)

_TEST_KEY_BYTES = b"0" * nacl.secret.SecretBox.KEY_SIZE
_X_BEARER = "x-valid-bearer-token-0123456789abcdef"
_YT_KEY = "AIza" + "a" * 24


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def artifact(tmp_path: Path) -> str:
    return str(tmp_path / "credentials.enc")


def _mock_transport(handler):
    """Build an httpx.MockTransport from a handler function."""
    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# (a) X key validation
# ---------------------------------------------------------------------------

def test_x_validate_key_success(artifact: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/2/users/me"
        auth = request.headers.get("authorization", "")
        assert auth == f"Bearer {_X_BEARER}"
        return httpx.Response(
            200,
            json={"data": {"id": "12345", "name": "Test User", "username": "test"}},
        )

    conn = XTwitterConnector(
        cred_id=None,
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        governor=_fake_governor(tmp_dir="/tmp/unused"),
    )
    cred_id = conn.attach_key(_X_BEARER)
    assert cred_id is not None
    result = conn.validate_key()
    assert result["username"] == "test"
    conn.close()


def test_x_validate_key_failure(artifact: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid token"})

    conn = XTwitterConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        governor=_fake_governor(tmp_dir="/tmp/unused2"),
    )
    conn.attach_key(_X_BEARER)
    with pytest.raises(XTwitterError) as exc_info:
        conn.validate_key()
    assert exc_info.value.status_code == 401
    assert _X_BEARER not in str(exc_info.value)
    conn.close()


def test_x_keyless_refuses_validate(artifact: str) -> None:
    conn = XTwitterConnector(artifact_path=artifact, key_bytes=_TEST_KEY_BYTES)
    with pytest.raises(XTwitterKeyRequired):
        conn.validate_key()


# ---------------------------------------------------------------------------
# (b) X search wrapper
# ---------------------------------------------------------------------------

def test_x_search_tweets(artifact: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/2/tweets/search/recent"
        params = dict(request.url.params)
        assert params["query"] == "AI agents"
        return httpx.Response(
            200,
            json={"data": [{"id": "1", "text": "hello"}, {"id": "2", "text": "world"}]},
        )

    conn = XTwitterConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        governor=_fake_governor(tmp_dir="/tmp/unused3"),
    )
    conn.attach_key(_X_BEARER)
    tweets = conn.search_tweets("AI agents", max_results=10)
    assert len(tweets) == 2
    assert tweets[0]["text"] == "hello"
    conn.close()


# ---------------------------------------------------------------------------
# (c) YouTube key validation
# ---------------------------------------------------------------------------

def test_youtube_validate_key_success(artifact: str, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/youtube/v3/videos"
        params = dict(request.url.params)
        assert params["part"] == "id"
        assert params["chart"] == "mostPopular"
        assert params["maxResults"] == "1"
        assert params["key"] == _YT_KEY
        return httpx.Response(200, json={"items": [{"id": "dQw4w9WgXcQ"}]})

    conn = YouTubeDataConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        meter=_fake_meter(tmp_path / "quota"),
    )
    conn.attach_key(_YT_KEY)
    result = conn.validate_key()
    assert result["items"][0]["id"] == "dQw4w9WgXcQ"
    # validate_key costs 1 unit (videos.list)
    remaining = conn.quota_remaining()
    assert remaining.remaining == 10000 - 1
    conn.close()


def test_youtube_validate_key_failure(artifact: str, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"errors": [{"reason": "badRequest"}]}})

    conn = YouTubeDataConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        meter=_fake_meter(tmp_path / "quota2"),
    )
    conn.attach_key(_YT_KEY)
    with pytest.raises(YouTubeError) as exc_info:
        conn.validate_key()
    assert exc_info.value.status_code == 403
    assert _YT_KEY not in str(exc_info.value)
    # The hold was released on failure
    assert conn.quota_remaining().remaining == 10000
    conn.close()


def test_youtube_keyless_refuses_validate(artifact: str) -> None:
    conn = YouTubeDataConnector(artifact_path=artifact, key_bytes=_TEST_KEY_BYTES)
    with pytest.raises(YouTubeKeyRequired):
        conn.validate_key()


# ---------------------------------------------------------------------------
# YouTube search wrapper + quota flow
# ---------------------------------------------------------------------------

def test_youtube_search_reserves_quota(artifact: str, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/youtube/v3/search"
        return httpx.Response(
            200,
            json={"items": [{"id": {"videoId": "v1"}, "snippet": {"title": "Test"}}]},
        )

    conn = YouTubeDataConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        meter=_fake_meter(tmp_path / "quota3"),
    )
    conn.attach_key(_YT_KEY)
    items = conn.search("machine learning", max_results=5)
    assert len(items) == 1
    # search.list costs 100 units
    assert conn.quota_remaining().remaining == 10000 - 100
    conn.close()


def test_youtube_search_failure_releases_quota(artifact: str, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "server error"})

    conn = YouTubeDataConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        meter=_fake_meter(tmp_path / "quota4"),
    )
    conn.attach_key(_YT_KEY)
    with pytest.raises(YouTubeError):
        conn.search("test query")
    # 100 units were reserved then released on failure
    assert conn.quota_remaining().remaining == 10000
    conn.close()


# ---------------------------------------------------------------------------
# (e) Secret hygiene
# ---------------------------------------------------------------------------

def test_x_repr_has_no_key(artifact: str) -> None:
    conn = XTwitterConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(lambda r: httpx.Response(200, json={}))),
        governor=_fake_governor(tmp_dir="/tmp/unused4"),
    )
    conn.attach_key(_X_BEARER)
    rendered = repr(conn) + str(conn)
    assert _X_BEARER not in rendered
    conn.close()


def test_youtube_repr_has_no_key(artifact: str) -> None:
    conn = YouTubeDataConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(lambda r: httpx.Response(200, json={}))),
    )
    conn.attach_key(_YT_KEY)
    rendered = repr(conn) + str(conn)
    assert _YT_KEY not in rendered
    conn.close()


# ---------------------------------------------------------------------------
# (d) Registry round-trip
# ---------------------------------------------------------------------------

@pytest.fixture
def registry_paths(tmp_path: Path, monkeypatch):
    registry = tmp_path / "tool_connections.json"
    artifact = tmp_path / "credentials.enc"
    monkeypatch.setenv("ANTIEK_TOOL_CONNECTIONS_PATH", str(registry))
    return str(registry), str(artifact)


def test_registry_roundtrip_x(registry_paths) -> None:
    _, artifact = registry_paths
    connect_tool("user-a", "x", _X_BEARER, artifact_path=artifact, key_bytes=_TEST_KEY_BYTES)
    connector = resolve_tool_connection("user-a", "x", artifact_path=artifact, key_bytes=_TEST_KEY_BYTES)
    assert isinstance(connector, XTwitterConnector)
    assert connector.descriptor.vendor == "x"
    assert connector.cred_id is not None
    assert _X_BEARER not in repr(connector)
    connector.close()


def test_registry_roundtrip_youtube(registry_paths) -> None:
    _, artifact = registry_paths
    connect_tool("user-a", "youtube", _YT_KEY, artifact_path=artifact, key_bytes=_TEST_KEY_BYTES)
    connector = resolve_tool_connection("user-a", "youtube", artifact_path=artifact, key_bytes=_TEST_KEY_BYTES)
    assert isinstance(connector, YouTubeDataConnector)
    assert connector.descriptor.vendor == "youtube"
    assert connector.cred_id is not None
    assert _YT_KEY not in repr(connector)
    connector.close()


def test_registry_disconnect(registry_paths) -> None:
    _, artifact = registry_paths
    connect_tool("user-a", "x", _X_BEARER, artifact_path=artifact, key_bytes=_TEST_KEY_BYTES)
    assert disconnect_tool("user-a", "x", artifact_path=artifact) is True
    rows = {r.vendor: r for r in list_tool_connections("user-a", artifact_path=artifact)}
    assert rows["x"].credential_present is False


# ---------------------------------------------------------------------------
# Fixtures for governor/meter
# ---------------------------------------------------------------------------

def _fake_governor(tmp_dir: str):
    """Build a VendorRateGovernor with a temp state dir."""
    import tempfile

    from runtime.connectors.base import RateSpec
    from runtime.connectors.rate_governor import VendorRateGovernor
    real_tmp = tempfile.mkdtemp()
    return VendorRateGovernor("x", RateSpec(max_calls=25, window_s=900.0), state_dir=real_tmp)


def _fake_meter(state_path: Path):
    """Build a QuotaMeter pinned to a temp state dir + UTC reset."""
    from runtime.connectors.quota_meter import QuotaMeter
    return QuotaMeter("youtube", state_dir=str(state_path), reset_tz="UTC")


# ---------------------------------------------------------------------------
# (f) Search return shapes — the seam the research-tool route reads
#
# Both connectors decode the vendor envelope here so the route never has to.
# A page whose ids and authors sit where the vendor really puts them (X keys a
# tweet by ``id`` and names the author only in ``includes.users``; YouTube
# nests the id under ``id.videoId`` keyed by ``id.kind``) must come back flat.
# ---------------------------------------------------------------------------

def test_x_search_flattens_tweets_and_joins_the_author_expansion(artifact: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        assert params["expansions"] == "author_id"
        assert params["user.fields"] == "username"
        return httpx.Response(200, json={
            "data": [
                {
                    "id": "1799999999999999999",
                    "text": "First hit.",
                    "author_id": "44196397",
                    "created_at": "2026-08-12T09:30:00.000Z",
                    "conversation_id": "1799999999999999999",
                },
                {
                    "id": "1799999999999999998",
                    "text": "Hit whose author X declined to expand.",
                    "author_id": "999",
                    "created_at": "2026-08-12T09:31:00.000Z",
                    "conversation_id": "1799999999999999998",
                },
            ],
            "includes": {"users": [{"id": "44196397", "username": "labnotes"}]},
            "meta": {"result_count": 2},
        })

    conn = XTwitterConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        governor=_fake_governor(tmp_dir="/tmp/unused5"),
    )
    conn.attach_key(_X_BEARER)
    tweets = conn.search_tweets("fusion materials", max_results=10)
    assert tweets == [
        {
            "tweet_id": "1799999999999999999",
            "text": "First hit.",
            "author_handle": "labnotes",
            "created_at": "2026-08-12T09:30:00.000Z",
            "conversation_id": "1799999999999999999",
        },
        {
            "tweet_id": "1799999999999999998",
            "text": "Hit whose author X declined to expand.",
            "author_handle": "",
            "created_at": "2026-08-12T09:31:00.000Z",
            "conversation_id": "1799999999999999998",
        },
    ]
    conn.close()


def test_youtube_search_parses_nested_ids_and_snippets(artifact: str, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "kind": "youtube#searchListResponse",
            "items": [
                {
                    "id": {"kind": "youtube#video", "videoId": "dQw4w9WgXcQ"},
                    "snippet": {
                        "publishedAt": "2026-07-01T12:00:00Z",
                        "channelId": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
                        "title": "Fusion first-wall materials, explained",
                        "description": "Tungsten armour trade space.",
                        "channelTitle": "Lab Notes",
                    },
                },
                {
                    "id": {"kind": "youtube#channel", "channelId": "UC_channel_1"},
                    "snippet": {"title": "A channel", "channelTitle": "A channel"},
                },
                {"id": {"kind": "youtube#video"}, "snippet": {"title": "No id at all"}},
            ],
        })

    conn = YouTubeDataConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        meter=_fake_meter(tmp_path / "quota5"),
    )
    conn.attach_key(_YT_KEY)
    hits = conn.search("fusion materials", max_results=5)
    assert [(h.video_id, h.kind) for h in hits] == [
        ("dQw4w9WgXcQ", "video"),
        ("UC_channel_1", "channel"),
    ]
    assert hits[0].title == "Fusion first-wall materials, explained"
    assert hits[0].channel_title == "Lab Notes"
    assert hits[0].published_at == "2026-07-01T12:00:00Z"
    conn.close()


def test_youtube_search_of_an_empty_page_is_empty(artifact: str, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"kind": "youtube#searchListResponse", "items": []})

    conn = YouTubeDataConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        meter=_fake_meter(tmp_path / "quota6"),
    )
    conn.attach_key(_YT_KEY)
    assert conn.search("nothing matches this", max_results=5) == []
    conn.close()


def test_youtube_hit_without_a_kind_takes_the_one_its_id_field_implies(
    artifact: str, tmp_path: Path
) -> None:
    """``id.kind`` missing must not silently make a channel look like a video.

    The route turns ``kind`` into the candidate's URL, so a channel id read as
    a video builds ``watch?v=<channel id>`` — a link that resolves to nothing
    and a control that looks like it worked. The id field the vendor did fill
    already says which kind it is.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [
            {"id": {"videoId": "v1"}, "snippet": {"title": "A video"}},
            {"id": {"channelId": "UC_no_kind"}, "snippet": {"title": "A channel"}},
            {"id": {"playlistId": "PL_no_kind"}, "snippet": {"title": "A playlist"}},
        ]})

    conn = YouTubeDataConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        meter=_fake_meter(tmp_path / "quota7"),
    )
    conn.attach_key(_YT_KEY)
    hits = conn.search("anything", max_results=5)
    assert [(h.video_id, h.kind) for h in hits] == [
        ("v1", "video"),
        ("UC_no_kind", "channel"),
        ("PL_no_kind", "playlist"),
    ]
    conn.close()


# ---------------------------------------------------------------------------
# (f) X cost model — pay-per-use credits, not a retired flat tier
# ---------------------------------------------------------------------------

def test_x_tool_quota_estimate_is_the_published_per_post_rate_times_the_page() -> None:
    """The estimate is arithmetic over a sourced rate, so pin the arithmetic.

    Asserted against literals rather than against ``X_POST_READ_USD`` itself:
    a test that recomputes the production constant moves with it and would
    stay green if someone changed the price, which is the one change this
    number must never absorb silently.
    """
    assert SEARCH_MAX_RESULTS == 25
    assert estimated_search_cost_usd(25) == 0.125
    assert estimated_search_cost_usd(1) == 0.005
    assert estimated_search_cost_usd(10) == 0.05
    # The default is the full page, because that is what the settings surface
    # quotes and the number a user needs is the worst case.
    assert estimated_search_cost_usd() == 0.125


def test_x_tool_quota_estimate_refuses_counts_the_connector_would_refuse() -> None:
    """An estimate for a call that cannot be made is a number with no meaning."""
    for bad in (0, -1, SEARCH_MAX_RESULTS + 1):
        with pytest.raises(ValueError):
            estimated_search_cost_usd(bad)


def test_x_tool_quota_source_carries_no_retired_flat_tier_reasoning() -> None:
    """X closed the flat 200-USD Basic tier to new signups on 2026-02-06.

    The connector reasoned in that tier's request-allowance terms, which is why
    the settings surface showed a ceiling where a price belonged. Guard the
    source text so the retired framing cannot creep back in a later edit.
    """
    import runtime.connectors.x_twitter as module

    source = Path(str(module.__file__)).read_text(encoding="utf-8")
    assert "450 req" not in source
    assert "app-rate budget" not in source
    assert "pay-per-use" in source
    # The rate must be stated with a source and a date it was read.
    assert "https://docs.x.com/x-api/getting-started/pricing" in source
    assert X_POST_READ_USD == 0.005


# ---------------------------------------------------------------------------
# (g) Single-item fetches — the seam /research/tools/ingest reads (SPR-04 task 5)
#
# Ingesting a candidate fetches that one item again with the owner's own key.
# YouTube's videos.list is 1 quota unit; X's GET /2/tweets/:id is one billed
# post read. A malformed id must be refused before either is spent.
# ---------------------------------------------------------------------------


def test_youtube_video_metadata_spends_one_unit_and_parses_snippet(
    artifact: str, tmp_path: Path
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.path == "/youtube/v3/videos"
        assert request.url.params["id"] == "dQw4w9WgXcQ"
        assert request.url.params["part"] == "snippet,contentDetails"
        return httpx.Response(
            200,
            json={"items": [{
                "id": "dQw4w9WgXcQ",
                "snippet": {
                    "title": "A lecture on solid-state batteries",
                    "channelTitle": "Materials Lab",
                    "description": "Full description.",
                    "publishedAt": "2026-08-12T00:00:00Z",
                },
                "contentDetails": {"duration": "PT1H2M3S"},
            }]},
        )

    conn = YouTubeDataConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        meter=_fake_meter(tmp_path / "quota-meta"),
    )
    conn.attach_key(_YT_KEY)
    before = conn.quota_remaining().remaining
    meta = conn.video_metadata("dQw4w9WgXcQ")
    assert before - conn.quota_remaining().remaining == 1
    assert len(seen) == 1
    assert meta.title == "A lecture on solid-state batteries"
    assert meta.channel_title == "Materials Lab"
    assert meta.description == "Full description."
    assert meta.published_at == "2026-08-12T00:00:00Z"
    assert meta.duration_seconds == 3723
    conn.close()


def test_youtube_video_metadata_rejects_bad_id_before_any_send(
    artifact: str, tmp_path: Path
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"items": []})

    conn = YouTubeDataConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        meter=_fake_meter(tmp_path / "quota-bad-id"),
    )
    conn.attach_key(_YT_KEY)
    for bad in ("short", "dQw4w9WgXcQ&x=1", "../../etc/pw", ""):
        with pytest.raises(ValueError):
            conn.video_metadata(bad)
    assert calls == []
    assert conn.quota_remaining().remaining == 10000
    conn.close()


def test_youtube_video_metadata_of_an_unknown_video_is_a_404(
    artifact: str, tmp_path: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})

    conn = YouTubeDataConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        meter=_fake_meter(tmp_path / "quota-404"),
    )
    conn.attach_key(_YT_KEY)
    with pytest.raises(YouTubeError) as exc_info:
        conn.video_metadata("aaaaaaaaaaa")
    assert exc_info.value.status_code == 404
    conn.close()


def test_x_get_tweet_joins_the_author_handle(artifact: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/2/tweets/1790000000000000001"
        assert request.url.params["expansions"] == "author_id"
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": "1790000000000000001",
                    "text": "A thread worth reading",
                    "author_id": "42",
                    "created_at": "2026-08-12T10:00:00.000Z",
                    "conversation_id": "1790000000000000001",
                },
                "includes": {"users": [{"id": "42", "username": "@researcher", "verified": True}]},
            },
        )

    conn = XTwitterConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        governor=_fake_governor(tmp_dir="/tmp/unused-get"),
    )
    conn.attach_key(_X_BEARER)
    record = conn.get_tweet("1790000000000000001")
    assert record == {
        "tweet_id": "1790000000000000001",
        "text": "A thread worth reading",
        "author_handle": "researcher",
        "created_at": "2026-08-12T10:00:00.000Z",
        "conversation_id": "1790000000000000001",
        "author_verified": True,
    }
    conn.close()


def test_x_get_tweet_refuses_a_malformed_id_and_reports_a_missing_post(
    artifact: str,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"errors": [{"title": "Not Found Error"}]})

    conn = XTwitterConnector(
        artifact_path=artifact,
        key_bytes=_TEST_KEY_BYTES,
        client=httpx.Client(transport=_mock_transport(handler)),
        governor=_fake_governor(tmp_dir="/tmp/unused-get-404"),
    )
    conn.attach_key(_X_BEARER)
    with pytest.raises(ValueError):
        conn.get_tweet("12ab")
    assert calls == []
    with pytest.raises(XTwitterError) as exc_info:
        conn.get_tweet("123")
    assert exc_info.value.status_code == 404
    conn.close()
