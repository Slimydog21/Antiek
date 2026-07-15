"""Authenticated commands for zero-provider local multimedia production."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from substrate.multimedia.local_workstation import (
    LocalPreparedSet,
    LocalWorkstationError,
    LocalWorkstationRuntime,
)

from .multimedia_reconciliation_routes import authenticated_multimedia_operator

_LOG = logging.getLogger(__name__)
T = TypeVar("T")


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LocalPrepareBody(_Body):
    expected_revision_id: str = Field(min_length=1, max_length=128)


class LocalSetCommandBody(LocalPrepareBody):
    set_id: str = Field(pattern=r"^mmlocalset_[0-9a-f]{64}$")


class LocalCapabilityResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    available: bool
    reason: Literal["ready", "unavailable"]
    route_policy: Literal["cheapest"] = "cheapest"
    cost_usd: float = 0.0


def get_multimedia_local_runtime_optional() -> LocalWorkstationRuntime | None:
    return None


def get_multimedia_local_runtime() -> LocalWorkstationRuntime:
    runtime = get_multimedia_local_runtime_optional()
    if runtime is None:
        raise HTTPException(status_code=503, detail="local multimedia runtime is unavailable")
    return runtime


multimedia_local_router = APIRouter(tags=["multimedia-local"])


@multimedia_local_router.get("/local/capability", response_model=LocalCapabilityResponse)
def get_local_multimedia_capability(
    _operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: LocalWorkstationRuntime | None = Depends(get_multimedia_local_runtime_optional),
) -> LocalCapabilityResponse:
    return LocalCapabilityResponse(
        available=runtime is not None,
        reason="ready" if runtime is not None else "unavailable",
    )


@multimedia_local_router.post(
    "/assets/{asset_id}/local/prepare", response_model=LocalPreparedSet
)
def prepare_local_multimedia(
    asset_id: str,
    body: LocalPrepareBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: LocalWorkstationRuntime = Depends(get_multimedia_local_runtime),
) -> LocalPreparedSet:
    return _command(
        lambda: runtime.prepare(
            asset_id, body.expected_revision_id, owner_id=operator_id
        )
    )


@multimedia_local_router.get(
    "/assets/{asset_id}/local/{revision_id}/{set_id}", response_model=LocalPreparedSet
)
def inspect_local_multimedia(
    asset_id: str,
    revision_id: str,
    set_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: LocalWorkstationRuntime = Depends(get_multimedia_local_runtime),
) -> LocalPreparedSet:
    return _command(
        lambda: runtime.inspect(asset_id, revision_id, set_id, owner_id=operator_id)
    )


@multimedia_local_router.post(
    "/assets/{asset_id}/local/cards/{card_id}/attest", response_model=LocalPreparedSet
)
def attest_local_multimedia_card(
    asset_id: str,
    card_id: str,
    body: LocalSetCommandBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: LocalWorkstationRuntime = Depends(get_multimedia_local_runtime),
) -> LocalPreparedSet:
    return _command(
        lambda: runtime.attest(
            asset_id, body.expected_revision_id, body.set_id, card_id,
            owner_id=operator_id,
        )
    )


@multimedia_local_router.post(
    "/assets/{asset_id}/local/produce", response_model=LocalPreparedSet
)
def produce_local_multimedia(
    asset_id: str,
    body: LocalSetCommandBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: LocalWorkstationRuntime = Depends(get_multimedia_local_runtime),
) -> LocalPreparedSet:
    return _command(
        lambda: runtime.produce(
            asset_id, body.expected_revision_id, body.set_id, owner_id=operator_id
        )
    )


@multimedia_local_router.get(
    "/assets/{asset_id}/local/{revision_id}/{set_id}/cards/{card_id}/content"
)
def preview_local_multimedia_card(
    asset_id: str,
    revision_id: str,
    set_id: str,
    card_id: str,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: LocalWorkstationRuntime = Depends(get_multimedia_local_runtime),
) -> Response:
    payload = _command(
        lambda: runtime.preview_card(
            asset_id, revision_id, set_id, card_id, owner_id=operator_id
        )
    )
    return Response(
        content=payload,
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@multimedia_local_router.post(
    "/assets/{asset_id}/local/recover", response_model=LocalPreparedSet
)
def recover_local_multimedia(
    asset_id: str,
    body: LocalSetCommandBody,
    operator_id: str = Depends(authenticated_multimedia_operator),
    runtime: LocalWorkstationRuntime = Depends(get_multimedia_local_runtime),
) -> LocalPreparedSet:
    return _command(
        lambda: runtime.recover(
            asset_id, body.expected_revision_id, body.set_id, owner_id=operator_id
        )
    )


def _command(operation: Callable[[], T]) -> T:  # noqa: UP047 - Python 3.11 support
    try:
        return operation()
    except LocalWorkstationError as exc:
        unavailable = "unavailable" in str(exc)
        raise HTTPException(
            status_code=404 if unavailable else 409,
            detail=(
                "local multimedia authority is unavailable"
                if unavailable
                else "local multimedia authority conflicts"
            ),
        ) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=409, detail="local multimedia authority conflicts"
        ) from exc
    except RuntimeError as exc:
        _LOG.exception("local multimedia runtime failed")
        raise HTTPException(
            status_code=503, detail="local multimedia runtime is unavailable"
        ) from exc


__all__ = [
    "LocalCapabilityResponse", "LocalPrepareBody", "LocalSetCommandBody",
    "get_multimedia_local_runtime", "get_multimedia_local_runtime_optional",
    "multimedia_local_router",
]
