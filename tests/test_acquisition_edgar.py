"""SEC EDGAR connector tests (spec §5.7 row 1, sprint S1) — all offline.

The acceptance bar, each asserted for real over ``httpx.MockTransport`` (NO
live calls anywhere in this file):

  (a) URL CONSTRUCTION — ``search()`` GETs ``https://efts.sec.gov/LATEST/
      search-index`` with the query + filters as params.
  (b) USER-AGENT — the SEC-mandated descriptive UA is present on the request;
      the client FAILS CLOSED without a contact identity (gate §4.1).
  (c) PARSE — a recorded EDGAR JSON envelope maps to structured ``EdgarHit``s
      (and the Archives document URL derives from the hit id).
  (d) THROTTLE — successive searches are spaced by the host-global governor
      with an INJECTED FAKE CLOCK (no real sleeps); a vendor 429 bans the next
      search BEFORE it reaches the transport.
  (e) KEYLESS — the degenerate paste-a-key: no credential anywhere, no
      Authorization header, ``attach_key`` refused.
  (f) ERROR DISCIPLINE — a non-200 surfaces status + PATH only, never the
      query string.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import httpx  # noqa: E402
import pytest  # noqa: E402

from acquisition.edgar.client import (  # noqa: E402
    EdgarApiError,
    EdgarConnector,
    EdgarContactRequired,
    parse_search_response,
)
from runtime.connectors.base import KeyShapeError, RateSpec  # noqa: E402
from runtime.connectors.rate_governor import (  # noqa: E402
    VendorBanned,
    VendorRateGovernor,
)

_CONTACT = "research@antiek.ai"

# A recorded-shape EDGAR full-text-search envelope (fixture-validated,
# live-unverified — see the client module docstring).
_EDGAR_FIXTURE = {
    "took": 17,
    "total": {"value": 2, "relation": "eq"},
    "hits": {
        "total": {"value": 2, "relation": "eq"},
        "hits": [
            {
                "_id": "0000320193-24-000123:apple-20240928.htm",
                "_source": {
                    "ciks": ["0000320193"],
                    "display_names": ["Apple Inc.  (AAPL)"],
                    "form": "10-K",
                    "file_date": "2024-11-01",
                    "period_ending": "2024-09-28",
                    "adsh": "0000320193-24-000123",
                },
            },
            {
                "_id": "0001018724-24-000008:amzn-20240930.htm",
                "_source": {
                    "ciks": ["0001018724"],
                    "display_names": ["AMAZON COM INC  (AMZN)"],
                    "form": "10-Q",
                    "file_date": "2024-11-05",
                    "period_ending": "2024-09-30",
                    "adsh": "0001018724-24-000008",
                },
            },
        ],
    },
}


class _FakeClock:
    """Monotonic fake clock; ``sleep`` advances it (no real waiting)."""

    def __init__(self, start: float = 1000.0) -> None:
        self._t = float(start)
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._t

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self._t += max(0.0, float(seconds))


def _connector(
    requests: list[httpx.Request],
    tmp_path: Path,
    *,
    payload: object = None,
    status: int = 200,
    clock: _FakeClock | None = None,
    max_calls: int = 8,
    send_times: list[float] | None = None,
) -> EdgarConnector:
    """An EdgarConnector over MockTransport + a fake-clock governor. Every
    request is recorded in ``requests``; when ``send_times`` is given the
    handler stamps the fake clock at each send."""
    clk = clock or _FakeClock()

    def _handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if send_times is not None:
            send_times.append(clk.now())
        body = payload if payload is not None else _EDGAR_FIXTURE
        return httpx.Response(status, json=body)

    governor = VendorRateGovernor(
        "edgar",
        RateSpec(max_calls=max_calls, window_s=1.0),
        state_dir=str(tmp_path),
        clock=clk.now,
        sleeper=clk.sleep,
        lock_poll_interval_s=0.01,
    )
    return EdgarConnector(
        contact=_CONTACT,
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
        governor=governor,
    )


# ── (b) fail-closed contact identity + the UA itself ──────────────────────


def test_refuses_to_construct_without_a_contact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTIEK_EDGAR_CONTACT", raising=False)
    with pytest.raises(EdgarContactRequired) as excinfo:
        EdgarConnector()
    assert "ANTIEK_EDGAR_CONTACT" in str(excinfo.value)


def test_blank_contact_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTIEK_EDGAR_CONTACT", "   ")
    with pytest.raises(EdgarContactRequired):
        EdgarConnector()
    with pytest.raises(EdgarContactRequired):
        EdgarConnector(contact="")


def test_contact_comes_from_the_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTIEK_EDGAR_CONTACT", "ops@antiek.ai")
    conn = EdgarConnector(
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))),
        governor=VendorRateGovernor("edgar", RateSpec(8, 1.0), state_dir=str(tmp_path)),
    )
    assert conn.user_agent == "Antiek/1 ops@antiek.ai"


def test_user_agent_header_on_the_request(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    conn.search("liquidity")
    assert len(requests) == 1
    ua = requests[0].headers["user-agent"]
    assert ua == f"Antiek/1 {_CONTACT}"
    assert "Antiek" in ua and _CONTACT in ua  # descriptive, per SEC's mandate


# ── (a) URL construction ──────────────────────────────────────────────────


def test_search_builds_the_edgar_url(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    conn.search(
        '"material weakness"',
        forms=["10-K", "10-Q"],
        date_from="2024-01-01",
        date_to="2024-12-31",
        start=20,
        size=25,
    )
    url = requests[0].url
    assert url.scheme == "https"
    assert url.host == "efts.sec.gov"
    assert url.path == "/LATEST/search-index"
    assert url.params["q"] == '"material weakness"'
    assert url.params["forms"] == "10-K,10-Q"
    assert url.params["startdt"] == "2024-01-01"
    assert url.params["enddt"] == "2024-12-31"
    assert url.params["from"] == "20"
    assert url.params["size"] == "25"


def test_default_search_sends_only_the_query(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    conn.search("liquidity")
    assert dict(requests[0].url.params) == {"q": "liquidity"}


def test_search_rejects_empty_query_and_bad_paging(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    with pytest.raises(ValueError):
        conn.search("   ")
    with pytest.raises(ValueError):
        conn.search("q", start=-1)
    with pytest.raises(ValueError):
        conn.search("q", size=0)
    assert requests == []  # input refused BEFORE any request was built


# ── (c) fixture parse ─────────────────────────────────────────────────────


def test_fixture_parses_into_structured_hits(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    hits = conn.search("supply chain")
    assert len(hits) == 2
    apple, amazon = hits
    assert apple.accession_no == "0000320193-24-000123"
    assert apple.form == "10-K"
    assert apple.file_date == "2024-11-01"
    assert apple.period_ending == "2024-09-28"
    assert apple.ciks == ("0000320193",)
    assert apple.entity_name == "Apple Inc.  (AAPL)"
    assert amazon.form == "10-Q"
    assert amazon.entity_name == "AMAZON COM INC  (AMZN)"


def test_document_url_derives_from_the_hit_id(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    hits = conn.search("supply chain")
    assert hits[0].document_url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019324000123/apple-20240928.htm"
    )


def test_parse_skips_malformed_hits_and_empty_envelopes() -> None:
    assert parse_search_response({"hits": {"hits": []}}) == []
    assert parse_search_response({}) == []
    messy = {
        "hits": {
            "hits": [
                {"_id": "x:y.htm", "_source": {"adsh": "a", "form": "8-K"}},
                {"_id": "no-source"},
                "not-a-dict",
            ]
        }
    }
    hits = parse_search_response(messy)
    assert len(hits) == 1 and hits[0].form == "8-K"
    with pytest.raises(EdgarApiError):
        parse_search_response(["not", "a", "dict"])


# ── (d) the throttle spaces successive searches (fake clock) ──────────────


def test_successive_searches_are_spaced(tmp_path: Path) -> None:
    """With a fake clock and RateSpec(1, 1.0), two searches fire 1.0 fake
    seconds apart — and the test never sleeps a real millisecond."""
    clock = _FakeClock()
    requests: list[httpx.Request] = []
    send_times: list[float] = []
    conn = _connector(
        requests, tmp_path, clock=clock, max_calls=1, send_times=send_times
    )
    conn.search("first")
    conn.search("second")
    assert send_times == [1000.0, 1001.0]
    assert len(requests) == 2  # both went through — spaced, not dropped


def test_edgar_default_budget_is_under_the_sec_ceiling(tmp_path: Path) -> None:
    """The shipped budget (8 calls/s) never sleeps for the first 8 sends of a
    window and DOES sleep for the 9th — one notch under SEC's 10 req/s."""
    clock = _FakeClock()
    requests: list[httpx.Request] = []
    send_times: list[float] = []
    conn = _connector(
        requests, tmp_path, clock=clock, max_calls=8, send_times=send_times
    )
    for i in range(9):
        conn.search(f"q{i}")
    assert send_times[:8] == [1000.0] * 8
    assert send_times[8] == 1001.0


def test_429_bans_the_next_search_before_the_transport(tmp_path: Path) -> None:
    """A 429 from EDGAR writes the cross-process ban sentinel; the NEXT search
    is refused by the governor BEFORE the transport is touched."""
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, payload={"error": "slow down"}, status=429)
    with pytest.raises(EdgarApiError) as excinfo:
        conn.search("first")
    assert excinfo.value.status_code == 429
    assert len(requests) == 1
    with pytest.raises(VendorBanned):
        conn.search("second")
    assert len(requests) == 1  # the refusal fired before any second request


# ── (e) the keyless degenerate case ───────────────────────────────────────


def test_keyless_connector_carries_no_credential(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path)
    assert conn.cred_id is None
    assert conn.key_present() is False
    assert conn._resolve_key() is None
    with pytest.raises(KeyShapeError):
        conn.attach_key("any-key-at-all")
    conn.search("liquidity")
    assert "authorization" not in requests[0].headers


# ── (f) error discipline: status + path, never the query ──────────────────


def test_non_200_surfaces_status_and_path_only(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    conn = _connector(requests, tmp_path, status=500)
    with pytest.raises(EdgarApiError) as excinfo:
        conn.search("insidertradingprobe")
    err = excinfo.value
    assert err.status_code == 500
    assert "/LATEST/search-index" in str(err)
    assert "insidertradingprobe" not in str(err)  # the query is never echoed


def test_non_json_body_is_an_honest_error(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="<html>oops</html>")

    conn = EdgarConnector(
        contact=_CONTACT,
        client=httpx.Client(transport=httpx.MockTransport(_handler)),
        governor=VendorRateGovernor(
            "edgar", RateSpec(8, 1.0), state_dir=str(tmp_path)
        ),
    )
    with pytest.raises(EdgarApiError):
        conn.search("anything")
