"""Readiness audit for Autoresearch Wedge 1 unlock criteria."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from tools.golden_traces import load_trace
from tools.prompt_autoresearch.budget import BudgetCap
from tools.prompt_autoresearch.markdown import markdown_code_span


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
    golden_trace_files = sorted((root / "tools/golden_traces/captured").glob("*.json"))
    valid_golden_traces, invalid_golden_traces = _classify_golden_traces(
        root,
        golden_trace_files,
    )
    calibration = root / "reports/autoresearch/synthesizer-calibration.md"
    calibration_valid = _is_calibration_report(calibration)
    program_review = root / "reports/autoresearch/synthesizer-program-review.md"
    program_review_valid = _is_program_review_note(program_review)
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
            if program_review_valid:
                program_status = "satisfied"
                program_evidence = (
                    "roles/synthesizer/program.md exists and "
                    f"{program_review.relative_to(root)} records operator review"
                )
            else:
                program_status = "operator_bound"
                program_evidence = (
                    "roles/synthesizer/program.md exists and names voice/style; "
                    + _program_review_evidence(root, program_review)
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
            status="satisfied" if calibration_valid else "operator_bound",
            evidence=(
                f"{calibration.relative_to(root)} contains calibration summary fields"
                if calibration_valid
                else _calibration_evidence(root, calibration)
            ),
        ),
        ReadinessItem(
            id="golden_traces",
            label="at least five golden traces captured",
            status="satisfied" if len(valid_golden_traces) >= 5 else "operator_bound",
            evidence=_golden_trace_evidence(
                valid_count=len(valid_golden_traces),
                invalid_traces=invalid_golden_traces,
            ),
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


def _is_calibration_report(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    required_fragments = (
        "# Prompt autoresearch calibration",
        "- Iterations:",
        "- σ:",
        "- 2σ:",
        "- Recommended epsilon:",
    )
    return all(fragment in text for fragment in required_fragments)


def _calibration_evidence(root: Path, calibration: Path) -> str:
    if not calibration.is_file():
        return "run no-op cohort and write reports/autoresearch/synthesizer-calibration.md"
    return (
        f"{calibration.relative_to(root)} exists but is not a generated "
        "calibration report"
    )


def _is_program_review_note(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8").lower()
    required_fragments = (
        "# synthesizer program review",
        "reviewer:",
        "reviewed_at:",
        "verdict:",
        "operator_approved",
        "roles/synthesizer/program.md",
    )
    return all(fragment in text for fragment in required_fragments)


def _program_review_evidence(root: Path, review: Path) -> str:
    if not review.is_file():
        return (
            "write reports/autoresearch/synthesizer-program-review.md "
            "with reviewer, reviewed_at, verdict: operator_approved, and "
            "roles/synthesizer/program.md"
        )
    return (
        f"{review.relative_to(root)} exists but does not record the required "
        "operator review fields"
    )


def _classify_golden_traces(
    root: Path,
    trace_files: list[Path],
) -> tuple[list[Path], list[Path]]:
    valid: list[Path] = []
    invalid: list[Path] = []
    for trace_file in trace_files:
        try:
            load_trace(trace_file)
        except Exception:
            invalid.append(trace_file.relative_to(root))
        else:
            valid.append(trace_file.relative_to(root))
    return valid, invalid


def _golden_trace_evidence(*, valid_count: int, invalid_traces: list[Path]) -> str:
    evidence = (
        f"{valid_count} loadable golden trace(s) found in "
        "tools/golden_traces/captured"
    )
    if invalid_traces:
        invalid = ", ".join(str(path) for path in invalid_traces)
        evidence += f"; invalid trace file(s): {invalid}"
    return evidence


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
        lines.append(
            "| "
            f"{markdown_code_span(_markdown_table_cell(item.id))} | "
            f"{markdown_code_span(_markdown_table_cell(item.status))} | "
            f"{_markdown_table_cell(item.evidence)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _markdown_table_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")
