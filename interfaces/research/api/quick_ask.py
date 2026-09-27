"""Question-only Quick Ask: one owner-paid model request per operation."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

from interfaces.research.api import settings_models_admin as models_admin
from interfaces.research.api.owner_byot_dispatch import (
    OwnerByotDispatchUnavailable,
    OwnerByotOutcomeUnknown,
    _freeze_current_authority,
    authenticated_distinct_owner,
    dispatch_talk_to_book_byot,
)
from runtime.research_runner.byot_provider_catalog import get_model_variant, get_provider_preset
from substrate.byot_usage.ledger import ByotUsageLedger, OperationRow
from substrate.dispatch.router import DispatchConfig

quick_ask_router = APIRouter(prefix="/research/quick-ask", tags=["ask"])

_ACTION = "research.quick_ask.single"
_ROLE = "thought_partner"
_MAX_OUTPUT_TOKENS = 1024
_MAX_BODY_BYTES = 16_384
_PRICE_MAX_AGE = timedelta(days=30)
_RECENT_CACHE_CONTROL = "private, no-store"
_SNAPSHOT_DATE = re.compile(r"(?<!\d)(20\d\d-\d\d-\d\d)(?!\d)")
_WARNING = (
    "Estimate, not a provider cap. A network failure after sending may leave "
    "the charge unknown. Check your provider dashboard before trying again."
)
# Exact IDs agreed for personal V1. The present August catalog contains none
# of these; routes stay unavailable until a fresh preset and live adapter exist.
_APPROVED_MODELS = frozenset({
    "gpt-6-sol", "gpt-6-luna", "glm-5.3", "glm-5.3-flash", "kimi-k3",
    "grok-4.7", "mimo-v2.6-pro", "deepseek-v4-pro", "deepseek-flash",
    "deepseek-flash-nothink",
})
_INVENTORY_OPERATION = UUID("00000000-0000-4000-8000-000000000000")


class QuickAskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=12_000)
    operation_id: UUID
    model_choice: models_admin.UserModelChoice

    @field_validator("question")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question is blank")
        return value


class QuickAskExecute(QuickAskInput):
    quote_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class _Quote:
    authority_digest: str
    estimated_usd: Decimal
    reserved_cents: int
    price_snapshot: str
    price_source: str
    provider_id: str
    model_id: str


def _owner(request: Request) -> str:
    try:
        return authenticated_distinct_owner(request)
    except OwnerByotDispatchUnavailable:
        raise HTTPException(status_code=401, detail="signed_owner_required") from None


async def _body(request: Request, schema: type[QuickAskInput]) -> QuickAskInput:
    media_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(status_code=415, detail="quick_ask_json_required")
    declared = request.headers.get("Content-Length")
    if declared is not None:
        try:
            if int(declared) < 1 or int(declared) > _MAX_BODY_BYTES:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="quick_ask_request_invalid") from None
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > _MAX_BODY_BYTES:
            raise HTTPException(status_code=400, detail="quick_ask_request_invalid")
        data.extend(chunk)
    try:
        raw = json.loads(data)
        return schema.model_validate(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValidationError):
        # FastAPI's automatic 422 echoes invalid private input in its detail.
        raise HTTPException(status_code=422, detail="quick_ask_request_invalid") from None


def _config() -> DispatchConfig:
    loaded = DispatchConfig.from_yaml(
        Path(__file__).parents[3] / "substrate/dispatch/config.yaml"
    )
    tier_name = loaded.role_tiers[_ROLE]
    tiers = dict(loaded.tiers)
    tiers[tier_name] = replace(tiers[tier_name], max_tokens=_MAX_OUTPUT_TOKENS)
    return DispatchConfig(loaded.role_tiers, tiers)


def _prompt_digest(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def _event_scope(owner: str, operation: UUID) -> str:
    # Event trajectories are keyed by one string, unlike the journal's
    # (owner, operation) primary key. Keep equal UUIDs across owners apart.
    owner_hash = hashlib.sha256(owner.encode("utf-8")).hexdigest()[:16]
    return f"quick-ask-{owner_hash}-{operation.hex}"


def _ledger(request: Request, *, read_only: bool = False) -> ByotUsageLedger:
    configured = getattr(request.app.state, "quick_ask_usage_ledger", None)
    return configured if isinstance(configured, ByotUsageLedger) else ByotUsageLedger(
        create=not read_only,
    )


def _request_digest(owner: str, operation_id: str, body: QuickAskExecute) -> str:
    # The V1 outbound prompt is exactly question, byte for byte. Keep only
    # hashes of those private bytes in durable authority, never the text.
    question_bytes = body.question.encode("utf-8")
    prompt_bytes = body.question.encode("utf-8")
    material = {
        "version": "quick-ask-request-v1",
        "owner": owner,
        "operation_id": operation_id,
        "question_utf8_sha256": hashlib.sha256(question_bytes).hexdigest(),
        "question_utf8_length": len(question_bytes),
        "outbound_prompt_utf8_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "outbound_prompt_utf8_length": len(prompt_bytes),
        "model_choice": body.model_choice.model_dump(mode="json"),
        "quote_digest": body.quote_digest,
        "action": _ACTION,
        "role": _ROLE,
        "max_output_tokens": _MAX_OUTPUT_TOKENS,
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _settled_estimates(row: OperationRow) -> tuple[Decimal, Decimal] | None:
    if (
        not isinstance(row.actual_cents, int)
        or not isinstance(row.cost_usd_estimate, str)
        or not isinstance(row.quote_estimate_usd, str)
        or len(row.cost_usd_estimate) > 80 or len(row.quote_estimate_usd) > 80
    ):
        return None
    try:
        cost = Decimal(row.cost_usd_estimate)
        quote = Decimal(row.quote_estimate_usd)
    except InvalidOperation:
        return None
    if (
        not cost.is_finite() or not quote.is_finite()
        or not 0 <= cost <= Decimal("1000000")
        or not 0 <= quote <= Decimal("1000000")
        or int((cost * 100).to_integral_value(rounding=ROUND_CEILING)) != row.actual_cents
    ):
        return None
    return cost, quote


def _terminal_replay(
    row: OperationRow | None, *, request_digest: str,
    body: QuickAskExecute,
) -> dict[str, object] | None:
    if row is None:
        return None
    if row.request_digest is None or row.request_digest != request_digest:
        raise HTTPException(status_code=409, detail="quick_ask_operation_conflict")
    if (
        (row.provider_id is not None and row.provider_id != body.model_choice.provider_id)
        or (row.model_id is not None and row.model_id != body.model_choice.model_id)
    ):
        raise HTTPException(status_code=409, detail="quick_ask_operation_conflict")
    settled_estimates = _settled_estimates(row) if row.state == "settled" else None
    if row.state == "settled" and (
        row.result_text is not None and row.actual_cents is not None
        and row.evidence_sha256 is not None and row.dispatch_event_id is not None
        and row.provider_id is not None and row.model_id is not None
        and settled_estimates is not None
    ):
        cost_estimate, quote_estimate = settled_estimates
        return {
            "answer": row.result_text,
            "operation_id": str(body.operation_id),
            "provider_id": row.provider_id,
            "model_id": row.model_id,
            # The same Antiek-calculated estimate shown on the first response;
            # actual_cents remains the rounded local budget-bookkeeping value.
            "estimated_cost_usd": float(cost_estimate),
            "reported_usage_estimate_exceeds_quote": cost_estimate > quote_estimate,
            "usage_basis": "prior_receipt",
            "input_tokens": None,
            "output_tokens": None,
            "replayed": True,
            "incomplete": row.finish_reason in {"length", "content_filter"},
        }
    if row.state == "unknown" and (
        row.result_text is not None
        and row.provider_id is not None and row.model_id is not None
    ):
        return {
            "answer": row.result_text,
            "operation_id": str(body.operation_id),
            "provider_id": row.provider_id,
            "model_id": row.model_id,
            "estimated_cost_usd": None,
            "reported_usage_estimate_exceeds_quote": None,
            "usage_basis": "charge_unknown",
            "input_tokens": None,
            "output_tokens": None,
            "replayed": True,
            "incomplete": row.finish_reason in {"length", "content_filter"},
        }
    detail = "charge_unknown" if row.state in {
        "sent", "settlement_pending", "unknown", "settled",
    } else "quick_ask_operation_conflict"
    raise HTTPException(status_code=409, detail=detail)


def _recent_receipt(row: OperationRow, operation_id: str) -> dict[str, object] | None:
    if (
        not isinstance(row.result_text, str) or not row.result_text
        or not isinstance(row.provider_id, str) or not row.provider_id
        or not isinstance(row.model_id, str) or not row.model_id
    ):
        return None
    if row.state == "unknown":
        return {
            "answer": row.result_text,
            "operation_id": operation_id,
            "provider_id": row.provider_id,
            "model_id": row.model_id,
            "estimated_cost_usd": None,
            "reported_usage_estimate_exceeds_quote": None,
            "usage_basis": "charge_unknown",
            "input_tokens": None,
            "output_tokens": None,
            "replayed": True,
            "incomplete": row.finish_reason in {"length", "content_filter"},
        }
    if (
        row.state != "settled"
        or not isinstance(row.evidence_sha256, str) or not row.evidence_sha256
        or not isinstance(row.dispatch_event_id, str) or not row.dispatch_event_id
    ):
        return None
    estimates = _settled_estimates(row)
    if estimates is None:
        return None
    cost_estimate, quote_estimate = estimates
    return {
        "answer": row.result_text,
        "operation_id": operation_id,
        "provider_id": row.provider_id,
        "model_id": row.model_id,
        "estimated_cost_usd": float(cost_estimate),
        "reported_usage_estimate_exceeds_quote": cost_estimate > quote_estimate,
        "usage_basis": "prior_receipt",
        "input_tokens": None,
        "output_tokens": None,
        "replayed": True,
        "incomplete": row.finish_reason in {"length", "content_filter"},
    }


def _quote(request: Request, owner: str, body: QuickAskInput) -> _Quote:
    prompt_digest = _prompt_digest(body.question)
    config = _config()
    authority, _, resolved = _freeze_current_authority(
        app=request.app,
        request_owner_user_id=owner,
        resource_owner_user_id=owner,
        document_id=f"quick-ask:{prompt_digest}",
        choice=body.model_choice,
        prompt=body.question,
        logical_operation_id=f"quick-ask:{body.operation_id}",
        resource_authority_digest=prompt_digest,
        config=config,
        role=_ROLE,
        action=_ACTION,
    )
    if resolved.model_id not in _APPROVED_MODELS:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    preset = get_provider_preset(resolved.record.provider_catalog_id or "")
    variant = get_model_variant(preset, resolved.model_id)
    match = _SNAPSHOT_DATE.search(variant.snapshot)
    if match is None:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    snapshot_date = date.fromisoformat(match.group(1))
    today = datetime.now(UTC).date()
    if not today - _PRICE_MAX_AGE <= snapshot_date <= today:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    rates = {rate.unit.value: rate.usd_per_unit for rate in variant.rates}
    if rates.get("input_token", 0) <= 0 or rates.get("output_token", 0) <= 0:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    estimated_usd = (
        Decimal(max(1, len(body.question.encode("utf-8")))) * rates["input_token"]
        + Decimal(_MAX_OUTPUT_TOKENS) * rates["output_token"]
    )
    return _Quote(
        authority_digest=authority.digest(),
        estimated_usd=estimated_usd,
        reserved_cents=authority.fallback_manifest[0].projected_max_cents,
        price_snapshot=variant.snapshot,
        price_source=preset.pricing_source,
        provider_id=resolved.record.id,
        model_id=resolved.model_id,
    )


@quick_ask_router.get("/models")
async def list_quick_ask_models(request: Request) -> dict[str, object]:
    """List only current, owner-bound variants that pass the quote predicate."""
    owner = _owner(request)
    try:
        records = models_admin._load_registry().values()
    except Exception:
        raise HTTPException(status_code=503, detail="quick_ask_models_unavailable") from None
    rows: list[dict[str, str]] = []
    for record in records:
        if record.owner_user_id != owner:
            continue
        for model_id in record.model_ids:
            try:
                choice = models_admin.UserModelChoice(
                    authority="user_model", provider_id=record.id, model_id=model_id,
                )
                quote = _quote(
                    request, owner,
                    QuickAskInput(
                        question="?", operation_id=_INVENTORY_OPERATION,
                        model_choice=choice,
                    ),
                )
            except Exception:
                continue
            rows.append({
                "provider_id": quote.provider_id,
                "model_id": quote.model_id,
                "display_name": record.display_name,
                "price_snapshot": quote.price_snapshot,
                "price_source": quote.price_source,
            })
    return {"models": rows, "count": len(rows)}


@quick_ask_router.get("/recent")
async def recent_quick_ask(request: Request, response: Response) -> dict[str, object]:
    try:
        owner = _owner(request)
    except HTTPException:
        raise HTTPException(
            status_code=401, detail="signed_owner_required",
            headers={"Cache-Control": _RECENT_CACHE_CONTROL},
        ) from None
    if request.query_params:
        raise HTTPException(
            status_code=400, detail="quick_ask_request_invalid",
            headers={"Cache-Control": _RECENT_CACHE_CONTROL},
        )
    response.headers["Cache-Control"] = _RECENT_CACHE_CONTROL
    try:
        rows = await run_in_threadpool(
            _ledger(request, read_only=True).recent_quick_ask_operations, owner,
        )
    except sqlite3.Error:
        raise HTTPException(
            status_code=503, detail="quick_ask_receipts_unavailable",
            headers={"Cache-Control": _RECENT_CACHE_CONTROL},
        ) from None
    operations: list[dict[str, object]] = []
    for row in rows:
        operation_id = row.operation_id.removeprefix("quick-ask:")
        result = _recent_receipt(row, operation_id)
        operations.append({
            "operation_id": operation_id,
            "created_at": row.created_at,
            "status": "answered" if result is not None else "charge_unknown",
            "result": result,
        })
    return {"operations": operations}


@quick_ask_router.post("/quote")
async def quote_quick_ask(request: Request) -> dict[str, object]:
    owner = _owner(request)
    body = await _body(request, QuickAskInput)
    try:
        quote = _quote(request, owner, body)
    except Exception:
        raise HTTPException(status_code=409, detail="quick_ask_model_unavailable") from None
    return {
        "quote_digest": quote.authority_digest,
        "estimate_usd": str(quote.estimated_usd),
        "reserved_cents": quote.reserved_cents,
        "price_snapshot": quote.price_snapshot,
        "price_source": quote.price_source,
        "provider_id": quote.provider_id,
        "model_id": quote.model_id,
        "max_output_tokens": _MAX_OUTPUT_TOKENS,
        "warning": _WARNING,
    }


@quick_ask_router.post("")
async def execute_quick_ask(request: Request) -> dict[str, object]:
    owner = _owner(request)
    parsed = await _body(request, QuickAskExecute)
    assert isinstance(parsed, QuickAskExecute)
    body = parsed
    ledger = _ledger(request)
    operation_id = f"quick-ask:{body.operation_id}"
    request_digest = _request_digest(owner, operation_id, body)
    prior = _terminal_replay(
        ledger.operation(owner, operation_id), request_digest=request_digest, body=body,
    )
    if prior is not None:
        return prior
    try:
        quote = _quote(request, owner, body)
    except Exception:
        prior = _terminal_replay(
            ledger.operation(owner, operation_id), request_digest=request_digest, body=body,
        )
        if prior is not None:
            return prior
        raise HTTPException(status_code=409, detail="quick_ask_model_unavailable") from None
    if quote.authority_digest != body.quote_digest:
        prior = _terminal_replay(
            ledger.operation(owner, operation_id), request_digest=request_digest, body=body,
        )
        if prior is not None:
            return prior
        raise HTTPException(status_code=409, detail="quick_ask_quote_changed")
    try:
        result, _ = await run_in_threadpool(
            dispatch_talk_to_book_byot,
            app=request.app,
            request_owner_user_id=owner,
            resource_owner_user_id=owner,
            document_id=f"quick-ask:{_prompt_digest(body.question)}",
            choice=body.model_choice,
            prompt=body.question,
            investigation_id=_event_scope(owner, body.operation_id),
            logical_operation_id=operation_id,
            resource_authority_digest=_prompt_digest(body.question),
            config=_config(),
            usage_ledger=ledger,
            role=_ROLE,
            action=_ACTION,
            expected_authority_digest=body.quote_digest,
            require_reported_usage=True,
            request_digest=request_digest,
            quote_estimate_usd=str(quote.estimated_usd),
        )
    except OwnerByotOutcomeUnknown:
        raise HTTPException(status_code=409, detail="charge_unknown") from None
    except OwnerByotDispatchUnavailable:
        row = ledger.operation(owner, operation_id)
        prior = _terminal_replay(row, request_digest=request_digest, body=body)
        if prior is not None:
            return prior
        detail = "quick_ask_operation_conflict"
        raise HTTPException(status_code=409, detail=detail) from None
    except Exception:
        raise HTTPException(status_code=503, detail="quick_ask_unavailable") from None
    if result.finish_reason in {"replayed", "charge_unknown_replay"}:
        prior = _terminal_replay(
            ledger.operation(owner, operation_id), request_digest=request_digest, body=body,
        )
        if prior is not None:
            return prior
        raise HTTPException(status_code=409, detail="quick_ask_operation_conflict")
    replay = result.finish_reason in {"replayed", "charge_unknown_replay"}
    unknown_charge = not result.usage.reported
    return {
        "answer": result.text,
        "operation_id": str(body.operation_id),
        "provider_id": result.provider,
        "model_id": result.model,
        "estimated_cost_usd": None if unknown_charge else result.cost_usd,
        "reported_usage_estimate_exceeds_quote": (
            None if replay or unknown_charge
            else Decimal(str(result.cost_usd)) > quote.estimated_usd
        ),
        "usage_basis": (
            "charge_unknown" if unknown_charge else
            "prior_receipt" if replay else "provider_reported_tokens_priced_locally"
        ),
        "input_tokens": None if replay or unknown_charge else result.usage.input_tokens,
        "output_tokens": None if replay or unknown_charge else result.usage.output_tokens,
        "replayed": replay,
        "incomplete": result.finish_reason in {"length", "content_filter"},
    }
