# tests/

Pytest. Three subdirectories:

- **`unit/`** — Per-module unit tests. Run on every commit, must be fast.
- **`integration/`** — Cross-module tests. May spin up DuckDB, may
  exercise dispatch with mock providers. Slower; run on every PR.
- **`fixtures/`** — Shared test data (sample chunks, sample events,
  sample skill files for diff tests).

## Critical tests (from the validation criteria)

The spec lists tests that must pass before the build is considered
complete (architecture_notes.md "validation criteria" section, plus
the spec's "validation criteria" section):

- Side-by-side test on 10 historical investigations from kanban
  history shows no regression in synthesis quality.
- End-to-end interview test: capture (audio or text) → chunking →
  extraction → graph entry with attribution → pass.
- DuckDB write-lock under concurrent load (simulated daily cron +
  weekly monitor + on-demand kanban): no corrupted writes, no
  deadlocks.
- Compounding-skill verifier: manually skip a Phase 8 execution,
  confirm the alert fires.
- User Agent: can simulate realistic interview subjects for
  development purposes (qualitative; tracked as a fixture set).

## Conventions

- Filenames: `test_<module>.py` mirroring the source structure.
- Markers: `@pytest.mark.integration` for tests that touch DuckDB or
  network.
- Async: `pytest-asyncio` in auto mode (configured in `pyproject.toml`).
