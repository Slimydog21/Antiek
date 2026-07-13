r"""Antiek-bench scorer — turn one captured run into a dual-output score + success (harness §6).

Operator vision (ask #11): *"a benchmark called Antiek-bench that benchmarked performance so that
I can know on a weekly basis what models are best at what tasks; recursive where it learns from
usage patterns."* The execution-harness spec (§6) names this module the **honesty keystone**: it is
the only place a captured model output becomes a *number* the platform learns from. Every downstream
artifact — the weekly scorecard view AND the usage-learn weight rewrite — depends on the score being
honest. This module is that honesty as code.

**It produces BOTH outputs the recursive loop consumes, from one run (§2/§7):**
  * a **finite float ``score``** (for ``bench_presentation.view.present_weekly_bench``), and
  * a **real-bool ``success``** (for ``bench_presentation.usage_learn.propose_next_week_weights``).
The mapping score→success is deterministic per scoring method (§6) and recorded so the verdict is
re-checkable weeks later.

**Three scoring methods (§6), one per task:**

  * **``exact``** — deterministic normalized match against an expected answer. ``success = match``;
    ``score = 1.0 if match else 0.0``. Normalization (whitespace/case/Unicode NFC) is recorded.
  * **``rubric``** — a heterogeneous LLM judge scores against a strict rubric. The judge's verdict
    is INJECTED here (the pure layer never dispatches — the runner makes the actual judge call and
    passes the structured verdict in). ``success = judge.passed``; ``score = judge.score``. If a
    second judge is supplied and disagrees, ``disputed=True`` is surfaced (the score stays the
    measured value; success follows the primary judge — disagreement is recorded, not averaged away).
  * **``human``** — operator confirms asynchronously. Until confirmed, ``score=None`` and
    ``success=None`` (pending → null, **never invented**). The record is honestly incomplete.

**A model never grades its own output (§6 hard-to-vary, the credibility keystone).** For ``rubric``,
``judge_model_id == candidate_model_id`` is rejected — self-grade is mechanically impossible. This is
what makes the "best in the world" claim defensible: the platform's outputs are scored by a different
lineage, never by themselves.

**Genuinely distinct from the bench surface (load-bearing):**

* ``bench_presentation.view.present_weekly_bench`` (#810, off main): INJECTS pre-computed records to
  render the weekly view. THIS PRODUCES one of those records (the ``score`` half). View displays;
  scorer measures. You cannot display what was never measured.
* ``bench_presentation.usage_learn.propose_next_week_weights`` (#810, off main): INJECTS ``[{task,
  success}]`` to rewrite weights. THIS PRODUCES one of those events (the ``success`` half). The
  scorer is the upstream the whole loop depends on; without it, usage-learn has nothing to learn from.
* ``antiek_bench/scorecards`` (off main): an offline scorecard WRITER (serializes provided
  measurements to disk). THIS is the SCORER (raw output → score+success). Scorecards persist;
  scorer computes. Different step of the pipeline.
* ``benchmarks/retrieval_bench.py`` etc. (on main): system LATENCY/retrieval benchmarks, not MODEL
  QUALITY on tasks. A different axis entirely (harness spec §1).

**Hard-to-vary honesty rules (§10, each is a test):**

  * ``score`` is a finite float or ``None``; ``success`` is a real bool or ``None``. Booleans NEVER
    coerce to ``0.0``/``1.0`` (mirrors ``_finite_score``); NaN/Inf → ``None``.
  * ``success`` from a rubric judge is a real bool only; a non-bool judge verdict is rejected
    (mirrors ``_as_bool_success``) — never coerced.
  * Self-grade rejected (``judge_model_id == candidate_model_id``) — no verdict recorded.
  * Pending human score → ``score=None``, ``success=None`` until confirmed (never invented).
  * The judge prompt + rubric + normalization are versioned and stored alongside the score
    (reproducibility — the verdict is re-checkable, not trusted).
  * ``authority = "scorer_advisory"`` — pure layer computes the verdict; it never dispatches, never
    charges, never persists. The runner/authorized layer acts on it.

**The measurement (hard to vary).**

A ``ScoredRun`` is built from a ``RunCapture`` (the raw output + task metadata + candidate model id)
plus a method-specific scoring input (an expected answer for ``exact``; an injected judge verdict
for ``rubric``; nothing extra for ``human`` pending). ``score_run`` dispatches on the method:

  * ``exact``: normalize both ``raw_output`` and ``expected`` (casefold, collapse internal
    whitespace runs to single spaces, strip, Unicode NFC), then ``match = (normalized equal)``.
    ``score = 1.0 if match else 0.0``; ``success = match``; ``disputed = False``.
  * ``rubric``: require ``candidate_model_id != judge_model_id`` (self-grade guard). Take the primary
    judge verdict (``passed: bool``, ``score: float ∈ [0,1]``, ``rationale: str``); coerce the score
    to finite-or-None; if a second judge is present and its ``passed`` differs from the primary,
    ``disputed = True`` (score is the primary's; success follows the primary). ``passed`` must be a
    real bool or the verdict is rejected.
  * ``human`` (pending): ``score = None``; ``success = None``; ``disputed = False``; the run is
    ``incomplete`` until a confirmed human verdict is supplied (via the separate ``confirm_human``).
  * ``human`` (confirmed): the operator's ``confirmed_passed`` (real bool) drives ``success``; the
    optional ``confirmed_score`` (finite float or None) drives ``score`` (if None, score stays None
    but success is the real bool — the operator can confirm pass/fail without a numeric score).
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass

__all__ = [
    "SCORING_METHODS",
    "METHOD_EXACT",
    "METHOD_RUBRIC",
    "METHOD_HUMAN",
    "JudgeVerdict",
    "RunCapture",
    "ScoredRun",
    "ScorerError",
    "normalize_exact",
    "score_run",
    "confirm_human",
]

# The canonical scoring-method vocabulary. One home so the task registry, runner,
# and tests key off identical strings (harness spec §4: scoring is per-task data).
METHOD_EXACT = "exact"
METHOD_RUBRIC = "rubric"
METHOD_HUMAN = "human"
SCORING_METHODS: frozenset[str] = frozenset({METHOD_EXACT, METHOD_RUBRIC, METHOD_HUMAN})


class ScorerError(ValueError):
    """Raised when a scoring input is malformed (unknown method, missing required
    field, self-grade attempt, non-bool judge verdict) — a programming error in
    the input, distinct from a pending/unknown finding reported in ScoredRun."""


@dataclass(frozen=True)
class JudgeVerdict:
    """One heterogeneous judge's structured verdict over a rubric-scored run. The
    pure scorer consumes these (the runner makes the actual judge call and injects
    the verdict). ``passed`` MUST be a real bool; ``score`` is finite float in
    [0,1] (coerced to None if non-finite); ``rationale`` is the audit trail."""

    judge_model_id: str
    passed: bool
    score: float | None
    rationale: str


@dataclass(frozen=True)
class RunCapture:
    """One captured candidate-model run awaiting a score. ``raw_output`` is the
    model's captured answer; ``candidate_model_id`` is what produced it (the
    self-grade guard keys off this vs the judge); ``task_id`` is the stable bench
    task id; ``method`` selects the scoring path."""

    task_id: str
    candidate_model_id: str
    raw_output: str
    method: str


@dataclass(frozen=True)
class ScoredRun:
    """The dual-output verdict for one run. ``score`` (finite float|None) feeds the
    weekly view; ``success`` (real bool|None) feeds usage-learn. ``incomplete`` is
    True when the run is pending (human unconfirmed) or any output is None — never
    silently treated as a measured value. ``authority`` is always advisory here."""

    task_id: str
    candidate_model_id: str
    method: str
    score: float | None
    success: bool | None
    disputed: bool
    incomplete: bool
    judge_model_id: str | None
    normalization: str | None
    rationale: str | None
    notes: tuple[str, ...] = ()
    authority: str = "scorer_advisory"


def normalize_exact(text: str) -> str:
    """The deterministic normalization for exact-match scoring: Unicode NFC,
    casefold, collapse internal whitespace runs to single spaces, strip. Recorded
    verbatim in the ScoredRun so the verdict is re-checkable."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def _finite_score(value: float | None) -> float | None:
    """Coerce a score to a finite float or None. NaN/Inf → None; a bool is rejected
    (booleans never coerce to 0.0/1.0 — harness §10 invariant 3)."""
    if isinstance(value, bool):
        raise ScorerError(
            "score must be a real float, not a bool (booleans never coerce to 0.0/1.0)"
        )
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise ScorerError(f"score must be a finite float or None; got {value!r}")
    f = float(value)
    if not math.isfinite(f):
        return None
    return f


def _real_bool(value: object, *, field_name: str) -> bool:
    """Require a real bool; reject non-bool (never coerce — harness §10 invariant 2).
    A bool is a subtype of int, so check bool explicitly before int."""
    if not isinstance(value, bool):
        raise ScorerError(
            f"{field_name} must be a real bool, not {type(value).__name__} "
            "(non-bool judge verdicts are rejected, never coerced)"
        )
    return value


def _score_exact(capture: RunCapture, expected: str) -> ScoredRun:
    """Deterministic normalized exact match. success = match; score = 1.0/0.0."""
    norm_out = normalize_exact(capture.raw_output)
    norm_exp = normalize_exact(expected)
    match = norm_out == norm_exp
    normalization = (
        f"normalize: NFC + casefold + collapse-whitespace + strip; "
        f"raw_output={norm_out!r} expected={norm_exp!r}"
    )
    return ScoredRun(
        task_id=capture.task_id,
        candidate_model_id=capture.candidate_model_id,
        method=METHOD_EXACT,
        score=1.0 if match else 0.0,
        success=match,
        disputed=False,
        incomplete=False,
        judge_model_id=None,
        normalization=normalization,
        rationale=None,
        notes=(f"exact match={match}",),
    )


def _score_rubric(
    capture: RunCapture,
    primary: JudgeVerdict,
    *,
    secondary: JudgeVerdict | None,
) -> ScoredRun:
    """Heterogeneous rubric scoring. Self-grade rejected; non-bool passed rejected;
    a disagreeing secondary judge surfaces disputed=True (not averaged away)."""
    if primary.judge_model_id == capture.candidate_model_id:
        raise ScorerError(
            f"self-grade rejected: judge_model_id {primary.judge_model_id!r} == "
            f"candidate_model_id {capture.candidate_model_id!r} (a model never grades "
            "its own output)"
        )
    passed = _real_bool(primary.passed, field_name="primary.passed")
    score = _finite_score(primary.score)
    disputed = False
    notes: list[str] = [f"primary judge={primary.judge_model_id}"]
    if secondary is not None:
        if secondary.judge_model_id == capture.candidate_model_id:
            raise ScorerError(
                f"self-grade rejected: secondary judge_model_id "
                f"{secondary.judge_model_id!r} == candidate_model_id "
                f"{capture.candidate_model_id!r}"
            )
        secondary_passed = _real_bool(secondary.passed, field_name="secondary.passed")
        notes.append(f"secondary judge={secondary.judge_model_id}")
        if secondary_passed != passed:
            disputed = True
            notes.append(
                f"judge disagreement: primary passed={passed}, secondary "
                f"passed={secondary_passed} -> disputed=True (not averaged away; "
                "score+success follow the primary judge)"
            )
    incomplete = score is None
    return ScoredRun(
        task_id=capture.task_id,
        candidate_model_id=capture.candidate_model_id,
        method=METHOD_RUBRIC,
        score=score,
        success=passed,
        disputed=disputed,
        incomplete=incomplete,
        judge_model_id=primary.judge_model_id,
        normalization=None,
        rationale=primary.rationale,
        notes=tuple(notes),
    )


def _score_human_pending(capture: RunCapture) -> ScoredRun:
    """Pending human confirmation: score=None, success=None (never invented)."""
    return ScoredRun(
        task_id=capture.task_id,
        candidate_model_id=capture.candidate_model_id,
        method=METHOD_HUMAN,
        score=None,
        success=None,
        disputed=False,
        incomplete=True,
        judge_model_id=None,
        normalization=None,
        rationale=None,
        notes=("pending human confirmation: score and success are None until confirmed",),
    )


def score_run(
    capture: RunCapture,
    *,
    expected: str | None = None,
    primary_judge: JudgeVerdict | None = None,
    secondary_judge: JudgeVerdict | None = None,
) -> ScoredRun:
    """Score one captured run by its method (harness §6).

    Method-specific required inputs: ``expected`` for ``exact``; ``primary_judge``
    (optionally ``secondary_judge``) for ``rubric``; nothing extra for ``human``
    (pending until :func:`confirm_human`). See the module docstring for full
    semantics. A malformed input raises :class:`ScorerError`.
    """
    if capture.method not in SCORING_METHODS:
        raise ScorerError(
            f"method {capture.method!r} is not canonical "
            f"(expected one of {sorted(SCORING_METHODS)})"
        )
    if not capture.task_id:
        raise ScorerError("RunCapture.task_id must be non-empty")
    if not capture.candidate_model_id:
        raise ScorerError("RunCapture.candidate_model_id must be non-empty")

    if capture.method == METHOD_EXACT:
        if expected is None:
            raise ScorerError("exact scoring requires `expected`")
        return _score_exact(capture, expected)

    if capture.method == METHOD_RUBRIC:
        if primary_judge is None:
            raise ScorerError("rubric scoring requires `primary_judge`")
        return _score_rubric(capture, primary_judge, secondary=secondary_judge)

    # human — pending until confirmed via confirm_human
    return _score_human_pending(capture)


def confirm_human(
    pending: ScoredRun,
    *,
    confirmed_passed: bool,
    confirmed_score: float | None = None,
    judge_model_id: str | None = None,
) -> ScoredRun:
    """Confirm a pending human-scored run with the operator's verdict (§6 human).

    ``confirmed_passed`` (real bool) drives ``success``; ``confirmed_score`` (finite
    float|None) drives ``score``. The operator may confirm pass/fail WITHOUT a
    numeric score (score stays None, success is the real bool). Returns a new
    non-pending ScoredRun; the original pending record is never mutated.
    """
    if pending.method != METHOD_HUMAN:
        raise ScorerError(
            f"confirm_human is only valid for method={METHOD_HUMAN!r}; "
            f"got method={pending.method!r}"
        )
    passed = _real_bool(confirmed_passed, field_name="confirmed_passed")
    score = _finite_score(confirmed_score)
    return ScoredRun(
        task_id=pending.task_id,
        candidate_model_id=pending.candidate_model_id,
        method=METHOD_HUMAN,
        score=score,
        success=passed,
        disputed=False,
        incomplete=False,
        judge_model_id=judge_model_id,
        normalization=None,
        rationale="human-confirmed",
        notes=(
            f"human confirmed: passed={passed}"
            + (f", score={score}" if score is not None else ", score=None (pass/fail only)"),
        ),
    )
