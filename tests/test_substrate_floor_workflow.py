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


def test_substrate_floor_mypy_covers_cli_and_perf_harness() -> None:
    text = _workflow_text()
    block = _step_block(text, "mypy --strict (Wave 1 substrate + lints + cli + perf harness)")
    assert (
        "mypy --strict --explicit-package-bases --namespace-packages" in block
    ), "substrate-floor must run strict mypy, not only ruff/tests"
    assert "tools/antiek_cli/check.py" in block, (
        "substrate-floor mypy must cover the antiek check CLI"
    )
    assert "tools/benchmarks/hot_paths" in block, (
        "substrate-floor mypy must cover the hot-path benchmark harness"
    )


def test_substrate_floor_runs_perf_cli_tests() -> None:
    text = _workflow_text()
    block = _step_block(text, "Unit tests — Wave 1 + Wave 2 + Wave 3 + Wave 4")
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
