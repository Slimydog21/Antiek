# DONE — agent kernel skills (DuckDB / Python analysis / Processing-SVG)

**Commit:** `2b5b751e9` on `swarm4/agent-kernel-skills` (purely additive:
9 files, +1876/−0; zero modifications to existing files). **No push.**

## What shipped

`substrate/agent_skills/` — a typed skill registry + 3 kernel skills, each a
typed function family + SKILL.md-style manifest (name, summary, description,
entrypoint, function family, parameters, returns, safety notes, examples):

| Skill | Functions | Notes |
|---|---|---|
| `duckdb_store` | `create_store`, `run_sql`, `close` | Ephemeral **in-memory** DuckDB store; `QueryResult` (columns, rows, row_count, truncated, `as_dicts()`); native `?`-placeholder binding; `max_rows` cap reported honestly. No path argument exists — cannot touch the corpus DB (single-writer invariant). |
| `py_analysis` | `summarize_rows`, `summarize_series`, `group_summarize` | **Stdlib-only** (`statistics`, `collections`) — pandas/numpy NOT added (verified `pyproject.toml`: neither is core). Kind-lattice (numeric/categorical/mixed/empty); None + non-finite counted as missing, never averaged; bools categorical; population stddev; canonical tie-ordering. |
| `sketch_svg` | `sketch_svg`, `SeededRng` | Deterministic splitmix64-seeded p5-style generative composition (nested circles grid) or faithful bar sketch of a distribution (zero-aware baseline). Every document is validated through the real zero-script gate (`services.html_projection.gate.assert_script_free`) before return. |

Registry: `list_skills()` → 3 manifests; `get_skill(name)`; `SKILLS` tuple.
Manifest contract in `substrate/agent_skills/manifest.py`
(`SkillManifest`/`SkillParameter`). Package README doubles as SKILL.md-style
usage doc. No `pyproject.toml` changes (duckdb already core; `services` is a
namespace package on the repo root path, same import pattern as
`substrate/multimedia/information_asset.py:13`).

## Acceptance results (for real)

```
$ ~/Antiek/platform/.venv/bin/python -m pytest tests/test_agent_skills.py -q
32 passed in 0.40s
```

Coverage of the four acceptance items (exact pass counts by area):
- **duckdb_store round-trip** — 7 tests: create/insert/query round-trip with
  typed `QueryResult`; bound-parameter injection safety (a value containing
  `; DROP TABLE` lands as data); `max_rows` truncation reported, never
  silent; idempotent close + closed-store guard; context-manager close;
  env-independence (works with `ANTIEK_DUCKDB_PATH` pointed at a bogus path);
  typed store instance.
- **py_analysis fixture stats** — 12 tests: hand-computed stats on fixtures
  (mean 25.0, pstdev √125, quartiles 12.5/25.0/37.5 verified against
  `statistics.quantiles` in-venv, min/median/max/sum, top-values);
  categorical/mixed/empty kinds; None+`inf`+`nan` counted as missing;
  bools categorical; numeric strings coerce; `summarize_rows` + `group
  _summarize` on the fixture with group ordering independent of row order;
  non-numeric group values → None stats (never coerced).
- **sketch_svg deterministic + gate-passing** — 10 tests: byte-identical
  regeneration (generative + data sketches); `gate.find_violations == []`
  across 5 seeds, 3 data sets, 3 titles (incl. non-ASCII); well-formed XML
  (ElementTree parse); caption + bar-count assertions; zero baseline on
  negative data; text escaping; gate-flagged title raises `ScriptViolation`
  at generation (live gate, not decorative); loud named `ValueError`s for
  every invalid input (0-width, empty/non-finite/501-value data, bad
  palette); `SeededRng` determinism.
- **registry manifests** — 3 tests: `list_skills()` = 3 manifests
  (`duckdb_store`, `py_analysis`, `sketch_svg`) each with summary,
  description, callable entrypoint, function family, returns, safety,
  examples; entrypoints are the real functions (`is` identity); `SKILLS`
  constant matches the registry.
- **dark import** — 1 test: package imports clean in a scrubbed subprocess
  env (all `ANTIEK_*`/`PRIME*` vars removed) and lists 3 skills. No
  network, no GPU, no prime-agent binary anywhere in the suite.

Lint + types (new code only, per brief):
```
$ ~/Antiek/platform/.venv/bin/python -m ruff check substrate/agent_skills/ tests/test_agent_skills.py
All checks passed!
$ ~/Antiek/platform/.venv/bin/python -m mypy substrate/agent_skills tests/test_agent_skills.py
Success: no issues found in 7 source files
```

Regression on the reused gate (sketch_svg imports it top-level, matching
`substrate/multimedia/*` precedent):
```
$ ~/Antiek/platform/.venv/bin/python -m pytest services/html_projection/tests/ -q
379 passed in 1.74s
```

## Honest gaps / notes

1. **Full-suite collection has 18 PRE-EXISTING errors**, verified unrelated
   to this work: `pytest tests/ --co -q --ignore=tests/test_agent_skills.py`
   reproduces them (8381 tests collect). All 18 are import failures in
   `tests/resilience/` + `tests/test_multimedia_visual_*` /
   `test_multimedia_reconciliation_*` (e.g. `No module named
   'tests.resilience'` — an import-mode quirk of this checkout's layout, not
   this package). Neighbor suites sharing the gate import surface pass:
   `tests/test_multimedia_information_asset.py` +
   `tests/test_html_projection_contract.py` → 30 passed.
2. **No prime-agent integration** (per brief non-goals): skills are
   standalone callables; wiring into a prime-agent kernel venv is a later
   lane. The spec's `runtime/prime_agent/kernel_skills/` location was
   deliberately NOT used — the brief's scope says `substrate/agent_skills/`,
   which this ships.
3. **DuckDB `Count` pseudo-result surfaced, not normalized**: `CREATE`/`INSERT`
   return `columns=("Count",)` (empty rows for DDL, `(n,)` affected count
   for DML) — the driver's real behavior, documented in the module
   docstring (a `SELECT Count FROM t` is indistinguishable by name, and the
   affected count is real information). Tests assert this contract.
4. **Quartile fallback for n < 4**: `statistics.quantiles(n=4)` extrapolates
   outside the observed range for tiny samples (verified: n=2 → p25 = 7.5
   for data 10,20); `py_analysis` falls back to observed min/max for n < 4,
   documented in the field docstring rather than shipped silently.
5. **`sketch_svg` title caveat**: a title containing gate-flagged byte
   sequences (e.g. `src=javascript:`) raises `ScriptViolation` — the gate
   is position-conservative; failing at generation beats failing at ingest.
6. Not run: the full 8k-test suite (18 collection errors above block a
   clean full run; out of scope for this bounded sub-goal), and no
   `benchmarks.rubric_latency`/test-integrity gates (untouched surfaces).
