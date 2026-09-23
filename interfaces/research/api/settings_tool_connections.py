"""Authenticated Settings API for owner-scoped BYO data tools."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from runtime.connectors.base import KeyShapeError, RateSpec
from runtime.connectors.quota_meter import QuotaMeter
from runtime.connectors.registry import (
    ToolConnectionIntegrityError,
    ToolConnectionSnapshot,
    ToolConnectionUnavailable,
    connect_tool,
    disconnect_tool,
    list_tool_connections,
    tool_catalog,
)
from runtime.connectors.x_twitter import (
    SEARCH_MAX_RESULTS,
    X_POST_READ_USD,
    X_PRICING_CHECKED_ON,
    X_PRICING_SOURCE_URL,
    estimated_search_cost_usd,
)

tool_connections_router = APIRouter(prefix="/settings/tools", tags=["settings-tools"])
_PRIVATE_NO_STORE = "private, no-store"
_MAX_CREDENTIAL_BODY_BYTES = 1_024
_AUTHENTICATED_METHODS = frozenset(
    {
        "antiek_session_cookie",
        "cloudflare_access_email",
        "cloudflare_service_token",
        "bearer_token",
    }
)
_SHARED_OPERATOR_METHODS = frozenset(
    {"cloudflare_access_email", "cloudflare_service_token", "bearer_token"}
)

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
    vendor: Literal["youtube", "x", "polygon", "fmp", "edgar", "fred", "alpha_vantage"]
    display_name: str
    credential_kind: Literal["api_key", "contact"]
    auth: str
    docs_url: str
    status: Literal["unconfigured", "configured_unverified", "degraded"]
    credential_present: bool
    status_note: str | None = None
    quota: ToolQuotaResponse
    # Whether any Antiek surface spends this credential today. False means
    # the key is stored and scoped to the owner but nothing reads it yet, and
    # the panel says so instead of calling it configured.
    searchable: bool


class ToolConnectionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connections: list[ToolConnectionResponse]
    count: int


class ToolDisconnectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    removed: Literal["youtube", "x", "polygon", "fmp", "edgar", "fred", "alpha_vantage"]


def _owner(request: Request) -> str:
    owner_user_id = getattr(request.state, "user_id", None)
    auth_method = getattr(request.state, "auth_method", None)
    normalized_owner = owner_user_id.strip() if isinstance(owner_user_id, str) else ""
    if (
        not normalized_owner
        or len(normalized_owner) > 256
        or auth_method not in _AUTHENTICATED_METHODS
        or (
            normalized_owner == "__operator__"
            and auth_method in _SHARED_OPERATOR_METHODS
        )
    ):
        raise HTTPException(status_code=401, detail="authenticated user identity required")
    return normalized_owner


def _quota(snapshot: ToolConnectionSnapshot, owner_user_id: str) -> ToolQuotaResponse:
    # Quota and rate state are keyed per owner: YouTube's budget is per GCP
    # project, so it is per key, and a host-wide meter refused user B once
    # user A had spent A's units. The notes say per-account because that is
    # what the meter now measures; the old "host-global" copy would be a lie.
    # The one exception is a keyless vendor (EDGAR): it can tell callers
    # apart only by IP, so its brake stays the host's and its note says so.
    if snapshot.quota_kind == "youtube_units":
        if not snapshot.credential_present:
            return ToolQuotaResponse(
                kind="youtube_units",
                note="Connect a credential to start per-account quota tracking",
            )
        quota = QuotaMeter("youtube", owner=owner_user_id).remaining()
        return ToolQuotaResponse(
            kind="youtube_units",
            remaining=quota.remaining,
            limit=quota.units_per_day,
            reset_at=quota.reset_at,
            hard_exhausted=quota.hard_exhausted,
            note=(
                "Per-account Antiek meter for your own key, not shared with other "
                "accounts; the provider remains authoritative"
            ),
        )
    if snapshot.quota_kind == "rate_ceiling":
        is_x = snapshot.vendor == "x"
        rate = _catalog_rate(snapshot.vendor)
        if rate is None:
            return ToolQuotaResponse(kind="unavailable", note="No Antiek brake is set for this tool")
        limit = rate.max_calls
        scope = (
            "server-wide brake, shared by every account because the provider limits by IP address"
            if snapshot.auth == "none"
            else "per-account brake on your key"
        )
        return ToolQuotaResponse(
            kind="rate_ceiling",
            limit=limit,
            note=(
                f"Antiek's own {scope}: "
                f"{limit} request{'' if limit == 1 else 's'} per {_window_phrase(rate.window_s)}. "
                "It is not a provider allowance."
            ),
            estimated_cost_usd=_X_SEARCH_COST_USD if is_x else None,
            cost_note=_X_COST_NOTE if is_x else None,
        )
    return ToolQuotaResponse(
        kind="unavailable",
        note="Provider quota is not available to Antiek",
    )


def _catalog_rate(vendor: str) -> RateSpec | None:
    """The brake a vendor's connector actually runs, read from the catalog.

    This used to be hardcoded as ``25 if x else 8``, which was true only while
    X and EDGAR were the two rate-limited vendors; a third would have been
    shown EDGAR's "8 requests per second" whatever its governor did.
    """
    for definition in tool_catalog():
        if definition.vendor == vendor:
            return definition.descriptor.rate
    return None


def _window_phrase(window_s: float) -> str:
    if window_s == 1.0:
        return "second"
    if window_s == 60.0:
        return "minute"
    if window_s % 60 == 0:
        return f"{int(window_s // 60)} minutes"
    return f"{window_s:g} seconds"


def _response(snapshot: ToolConnectionSnapshot, owner_user_id: str) -> ToolConnectionResponse:
    return ToolConnectionResponse(
        vendor=snapshot.vendor,
        display_name=snapshot.display_name,
        credential_kind=snapshot.credential_kind,
        auth=snapshot.auth,
        docs_url=snapshot.docs_url,
        status=snapshot.status,
        credential_present=snapshot.credential_present,
        status_note=snapshot.status_note,
        quota=_quota(snapshot, owner_user_id),
        searchable=snapshot.searchable,
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = _PRIVATE_NO_STORE


@tool_connections_router.get("", response_model=ToolConnectionsResponse)
def get_tool_connections(request: Request, response: Response) -> ToolConnectionsResponse:
    owner_user_id = _owner(request)
    _no_store(response)
    try:
        rows = [_response(item, owner_user_id) for item in list_tool_connections(owner_user_id)]
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
        return _response(connect_tool(owner_user_id, vendor, credential), owner_user_id)
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
