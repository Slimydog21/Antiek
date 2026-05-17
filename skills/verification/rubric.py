"""Rubric provenance layer (Sprint 6 day 3-4 port of upstream
``rubrics.py``).

Separates scoring signals by their **epistemic kind** so future
training pipelines never mix gradient signals from different
ground-truth classes without knowing it. The operator's named worst
failure mode is "rubric Goodhart": cheap-to-score proxies
(citation tier composition, schema validity, constraint pass-rate)
get maxed out while real research quality degrades. Mitigation:
every reward signal is explicitly tagged with which class produced
it.

Three rubric kinds (the ``VALID_KINDS`` closed set):

- ``verifiable`` — deterministic, no LLM, reproducible. Cheapest.
- ``judged`` — LLM-mediated. Mid-cost. Known biases (verbosity,
  sycophancy, judge-model preference). Never sole reward.
- ``outcome`` — deferred ground truth from the outcomes table.
  Highest quality, sparsest. The north-star for held-out cohorts.

**Bridge wiring (the Sprint 5 day 2-3 gap closer):**
``score_and_emit`` maps the rubric kind to ``RubricScoredPayload``
fields — ``verifiable`` → ``deterministic_score``, ``judged`` →
``judged_score``, ``outcome`` → both None (the outcome IS the final
ground-truth signal). ``final_score`` is always populated. The
event is published via ``substrate.event_log.emit_typed``.

Four concrete rubrics are pre-registered at import time:

- ``verifiable.decomposer.paraphrase_guard`` — wraps
  ``roles.decomposer.check_paraphrases`` (Sprint 5 helper).
- ``verifiable.constraint.deterministic_pass_rate`` — operates on a
  constraint-loop result dict.
- ``verifiable.synthesizer.citation_provenance`` — fraction of
  thesis components with citations.
- ``outcome.thesis.confirmation_rate`` — wraps the outcomes table's
  per-synthesis thesis_outcomes list.

``LlmJudgeRubric`` is a constructor-injected wrapper for judged
rubrics — callers supply the ``judge_fn`` and ``judge_policy_id``;
this module never imports an LLM client.
"""

from __future__ import annotations

import abc
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

try:
    from ...constants import (
        ANTIEK_PARAM_VERSION,
        DECOMPOSER_PARAPHRASE_COSINE_MAX,
    )
    from ...event_log import emit_typed
    from ...schemas import RubricScoredPayload
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import (  # type: ignore[no-redef]
        ANTIEK_PARAM_VERSION,
        DECOMPOSER_PARAPHRASE_COSINE_MAX,
    )
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.schemas import RubricScoredPayload  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Kinds
# ---------------------------------------------------------------------------


VERIFIABLE = "verifiable"
JUDGED = "judged"
OUTCOME = "outcome"

VALID_KINDS: tuple[str, ...] = (VERIFIABLE, JUDGED, OUTCOME)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class RubricResult:
    """One rubric's score + provenance tags.

    ``policy_id_scored`` is the policy whose output was graded;
    ``judge_policy_id`` is the policy that did the grading (only set
    for judged rubrics). ``details`` is a freeform dict the rubric
    populates with the diagnostic numbers (component counts, threshold
    used, etc.) — the operator reads this when triaging a score, but
    no consumer keys on its shape."""

    rubric_id: str
    kind: str
    score: float            # normalized to [0, 1]; 1 = best
    passed: Optional[bool] = None   # for hard-filter rubrics; None for graded
    details: Dict[str, Any] = field(default_factory=dict)
    policy_id_scored: Optional[str] = None
    judge_policy_id: Optional[str] = None
    param_version: str = field(default_factory=lambda: ANTIEK_PARAM_VERSION)
    evaluated_at: str = field(default_factory=_utc_iso_now)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "rubric_id": self.rubric_id,
            "kind": self.kind,
            "score": self.score,
            "passed": self.passed,
            "details": self.details,
            "policy_id_scored": self.policy_id_scored,
            "judge_policy_id": self.judge_policy_id,
            "param_version": self.param_version,
            "evaluated_at": self.evaluated_at,
        }


# ---------------------------------------------------------------------------
# ABC + registry
# ---------------------------------------------------------------------------


class Rubric(abc.ABC):
    """Named scoring rubric with explicit provenance.

    Subclasses set:
      ``rubric_id`` — stable string used as the training-data row key
                      (never reused for a different rubric).
      ``kind``      — one of ``VALID_KINDS``.
    """

    rubric_id: str = "abstract"
    kind: str = VERIFIABLE

    def __init__(self):
        if self.kind not in VALID_KINDS:
            raise ValueError(
                f"Rubric {self.rubric_id!r} has invalid kind "
                f"{self.kind!r}; must be one of {VALID_KINDS}"
            )

    @abc.abstractmethod
    def score(
        self, target: Any, *, context: Optional[Dict[str, Any]] = None,
    ) -> RubricResult:
        """Score ``target``. Each subclass documents the shape it
        accepts via its docstring."""


_REGISTRY: Dict[str, Rubric] = {}


def register(rubric: Rubric) -> None:
    """Register a rubric instance. Raises on duplicate id — the
    typed vocabulary is stable, not overwrite-friendly."""
    if rubric.rubric_id in _REGISTRY:
        raise ValueError(f"Rubric {rubric.rubric_id!r} already registered")
    _REGISTRY[rubric.rubric_id] = rubric


def get(rubric_id: str) -> Rubric:
    return _REGISTRY[rubric_id]


def all_rubrics(kind: Optional[str] = None) -> List[Rubric]:
    if kind is None:
        return list(_REGISTRY.values())
    return [r for r in _REGISTRY.values() if r.kind == kind]


def known_ids() -> List[str]:
    return sorted(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Bridge: RubricResult → RubricScoredPayload typed event
# ---------------------------------------------------------------------------


def _rubric_notes(result: RubricResult) -> str:
    """Compact one-line summary for the payload's ``notes`` field.
    Free-form; the trajectory consumer surfaces this in the rubric
    feed without needing to inspect ``details``."""
    pieces = [
        f"kind={result.kind}",
        f"score={result.score:.3f}",
    ]
    if result.passed is not None:
        pieces.append(f"passed={result.passed}")
    if result.policy_id_scored:
        pieces.append(f"scored_policy={result.policy_id_scored}")
    if result.judge_policy_id:
        pieces.append(f"judge_policy={result.judge_policy_id}")
    return "; ".join(pieces)


def emit_score(
    investigation_id: str,
    result: RubricResult,
    *,
    synthesis_id: Optional[str] = None,
    target_claim_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
) -> Optional[str]:
    """Write a typed ``RUBRIC_SCORED`` event into the trajectory.

    Kind → payload-field mapping (the Sprint 5 day 2-3 gap closer):
    ``verifiable`` populates ``deterministic_score``; ``judged``
    populates ``judged_score``; ``outcome`` leaves both ``None``
    (the outcome IS the final ground-truth signal — no decomposition
    into a deterministic / judged component). ``final_score`` is
    always the rubric's score so a single-axis ranking is always
    possible.

    Returns the emitted event_id (or ``None`` when events are
    disabled). The ``judge_policy_id`` on the result becomes the
    event's ``policy_id`` so trajectory consumers can filter by
    grading judge.
    """
    deterministic_score: Optional[float] = None
    judged_score: Optional[float] = None
    if result.kind == VERIFIABLE:
        deterministic_score = float(result.score)
    elif result.kind == JUDGED:
        judged_score = float(result.score)
    # OUTCOME: both stay None; final_score is the outcome itself.

    payload = RubricScoredPayload(
        rubric_id=result.rubric_id,
        target_claim_id=target_claim_id,
        deterministic_score=deterministic_score,
        judged_score=judged_score,
        final_score=float(result.score),
        notes=_rubric_notes(result),
    )
    return emit_typed(
        investigation_id,
        payload,
        parent_event_id=parent_event_id,
        synthesis_id=synthesis_id,
        role="rubric_scorer",
        policy_id=result.judge_policy_id or "orchestrator-deterministic",
    )


def score_and_emit(
    rubric_id: str,
    target: Any,
    *,
    investigation_id: str,
    context: Optional[Dict[str, Any]] = None,
    synthesis_id: Optional[str] = None,
    target_claim_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
) -> RubricResult:
    """Score with the named rubric and emit the result as a typed
    event. Returns the ``RubricResult`` so the caller can also use
    the score directly (gate decisions etc.) without re-deriving it
    from the trajectory."""
    rubric = get(rubric_id)
    result = rubric.score(target, context=context)
    emit_score(
        investigation_id, result,
        synthesis_id=synthesis_id,
        target_claim_id=target_claim_id,
        parent_event_id=parent_event_id,
    )
    return result


# ---------------------------------------------------------------------------
# Concrete rubrics — verifiable kind
# ---------------------------------------------------------------------------


class ParaphraseGuardRubric(Rubric):
    """Wraps ``roles.decomposer.check_paraphrases`` (Sprint 5 helper).

    Target: ``{"top_question": str, "sub_questions": list[str],
              "embedder": optional EmbeddingModel}``.

    Score: 1.0 if no flagged sub-questions; 0.0 otherwise. (A graded
    version returning ``1 - max_cosine_above_threshold`` would be
    more useful for RL but the underlying primitive returns pass/fail
    at threshold — parity preserved.)"""

    rubric_id = "verifiable.decomposer.paraphrase_guard"
    kind = VERIFIABLE

    def score(
        self, target: Any, *, context: Optional[Dict[str, Any]] = None,
    ) -> RubricResult:
        # Local import — keeps this module standalone-importable even
        # if roles.decomposer isn't installed.
        from roles.decomposer import check_paraphrases

        top_q = target.get("top_question") if isinstance(target, dict) else None
        sub_qs = target.get("sub_questions") if isinstance(target, dict) else None
        embedder = target.get("embedder") if isinstance(target, dict) else None
        if not top_q or not sub_qs:
            return RubricResult(
                rubric_id=self.rubric_id, kind=self.kind,
                score=0.0, passed=False,
                details={
                    "error": "ParaphraseGuardRubric requires "
                             "{'top_question', 'sub_questions'}",
                },
            )
        try:
            flagged = check_paraphrases(top_q, list(sub_qs), embedder=embedder)
        except ImportError as e:
            return RubricResult(
                rubric_id=self.rubric_id, kind=self.kind,
                score=0.0, passed=None,
                details={
                    "skipped_reason": f"embedder unavailable: {e!r}",
                    "n_sub_questions": len(sub_qs),
                },
            )
        passed = not flagged
        return RubricResult(
            rubric_id=self.rubric_id, kind=self.kind,
            score=1.0 if passed else 0.0,
            passed=passed,
            details={
                "n_sub_questions": len(sub_qs),
                "n_flagged": len(flagged),
                "threshold": DECOMPOSER_PARAPHRASE_COSINE_MAX,
            },
        )


class ConstraintDeterministicRubric(Rubric):
    """Wraps the deterministic path of the constraint loop.

    Target: ``{"final_violations": [...], "constraints": [...]}``.
    Score: ``1 - hard_violations / max(1, total_constraints)``. Hard
    violations are weighted; soft / target are diagnostic only."""

    rubric_id = "verifiable.constraint.deterministic_pass_rate"
    kind = VERIFIABLE

    def score(
        self, target: Any, *, context: Optional[Dict[str, Any]] = None,
    ) -> RubricResult:
        violations = (target or {}).get("final_violations", []) if isinstance(target, dict) else []
        constraints = (target or {}).get("constraints", []) if isinstance(target, dict) else []
        total = max(1, len(constraints))
        hard_violations = sum(
            1 for v in violations
            if (v.get("strictness") if isinstance(v, dict) else None) == "hard"
        )
        score = max(0.0, 1.0 - (hard_violations / total))
        return RubricResult(
            rubric_id=self.rubric_id, kind=self.kind,
            score=score,
            passed=(hard_violations == 0),
            details={
                "n_constraints": len(constraints),
                "n_hard_violations": hard_violations,
                "n_total_violations": len(violations),
            },
        )


class CitationProvenanceRubric(Rubric):
    """Wraps the "every load-bearing thesis claim must cite at least
    one chunk_id or substrate path index" rule.

    Target: synthesizer thesis dict.
    Score: fraction of ``thesis_components`` with at least one
    citation."""

    rubric_id = "verifiable.synthesizer.citation_provenance"
    kind = VERIFIABLE

    def score(
        self, target: Any, *, context: Optional[Dict[str, Any]] = None,
    ) -> RubricResult:
        thesis = target if isinstance(target, dict) else {}
        components = thesis.get("thesis_components", []) or []
        if not components:
            return RubricResult(
                rubric_id=self.rubric_id, kind=self.kind,
                score=0.0, passed=False,
                details={"error": "no thesis_components"},
            )
        cited = 0
        for c in components:
            chunk_ids = c.get("chunk_ids") or c.get("citations") or []
            substrate_paths = c.get("supporting_path_indices") or []
            if chunk_ids or substrate_paths:
                cited += 1
        rate = cited / len(components)
        return RubricResult(
            rubric_id=self.rubric_id, kind=self.kind,
            score=rate,
            passed=(rate == 1.0),
            details={
                "n_components": len(components),
                "n_cited": cited,
                "citation_rate": rate,
            },
        )


# ---------------------------------------------------------------------------
# Concrete rubric — outcome kind (deferred ground truth)
# ---------------------------------------------------------------------------


class ThesisConfirmationRubric(Rubric):
    """Wraps per-synthesis observations from the outcomes table.

    Target: ``{"thesis_outcomes": [{"outcome": str, ...}, ...]}``.
    Score: fraction with outcome == ``confirmed``."""

    rubric_id = "outcome.thesis.confirmation_rate"
    kind = OUTCOME

    def score(
        self, target: Any, *, context: Optional[Dict[str, Any]] = None,
    ) -> RubricResult:
        outcomes = (target or {}).get("thesis_outcomes", []) if isinstance(target, dict) else []
        if not outcomes:
            return RubricResult(
                rubric_id=self.rubric_id, kind=self.kind,
                score=0.0, passed=None,
                details={
                    "n_outcomes": 0,
                    "note": "no observed outcomes yet — deferred ground truth",
                },
            )
        confirmed = sum(1 for o in outcomes if o.get("outcome") == "confirmed")
        return RubricResult(
            rubric_id=self.rubric_id, kind=self.kind,
            score=confirmed / len(outcomes),
            passed=(confirmed == len(outcomes)),
            details={
                "n_outcomes": len(outcomes),
                "n_confirmed": confirmed,
            },
        )


# ---------------------------------------------------------------------------
# Concrete rubric — judged kind (LLM-mediated, callable-injected)
# ---------------------------------------------------------------------------


class LlmJudgeRubric(Rubric):
    """Generic LLM-judged rubric. ``judge_fn`` is constructor-injected
    so this module never imports an LLM client. Caller wires the
    closure with whatever dispatch shape they have.

    ``judge_fn(target, context) -> (score in [0,1], details_dict)``.
    Score is clamped to [0, 1] defensively.

    Known biases (per the operator's risk list): verbosity, sycophancy,
    judge-model preference. Never sole reward signal in training
    without held-out outcome validation."""

    kind = JUDGED

    def __init__(
        self,
        rubric_id: str,
        judge_fn: Callable[
            [Any, Optional[Dict[str, Any]]], "tuple[float, Dict[str, Any]]",
        ],
        judge_policy_id: str,
    ):
        self.rubric_id = rubric_id
        self.judge_fn = judge_fn
        self.judge_policy_id = judge_policy_id
        super().__init__()

    def score(
        self, target: Any, *, context: Optional[Dict[str, Any]] = None,
    ) -> RubricResult:
        score_val, details = self.judge_fn(target, context)
        score_val = max(0.0, min(1.0, float(score_val)))
        return RubricResult(
            rubric_id=self.rubric_id, kind=self.kind,
            score=score_val,
            passed=None,
            details=details or {},
            judge_policy_id=self.judge_policy_id,
        )


# ---------------------------------------------------------------------------
# Default registrations
# ---------------------------------------------------------------------------


# Verifiable + outcome rubrics are pre-registered. Judged rubrics
# require a judge_fn injection at construction time, so they are not
# pre-registered here — callers register their own via ``register()``.
for _r in (
    ParaphraseGuardRubric(),
    ConstraintDeterministicRubric(),
    CitationProvenanceRubric(),
    ThesisConfirmationRubric(),
):
    register(_r)
