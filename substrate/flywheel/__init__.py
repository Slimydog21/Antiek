"""AFF SPR-08 — the flywheel's trust gate.

The reuse half (SPR-06) injects PRIOR investigations' knowledge units into a
NEW investigation's context pack. That is the compounding mechanism — and it is
also the amplification hazard: an ungrounded unit does not merely sit in the
graph, it SEEDS the next synthesis. Without a trust gate the loop amplifies
hallucination at the same rate it amplifies signal.

This package is the gate. It COMPOSES two shipped components — it builds neither
a scorer nor a servability rule:

* the #27 groundedness scorer (``substrate/eval/groundedness``) attaches a
  groundedness score to each candidate unit, and
* the §9.0 servability answer already recorded on the unit at deposit
  (``unit.servability.serves_full_text`` — deny-by-default, single-owner) is
  read, never re-derived.

A unit is reusable ONLY if its groundedness score ≥ ``REUSE_GROUNDEDNESS_THRESHOLD``
AND it serves full text. The two conditions are INDEPENDENT. Every excluded unit
emits exactly one ``reuse.gated`` event recording its score, the threshold, and
the reason(s) it was excluded (``below-threshold`` and/or ``non-servable``).
"""

from substrate.flywheel.reuse_gate import (
    REUSE_GROUNDEDNESS_THRESHOLD,
    GateDecision,
    filter_reusable,
    groundedness_of,
)

__all__ = [
    "REUSE_GROUNDEDNESS_THRESHOLD",
    "GateDecision",
    "filter_reusable",
    "groundedness_of",
]
