"""AFA-S2 (M2) — frame-attention Invalid-Traffic (IVT) classification.

Filter-before-allocate: invalid frame-attention seconds are NON-BILLABLE, not
merely flagged (the MRC IVT model). This module is the pure classifier; the
accrual integration (AFA-S2 M5) excludes the seconds this module marks invalid
from BOTH the numerator and the denominator of the per-window split, and reports
the exclusion counts — never silently drops a second.

SCOPE OF THIS MODULE, HONESTLY (rigor #1):
  * M2 (built): GIVT — General Invalid Traffic. Mechanically-impossible or
    self-contradictory batches: duplicated/non-monotonic second indices, sample
    geometry that cannot co-occur, an implausibly large batch. These are
    deterministic FACTS about the batch, not judgements — high confidence; they
    mark individual seconds NON-BILLABLE.
  * M3 (built): SIVT — Sophisticated Invalid Traffic. Behavioural implausibility
    over a long-enough window (constant-attention signature, implausible focus
    marathon). HEURISTIC, honestly labelled — real false-positive/negative
    rates, so a SIVT hit is a REVIEW-tier WINDOW signal (operator queue), never
    a silent per-second drop. The parallel-window-count signal needs cross-window
    session state and lands in M5's integration (where request identity is
    available), NOT in this single-batch pure function.
  * M4 (next): per-identity saturation caps (a clamp, not a classifier).

A GIVT rule is a FACT ("index 3 appears twice"); it does not need calibration.
That is why GIVT lands first and standalone: it is provable, and its passed-good
near-misses (a single dropped-tick gap is LEGITIMATE, not invalid) are equally
provable.

PURE + CLOCK-FREE (rigor #3): the classification DECISION (which seconds are
invalid, and the window verdict kind + signals) is a pure function of the batch
plus server-supplied receipt metadata. No DB, no ``now()`` inside the logic.
(The returned ``FraudVerdict`` stamps an audit ``decided_at`` via its own
default_factory — metadata, exactly as every existing detector does; tests
assert on ``kind`` + ``signals``, never on ``decided_at``.)
"""

from __future__ import annotations

from dataclasses import dataclass

from substrate.ad_inventory.frame_attention import (
    FrameSecond,
    WindowFrameBatch,
)
from substrate.anti_gaming.verdict import (
    BLOCK_THRESHOLD,
    REVIEW_THRESHOLD,
    FraudSignal,
    FraudVerdict,
    FraudVerdictKind,
)

# ---------------------------------------------------------------------------
# Tunables — every constant carries its derivation (rigor #5). These are GIVT
# ceilings, not SIVT thresholds; they bound the mechanically-impossible, so they
# are set generously (a legitimate session must never trip them).
# ---------------------------------------------------------------------------

# A window is one lens-session in the reading app; it rolls on lens change and
# the emitter flushes on a 30s ceiling. Even a multi-hour uninterrupted read is
# a few thousand seconds. 24h = 86_400s is a hard "no honest window is this
# long" ceiling — beyond it the batch is fabricated, not measured.
MAX_WINDOW_SECONDS = 86_400

# --- SIVT (M3) tunables. These are HEURISTIC thresholds, not facts — set to
# minimise false positives on real reading, and their hits produce REVIEW-tier
# signals (operator queue), never a silent per-second drop. ---

# SIVT signatures are only meaningful over a long-enough window: a 3-second
# window can legitimately show identical vectors. 30s is the emitter's flush
# ceiling — a natural "enough signal to judge a pattern" floor. Below it, SIVT
# is not evaluated (too little data → presumed innocent).
MIN_SIVT_WINDOW_SECONDS = 30

# Constant-attention: real reading JITTERS — scrolling and pausing change the
# in-frame geometry second to second, so the exact (asset, area, prominence,
# dwell) tuple rarely repeats. A window where >90% of valid seconds share ONE
# modal tuple is a replayed/synthetic sample. 0.9 (not 1.0) tolerates a genuinely
# static layout briefly; the residual false-positive risk is why it is
# REVIEW-tier, not BLOCK.
CONSTANT_VECTOR_FRACTION = 0.9

# Focus-marathon: you can read for a long time, but sustained PERFECT
# uninterrupted focus with frozen geometry is bot-like — real long reads include
# glancing/scrolling seconds (the sampler's 250ms dwell) and area variation.
# Trip only when mean dwell is essentially pinned at the 1000ms max AND the
# viewport area barely varies AND there are NO scrolled-past seconds.
MARATHON_DWELL_MEAN_MS = 995.0
MARATHON_AREA_VARIANCE_MAX = 1e-4

# SIVT signal weight — deliberately in the REVIEW band ([0.45, 0.75)): a single
# heuristic hit warrants REVIEW (operator queue + escrow), not an automatic
# BLOCK. The window verdict aggregates signals by MAX severity (see
# ``_compose_max_severity``), so a SIVT hit lands at REVIEW while a stronger GIVT
# fact in the same window still drives BLOCK — the strongest evidence wins, and
# a heuristic never downgrades a fact.
SIVT_SIGNAL_SCORE = 0.6

# Reason codes (stable strings — they are persisted counts in M5 and read by the
# S6 statement's disclosed denominators; renaming one is a contract change).
REASON_DUPLICATE_INDEX = "givt_duplicate_second_index"
REASON_NON_MONOTONIC = "givt_non_monotonic_second_index"
REASON_IMPOSSIBLE_GEOMETRY = "givt_impossible_sample_geometry"
REASON_OVERSIZED_BATCH = "givt_oversized_batch"
REASON_CONSTANT_ATTENTION = "sivt_constant_attention_signature"
REASON_FOCUS_MARATHON = "sivt_implausible_focus_marathon"
REASON_DWELL_CAP_CLAMPED = "cap_daily_asset_dwell_clamped"

# --- M4: per-(user, asset, day) countable-dwell saturation cap. ---
#
# HONEST STATUS (rigor #1): this default is an UN-CALIBRATED structural ceiling,
# NOT a data-derived percentile. The spec's M4 wants the cap fitted to a
# percentile of the honest-traffic dwell distribution — but frame_attention_
# accruals is empty (no real ad traffic yet), so there is no distribution to fit.
# Until there is, the default is a generous "no honest single-document day
# exceeds this" ceiling; the CALIBRATION step (fit the percentile on real
# accrual rows, re-mint the constant with a recorded rationale, mirroring
# benchmarks/rubric_latency --update-baseline) belongs to whoever first has real
# data and is recorded in the S2 handoff — it is deliberately NOT faked here.
#
# Ceiling rationale: countable focused dwell is capped at 1000 ms/second. Even a
# very heavy reader rarely focus-reads ONE document for more than a few hours in
# a day; 6 h of COUNTABLE dwell on a SINGLE asset in a SINGLE day is beyond
# plausible sustained single-document reading — it is where a re-reading bot's
# otherwise-unbounded accrual is clamped. 6 h = 21_600_000 ms.
DEFAULT_DAILY_ASSET_DWELL_CAP_MS = 21_600_000


def clamp_countable_dwell(
    prior_counted_ms: int,
    incremental_ms: int,
    *,
    cap_ms: int = DEFAULT_DAILY_ASSET_DWELL_CAP_MS,
) -> tuple[int, int]:
    """Clamp one (user, asset, day)'s INCREMENTAL countable dwell to the
    saturation cap. Bounds any single identity's payout influence: past the cap,
    extra dwell on the same asset the same day earns nothing, so a sybil's
    maximum extractable value is bounded and its cost exceeds its return (the
    uncapped-unit failure mode of the $10M bot-streaming fraud).

    Returns ``(counted_ms, clamped_ms)``: the portion that counts toward the
    weight, and the excess that is CLAMPED — reported (via
    ``REASON_DWELL_CAP_CLAMPED``), never silently dropped.

    ``prior_counted_ms`` is the day's already-counted dwell for this
    (user, asset). Pure arithmetic: the DB read of ``prior_counted_ms`` and the
    wiring into the accrual weight are M5's job (they need the write connection +
    the day bucket + the request identity).
    """
    if incremental_ms <= 0:
        return 0, 0
    if prior_counted_ms >= cap_ms:
        return 0, incremental_ms  # already saturated: nothing new counts
    room = cap_ms - prior_counted_ms
    counted = min(incremental_ms, room)
    return counted, incremental_ms - counted


@dataclass(frozen=True)
class SecondClassification:
    """One second's validity. ``valid=False`` means NON-BILLABLE — the accrual
    stage (M5) excludes it from numerator AND denominator and counts it under
    ``reason``. A valid second has ``reason=None``."""

    second_index: int
    position: int  # 0-based position in the batch (distinguishes duplicates)
    valid: bool
    reason: str | None = None


@dataclass(frozen=True)
class BatchClassification:
    """The classifier's full output for one window batch.

    ``window_verdict`` is the composite ``FraudVerdict`` (PASS/REVIEW/BLOCK) —
    the SAME ``FraudVerdictKind`` vocabulary + REVIEW/BLOCK thresholds every
    detector uses (aggregated by max severity, see ``_compose_max_severity``), so
    the accrual/payout mediation treats a frame batch exactly like an impression:
    PASS accrues, BLOCK zeroes the window, REVIEW accrues-to-escrow for the
    operator queue (M5 wires the routing; this module only classifies).
    """

    window_id: str
    seconds: tuple[SecondClassification, ...]
    window_verdict: FraudVerdict

    @property
    def invalid_positions(self) -> frozenset[int]:
        return frozenset(s.position for s in self.seconds if not s.valid)

    @property
    def valid_positions(self) -> frozenset[int]:
        return frozenset(s.position for s in self.seconds if s.valid)

    def counts_by_reason(self) -> dict[str, int]:
        """Per-reason invalid-second counts — the REPORTED exclusions (honesty
        over coverage): every dropped second is counted here, never silently
        removed."""
        out: dict[str, int] = {}
        for s in self.seconds:
            if s.reason is not None:
                out[s.reason] = out.get(s.reason, 0) + 1
        return out


def _classify_geometry(sec: FrameSecond) -> bool:
    """Return True if this second contains at least one JOINTLY-IMPOSSIBLE
    sample. The frozen-dataclass ``__post_init__`` already range-validates each
    field independently ([0,1] area/prominence, [0,1000] dwell); this catches
    combinations that pass the ranges but cannot physically co-occur:

      * focused dwell > 0 with viewport_area_fraction == 0 — you cannot focus-
        dwell on an asset that occupies zero viewport area (the client sampler's
        ``measure()`` returns null for a zero-area element, so a real emitter
        never produces this; a crafted batch does).
      * prominence > 0 with viewport_area_fraction == 0 — prominence is a
        centering signal over the VISIBLE region; zero visible area cannot be
        prominent.
    """
    for s in sec.samples:
        if s.viewport_area_fraction == 0.0 and (
            s.focused_dwell_ms > 0 or s.prominence > 0.0
        ):
            return True
    return False


def classify_batch(
    batch: WindowFrameBatch,
    *,
    max_window_seconds: int = MAX_WINDOW_SECONDS,
    min_sivt_window_seconds: int = MIN_SIVT_WINDOW_SECONDS,
) -> BatchClassification:
    """Classify each second of a window batch as billable or GIVT-invalid, and
    compose the window-level fraud verdict.

    GIVT rules (each a deterministic fact, each with a caught-bad AND a
    passed-good near-miss fixture in ``tests/test_frame_ivt.py``):

    1. NON-MONOTONIC / DUPLICATE second_index — the 1 Hz emitter increments
       ``second_index`` strictly. A duplicate (index seen before) or a
       regression (index <= the previous position's index) is replay/reorder
       tampering. A GAP (0, 1, 3 — a dropped tick) is LEGITIMATE and stays
       valid: honest sampling misses ticks; only order/duplication is invalid.
    2. IMPOSSIBLE SAMPLE GEOMETRY — see ``_classify_geometry``.
    3. OVERSIZED BATCH — more seconds than ``max_window_seconds`` is fabricated,
       not measured; the WHOLE batch is invalid (a single window cannot be a
       day long).

    The per-second validity feeds the M5 filter (excluded from both sides of the
    split, counted by reason). The window verdict is composed from GIVT signals:
    a batch with any GIVT hit scores toward REVIEW/BLOCK proportional to the
    invalid fraction, so a mostly-invalid batch BLOCKs while a single impossible
    second in an otherwise-clean window only nudges toward REVIEW.
    """
    n = len(batch.seconds)
    oversized = n > max_window_seconds

    classifications: list[SecondClassification] = []
    prev_index: int | None = None
    seen_indexes: set[int] = set()

    for position, sec in enumerate(batch.seconds):
        reason: str | None = None
        if oversized:
            reason = REASON_OVERSIZED_BATCH
        elif sec.second_index in seen_indexes:
            reason = REASON_DUPLICATE_INDEX
        elif prev_index is not None and sec.second_index <= prev_index:
            # A later position must carry a strictly larger index (gaps allowed,
            # regressions/equal are not).
            reason = REASON_NON_MONOTONIC
        elif _classify_geometry(sec):
            reason = REASON_IMPOSSIBLE_GEOMETRY

        seen_indexes.add(sec.second_index)
        # prev_index tracks the last SEEN index so a regression is caught even
        # after a duplicate; it advances on every position.
        prev_index = sec.second_index
        classifications.append(
            SecondClassification(
                second_index=sec.second_index,
                position=position,
                valid=reason is None,
                reason=reason,
            )
        )

    signals = _givt_signals(classifications, oversized=oversized)
    if not oversized:
        # SIVT judges the residual behavioural pattern of the seconds that
        # survived GIVT; an oversized batch is already wholesale-fabricated, so
        # SIVT adds nothing.
        signals += _sivt_signals(batch, classifications, min_sivt_window_seconds)
    verdict = _compose_max_severity(batch.window_id, signals)
    return BatchClassification(
        window_id=batch.window_id,
        seconds=tuple(classifications),
        window_verdict=verdict,
    )


def _compose_max_severity(
    window_id: str, signals: tuple[FraudSignal, ...]
) -> FraudVerdict:
    """Window verdict by MAX severity, not mean.

    We reuse ``FraudVerdictKind`` and the shared ``REVIEW_THRESHOLD`` /
    ``BLOCK_THRESHOLD``, but aggregate the signal scores by MAX rather than the
    mean that ``verdict_from_signals`` uses — deliberately, and here is why: our
    signals mix HIGH-CONFIDENCE GIVT facts (scores up to 1.0) with LOWER SIVT
    heuristics (0.6). Averaging would let a weak SIVT signal DOWNGRADE a strong
    GIVT block (0.9 fact + 0.6 heuristic → mean 0.75-ish → REVIEW), i.e. more
    evidence reducing suspicion — wrong for a fraud verdict. Max makes the
    strongest evidence drive the kind; a heuristic can only ADD a REVIEW, never
    subtract from a fact. (For a single signal, max == mean, so every GIVT-only
    batch keeps its M2 verdict.)
    """
    if not signals:
        return FraudVerdict(subject_ref=window_id)
    top = max(s.score for s in signals)
    if top >= BLOCK_THRESHOLD:
        kind = FraudVerdictKind.BLOCK
    elif top >= REVIEW_THRESHOLD:
        kind = FraudVerdictKind.REVIEW
    else:
        kind = FraudVerdictKind.PASS
    return FraudVerdict(kind=kind, signals=signals, subject_ref=window_id)


def _givt_signals(
    classifications: list[SecondClassification],
    *,
    oversized: bool,
) -> tuple[FraudSignal, ...]:
    """GIVT window signals — monotone in the invalid fraction (GIVT is a fact,
    so the score is evidence weight, not a learned probability).

      * oversized → a hard BLOCK signal (score 1.0), fabricated wholesale.
      * otherwise the score is the invalid-second FRACTION: a majority-invalid
        batch crosses BLOCK (0.75), a small minority crosses only REVIEW (0.45),
        a clean batch yields no signal (PASS).
    """
    total = len(classifications)
    invalid = sum(1 for c in classifications if not c.valid)
    if total == 0 or invalid == 0:
        return ()
    if oversized:
        return (
            FraudSignal(
                name=REASON_OVERSIZED_BATCH,
                score=1.0,
                detail=f"{total} seconds exceeds the honest-window ceiling",
            ),
        )
    fraction = invalid / total
    reasons = sorted({c.reason for c in classifications if c.reason is not None})
    return (
        FraudSignal(
            name="givt_invalid_fraction",
            score=fraction,
            detail=f"{invalid}/{total} seconds GIVT-invalid ({', '.join(reasons)})",
        ),
    )


def _sivt_signals(
    batch: WindowFrameBatch,
    classifications: list[SecondClassification],
    min_sivt_window_seconds: int,
) -> tuple[FraudSignal, ...]:
    """SIVT window signals (M3) — HEURISTIC behavioural implausibility over the
    GIVT-valid seconds of a long-enough window.

    Honesty (rigor #1): these are heuristics with real false-positive/negative
    rates, so each emits a REVIEW-tier score (``SIVT_SIGNAL_SCORE`` < BLOCK on
    its own). Only evaluated when the window has >= ``min_sivt_window_seconds``
    VALID seconds — a short window has too little signal to judge a pattern, and
    a window dominated by GIVT-invalid seconds is already being handled.
    """
    valid_positions = {c.position for c in classifications if c.valid}
    valid_seconds = [
        sec for pos, sec in enumerate(batch.seconds) if pos in valid_positions
    ]
    if len(valid_seconds) < min_sivt_window_seconds:
        return ()

    signals: list[FraudSignal] = []

    # SIVT-1 constant-attention: fraction of seconds sharing the modal
    # per-second signature (the sorted tuple of each sample's rounded features).
    # Real reading jitters; a near-constant signature is replayed/synthetic.
    sig_counts: dict[tuple, int] = {}
    for sec in valid_seconds:
        key = tuple(
            sorted(
                (
                    s.asset_id,
                    round(s.viewport_area_fraction, 4),
                    round(s.prominence, 4),
                    s.focused_dwell_ms,
                )
                for s in sec.samples
            )
        )
        sig_counts[key] = sig_counts.get(key, 0) + 1
    modal = max(sig_counts.values())
    constant_fraction = modal / len(valid_seconds)
    if constant_fraction >= CONSTANT_VECTOR_FRACTION:
        signals.append(
            FraudSignal(
                name=REASON_CONSTANT_ATTENTION,
                score=SIVT_SIGNAL_SCORE,
                detail=(
                    f"{modal}/{len(valid_seconds)} seconds share one signature "
                    f"({constant_fraction:.2f} >= {CONSTANT_VECTOR_FRACTION})"
                ),
            )
        )

    # SIVT-2 focus-marathon: mean dwell pinned at the max, near-zero viewport-
    # area variance, and NO scrolled-past (250ms) seconds — sustained perfect
    # frozen focus over a long window, which real reading does not sustain.
    dwells = [s.focused_dwell_ms for sec in valid_seconds for s in sec.samples]
    areas = [s.viewport_area_fraction for sec in valid_seconds for s in sec.samples]
    if dwells:
        mean_dwell = sum(dwells) / len(dwells)
        area_var = _variance(areas)
        has_glance = any(d < 1000 for d in dwells)
        if (
            mean_dwell >= MARATHON_DWELL_MEAN_MS
            and area_var <= MARATHON_AREA_VARIANCE_MAX
            and not has_glance
        ):
            signals.append(
                FraudSignal(
                    name=REASON_FOCUS_MARATHON,
                    score=SIVT_SIGNAL_SCORE,
                    detail=(
                        f"mean dwell {mean_dwell:.0f}ms, area variance "
                        f"{area_var:.2e}, no glancing over "
                        f"{len(valid_seconds)} seconds"
                    ),
                )
            )

    return tuple(signals)


def _variance(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mean = sum(xs) / len(xs)
    return sum((x - mean) ** 2 for x in xs) / len(xs)
