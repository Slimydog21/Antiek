"""Dependency contract for the canonical agent-execution workflow."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "agent_execution_gates.yml"


def test_deep_research_gate_installs_eager_pdf_reader_dependency() -> None:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["agent-execution-gates"]["steps"]
    install = next(
        step for step in steps
        if step.get("name") == "Install Antiek + canonical deep-research deps"
    )
    deep_research = next(
        step for step in steps
        if step.get("name") == "Canonical verify — deep-research (P-11..P-15)"
    )
    executable_lines = [
        line.strip() for line in install["run"].splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert 'pip install -c tools/lints/constraints.txt -e ".[dev,pdf]"' in (
        executable_lines
    )
    assert sum("pip install" in line and " -e " in line for line in executable_lines) == 1
    assert deep_research["run"] == "./scripts/canonical_verify.sh deep-research"
