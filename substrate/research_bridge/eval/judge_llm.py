"""LLM-backed semantic judge for eval-precision (SPR-02 milestone 5).

The ``SubstringJudge`` baseline in ``scoring.py`` answers "does
extracted item A match labelled item B?" by substring containment.
That's deterministic and good for unit tests, but it under-counts
real matches: the operator labels a question "Will the verifier
toolkit consolidate?" and the LLM extracts "How quickly does
verifier-tooling parity arrive?" — semantically the same, zero
substring overlap.

This module builds a ``SemanticJudge`` that asks an LLM the yes/no
match question. It is the production judge SPR-06 uses to compute the
real S3 precision number against the operator's 20 hand-labelled
blocks.

Design — same discipline as the rest of the bridge:

  - The judge takes an injectable ``LlmCallable`` (the extractor's
    type). Tests pass a fake; production passes the dispatch wrapper.
    No API credits burned in CI.
  - The prompt asks for a single token — YES or NO — and we parse the
    first such token. We treat unparseable / empty responses as NO
    (a non-match), because the failure mode that matters is
    over-counting matches (inflating precision); under-counting is
    the safe direction for a gate.
  - The judge is order-symmetric in intent but we always pass
    (extracted, labelled) so the prompt can frame it as "does the
    candidate answer the labelled item." Determinism is the caller's
    concern (set temperature low in the dispatch tier).

Build it with ``build_llm_judge(llm_callable)`` and hand the result
to ``score_against_labels(..., judge=...)``.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Callable

try:
    from ..extractor import LlmCallable
    from .scoring import SemanticJudge
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(_here))))
    from substrate.research_bridge.extractor import LlmCallable  # type: ignore[no-redef]
    from substrate.research_bridge.eval.scoring import SemanticJudge  # type: ignore[no-redef]


# Bumped when the judge prompt changes such that the same pair now
# yields a different YES/NO. Stamped nowhere persistent today (the
# judge runs ad-hoc in eval-precision), but kept as the version
# anchor + CHANGELOG hook for when the eval results get archived.
JUDGE_VERSION: int = 1


_JUDGE_PROMPT = """You are grading a research-extraction system. The
operator hand-wrote an EXPECTED open question (or insight). The system
produced a CANDIDATE. Decide whether the candidate is the same
question/claim as the expected one — same underlying thing being
asked or asserted, even if the wording differs.

Answer with a single word: YES or NO. Nothing else.

EXPECTED: {labelled}
CANDIDATE: {extracted}

Same underlying question/claim? Answer YES or NO."""


_YES_NO_RE = re.compile(r"\b(YES|NO)\b", re.IGNORECASE)


def _parse_yes_no(text: str) -> bool:
    """Return True iff the first YES/NO token is YES. Unparseable →
    False (the safe direction for a precision gate — never inflate)."""
    m = _YES_NO_RE.search(text or "")
    if not m:
        return False
    return m.group(1).upper() == "YES"


def build_llm_judge(llm_callable: LlmCallable) -> SemanticJudge:
    """Build a ``SemanticJudge`` backed by ``llm_callable``.

    The returned function has the ``(extracted, labelled) -> bool``
    shape ``score_against_labels`` expects. Empty inputs short-circuit
    to False without an LLM call (matches SubstringJudge's contract
    and saves a pointless round-trip).
    """
    def _judge(extracted: str, labelled: str) -> bool:
        if not extracted.strip() or not labelled.strip():
            return False
        prompt = _JUDGE_PROMPT.format(
            labelled=labelled.strip()[:2000],
            extracted=extracted.strip()[:2000],
        )
        try:
            result = llm_callable(prompt)
        except Exception:
            # A judge call that errors must not crash the whole eval
            # run. Treat as NO (safe direction); the operator sees a
            # lower precision and can re-run.
            return False
        return _parse_yes_no(result.text)

    return _judge
