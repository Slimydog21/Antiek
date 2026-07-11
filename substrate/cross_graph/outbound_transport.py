"""Federation outbound HTTP transmit (Sprint 30+ thread 1).

Closes the last substrate-side gap in the federation outbound path:
``federate_outbound_citation`` builds + signs a token but does not
transmit it. This module is the thin httpx wrapper that POSTs the
token to ``partner.substrate_url + /federation/inbound-citation``.

Why this lives in substrate (not interfaces/) — the federation
outbound primitive is substrate-owned (it's the single source of
truth for how Antiek talks to a peer). The interfaces/ layer's
``/federation/outbound-citation`` endpoint just builds the bundle;
this module is what production calls AFTER receiving the bundle
to actually transmit.

Substrate-side tests use the ``MockOutboundTransport`` to verify
the bridge fires correctly without making real network calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from .federation import FederatedOutboundCitation
from .inbound import InboundRejection

# Default timeout — federation calls cross network boundaries; keep
# the bound moderately generous so transient delays don't fail every
# transmit, but not unbounded.
DEFAULT_TRANSMIT_TIMEOUT_S: float = 30.0

# The receiver endpoint path on every Antiek instance. Hard-coded
# because the substrate's interfaces/research/api/federation.py
# always mounts it at this path; no per-partner override.
INBOUND_CITATION_PATH: str = "/federation/inbound-citation"
MAX_PARTNER_RESPONSE_BYTES: int = 64 * 1024


class OutboundTransportError(Exception):
    """Surfaces structural / HTTP / parse failures from the partner
    transmit. The caller (federation event log or the operator CLI)
    maps this to an audit event with the failure reason."""


@dataclass(frozen=True)
class OutboundTransmitResult:
    """The shape every OutboundTransport returns. ``status`` is one
    of:
      - "accepted"       — partner returned 200 + accepted=true
      - "refused"        — partner returned 200 + accepted=false
      - "transport_error" — HTTP failure, non-200, parse error
    """

    status: str
    rejection: str | None
    detail: str
    partner_response_body: dict[str, object] | None


class OutboundTransport(Protocol):
    """Protocol any outbound-transport adapter satisfies. Production
    injects ``HttpxOutboundTransport``; tests inject
    ``MockOutboundTransport``."""

    name: str

    def transmit(
        self, citation: FederatedOutboundCitation,
        *,
        timeout_s: float = DEFAULT_TRANSMIT_TIMEOUT_S,
    ) -> OutboundTransmitResult: ...


# ── httpx-backed transport ─────────────────────────────────────────


class HttpxOutboundTransport:
    """Production transport. POSTs the signed token to the partner
    instance's inbound endpoint."""

    name = "httpx_outbound"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
    ):
        self._client = client
        self._owns_client = client is None

    def _ensure_client(
        self, timeout_s: float,
    ) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=timeout_s)
        return self._client

    def transmit(
        self,
        citation: FederatedOutboundCitation,
        *,
        timeout_s: float = DEFAULT_TRANSMIT_TIMEOUT_S,
    ) -> OutboundTransmitResult:
        url = citation.partner_substrate_url.rstrip("/") + INBOUND_CITATION_PATH
        body = {
            "partner_id": citation.partner_id,
            "token": citation.signed_token,
        }
        client = self._ensure_client(timeout_s)
        try:
            with client.stream(
                "POST",
                url,
                json=body,
                headers={"Accept-Encoding": "identity"},
            ) as response:
                if response.status_code != 200:
                    return OutboundTransmitResult(
                        status="transport_error",
                        rejection=None,
                        detail=f"partner returned HTTP {response.status_code}",
                        partner_response_body=None,
                    )
                content_encoding = response.headers.get("content-encoding")
                if (
                    content_encoding is not None
                    and content_encoding.strip().lower() not in ("", "identity")
                ):
                    return OutboundTransmitResult(
                        status="transport_error",
                        rejection=None,
                        detail="partner response used unsupported content encoding",
                        partner_response_body=None,
                    )
                response_body = bytearray()
                for chunk in response.iter_bytes():
                    if len(response_body) + len(chunk) > MAX_PARTNER_RESPONSE_BYTES:
                        return OutboundTransmitResult(
                            status="transport_error",
                            rejection=None,
                            detail="partner response exceeded size limit",
                            partner_response_body=None,
                        )
                    response_body.extend(chunk)
        except httpx.HTTPError as exc:
            return OutboundTransmitResult(
                status="transport_error",
                rejection=None,
                detail=f"HTTP transport failure: {type(exc).__name__}",
                partner_response_body=None,
            )
        try:
            payload = json.loads(response_body)
        except ValueError:
            return OutboundTransmitResult(
                status="transport_error",
                rejection=None,
                detail="partner response was not valid JSON",
                partner_response_body=None,
            )

        if not isinstance(payload, dict):
            return OutboundTransmitResult(
                status="transport_error",
                rejection=None,
                detail="partner response was not a JSON object",
                partner_response_body=None,
            )

        accepted = payload.get("accepted")
        if not isinstance(accepted, bool):
            return OutboundTransmitResult(
                status="transport_error",
                rejection=None,
                detail="partner response had invalid accepted field",
                partner_response_body=None,
            )
        if accepted:
            if payload.get("rejection") is not None:
                return OutboundTransmitResult(
                    status="transport_error",
                    rejection=None,
                    detail="partner response had inconsistent acceptance fields",
                    partner_response_body=None,
                )
            return OutboundTransmitResult(
                status="accepted",
                rejection=None,
                detail="",
                partner_response_body=None,
            )
        rejection = payload.get("rejection")
        try:
            typed_rejection = InboundRejection(rejection)
        except (TypeError, ValueError):
            return OutboundTransmitResult(
                status="transport_error",
                rejection=None,
                detail="partner response had invalid rejection field",
                partner_response_body=None,
            )
        return OutboundTransmitResult(
            status="refused",
            rejection=typed_rejection.value,
            detail=f"partner refused citation: {typed_rejection.value}",
            partner_response_body=None,
        )


# ── Test double ────────────────────────────────────────────────────


@dataclass
class MockOutboundTransport:
    """Test injection. Captures every transmit call's args and
    returns a pre-canned ``OutboundTransmitResult``. Default returns
    "accepted" so happy-path tests are concise; flip
    ``canned_status`` for refusal/error paths."""

    name: str = "mock_outbound"
    canned_status: str = "accepted"
    canned_rejection: str | None = None
    canned_detail: str = ""
    canned_response_body: dict[str, object] | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    def transmit(
        self,
        citation: FederatedOutboundCitation,
        *,
        timeout_s: float = DEFAULT_TRANSMIT_TIMEOUT_S,
    ) -> OutboundTransmitResult:
        self.calls.append({
            "citation_reference_id": citation.reference.reference_id,
            "partner_id": citation.partner_id,
            "partner_substrate_url": citation.partner_substrate_url,
            "signed_token_prefix": citation.signed_token[:8],
            "timeout_s": timeout_s,
        })
        return OutboundTransmitResult(
            status=self.canned_status,
            rejection=self.canned_rejection,
            detail=self.canned_detail,
            partner_response_body=self.canned_response_body,
        )


__all__ = [
    "DEFAULT_TRANSMIT_TIMEOUT_S",
    "HttpxOutboundTransport",
    "INBOUND_CITATION_PATH",
    "MAX_PARTNER_RESPONSE_BYTES",
    "MockOutboundTransport",
    "OutboundTransport",
    "OutboundTransportError",
    "OutboundTransmitResult",
]
