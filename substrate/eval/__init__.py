"""Offline evaluation substrate.

Read-only, on-disk, no new datastore. The first resident is the
groundedness eval (Foundation v2 SPR-02): a per-claim entailment
scorer over the EXISTING claim→chunk provenance, plus an offline
harness that runs it over real Phase-6 traces and reports whether the
score separates faithful claims from hallucinated ones.

This is distinct from (and supersedes the role of) the dead
``substrate/research_bridge/eval/`` precision/recall scorer, which has
zero production callers — see ``substrate/eval/groundedness`` and the
NOTES carry-forward in PROMOTE_TO_GATE.md.
"""
