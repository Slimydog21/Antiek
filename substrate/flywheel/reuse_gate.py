"""AFF SPR-08 — gate the flywheel's reuse on groundedness + §9.0 servability.

This is a THIN, composing seam. It owns no scoring logic, no trust signal, and
no servability derivation:

* the groundedness score is the shipped #27 lexical entailment scorer's verdict
  (``substrate/eval/groundedness/score_claim``), read off the unit's
  ``groundedness_score`` slot (filled at projection time by
  ``knowledge_unit_of(..., score_groundedness=True)``) or re-scored lazily from
  the unit's cited chunk text if the slot is unset — the lexical backend is
  deterministic, so the two are identical;
* servability is the §9.0 deny-by-default answer recorded on the unit at deposit
  (``unit.servability.serves_full_text``), read through SPR-06's
  ``RetrievedUnit.serves_full_text`` property — the classifier is the single
  owner; this gate never re-derives deny-by-default.

A unit is REUSABLE iff its groundedness score ≥ ``REUSE_GROUNDEDNESS_THRESHOLD``
AND it serves full text. The two conditions are INDEPENDENT: a high-groundedness
but non-servable unit is excluded; a servable but below-threshold unit is
excluded. Every EXCLUDED unit produces exactly one ``reuse.gated`` event
recording its score, the threshold in force, and the reason(s) it failed
(``below-threshold`` and/or ``non-servable``, BOTH when both apply). An ADMITTED
unit produces no event.

----------------------------------------------------------------------------
What this gate does NOT claim (honesty)
----------------------------------------------------------------------------
The lexical scorer is a COVERAGE + polarity + number proxy, not a judge: it
rewards a claim whose content tokens are covered by its cited evidence and
penalises negation flips + fabricated numbers, but it cannot catch a faithful-
sounding paraphrase that subtly distorts a relation, nor reward a correct claim
phrased in disjoint vocabulary. So this gate does NOT make reuse "safe". It
excludes below-threshold + non-servable units, mutation-proven and logged — that
is its whole claim. The future A/B path to a real judge is #27's ``llm_judge``
backend (off by default, never exercised in CI); promoting it is a later
sprint's decision, recorded against ``substrate/eval/groundedness/PROMOTE_TO_GATE.md``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from substrate.eval.groundedness import (
    DEFAULT_SCORER_ID,
    DEFAULT_SUPPORTED_THRESHOLD,
    score_claim,
)
from substrate.schemas.events import ReuseGateReason

# A resolver maps a chunk_id to its text (or None). Mirrors
# ``substrate.eval.groundedness.provenance.ChunkTextResolver`` so the gate can
# lazily re-score a unit whose slot is unset WITHOUT opening its own DB
# connection — the caller (which already holds the read connection) injects it.
ChunkTextResolver = Callable[[str], str | None]


def _threshold_from_env(default: float) -> float:
    """Read ``REUSE_GROUNDEDNESS_THRESHOLD`` from the environment, else the
    default. A malformed/out-of-range value is rejected LOUDLY rather than
    silently clamped — a typo'd trust bar should fail, not quietly weaken the
    gate. This is the ONLY place the knob is sourced; the gate, the tests, and
    the event all read this one constant."""
    raw = os.environ.get("REUSE_GROUNDEDNESS_THRESHOLD")
    if raw is None or not raw.strip():
        return default
    value = float(raw)  # ValueError on garbage — intentional, fail loud
    if not 0.0 <= value <= 1.0:
        raise ValueError(
            f"REUSE_GROUNDEDNESS_THRESHOLD={value!r} out of range [0,1]"
        )
    return value


# The single trust knob. Default anchored to the #27 scorer's supported
# threshold (``DEFAULT_SUPPORTED_THRESHOLD = 0.5``): the gate's bar is AT LEAST
# as strict as "the scorer would call this claim supported", never weaker — a
# unit the scorer would not call supported is never reused. Env-overridable for
# an operator who wants a stricter bar (e.g. 0.9). Rationale + reconsider-if:
# docs/decisions/spr-08-reuse-threshold.md.
REUSE_GROUNDEDNESS_THRESHOLD: float = _threshold_from_env(DEFAULT_SUPPORTED_THRESHOLD)

# The reason vocabulary, surfaced here so callers + tests read one source. These
# ARE the ``ReuseGateReason`` Literal values (events.py is the type owner).
REASON_BELOW_THRESHOLD: ReuseGateReason = "below-threshold"
REASON_NON_SERVABLE: ReuseGateReason = "non-servable"


@dataclass(frozen=True)
class GateDecision:
    """One candidate unit's trust verdict. ``reusable`` is the AND of both
    conditions; ``reasons`` is empty for an admitted unit and carries every
    failing reason (one or both) for an excluded one. ``score`` is the unit's
    groundedness score (``None`` only when it was unset AND could not be
    re-scored — an honest unknown, treated as below any threshold)."""

    unit: Any                       # the RetrievedUnit
    reusable: bool
    score: float | None
    reasons: tuple[ReuseGateReason, ...]


def groundedness_of(
    retrieved_unit: Any,
    *,
    chunk_text_for: ChunkTextResolver | None = None,
) -> float | None:
    """The unit's groundedness score.

    Prefers the value already on the unit's ``groundedness_score`` slot (filled
    at projection time — Decision B). If the slot is unset, re-scores lazily:
    the unit IS one claim, so ``score_claim(unit.text, [chunk_text])`` against
    the text of its single cited chunk (resolved via the injected resolver). The
    lexical backend is deterministic, so this matches the deposit-time score
    exactly. With no resolver and an unset slot the score is ``None`` — an
    honest unknown, below any threshold."""
    unit = retrieved_unit.unit
    stored = getattr(unit, "groundedness_score", None)
    if stored is not None:
        return float(stored)
    if chunk_text_for is None:
        return None
    chunk_id = unit.provenance.chunk_id
    text = chunk_text_for(chunk_id) if chunk_id else None
    chunk_texts = [text] if text else []
    verdict = score_claim(
        unit.text, chunk_texts, cited_chunk_ids=[chunk_id] if chunk_id else []
    )
    return verdict.score


def evaluate_unit(
    retrieved_unit: Any,
    *,
    threshold: float = REUSE_GROUNDEDNESS_THRESHOLD,
    chunk_text_for: ChunkTextResolver | None = None,
) -> GateDecision:
    """Apply the two INDEPENDENT trust conditions to one candidate unit.

    Returns a ``GateDecision`` whose ``reasons`` names every condition that
    failed. ``below-threshold`` fires when the score is ``None`` (unknown ⇒ not
    grounded) or strictly below ``threshold``; ``non-servable`` fires when the
    unit's §9.0 tag does not serve full text. A unit can fail BOTH."""
    score = groundedness_of(retrieved_unit, chunk_text_for=chunk_text_for)
    reasons: list[ReuseGateReason] = []
    if score is None or score < threshold:
        reasons.append(REASON_BELOW_THRESHOLD)
    if not retrieved_unit.serves_full_text:
        reasons.append(REASON_NON_SERVABLE)
    return GateDecision(
        unit=retrieved_unit,
        reusable=not reasons,
        score=score,
        reasons=tuple(reasons),
    )


def filter_reusable(
    units: Sequence[Any],
    *,
    investigation_id: str,
    threshold: float = REUSE_GROUNDEDNESS_THRESHOLD,
    chunk_text_for: ChunkTextResolver | None = None,
    context_pack_event_id: str = "",
    role: str | None = None,
    events_dir: str | None = None,
    policy_id: str | None = None,
    emit: bool = True,
) -> tuple[list[Any], list[GateDecision]]:
    """The gate. Partition candidate ``RetrievedUnit``s into the reusable set
    and emit one ``reuse.gated`` event per EXCLUDED unit.

    Returns ``(reusable, decisions)``: ``reusable`` is the units that cleared
    BOTH conditions, in input order; ``decisions`` covers EVERY input unit (the
    full audit of the trust partition). Admitted units emit NO event — absence
    is the signal that a reused unit cleared the gate.

    This runs BEFORE SPR-06's ``partition_units``, so an excluded unit is gone
    before any of its text reaches the pack — partition_units' own §9.0 check
    then becomes defense-in-depth that no longer fires for these units (one
    exclusion, one event, never two conflicting decisions for the same unit)."""
    reusable: list[Any] = []
    decisions: list[GateDecision] = []
    for ru in units:
        decision = evaluate_unit(
            ru, threshold=threshold, chunk_text_for=chunk_text_for
        )
        decisions.append(decision)
        if decision.reusable:
            reusable.append(ru)
        elif emit:
            _emit_reuse_gated(
                decision,
                investigation_id=investigation_id,
                threshold=threshold,
                context_pack_event_id=context_pack_event_id,
                role=role,
                events_dir=events_dir,
                policy_id=policy_id,
            )
    return reusable, decisions


def _emit_reuse_gated(
    decision: GateDecision,
    *,
    investigation_id: str,
    threshold: float,
    context_pack_event_id: str,
    role: str | None,
    events_dir: str | None,
    policy_id: str | None,
) -> str | None:
    """Emit one ``reuse.gated`` event for an EXCLUDED unit. The score, threshold,
    and reasons are carried on the event so an audit reads the exact bar in
    force, not today's constant. Parented to the assembled pack so the exclusion
    is joinable to what the model (did not) see."""
    from substrate.event_log import emit_typed
    from substrate.schemas.events import ReuseGatedPayload

    ru = decision.unit
    payload = ReuseGatedPayload(
        unit_id=ru.unit_id,
        source_investigation_id=ru.source_investigation_id,
        groundedness_score=(
            round(float(decision.score), 6) if decision.score is not None else None
        ),
        scorer_id=DEFAULT_SCORER_ID,
        threshold=threshold,
        reasons=list(decision.reasons),
        context_pack_event_id=context_pack_event_id or "",
    )
    return emit_typed(
        investigation_id,
        payload,
        parent_event_id=context_pack_event_id or None,
        role=role,
        events_dir=events_dir,
        policy_id=policy_id,
    )
