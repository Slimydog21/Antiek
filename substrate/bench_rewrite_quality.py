"""Benchmark rewrite quality — did the self-rewrite improve the benchmark?

Operator vision (ask #11): *"a benchmark called Antiek-bench that benchmarked
performance ... I would like for the benchmark to be recursive where it learns
from usage patterns to understand what worked and what didn't in a given week to
re-write the benchmark (and sub-benchmarks within it of differentiating tasks as
the platform expands)."* The recursion's WHOLE POINT is that the benchmark
LEARNS — each weekly rewrite should keep what worked (discriminative tasks) and
drop what didn't (noise). But nothing measures whether the rewrite actually
IMPROVED anything. A rewrite that adds new noise while dropping working
discriminators is a REGRESSION masquerading as progress: the operator believes
the benchmark is learning, when it is forgetting. ``task_discrimination`` (#1960)
measures whether ONE task carries signal (static, per-task quality); it cannot
express "did the rewrite keep signal and drop noise?" — that is a SET-LEVEL,
LONGITUDINAL question across two benchmark snapshots.

**Genuinely distinct (static quality vs longitudinal delta).**
``task_discrimination`` answers "is task X good?" (one task, one snapshot). THIS
axis answers "did rewrite N→N+1 improve the benchmark?" (the whole task set, two
snapshots). The parallel: ``recursion_closure`` (#1961) measures whether a child
INVESTIGATION closed its parent question (the research recursion's success
metric); this measures whether a BENCHMARK REWRITE improved on its prior version
(the benchmark recursion's success metric). Both are "did the recursion succeed"
for different recursion types — and both were previously open loops (the
recursion ran, but nothing checked whether it WORKED).

**The measurement (hard to vary).** Given two benchmark snapshots — ``old``
(prior version) and ``new`` (after rewrite) — each a mapping of ``task_id`` to a
discrimination band (``"discriminates"`` / ``"trivial"`` / ``"impossible"`` /
``"unattempted"``):

Each task is classified by its band:

* ``SIGNAL`` — ``discriminates`` (at least one model passed AND one failed — the
  task separates models; this is the only band that carries ranking signal).
* ``NOISE`` — ``trivial`` (every model passed) or ``impossible`` (every model
  failed) — no separation; clutter for the weekly report.
* ``UNEVALUATED`` — ``unattempted`` (no models tried — could go either way;
  excluded from signal/noise judgment, never fabricated as noise).

The rewrite's changes decompose into a 4-way set analysis:

* **Retained** (in both old and new):
  - ``preserved_signal``: SIGNAL→SIGNAL (kept a working discriminator — good for
    stability; the recursion's "keep what worked").
  - ``recovered``: NOISE→SIGNAL (a noise task became discriminative — the rewrite
    FIXED it).
  - ``lost_signal``: SIGNAL→NOISE/UNEVALUATED (a working discriminator stopped
    working — REGRESSION within retained).
* **Added** (in new, not old):
  - ``added_signal``: new SIGNAL task (the rewrite discovered new signal).
  - ``added_noise``: new NOISE task (the rewrite introduced new clutter).
* **Removed** (in old, not new):
  - ``removed_signal``: dropped SIGNAL task (REGRESSION — lost a working
    discriminator; the recursion's worst failure: it FORGOT what worked).
  - ``removed_noise``: dropped NOISE task (the rewrite cleaned up clutter — good).

The net quality:

* ``positive = added_signal + removed_noise + recovered`` (changes that helped).
* ``negative = removed_signal + added_noise + lost_signal`` (changes that hurt).
* ``net_benefit = positive - negative``.
* ``improvement_ratio = positive / (positive + negative)`` (``None`` when zero
  changes — defer, never ``0.0``/``1.0``).

The verdict:

* both snapshots empty (or all tasks unevaluated) → ``unknown`` (no measurable
  content — defer, never fabricated).
* ``net_benefit > 0`` → ``improved`` (the rewrite was a net positive).
* ``net_benefit < 0`` → ``regressed`` (the rewrite was a net negative).
* ``net_benefit == 0`` → ``neutral`` (the rewrite broke even — or made no
  measurable change).

**Regression is the critical signal (load-bearing).** The operator's directive
"learn what worked and what didn't" means PRESERVING what worked is the baseline
duty. A rewrite that drops a working discriminator (``removed_signal`` or
``lost_signal``) is worse than one that simply adds nothing — it destroys
verified signal. The module carries ``regressed_signal_count`` (removed_signal +
lost_signal) as a standalone regression surface so the operator sees FORGETTING
separately from EXPLORATION, even when the net verdict is ``improved`` (a rewrite
can be net-improved while still regressing on specific tasks — both facts matter).

**Honesty rules (load-bearing):**

* ``unknown`` when both snapshots are empty or every task is unevaluated (never
  ``improved``/``regressed`` — fabricating a verdict on unmeasured content would
  hide a non-learning benchmark behind a phony verdict).
* ``improvement_ratio`` is ``None`` when zero changes (no positive + no negative
  — defer, never ``0.0``/``1.0``).
* ``unattempted`` tasks are ``UNEVALUATED`` — excluded from signal/noise
  classification (carried as ``unevaluated_*`` counts) — fabricating a noise
  verdict on an unrun task would conflate "not yet tried" with "confirmed
  clutter."
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** The ``antiek_bench`` package is not on
frozen origin/main (so importing ``task_discrimination`` would break the bar on
frozen main). This module defines its own band constants and takes plain
``dict[str, str]`` snapshots (the route layer adapts: it calls
``task_discrimination`` per task, then passes the two id→band maps).
"""

from __future__ import annotations

from dataclasses import dataclass

SIGNAL = "discriminates"
NOISE_TRIVIAL = "trivial"
NOISE_IMPOSSIBLE = "impossible"
UNEVALUATED = "unattempted"

_NOISE_BANDS = frozenset({NOISE_TRIVIAL, NOISE_IMPOSSIBLE})


class BenchRewriteQualityError(ValueError):
    """A benchmark-rewrite-quality input violates a load-bearing invariant."""


def _classify(band: str) -> str:
    """Map a discrimination band to SIGNAL / NOISE / UNEVALUATED."""
    if band == SIGNAL:
        return "signal"
    if band in _NOISE_BANDS:
        return "noise"
    return "unevaluated"


@dataclass(frozen=True)
class RewriteQualityReport:
    """The benchmark self-rewrite's improvement profile. Advisory, pure."""

    positive_count: int  # added_signal + removed_noise + recovered
    negative_count: int  # removed_signal + added_noise + lost_signal
    net_benefit: int  # positive - negative
    improvement_ratio: float | None  # positive/(positive+negative); None if 0 changes
    preserved_signal: int  # retained SIGNAL->SIGNAL
    recovered: int  # retained NOISE->SIGNAL
    lost_signal: int  # retained SIGNAL->non-signal (regression within retained)
    added_signal: int  # new SIGNAL task
    added_noise: int  # new NOISE task
    removed_signal: int  # dropped SIGNAL task (regression)
    removed_noise: int  # dropped NOISE task (cleanup)
    preserved_noise: int  # retained NOISE->NOISE
    added_unevaluated: int  # new UNEVALUATED task (neutral)
    removed_unevaluated: int  # dropped UNEVALUATED task (neutral)
    retained_unevaluated: int  # retained UNEVALUATED (neutral)
    signal_count_old: int  # total SIGNAL tasks in old
    signal_count_new: int  # total SIGNAL tasks in new
    noise_count_old: int
    noise_count_new: int
    regressed_signal_count: int  # removed_signal + lost_signal (the forgetting surface)
    has_regression: bool  # True if any working discriminator was lost
    verdict: str  # improved | regressed | neutral | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_rewrite_quality(
    old_snapshot: dict[str, str],
    new_snapshot: dict[str, str],
) -> RewriteQualityReport:
    """Measure whether a benchmark self-rewrite improved on its prior version.

    ``old_snapshot`` and ``new_snapshot`` are mappings of ``task_id`` to a
    discrimination band (``"discriminates"`` / ``"trivial"`` / ``"impossible"`` /
    ``"unattempted"``) — the prior and rewritten benchmark versions. Returns a
    :class:`RewriteQualityReport` with the 4-way set decomposition + net verdict.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    valid_bands = {SIGNAL, NOISE_TRIVIAL, NOISE_IMPOSSIBLE, UNEVALUATED}
    for label, snap in (("old_snapshot", old_snapshot), ("new_snapshot", new_snapshot)):
        for task_id, band in snap.items():
            if not task_id or not task_id.strip():
                raise BenchRewriteQualityError(
                    f"{label} contains an empty task_id"
                )
            if band not in valid_bands:
                raise BenchRewriteQualityError(
                    f"{label} task {task_id!r} has invalid band {band!r}; "
                    f"expected one of {sorted(valid_bands)}"
                )

    old_class = {tid: _classify(b) for tid, b in old_snapshot.items()}
    new_class = {tid: _classify(b) for tid, b in new_snapshot.items()}

    old_ids = set(old_snapshot)
    new_ids = set(new_snapshot)
    retained = old_ids & new_ids
    added = new_ids - old_ids
    removed = old_ids - new_ids

    preserved_signal = 0
    recovered = 0
    lost_signal = 0
    preserved_noise = 0
    retained_unevaluated = 0

    for tid in retained:
        o = old_class[tid]
        n = new_class[tid]
        if o == "signal" and n == "signal":
            preserved_signal += 1
        elif o == "noise" and n == "signal":
            recovered += 1
        elif o == "signal" and n != "signal":
            lost_signal += 1
        elif o == "noise" and n == "noise":
            preserved_noise += 1
        else:
            retained_unevaluated += 1

    added_signal = sum(1 for tid in added if new_class[tid] == "signal")
    added_noise = sum(1 for tid in added if new_class[tid] == "noise")
    added_unevaluated = sum(1 for tid in added if new_class[tid] == "unevaluated")

    removed_signal = sum(1 for tid in removed if old_class[tid] == "signal")
    removed_noise = sum(1 for tid in removed if old_class[tid] == "noise")
    removed_unevaluated = sum(
        1 for tid in removed if old_class[tid] == "unevaluated"
    )

    positive = added_signal + removed_noise + recovered
    negative = removed_signal + added_noise + lost_signal
    net = positive - negative
    improvement_ratio = positive / (positive + negative) if (positive + negative) else None

    signal_count_old = sum(1 for c in old_class.values() if c == "signal")
    signal_count_new = sum(1 for c in new_class.values() if c == "signal")
    noise_count_old = sum(1 for c in old_class.values() if c == "noise")
    noise_count_new = sum(1 for c in new_class.values() if c == "noise")

    regressed_signal_count = removed_signal + lost_signal
    has_regression = regressed_signal_count > 0

    measurable_tasks = sum(
        1 for c in (*old_class.values(), *new_class.values()) if c != "unevaluated"
    )
    if measurable_tasks == 0 and positive + negative == 0:
        verdict = "unknown"
    elif net > 0:
        verdict = "improved"
    elif net < 0:
        verdict = "regressed"
    else:
        verdict = "neutral"

    ratio_str = (
        f"{improvement_ratio:.0%}" if improvement_ratio is not None else "n/a"
    )
    notes: list[str] = [
        "benchmark rewrite quality measures whether a self-rewrite IMPROVED the "
        "benchmark — the recursion's success metric for ask #11; task_discrimination "
        "#1960 measures one task's static quality (is it good?), this measures the "
        "longitudinal delta (did the rewrite keep signal and drop noise?)",
        "4-way decomposition: positive = added_signal + removed_noise + recovered "
        "(new signal discovered + clutter cleaned + noise fixed); negative = "
        "removed_signal + added_noise + lost_signal (working discriminator dropped + "
        "new clutter introduced + signal stopped working)",
        "regression is the critical signal: the operator's 'learn what worked' "
        "directive means PRESERVING working discriminators is the baseline duty — a "
        "rewrite that drops signal (removed_signal + lost_signal) is FORGETTING, "
        "carried as regressed_signal_count even when the net verdict is improved "
        "(a rewrite can be net-positive while still regressing on specific tasks)",
        "unknown when both snapshots are empty or all tasks unevaluated (never "
        "fabricated improved/regressed — hides a non-learning benchmark behind a "
        "phony verdict); improvement_ratio None when zero changes (defer, never "
        "0.0/1.0); unattempted tasks are UNEVALUATED (excluded from signal/noise, "
        "never fabricated as confirmed clutter)",
        "the parallel: recursion_closure #1961 measures whether a child investigation "
        "closed its parent question (research recursion success); this measures "
        "whether a benchmark rewrite improved on its prior version (benchmark "
        "recursion success) — both were open loops where the recursion ran but "
        "nothing checked whether it WORKED",
    ]
    notes.append(
        f"verdict {verdict}: net_benefit {net:+d} ({positive} positive, {negative} "
        f"negative), improvement_ratio {ratio_str}; signal pool "
        f"{signal_count_old}->{signal_count_new}, noise pool "
        f"{noise_count_old}->{noise_count_new}; "
        f"regressed_signal_count {regressed_signal_count}"
    )

    return RewriteQualityReport(
        positive_count=positive,
        negative_count=negative,
        net_benefit=net,
        improvement_ratio=improvement_ratio,
        preserved_signal=preserved_signal,
        recovered=recovered,
        lost_signal=lost_signal,
        added_signal=added_signal,
        added_noise=added_noise,
        removed_signal=removed_signal,
        removed_noise=removed_noise,
        preserved_noise=preserved_noise,
        added_unevaluated=added_unevaluated,
        removed_unevaluated=removed_unevaluated,
        retained_unevaluated=retained_unevaluated,
        signal_count_old=signal_count_old,
        signal_count_new=signal_count_new,
        noise_count_old=noise_count_old,
        noise_count_new=noise_count_new,
        regressed_signal_count=regressed_signal_count,
        has_regression=has_regression,
        verdict=verdict,
        notes=tuple(notes),
    )
