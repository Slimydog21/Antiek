"""Verification skills (Sprint 6 day 3-4 migration of Researchmaxx
``verify.py`` + ``rlm_verify.py`` + ``rubrics.py``, ~1,320 LOC total).

Four submodules:

- ``types`` — ``VerifyResult`` (role re-dispatch) and
  ``VerificationResult`` (RLM claim verification) dataclasses.
- ``agreement`` — ``default_agreement_synthesizer`` /
  ``default_agreement_evidence`` / ``default_agreement_strict``
  pure functions consumed by ``verify_with_redispatch``.
- ``redispatch`` — ``verify_with_redispatch`` with callable-injected
  ``role_runner``. Constraint-loop fallback path.
- ``rlm`` — plausibility checks (sign / range / units / shape) +
  ``REPHRASE_TEMPLATES`` + ``verify_claim`` / ``verified_answer`` /
  ``verify_layer_answers`` with callable-injected ``llm_batch_fn``.
- ``rubric`` — ``Rubric`` ABC + 4 pre-registered concrete rubrics +
  ``LlmJudgeRubric`` constructor-injected wrapper + ``score_and_emit``
  bridge to ``RubricScoredPayload`` (closes the Sprint 5 day 2-3 gap
  where the payload was added but no caller existed).

Both LLM seams (``role_runner`` for redispatch and ``llm_batch_fn``
for rlm) are injected so the modules import cleanly without dragging
in ``substrate.dispatch``. Production wires closures around dispatch;
tests inject deterministic stubs.

What's deferred:

- The judged-rubric judge closures themselves. ``LlmJudgeRubric``
  ships but no judge-fn factories are pre-registered — those land
  alongside the synthesizer / decomposer judges in Sprint 7+.
- Constraint-loop wiring of ``verify_with_redispatch`` as the
  fallback path. Gated on ``parameter_extractor`` extraction
  (Sprint 7).
"""

from .agreement import (
    default_agreement_evidence,
    default_agreement_strict,
    default_agreement_synthesizer,
)
from .redispatch import verify_with_redispatch
from .rlm import (
    REPHRASE_TEMPLATES,
    check_expected_shape,
    check_numeric_range,
    check_sign,
    check_units_rough,
    rephrase_framings,
    run_plausibility_checks,
    verified_answer,
    verify_claim,
    verify_layer_answers,
)
from .rubric import (
    JUDGED,
    OUTCOME,
    VALID_KINDS,
    VERIFIABLE,
    CitationProvenanceRubric,
    ConstraintDeterministicRubric,
    LlmJudgeRubric,
    ParaphraseGuardRubric,
    Rubric,
    RubricResult,
    ThesisConfirmationRubric,
    all_rubrics,
    emit_score,
    get,
    known_ids,
    register,
    score_and_emit,
)
from .types import VerificationResult, VerifyResult

__all__ = [
    # types
    "VerifyResult",
    "VerificationResult",
    # agreement
    "default_agreement_synthesizer",
    "default_agreement_evidence",
    "default_agreement_strict",
    # redispatch
    "verify_with_redispatch",
    # rlm
    "REPHRASE_TEMPLATES",
    "check_numeric_range",
    "check_sign",
    "check_units_rough",
    "check_expected_shape",
    "run_plausibility_checks",
    "rephrase_framings",
    "verify_claim",
    "verified_answer",
    "verify_layer_answers",
    # rubric
    "VALID_KINDS",
    "VERIFIABLE",
    "JUDGED",
    "OUTCOME",
    "Rubric",
    "RubricResult",
    "ParaphraseGuardRubric",
    "ConstraintDeterministicRubric",
    "CitationProvenanceRubric",
    "ThesisConfirmationRubric",
    "LlmJudgeRubric",
    "register",
    "get",
    "all_rubrics",
    "known_ids",
    "emit_score",
    "score_and_emit",
]
