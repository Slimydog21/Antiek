"""Pure whole-run admission envelope for the canonical Loop One call graph."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, Decimal

from skills.domain.keywords import DOMAIN_KEYWORDS
from substrate.constants import CONSTRAINT_MAX_ITERATIONS

from .research_quote import ResearchRouteManifest, ResearchRouteQuote

_PLAN_VERSION = 1
_MONEY_QUANTUM = Decimal("0.00000001")
_SYNTHESIS_ATTEMPTS_PER_PASS = 2  # initial call plus one structural repair
_KNOWLEDGE_ATTEMPTS_PER_DOMAIN = 2  # initial call plus one structural repair


class ResearchCostEnvelopeInvalid(ValueError):
    """The workload or accepted pricing cannot support an honest envelope."""


@dataclass(frozen=True)
class ResearchWorkloadRole:
    role: str
    mandatory_calls: int
    conditional_calls: int

    @property
    def max_calls(self) -> int:
        return self.mandatory_calls + self.conditional_calls


@dataclass(frozen=True)
class ResearchWorkloadPlan:
    schema_version: int
    max_sub_questions: int
    roles: tuple[ResearchWorkloadRole, ...]
    plan_sha256: str


@dataclass(frozen=True)
class ResearchRoleCostEnvelope:
    role: str
    mandatory_calls: int
    conditional_calls: int
    max_calls: int
    selected_route_only: bool
    route_max_usd: str
    role_max_usd: str
    pricing_fingerprints: tuple[str, ...]


@dataclass(frozen=True)
class ResearchWholeRunCostEnvelope:
    schema_version: int
    projection_kind: str
    plan_sha256: str
    maximum_usd: str
    forecast_usd_low: None
    forecast_usd_high: None
    forecast_status: str
    roles: tuple[ResearchRoleCostEnvelope, ...]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def build_loop_one_workload_plan(*, max_sub_questions: int = 8) -> ResearchWorkloadPlan:
    if type(max_sub_questions) is not int or not 1 <= max_sub_questions <= 20:
        raise ResearchCostEnvelopeInvalid("max_sub_questions is outside Loop One bounds")
    synthesis_max = CONSTRAINT_MAX_ITERATIONS * _SYNTHESIS_ATTEMPTS_PER_PASS
    knowledge_max = len(DOMAIN_KEYWORDS) * _KNOWLEDGE_ATTEMPTS_PER_DOMAIN
    roles = (
        ResearchWorkloadRole("decomposer", 1, 1),
        ResearchWorkloadRole("evidence_retriever", 1, max_sub_questions - 1),
        ResearchWorkloadRole("parameter_extractor", 1, 0),
        ResearchWorkloadRole("connector", 1, 0),
        ResearchWorkloadRole("synthesizer", 1, synthesis_max - 1),
        ResearchWorkloadRole("knowledge_extractor", 0, knowledge_max),
    )
    document = {
        "schema_version": _PLAN_VERSION,
        "max_sub_questions": max_sub_questions,
        "roles": [{**asdict(row), "max_calls": row.max_calls} for row in roles],
    }
    return ResearchWorkloadPlan(
        schema_version=_PLAN_VERSION,
        max_sub_questions=max_sub_questions,
        roles=roles,
        plan_sha256=hashlib.sha256(
            b"antiek.loop-one-workload-plan.v1\x00" + _canonical(document)
        ).hexdigest(),
    )


def _route_maximum_usd(route: ResearchRouteQuote) -> Decimal:
    try:
        currency = str(route.currency)
        billing_unit = str(route.billing_unit)
        context_tokens = int(route.context_budget_tokens)
        output_tokens = int(route.max_output_tokens)
        input_rate = Decimal(str(route.input_per_mtok))
        output_rate = Decimal(str(route.output_per_mtok))
        cached_input_rate = Decimal(str(route.cached_input_per_mtok))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ResearchCostEnvelopeInvalid("route pricing fields are invalid") from exc
    if currency != "USD" or billing_unit != "per_million_tokens":
        raise ResearchCostEnvelopeInvalid("route pricing unit is unsupported")
    if (
        context_tokens <= 0
        or output_tokens <= 0
        or input_rate < 0
        or output_rate < 0
        or cached_input_rate < 0
    ):
        raise ResearchCostEnvelopeInvalid("route token or pricing bound is invalid")
    if input_rate == 0 and output_rate == 0:
        raise ResearchCostEnvelopeInvalid("route pricing authority is unknown")
    conservative_input_rate = max(
        input_rate,
        cached_input_rate,
        input_rate * Decimal("1.25"),
    )
    return (
        (
            Decimal(context_tokens * 4) * conservative_input_rate
            + Decimal(output_tokens) * output_rate
        )
        / Decimal(1_000_000)
    ).quantize(_MONEY_QUANTUM, rounding=ROUND_CEILING)


def build_whole_run_cost_envelope(
    manifest: ResearchRouteManifest,
    *,
    selected_driver_role: str,
    selected_driver_provider: str,
    selected_driver_model: str,
    selected_driver_pricing_fingerprint: str,
    max_sub_questions: int = 8,
) -> ResearchWholeRunCostEnvelope:
    plan = build_loop_one_workload_plan(max_sub_questions=max_sub_questions)
    role_rows: list[ResearchRoleCostEnvelope] = []
    total = Decimal("0")
    for workload in plan.roles:
        routes = [row for row in manifest.routes if row.role == workload.role]
        if workload.role == selected_driver_role:
            routes = [
                row
                for row in routes
                if row.provider == selected_driver_provider
                and row.model == selected_driver_model
                and row.pricing_fingerprint == selected_driver_pricing_fingerprint
            ]
            selected_only = True
        else:
            selected_only = False
        if not routes:
            raise ResearchCostEnvelopeInvalid(
                f"accepted route manifest has no priceable {workload.role} route"
            )
        priced = [(_route_maximum_usd(row), row) for row in routes]
        route_max = max(value for value, _row in priced)
        role_max = (route_max * workload.max_calls).quantize(_MONEY_QUANTUM, rounding=ROUND_CEILING)
        total += role_max
        role_rows.append(
            ResearchRoleCostEnvelope(
                role=workload.role,
                mandatory_calls=workload.mandatory_calls,
                conditional_calls=workload.conditional_calls,
                max_calls=workload.max_calls,
                selected_route_only=selected_only,
                route_max_usd=f"{route_max:.8f}",
                role_max_usd=f"{role_max:.8f}",
                pricing_fingerprints=tuple(
                    sorted({row.pricing_fingerprint for _value, row in priced})
                ),
            )
        )
    return ResearchWholeRunCostEnvelope(
        schema_version=1,
        projection_kind="admission_upper_bound",
        plan_sha256=plan.plan_sha256,
        maximum_usd=f"{total.quantize(_MONEY_QUANTUM, rounding=ROUND_CEILING):.8f}",
        forecast_usd_low=None,
        forecast_usd_high=None,
        forecast_status="not_measured",
        roles=tuple(role_rows),
    )


__all__ = [
    "ResearchCostEnvelopeInvalid",
    "ResearchRoleCostEnvelope",
    "ResearchWholeRunCostEnvelope",
    "ResearchWorkloadPlan",
    "ResearchWorkloadRole",
    "build_loop_one_workload_plan",
    "build_whole_run_cost_envelope",
]
