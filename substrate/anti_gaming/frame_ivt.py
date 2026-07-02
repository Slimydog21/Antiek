"""AFA-S2 (M2) — frame-attention Invalid-Traffic (IVT) classification.

Filter-before-allocate: invalid frame-attention seconds are NON-BILLABLE, not
merely flagged (the MRC IVT model). This module is the pure classifier; the
accrual integration (AFA-S2 M5) excludes the seconds this module marks invalid
from BOTH the numerator and the denominator of the per-window split, and reports
the exclusion counts — never silently drops a second.

SCOPE OF THIS MODULE, HONESTLY (rigor #1):
  * M2 (here now): GIVT — General Invalid Traffic. Mechanically-impossible or
    self-contradictory batches: duplicated/non-monotonic second indices, sample
    geometry that cannot co-occur, an implausibly large batch. These are
    deterministic facts about the batch, not judgements — high confidence.
  * M3 (next): SIVT — Sophisticated Invalid Traffic. Behavioural implausibility
    (constant-attention signatures, marathon perfect dwell, parallel-window
    counts). Heuristic, honestly labelled — real false-positive/negative rates.
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
    FraudSignal,
    FraudVerdict,
    verdict_from_signals,
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

# Reason codes (stable strings — they are persisted counts in M5 and read by the
# S6 statement's disclosed denominators; renaming one is a contract change).
REASON_DUPLICATE_INDEX = "givt_duplicate_second_index"
REASON_NON_MONOTONIC = "givt_non_monotonic_second_index"
REASON_IMPOSSIBLE_GEOMETRY = "givt_impossible_sample_geometry"
REASON_OVERSIZED_BATCH = "givt_oversized_batch"


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

    ``window_verdict`` is the composite ``FraudVerdict`` (PASS/REVIEW/BLOCK) via
    the shared ``verdict_from_signals`` — the SAME vocabulary every detector
    emits, so the accrual/payout mediation treats a frame batch exactly like an
    impression: PASS accrues, BLOCK zeroes the window, REVIEW accrues-to-escrow
    for the operator queue (M5 wires the routing; this module only classifies).
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

    verdict = _window_verdict(batch.window_id, classifications, oversized=oversized)
    return BatchClassification(
        window_id=batch.window_id,
        seconds=tuple(classifications),
        window_verdict=verdict,
    )


def _window_verdict(
    window_id: str,
    classifications: list[SecondClassification],
    *,
    oversized: bool,
) -> FraudVerdict:
    """Compose the window FraudVerdict from GIVT hits.

    Scoring is deliberately simple and monotone in the invalid fraction (GIVT is
    a fact, so the score is the evidence weight, not a learned probability):

      * an oversized batch is a hard BLOCK (score 1.0) — fabricated wholesale.
      * otherwise the signal score is the invalid-second FRACTION, so a batch
        that is majority-invalid crosses BLOCK (0.75) and a small minority
        crosses only REVIEW (0.45); a clean batch PASSes with no signals.

    Using the shared ``verdict_from_signals`` keeps a frame batch on the exact
    PASS/REVIEW/BLOCK ladder as every impression detector.
    """
    total = len(classifications)
    invalid = sum(1 for c in classifications if not c.valid)
    if total == 0 or invalid == 0:
        return verdict_from_signals((), subject_ref=window_id)

    if oversized:
        signals = (
            FraudSignal(
                name=REASON_OVERSIZED_BATCH,
                score=1.0,
                detail=f"{total} seconds exceeds the honest-window ceiling",
            ),
        )
        return verdict_from_signals(signals, subject_ref=window_id)

    fraction = invalid / total
    reasons = sorted({c.reason for c in classifications if c.reason is not None})
    signals = (
        FraudSignal(
            name="givt_invalid_fraction",
            score=fraction,
            detail=(
                f"{invalid}/{total} seconds GIVT-invalid "
                f"({', '.join(reasons)})"
            ),
        ),
    )
    return verdict_from_signals(signals, subject_ref=window_id)
