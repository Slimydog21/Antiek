"""Pure declaration and accounting for research budget run records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import Any, cast

from .tiers import TierBudget


class BudgetVerdict(StrEnum):
    WITHIN = "within"
    WARNED = "warned"
    EXCEEDED = "exceeded"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    tier: str
    declared: TierBudget
    tokens_spent: int = 0
    tool_calls_made: int = 0
    verdict: BudgetVerdict = BudgetVerdict.WITHIN

    def to_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "tier": self.tier,
            "declared": asdict(self.declared),
            "actuals": {
                "tokens_spent": self.tokens_spent,
                "tool_calls_made": self.tool_calls_made,
            },
            "verdict": self.verdict.value,
        }


def declare_run(run_id: str, tier: str, budget: TierBudget) -> RunRecord:
    if not run_id.strip() or not tier.strip():
        raise ValueError("run_id and tier must be non-empty")
    return RunRecord(run_id=run_id, tier=tier, declared=budget)


def _verdict(tokens: int, calls: int, budget: TierBudget) -> BudgetVerdict:
    if tokens > budget.token_budget or calls > budget.max_tool_calls:
        return BudgetVerdict.EXCEEDED
    if tokens * 5 >= budget.token_budget * 4 or calls * 5 >= budget.max_tool_calls * 4:
        return BudgetVerdict.WARNED
    return BudgetVerdict.WITHIN


def accumulate_actuals(
    record: RunRecord, *, tokens_spent: int = 0, tool_calls_made: int = 0
) -> RunRecord:
    if tokens_spent < 0 or tool_calls_made < 0:
        raise ValueError("actual increments must be non-negative")
    tokens = record.tokens_spent + tokens_spent
    calls = record.tool_calls_made + tool_calls_made
    return replace(
        record,
        tokens_spent=tokens,
        tool_calls_made=calls,
        verdict=_verdict(tokens, calls, record.declared),
    )


def parse_run_record(payload: Mapping[str, Any]) -> RunRecord:
    declared = cast(Mapping[str, Any], payload["declared"])
    actuals = cast(Mapping[str, Any], payload["actuals"])
    return RunRecord(
        run_id=str(payload["run_id"]),
        tier=str(payload["tier"]),
        declared=TierBudget(
            breadth=int(declared["breadth"]),
            depth=int(declared["depth"]),
            token_budget=int(declared["token_budget"]),
            max_tool_calls=int(declared["max_tool_calls"]),
        ),
        tokens_spent=int(actuals["tokens_spent"]),
        tool_calls_made=int(actuals["tool_calls_made"]),
        verdict=BudgetVerdict(str(payload["verdict"])),
    )
