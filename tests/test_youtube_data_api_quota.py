"""YouTube Data API v3 connector + quota-meter tests (spec §5.7 row 2, S2).

The acceptance bar, each asserted for real over ``httpx.MockTransport`` (NO
live calls anywhere in this file):

  (a) URL CONSTRUCTION — ``search()`` GETs ``https://www.googleapis.com/
      youtube/v3/search`` with ``part=snippet``, ``q``, the attached key in
      the ``key`` param, and the optional filters, verbatim vendor names.
  (b) QUOTA UNITS — a successful search reserves exactly
      ``YOUTUBE_UNIT_COSTS["search.list"]`` = 100 units; an exhausted meter
      refuses BEFORE the transport is touched, carrying the PT reset time;
      the day rolls over at midnight America/Los_Angeles (fake clock);
      ``record_actual`` reconciles a released hold; a vendor 403
      ``quotaExceeded`` hard-sets the meter exhausted (spec §10 risk 3).
  (c) PARSE — a recorded Data API envelope maps to structured
      ``YouTubeSearchResult``s; malformed items are skipped, a non-object
      envelope is an honest error.
  (d) KEY HYGIENE — the key is attached via the chassis store (never
      plaintext in the connector), sent only in the ``key`` query param at
      call time, and NEVER echoed in errors (byte-scanned) or repr; a
      keyless connector refuses before any request is built.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import httpx  # noqa: E402
import nacl.secret  # noqa: E402
import pytest  # noqa: E402

from acquisition.youtube.data_api import (  # noqa: E402
    YouTubeApiError,
    YouTubeConnector,
    YouTubeKeyRequired,
    YouTubeQuotaExhausted,
    YouTubeSearchResult,
    parse_search_response,
)
from runtime.connectors.quota_meter import (  # noqa: E402
    YOUTUBE_UNIT_COSTS,
    QuotaExhausted,
    QuotaMeter,
)

_TEST_KEY_BYTES = b"0" * nacl.secret.SecretBox.KEY_SIZE  # 32 bytes, test-injected
# A GCP-shaped API key (the descriptor's prefix class is "AIza").
_SECRET = "AIzaSyD-test-only-key-0123456789abcdefg"

# A recorded-shape Data API v3 search envelope (fixture-validated,
# live-unverified — see the client module docstring).
_YOUTUBE_FIXTURE = {
    "kind": "youtube#searchListResponse",
    "etag": '"fixture-etag"',
    "items": [
        {
            "kind": "youtube#searchResult",
            "id": {"kind": "youtube#video", "videoId": "dQw4w9WgXcQ"},
            "snippet": {
                "publishedAt": "2024-01-15T10:00:00Z",
                "channelId": "UC-9-kyTW8ZkZNDHQJ6FgpwQ",
                "title": "Video title here",
                "description": "A description.",
                "thumbnails": {
                    "default": {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg"}
                },
                "channelTitle": "Some Channel",
            },
        },
        {
            "kind": "youtube#searchResult",
            "id": {"kind": "youtube#channel", "channelId": "UC-9-kyTW8ZkZNDHQJ6FgpwQ"},
            "snippet": {
                "publishedAt": "2022-06-01T00:00:00Z",
                "channelId": "UC-9-kyTW8ZkZNDHQJ6FgpwQ",
                "title": "Some Channel",
                "description": "Channel about things.",
                "channelTitle": "Some Channel",
            },
        },
    ],
}

_PT = ZoneInfo("America/Los_Angeles")


class _FakeClock:
    """Settable epoch clock (``time.time`` shape) so the PT day can be
    pinned and rolled with zero real waiting."""

    def __init__(self, start: float) -> None:
        self._t = float(start)

    def now(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += max(0.0, float(seconds))

    def set(self, t: float) -> None:
        self._t = float(t)


def _pt_epoch(year: int, month: int, day: int, hour: int, minute: int) -> float:
    return datetime(year, month, day, hour, minute, tzinfo=_PT).timestamp()


def _connector(
    requests: list[httpx.Request],
    tmp_path: Path,
    *,
    payload: object = None,
    status: int = 200,
    secret: str | None = _SECRET,
    meter: QuotaMeter | None = None,
    clock: _FakeClock | None = None,
    state_dir: str | None = None,
) -> YouTubeConnector:
    """A keyed YouTubeConnector over MockTransport. Every request is
    recorded in ``requests``. The meter (injected or self-built from
    ``state_dir`` + ``clock``) ALWAYS points into ``tmp_path`` — a test that
    wrote quota state into ``~/.antiek`` would be a test-integrity
    violation. ``secret=None`` leaves the connector keyless (attach
    nothing)."""
    clk = clock or _FakeClock(_pt_epoch(2026, 8, 7, 12, 0))

    def _handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = payload if payload is not None else _YOUTUBE_FIXTURE
        return httpx.Response(status, json=body)

    kwargs: dict[str, object] = {
        "client": httpx.Client(transport=httpx.MockTransport(_handler)),
    }
    if secret is not None:
        kwargs["artifact_path"] = str(tmp_path / "byok_artifact.json")
        kwargs["key_bytes"] = _TEST_KEY_BYTES
    if meter is not None:
        kwargs["meter"] = meter
    else:
        # Never the real default dir — pin under tmp_path.
        kwargs["state_dir"] = state_dir or str(tmp_path / "quota_default")
        kwargs["clock"] = clk.now
    conn = YouTubeConnector(**kwargs)  # type: ignore[arg-type]
    if secret is not None:
        conn.attach_key(secret)
    return conn


def _small_meter(tmp_path: Path, clock: _FakeClock, *, units_per_day: int) -> QuotaMeter:
    return QuotaMeter(
        "youtube",
        units_per_day=units_per_day,
        state_dir=str(tmp_path / "quota"),
        clock=clock.now,
    )


# ── (a) URL construction ─────────────────────────────────────────────────


def test_search_builds_the_youtube_url(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    conn.search(
        "supply chain",
        max_results=10,
        order="viewCount",
        published_after="2024-01-01T00:00:00Z",
        published_before="2024-12-31T23:59:59Z",
        region_code="US",
        type_="video",
        relevance_language="en",
    )
    url = requests[0].url
    assert url.scheme == "https"
    assert url.host == "www.googleapis.com"
    assert url.path == "/youtube/v3/search"
    params = dict(url.params)
    assert params["part"] == "snippet"
    assert params["q"] == "supply chain"
    assert params["key"] == _SECRET  # the key rides the query param, at send
    assert params["maxResults"] == "10"
    assert params["order"] == "viewCount"
    assert params["publishedAfter"] == "2024-01-01T00:00:00Z"
    assert params["publishedBefore"] == "2024-12-31T23:59:59Z"
    assert params["regionCode"] == "US"
    assert params["type"] == "video"
    assert params["relevanceLanguage"] == "en"


def test_default_search_sends_only_the_minimal_params(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    conn.search("liquidity")
    assert dict(requests[0].url.params) == {
        "part": "snippet",
        "q": "liquidity",
        "key": _SECRET,
        "maxResults": "25",
        "type": "video",
    }


def test_search_rejects_bad_input_before_the_transport(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    with pytest.raises(ValueError):
        conn.search("   ")
    with pytest.raises(ValueError):
        conn.search("q", max_results=0)
    with pytest.raises(ValueError):
        conn.search("q", max_results=51)
    with pytest.raises(ValueError):
        conn.search("q", type_="playlistx")
    assert requests == []  # input refused BEFORE any request was built


# ── (b) quota-unit accounting ────────────────────────────────────────────


def test_search_decrements_exactly_100_quota_units(tmp_path: Path) -> None:
    assert YOUTUBE_UNIT_COSTS["search.list"] == 100
    clock = _FakeClock(_pt_epoch(2026, 8, 7, 12, 0))
    requests: list[httpx.Request] = []
    meter = _small_meter(tmp_path, clock, units_per_day=10_000)
    conn = _connector(requests, tmp_path, meter=meter)
    assert conn.quota_remaining().remaining == 10_000
    conn.search("first")
    assert conn.quota_remaining().remaining == 9_900  # exactly one search.list
    conn.search("second")
    assert conn.quota_remaining().remaining == 9_800


def test_exhausted_meter_refuses_before_the_transport_with_reset_time(
    tmp_path: Path,
) -> None:
    clock = _FakeClock(_pt_epoch(2026, 8, 7, 23, 30))  # late evening PT
    requests: list[httpx.Request] = []
    meter = _small_meter(tmp_path, clock, units_per_day=100)
    conn = _connector(requests, tmp_path, meter=meter)
    conn.search("first")  # 100 units reserved — day is now full
    assert conn.quota_remaining().remaining == 0
    with pytest.raises(QuotaExhausted) as excinfo:
        conn.search("second")
    assert len(requests) == 1  # the refusal fired before any second request
    err = excinfo.value
    assert err.remaining == 0
    assert "T00:00:00" in err.reset_at  # midnight PT, next day
    assert err.reset_at.endswith("-07:00")  # August = PDT; unambiguous offset
    assert str(err)  # the message itself carries the reset, never a key


def test_quota_rolls_over_at_midnight_pacific(tmp_path: Path) -> None:
    clock = _FakeClock(_pt_epoch(2026, 8, 7, 23, 30))
    requests: list[httpx.Request] = []
    meter = _small_meter(tmp_path, clock, units_per_day=100)
    conn = _connector(requests, tmp_path, meter=meter)
    conn.search("first")  # day full: used 100/100
    with pytest.raises(QuotaExhausted):
        conn.search("blocked")
    clock.advance(30 * 60)  # 00:30 PT — Google's reset has passed
    assert conn.quota_remaining().remaining == 100  # fresh vendor day
    conn.search("second")  # and the send works again
    assert conn.quota_remaining().remaining == 0


def test_record_actual_reconciles_and_failed_sends_release_their_hold(
    tmp_path: Path,
) -> None:
    clock = _FakeClock(_pt_epoch(2026, 8, 7, 12, 0))
    meter = _small_meter(tmp_path, clock, units_per_day=10_000)

    # Direct reconcile: a reservation that was too optimistic is corrected.
    meter.check_and_reserve(100)
    assert meter.remaining().remaining == 9_900
    meter.record_actual(-100)  # the call actually spent nothing
    assert meter.remaining().remaining == 10_000
    # A no-op reconcile is legal (deterministic cost: reservation == actual).
    meter.record_actual(0)
    assert meter.remaining().remaining == 10_000

    # A failed send (5xx) releases its 100-unit hold end-to-end.
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, payload={"error": "boom"}, status=500)
    with pytest.raises(YouTubeApiError):
        conn.search("failure")
    assert conn.quota_remaining().remaining == 10_000  # nothing stuck


def test_vendor_403_quota_exceeded_hard_sets_the_meter(tmp_path: Path) -> None:
    clock = _FakeClock(_pt_epoch(2026, 8, 7, 12, 0))
    requests: list[httpx.Request] = []
    meter = _small_meter(tmp_path, clock, units_per_day=10_000)
    conn = _connector(
        requests,
        tmp_path,
        meter=meter,
        payload={"error": {"code": 403, "errors": [{"reason": "quotaExceeded"}]}},
        status=403,
    )
    with pytest.raises(YouTubeQuotaExhausted) as excinfo:
        conn.search("over")
    assert excinfo.value.status_code == 403
    # Google's ledger wins: the meter is hard-set even though the local
    # counter thought 9,900 remained (spec §10 risk 3).
    snap = conn.quota_remaining()
    assert snap.remaining == 0
    assert snap.hard_exhausted is True
    assert "T00:00:00" in snap.reset_at
    # And the next search is refused before the transport.
    with pytest.raises(QuotaExhausted):
        conn.search("over2")
    assert len(requests) == 1


# ── (c) fixture parse ────────────────────────────────────────────────────


def test_fixture_parses_into_structured_results(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    hits = conn.search("things")
    assert len(hits) == 2
    video, channel = hits
    assert isinstance(video, YouTubeSearchResult)
    assert video.video_id == "dQw4w9WgXcQ"
    assert video.kind == "video"
    assert video.title == "Video title here"
    assert video.description == "A description."
    assert video.channel_id == "UC-9-kyTW8ZkZNDHQJ6FgpwQ"
    assert video.channel_title == "Some Channel"
    assert video.published_at == "2024-01-15T10:00:00Z"
    assert video.thumbnail_url == (
        "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg"
    )
    assert channel.kind == "channel"
    assert channel.video_id == "UC-9-kyTW8ZkZNDHQJ6FgpwQ"  # the channel id
    assert channel.thumbnail_url is None  # omitted snippet thumbnail


def test_parse_skips_malformed_items_and_rejects_non_object_envelopes() -> None:
    assert parse_search_response({"items": []}) == []
    assert parse_search_response({}) == []
    messy = {
        "items": [
            {"kind": "youtube#searchResult", "id": {"videoId": "x"}},  # no snippet
            {"kind": "youtube#searchResult", "snippet": {}},  # no id
            "not-a-dict",
        ]
    }
    assert parse_search_response(messy) == []
    with pytest.raises(YouTubeApiError):
        # A non-object body is exactly what the envelope check must reject;
        # the runtime check is broader than the declared param type.
        parse_search_response(["not", "an", "object"])  # type: ignore[arg-type]


# ── (d) key hygiene ──────────────────────────────────────────────────────


def test_keyless_search_refuses_before_the_transport(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, secret=None)
    assert conn.key_present() is False
    with pytest.raises(YouTubeKeyRequired):
        conn.search("anything")
    assert requests == []  # no keyless send ever built


def test_errors_never_echo_the_key_or_the_query(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(
        requests, tmp_path, payload={"error": "over quota or blocked"}, status=500
    )
    with pytest.raises(YouTubeApiError) as excinfo:
        conn.search("insidertradingprobe")
    err = str(excinfo.value)
    assert "/youtube/v3/search" in err  # path only
    assert _SECRET not in err  # the key is byte-absent from the message
    assert "AIza" not in err
    assert "insidertradingprobe" not in err  # the query is never echoed
    assert "key=" not in err


def test_non_quota_403_surfaces_status_and_path_only(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(
        requests,
        tmp_path,
        payload={"error": {"code": 403, "errors": [{"reason": "keyInvalid"}]}},
        status=403,
    )
    with pytest.raises(YouTubeApiError) as excinfo:
        conn.search("something")
    assert excinfo.value.status_code == 403  # generic API error, NOT quota
    err = str(excinfo.value)
    assert "/youtube/v3/search" in err
    assert _SECRET not in err


def test_connector_repr_carries_no_key(tmp_path: Path) -> None:
    conn = _connector([], tmp_path)
    rendered = repr(conn)
    assert _SECRET not in rendered
    assert "AIza" not in rendered
    assert "youtube" in rendered and "api_key_query" in rendered


def test_attach_key_roundtrips_through_the_chassis_store(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    cred_id = conn.cred_id
    assert cred_id is not None and cred_id.startswith("cred-x-")
    assert conn.key_present() is True
    conn.search("stored key")
    assert requests[0].url.params["key"] == _SECRET


def test_connector_builds_its_own_meter_from_state_dir(tmp_path: Path) -> None:
    """The state_dir + clock constructor path (no injected meter) also
    meters quota correctly."""
    clock = _FakeClock(_pt_epoch(2026, 8, 7, 12, 0))
    requests: list[httpx.Request] = []
    conn = _connector(
        requests,
        tmp_path,
        clock=clock,
        state_dir=str(tmp_path / "connector_quota"),
    )
    assert conn.quota_remaining().remaining == 10_000
    conn.search("self-built meter")
    assert conn.quota_remaining().remaining == 9_900


def test_meter_rejects_bad_arguments(tmp_path: Path) -> None:
    clock = _FakeClock(_pt_epoch(2026, 8, 7, 12, 0))
    with pytest.raises(ValueError):
        QuotaMeter("youtube", units_per_day=0)
    with pytest.raises(ValueError):
        QuotaMeter("", units_per_day=100)
    with pytest.raises(ValueError):
        QuotaMeter("youtube", reset_tz="Mars/Olympus")
    meter = _small_meter(tmp_path, clock, units_per_day=100)
    with pytest.raises(ValueError):
        meter.check_and_reserve(0)
