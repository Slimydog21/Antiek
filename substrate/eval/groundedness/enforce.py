"""Groundedness enforcement posture (Groundedness Gate SPR-03).

The activation flag that governs whether the Phase-6 truth-axis score
DOES anything beyond emit. Ships default-OFF (validate-before-gate per
``PROMOTE_TO_GATE.md``): until criterion 4 (2 weeks of live
``groundedness.failed`` < 1% traces) accrues, the score is observability-
only — exactly today's behavior.

Three postures (``ANTIEK_GROUNDEDNESS_ENFORCE``):

- ``off`` (default): today's behavior. Score + emit, nothing gates.
  ``should_enforce()`` is False; ``should_block()`` is False.
- ``flag``: the default-enabled posture when the operator turns the flag
  on. Emits ``groundedness.failed`` + marks a below-threshold synthesis,
  but still deposits (observability + alert, not a destructive block).
  ``should_enforce()`` is True; ``should_block()`` is False.
- ``block``: the stricter post-criterion-4 opt-in. PREVENTS a below-
  threshold synthesis from being deposited (typed rejection, logged,
  never a silent drop). ``should_enforce()`` is True; ``should_block()``
  is True.

The threshold the enforcement reads is the SAME
``DEFAULT_SUPPORTED_THRESHOLD`` the scorer + harness use (rigor #4: no
parallel threshold). The backend enforced on is SPR-02's NLI when
available (the validated signal); lexical is the never-block fallback
only if NLI is explicitly unavailable and the operator opts in — but
enforcing ``block`` on lexical is refused (lexical misses densely-cited
hallucinations; blocking on it would lose faithful work AND pass the
confident lies — rigor #1 of the SPR-03 spec).

This module is pure config-reading + decision logic — no side effects.
The orchestrator + provenance path consume its verdicts. That separation
makes ``off == no-op`` provable by a test that asserts nothing fires.
"""

from __future__ import annotations

import os
from enum import StrEnum

from substrate.eval.groundedness.scorer import DEFAULT_SUPPORTED_THRESHOLD


class EnforcePosture(StrEnum):
    """The three enforcement postures. ``StrEnum`` so env values compare
    directly (``"off" == EnforcePosture.OFF``)."""

    OFF = "off"
    FLAG = "flag"
    BLOCK = "block"


# The env var name — reuses the established ``ANTIEK_*`` surface (see
# orchestration/loop_one/orchestrator.py for the pattern). Do NOT invent a
# parallel config system.
ENFORCE_ENV_VAR = "ANTIEK_GROUNDEDNESS_ENFORCE"
_DEFAULT = EnforcePosture.OFF


def _coerce(raw: str | None) -> EnforcePosture:
    """Coerce a raw env value to a posture. Unknown values default to OFF
    (fail-safe: a typo never accidentally enables enforcement)."""
    if not raw:
        return _DEFAULT
    v = raw.strip().lower()
    for p in EnforcePosture:
        if v == p.value:
            return p
    # Fail-safe: unknown -> OFF (never accidentally block).
    return _DEFAULT


def current_posture() -> EnforcePosture:
    """Read the live enforcement posture from the env. Pure — no side
    effects, no caching (cheap to call; the env is the source of truth)."""
    return _coerce(os.environ.get(ENFORCE_ENV_VAR))


def should_enforce(posture: EnforcePosture | None = None) -> bool:
    """True iff the flag is anything other than OFF. ``OFF`` is the only
    no-op posture; both ``flag`` and ``block`` enforce (emit
    ``groundedness.failed`` on a below-threshold synthesis)."""
    p = posture or current_posture()
    return p is not EnforcePosture.OFF


def should_block(posture: EnforcePosture | None = None) -> bool:
    """True iff a below-threshold synthesis must be PREVENTED from
    depositing (not merely flagged). Only ``block`` — ``flag`` deposits
    anyway."""
    p = posture or current_posture()
    return p is EnforcePosture.BLOCK


def is_below_threshold(score: float, threshold: float = DEFAULT_SUPPORTED_THRESHOLD) -> bool:
    """The single threshold comparison the whole enforcement reads. Same
    ``DEFAULT_SUPPORTED_THRESHOLD`` (0.50) the scorer + harness use — no
    drift. Kept as a function (not a bare ``<``) so a future calibration
    has one place to reason about."""
    return score < threshold


class GroundednessEnforceError(RuntimeError):
    """Typed rejection raised when ``block`` posture prevents a below-
    threshold synthesis from depositing. Distinct from a scorer crash
    (``groundedness.failed``) — this is a deliberate gate refusal, not a
    bug. The loop logs it + emits a ``groundedness.failed`` and continues
    (never a silent drop, never an unhandled crash)."""


# Sanity invariants (documented for a maintainer who edits this):
# 1. OFF is the default — a fresh env never enables enforcement.
# 2. Unknown env values fail-safe to OFF, never to BLOCK.
# 3. The threshold is DEFAULT_SUPPORTED_THRESHOLD — edit ONE place to
#    recalibrate (and re-record the harness number).
