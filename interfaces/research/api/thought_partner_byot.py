"""Owner-selected thought-partner turns use the shared reserve/settle gateway."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from interfaces.research.api.books import ModelReceipt as ModelReceipt
from interfaces.research.api.owner_byot_dispatch import (
    OwnerByotDispatchUnavailable,
    OwnerByotOutcomeUnknown,
    authenticated_distinct_owner,
    dispatch_talk_to_book_byot,
)
from interfaces.research.api.settings_models_admin import UserModelChoice
from substrate.dispatch.router import DispatchResult


@dataclass(frozen=True)
class OwnerTurnSelection:
    owner: str
    choice: UserModelChoice
    operation_id: str


def parse_owner_turn_selection(
    request: Request, model_choice: object, operation_id: object,
) -> OwnerTurnSelection | None:
    if model_choice is None and operation_id is None:
        return None
    if (
        model_choice is None
        or not isinstance(operation_id, str)
        or not operation_id.strip()
        or len(operation_id) > 128
    ):
        raise HTTPException(status_code=422, detail="model_selection_invalid")
    try:
        choice = UserModelChoice.model_validate(model_choice)
    except ValidationError:
        raise HTTPException(status_code=422, detail="model_selection_invalid") from None
    try:
        owner = authenticated_distinct_owner(request)
    except OwnerByotDispatchUnavailable:
        raise HTTPException(status_code=503, detail="owner_model_unavailable") from None
    return OwnerTurnSelection(owner, choice, operation_id.strip())


def dispatch_owner_turn(
    app: FastAPI, selection: OwnerTurnSelection, prompt: str, investigation_id: str,
) -> tuple[DispatchResult, ModelReceipt]:
    try:
        result, authority = dispatch_talk_to_book_byot(
            app=app,
            request_owner_user_id=selection.owner,
            resource_owner_user_id=selection.owner,
            document_id=investigation_id,
            choice=selection.choice,
            prompt=prompt,
            investigation_id=investigation_id,
            logical_operation_id=selection.operation_id,
            # Budget estimation binds length, not content. Bind the actual
            # assembled context too, so equal-length changed turns cannot replay
            # an earlier answer or authorize another spend under the same ID.
            resource_authority_digest=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            role="thought_partner",
            action="thought_partner",
        )
    except OwnerByotOutcomeUnknown:
        raise HTTPException(status_code=503, detail="owner_model_outcome_unknown") from None
    except OwnerByotDispatchUnavailable:
        raise HTTPException(status_code=503, detail="owner_model_unavailable") from None
    return result, ModelReceipt(
        authority="owner_byot",
        requested_provider_id=selection.choice.provider_id,
        requested_model_id=selection.choice.model_id,
        actual_provider_id=result.provider,
        actual_model_id=result.model,
        authority_digest=authority.digest(),
    )
