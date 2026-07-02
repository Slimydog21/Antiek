"""Tests for tools/lint/test_desiderata_check.py — the Beck-desiderata AST lint.

These tests assert the lint's OUTPUT on a hand-authored fixture corpus of known
violating and must-not-flag shapes. They RUN the lint (via ``find_violations`` and
the CLI module); they do NOT mock it. Per the sprint rigor bar, every assertion
checks the violation list the operator would see, not internal AST walkers.

Fixture layout:
  fixtures/desiderata/violations/ — true-positive shapes (must flag)
  fixtures/desiderata/clean/      — guard shapes (must NOT flag)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.lint.test_desiderata_check import (  # noqa: E402
    Violation,
    find_violations,
    main,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "desiderata"
_VIOLATIONS = _FIXTURES / "violations"
_CLEAN = _FIXTURES / "clean"
_PYTHON = sys.executable


def _lint(paths: list[Path], rule: str = "all") -> list[Violation]:
    rules = ("structure", "isolation", "determinism") if rule == "all" else (rule,)
    return find_violations(paths, rules=rules, root=_REPO)


def _hard(paths: list[Path], rule: str = "all") -> list[Violation]:
    return [v for v in _lint(paths, rule) if v.severity == "violation"]


def _by_rule(violations: list[Violation], rule: str) -> list[Violation]:
    return [v for v in violations if v.rule == rule]


def _paths_contain(violations: list[Violation], fragment: str) -> list[Violation]:
    return [v for v in violations if fragment in v.path]


# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------


def test_violation_render_matches_repo_lint_contract():
    v = Violation("tests/x.py", 10, "structure", "example message")
    assert v.render() == "tests/x.py:10: [structure] example message"


def test_cli_clean_fixtures_exit_zero():
    proc = subprocess.run(
        [
            _PYTHON,
            "-m",
            "tools.lint.test_desiderata_check",
            "--paths",
            str(_CLEAN.relative_to(_REPO)),
            "--rule",
            "all",
        ],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK: no test-desiderata violations" in proc.stdout


# ---------------------------------------------------------------------------
# Structure rule — true positive + guards
# ---------------------------------------------------------------------------


def test_structure_flags_only_call_shape_on_behavioral_mock():
    hits = _by_rule(_hard([_VIOLATIONS], "structure"), "structure")
    matched = _paths_contain(hits, "test_structure_only.py")
    assert len(matched) == 1
    assert "provider" in matched[0].message
    assert "structure-insensitive" in matched[0].message


def test_structure_spares_mixed_assertion_test():
    hits = _by_rule(_hard([_CLEAN], "structure"), "structure")
    assert not _paths_contain(hits, "test_mixed_assertions.py")


def test_structure_spares_retry_count_steelman():
    hits = _by_rule(_hard([_CLEAN], "structure"), "structure")
    assert not _paths_contain(hits, "test_retry_count.py")


# ---------------------------------------------------------------------------
# Isolation rule — true positive + guards
# ---------------------------------------------------------------------------


def test_isolation_flags_module_scoped_mutable_fixture():
    hits = _by_rule(_hard([_VIOLATIONS], "isolation"), "isolation")
    matched = _paths_contain(hits, "test_module_scope_mutable.py")
    assert len(matched) == 1
    assert "shared_bucket" in matched[0].message
    assert "Beck: isolated" in matched[0].message


def test_isolation_flags_module_global_mutation():
    hits = _by_rule(_hard([_VIOLATIONS], "isolation"), "isolation")
    matched = _paths_contain(hits, "test_global_mutation.py")
    assert len(matched) == 1
    assert "_MODULE_CACHE" in matched[0].message


def test_isolation_spares_function_scoped_fixture():
    hits = _by_rule(_hard([_CLEAN], "isolation"), "isolation")
    assert not _paths_contain(hits, "test_function_scope_fixture.py")


# ---------------------------------------------------------------------------
# Determinism rule — true positive + guards
# ---------------------------------------------------------------------------


def test_determinism_flags_unfrozen_clock_inline_in_assert():
    hits = _by_rule(_hard([_VIOLATIONS], "determinism"), "determinism")
    matched = _paths_contain(hits, "test_unfrozen_clock.py")
    assert len(matched) == 1
    assert "time()" in matched[0].message or "time" in matched[0].message


def test_determinism_flags_unseeded_rng_inline_in_assert():
    hits = _by_rule(_hard([_VIOLATIONS], "determinism"), "determinism")
    matched = _paths_contain(hits, "test_unseeded_rng.py")
    assert len(matched) == 1
    assert "uuid" in matched[0].message


def test_determinism_flags_raw_network_call():
    hits = _by_rule(_hard([_VIOLATIONS], "determinism"), "determinism")
    matched = _paths_contain(hits, "test_raw_network.py")
    assert len(matched) == 1
    assert "httpx.get" in matched[0].message
    assert "integration" in matched[0].message


def test_determinism_spares_frozen_seeded_mocked_guard():
    hits = _by_rule(_hard([_CLEAN], "determinism"), "determinism")
    assert not _paths_contain(hits, "test_frozen_seeded_mocked.py")


# ---------------------------------------------------------------------------
# Guard corpus stays clean end-to-end
# ---------------------------------------------------------------------------


def test_no_false_positives_on_guard_fixtures():
    assert main(["--paths", str(_CLEAN.relative_to(_REPO)), "--rule", "all"]) == 0