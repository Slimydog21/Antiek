# roles/connector/

Cross-domain connection via graph traversal.

Critically, the LLM is constrained to propose connections only among
candidates already surfaced by embedding search. This prevents
hallucinated cross-domain links — the connector cannot "imagine" a
relationship between quantum and semiconductor research; it can only
elevate a relationship that the embedding index already suggested.

See architecture_notes §4 (preserved strengths of the existing codebase).

## Tier

Pro. The reasoning is "given these N candidate connections, which
ones are real, which ones are coincidence, and which ones are
load-bearing for the current synthesis?"

## Events emitted

- `attach_edge` — for each accepted connection
- `mark_stale` — when the connector identifies an edge that should be
  re-evaluated under newer evidence
