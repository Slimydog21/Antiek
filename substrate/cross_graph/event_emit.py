"""Federation event-emission bridges (Sprint 30+ thread 1).

Mirrors ``substrate/ad_inventory/event_emit.py``: pure converters
from in-memory federation records / outcomes to the typed event
envelope, plus broadcaster-hook factories so the federation code
paths emit ``federation.*`` events to the audit stream.

Per master-spec §13.7 audit: every partner-state transition and
every cross-instance citation flow lands as a typed event in the
trajectory. Refusals are first-class events (not silent drops),
with the typed ``InboundRejection`` value riding so the operator
can audit federation posture from the event log alone.

Audit-leak discipline:

  - The shared_secret_hex NEVER appears in any emitted payload.
  - The signed_token NEVER appears in any emitted payload (replay
    surface).
  - The inbound-refusal ``detail`` string is forwarded verbatim from
    the inbound handler, which itself enforces no-token / no-secret
    by construction.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from substrate.schemas.events import (
    ActionType,
    Event,
    FederationInboundCitationAcceptedPayload,
    FederationInboundCitationRefusedPayload,
    FederationOutboundCitationEmittedPayload,
    FederationPartnerRegisteredPayload,
    FederationPartnerRevokedPayload,
    FederationPartnerTrustedPayload,
)

from .federation import FederatedOutboundCitation
from .inbound import InboundCitationOutcome
from .partner_identity import PartnerSubstrate, PartnerTrustState

# ── Pure converters ────────────────────────────────────────────────


def partner_registered_to_payload(
    record: PartnerSubstrate,
) -> FederationPartnerRegisteredPayload:
    """Convert a PENDING_HANDSHAKE partner record to its payload form.
    Caller is responsible for only calling this on the registration
    record (state == PENDING_HANDSHAKE); other states emit different
    payloads via their dedicated converters."""
    return FederationPartnerRegisteredPayload(
        partner_id=record.partner_id,
        display_name=record.display_name,
        substrate_url=record.substrate_url,
        registered_at=record.registered_at,
    )


def partner_trusted_to_payload(
    record: PartnerSubstrate,
) -> FederationPartnerTrustedPayload:
    return FederationPartnerTrustedPayload(
        partner_id=record.partner_id,
        last_state_change_at=record.last_state_change_at,
        operator_notes=record.operator_notes,
    )


def partner_revoked_to_payload(
    record: PartnerSubstrate,
) -> FederationPartnerRevokedPayload:
    if record.revocation_reason is None:
        raise ValueError(
            f"partner {record.partner_id!r} is being converted to a "
            "revoked-payload but the record has no revocation_reason; "
            "the inbound substrate guarantees this is set on REVOKED rows"
        )
    return FederationPartnerRevokedPayload(
        partner_id=record.partner_id,
        last_state_change_at=record.last_state_change_at,
        revocation_reason=record.revocation_reason,
    )


def outbound_citation_to_payload(
    citation: FederatedOutboundCitation,
) -> FederationOutboundCitationEmittedPayload:
    """Convert an outbound citation to its audit payload. The
    signed_token is NOT carried — emitting it would create a replay
    surface in the event log."""
    return FederationOutboundCitationEmittedPayload(
        reference_id=citation.reference.reference_id,
        partner_id=citation.partner_id,
        partner_substrate_url=citation.partner_substrate_url,
        referencing_user_id=citation.reference.referencing_user_id,
        referencing_investigation_id=citation.reference.referencing_investigation_id,
        referenced_user_id=citation.reference.referenced_user_id,
        referenced_note_id=citation.reference.referenced_note_id,
        revenue_routing_handle=citation.revenue_routing_handle,
    )


def inbound_accepted_to_payload(
    outcome: InboundCitationOutcome, *, partner_id: str,
) -> FederationInboundCitationAcceptedPayload:
    if not outcome.accepted or outcome.reference is None:
        raise ValueError(
            "inbound_accepted_to_payload requires an accepted outcome "
            "with a materialized reference; refused outcomes go through "
            "inbound_refused_to_payload"
        )
    return FederationInboundCitationAcceptedPayload(
        receiver_reference_id=outcome.reference.reference_id,
        partner_id=partner_id,
        referencing_user_id=outcome.reference.referencing_user_id,
        referencing_investigation_id=outcome.reference.referencing_investigation_id,
        referenced_user_id=outcome.reference.referenced_user_id,
        referenced_note_id=outcome.reference.referenced_note_id,
        revenue_routing_handle=outcome.revenue_routing_handle or "",
        received_at=outcome.received_at,
    )


def inbound_refused_to_payload(
    outcome: InboundCitationOutcome, *, partner_id: str,
) -> FederationInboundCitationRefusedPayload:
    if outcome.accepted or outcome.rejection is None:
        raise ValueError(
            "inbound_refused_to_payload requires a refused outcome with "
            "a populated rejection field"
        )
    return FederationInboundCitationRefusedPayload(
        partner_id=partner_id,
        rejection=outcome.rejection.value,  # type: ignore[arg-type]
        detail=outcome.detail,
        received_at=outcome.received_at,
    )


# ── Event envelope materialization ─────────────────────────────────


def _envelope(
    payload: object,
    action_type: ActionType,
    *,
    investigation_id: str,
    param_version: str = "substrate-v0",
) -> Event:
    return Event(
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        investigation_id=investigation_id,
        action_type=action_type,
        payload=payload,  # type: ignore[arg-type]
        param_version=param_version,
        emitted_at=datetime.now(UTC),
    )


def partner_registered_to_event(
    record: PartnerSubstrate,
    *,
    investigation_id: str,
    param_version: str = "substrate-v0",
) -> Event:
    return _envelope(
        partner_registered_to_payload(record),
        ActionType.FEDERATION_PARTNER_REGISTERED,
        investigation_id=investigation_id,
        param_version=param_version,
    )


def partner_trusted_to_event(
    record: PartnerSubstrate,
    *,
    investigation_id: str,
    param_version: str = "substrate-v0",
) -> Event:
    return _envelope(
        partner_trusted_to_payload(record),
        ActionType.FEDERATION_PARTNER_TRUSTED,
        investigation_id=investigation_id,
        param_version=param_version,
    )


def partner_revoked_to_event(
    record: PartnerSubstrate,
    *,
    investigation_id: str,
    param_version: str = "substrate-v0",
) -> Event:
    return _envelope(
        partner_revoked_to_payload(record),
        ActionType.FEDERATION_PARTNER_REVOKED,
        investigation_id=investigation_id,
        param_version=param_version,
    )


def outbound_citation_to_event(
    citation: FederatedOutboundCitation,
    *,
    investigation_id: str,
    param_version: str = "substrate-v0",
) -> Event:
    return _envelope(
        outbound_citation_to_payload(citation),
        ActionType.FEDERATION_OUTBOUND_CITATION_EMITTED,
        investigation_id=investigation_id,
        param_version=param_version,
    )


def inbound_outcome_to_event(
    outcome: InboundCitationOutcome,
    *,
    partner_id: str,
    investigation_id: str,
    param_version: str = "substrate-v0",
) -> Event:
    """Convert either an accepted or refused inbound outcome to an
    Event. Picks the right ActionType + payload by branching on
    ``outcome.accepted``."""
    if outcome.accepted:
        return _envelope(
            inbound_accepted_to_payload(outcome, partner_id=partner_id),
            ActionType.FEDERATION_INBOUND_CITATION_ACCEPTED,
            investigation_id=investigation_id,
            param_version=param_version,
        )
    return _envelope(
        inbound_refused_to_payload(outcome, partner_id=partner_id),
        ActionType.FEDERATION_INBOUND_CITATION_REFUSED,
        investigation_id=investigation_id,
        param_version=param_version,
    )


# ── Broadcaster hook factories ─────────────────────────────────────


BroadcastFn = Callable[[Event], None]


def make_broadcasting_partner_state_hook(
    *,
    investigation_id: str,
    broadcast: BroadcastFn,
    param_version: str = "substrate-v0",
) -> Callable[[PartnerSubstrate], None]:
    """Build a hook that emits the right partner-state event based on
    the record's current state. Wire this as a callback into the
    ``register_partner`` / ``trust_partner`` / ``revoke_partner`` flow
    (the substrate state-machine functions don't emit events
    themselves — the operator's wiring decides whether to emit)."""

    def _hook(record: PartnerSubstrate) -> None:
        if record.state is PartnerTrustState.PENDING_HANDSHAKE:
            evt = partner_registered_to_event(
                record,
                investigation_id=investigation_id,
                param_version=param_version,
            )
        elif record.state is PartnerTrustState.TRUSTED:
            evt = partner_trusted_to_event(
                record,
                investigation_id=investigation_id,
                param_version=param_version,
            )
        elif record.state is PartnerTrustState.REVOKED:
            evt = partner_revoked_to_event(
                record,
                investigation_id=investigation_id,
                param_version=param_version,
            )
        else:
            return  # unknown state — silently ignored, defensive
        broadcast(evt)

    return _hook


def make_broadcasting_inbound_hook(
    *,
    investigation_id: str,
    broadcast: BroadcastFn,
    param_version: str = "substrate-v0",
) -> Callable[[InboundCitationOutcome, str], None]:
    """Build a hook that emits the right inbound event (accepted vs
    refused) for every ``InboundCitationOutcome`` the substrate
    produces. The second argument is the partner_id (which the inbound
    handler does not carry on the outcome itself)."""

    def _hook(outcome: InboundCitationOutcome, partner_id: str) -> None:
        evt = inbound_outcome_to_event(
            outcome,
            partner_id=partner_id,
            investigation_id=investigation_id,
            param_version=param_version,
        )
        broadcast(evt)

    return _hook


__all__ = [
    "BroadcastFn",
    "inbound_accepted_to_payload",
    "inbound_outcome_to_event",
    "inbound_refused_to_payload",
    "make_broadcasting_inbound_hook",
    "make_broadcasting_partner_state_hook",
    "outbound_citation_to_event",
    "outbound_citation_to_payload",
    "partner_registered_to_event",
    "partner_registered_to_payload",
    "partner_revoked_to_event",
    "partner_revoked_to_payload",
    "partner_trusted_to_event",
    "partner_trusted_to_payload",
]
