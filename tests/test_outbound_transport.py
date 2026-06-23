"""Federation outbound transport tests (Sprint 30+ thread 1)."""

from __future__ import annotations

import httpx

from substrate.cross_graph.federation import (
    CrossGraphReference,
    FederatedOutboundCitation,
)
from substrate.cross_graph.outbound_transport import (
    INBOUND_CITATION_PATH,
    HttpxOutboundTransport,
    MockOutboundTransport,
)


def _citation(*, signed_token: str = "v1.aa.0.0.bb") -> FederatedOutboundCitation:
    return FederatedOutboundCitation(
        reference=CrossGraphReference(
            reference_id="xref-1",
            referencing_user_id="user-a",
            referencing_investigation_id="inv-1",
            referenced_user_id="user-b",
            referenced_note_id="note-b",
            federated_substrate_id="prt-b",
        ),
        partner_id="prt-b",
        partner_substrate_url="https://partner.example",
        revenue_routing_handle="opaque",
        signed_token=signed_token,
    )


# ── Mock transport ────────────────────────────────────────────────


def test_mock_transport_captures_call_args():
    t = MockOutboundTransport()
    t.transmit(_citation())
    assert len(t.calls) == 1
    assert t.calls[0]["partner_id"] == "prt-b"
    assert t.calls[0]["citation_reference_id"] == "xref-1"


def test_mock_transport_returns_canned_status():
    t = MockOutboundTransport(canned_status="refused", canned_rejection="replay_detected")
    result = t.transmit(_citation())
    assert result.status == "refused"
    assert result.rejection == "replay_detected"


# ── httpx transport — happy + error paths ─────────────────────────


def test_httpx_transport_accepted_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "accepted": True,
                "rejection": None,
                "detail": "",
                "received_at": "2026-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    t = HttpxOutboundTransport(client=client)
    result = t.transmit(_citation())
    assert result.status == "accepted"
    assert INBOUND_CITATION_PATH in captured["url"]
    assert '"partner_id":"prt-b"' in captured["body"]


def test_httpx_transport_refused_with_typed_rejection():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "accepted": False,
                "rejection": "replay_detected",
                "detail": "nonce seen",
                "received_at": "2026-01-01T00:00:00Z",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    t = HttpxOutboundTransport(client=client)
    result = t.transmit(_citation())
    assert result.status == "refused"
    assert result.rejection == "replay_detected"


def test_httpx_transport_non_200_is_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream busy")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    t = HttpxOutboundTransport(client=client)
    result = t.transmit(_citation())
    assert result.status == "transport_error"
    assert "503" in result.detail


def test_httpx_transport_network_failure_is_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    t = HttpxOutboundTransport(client=client)
    result = t.transmit(_citation())
    assert result.status == "transport_error"
    assert "transport failure" in result.detail.lower()


def test_httpx_transport_non_json_response_is_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    t = HttpxOutboundTransport(client=client)
    result = t.transmit(_citation())
    assert result.status == "transport_error"
    assert "JSON" in result.detail or "json" in result.detail
