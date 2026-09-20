# substrate/agent_skills — agent kernel skills (the CODING surface)

Three typed, standalone skills a research agent calls to **mine** and
**sculpt** data. No binary, no network, no GPU — pure Python functions
tested directly. Registry: `registry.list_skills()` returns the full
SKILL.md-style manifest catalog (parameters, returns, safety notes).

| Skill | Function family | What it does |
|---|---|---|
| `duckdb_store` | `create_store`, `run_sql`, `close` | Ephemeral **in-memory** DuckDB store: create tables, insert, query, typed rows. Cannot touch the corpus DB (single-writer invariant) — there is no path argument at all. |
| `py_analysis` | `summarize_rows`, `summarize_series`, `group_summarize` | Stdlib-only summary stats + grouped aggregations. No pandas/numpy (not core deps). Deterministic, missing-aware, kind-honest (numeric/categorical/mixed/empty). |
| `sketch_svg` | `sketch_svg` | Deterministic Processing/p5-inspired SVG — seeded generative composition or a bar sketch of a distribution. Every output is passed through the zero-script gate (`services.html_projection.gate`) before return. |

## Quick start

```python
from substrate.agent_skills import create_store, run_sql, summarize_rows, sketch_svg

# 1. Mine: put mined numbers somewhere typed.
store = create_store()
run_sql(store, "CREATE TABLE prices (sku VARCHAR, amount DOUBLE)")
run_sql(store, "INSERT INTO prices VALUES (?, ?)", params=("A1", 12.5))
q = run_sql(store, "SELECT sku, amount FROM prices ORDER BY amount DESC")
q.columns  # ('sku', 'amount')
q.as_dicts()

# 2. Analyze: what does the data say?
rows = [{"dept": "a", "amount": 10}, {"dept": "a", "amount": 20}, {"dept": "b", "amount": 5}]
report = summarize_rows(rows)
report.summary("amount").median
group_summarize(rows, key="dept", value="amount")

# 3. Sculpt: sketch it as a gate-verified SVG, embed in an HTML asset.
svg = sketch_svg(seed=7, title="price distribution", data=[1.5, 2.0, 2.5, 1.0])
```

## Invariants

- **Single-writer preserved.** The store is in-memory by construction; the
  sketch emits static bytes; analysis reads only. Nothing in this package
  can write to the corpus DuckDB (`runtime/db_lock` funnel is the sole
  graph writer).
- **Script-free by the real gate.** `sketch_svg` reuses
  `services.html_projection.gate.assert_script_free` on every emitted
  document before returning — same check the autonomous-ingest daemon
  would apply. A script-violating byte sequence raises loudly at
  generation time, never ships.
- **No heavy deps.** `duckdb` (already core), stdlib `statistics`,
  `collections`, `math`, `html`, `re`. Nothing added to `pyproject.toml`.
- **Deterministic.** Same inputs → same bytes: seeded splitmix64 PRNG,
  no clock/env/filesystem reads, canonical tie-ordering.
- **Bounded.** `max_rows` caps query results (reported, not silent);
  data sketches cap at 500 bars; invalid inputs raise named `ValueError`s.

## Contract notes

- SQL parameter binding is DuckDB's native `?` placeholder — mined
  (untrusted) values go through `params`, never string interpolation.
- `None` and non-finite values are **missing** in analysis: counted and
  excluded, never silently averaged. Mixed-kind columns are reported as
  `mixed`, never coerced.
- A `title` containing gate-flagged byte sequences (e.g. `src=javascript:`)
  raises `ScriptViolation` from `sketch_svg` — the gate is deliberately
  position-conservative; failing at generation beats failing at ingest.
