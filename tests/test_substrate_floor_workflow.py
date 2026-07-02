from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_WORKFLOW = _REPO / ".github" / "workflows" / "substrate_floor.yml"


def _workflow_text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def _step_block(text: str, step_name: str) -> str:
    marker = f"      - name: {step_name}"
    start = text.index(marker)
    end = text.find("\n      - name:", start + len(marker))
    return text[start:] if end == -1 else text[start:end]


def _scope_files(text: str) -> str:
    marker = "      SCOPE_FILES: "
    for line in text.splitlines():
        if line.startswith(marker):
            return line.removeprefix(marker)
    raise AssertionError("substrate-floor SCOPE_FILES env not found")


def test_substrate_floor_mypy_covers_cli_and_perf_harness() -> None:
    text = _workflow_text()
    block = _step_block(
        text,
        "mypy --strict (substrate quality + lints + cli + perf harness)",
    )
    assert (
        "mypy --strict --explicit-package-bases --namespace-packages" in block
    ), "substrate-floor must run strict mypy, not only ruff/tests"
    assert "tools/antiek_cli/check.py" in block, (
        "substrate-floor mypy must cover the antiek check CLI"
    )
    assert "tools/benchmarks/hot_paths" in block, (
        "substrate-floor mypy must cover the hot-path benchmark harness"
    )


def test_substrate_floor_covers_paved_road_modules() -> None:
    text = _workflow_text()
    scope_files = _scope_files(text)
    mypy_block = _step_block(
        text,
        "mypy --strict (substrate quality + lints + cli + perf harness)",
    )
    unit_block = _step_block(text, "Unit tests — substrate quality waves")
    doctest_block = _step_block(text, "Doctests on substrate quality modules")

    for path in (
        "substrate/result_helpers.py",
        "substrate/ownership.py",
        "substrate/exhaustive.py",
        "docs/decisions/are-wave-5-paved-roads.md",
        "docs/substrate_quality_toolkit.md",
        "tests/test_result_helpers.py",
        "tests/test_ownership.py",
        "tests/test_exhaustive.py",
    ):
        assert f"- '{path}'" in text, f"{path} must trigger substrate-floor"

    for module in (
        "substrate/result_helpers.py",
        "substrate/ownership.py",
        "substrate/exhaustive.py",
    ):
        assert module in scope_files, f"{module} must be in substrate-floor SCOPE_FILES"
        assert "$SCOPE_FILES" in mypy_block, "strict mypy must consume SCOPE_FILES"
        assert "$SCOPE_FILES" in doctest_block, "doctests must consume SCOPE_FILES"

    for test_path in (
        "tests/test_result_helpers.py",
        "tests/test_ownership.py",
        "tests/test_exhaustive.py",
    ):
        assert test_path in unit_block, f"{test_path} must run in substrate-floor"


def test_substrate_floor_runs_perf_cli_tests() -> None:
    text = _workflow_text()
    block = _step_block(text, "Unit tests — substrate quality waves")
    assert "- 'tests/test_antiek_cli_perf.py'" in text, (
        "perf CLI test changes must trigger substrate-floor"
    )
    assert "            tests/test_antiek_cli_perf.py \\" in block, (
        "substrate-floor unit step must run the perf CLI tests"
    )
    assert "- 'tests/test_substrate_floor_workflow.py'" in text, (
        "this workflow guard must trigger substrate-floor when edited"
    )
    assert "            tests/test_substrate_floor_workflow.py \\" in block, (
        "substrate-floor unit step must run its own workflow guard"
    )
