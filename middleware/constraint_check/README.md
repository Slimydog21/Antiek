# middleware/constraint_check/

Pre-flight + deterministic + LLM-qualitative checks.

## Three layers

1. **Pre-flight** — schema validation. Does the role's proposed output
   conform to `substrate/schemas/`? Failures are mechanical, fast, and
   cheap.
2. **Deterministic** — hard rules. Date ranges plausible? Numeric
   bounds within physical limits? Required citations present?
3. **LLM-qualitative** — judged rubrics. Does the synthesis hedge
   where the evidence tier requires hedging? Does the connector
   proposal cite the embedding candidates that produced it?

## Events emitted

- `fail_constraint` — with which layer failed and which rule
- Pass-through (no event) when all layers pass

## Discipline

A constraint fail does not retry blindly. Downstream code reads the
failure and decides whether to escalate, downgrade, or surface to a
human.
