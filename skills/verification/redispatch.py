"""Independent re-dispatch verification.

Verbatim port of Researchmaxx ``verify.verify_with_redispatch``
(Sprint 6 day 3-4). The empirically strongest reliability mechanism
in the published RLM literature is re-dispatching a role with
**rephrased** instructions and accepting the answer only on
agreement — cheaper and more reliable than building a separate
verifier role with its own prompt.

The ``role_runner`` is **callable-injected**: this module does NOT
import ``substrate.dispatch`` or any orchestrator entry point.
The signature contract is::

    runner(role: str, *, placeholders: dict,
           extra_user_prefix: str = "", ...) -> dict_with_parsed_key

Production wires a closure around the orchestrator's role-call
function; tests inject a stub returning canned trace records.

Use cases:

1. **Constraint-loop fallback** — after ``max_iterations_reached``,
   re-dispatch the synthesizer with one rephrased framing. If they
   agree, ship with a hedged tier; if they disagree, the archived
   synthesis carries the disagreement reason for backtesting.
2. **Decomposer paraphrase regeneration** — a second framing is a
   cheaper consistency check than another full pipeline run.
3. **Outcome-record self-checks** — re-derive a judgment from a
   different angle before writing it to the outcomes table.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable, Dict, List, Optional

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

from .agreement import default_agreement_strict
from .types import VerifyResult


def _rephrase_prefix(framing: str) -> str:
    """Wrap a framing instruction so it leads the user prompt for the
    re-dispatched call. Tells the model to disregard anchoring on the
    earlier answer."""
    return (
        "## Independent re-derivation (verification pass)\n"
        "An earlier dispatch produced an answer for this exact task. "
        "Disregard any anchoring on that earlier answer and derive your "
        "response again, framed as follows:\n\n"
        f"{framing.strip()}\n\n"
        "Return the same structured-output schema as before."
    )


_DEFAULT_FIRST_PRINCIPLES_FRAMING = (
    "Derive the answer purely from first principles using only the "
    "provided evidence; produce no narrative justification beyond what "
    "the schema requires."
)

_TIEBREAKER_FRAMING = (
    "Two independent dispatches produced disagreeing answers for this "
    "task. Without seeing either prior answer, derive the answer one "
    "more time using only the evidence in the user message. Be "
    "especially careful about load-bearing fields (falsification "
    "conditions, recommendation, cited chunk_ids)."
)


def verify_with_redispatch(
    role_runner: Callable[..., Dict],
    role: str,
    placeholders: Dict[str, str],
    original_parsed: Dict,
    *,
    framings: Optional[List[str]] = None,
    agreement_fn: Callable[[Dict, Dict], bool] = default_agreement_strict,
    agreement_min: int = RLM_VERIFY_AGREEMENT_MIN,
    redispatch_count: int = RLM_VERIFY_REDISPATCH_COUNT,
    enable_tiebreaker: bool = True,
) -> VerifyResult:
    """Re-dispatch ``role`` with rephrased framings, compare each
    result to ``original_parsed`` via ``agreement_fn``.

    If ``agreement_min`` (counting the original) is met, ``agreed=True``.
    On disagreement, when ``enable_tiebreaker``, fire one more dispatch
    with a synthetic "evaluate the disagreement" framing and treat
    its agreement-with-original as the tie-break.

    The original is counted as one vote. ``redispatch_count`` framings
    add one vote each. The tie-breaker adds at most one more.
    """
    if framings is None:
        framings = [_DEFAULT_FIRST_PRINCIPLES_FRAMING][:redispatch_count]
        if not framings:
            framings = ["Re-derive independently with fresh framing."]
    framings = framings[:redispatch_count] if redispatch_count > 0 else framings

    votes: List[Dict[str, Any]] = [
        {"source": "original", "framing": None, "agrees_with_original": True}
    ]
    dispatched_responses: List[Dict[str, Any]] = []
    agreement_count = 1  # original counts toward agreement

    for i, framing in enumerate(framings):
        record = role_runner(
            role,
            placeholders=placeholders,
            extra_user_prefix=_rephrase_prefix(framing),
        )
        parsed = record.get("parsed") if isinstance(record, dict) else None
        agrees = bool(parsed is not None and agreement_fn(original_parsed, parsed))
        if agrees:
            agreement_count += 1
        votes.append({
            "source": f"rephrased_{i + 1}",
            "framing": framing,
            "agrees_with_original": agrees,
        })
        dispatched_responses.append(record)

    agreed = agreement_count >= agreement_min
    tiebreaker_used = False

    if not agreed and enable_tiebreaker and len(framings) >= 1:
        tb_record = role_runner(
            role,
            placeholders=placeholders,
            extra_user_prefix=_rephrase_prefix(_TIEBREAKER_FRAMING),
        )
        tb_parsed = tb_record.get("parsed") if isinstance(tb_record, dict) else None
        tb_agrees_with_original = bool(
            tb_parsed is not None and agreement_fn(original_parsed, tb_parsed)
        )
        votes.append({
            "source": "tiebreaker",
            "framing": _TIEBREAKER_FRAMING,
            "agrees_with_original": tb_agrees_with_original,
        })
        dispatched_responses.append(tb_record)
        if tb_agrees_with_original:
            agreement_count += 1
            agreed = agreement_count >= agreement_min
        tiebreaker_used = True

    return VerifyResult(
        agreed=agreed,
        agreement_count=agreement_count,
        dispatched_count=1 + len(framings) + (1 if tiebreaker_used else 0),
        votes=votes,
        dispatched_responses=dispatched_responses,
        tiebreaker_used=tiebreaker_used,
        notes=(
            "Used for constraint-loop fallback OR opportunistic check. "
            "Caller decides what to do with `agreed`."
        ),
    )
