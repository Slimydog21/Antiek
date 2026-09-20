"""Agent kernel skills acceptance suite (swarm sub-goal).

Covers the four acceptance items, for real:

1. ``duckdb_store`` round-trips create/insert/query and returns typed
   rows (``QueryResult`` with columns, rows, row_count, truncated).
2. ``py_analysis`` returns correct summary stats on a fixture dataset —
   expected values are hand-computed and hardcoded, not derived from the
   implementation under test.
3. ``sketch_svg`` emits deterministic SVG that passes the zero-script
   gate (``services.html_projection.gate.find_violations`` returns [])
   — the same gate the autonomous-ingest daemon would apply.
4. the registry lists all 3 skills with their manifests.

Hermetic by contract: no network, no GPU, no prime-agent binary. The
only subprocess is the dark-import check, which scrubs ``ANTIEK_*`` /
``PRIME*`` env vars and proves the package imports clean with none of
them set (the kernel-skills dark-import discipline).
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from services.html_projection.gate import ScriptViolation, find_violations
from substrate.agent_skills import (
    AnalysisReport,
    DuckDBStore,
    QueryResult,
    SeededRng,
    SeriesSummary,
    create_store,
    get_skill,
    group_summarize,
    list_skills,
    run_sql,
    sketch_svg,
    summarize_rows,
    summarize_series,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

FIXTURE_ROWS: tuple[dict[str, object], ...] = (
    {"dept": "a", "amount": 10},
    {"dept": "a", "amount": 20},
    {"dept": "b", "amount": 5},
)


# ── 1. duckdb_store: round-trip + typed rows ──


class TestDuckDBStore:
    def test_round_trip_create_insert_query(self) -> None:
        """Acceptance: create/insert/query round-trip with typed rows."""
        store = create_store()
        try:
            ddl = run_sql(store, "CREATE TABLE prices (sku VARCHAR, amount DOUBLE)")
            assert isinstance(ddl, QueryResult)
            # DuckDB answers DDL with its Count pseudo-result: no rows.
            assert ddl.columns == ("Count",)
            assert ddl.rows == ()
            assert ddl.row_count == 0
            assert not ddl.truncated

            ins = run_sql(
                store,
                "INSERT INTO prices VALUES ('A1', 12.5), ('B2', 7.25), ('C3', 99.0)",
            )
            # DML surfaces the affected-row count (surfaced, not normalized).
            assert ins.rows == ((3,),)
            q = run_sql(store, "SELECT sku, amount FROM prices ORDER BY amount DESC")
            assert q.columns == ("sku", "amount")
            assert q.rows == (("C3", 99.0), ("A1", 12.5), ("B2", 7.25))
            assert q.row_count == 3
            assert not q.truncated
            assert q.as_dicts() == (
                {"sku": "C3", "amount": 99.0},
                {"sku": "A1", "amount": 12.5},
                {"sku": "B2", "amount": 7.25},
            )
        finally:
            store.close()

    def test_bound_parameters_never_interpolated(self) -> None:
        """Native ?-placeholders bind mined values; ordering is explicit."""
        store = create_store()
        try:
            run_sql(store, "CREATE TABLE prices (sku VARCHAR, amount DOUBLE)")
            for sku, amount in (("A1", 12.5), ("B2", 7.25), ("C3", 99.0), ("D4", 3.5)):
                run_sql(store, "INSERT INTO prices VALUES (?, ?)", params=(sku, amount))
            q = run_sql(
                store,
                "SELECT sku FROM prices WHERE amount > ? ORDER BY sku",
                params=(10.0,),
            )
            assert q.rows == (("A1",), ("C3",))
            # A value containing SQL syntax cannot alter the query.
            run_sql(
                store,
                "INSERT INTO prices VALUES (?, ?)",
                params=("O'Reilly; DROP TABLE prices; --", 1.0),
            )
            assert run_sql(store, "SELECT count(*) AS n FROM prices").rows == ((5,),)
        finally:
            store.close()

    def test_max_rows_caps_and_reports_truncation(self) -> None:
        """The cap is honest: truncated=True, never silent loss."""
        store = create_store()
        try:
            run_sql(store, "CREATE TABLE t (x INTEGER)")
            for i in range(5):
                run_sql(store, "INSERT INTO t VALUES (?)", params=(i,))
            q = run_sql(store, "SELECT x FROM t ORDER BY x", max_rows=2)
            assert q.row_count == 2
            assert q.truncated
            assert q.rows == ((0,), (1,))
            full = run_sql(store, "SELECT x FROM t ORDER BY x")
            assert full.row_count == 5
            assert not full.truncated
        finally:
            store.close()

    def test_close_is_idempotent_and_guards_use(self) -> None:
        store = create_store()
        store.close()
        store.close()  # no-op, must not raise
        assert store.is_closed
        with pytest.raises(ValueError, match="closed"):
            run_sql(store, "SELECT 1")
        with pytest.raises(ValueError, match="max_rows"):
            # Valid open store, invalid cap:
            store2 = create_store()
            try:
                run_sql(store2, "SELECT 1", max_rows=0)
            finally:
                store2.close()

    def test_context_manager_closes(self) -> None:
        with create_store() as store:
            run_sql(store, "CREATE TABLE t (x INTEGER)")
        assert store.is_closed

    def test_ephemeral_and_env_independent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The store never consults corpus env vars — it cannot collide."""
        monkeypatch.setenv("ANTIEK_DUCKDB_PATH", "/nonexistent/corpus.db")
        store = create_store()
        try:
            run_sql(store, "CREATE TABLE t (x INTEGER)")
            run_sql(store, "INSERT INTO t VALUES (1), (2), (3)")
            q = run_sql(store, "SELECT sum(x) AS s FROM t")
            assert q.rows == ((6,),)
        finally:
            store.close()

    def test_store_is_typed(self) -> None:
        assert isinstance(create_store(), DuckDBStore)


# ── 2. py_analysis: correct stats on fixtures ──


class TestPyAnalysis:
    def test_numeric_summary_stats(self) -> None:
        """Acceptance: hand-computed stats on a fixture series."""
        s = summarize_series([10, 20, 30, 40], name="amount")
        assert isinstance(s, SeriesSummary)
        assert s.kind == "numeric"
        assert s.count == 4
        assert s.missing == 0
        assert s.distinct == 4
        assert s.mean == 25.0
        assert s.stddev == pytest.approx(math.sqrt(125.0))
        assert s.total == 100.0
        assert (s.minimum, s.median, s.maximum) == (10.0, 25.0, 40.0)
        # statistics.quantiles(n=4), exclusive method, verified in-venv:
        assert (s.p25, s.p75) == (12.5, 37.5)
        # Singletons ordered by label — deterministic regardless of order.
        assert s.top_values == (("10", 1), ("20", 1), ("30", 1), ("40", 1))

    def test_categorical_column(self) -> None:
        s = summarize_series(["red", "blue", "red", "green", "red"])
        assert s.kind == "categorical"
        assert s.count == 5
        assert s.distinct == 3
        assert s.mean is None and s.minimum is None and s.total is None
        assert s.top_values == (("red", 3), ("blue", 1), ("green", 1))

    def test_mixed_column_is_reported_not_coerced(self) -> None:
        s = summarize_series([1, "x", 2.5])
        assert s.kind == "mixed"
        assert s.count == 3
        assert s.mean is None  # never a half-coerced mean
        assert s.top_values == (("1", 1), ("2.5", 1), ("x", 1))

    def test_missing_and_non_finite_are_counted_not_averaged(self) -> None:
        s = summarize_series([None, 1, "inf", 2, float("nan")])
        assert s.kind == "numeric"
        assert s.count == 2
        assert s.missing == 3
        assert s.mean == 1.5
        assert s.total == 3.0
        assert s.median == 1.5
        assert s.stddev == pytest.approx(0.5)
        # n < 4: quartiles fall back to observed extremes (documented).
        assert (s.p25, s.p75) == (1.0, 2.0)

    def test_empty_series(self) -> None:
        assert summarize_series([]).kind == "empty"
        s = summarize_series([None, None])
        assert s.kind == "empty"
        assert s.count == 0
        assert s.missing == 2

    def test_bools_are_categorical_never_numeric(self) -> None:
        s = summarize_series([True, False, True])
        assert s.kind == "categorical"
        # Largest-first, ties by label.
        assert s.top_values == (("True", 2), ("False", 1))

    def test_numeric_strings_coerce(self) -> None:
        s = summarize_series(["10", "20", "30"])
        assert s.kind == "numeric"
        assert s.mean == 20.0

    def test_summarize_rows_fixture(self) -> None:
        """Acceptance: correct summary stats on the fixture dataset."""
        report = summarize_rows(FIXTURE_ROWS)
        assert isinstance(report, AnalysisReport)
        assert report.row_count == 3
        assert report.columns == ("dept", "amount")
        amounts = report.summary("amount")
        assert amounts is not None
        assert amounts.kind == "numeric"
        assert amounts.mean == pytest.approx(35.0 / 3.0)
        assert amounts.minimum == 5.0
        assert amounts.maximum == 20.0
        assert report.summary("nope") is None

    def test_group_summarize_fixture(self) -> None:
        """Acceptance: grouped aggregation on the fixture dataset."""
        groups = group_summarize(FIXTURE_ROWS, key="dept", value="amount")
        assert [g.group for g in groups] == ["a", "b"]
        a, b = groups
        assert a.count == 2
        assert (a.total, a.mean, a.minimum, a.maximum) == (30.0, 15.0, 10.0, 20.0)
        assert b.count == 1
        assert (b.total, b.mean, b.minimum, b.maximum) == (5.0, 5.0, 5.0, 5.0)

    def test_group_order_is_input_order_independent(self) -> None:
        rev = group_summarize(FIXTURE_ROWS[::-1], key="dept", value="amount")
        assert [g.group for g in rev] == ["a", "b"]

    def test_group_with_non_numeric_values_reports_none_stats(self) -> None:
        g = group_summarize([{"k": "g1", "v": "x"}], key="k", value="v")
        assert g[0].count == 1
        assert g[0].total is None and g[0].mean is None

    def test_group_missing_key_groups_under_none_label(self) -> None:
        g = group_summarize([{"v": 1}], key="k", value="v")
        assert g[0].group == "None"
        assert g[0].count == 1


# ── 3. sketch_svg: deterministic + gate-passing ──


class TestSketchSvg:
    def test_generative_sketch_is_deterministic(self) -> None:
        assert sketch_svg(seed=11) == sketch_svg(seed=11)
        assert sketch_svg(seed=11) != sketch_svg(seed=12)

    def test_data_sketch_is_deterministic(self) -> None:
        data = [1.5, 2.0, 2.5, 1.0]
        assert sketch_svg(seed=3, data=data) == sketch_svg(seed=3, data=data)

    def test_output_passes_the_zero_script_gate(self) -> None:
        """Acceptance: every emitted SVG passes gate.find_violations."""
        for seed in (0, 1, 7, 42, 99):
            assert find_violations(sketch_svg(seed=seed)) == []
        for data in ([1.0, -2.0, 3.5], [1.0], [0.0, 0.0, 0.0]):
            assert find_violations(sketch_svg(seed=0, data=data)) == []
        for title in ("price distribution", "a <b> &amp; c", "féminin · évolution"):
            assert find_violations(sketch_svg(seed=1, title=title)) == []

    def test_output_is_well_formed_xml(self) -> None:
        ET.fromstring(sketch_svg(seed=2))
        ET.fromstring(sketch_svg(seed=2, data=[1.0, 2.0, 3.0]))

    def test_data_sketch_caption_and_bar_count(self) -> None:
        data = [1.5, 2.0, 2.5, 1.0]
        svg = sketch_svg(seed=0, title="prices", data=data)
        assert "mean 1.75" in svg
        assert "n 4" in svg
        # 1 background rect + one rect per value.
        assert svg.count("<rect") == len(data) + 1
        # Zero-aware baseline when data goes negative.
        neg = sketch_svg(seed=0, data=[-3.0, -1.0, 2.0, 4.0])
        assert neg.count("<line") == 1

    def test_text_is_escaped(self) -> None:
        svg = sketch_svg(seed=0, title="a <b> &amp; c")
        assert "&lt;b&gt;" in svg
        assert "<b>" not in svg

    def test_gate_flagged_title_raises_loudly_at_generation(self) -> None:
        """The gate is live, not decorative: a flagged byte sequence fails
        at generation time, never reaching an artifact."""
        with pytest.raises(ScriptViolation):
            sketch_svg(title="src=javascript:alert(1)")

    def test_input_validation_is_loud_and_named(self) -> None:
        with pytest.raises(ValueError, match="positive ints"):
            sketch_svg(width=0)
        with pytest.raises(ValueError, match="positive ints"):
            sketch_svg(height=-5)
        with pytest.raises(ValueError, match="non-empty"):
            sketch_svg(data=[])
        with pytest.raises(ValueError, match="finite"):
            sketch_svg(data=[1.0, float("nan")])
        with pytest.raises(ValueError, match="capped"):
            sketch_svg(data=list(range(501)))
        with pytest.raises(ValueError, match="#RRGGBB"):
            sketch_svg(palette=("#fff", "#000"))
        with pytest.raises(ValueError, match=">= 2"):
            sketch_svg(palette=("#ffffff",))

    def test_seeded_rng_is_deterministic(self) -> None:
        r1, r2 = SeededRng(9), SeededRng(9)
        assert [r1.uniform() for _ in range(8)] == [r2.uniform() for _ in range(8)]
        assert all(0.0 <= SeededRng(9).uniform() < 1.0 for _ in range(10))
        assert SeededRng(9).uniform() != SeededRng(10).uniform()


# ── 4. registry: lists all 3 skills with manifests ──


class TestRegistry:
    def test_registry_lists_all_three_skills_with_manifests(self) -> None:
        """Acceptance: the registry lists all 3 skills with their manifests."""
        manifests = list_skills()
        assert [m.name for m in manifests] == ["duckdb_store", "py_analysis", "sketch_svg"]
        for m in manifests:
            assert m.summary
            assert m.description
            assert callable(m.entrypoint)
            assert m.functions and m.functions[0] == m.entrypoint.__name__
            assert m.returns
            assert m.safety
            assert m.examples
            assert isinstance(m.parameters, tuple)

    def test_registry_entrypoints_are_the_real_functions(self) -> None:
        # importlib, not `import pkg.sub as x`: the package __init__ binds
        # the sketch_svg FUNCTION into the package namespace, shadowing the
        # submodule attribute that `import ... as` resolves through.
        import importlib

        ds = importlib.import_module("substrate.agent_skills.duckdb_store")
        pa = importlib.import_module("substrate.agent_skills.py_analysis")
        ss = importlib.import_module("substrate.agent_skills.sketch_svg")

        ds_m = get_skill("duckdb_store")
        pa_m = get_skill("py_analysis")
        ss_m = get_skill("sketch_svg")
        assert ds_m is not None and ds_m.entrypoint is ds.create_store
        assert pa_m is not None and pa_m.entrypoint is pa.summarize_rows
        assert ss_m is not None and ss_m.entrypoint is ss.sketch_svg
        assert get_skill("no_such_skill") is None

    def test_registry_matches_module_constant(self) -> None:
        from substrate.agent_skills.registry import SKILLS

        assert tuple(list_skills()) == SKILLS


# ── dark import: package loads with no ANTIEK/PRIME env at all ──


def test_dark_import_with_no_antiek_env() -> None:
    """The package imports clean in a scrubbed environment (no ANTIEK_*,
    no PRIME* vars) — the kernel-skills dark-import discipline."""
    env = {
        k: v
        for k, v in os.environ.items()
        if "ANTIEK" not in k.upper() and "PRIME" not in k.upper()
    }
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import substrate.agent_skills as s; "
            "from substrate.agent_skills.registry import list_skills; "
            "print(len(list_skills()))",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "3"
