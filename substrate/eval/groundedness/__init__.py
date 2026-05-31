"""Groundedness eval (Foundation v2 SPR-02) — the TRUTH axis.

Asks whether each synthesis claim ENTAILS from the chunk(s) it cites,
over the EXISTING claim→chunk provenance. This is deliberately NOT the
style rubric (``substrate/synthesis_rubric``), which scores FORM (voice,
conviction, citation *density*, constraint compliance) — a fluent,
confident, densely-cited LIE scores high on FORM. The two ship side by
side: groundedness is the truth-axis signal, the style rubric is the
explicitly SECONDARY form-axis signal.

Public surface:

- ``score_claim`` / ``score_synthesis_groundedness`` — the scorer.
- ``lexical_entailment_score`` — the deterministic default backend.
- ``make_llm_judge_backend`` — the optional (off-by-default) LLM-judge
  backend over the one Hermes-routed dispatch path.
- ``resolve_synthesis_claims`` + the chunk-text resolvers — read the
  existing provenance.
- ``GroundednessResult`` — synthesis-level result.

The offline harness is ``python -m substrate.eval.groundedness.harness``.
The promote-to-gate criterion is ``PROMOTE_TO_GATE.md``.
"""

from substrate.eval.groundedness.provenance import (
    duckdb_chunk_text_resolver,
    mapping_chunk_text_resolver,
    resolve_synthesis_claims,
)
from substrate.eval.groundedness.scorer import (
    DEFAULT_SCORER_ID,
    DEFAULT_SUPPORTED_THRESHOLD,
    GroundednessResult,
    lexical_entailment_score,
    make_llm_judge_backend,
    score_claim,
    score_synthesis_groundedness,
)

__all__ = [
    "DEFAULT_SCORER_ID",
    "DEFAULT_SUPPORTED_THRESHOLD",
    "GroundednessResult",
    "lexical_entailment_score",
    "make_llm_judge_backend",
    "score_claim",
    "score_synthesis_groundedness",
    "resolve_synthesis_claims",
    "mapping_chunk_text_resolver",
    "duckdb_chunk_text_resolver",
]
