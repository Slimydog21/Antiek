"""Task discrimination — does a benchmark task actually separate models?

Operator vision (ask #11): *"the benchmark to be recursive where it learns from
usage patterns ... to re-write the benchmark ... so that I can know on a weekly
basis what models are best at what tasks."* The recursion's WHOLE POINT is to
discover which models are best at which tasks. But a task that EVERY model passes
(trivial) or EVERY model fails (impossible) carries ZERO discriminating signal —
it cannot tell models apart, so it teaches the recursion nothing and clutters the
weekly report with noise. The self-rewriting task engine (#1843) needs to know
which tasks discriminate so it can revise or graduate the ones that don't. No
module measures this.

**The measurement (hard to vary).** Given a task's pass/fail outcomes across
the models that attempted it:

* ``pass_rate = passes / attempts`` in ``[0.0, 1.0]`` — the fraction of models
  that passed.
* **Discrimination band** (load-bearing):
  - ``0.0 < pass_rate < 1.0`` → ``discriminates`` (at least one model passed AND
    at least one failed — the task separates models; this is the only band that
    carries ranking signal).
  - ``pass_rate == 1.0`` → ``trivial`` (every model passed — no separation; the
    task is too easy, a noise source for the recursion).
  - ``pass_rate == 0.0`` → ``impossible`` (every model failed — no separation; the
    task is too hard, also noise).
  - ``attempts == 0`` → ``unattempted`` (no models tried — ``None``, defer).

The module reports:

* ``pass_rate`` (``None`` when zero attempts).
* ``pass_count`` / ``fail_count`` / ``attempt_count``.
* ``discrimination`` verdict + ``passes_all`` / ``fails_all`` flags.
* ``task_id`` carried through (the route layer maps this to the task registry).

**Why pass_rate alone is the right signal (load-bearing, hard to vary).** A
benchmark task's discriminating POWER is exactly captured by whether it splits
the model set. The closer ``pass_rate`` is to ``0.5``, the MORE the task
discriminates (it splits the field evenly — maximum information). The closer to
``0.0`` or ``1.0``, the LESS it discriminates (near-trivial or near-impossible).
This is the binary-outcome analog of item-discrimination theory in psychometrics:
a test item that everyone gets right or everyone gets wrong tells you nothing
about the test-takers' relative ability. **No approximation, no invented weights**
— the pass/fail split IS the measurement.

**Honesty rules (load-bearing):**

* Zero attempts → ``pass_rate`` is ``None``, verdict ``unattempted`` (defer —
  never fabricated as 0.0 or 1.0; an unrun task has no signal).
* A single attempt is technically ``discriminates`` only if it's a pure 0 or 1
  split — but with ONE model, pass_rate is either 1.0 (trivial) or 0.0
  (impossible). The module reports this HONESTLY: a 1-of-1 pass is ``trivial``,
  not ``discriminates`` (one data point cannot prove separation — that would be
  fabricating discrimination from a sample of 1). A ``min_attempts`` floor
  (default 2) gates the ``discriminates`` verdict: below it, the verdict is
  ``insufficient_sample`` even if the split is mixed, and ``pass_rate`` is still
  reported (the raw signal is honest; the verdict is conservative).
* ``pass_rate`` is in ``[0.0, 1.0]``; ``pass_count + fail_count == attempt_count``.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Pure-Python, no imports beyond the standard
library. The task outcomes are a plain ``tuple[bool, ...]`` input (the route layer
supplies them from the bench runner's recorded results). This stays bar-clean on
frozen main independently — the recursion's meta-measurement exists before the
bench package merges.
"""

from __future__ import annotations

from dataclasses import dataclass

_DEFAULT_MIN_ATTEMPTS: int = 2


class TaskDiscriminationError(ValueError):
    """A task-discrimination input violates a load-bearing invariant."""


@dataclass(frozen=True)
class TaskDiscriminationReport:
    """One benchmark task's power to separate models. Advisory, pure."""

    task_id: str
    attempt_count: int
    pass_count: int
    fail_count: int
    pass_rate: float | None  # passes/attempts; None when zero attempts
    passes_all: bool  # every attempt passed (trivial)
    fails_all: bool  # every attempt failed (impossible)
    discrimination: str  # discriminates | trivial | impossible | insufficient_sample | unattempted
    min_attempts: int
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_task_discrimination(
    task_id: str,
    outcomes: tuple[bool, ...],
    *,
    min_attempts: int = _DEFAULT_MIN_ATTEMPTS,
) -> TaskDiscriminationReport:
    """Measure whether ``outcomes`` (pass/fail per model) discriminate.

    ``task_id`` identifies the benchmark task. ``outcomes`` is the per-model
    pass/fail list (``True`` = passed). Returns a
    :class:`TaskDiscriminationReport` with the pass rate + discrimination verdict.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if min_attempts < 1:
        raise TaskDiscriminationError(
            f"min_attempts must be >= 1, got {min_attempts!r}"
        )

    attempt_count = len(outcomes)
    pass_count = sum(1 for o in outcomes if o)
    fail_count = attempt_count - pass_count

    passes_all = attempt_count > 0 and pass_count == attempt_count
    fails_all = attempt_count > 0 and fail_count == attempt_count
    pass_rate = pass_count / attempt_count if attempt_count else None

    if attempt_count == 0:
        discrimination = "unattempted"
    elif passes_all:
        discrimination = "trivial"
    elif fails_all:
        discrimination = "impossible"
    elif attempt_count < min_attempts:
        discrimination = "insufficient_sample"
    else:
        discrimination = "discriminates"

    notes: list[str] = [
        "task discrimination measures whether a benchmark task separates models "
        "(some pass, some fail) — a task everyone passes (trivial) or everyone fails "
        "(impossible) carries zero ranking signal and clutters the recursion; this is "
        "the psychometric item-discrimination principle: a test item that splits the "
        "field tells you about relative ability, one that doesn't tells you nothing",
        "pass_rate near 0.5 = maximum discrimination (even split); near 0.0 or 1.0 = "
        "near-impossible or near-trivial (minimal signal); the discrimination verdict "
        "buckets this so the self-rewriting engine (#1843) can revise/graduate noise",
        f"min_attempts floor is {min_attempts}: below it, a mixed split is reported as "
        "insufficient_sample (one data point cannot PROVE separation — discrimination "
        "would be fabricated from a sample too small to support it); pass_rate is still "
        "honest, the verdict is conservative",
    ]
    if pass_rate is None:
        notes.append(
            "no attempts recorded — discrimination is not measurable (defer — never "
            "fabricated; an unrun task has no signal)"
        )
    else:
        notes.append(
            f"pass rate {pass_rate:.0%}: {pass_count} pass, {fail_count} fail of "
            f"{attempt_count} attempt(s) -> verdict {discrimination}"
        )

    return TaskDiscriminationReport(
        task_id=task_id,
        attempt_count=attempt_count,
        pass_count=pass_count,
        fail_count=fail_count,
        pass_rate=pass_rate,
        passes_all=passes_all,
        fails_all=fails_all,
        discrimination=discrimination,
        min_attempts=min_attempts,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "TaskDiscriminationError",
    "TaskDiscriminationReport",
    "measure_task_discrimination",
]
