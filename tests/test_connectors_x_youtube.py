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

import json
import os
import sys
from pathlib import Path

import httpx
import nacl.secret
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.connectors.x_twitter import (  # noqa: E402
    XTwitterConnector,
    XTwitterError,
    XTwitterKeyRequired,
)
from runtime.connectors.youtube import (  # noqa: E402
    YouTubeDataConnector,
    YouTubeError,
    YouTubeKeyRequired,
)
from runtime.connectors.registry import (  # noqa: E402
    connect_tool,
    disconnect_tool,
    list_tool_connections,
    resolve_tool_connection,
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
    from runtime.connectors.rate_governor import VendorRateGovernor
    from runtime.connectors.base import RateSpec
    import tempfile
    real_tmp = tempfile.mkdtemp()
    return VendorRateGovernor("x", RateSpec(max_calls=25, window_s=900.0), state_dir=real_tmp)


def _fake_meter(state_path: Path):
    """Build a QuotaMeter pinned to a temp state dir + UTC reset."""
    from runtime.connectors.quota_meter import QuotaMeter
    return QuotaMeter("youtube", state_dir=str(state_path), reset_tz="UTC")
