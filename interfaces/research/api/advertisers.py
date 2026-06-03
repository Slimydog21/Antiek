"""Advertiser onboarding API (Sprint 23-24 phase 5).

HTTP surface for the operator-only advertiser admission state machine.
The substrate primitives live in ``substrate/ad_inventory/advertiser_onboarding.py``;
this router is the thin adapter that makes them reachable from the
``AdvertiserConsole`` UI surface (``apps/reading/src/modes/AdvertiserConsole/``).

Endpoints:

  POST   /advertisers/applications         submit a new application
  POST   /advertisers/{id}/approve         operator approves PENDING_REVIEW
  POST   /advertisers/{id}/reject          operator rejects (terminal)
  POST   /advertisers/{id}/activate        APPROVED → ACTIVE (requires legal_gate_passed)
  POST   /advertisers/{id}/suspend         ACTIVE → SUSPENDED
  POST   /advertisers/{id}/churn           ACTIVE / SUSPENDED → CHURNED (terminal)
  GET    /advertisers                      list all (latest record per advertiser_id)
  GET    /advertisers/{id}                 read latest record
  GET    /advertisers/serving              list latest records whose status is in SERVING_STATUSES

All endpoints require an operator identity per the global auth middleware
in ``app.py`` (Antiek session cookie / Cloudflare Access / Bearer). The
endpoint code reads ``request.state.user_id`` to attribute operator_notes
when relevant; operator identity is implicit, not a body parameter.

Per master-spec §9.0: ``activate`` refuses unless ``legal_gate_passed=True``
is asserted in the body. The substrate primitive raises
``AdvertiserOnboardingError`` which this router maps to HTTP 409 with a
typed ``error.code``.
"""

from __future__ import annotations

import duckdb
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from substrate.ad_inventory.advertiser_onboarding import (
    AdvertiserOnboardingError,
    AdvertiserRecord,
    activate_advertiser,
    approve_advertiser,
    churn_advertiser,
    load_registry,
    reject_advertiser,
    save_record,
    submit_application,
    suspend_advertiser,
)

# ── Pydantic shapes ────────────────────────────────────────────────


class SubmitApplicationRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    contact_email: str = Field(min_length=3, max_length=200)
    verticals: tuple[str, ...] = ()
    audience_intents: tuple[str, ...] = ()
    monthly_budget_usd_cents: int | None = Field(default=None, ge=0)
    advertiser_id: str | None = Field(default=None, max_length=64)


class ApproveRequest(BaseModel):
    operator_notes: str = ""


class RejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=1, max_length=1000)


class ActivateRequest(BaseModel):
    """Per §9.0: caller MUST affirm the legal gate has passed. Sending
    ``legal_gate_passed=false`` returns 409 with code=legal_gate."""

    legal_gate_passed: bool


class SuspendRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class AdvertiserResponse(BaseModel):
    advertiser_id: str
    display_name: str
    contact_email: str
    verticals: tuple[str, ...]
    audience_intents: tuple[str, ...]
    status: str
    submitted_at: str
    last_status_change_at: str
    operator_notes: str
    rejection_reason: str | None
    monthly_budget_usd_cents: int | None

    @classmethod
    def from_record(cls, rec: AdvertiserRecord) -> AdvertiserResponse:
        return cls(
            advertiser_id=rec.advertiser_id,
            display_name=rec.display_name,
            contact_email=rec.contact_email,
            verticals=rec.verticals,
            audience_intents=rec.audience_intents,
            status=rec.status.value,
            submitted_at=rec.submitted_at,
            last_status_change_at=rec.last_status_change_at,
            operator_notes=rec.operator_notes,
            rejection_reason=rec.rejection_reason,
            monthly_budget_usd_cents=rec.monthly_budget_usd_cents,
        )


class AdvertiserListResponse(BaseModel):
    advertisers: list[AdvertiserResponse]


# ── Helpers ────────────────────────────────────────────────────────


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _load_then_save(state_fn, **kwargs) -> AdvertiserRecord:
    """Round-trip pattern: load → transition → save. The
    AdvertiserRegistry is purely in-memory and lives only for this
    HTTP call. Single-writer invariant enforced by db_lock."""
    from runtime.db_lock import connect_write

    db = _resolve_db_path()
    with connect_write(db, purpose="advertisers/transition") as con:
        registry = load_registry(con)
        record = state_fn(registry, **kwargs)
        save_record(con, record)
    return record


def _refuse(status_code: int, code: str, message: str) -> HTTPException:
    """Uniform error envelope matching the existing API style."""
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


def _map_onboarding_error(exc: AdvertiserOnboardingError) -> HTTPException:
    text = str(exc)
    if "legal gate" in text.lower():
        return _refuse(409, "legal_gate", text)
    if "already exists" in text.lower():
        return _refuse(409, "duplicate_advertiser_id", text)
    if "unknown advertiser_id" in text.lower():
        return _refuse(404, "advertiser_not_found", text)
    # Generic state-machine refusal (wrong starting state).
    return _refuse(409, "invalid_transition", text)


# ── Routes ─────────────────────────────────────────────────────────


def register_advertiser_routes(app: FastAPI) -> None:
    """Mount the advertiser-onboarding routes on the given FastAPI app.

    Pattern mirrors ``register_auth_routes`` in ``auth.py``: a single
    function call from ``create_app`` wires everything up."""

    @app.post(
        "/advertisers/applications",
        response_model=AdvertiserResponse,
        status_code=201,
        tags=["advertisers"],
    )
    async def post_application(
        req: SubmitApplicationRequest, request: Request,
    ) -> AdvertiserResponse:
        try:
            record = _load_then_save(
                submit_application,
                display_name=req.display_name,
                contact_email=req.contact_email,
                verticals=tuple(req.verticals),
                audience_intents=tuple(req.audience_intents),
                monthly_budget_usd_cents=req.monthly_budget_usd_cents,
                advertiser_id=req.advertiser_id,
            )
        except AdvertiserOnboardingError as exc:
            raise _map_onboarding_error(exc) from exc
        return AdvertiserResponse.from_record(record)

    @app.post(
        "/advertisers/{advertiser_id}/approve",
        response_model=AdvertiserResponse,
        tags=["advertisers"],
    )
    async def post_approve(
        advertiser_id: str, req: ApproveRequest,
    ) -> AdvertiserResponse:
        try:
            record = _load_then_save(
                approve_advertiser,
                advertiser_id=advertiser_id,
                operator_notes=req.operator_notes,
            )
        except AdvertiserOnboardingError as exc:
            raise _map_onboarding_error(exc) from exc
        return AdvertiserResponse.from_record(record)

    @app.post(
        "/advertisers/{advertiser_id}/reject",
        response_model=AdvertiserResponse,
        tags=["advertisers"],
    )
    async def post_reject(
        advertiser_id: str, req: RejectRequest,
    ) -> AdvertiserResponse:
        try:
            record = _load_then_save(
                reject_advertiser,
                advertiser_id=advertiser_id,
                rejection_reason=req.rejection_reason,
            )
        except AdvertiserOnboardingError as exc:
            raise _map_onboarding_error(exc) from exc
        return AdvertiserResponse.from_record(record)

    @app.post(
        "/advertisers/{advertiser_id}/activate",
        response_model=AdvertiserResponse,
        tags=["advertisers"],
    )
    async def post_activate(
        advertiser_id: str, req: ActivateRequest,
    ) -> AdvertiserResponse:
        try:
            record = _load_then_save(
                activate_advertiser,
                advertiser_id=advertiser_id,
                legal_gate_passed=req.legal_gate_passed,
            )
        except AdvertiserOnboardingError as exc:
            raise _map_onboarding_error(exc) from exc
        return AdvertiserResponse.from_record(record)

    @app.post(
        "/advertisers/{advertiser_id}/suspend",
        response_model=AdvertiserResponse,
        tags=["advertisers"],
    )
    async def post_suspend(
        advertiser_id: str, req: SuspendRequest,
    ) -> AdvertiserResponse:
        try:
            record = _load_then_save(
                suspend_advertiser,
                advertiser_id=advertiser_id,
                reason=req.reason,
            )
        except AdvertiserOnboardingError as exc:
            raise _map_onboarding_error(exc) from exc
        return AdvertiserResponse.from_record(record)

    @app.post(
        "/advertisers/{advertiser_id}/churn",
        response_model=AdvertiserResponse,
        tags=["advertisers"],
    )
    async def post_churn(advertiser_id: str) -> AdvertiserResponse:
        try:
            record = _load_then_save(
                churn_advertiser, advertiser_id=advertiser_id,
            )
        except AdvertiserOnboardingError as exc:
            raise _map_onboarding_error(exc) from exc
        return AdvertiserResponse.from_record(record)

    @app.get(
        "/advertisers",
        response_model=AdvertiserListResponse,
        tags=["advertisers"],
    )
    async def list_advertisers() -> AdvertiserListResponse:
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            registry = load_registry(con)
        finally:
            con.close()
        # latest() per advertiser, deterministic by advertiser_id.
        seen: dict[str, AdvertiserRecord] = {}
        for r in registry.records:
            seen[r.advertiser_id] = r
        ordered = [seen[k] for k in sorted(seen)]
        return AdvertiserListResponse(
            advertisers=[AdvertiserResponse.from_record(r) for r in ordered],
        )

    @app.get(
        "/advertisers/serving",
        response_model=AdvertiserListResponse,
        tags=["advertisers"],
    )
    async def list_serving() -> AdvertiserListResponse:
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            registry = load_registry(con)
        finally:
            con.close()
        return AdvertiserListResponse(
            advertisers=[
                AdvertiserResponse.from_record(r)
                for r in registry.all_serving()
            ],
        )

    @app.get(
        "/advertisers/{advertiser_id}",
        response_model=AdvertiserResponse,
        tags=["advertisers"],
    )
    async def get_advertiser(advertiser_id: str) -> AdvertiserResponse:
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            registry = load_registry(con)
        finally:
            con.close()
        record = registry.latest(advertiser_id)
        if record is None:
            raise _refuse(
                404, "advertiser_not_found",
                f"advertiser_id {advertiser_id!r} not found",
            )
        return AdvertiserResponse.from_record(record)


__all__ = [
    "ActivateRequest",
    "AdvertiserListResponse",
    "AdvertiserResponse",
    "ApproveRequest",
    "RejectRequest",
    "SubmitApplicationRequest",
    "SuspendRequest",
    "register_advertiser_routes",
]
