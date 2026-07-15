"""Provider-neutral classification of non-settling billing evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final

MAX_EVIDENCE_BYTES: Final = 256 * 1024
MAX_EVIDENCE_DEPTH: Final = 16
MAX_EVIDENCE_ITEMS: Final = 10_000
MAX_EVIDENCE_TEXT: Final = 16 * 1024


class BillingEvidenceKind(StrEnum):
    PROVIDER_METERING = "provider_metering"
    DERIVED_LIST_PRICE = "derived_list_price"
    CUR_OPEN_PERIOD = "cur_open_period"
    CUR_FINAL_UNATTRIBUTABLE = "cur_final_unattributable"
    UNSUPPORTED = "unsupported"


class BillingClassification(StrEnum):
    PROVIDER_METERING_ONLY = "provider_metering_only"
    DERIVED_LIST_PRICE = "derived_list_price"
    CUR_AGGREGATE_OBSERVED = "cur_aggregate_observed"
    INVOICE_PERIOD_FINALIZED_UNATTRIBUTABLE = "invoice_period_finalized_unattributable"
    EXACT_JOB_FINAL_COST_UNAVAILABLE = "exact_job_final_cost_unavailable"


class BillingRefusalReason(StrEnum):
    METERING_NOT_USD = "metering_not_usd"
    DERIVED_NOT_INVOICED = "derived_not_invoiced"
    ADJUSTMENTS_UNALLOCATED = "adjustments_unallocated"
    PERIOD_NOT_FINAL = "period_not_final"
    JOB_JOIN_UNPROVEN = "job_join_unproven"
    EVIDENCE_UNSUPPORTED = "evidence_unsupported"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"
    DUPLICATE_EVIDENCE = "duplicate_evidence"
    TAG_JOIN_UNPROVEN = "tag_join_unproven"
    CALLER_ASSERTION_UNTRUSTED = "caller_assertion_untrusted"
    EVIDENCE_INVARIANT_FAILED = "evidence_invariant_failed"


@dataclass(frozen=True)
class BillingAssessment:
    assessment_id: str
    assessment_key: str
    submission_id: str
    evidence_kind: BillingEvidenceKind
    evidence_json: str
    raw_digest: str
    classification: BillingClassification
    reason_codes: tuple[BillingRefusalReason, ...]
    settlement_authorized: bool
    created_at: str


_CLASSIFICATIONS: Final = {
    BillingEvidenceKind.PROVIDER_METERING: (
        BillingClassification.PROVIDER_METERING_ONLY,
        (BillingRefusalReason.METERING_NOT_USD,),
    ),
    BillingEvidenceKind.DERIVED_LIST_PRICE: (
        BillingClassification.DERIVED_LIST_PRICE,
        (
            BillingRefusalReason.DERIVED_NOT_INVOICED,
            BillingRefusalReason.ADJUSTMENTS_UNALLOCATED,
        ),
    ),
    BillingEvidenceKind.CUR_OPEN_PERIOD: (
        BillingClassification.CUR_AGGREGATE_OBSERVED,
        (
            BillingRefusalReason.PERIOD_NOT_FINAL,
            BillingRefusalReason.JOB_JOIN_UNPROVEN,
        ),
    ),
    BillingEvidenceKind.CUR_FINAL_UNATTRIBUTABLE: (
        BillingClassification.INVOICE_PERIOD_FINALIZED_UNATTRIBUTABLE,
        (
            BillingRefusalReason.JOB_JOIN_UNPROVEN,
            BillingRefusalReason.ADJUSTMENTS_UNALLOCATED,
        ),
    ),
    BillingEvidenceKind.UNSUPPORTED: (
        BillingClassification.EXACT_JOB_FINAL_COST_UNAVAILABLE,
        (BillingRefusalReason.EVIDENCE_UNSUPPORTED,),
    ),
}

_COMMON_REQUIRED: Final = frozenset(
    {
        "account_digest",
        "job_arn",
        "model",
        "owner_id",
        "provider",
        "region",
        "run_id",
        "submission_id",
    }
)
_KIND_REQUIRED: Final = {
    BillingEvidenceKind.PROVIDER_METERING: frozenset(
        {
            "terminal_observation_digest",
            "manifest_object_identity",
            "manifest_object_version",
            "manifest_digest",
            "record_count",
            "input_token_count",
            "output_token_count",
            "retrieved_at",
        }
    ),
    BillingEvidenceKind.DERIVED_LIST_PRICE: frozenset(
        {
            "metering_digest",
            "rate_provider",
            "rate_model",
            "rate_region",
            "rate_tier",
            "rate_snapshot_digest",
            "input_rate_dec",
            "output_rate_dec",
            "input_token_count",
            "output_token_count",
            "calculated_cost_dec",
        }
    ),
    BillingEvidenceKind.CUR_OPEN_PERIOD: frozenset(
        {
            "report_identity",
            "billing_period",
            "product",
            "operation",
            "usage_type",
            "resource_id",
            "line_item_type",
            "usage_amount_dec",
            "rate_dec",
            "cost_dec",
            "tags",
            "ingested_at",
            "report_status",
        }
    ),
    BillingEvidenceKind.CUR_FINAL_UNATTRIBUTABLE: frozenset(
        {
            "report_identity",
            "billing_period",
            "product",
            "operation",
            "usage_type",
            "resource_id",
            "line_item_type",
            "usage_amount_dec",
            "rate_dec",
            "cost_dec",
            "tags",
            "ingested_at",
            "report_status",
        }
    ),
    BillingEvidenceKind.UNSUPPORTED: frozenset(),
}


def canonical_billing_evidence(value: object) -> str:
    """Return canonical redacted JSON, rejecting floats and invalid counters/decimals."""

    item_count = 0

    def validate(item: object, key: str = "evidence", depth: int = 0) -> object:
        nonlocal item_count
        item_count += 1
        if item_count > MAX_EVIDENCE_ITEMS:
            raise ValueError("billing evidence has too many values")
        if depth > MAX_EVIDENCE_DEPTH:
            raise ValueError("billing evidence is nested too deeply")
        if item is None or isinstance(item, (str, bool)):
            if isinstance(item, str) and len(item) > MAX_EVIDENCE_TEXT:
                raise ValueError(f"{key} is too long")
            if key.endswith("_dec") and (
                not isinstance(item, str)
                or re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?", item) is None
                or re.fullmatch(r"-0(?:\.0+)?", item) is not None
            ):
                raise ValueError(f"{key} must be a canonical decimal string")
            return item
        if isinstance(item, int) and not isinstance(item, bool):
            if key.endswith("_count") and item < 0:
                raise ValueError(f"{key} must be non-negative")
            return item
        if isinstance(item, list):
            return [validate(element, key, depth + 1) for element in item]
        if isinstance(item, dict) and all(isinstance(name, str) and name for name in item):
            return {name: validate(child, name, depth + 1) for name, child in item.items()}
        raise TypeError("billing evidence accepts JSON scalars without floats")

    encoded = json.dumps(validate(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(encoded.encode()) > MAX_EVIDENCE_BYTES:
        raise ValueError("billing evidence exceeds the canonical size limit")
    return encoded


def classify_billing_evidence(
    kind: BillingEvidenceKind,
    evidence: Mapping[str, object],
) -> tuple[BillingClassification, tuple[BillingRefusalReason, ...]]:
    if not isinstance(kind, BillingEvidenceKind):
        raise TypeError("kind must be BillingEvidenceKind")
    if not isinstance(evidence, Mapping):
        raise TypeError("evidence must be a mapping")
    unavailable = BillingClassification.EXACT_JOB_FINAL_COST_UNAVAILABLE
    claims = evidence.get("claims")
    if isinstance(claims, list):
        claimed: dict[str, object] = {}
        for claim in claims:
            if not isinstance(claim, dict) or set(claim) != {"field", "value"}:
                return unavailable, (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
            field = claim["field"]
            if not isinstance(field, str) or not field:
                return unavailable, (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
            if field in claimed and claimed[field] != claim["value"]:
                return unavailable, (BillingRefusalReason.CONTRADICTORY_EVIDENCE,)
            claimed[field] = claim["value"]
    rows = evidence.get("rows")
    if isinstance(rows, list) and len({canonical_billing_evidence(row) for row in rows}) != len(
        rows
    ):
        return unavailable, (BillingRefusalReason.DUPLICATE_EVIDENCE,)
    if evidence.get("tag_only") is True:
        return unavailable, (BillingRefusalReason.TAG_JOIN_UNPROVEN,)
    if evidence.get("line_item_type") in {"Credit", "Refund", "Tax"}:
        return unavailable, (BillingRefusalReason.ADJUSTMENTS_UNALLOCATED,)
    if evidence.get("matching_concurrent_jobs") not in (None, 1):
        return unavailable, (BillingRefusalReason.JOB_JOIN_UNPROVEN,)
    if "caller_classification" in evidence or "caller_finality" in evidence:
        return unavailable, (BillingRefusalReason.CALLER_ASSERTION_UNTRUSTED,)
    required = _COMMON_REQUIRED | _KIND_REQUIRED[kind]
    if any(name not in evidence or evidence[name] is None for name in required):
        return unavailable, (BillingRefusalReason.MISSING_REQUIRED_FIELD,)
    text_fields = required - {
        "record_count",
        "input_token_count",
        "output_token_count",
        "tags",
        "resource_id",
    }
    if any(not isinstance(evidence[name], str) or not evidence[name] for name in text_fields):
        return unavailable, (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
    if kind is BillingEvidenceKind.PROVIDER_METERING:
        counts = ("record_count", "input_token_count", "output_token_count")
        if any(
            isinstance(evidence[name], bool)
            or not isinstance(evidence[name], int)
            or evidence[name] < 0
            for name in counts
        ):
            return unavailable, (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
    if kind is BillingEvidenceKind.DERIVED_LIST_PRICE and (
        evidence["rate_provider"] != evidence["provider"]
        or evidence["rate_model"] != evidence["model"]
        or evidence["rate_region"] != evidence["region"]
    ):
        return unavailable, (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
    if kind is BillingEvidenceKind.DERIVED_LIST_PRICE:
        counts = ("input_token_count", "output_token_count")
        if any(
            isinstance(evidence[name], bool)
            or not isinstance(evidence[name], int)
            or evidence[name] < 0
            for name in counts
        ):
            return unavailable, (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
        calculated = (
            Decimal(str(evidence["input_rate_dec"])) * evidence["input_token_count"]
            + Decimal(str(evidence["output_rate_dec"])) * evidence["output_token_count"]
        )
        if calculated != Decimal(str(evidence["calculated_cost_dec"])):
            return unavailable, (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
    if kind is BillingEvidenceKind.CUR_OPEN_PERIOD and evidence["report_status"] != "open":
        return unavailable, (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
    if (
        kind is BillingEvidenceKind.CUR_FINAL_UNATTRIBUTABLE
        and evidence["report_status"] != "final"
    ):
        return unavailable, (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
    if kind in {
        BillingEvidenceKind.CUR_OPEN_PERIOD,
        BillingEvidenceKind.CUR_FINAL_UNATTRIBUTABLE,
    } and not isinstance(evidence["tags"], Mapping):
        return unavailable, (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)
    return _CLASSIFICATIONS[kind]


def billing_assessment_id(submission_id: str, assessment_key: str) -> str:
    encoded = canonical_billing_evidence(
        {
            "assessment_key": assessment_key,
            "domain": "research-provider-billing-assessment-v1",
            "submission_id": submission_id,
        }
    )
    return "rpba_" + hashlib.sha256(encoded.encode()).hexdigest()[:48]


__all__ = [
    "BillingAssessment",
    "BillingClassification",
    "BillingEvidenceKind",
    "BillingRefusalReason",
    "billing_assessment_id",
    "canonical_billing_evidence",
    "classify_billing_evidence",
]
