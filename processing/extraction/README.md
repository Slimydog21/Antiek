# processing/extraction/

LLM-structured node and edge extraction. Reads chunks, emits typed
nodes and typed edges conforming to `substrate/schemas/graph.py`.

## Routing

Bulk work. Routes through the Flash tier in `substrate/dispatch/`
(`note_taker` and `parameter_extractor` roles). Token volume dominates
ingestion-phase spend; getting this routing right is what makes the
rental path economically viable.

## Output

For each chunk processed, emits:
- `extract_node` events — one per node identified
- `attach_edge` events — one per typed edge with source attribution
- `attribute_source` events — linking nodes/edges to chunk ID

## Schema constraint

Outputs must conform to `substrate/schemas/graph.py`. Schema violations
fire a `fail_constraint` event; downstream code reads the failure
rather than retrying blindly.
