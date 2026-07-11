"""Federation outbound transport tests (Sprint 30+ thread 1)."""

from __future__ import annotations

from collections.abc import Iterator

import httpx

from substrate.cross_graph.federation import (
    CrossGraphReference,
    FederatedOutboundCitation,
)
from substrate.cross_graph.outbound_transport import (
    INBOUND_CITATION_PATH,
    MAX_PARTNER_RESPONSE_BYTES,
    HttpxOutboundTransport,
    MockOutboundTransport,
)


class _FailIfOverreadStream(httpx.SyncByteStream):  # type: ignore[misc]
    def __init__(self) -> None:
        self.chunks_read = 0

    def __iter__(self) -> Iterator[bytes]:
        self.chunks_read += 1
        yield b" " * MAX_PARTNER_RESPONSE_BYTES
        self.chunks_read += 1
        yield b"x"
        raise AssertionError("transport consumed beyond the response limit")


class _FailIfReadStream(httpx.SyncByteStream):  # type: ignore[misc]
    def __iter__(self) -> Iterator[bytes]:
        raise AssertionError("encoded response body must not be read")
        yield b""  # pragma: no cover


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


def test_mock_transport_captures_call_args() -> None:
    t = MockOutboundTransport()
    t.transmit(_citation())
    assert len(t.calls) == 1
    assert t.calls[0]["partner_id"] == "prt-b"
    assert t.calls[0]["citation_reference_id"] == "xref-1"


def test_mock_transport_returns_canned_status() -> None:
    t = MockOutboundTransport(canned_status="refused", canned_rejection="replay_detected")
    result = t.transmit(_citation())
    assert result.status == "refused"
    assert result.rejection == "replay_detected"


# ── httpx transport — happy + error paths ─────────────────────────


def test_httpx_transport_accepted_response() -> None:
    captured: dict[str, str] = {}

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
    assert result.partner_response_body is None


def test_httpx_transport_refused_with_typed_rejection() -> None:
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
    assert result.detail == "partner refused citation: replay_detected"
    assert result.partner_response_body is None


def test_httpx_transport_non_200_is_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream busy")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    t = HttpxOutboundTransport(client=client)
    result = t.transmit(_citation())
    assert result.status == "transport_error"
    assert "503" in result.detail


def test_httpx_transport_network_failure_is_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    t = HttpxOutboundTransport(client=client)
    result = t.transmit(_citation())
    assert result.status == "transport_error"
    assert "transport failure" in result.detail.lower()


def test_httpx_transport_non_json_response_is_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    t = HttpxOutboundTransport(client=client)
    result = t.transmit(_citation())
    assert result.status == "transport_error"
    assert "JSON" in result.detail or "json" in result.detail


def test_partner_cannot_reflect_signed_token_through_error_surfaces() -> None:
    token = "signed-secret-citation-token"

    def non_200(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text=request.content.decode("utf-8"))

    def transport_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            f"reflected {request.content.decode('utf-8')}",
            request=request,
        )

    for handler in (non_200, transport_error):
        result = HttpxOutboundTransport(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        ).transmit(_citation(signed_token=token))
        assert result.status == "transport_error"
        assert token not in result.detail
        assert result.partner_response_body is None


def test_partner_cannot_reflect_signed_token_through_success_payload() -> None:
    token = "signed-secret-citation-token"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "accepted": False,
                "rejection": "replay_detected",
                "detail": token,
                "echo": token,
            },
        )

    result = HttpxOutboundTransport(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    ).transmit(_citation(signed_token=token))
    assert result.status == "refused"
    assert token not in result.detail
    assert result.partner_response_body is None


def test_partner_response_requires_boolean_accepted_and_typed_rejection() -> None:
    payloads: tuple[dict[str, object], ...] = (
        {"accepted": "false", "rejection": "replay_detected"},
        {"accepted": False, "rejection": "attacker-controlled"},
        {"accepted": False, "rejection": None},
        {"accepted": True, "rejection": "replay_detected"},
        {},
    )
    for payload in payloads:
        result = HttpxOutboundTransport(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda _request, response=payload: httpx.Response(200, json=response)
                )
            )
        ).transmit(_citation())
        assert result.status == "transport_error"
        assert result.rejection is None
        assert result.partner_response_body is None


def test_partner_response_size_is_bounded_before_json_decode() -> None:
    stream = _FailIfOverreadStream()
    result = HttpxOutboundTransport(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, stream=stream)
            )
        )
    ).transmit(_citation())

    assert result.status == "transport_error"
    assert result.detail == "partner response exceeded size limit"
    assert result.partner_response_body is None
    assert stream.chunks_read == 2


def test_encoded_response_is_rejected_before_decompression() -> None:
    captured_accept_encoding: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_accept_encoding.append(request.headers["accept-encoding"])
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip"},
            stream=_FailIfReadStream(),
        )

    result = HttpxOutboundTransport(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    ).transmit(_citation())

    assert result.status == "transport_error"
    assert result.detail == "partner response used unsupported content encoding"
    assert result.partner_response_body is None
    assert captured_accept_encoding == ["identity"]


def test_identity_content_encoding_is_case_insensitive() -> None:
    result = HttpxOutboundTransport(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    headers={"content-encoding": "Identity"},
                    stream=httpx.ByteStream(
                        b'{"accepted":true,"rejection":null}'
                    ),
                )
            )
        )
    ).transmit(_citation())

    assert result.status == "accepted"
