"""Antiek-bench recursive rewrite proposal (pure, advisory).

Learns from usage patterns to propose sub-benchmark rewrites.
applied is always False — never mutates production bench.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

UsageOutcome = Literal["worked", "failed", "mixed", "unknown"]


class AntiekBenchRewriteError(ValueError):
    """Fail-closed validation for bench rewrite proposals."""


@dataclass(frozen=True)
class UsagePattern:
    task_family: str
    model_id: str
    outcome: UsageOutcome
    n: float


@dataclass(frozen=True)
class SubBenchmarkProposal:
    sub_benchmark_id: str
    task_family: str
    rationale: str
    focus_models: tuple[str, ...]
    priority: float


@dataclass(frozen=True)
class BenchRewriteProposal:
    week_label: str
    proposals: tuple[SubBenchmarkProposal, ...]
    applied: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_label": self.week_label,
            "proposals": [
                {
                    "sub_benchmark_id": p.sub_benchmark_id,
                    "task_family": p.task_family,
                    "rationale": p.rationale,
                    "focus_models": list(p.focus_models),
                    "priority": p.priority,
                }
                for p in self.proposals
            ],
            "applied": False,
            "notes": list(self.notes),
            "authority": "antiek_bench_rewrite_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AntiekBenchRewriteError(f"{field} must be a non-empty string")
    return value.strip()


def propose_antiek_bench_recursive_rewrite(
    *,
    week_label: object,
    patterns: object,
) -> BenchRewriteProposal:
    week = _require_nonempty(week_label, field="week_label")
    if not isinstance(patterns, list):
        raise AntiekBenchRewriteError("patterns must be an array")

    notes: list[str] = [
        "applied=false — proposal only, production bench not mutated",
    ]

    if len(patterns) == 0:
        notes.append("no usage patterns — empty proposals (no invent)")
        return BenchRewriteProposal(
            week_label=week,
            proposals=(),
            applied=False,
            notes=tuple(notes),
            authority="antiek_bench_rewrite_advisory",
        )

    # task_family -> fail_weight, work_weight, models fail weight
    fail: dict[str, float] = {}
    work: dict[str, float] = {}
    models: dict[str, dict[str, float]] = {}

    for i, raw in enumerate(patterns):
        if not isinstance(raw, dict):
            raise AntiekBenchRewriteError(f"patterns[{i}] must be an object")
        task = _require_nonempty(raw.get("task_family"), field=f"patterns[{i}].task_family")
        model = _require_nonempty(raw.get("model_id"), field=f"patterns[{i}].model_id")
        outcome = raw.get("outcome")
        if outcome not in ("worked", "failed", "mixed", "unknown"):
            raise AntiekBenchRewriteError(
                f"patterns[{i}].outcome must be worked|failed|mixed|unknown"
            )
        n_raw = raw.get("n", 1)
        if not isinstance(n_raw, (int, float)) or isinstance(n_raw, bool):
            raise AntiekBenchRewriteError(
                f"patterns[{i}].n must be positive finite when set"
            )
        n = float(n_raw)
        if n != n or n <= 0 or n == float("inf"):
            raise AntiekBenchRewriteError(
                f"patterns[{i}].n must be positive finite when set"
            )

        fail.setdefault(task, 0.0)
        work.setdefault(task, 0.0)
        models.setdefault(task, {})

        if outcome == "failed":
            fail[task] += n
            models[task][model] = models[task].get(model, 0.0) + n
        elif outcome == "mixed":
            fail[task] += n * 0.5
            models[task][model] = models[task].get(model, 0.0) + n * 0.5
        elif outcome == "worked":
            work[task] += n
        else:
            notes.append(
                f"patterns[{i}] outcome=unknown ignored for rewrite weight (no invent failure)"
            )

    proposals: list[SubBenchmarkProposal] = []
    for task, fw in fail.items():
        if fw <= 0:
            continue
        focus = tuple(
            m for m, _w in sorted(models[task].items(), key=lambda kv: -kv[1])
        )
        if fw != fw or fw == float("inf"):
            raise AntiekBenchRewriteError("priority overflowed to non-finite")
        sid = "sb_" + re.sub(r"[^a-zA-Z0-9_-]+", "_", task)
        proposals.append(
            SubBenchmarkProposal(
                sub_benchmark_id=sid,
                task_family=task,
                rationale=(
                    f"Usage showed fail/mixed weight={fw} vs worked={work.get(task, 0.0)}; "
                    "differentiate models on this family."
                ),
                focus_models=focus,
                priority=fw,
            )
        )

    proposals.sort(key=lambda p: p.priority, reverse=True)
    notes.append(f"proposals={len(proposals)} from {len(fail)} task families")
    notes.append("applied=false")

    return BenchRewriteProposal(
        week_label=week,
        proposals=tuple(proposals),
        applied=False,
        notes=tuple(notes),
        authority="antiek_bench_rewrite_advisory",
    )


__all__ = [
    "AntiekBenchRewriteError",
    "BenchRewriteProposal",
    "SubBenchmarkProposal",
    "UsagePattern",
    "propose_antiek_bench_recursive_rewrite",
]
