"""Polygon.io connector tests (spec §5.7 row 3b, sprint S3).

The acceptance bar, each asserted for real over ``httpx.MockTransport`` (NO
live calls anywhere in this file):

  (a) URL CONSTRUCTION — ``ticker_details()`` GETs
      ``/v3/reference/tickers/{symbol}`` and ``aggregates()`` GETs
      ``/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from}/{to}``
      with the attached key in the ``apiKey`` query param + the request
      params, verbatim vendor names.
  (b) KEY REDACTION — this client authenticates key-in-query, so this is
      the redaction-critical lane: every error carries status + PATH only
      (byte-scanned against the key), ``redact_query`` drops the query
      string, and repr never shows the key.
  (c) PARSE — recorded Polygon object envelopes map to structured
      ``PolygonTickerDetails`` / ``list[PolygonAggregateBar]``; HTTP 404
      and an absent ``results`` key are the no-record signals (``None`` /
      ``[]``); a non-object body is an honest error.
  (d) CHASSIS — key attached via the byok store, resolved at call time,
      sent only in the ``apiKey`` param; a keyless connector refuses before
      the transport; a vendor 429 writes the governor's ban sentinel and
      the next fetch is refused BEFORE the transport.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import httpx  # noqa: E402
import nacl.secret  # noqa: E402
import pytest  # noqa: E402

from acquisition.polygon.client import (  # noqa: E402
    PolygonApiError,
    PolygonConnector,
    PolygonKeyRequired,
    parse_aggregates_response,
    parse_ticker_details_response,
    redact_query,
)
from runtime.connectors.base import RateSpec  # noqa: E402
from runtime.connectors.rate_governor import VendorBanned, VendorRateGovernor  # noqa: E402

_TEST_KEY_BYTES = b"0" * nacl.secret.SecretBox.KEY_SIZE  # 32 bytes, test-injected
_SECRET = "polygon-test-key-0123456789abcdef"

# Recorded-shape Polygon object envelopes (fixture-validated, live-unverified —
# see the client module docstring).
_TICKER_DETAILS_FIXTURE = {
    "status": "OK",
    "request_id": "31bb59ddb5e139ca1b8c9b6e2c6a92d1",
    "results": {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "market": "stocks",
        "locale": "us",
        "primary_exchange": "XNAS",
        "type": "CS",
        "active": True,
        "currency_name": "usd",
        "cik": "0000320193",
        "market_cap": 3430000000000,
    },
}
_AGGREGATES_FIXTURE = {
    "status": "OK",
    "ticker": "AAPL",
    "queryCount": 2,
    "resultsCount": 2,
    "adjusted": True,
    "results": [
        {
            "v": 70792213,
            "vw": 226.1773,
            "o": 225.87,
            "c": 226.48,
            "h": 227.29,
            "l": 224.2,
            "t": 1751500800000,
            "n": 512345,
        },
        {
            "v": 61234567,
            "vw": 227.5123,
            "o": 226.5,
            "c": 227.65,
            "h": 228.4,
            "l": 225.9,
            "t": 1751587200000,
            "n": 498123,
        },
    ],
}


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self._t = float(start)

    def now(self) -> float:
        return self._t

    def sleep(self, seconds: float) -> None:
        self._t += max(0.0, float(seconds))


def _connector(
    requests: list[httpx.Request],
    tmp_path: Path,
    *,
    payload: object = None,
    status: int = 200,
    secret: str | None = _SECRET,
) -> PolygonConnector:
    """A keyed PolygonConnector over MockTransport. Every request is recorded
    in ``requests``. The governor's state dir ALWAYS points into ``tmp_path``
    (never the real ``~/.antiek``). ``secret=None`` leaves it keyless."""
    clock = _FakeClock()

    def _handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = payload if payload is not None else _TICKER_DETAILS_FIXTURE
        return httpx.Response(status, json=body)

    kwargs: dict[str, object] = {
        "client": httpx.Client(transport=httpx.MockTransport(_handler)),
        "governor": VendorRateGovernor(
            "polygon",
            RateSpec(max_calls=1_000_000, window_s=60.0),
            state_dir=str(tmp_path / "governor"),
            clock=clock.now,
            sleeper=clock.sleep,
            lock_poll_interval_s=0.01,
        ),
    }
    if secret is not None:
        kwargs["artifact_path"] = str(tmp_path / "byok_artifact.json")
        kwargs["key_bytes"] = _TEST_KEY_BYTES
    conn = PolygonConnector(**kwargs)  # type: ignore[arg-type]
    if secret is not None:
        conn.attach_key(secret)
    return conn


# ── (a) URL construction ─────────────────────────────────────────────────


def test_ticker_details_builds_the_polygon_url(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    conn.ticker_details("AAPL")
    url = requests[0].url
    assert url.scheme == "https"
    assert url.host == "api.polygon.io"
    assert url.path == "/v3/reference/tickers/AAPL"
    assert dict(url.params) == {"apiKey": _SECRET}  # key rides the query, at send


def test_aggregates_builds_the_polygon_url(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, payload=_AGGREGATES_FIXTURE)
    conn.aggregates(
        "AAPL",
        date_from="2026-07-01",
        date_to="2026-08-01",
        multiplier=1,
        timespan="day",
        limit=120,
    )
    url = requests[0].url
    assert url.path == "/v2/aggs/ticker/AAPL/range/1/day/2026-07-01/2026-08-01"
    params = dict(url.params)
    assert params["apiKey"] == _SECRET
    assert params["adjusted"] == "true"
    assert params["sort"] == "asc"
    assert params["limit"] == "120"


def test_symbol_is_validated_before_the_transport(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    with pytest.raises(ValueError):
        conn.ticker_details("   ")
    with pytest.raises(ValueError):
        conn.aggregates("", date_from="2026-07-01", date_to="2026-08-01")
    assert requests == []


# ── (b) key redaction ────────────────────────────────────────────────────


def test_redact_query_drops_the_query_string() -> None:
    full = f"https://api.polygon.io/v3/reference/tickers/AAPL?apiKey={_SECRET}&adjusted=true"
    rendered = redact_query(full)
    assert rendered == "https://api.polygon.io/v3/reference/tickers/AAPL"
    assert _SECRET not in rendered
    assert "apiKey" not in rendered
    assert "?" not in rendered


def test_errors_never_echo_the_apikey(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, payload={"error": "server boom"}, status=500)
    with pytest.raises(PolygonApiError) as excinfo:
        conn.ticker_details("AAPL")
    err = excinfo.value
    assert err.status_code == 500
    rendered = str(err)
    assert "/v3/reference/tickers/AAPL" in rendered  # path only
    assert _SECRET not in rendered  # the key is byte-absent
    assert "apiKey" not in rendered
    assert "polygon-test" not in rendered


def test_unauthorized_401_surfaces_status_and_path_only(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(
        requests, tmp_path, payload={"status": "ERROR", "error": "Unknown API Key"}, status=401
    )
    with pytest.raises(PolygonApiError) as excinfo:
        conn.ticker_details("AAPL")
    rendered = str(excinfo.value)
    assert "/v3/reference/tickers/AAPL" in rendered
    assert _SECRET not in rendered


def test_aggregates_error_carries_status_and_path_only(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, payload={"error": "server boom"}, status=503)
    with pytest.raises(PolygonApiError) as excinfo:
        conn.aggregates("AAPL", date_from="2026-07-01", date_to="2026-08-01")
    rendered = str(excinfo.value)
    assert "/v2/aggs/ticker/AAPL/range/1/day/2026-07-01/2026-08-01" in rendered
    assert _SECRET not in rendered
    assert "apiKey" not in rendered


def test_connector_repr_carries_no_key(tmp_path: Path) -> None:
    conn = _connector([], tmp_path)
    rendered = repr(conn)
    assert _SECRET not in rendered
    assert "polygon-test" not in rendered
    assert "polygon" in rendered and "api_key_query" in rendered


def test_429_bans_the_next_fetch_before_the_transport(tmp_path: Path) -> None:
    """vendor-429 via governor (spec §5.4): a 429 writes the cross-process
    ban sentinel; the NEXT fetch is refused by the governor BEFORE the
    transport is touched."""
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, payload={"error": "slow down"}, status=429)
    with pytest.raises(PolygonApiError) as excinfo:
        conn.ticker_details("AAPL")
    assert excinfo.value.status_code == 429
    assert len(requests) == 1
    with pytest.raises(VendorBanned):
        conn.aggregates("AAPL", date_from="2026-07-01", date_to="2026-08-01")
    assert len(requests) == 1  # refused before any second request


# ── (c) fixture parse ────────────────────────────────────────────────────


def test_ticker_details_fixture_parses_into_structured_fields(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    details = conn.ticker_details("AAPL")
    assert details is not None
    assert details.symbol == "AAPL"
    assert details.name == "Apple Inc."
    assert details.market == "stocks"
    assert details.locale == "us"
    assert details.primary_exchange == "XNAS"
    assert details.type == "CS"
    assert details.active is True
    assert details.currency_name == "usd"
    assert details.cik == "0000320193"
    assert details.market_cap == 3430000000000


def test_aggregates_fixture_parses_into_structured_bars(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, payload=_AGGREGATES_FIXTURE)
    bars = conn.aggregates("AAPL", date_from="2026-07-01", date_to="2026-08-01")
    assert len(bars) == 2
    first = bars[0]
    assert first.timestamp_ms == 1751500800000
    assert first.open == pytest.approx(225.87)
    assert first.high == pytest.approx(227.29)
    assert first.low == pytest.approx(224.2)
    assert first.close == pytest.approx(226.48)
    assert first.volume == pytest.approx(70792213)
    assert first.vwap == pytest.approx(226.1773)
    assert first.transactions == 512345
    assert bars[1].timestamp_ms == 1751587200000


def test_unknown_ticker_404_is_the_no_record_signal(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(
        requests,
        tmp_path,
        payload={"status": "NOT_FOUND", "request_id": "abc"},
        status=404,
    )
    assert conn.ticker_details("NOTREAL") is None
    assert len(requests) == 1  # the request DID fire; 404 is an answer, not an exception


def test_absent_results_is_the_no_record_signal() -> None:
    assert parse_ticker_details_response({"status": "OK", "request_id": "abc"}) is None
    assert parse_aggregates_response({"status": "OK", "ticker": "AAPL"}) == []
    assert parse_aggregates_response({"status": "OK", "results": []}) == []


def test_non_object_body_is_an_honest_error() -> None:
    with pytest.raises(PolygonApiError):
        parse_ticker_details_response([{"ticker": "AAPL"}])  # an array, not an object
    with pytest.raises(PolygonApiError):
        parse_aggregates_response("text")  # not even JSON-object-ish
    with pytest.raises(PolygonApiError):
        parse_ticker_details_response({"results": ["AAPL"]})  # a non-mapping record
    with pytest.raises(PolygonApiError):
        parse_aggregates_response({"results": {"ticker": "AAPL"}})  # a non-list results
    with pytest.raises(PolygonApiError):
        parse_aggregates_response({"results": ["AAPL"]})  # a non-mapping bar


# ── (d) chassis ──────────────────────────────────────────────────────────


def test_keyless_fetch_refuses_before_the_transport(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, secret=None)
    assert conn.key_present() is False
    with pytest.raises(PolygonKeyRequired):
        conn.ticker_details("AAPL")
    with pytest.raises(PolygonKeyRequired):
        conn.aggregates("AAPL", date_from="2026-07-01", date_to="2026-08-01")
    assert requests == []  # no keyless send ever built


def test_attach_key_roundtrips_through_the_chassis_store(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    assert conn.cred_id is not None and conn.cred_id.startswith("cred-x-")
    assert conn.key_present() is True
    conn.ticker_details("AAPL")
    assert requests[0].url.params["apiKey"] == _SECRET


def test_non_json_body_is_an_honest_error(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="<html>oops</html>")

    conn = PolygonConnector(
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
        artifact_path=str(tmp_path / "byok_artifact.json"),
        key_bytes=_TEST_KEY_BYTES,
        governor=VendorRateGovernor(
            "polygon",
            RateSpec(max_calls=1_000_000, window_s=60.0),
            state_dir=str(tmp_path / "governor2"),
            lock_poll_interval_s=0.01,
        ),
    )
    conn.attach_key(_SECRET)
    with pytest.raises(PolygonApiError):
        conn.ticker_details("AAPL")
