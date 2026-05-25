"""Hot-path measurement harness — ARE-12 of the Antiek Rust-Execution Spec.

Each ``bench_*.py`` module exposes a ``run() -> list[BenchResult]``
function that captures median + p95 + p99 + iterations + metadata,
suitable for JSON serialization. The driver (``__main__.py``) runs
every registered benchmark.

stdlib-only (``time.perf_counter_ns``); no new dependency added.
``pytest-benchmark`` was considered and rejected per the
invariants-pointer discipline (no pyproject direct-dep changes).
"""
