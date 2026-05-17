"""RLM-style claim verification (Sprint 6 day 3-4 port of upstream
``rlm_verify.py``).

Two-tier mechanism:

1. **Plausibility checks** — cheap pre-filters (sign / numeric range /
   units / type). No LLM. Run before the expensive re-dispatch so an
   obviously-wrong answer fails fast.
2. **Re-dispatch with rephrased framings** — generate ``N`` rephrased
   prompts via ``REPHRASE_TEMPLATES``, dispatch all via the injected
   ``llm_batch_fn``, check for agreement. On disagreement, one
   tie-breaker dispatch with adversarial framing.

The ``llm_batch_fn`` injection is the migration improvement over
upstream — production wires a closure around ``substrate.dispatch``;
tests inject a deterministic stub.

Used by ``orchestration/`` (later sprints) to verify DAG-layer
answers before they propagate to children — the layer-by-layer
verifier gate is in ``verify_layer_answers``.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from ...constants import (
        RLM_VERIFY_AGREEMENT_MIN,
        RLM_VERIFY_REDISPATCH_COUNT,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import (  # type: ignore[no-redef]
        RLM_VERIFY_AGREEMENT_MIN,
        RLM_VERIFY_REDISPATCH_COUNT,
    )

from .types import VerificationResult


# ---------------------------------------------------------------------------
# Plausibility checks (cheap filters)
# ---------------------------------------------------------------------------


def check_numeric_range(
    value: Any,
    expected_min: Optional[float] = None,
    expected_max: Optional[float] = None,
) -> Optional[str]:
    """Return an issue string if a numeric value is outside the
    range; ``None`` for non-numeric (the type check is a separate
    rubric) or for values inside the range."""
    if not isinstance(value, (int, float)):
        return None
    if expected_min is not None and value < expected_min:
        return f"value {value} < expected_min {expected_min}"
    if expected_max is not None and value > expected_max:
        return f"value {value} > expected_max {expected_max}"
    return None


def check_sign(value: Any, expected_sign: str) -> Optional[str]:
    """``expected_sign`` is one of ``positive`` / ``negative`` /
    ``non-negative`` / ``non-positive``. Unknown signs are silently
    ignored (returning ``None``) so an upstream typo doesn't gate
    verification."""
    if not isinstance(value, (int, float)):
        return None
    checks = {
        "positive": lambda v: v > 0,
        "negative": lambda v: v < 0,
        "non-negative": lambda v: v >= 0,
        "non-positive": lambda v: v <= 0,
    }
    fn = checks.get(expected_sign)
    if fn and not fn(value):
        return f"value {value} does not satisfy sign={expected_sign}"
    return None


def check_units_rough(
    value: Any, expected_magnitude: Tuple[float, float],
) -> Optional[str]:
    """Flag values more than 3 orders of magnitude outside the
    expected ``(low, high)`` envelope. Generous on purpose — the goal
    is to catch unit-confusion bugs (m vs mm, GB vs MB), not enforce
    tight bounds."""
    if not isinstance(value, (int, float)):
        return None
    lo, hi = expected_magnitude
    if value < lo / 1000 or value > hi * 1000:
        return f"value {value} is >3 orders of magnitude outside [{lo}, {hi}]"
    return None


def check_expected_shape(value: Any, expected_type: type) -> Optional[str]:
    """Type check. ``None`` when types match; issue string otherwise."""
    if not isinstance(value, expected_type):
        return (
            f"expected type {expected_type.__name__}, got "
            f"{type(value).__name__}"
        )
    return None


def run_plausibility_checks(
    value: Any,
    *,
    expected_type: Optional[type] = None,
    expected_min: Optional[float] = None,
    expected_max: Optional[float] = None,
    expected_sign: Optional[str] = None,
    expected_magnitude: Optional[Tuple[float, float]] = None,
) -> List[str]:
    """Run all configured plausibility checks. Empty list ⇒ all
    checks passed. Caller (``verified_answer``) decides whether to
    reject or just flag."""
    issues: List[str] = []
    if expected_type is not None:
        iss = check_expected_shape(value, expected_type)
        if iss:
            issues.append(iss)
    if expected_min is not None or expected_max is not None:
        iss = check_numeric_range(value, expected_min, expected_max)
        if iss:
            issues.append(iss)
    if expected_sign is not None:
        iss = check_sign(value, expected_sign)
        if iss:
            issues.append(iss)
    if expected_magnitude is not None:
        iss = check_units_rough(value, expected_magnitude)
        if iss:
            issues.append(iss)
    return issues


# ---------------------------------------------------------------------------
# Rephrasing templates
# ---------------------------------------------------------------------------


REPHRASE_TEMPLATES: tuple[str, ...] = (
    # Framing 1: direct verification
    (
        "You are verifying a factual claim. Answer ONLY with the verified "
        "value, no explanation. If the claim cannot be verified from the "
        'context, say "UNVERIFIABLE".\n\n'
        "Claim: {claim}\n\n"
        "Context: {context}"
    ),
    # Framing 2: extract / count / compute
    (
        "Extract the precise answer to this question from the provided "
        "context. Return ONLY the answer as a single value (number or short "
        "string). No prose.\n\n"
        "Question: {claim}\n\n"
        "Context: {context}"
    ),
    # Framing 3 (tie-breaker): adversarial critique
    (
        "Critique this claim. Is it fully supported by the context? If YES, "
        "state the verified value. If NO, explain why not in one sentence.\n\n"
        "Claim: {claim}\n\n"
        "Context: {context}"
    ),
)


def rephrase_framings(claim: str, context: str, count: int = 2) -> List[str]:
    """Generate ``count`` rephrased prompts from the templates."""
    prompts: List[str] = []
    for i in range(min(count, len(REPHRASE_TEMPLATES))):
        prompts.append(REPHRASE_TEMPLATES[i].format(claim=claim, context=context))
    return prompts


# ---------------------------------------------------------------------------
# Agreement heuristic (response-text level)
# ---------------------------------------------------------------------------


def _normalize_response(s: str) -> str:
    return s.strip().lower().rstrip(".,;:!?\"'")


def _responses_agree(responses: List[str]) -> Tuple[bool, Optional[str]]:
    """Heuristic: two responses agree if their normalized forms match.

    Tiers in order:

    1. Exact normalized equality.
    2. Numeric tolerance — within 1% (catches LLM rounding noise).
    3. Majority vote — winner has ≥ ``RLM_VERIFY_AGREEMENT_MIN``.
    """
    if len(responses) < 2:
        return True, (responses[0] if responses else None)

    norms = [_normalize_response(r) for r in responses]

    if all(n == norms[0] for n in norms):
        return True, responses[0]

    try:
        nums = [float(n) for n in norms]
        if all(abs(n - nums[0]) / max(abs(nums[0]), 1e-9) < 0.01 for n in nums):
            return True, responses[0]
    except (ValueError, TypeError):
        pass

    c = Counter(norms)
    winner_norm, winner_count = c.most_common(1)[0]
    if winner_count >= RLM_VERIFY_AGREEMENT_MIN:
        for orig, norm in zip(responses, norms):
            if norm == winner_norm:
                return True, orig
        return True, responses[0]

    return False, None


def _count_agreements(responses: List[str]) -> int:
    """Number of responses matching the most-common normalized form."""
    if not responses:
        return 0
    norms = [_normalize_response(r) for r in responses]
    c = Counter(norms)
    return c.most_common(1)[0][1]


# ---------------------------------------------------------------------------
# Core: verify_claim
# ---------------------------------------------------------------------------


def verify_claim(
    claim: str,
    context: str,
    llm_batch_fn: Callable[[List[str]], List[str]],
    *,
    claim_id: str = "",
    redispatch_count: int = RLM_VERIFY_REDISPATCH_COUNT,
    agreement_min: int = RLM_VERIFY_AGREEMENT_MIN,
) -> VerificationResult:
    """Verify a single claim through independent re-dispatch.

    Phases:

    1. Build prompts — one direct + ``redispatch_count`` rephrased.
    2. Dispatch all via ``llm_batch_fn``.
    3. Check agreement; if ≥ ``agreement_min`` agree, accept.
    4. On disagreement, run one tie-breaker dispatch with adversarial
       framing + the prior responses included for context. Accept with
       ``hedged=True`` if the tie-breaker resolves; else surface the
       structured failure.
    """
    direct = (
        "Answer ONLY with the verified value, no explanation.\n\n"
        f"Claim: {claim}\n\nContext: {context}"
    )
    rephrased = rephrase_framings(claim, context, count=redispatch_count)
    all_prompts = [direct] + rephrased

    responses = llm_batch_fn(all_prompts)
    if not responses:
        return VerificationResult(
            claim_id=claim_id,
            accepted=False,
            agreement_count=0,
            dispatch_count=len(all_prompts),
            disagreement_reason="llm_batch returned empty results",
        )

    agreed, agreed_answer = _responses_agree(responses)
    agreement_count = _count_agreements(responses)
    if agreed and agreement_count >= agreement_min:
        return VerificationResult(
            claim_id=claim_id,
            accepted=True,
            agreement_count=agreement_count,
            dispatch_count=len(all_prompts),
            responses=responses,
            agreed_answer=agreed_answer,
        )

    # Tie-breaker
    tiebreaker_prompt = REPHRASE_TEMPLATES[2].format(claim=claim, context=context)
    tiebreaker_prompt += (
        "\n\nPrevious responses disagreed:\n"
        + "\n".join(f"  R{i}: {r[:200]}" for i, r in enumerate(responses))
        + "\n\nResolve the disagreement. State the correct value."
    )
    tb_responses = llm_batch_fn([tiebreaker_prompt])
    if tb_responses:
        responses.append(tb_responses[0])

    agreed2, agreed_answer2 = _responses_agree(responses)
    if agreed2:
        return VerificationResult(
            claim_id=claim_id,
            accepted=True,
            agreement_count=_count_agreements(responses),
            dispatch_count=len(all_prompts) + 1,
            responses=responses,
            agreed_answer=agreed_answer2,
            hedged=True,
        )

    return VerificationResult(
        claim_id=claim_id,
        accepted=False,
        agreement_count=_count_agreements(responses),
        dispatch_count=len(all_prompts) + 1,
        responses=responses,
        disagreement_reason=f"responses disagreed after {len(responses)} dispatches",
    )


# ---------------------------------------------------------------------------
# Combined gate: plausibility + re-dispatch
# ---------------------------------------------------------------------------


def verified_answer(
    claim: str,
    context: str,
    llm_batch_fn: Callable[[List[str]], List[str]],
    *,
    claim_id: str = "",
    expected_type: Optional[type] = None,
    expected_min: Optional[float] = None,
    expected_max: Optional[float] = None,
    expected_sign: Optional[str] = None,
    expected_magnitude: Optional[Tuple[float, float]] = None,
) -> VerificationResult:
    """Full verification gate for a claim that produces a single
    factual answer. Plausibility runs AFTER re-dispatch on the agreed
    answer (the value isn't known until verification produces it).
    Plausibility issues don't reject — they set ``hedged=True``."""
    result = verify_claim(
        claim=claim, context=context, llm_batch_fn=llm_batch_fn,
        claim_id=claim_id,
    )

    if result.accepted and result.agreed_answer is not None:
        try:
            val = float(result.agreed_answer.strip().rstrip(".,;:!?\""))
            issues = run_plausibility_checks(
                val,
                expected_type=expected_type or float,
                expected_min=expected_min,
                expected_max=expected_max,
                expected_sign=expected_sign,
                expected_magnitude=expected_magnitude,
            )
            if issues:
                result.plausibility_issues = issues
                result.hedged = True
        except (ValueError, TypeError):
            # Non-numeric answer — type check only.
            if expected_type is not None:
                issues = run_plausibility_checks(
                    result.agreed_answer, expected_type=expected_type,
                )
                if issues:
                    result.plausibility_issues = issues
                    result.hedged = True

    return result


# ---------------------------------------------------------------------------
# Bulk verification of DAG layer answers
# ---------------------------------------------------------------------------


def verify_layer_answers(
    answers: Dict[str, Any],
    node_specs: List[Dict[str, Any]],
    llm_batch_fn: Callable[[List[str]], List[str]],
) -> Dict[str, VerificationResult]:
    """Verify every non-null answer in a DAG layer before propagation.

    ``node_specs`` provides per-node ``id`` / ``question`` / ``deps``;
    ``answers`` maps ``node_id`` → computed value. For each node, the
    verifier builds a context string with the question + parent
    answers and calls ``verify_claim``.

    Null answers fail with ``disagreement_reason="answer is None"`` so
    the gate can distinguish "not yet computed" from "failed to
    verify"."""
    results: Dict[str, VerificationResult] = {}
    node_map = {n["id"]: n for n in node_specs}

    for node_id, answer in answers.items():
        if answer is None:
            results[node_id] = VerificationResult(
                claim_id=node_id,
                accepted=False,
                agreement_count=0,
                dispatch_count=0,
                disagreement_reason="answer is None",
            )
            continue

        spec = node_map.get(node_id, {})
        question = spec.get("question", node_id)
        deps = spec.get("deps", [])

        context_parts = [f"Question: {question}"]
        for dep in deps:
            if dep in answers and answers[dep] is not None:
                context_parts.append(f"Parent [{dep}]: {answers[dep]}")
        context = "\n".join(context_parts)

        claim = f"For question '{question}', the computed answer is: {answer}"
        results[node_id] = verify_claim(
            claim=claim, context=context, llm_batch_fn=llm_batch_fn,
            claim_id=node_id,
        )

    return results
