# `connector` program

**What this role does**: traces relationships between claims and
parameters across the graph — causal, empirical, temporal, mechanistic.
Produces edges between nodes. The synthesizer uses these connections
to argue, not just enumerate.

**Why this role matters**: connector is the mechanism that turns a
graph of disconnected nodes into a graph that supports argumentation.
Without connector output, the synthesizer can only restate claims;
with it, the synthesizer can argue from premises to conclusions.

## What good output looks like

- Each connection has a typed relationship (`causes`, `enables`,
  `precedes`, `contradicts`, `corroborates`, `bounds`, `requires`,
  `falsifies`).
- Each connection cites the chunk(s) that warrant the connection.
  Connection edges are first-class graph edges with provenance.
- Connections respect direction. `A causes B` is not the same as
  `B causes A`; the connector preserves direction.
- Connections that span source tiers are flagged. A Tier-1 paper
  saying X corroborates a Tier-4 blog saying X is structurally
  different from two Tier-1 papers saying X.

## What to avoid (forbidden)

- Spurious connections — claims connected by topical similarity
  rather than mechanism.
- Overstated mechanisms — "A enables B" when the source only says
  "A is correlated with B."
- Bidirectional edges where the source clearly states direction.
- Connections that re-use the same chunk to support both the claims
  AND the connection between them (the connection needs independent
  warrant).

## Hypotheses to try when iterating

1. Require each connection to cite a chunk that is distinct from
   the chunks supporting the two endpoint claims (independent-warrant
   discipline). Measure spurious-connection rate.
2. Force the connector to surface contradictory connections, not
   just supporting ones (`A contradicts B` is as important as
   `A enables B`). Measure challenger-role triggering downstream.
3. Time-bound connections — `A precedes B` requires temporal
   evidence. Reject connections that imply temporality without
   timestamps.

## Cross-references

- Master-spec §2.3 (graph as accumulating product; connector edges
  are what make it a graph and not a bag of nodes)
- Substrate `substrate/graph/traverse.py` (the 4 recursive-CTE
  traversal algorithms operate on connector output)
