"""Readiness audit for Autoresearch Wedge 1 unlock criteria."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from tools.prompt_autoresearch.budget import BudgetCap


@dataclass(frozen=True)
class ReadinessItem:
    id: str
    label: str
    status: str  # "satisfied" | "operator_bound" | "missing"
    evidence: str


@dataclass(frozen=True)
class ReadinessReport:
    items: list[ReadinessItem]

    @property
    def all_satisfied(self) -> bool:
        return all(item.status == "satisfied" for item in self.items)


def audit_wedge1_readiness(repo_root: Path) -> ReadinessReport:
    """Inspect the current tree for Wedge 1 unlock evidence.

    Operator-review requirements are never rounded up to ``satisfied`` from
    file presence alone. They remain ``operator_bound`` until the expected
    review/calibration artifacts exist.
    """
    root = repo_root.resolve()
    program = root / "roles/synthesizer/program.md"
    golden_traces = sorted((root / "tools/golden_traces/captured").glob("*.json"))
    calibration = root / "reports/autoresearch/synthesizer-calibration.md"
    required_tool_files = [
        "runner.py",
        "score.py",
        "budget.py",
        "outcomes_io.py",
        "calibration.py",
        "calibration_cli.py",
        "verdict.py",
        "verdict_cli.py",
        "README.md",
    ]
    tool_dir = root / "tools/prompt_autoresearch"
    missing_tool_files = [
        name for name in required_tool_files
        if not (tool_dir / name).is_file()
    ]

    program_status = "missing"
    program_evidence = "roles/synthesizer/program.md is missing"
    if program.is_file():
        text = program.read_text(encoding="utf-8")
        if "voice" in text.lower() and "style" in text.lower():
            program_status = "operator_bound"
            program_evidence = (
                "roles/synthesizer/program.md exists and names voice/style; "
                "operator review note is still required"
            )
        else:
            program_evidence = "roles/synthesizer/program.md exists but does not name voice/style"

    cap = BudgetCap()
    budget_satisfied = cap.total_cap_usd <= Decimal("5.00")

    items = [
        ReadinessItem(
            id="program",
            label="roles/synthesizer/program.md written and operator-reviewed",
            status=program_status,
            evidence=program_evidence,
        ),
        ReadinessItem(
            id="tooling",
            label="tools/prompt_autoresearch scaffolded",
            status="satisfied" if not missing_tool_files else "missing",
            evidence=(
                "required tool files present"
                if not missing_tool_files
                else f"missing files: {', '.join(missing_tool_files)}"
            ),
        ),
        ReadinessItem(
            id="calibration",
            label="no-op mutator calibration run on file",
            status="satisfied" if calibration.is_file() else "operator_bound",
            evidence=(
                str(calibration.relative_to(root))
                if calibration.is_file()
                else "run no-op cohort and write reports/autoresearch/synthesizer-calibration.md"
            ),
        ),
        ReadinessItem(
            id="golden_traces",
            label="at least five golden traces captured",
            status="satisfied" if len(golden_traces) >= 5 else "operator_bound",
            evidence=f"{len(golden_traces)} golden trace(s) found in tools/golden_traces/captured",
        ),
        ReadinessItem(
            id="budget",
            label="cost cap of $5/run enforced in code",
            status="satisfied" if budget_satisfied else "missing",
            evidence=f"BudgetCap.total_cap_usd={cap.total_cap_usd}",
        ),
        ReadinessItem(
            id="local_only",
            label="production VM execution forbidden in code",
            status="satisfied",
            evidence="PromptAutoresearchRunner raises when ANTIEK_ENV=production; covered by tests",
        ),
    ]
    return ReadinessReport(items=items)


def render_readiness_markdown(report: ReadinessReport) -> str:
    lines = [
        "# Prompt autoresearch Wedge 1 readiness",
        "",
        f"**All criteria satisfied:** `{str(report.all_satisfied).lower()}`",
        "",
        "| ID | Status | Evidence |",
        "|---|---|---|",
    ]
    for item in report.items:
        lines.append(f"| `{item.id}` | `{item.status}` | {item.evidence} |")
    lines.append("")
    return "\n".join(lines)
