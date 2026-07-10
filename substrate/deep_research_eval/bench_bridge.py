"""Pull-based bridge to Antiek-bench: a ``by_task=deep_research`` record.

Pure function only — this module registers nothing, imports nothing that
mutates, and never touches antiek_bench state. The #465 owner pulls it into
the weekly cycle (see WIRING.md in this directory). Record keys follow the
``BenchRunResult.to_dict`` / ``BenchStore`` conventions in
``substrate/antiek_bench`` so the record slots into stored-run surfaces —
except ``view_format``, which is deliberately not "html" (v1 has no UI).
"""

from __future__ import annotations

from typing import Any, Final

from .runner import EvalRun

BENCH_TASK: Final = "deep_research"


class IncompleteRunError(ValueError):
    """Refusing to emit a bench record for an incomplete run (fail closed):
    a mean over a partial query subset would masquerade as a full-suite score."""


def deep_research_bench_record(run: EvalRun) -> dict[str, Any]:
    if not run.complete:
        raise IncompleteRunError(
            f"run {run.run_id} is incomplete ({run.measured_count}/{len(run.scores)} "
            "queries measured); refusing bench record"
        )
    return {
        "by_task": BENCH_TASK,
        "run_id": run.run_id,
        "week_id": run.week_id,
        "suite_version": f"{run.dataset_id}@{run.dataset_version}",
        "mean_score": run.mean_judge_score,
        "by_task_class": {BENCH_TASK: run.mean_judge_score},
        "by_axis": dict(run.mean_axis_scores),
        "coverage_hit_rate": run.mean_coverage_hit_rate,
        "query_count": len(run.scores),
        "measured_count": run.measured_count,
        "complete": run.complete,
        "comparability_key": list(run.comparability_key),
        "rubric_version": run.rubric_version,
        "judge_model_id": run.judge_model_id,
        "view_format": "none",
    }
