"""Authenticated Settings API for owner-scoped BYO data tools."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from runtime.connectors.base import KeyShapeError
from runtime.connectors.quota_meter import QuotaMeter
from runtime.connectors.registry import (
    ToolConnectionIntegrityError,
    ToolConnectionSnapshot,
    ToolConnectionUnavailable,
    connect_tool,
    disconnect_tool,
    list_tool_connections,
)
from runtime.connectors.x_twitter import (
    SEARCH_MAX_RESULTS,
    X_POST_READ_USD,
    X_PRICING_CHECKED_ON,
    X_PRICING_SOURCE_URL,
    estimated_search_cost_usd,
)

from .account_memory_identity import distinct_signed_owner

tool_connections_router = APIRouter(prefix="/settings/tools", tags=["settings-tools"])
_PRIVATE_NO_STORE = "private, no-store"
_MAX_CREDENTIAL_BODY_BYTES = 1_024
# What a connected X key actually costs its owner. Surfacing only the rate
# ceiling here used to imply a monthly allowance; X sells pay-per-use credits
# and bills per post returned, so a search spends real money and the ceiling
# says nothing about how much. The note carries the per-read rate, its source
# and the date it was read, because an unsourced price is the thing this field
# exists to stop. It deliberately states that Antiek cannot see the balance:
# X publishes no billing endpoint, and inventing a balance read would be worse
# than saying nothing.
_X_SEARCH_COST_USD = estimated_search_cost_usd(SEARCH_MAX_RESULTS)
_X_COST_NOTE = (
    "X bills pay-per-use credits, not a flat monthly tier: about "
    f"${X_POST_READ_USD:.3f} per post returned, as published at "
    f"{X_PRICING_SOURCE_URL} and read on {X_PRICING_CHECKED_ON}. A search that "
    "returns fewer posts costs proportionally less. Antiek cannot read your "
    "credit balance, because X publishes no billing endpoint, so this is an "
    "estimate from the published rate and not a charge Antiek has seen."
)


class ToolQuotaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["youtube_units", "rate_ceiling", "unavailable"]
    remaining: int | None = None
    limit: int | None = None
    reset_at: str | None = None
    hard_exhausted: bool | None = None
    note: str | None = None
    estimated_cost_usd: float | None = None
    cost_note: str | None = None


class ToolConnectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vendor: Literal["youtube", "x", "polygon", "fmp", "edgar"]
    display_name: str
    credential_kind: Literal["api_key", "contact"]
    auth: str
    docs_url: str
    status: Literal["unconfigured", "configured_unverified", "degraded"]
    credential_present: bool
    status_note: str | None = None
    quota: ToolQuotaResponse


class ToolConnectionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connections: list[ToolConnectionResponse]
    count: int


class ToolDisconnectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    removed: Literal["youtube", "x", "polygon", "fmp", "edgar"]


def _owner(request: Request) -> str:
    """Resolve the person whose connected-tool credential this request stores.

    This returned ``request.state.user_id`` verbatim, refusing the
    ``__operator__`` sentinel only for the machine auth methods. Every
    production login mints exactly that sentinel on a session cookie, so a
    connection was WRITTEN under ``__operator__`` while
    ``research_tool_search`` READ it under the derived ``acct_<hash>``.
    ``runtime/connectors/registry._record_key`` hashes the owner into the
    record key, so the two never named the same row: connecting a tool
    appeared to succeed and the credential was then invisible to every search
    that would spend it. The read side's own docstring already recorded this
    asymmetry; only the read half had been fixed.

    Delegates to the one shared predicate (``distinct_signed_owner``) that
    account memory, BYOT dispatch and connected-tool search all use, so the
    write side and the read side cannot disagree by construction rather than
    by keeping four copies of the same logic in step.

    Fails closed: a machine method, a shared sentinel other than the operator
    one, or a session with no verified address each get 401 rather than an
    invented owner. Legacy rows written under the sentinel stay invisible
    until ``tools/migrate_owner_namespace.py`` re-owns them — there is
    deliberately no read-fallback.
    """
    owner = distinct_signed_owner(request)
    if owner is None:
        raise HTTPException(status_code=401, detail="authenticated user identity required")
    return owner


def _quota(snapshot: ToolConnectionSnapshot) -> ToolQuotaResponse:
    if snapshot.quota_kind == "youtube_units":
        if not snapshot.credential_present:
            return ToolQuotaResponse(
                kind="youtube_units",
                note="Connect a credential to start host-global shared quota tracking",
            )
        quota = QuotaMeter("youtube").remaining()
        return ToolQuotaResponse(
            kind="youtube_units",
            remaining=quota.remaining,
            limit=quota.units_per_day,
            reset_at=quota.reset_at,
            hard_exhausted=quota.hard_exhausted,
            note=(
                "Host-global shared Antiek meter across all owners and keys; "
                "the provider remains authoritative"
            ),
        )
    if snapshot.quota_kind == "rate_ceiling":
        is_x = snapshot.vendor == "x"
        limit = 25 if is_x else 8
        window = "15 minutes" if is_x else "second"
        return ToolQuotaResponse(
            kind="rate_ceiling",
            limit=limit,
            note=(
                "Antiek's own host-global brake across all owners and keys: "
                f"{limit} requests per {window}. It is not a provider allowance."
            ),
            estimated_cost_usd=_X_SEARCH_COST_USD if is_x else None,
            cost_note=_X_COST_NOTE if is_x else None,
        )
    return ToolQuotaResponse(
        kind="unavailable",
        note="Provider quota is not available to Antiek",
    )


def _response(snapshot: ToolConnectionSnapshot) -> ToolConnectionResponse:
    return ToolConnectionResponse(
        vendor=snapshot.vendor,
        display_name=snapshot.display_name,
        credential_kind=snapshot.credential_kind,
        auth=snapshot.auth,
        docs_url=snapshot.docs_url,
        status=snapshot.status,
        credential_present=snapshot.credential_present,
        status_note=snapshot.status_note,
        quota=_quota(snapshot),
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = _PRIVATE_NO_STORE


@tool_connections_router.get("", response_model=ToolConnectionsResponse)
def get_tool_connections(request: Request, response: Response) -> ToolConnectionsResponse:
    owner_user_id = _owner(request)
    _no_store(response)
    try:
        rows = [_response(item) for item in list_tool_connections(owner_user_id)]
    except (OSError, ToolConnectionIntegrityError) as exc:
        raise HTTPException(status_code=503, detail="tool connections are unavailable") from exc
    return ToolConnectionsResponse(connections=rows, count=len(rows))


async def _credential_from_request(request: Request) -> str:
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="credential payload is invalid") from exc
        if declared_size < 0 or declared_size > _MAX_CREDENTIAL_BODY_BYTES:
            raise HTTPException(status_code=413, detail="credential payload is too large")
    raw = bytearray()
    try:
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > _MAX_CREDENTIAL_BODY_BYTES:
                raise HTTPException(status_code=413, detail="credential payload is too large")
        body: Any = json.loads(raw)
    except HTTPException:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="credential payload is invalid") from exc
    if not isinstance(body, dict) or set(body) != {"credential"}:
        raise HTTPException(status_code=422, detail="credential payload is invalid")
    credential = body.get("credential")
    if not isinstance(credential, str) or not credential:
        raise HTTPException(status_code=422, detail="credential payload is invalid")
    return credential


@tool_connections_router.put("/{vendor}", response_model=ToolConnectionResponse)
async def put_tool_connection(
    vendor: str,
    request: Request,
    response: Response,
) -> ToolConnectionResponse:
    owner_user_id = _owner(request)
    _no_store(response)
    credential = await _credential_from_request(request)
    try:
        return _response(connect_tool(owner_user_id, vendor, credential))
    except ToolConnectionUnavailable as exc:
        raise HTTPException(status_code=404, detail="unsupported tool vendor") from exc
    except (KeyShapeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="credential does not match the expected format",
        ) from exc
    except (OSError, ToolConnectionIntegrityError) as exc:
        raise HTTPException(status_code=503, detail="tool connection could not be saved") from exc


@tool_connections_router.delete("/{vendor}", response_model=ToolDisconnectResponse)
def delete_tool_connection(
    vendor: str,
    request: Request,
    response: Response,
) -> ToolDisconnectResponse:
    owner_user_id = _owner(request)
    _no_store(response)
    try:
        removed = disconnect_tool(owner_user_id, vendor)
    except ToolConnectionUnavailable as exc:
        raise HTTPException(status_code=404, detail="unsupported tool vendor") from exc
    except (OSError, ToolConnectionIntegrityError) as exc:
        raise HTTPException(status_code=503, detail="tool connection could not be removed") from exc
    if not removed:
        raise HTTPException(status_code=404, detail="tool connection is not configured")
    return ToolDisconnectResponse(removed=vendor)  # type: ignore[arg-type]


def register_settings_tool_connection_routes(app: FastAPI) -> None:
    app.include_router(tool_connections_router)


__all__ = [
    "ToolConnectionResponse",
    "ToolConnectionsResponse",
    "register_settings_tool_connection_routes",
]
