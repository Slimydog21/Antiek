"""FRED and Alpha Vantage paste-key connectors (SPR-04 task 7).

Offline: the byok artifact and key bytes live in tmp_path and every send goes
through ``httpx.MockTransport``. The response bodies are the ones the vendors
actually returned on 2026-09-23 when the lane driver probed them with a
deliberately invalid key, recorded verbatim so the parse is pinned to the
real wire shape rather than to a guess.
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

from runtime.connectors.alpha_vantage import (  # noqa: E402
    AlphaVantageConnector,
    AlphaVantageError,
    AlphaVantageKeyRejected,
)
from runtime.connectors.base import KeyShapeError, owner_state_key  # noqa: E402
from runtime.connectors.fred import FredConnector, FredError, FredKeyRejected  # noqa: E402
from runtime.connectors.registry import connect_tool, resolve_tool_connection  # noqa: E402

_TEST_KEY_BYTES = b"0" * nacl.secret.SecretBox.KEY_SIZE
_FRED_KEY = "abcdefghijklmnopqrstuvwxyz123456"  # FRED's own documented example shape
_AV_KEY = "ZZZZINVALID00000"

# Recorded 2026-09-23: GET https://api.stlouisfed.org/fred/series with an
# unregistered 32-character key answered HTTP 400 with exactly this body.
_FRED_UNREGISTERED = (
    '{"error_code":400,"error_message":"Bad Request.  The value for variable '
    'api_key is not registered.  Read https:\\/\\/fred.stlouisfed.org\\/docs\\/api'
    '\\/api_key.html for more information."}'
)
_FRED_SERIES_OK = {
    "realtime_start": "2026-09-23",
    "realtime_end": "2026-09-23",
    "seriess": [{"id": "GNPCA", "title": "Real Gross National Product"}],
}
# Recorded 2026-09-23 from https://www.alphavantage.co/query.
_AV_MISSING_KEY = {
    "Error Message": (
        "the parameter apikey is invalid or missing. Please claim your free API key on "
        "(https://www.alphavantage.co/support/#api-key). It should take less than 20 seconds."
    )
}
_AV_RATE_LIMITED = {
    "Information": (
        "Thank you for using Alpha Vantage! Please consider spreading out your free API "
        "requests more sparingly (1 request per second). You may subscribe to any of the "
        "premium plans at https://www.alphavantage.co/premium/ to lift the free key rate "
        "limit (25 requests per day), raise the per-second burst limit, and instantly "
        "unlock all premium endpoints"
    )
}
_AV_GLOBAL_QUOTE = {
    "Global Quote": {
        "01. symbol": "IBM",
        "05. price": "231.3800",
        "07. latest trading day": "2026-09-22",
    }
}


class _Transport:
    """A MockTransport that records every request and answers from a script."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.requests: list[httpx.Request] = []

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self.response

        return httpx.Client(transport=httpx.MockTransport(handler))


def _fred(tmp_path: Path, transport: _Transport, key: str = _FRED_KEY) -> FredConnector:
    conn = FredConnector(
        artifact_path=str(tmp_path / "cred.enc"),
        key_bytes=_TEST_KEY_BYTES,
        client=transport.client(),
        owner="owner-a",
        state_dir=str(tmp_path / "rate"),
    )
    conn.attach_key(key)
    return conn


def _alpha_vantage(tmp_path: Path, transport: _Transport, key: str = _AV_KEY) -> AlphaVantageConnector:
    conn = AlphaVantageConnector(
        artifact_path=str(tmp_path / "cred.enc"),
        key_bytes=_TEST_KEY_BYTES,
        client=transport.client(),
        owner="owner-a",
        state_dir=str(tmp_path / "rate"),
    )
    conn.attach_key(key)
    return conn


# ── FRED ──────────────────────────────────────────────────────────────────


def test_fred_validate_key_rejects_a_malformed_key_before_any_send(tmp_path: Path) -> None:
    transport = _Transport(httpx.Response(200, json=_FRED_SERIES_OK))
    # Wrong length never reaches the store: the catalog KeyShape pins 32.
    with pytest.raises(KeyShapeError):
        _fred(tmp_path, transport, key="short")
    # Right length, wrong alphabet: stored, then refused before any request.
    conn = _fred(tmp_path, transport, key="ABCDEFGHIJKLMNOPQRSTUVWXYZ123456")
    with pytest.raises(FredKeyRejected) as exc_info:
        conn.validate_key()
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456" not in str(exc_info.value)
    assert transport.requests == []
    conn.close()


def test_fred_validate_key_rejects_an_unregistered_key_on_the_recorded_400(tmp_path: Path) -> None:
    transport = _Transport(
        httpx.Response(400, content=_FRED_UNREGISTERED, headers={"content-type": "application/json"})
    )
    conn = _fred(tmp_path, transport)
    with pytest.raises(FredKeyRejected) as exc_info:
        conn.validate_key()
    assert exc_info.value.status_code == 400
    assert _FRED_KEY not in str(exc_info.value)
    assert len(transport.requests) == 1
    conn.close()


def test_fred_validate_key_accepts_a_well_formed_key_on_a_recorded_200(tmp_path: Path) -> None:
    transport = _Transport(httpx.Response(200, json=_FRED_SERIES_OK))
    conn = _fred(tmp_path, transport)
    payload = conn.validate_key()
    assert payload["seriess"][0]["id"] == "GNPCA"
    (request,) = transport.requests
    assert request.url.path == "/fred/series"
    assert request.url.params["api_key"] == _FRED_KEY
    assert request.url.params["series_id"] == "GNPCA"
    assert request.url.params["file_type"] == "json"
    conn.close()


def test_fred_validate_key_reports_other_failures_without_the_key(tmp_path: Path) -> None:
    transport = _Transport(httpx.Response(500, text="upstream"))
    conn = _fred(tmp_path, transport)
    with pytest.raises(FredError) as exc_info:
        conn.validate_key()
    assert not isinstance(exc_info.value, FredKeyRejected)
    assert exc_info.value.status_code == 500
    assert _FRED_KEY not in str(exc_info.value)
    conn.close()


# ── Alpha Vantage ─────────────────────────────────────────────────────────


def test_alpha_vantage_validate_key_rejects_a_malformed_key_before_any_send(tmp_path: Path) -> None:
    transport = _Transport(httpx.Response(200, json=_AV_GLOBAL_QUOTE))
    with pytest.raises(KeyShapeError):
        _alpha_vantage(tmp_path, transport, key="demo")
    conn = _alpha_vantage(tmp_path, transport, key="has spaces and-dash")
    with pytest.raises(AlphaVantageKeyRejected):
        conn.validate_key()
    assert transport.requests == []
    conn.close()


def test_alpha_vantage_validate_key_rejects_on_the_recorded_error_message(tmp_path: Path) -> None:
    transport = _Transport(httpx.Response(200, json=_AV_MISSING_KEY))
    conn = _alpha_vantage(tmp_path, transport)
    with pytest.raises(AlphaVantageKeyRejected) as exc_info:
        conn.validate_key()
    assert exc_info.value.status_code == 400
    conn.close()


def test_alpha_vantage_validate_key_maps_the_information_body_to_a_429(tmp_path: Path) -> None:
    transport = _Transport(httpx.Response(200, json=_AV_RATE_LIMITED))
    conn = _alpha_vantage(tmp_path, transport)
    with pytest.raises(AlphaVantageError) as exc_info:
        conn.validate_key()
    assert not isinstance(exc_info.value, AlphaVantageKeyRejected)
    assert exc_info.value.status_code == 429
    conn.close()


def test_alpha_vantage_validate_key_accepts_a_recorded_global_quote(tmp_path: Path) -> None:
    transport = _Transport(httpx.Response(200, json=_AV_GLOBAL_QUOTE))
    conn = _alpha_vantage(tmp_path, transport)
    payload = conn.validate_key()
    assert payload["Global Quote"]["01. symbol"] == "IBM"
    (request,) = transport.requests
    assert request.url.params["function"] == "GLOBAL_QUOTE"
    assert request.url.params["apikey"] == _AV_KEY
    conn.close()


def test_alpha_vantage_docstring_admits_a_pass_is_not_ownership() -> None:
    """The vendor accepted a fabricated key on 2026-09-23; say so, forever."""
    import runtime.connectors.alpha_vantage as module

    doc = module.AlphaVantageConnector.validate_key.__doc__ or ""
    assert "NOT ownership" in doc
    assert "ZZZZINVALID00000" in (module.__doc__ or "")


# ── Registry: born per-owner ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("vendor", "key", "connector_type"),
    [("fred", _FRED_KEY, FredConnector), ("alpha_vantage", _AV_KEY, AlphaVantageConnector)],
)
def test_fred_and_alpha_vantage_resolve_per_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, vendor: str, key: str, connector_type: type
) -> None:
    monkeypatch.setenv("ANTIEK_TOOL_CONNECTIONS_PATH", str(tmp_path / "tools.json"))
    monkeypatch.setenv("ANTIEK_CONNECTOR_RATE_DIR", str(tmp_path / "rate"))
    artifact = str(tmp_path / "credentials.enc")
    connect_tool("owner-a", vendor, key, artifact_path=artifact, key_bytes=_TEST_KEY_BYTES)
    connector = resolve_tool_connection(
        "owner-a", vendor, artifact_path=artifact, key_bytes=_TEST_KEY_BYTES
    )
    try:
        assert isinstance(connector, connector_type)
        assert connector.descriptor.vendor == vendor
        assert connector.governor.scope == "owner"
        state = Path(connector.governor.state_path)
        assert state.parent == tmp_path / "rate" / vendor
        assert state.name == f"{owner_state_key('owner-a')}.json"
        assert key not in repr(connector)
    finally:
        connector.close()
