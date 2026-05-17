# roles/parameter_extractor/

Structured parameter extraction from retrieved evidence.

Input: a chunk plus a parameter schema (which fields to extract).
Output: a typed record conforming to the schema, with source
attribution.

## Tier

Flash. Schema-constrained output; the model can't go off the rails
because the schema is the contract.

## Events emitted

- `extract_node` — typed node with attribution
- `fail_constraint` — when extraction violates the schema
