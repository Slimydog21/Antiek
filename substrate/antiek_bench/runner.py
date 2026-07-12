"""Benchmark runner — the provider-dispatch boundary.

Composes a :class:`BenchTask`, an injectable :class:`ModelCaller`, and the
appropriate scorer into one scored run. The runner is the place where the
\"run\" half of the recursive loop actually happens: invoke the candidate model
on the task prompt → capture raw output + cost metadata → score it → return a
:class:`ScoreVerdict` ready for the recorder.

**No network in the pure layer.** The actual provider call lives behind the
:class:`ModelCaller` protocol; tests pass a fake. The pure runner never holds
live credentials, never imports a provider SDK, and never invents cost.

Authority split (matches Midnight Oil #1000 + doctrine): the pure runner sets
``live_dispatch_authorized=False`` and ``charge_executed=False`` on every run
result. A **separate authorized runner** (future module, behind the budget gate)
sets these only after operator spend-consent + the LIVE ``would_exceed_budget``
check. Cheapest/local models run ungated; only paid dispatch needs the gate.

Deterministic invocation: fixed temperature/seed (recorded on the result) for
reproducibility. One invocation per ``(task_id, model_id, week_id)`` unless the
task declares ``n_runs > 1`` (aggregation is the caller's job, not the runner's).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .scorer import (
    ExactScorer,
    HumanScorer,
    RubricJudge,
    RubricScorer,
    ScoreVerdict,
)
from .task_registry import BenchTask

# Fixed for reproducibility (recorded on every RunResult).
DEFAULT_TEMPERATURE: float = 0.0
DEFAULT_SEED: int = 0


class ModelCaller(Protocol):
    """The provider-dispatch boundary. Implementations hold the live HTTP call.

    The pure runner never imports a provider SDK; it calls through this
    protocol. ``cost_usd`` is the **provider-reported** figure — if the provider
    reports none, return ``None`` (the runner never invents 0).
    """

    model_id: str

    def invoke(
        self,
        *,
        prompt: str,
        temperature: float,
        seed: int,
    ) -> RawModelOutput:
        ...


@dataclass(frozen=True)
class RawModelOutput:
    """Raw output + cost metadata from one model invocation."""

    model_id: str
    raw_output: str
    tokens: int | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None  # provider-reported; None = not reported (never 0)


@dataclass(frozen=True)
class RunResult:
    """One scored run: the verdict + the raw output/cost metadata + authority flags.

    ``live_dispatch_authorized`` and ``charge_executed`` are hardcoded ``False``
    in the pure runner. The authorized runner (behind the budget gate) sets them
    only after operator consent.
    """

    verdict: ScoreVerdict
    raw: RawModelOutput
    week_id: str
    temperature: float = DEFAULT_TEMPERATURE
    seed: int = DEFAULT_SEED
    live_dispatch_authorized: bool = False
    charge_executed: bool = False


def run_and_score(
    *,
    task: BenchTask,
    caller: ModelCaller,
    week_id: str,
    rubric_judge: RubricJudge | None = None,
    second_judge: RubricJudge | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int = DEFAULT_SEED,
) -> RunResult:
    """Invoke a candidate model on a task, score the output, return a RunResult.

    Selects the scorer by ``task.scoring``:

    - ``exact`` → :class:`ExactScorer` (deterministic normalised match).
    - ``rubric`` → :class:`RubricScorer` (requires ``rubric_judge``; self-grade
      is mechanically rejected by the scorer).
    - ``human`` → :class:`HumanScorer` in pending state (the operator confirms
      asynchronously; the run is incomplete until then).

    The runner does NOT aggregate multiple runs — that is the weekly
    orchestrator's job. One call here = one invocation.
    """

    raw = caller.invoke(prompt=task.prompt, temperature=temperature, seed=seed)

    if task.scoring == "exact":
        verdict = ExactScorer().score(task=task, candidate_output=raw.raw_output)
        verdict = _stamp_candidate(verdict, raw.model_id)
    elif task.scoring == "rubric":
        if rubric_judge is None:
            raise ValueError(
                f"rubric task {task.task_id!r} requires a rubric_judge (different lineage)"
            )
        verdict = RubricScorer(rubric_judge, second_judge=second_judge).score(
            task=task,
            candidate_output=raw.raw_output,
            candidate_model_id=raw.model_id,
        )
    elif task.scoring == "human":
        verdict = HumanScorer().pending(task=task, candidate_model_id=raw.model_id)
    else:
        raise ValueError(f"unknown scoring method {task.scoring!r}")

    return RunResult(
        verdict=verdict,
        raw=raw,
        week_id=week_id,
        temperature=temperature,
        seed=seed,
        live_dispatch_authorized=False,
        charge_executed=False,
    )


def _stamp_candidate(verdict: ScoreVerdict, model_id: str) -> ScoreVerdict:
    """Exact scoring is model-agnostic; stamp the candidate id post-score."""
    return verdict.model_copy(update={"candidate_model_id": model_id})
