"""Financial Modeling Prep connector tests (spec §5.7 row 3a, sprint S3).

The acceptance bar, each asserted for real over ``httpx.MockTransport`` (NO
live calls anywhere in this file):

  (a) URL CONSTRUCTION — ``profile()`` GETs ``/api/v3/profile/{symbol}`` and
      ``transcripts()`` GETs ``/api/v3/earning_call_transcript/{symbol}``
      with the attached key in the ``apikey`` query param + the request
      params, verbatim vendor names.
  (b) KEY REDACTION — FMP authenticates key-in-query, so this is the
      redaction-critical lane: every error carries status + PATH only
      (byte-scanned against the key), ``redact_query`` drops the query
      string, and repr never shows the key.
  (c) PARSE — recorded FMP array envelopes map to structured
      ``FmpProfile`` / ``FmpTranscript``; ``[]`` is the no-record signal
      (``None``); a non-array body is an honest error.
  (d) CHASSIS — key attached via the byok store, resolved at call time,
      sent only in the ``apikey`` param; a keyless connector refuses before
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

from acquisition.fmp.client import (  # noqa: E402
    FmpApiError,
    FmpConnector,
    FmpKeyRequired,
    parse_profile_response,
    parse_transcript_response,
    redact_query,
)
from runtime.connectors.base import RateSpec  # noqa: E402
from runtime.connectors.rate_governor import VendorBanned, VendorRateGovernor  # noqa: E402

_TEST_KEY_BYTES = b"0" * nacl.secret.SecretBox.KEY_SIZE  # 32 bytes, test-injected
_SECRET = "fmp-test-key-0123456789abcdef"

# Recorded-shape FMP array envelopes (fixture-validated, live-unverified —
# see the client module docstring).
_PROFILE_FIXTURE = [
    {
        "symbol": "AAPL",
        "price": 226.04,
        "mktCap": 3430000000000,
        "companyName": "Apple Inc.",
        "exchange": "NASDAQ",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "website": "https://www.apple.com",
        "description": "Apple Inc. designs, manufactures and markets...",
        "currency": "USD",
    }
]
_TRANSCRIPT_FIXTURE = [
    {
        "symbol": "AAPL",
        "date": "2024-11-01",
        "quarter": 4,
        "year": 2024,
        "content": "Operator: Good afternoon. Tim Cook: Thanks everyone...",
    }
]


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
) -> FmpConnector:
    """A keyed FmpConnector over MockTransport. Every request is recorded in
    ``requests``. The governor's state dir ALWAYS points into ``tmp_path``
    (never the real ``~/.antiek``). ``secret=None`` leaves it keyless."""
    clock = _FakeClock()

    def _handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = payload if payload is not None else _PROFILE_FIXTURE
        return httpx.Response(status, json=body)

    kwargs: dict[str, object] = {
        "client": httpx.Client(transport=httpx.MockTransport(_handler)),
        "governor": VendorRateGovernor(
            "fmp",
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
    conn = FmpConnector(**kwargs)  # type: ignore[arg-type]
    if secret is not None:
        conn.attach_key(secret)
    return conn


# ── (a) URL construction ─────────────────────────────────────────────────


def test_profile_builds_the_fmp_url(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    conn.profile("AAPL")
    url = requests[0].url
    assert url.scheme == "https"
    assert url.host == "financialmodelingprep.com"
    assert url.path == "/api/v3/profile/AAPL"
    assert dict(url.params) == {"apikey": _SECRET}  # key rides the query, at send


def test_transcripts_builds_the_fmp_url(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, payload=_TRANSCRIPT_FIXTURE)
    conn.transcripts("AAPL", year=2024, quarter=4)
    url = requests[0].url
    assert url.path == "/api/v3/earning_call_transcript/AAPL"
    params = dict(url.params)
    assert params["apikey"] == _SECRET
    assert params["year"] == "2024"
    assert params["quarter"] == "4"


def test_symbol_is_validated_before_the_transport(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    with pytest.raises(ValueError):
        conn.profile("   ")
    assert requests == []


# ── (b) key redaction ────────────────────────────────────────────────────


def test_redact_query_drops_the_query_string() -> None:
    full = f"https://financialmodelingprep.com/api/v3/profile/AAPL?apikey={_SECRET}&year=2024"
    rendered = redact_query(full)
    assert rendered == "https://financialmodelingprep.com/api/v3/profile/AAPL"
    assert _SECRET not in rendered
    assert "apikey" not in rendered
    assert "?" not in rendered


def test_errors_never_echo_the_apikey(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, payload={"error": "server boom"}, status=500)
    with pytest.raises(FmpApiError) as excinfo:
        conn.profile("AAPL")
    err = excinfo.value
    assert err.status_code == 500
    rendered = str(err)
    assert "/api/v3/profile/AAPL" in rendered  # path only
    assert _SECRET not in rendered  # the key is byte-absent
    assert "apikey" not in rendered
    assert "fmp-test" not in rendered


def test_unauthorized_401_surfaces_status_and_path_only(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, payload={"error": "invalid key"}, status=401)
    with pytest.raises(FmpApiError) as excinfo:
        conn.profile("AAPL")
    rendered = str(excinfo.value)
    assert "/api/v3/profile/AAPL" in rendered
    assert _SECRET not in rendered


def test_connector_repr_carries_no_key(tmp_path: Path) -> None:
    conn = _connector([], tmp_path)
    rendered = repr(conn)
    assert _SECRET not in rendered
    assert "fmp-test" not in rendered
    assert "fmp" in rendered and "api_key_query" in rendered


def test_429_bans_the_next_fetch_before_the_transport(tmp_path: Path) -> None:
    """vendor-429 via governor (spec §5.4): a 429 writes the cross-process
    ban sentinel; the NEXT fetch is refused by the governor BEFORE the
    transport is touched."""
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, payload={"error": "slow down"}, status=429)
    with pytest.raises(FmpApiError) as excinfo:
        conn.profile("AAPL")
    assert excinfo.value.status_code == 429
    assert len(requests) == 1
    with pytest.raises(VendorBanned):
        conn.transcripts("AAPL", year=2024, quarter=1)
    assert len(requests) == 1  # refused before any second request


# ── (c) fixture parse ────────────────────────────────────────────────────


def test_profile_fixture_parses_into_structured_fields(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    profile = conn.profile("AAPL")
    assert profile is not None
    assert profile.symbol == "AAPL"
    assert profile.company_name == "Apple Inc."
    assert profile.exchange == "NASDAQ"
    assert profile.sector == "Technology"
    assert profile.industry == "Consumer Electronics"
    assert profile.website == "https://www.apple.com"
    assert profile.currency == "USD"
    assert profile.market_cap == 3430000000000
    assert profile.price == pytest.approx(226.04)


def test_transcript_fixture_parses_into_structured_fields(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, payload=_TRANSCRIPT_FIXTURE)
    transcript = conn.transcripts("AAPL", year=2024, quarter=4)
    assert transcript is not None
    assert transcript.symbol == "AAPL"
    assert transcript.date == "2024-11-01"
    assert transcript.quarter == 4
    assert transcript.year == 2024
    assert "Tim Cook" in transcript.content


def test_empty_array_is_the_no_record_signal() -> None:
    assert parse_profile_response([]) is None
    assert parse_transcript_response([]) is None


def test_non_array_body_is_an_honest_error() -> None:
    with pytest.raises(FmpApiError):
        parse_profile_response({"symbol": "AAPL"})  # an object, not an array
    with pytest.raises(FmpApiError):
        parse_transcript_response("text")  # not even JSON-object-ish
    with pytest.raises(FmpApiError):
        parse_profile_response(["AAPL"])  # a non-mapping entry


# ── (d) chassis ──────────────────────────────────────────────────────────


def test_keyless_fetch_refuses_before_the_transport(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, secret=None)
    assert conn.key_present() is False
    with pytest.raises(FmpKeyRequired):
        conn.profile("AAPL")
    with pytest.raises(FmpKeyRequired):
        conn.transcripts("AAPL", year=2024, quarter=1)
    assert requests == []  # no keyless send ever built


def test_attach_key_roundtrips_through_the_chassis_store(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    assert conn.cred_id is not None and conn.cred_id.startswith("cred-x-")
    assert conn.key_present() is True
    conn.profile("AAPL")
    assert requests[0].url.params["apikey"] == _SECRET


def test_non_json_body_is_an_honest_error(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="<html>oops</html>")

    conn = FmpConnector(
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
        artifact_path=str(tmp_path / "byok_artifact.json"),
        key_bytes=_TEST_KEY_BYTES,
        governor=VendorRateGovernor(
            "fmp",
            RateSpec(max_calls=1_000_000, window_s=60.0),
            state_dir=str(tmp_path / "governor2"),
            lock_poll_interval_s=0.01,
        ),
    )
    conn.attach_key(_SECRET)
    with pytest.raises(FmpApiError):
        conn.profile("AAPL")
