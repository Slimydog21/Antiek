"""Federation API (Sprint 30+ thread 1).

HTTP surface for the operator-only partner-substrate registry plus
the live cross-instance citation endpoints. The substrate primitives
live in ``substrate/cross_graph/{partner_identity,federation,inbound}.py``;
this router is the thin adapter that exposes them over the wire.

Endpoints (operator-only, gated by the global auth middleware):

  POST   /federation/partners              register a new partner (PENDING_HANDSHAKE)
  POST   /federation/partners/{id}/trust   PENDING_HANDSHAKE → TRUSTED
  POST   /federation/partners/{id}/revoke  TRUSTED → REVOKED (terminal)
  GET    /federation/partners              list every partner (latest record)
  GET    /federation/partners/{id}         read latest record
  GET    /federation/config                read FederationConfig singleton
  PUT    /federation/config                update FederationConfig
  POST   /federation/outbound-citation     build + sign an outbound citation
  POST   /federation/inbound-citation      receiver endpoint — verify + record + emit audit event

The inbound endpoint is the live counterpart to the in-process
``accept_inbound_citation``. It expects ``partner_id`` + ``token`` in
the body. The response carries the outcome shape; on a refusal,
status is 200 with ``accepted=false`` and a typed rejection — the
substrate's no-raise contract is preserved over the wire.

The signed_token + shared_secret are NEVER reflected in API responses
(no-leak invariant from substrate/cross_graph/event_emit.py).
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from runtime.db_lock import connect_read
from substrate.cross_graph.federation import (
    FederationConfig,
    FederationGateError,
    federate_outbound_citation,
)
from substrate.cross_graph.federation_config_store import (
    load_config as load_federation_config,
)
from substrate.cross_graph.federation_config_store import (
    save_config as save_federation_config,
)
from substrate.cross_graph.inbound import (
    InboundCitationOutcome,
    accept_inbound_citation,
    load_active_nonces,
    remember_nonce_persistent,
)
from substrate.cross_graph.partner_identity import (
    PartnerIdentityError,
    PartnerSubstrate,
    generate_shared_secret,
    load_registry,
    register_partner,
    revoke_partner,
    save_record,
    trust_partner,
)
from substrate.cross_graph.partner_identity import (
    ensure_table as ensure_partner_table,
)

# ── Pydantic shapes ────────────────────────────────────────────────


class RegisterPartnerRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    substrate_url: str = Field(min_length=1, max_length=500)
    # The operator may supply a pre-negotiated shared secret OR omit it
    # to have the substrate generate one. The response always carries
    # the secret EXACTLY ONCE so the operator can hand it to the
    # partner; subsequent reads NEVER carry the secret.
    shared_secret_hex: str | None = Field(default=None, min_length=64, max_length=64)
    operator_notes: str = ""
    partner_id: str | None = Field(default=None, max_length=64)


class TrustRequest(BaseModel):
    operator_notes: str = ""


class RevokeRequest(BaseModel):
    revocation_reason: str = Field(min_length=1, max_length=1000)


class PartnerPublicResponse(BaseModel):
    """Response shape that NEVER includes shared_secret_hex. This is
    the default partner-read view. The one-time-on-registration view
    is ``PartnerWithSecretResponse`` below."""

    partner_id: str
    display_name: str
    substrate_url: str
    state: str
    registered_at: str
    last_state_change_at: str
    operator_notes: str
    revocation_reason: str | None

    @classmethod
    def from_record(cls, rec: PartnerSubstrate) -> PartnerPublicResponse:
        return cls(
            partner_id=rec.partner_id,
            display_name=rec.display_name,
            substrate_url=rec.substrate_url,
            state=rec.state.value,
            registered_at=rec.registered_at,
            last_state_change_at=rec.last_state_change_at,
            operator_notes=rec.operator_notes,
            revocation_reason=rec.revocation_reason,
        )


class PartnerWithSecretResponse(PartnerPublicResponse):
    """One-time response carrying the shared_secret_hex. Returned ONLY
    by POST /federation/partners (registration) so the operator can
    hand the secret to the partner out-of-band. All subsequent reads
    return PartnerPublicResponse with no secret field."""

    shared_secret_hex: str


class PartnerListResponse(BaseModel):
    partners: list[PartnerPublicResponse]


class FederationConfigResponse(BaseModel):
    allowed_partner_substrates: tuple[str, ...]
    require_opt_in_for_outbound_citations: bool
    require_attribution_for_outbound_citations: bool


class FederationConfigUpdateRequest(BaseModel):
    allowed_partner_substrates: tuple[str, ...] = ()
    require_opt_in_for_outbound_citations: bool = True
    require_attribution_for_outbound_citations: bool = True


class OutboundCitationRequest(BaseModel):
    partner_id: str = Field(min_length=1, max_length=64)
    referencing_user_id: str = Field(min_length=1, max_length=64)
    referencing_investigation_id: str = Field(min_length=1, max_length=64)
    referenced_user_id: str = Field(min_length=1, max_length=64)
    referenced_note_id: str = Field(min_length=1, max_length=64)
    revenue_routing_handle: str = Field(min_length=1, max_length=200)
    referenced_user_opted_in: bool
    referenced_user_attribution_consented: bool
    nonce: str | None = Field(default=None, max_length=64)


class OutboundCitationResponse(BaseModel):
    reference_id: str
    partner_id: str
    partner_substrate_url: str
    revenue_routing_handle: str
    # signed_token is included EXACTLY here so the caller can transmit
    # it to the partner. It is NEVER persisted in this substrate's
    # event log or audit trail per the no-leak invariant. Callers
    # treat this field as transient — do not log it.
    signed_token: str


class InboundCitationRequest(BaseModel):
    partner_id: str = Field(min_length=1, max_length=64)
    token: str = Field(min_length=1, max_length=8192)


class InboundCitationResult(BaseModel):
    accepted: bool
    rejection: str | None
    detail: str
    # Set only on accept.
    receiver_reference_id: str | None
    referencing_user_id: str | None
    referenced_user_id: str | None
    revenue_routing_handle: str | None
    received_at: str

    @classmethod
    def from_outcome(
        cls, outcome: InboundCitationOutcome,
    ) -> InboundCitationResult:
        ref = outcome.reference
        return cls(
            accepted=outcome.accepted,
            rejection=(
                outcome.rejection.value
                if outcome.rejection is not None
                else None
            ),
            detail=outcome.detail,
            receiver_reference_id=(ref.reference_id if ref is not None else None),
            referencing_user_id=(
                ref.referencing_user_id if ref is not None else None
            ),
            referenced_user_id=(
                ref.referenced_user_id if ref is not None else None
            ),
            revenue_routing_handle=outcome.revenue_routing_handle,
            received_at=outcome.received_at,
        )


# ── Helpers ────────────────────────────────────────────────────────


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _refuse(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


def _map_partner_error(exc: PartnerIdentityError) -> HTTPException:
    text = str(exc)
    if "already registered" in text.lower():
        return _refuse(409, "duplicate_partner_id", text)
    if "unknown partner_id" in text.lower():
        return _refuse(404, "partner_not_found", text)
    if "already REVOKED" in text:
        return _refuse(409, "partner_already_revoked", text)
    return _refuse(409, "invalid_transition", text)


# ── Routes ─────────────────────────────────────────────────────────


def register_federation_routes(app: FastAPI) -> None:
    """Mount the federation routes on the given FastAPI app. Pattern
    matches ``register_auth_routes`` + ``register_advertiser_routes``."""

    # ── Partner registry ────────────────────────────────────────────

    @app.post(
        "/federation/partners",
        response_model=PartnerWithSecretResponse,
        status_code=201,
        tags=["federation"],
    )
    async def post_partner(
        req: RegisterPartnerRequest,
    ) -> PartnerWithSecretResponse:
        from runtime.db_lock import connect_write

        secret = req.shared_secret_hex or generate_shared_secret()
        db = _resolve_db_path()
        with connect_write(db, purpose="federation/register_partner") as con:
            registry = load_registry(con)
            try:
                record = register_partner(
                    registry,
                    display_name=req.display_name,
                    substrate_url=req.substrate_url,
                    shared_secret_hex=secret,
                    operator_notes=req.operator_notes,
                    partner_id=req.partner_id,
                )
            except PartnerIdentityError as exc:
                raise _map_partner_error(exc) from exc
            save_record(con, record)

        base = PartnerPublicResponse.from_record(record).model_dump()
        return PartnerWithSecretResponse(
            **base, shared_secret_hex=secret,
        )

    @app.post(
        "/federation/partners/{partner_id}/trust",
        response_model=PartnerPublicResponse,
        tags=["federation"],
    )
    async def post_trust(
        partner_id: str, req: TrustRequest,
    ) -> PartnerPublicResponse:
        from runtime.db_lock import connect_write

        db = _resolve_db_path()
        with connect_write(db, purpose="federation/trust_partner") as con:
            registry = load_registry(con)
            try:
                record = trust_partner(
                    registry,
                    partner_id=partner_id,
                    operator_notes=req.operator_notes,
                )
            except PartnerIdentityError as exc:
                raise _map_partner_error(exc) from exc
            save_record(con, record)
        return PartnerPublicResponse.from_record(record)

    @app.post(
        "/federation/partners/{partner_id}/revoke",
        response_model=PartnerPublicResponse,
        tags=["federation"],
    )
    async def post_revoke(
        partner_id: str, req: RevokeRequest,
    ) -> PartnerPublicResponse:
        from runtime.db_lock import connect_write

        db = _resolve_db_path()
        with connect_write(db, purpose="federation/revoke_partner") as con:
            registry = load_registry(con)
            try:
                record = revoke_partner(
                    registry,
                    partner_id=partner_id,
                    revocation_reason=req.revocation_reason,
                )
            except PartnerIdentityError as exc:
                raise _map_partner_error(exc) from exc
            save_record(con, record)
        return PartnerPublicResponse.from_record(record)

    @app.get(
        "/federation/partners",
        response_model=PartnerListResponse,
        tags=["federation"],
    )
    async def list_partners() -> PartnerListResponse:
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            ensure_partner_table(con)
            registry = load_registry(con)
        finally:
            con.close()
        seen: dict[str, PartnerSubstrate] = {}
        for r in registry.records:
            seen[r.partner_id] = r
        ordered = [seen[k] for k in sorted(seen)]
        return PartnerListResponse(
            partners=[PartnerPublicResponse.from_record(r) for r in ordered],
        )

    @app.get(
        "/federation/partners/{partner_id}",
        response_model=PartnerPublicResponse,
        tags=["federation"],
    )
    async def get_partner(partner_id: str) -> PartnerPublicResponse:
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            ensure_partner_table(con)
            registry = load_registry(con)
        finally:
            con.close()
        record = registry.latest(partner_id)
        if record is None:
            raise _refuse(
                404, "partner_not_found",
                f"partner_id {partner_id!r} not found",
            )
        return PartnerPublicResponse.from_record(record)

    # ── Federation config singleton ────────────────────────────────

    @app.get(
        "/federation/config",
        response_model=FederationConfigResponse,
        tags=["federation"],
    )
    async def get_config() -> FederationConfigResponse:
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            cfg = load_federation_config(con)
        finally:
            con.close()
        return FederationConfigResponse(
            allowed_partner_substrates=cfg.allowed_partner_substrates,
            require_opt_in_for_outbound_citations=cfg.require_opt_in_for_outbound_citations,
            require_attribution_for_outbound_citations=cfg.require_attribution_for_outbound_citations,
        )

    @app.put(
        "/federation/config",
        response_model=FederationConfigResponse,
        tags=["federation"],
    )
    async def put_config(
        req: FederationConfigUpdateRequest,
    ) -> FederationConfigResponse:
        from runtime.db_lock import connect_write

        db = _resolve_db_path()
        cfg = FederationConfig(
            allowed_partner_substrates=tuple(req.allowed_partner_substrates),
            require_opt_in_for_outbound_citations=req.require_opt_in_for_outbound_citations,
            require_attribution_for_outbound_citations=req.require_attribution_for_outbound_citations,
        )
        with connect_write(db, purpose="federation/update_config") as con:
            save_federation_config(con, cfg)
        return FederationConfigResponse(
            allowed_partner_substrates=cfg.allowed_partner_substrates,
            require_opt_in_for_outbound_citations=cfg.require_opt_in_for_outbound_citations,
            require_attribution_for_outbound_citations=cfg.require_attribution_for_outbound_citations,
        )

    # ── Outbound + inbound citation flow ───────────────────────────

    @app.post(
        "/federation/outbound-citation",
        response_model=OutboundCitationResponse,
        tags=["federation"],
    )
    async def post_outbound(
        req: OutboundCitationRequest,
    ) -> OutboundCitationResponse:
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            cfg = load_federation_config(con)
            registry = load_registry(con)
        finally:
            con.close()
        try:
            citation = federate_outbound_citation(
                config=cfg,
                partner_registry=registry,
                partner_id=req.partner_id,
                referencing_user_id=req.referencing_user_id,
                referencing_investigation_id=req.referencing_investigation_id,
                referenced_user_id=req.referenced_user_id,
                referenced_note_id=req.referenced_note_id,
                revenue_routing_handle=req.revenue_routing_handle,
                referenced_user_opted_in=req.referenced_user_opted_in,
                referenced_user_attribution_consented=req.referenced_user_attribution_consented,
                nonce=req.nonce,
            )
        except FederationGateError as exc:
            text = str(exc)
            code = "gate_refused"
            if "not in the operator's" in text:
                code = "partner_not_allowed"
            elif "not registered" in text:
                code = "partner_not_registered"
            elif "TRUSTED" in text:
                code = "partner_not_trusted"
            elif "opted in" in text:
                code = "opt_in_required"
            elif "attribution" in text:
                code = "attribution_consent_required"
            raise _refuse(409, code, text) from exc
        return OutboundCitationResponse(
            reference_id=citation.reference.reference_id,
            partner_id=citation.partner_id,
            partner_substrate_url=citation.partner_substrate_url,
            revenue_routing_handle=citation.revenue_routing_handle,
            signed_token=citation.signed_token,
        )

    @app.post(
        "/federation/inbound-citation",
        response_model=InboundCitationResult,
        tags=["federation"],
    )
    async def post_inbound(
        req: InboundCitationRequest,
    ) -> InboundCitationResult:
        """Receiver endpoint. Always returns 200; the body's
        ``accepted`` field tells you whether the citation was admitted.
        Refusals carry a typed ``rejection`` code, never the offending
        token or secret."""
        from runtime.db_lock import connect_write

        db = _resolve_db_path()
        with connect_write(db, purpose="federation/inbound_citation") as con:
            cfg = load_federation_config(con)
            registry = load_registry(con)
            ledger = load_active_nonces(con)
            outcome = accept_inbound_citation(
                config=cfg,
                partner_registry=registry,
                nonce_ledger=ledger,
                partner_id=req.partner_id,
                token=req.token,
            )
            # Persist the nonce so a process restart inherits replay
            # defense. Only on accept — refused nonces don't need to
            # be remembered (the token they rode in on is already
            # rejected for a different reason).
            if outcome.accepted:
                # The substrate's accept_inbound_citation already
                # called nonce_ledger.remember on the in-memory ledger;
                # we mirror that into persistent storage here. Re-claim
                # is idempotent on first-claim, ignored on already-seen.
                # The nonce came from the verified payload — extract
                # it by re-verifying (we have all the inputs).
                from substrate.cross_graph.partner_identity import (
                    verify_partner_token,
                )

                partner = registry.latest(req.partner_id)
                if partner is not None:
                    payload = verify_partner_token(
                        shared_secret_hex=partner.shared_secret_hex,
                        token=req.token,
                    )
                    if payload is not None and isinstance(
                        payload.get("nonce"), str,
                    ):
                        remember_nonce_persistent(
                            con,
                            nonce=payload["nonce"],
                            partner_id=req.partner_id,
                        )
        return InboundCitationResult.from_outcome(outcome)


__all__ = [
    "FederationConfigResponse",
    "FederationConfigUpdateRequest",
    "InboundCitationRequest",
    "InboundCitationResult",
    "OutboundCitationRequest",
    "OutboundCitationResponse",
    "PartnerListResponse",
    "PartnerPublicResponse",
    "PartnerWithSecretResponse",
    "RegisterPartnerRequest",
    "RevokeRequest",
    "TrustRequest",
    "register_federation_routes",
]
