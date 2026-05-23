"""Automatic synthesis rubric scoring (master-spec §14.4 wire-up).

The §14.4 dispatch tier-differentiation measurement gate assumes
``rubric.scored`` events fire after every synthesis. The G5 audit
(2026-05-23) found ``emit_rubric_scored`` was only called from test
code in production. This module wires the gap: an inline
deterministic rubric that runs immediately after Phase 6 exit in
``orchestration.loop_one.orchestrator``.

The rubric is fully deterministic — no LLM call, no extra cost,
runs in <1ms. It produces a composite score in [0, 1] from four
sub-components:

1. **Voice/style adherence** (`voice_style`) — re-uses the
   ``deterministic_voice_style_score`` heuristic from
   ``tools.prompt_autoresearch.score`` (em-dash density, padding
   constructions, hedging).
2. **Conviction-grounded score** (`conviction`) — the synthesizer's
   own ``conviction_level``, clamped to [0, 1].
3. **Citation density** (`citation_density`) — fraction of
   load-bearing claims with at least one supporting_chunk_id.
4. **Constraint compliance** (`constraint_compliance`) — the
   synthesis's own ``hard_constraints_satisfied`` field;
   1.0 when satisfied, 0.0 when not.

When the synthesis self-reports ``insufficient_evidence``, the
composite score floors at 0.1 — the synthesizer correctly declined
to fabricate, which is a small positive signal of constraint
discipline but cannot pass the §14.4 pass threshold of 0.5.

A judged component (`rubric.judged_score`) is intentionally left
None for now. Adding an LLM judge here would cost ~$0.005/synthesis
and is out of scope for the wire-up; the deterministic side is the
floor that the §14.4 gate needs to function at all.
"""

from substrate.synthesis_rubric.scorer import (
    CompositeRubricScore,
    score_synthesis,
)

__all__ = [
    "CompositeRubricScore",
    "score_synthesis",
]
