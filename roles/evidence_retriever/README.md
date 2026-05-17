# roles/evidence_retriever/

Per sub-question evidence retrieval against the graph.

Input: a sub-question plus its evidence-type tags.
Output: a ranked candidate set of chunks/nodes/edges.

## Mechanics

Retrieval is embedding-first: surface candidates via vector proximity,
then apply typed filters (source tier, temporal window, evidence type).
The LLM step ranks and prunes — it never invents candidates.

## Tier

Flash. Volume is the binding constraint; this role runs many times per
investigation.

## Events emitted

- `run_retrieval` — one per call, with the candidate set
