"""Phase 2 execution audit — read-only VIEW over the audit markdown.

The Phase 2 audit documents answer a different question from the roadmap:
not "which sprint nodes are dependency-ready?" but "what did the execution
audit classify as met, partial, unmet, and still blocked by non-engineering
conditions?"

This module reads the current v5 addendum plus the v4 sprint scorecard. It is
status-only: the markdown remains the source, and this package has no write path
back to the audit files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def canonical_phase2_audit_path() -> Path:
    return _repo_root() / "docs" / "phase2_execution_audit_v5_2026_07_01.md"


def canonical_phase2_scorecard_path() -> Path:
    return _repo_root() / "docs" / "phase2_execution_audit_v4_2026_05_23.md"


@dataclass(frozen=True)
class Phase2SprintScore:
    sprint: str
    phases: int
    met: int
    partial: int
    unmet: int
    delta_vs_v3: str


@dataclass(frozen=True)
class Phase2ExitCriteria:
    total: int
    met: int
    partial: int
    unmet: int
    note: str


@dataclass(frozen=True)
class Phase2AuditView:
    source_path: str
    scorecard_source_path: str
    current_commit_evidence: str | None
    engineering_blocked_count: int | None
    status_summary: str | None
    next_action_ordering: tuple[str, ...]
    sprint_scorecard: tuple[Phase2SprintScore, ...]
    total_score: Phase2SprintScore | None
    exit_criteria: Phase2ExitCriteria | None


def _repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(_repo_root()))
    except ValueError:
        return str(path)


def _strip_markdown(text: str) -> str:
    text = text.replace("**", "").replace("`", "")
    return " ".join(text.split())


def _first_match(pattern: str, md: str) -> str | None:
    m = re.search(pattern, md, flags=re.MULTILINE | re.DOTALL)
    return _strip_markdown(m.group(1)) if m else None


def _first_int_match(pattern: str, md: str) -> int | None:
    m = re.search(pattern, md, flags=re.MULTILINE | re.DOTALL)
    return int(m.group(1)) if m else None


def _parse_int_cell(cell: str) -> int:
    m = re.search(r"\d+", cell)
    if not m:
        raise ValueError(f"scorecard cell has no integer: {cell!r}")
    return int(m.group(0))


def parse_phase2_scorecard(
    md: str,
    *,
    source_path: str,
) -> tuple[tuple[Phase2SprintScore, ...], Phase2SprintScore | None, Phase2ExitCriteria | None]:
    rows: list[Phase2SprintScore] = []
    total: Phase2SprintScore | None = None
    in_table = False
    for line in md.splitlines():
        if line.strip() == "| Sprint | Phases | Met | Partial | Unmet | Δ vs v3 |":
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("|---"):
            continue
        if not line.startswith("|"):
            if rows or total:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            continue
        row = Phase2SprintScore(
            sprint=_strip_markdown(cells[0]),
            phases=_parse_int_cell(cells[1]),
            met=_parse_int_cell(cells[2]),
            partial=_parse_int_cell(cells[3]),
            unmet=_parse_int_cell(cells[4]),
            delta_vs_v3=_strip_markdown(cells[5]),
        )
        if row.sprint == "TOTAL":
            total = row
        else:
            rows.append(row)

    exit_criteria = None
    m = re.search(
        r"Sprint-level exit criteria \((\d+) total\): unchanged at (\d+) met / (\d+)\s+partial / (\d+) unmet, because ([^.]+\.)",
        md,
        flags=re.MULTILINE,
    )
    if m:
        exit_criteria = Phase2ExitCriteria(
            total=int(m.group(1)),
            met=int(m.group(2)),
            partial=int(m.group(3)),
            unmet=int(m.group(4)),
            note=_strip_markdown(m.group(5)),
        )
    if not rows:
        raise ValueError(f"no sprint scorecard rows found in {source_path}")
    return tuple(rows), total, exit_criteria


def parse_phase2_audit(
    md: str,
    scorecard_md: str,
    *,
    source_path: str,
    scorecard_source_path: str,
) -> Phase2AuditView:
    scorecard, total, exit_criteria = parse_phase2_scorecard(
        scorecard_md,
        source_path=scorecard_source_path,
    )
    ordering: list[str] = []
    ordering_section = re.search(
        r"## 4\. Recommended next action ordering\n\n(?P<body>.*?)(?:\n---|\n## 5\.)",
        md,
        flags=re.DOTALL,
    )
    if ordering_section:
        for line in ordering_section.group("body").splitlines():
            m = re.match(r"\s*\d+\.\s+(.*)", line)
            if m:
                ordering.append(_strip_markdown(m.group(1)))
    return Phase2AuditView(
        source_path=source_path,
        scorecard_source_path=scorecard_source_path,
        current_commit_evidence=_first_match(r"\*\*Current commit evidence:\*\*\s*`([^`]+)`", md),
        engineering_blocked_count=_first_int_match(
            r"Current reconciled state:\*\*\s*net engineering-side-blocked items known from\s+v4:\s*\*\*(\d+)\*\*",
            md,
        ),
        status_summary=_first_match(r"\*\*Current reconciled state:\*\*\s*(.*?)\n\n", md),
        next_action_ordering=tuple(ordering),
        sprint_scorecard=scorecard,
        total_score=total,
        exit_criteria=exit_criteria,
    )


def load_phase2_audit(
    path: Path | None = None,
    scorecard_path: Path | None = None,
) -> Phase2AuditView:
    audit_source = path or canonical_phase2_audit_path()
    scorecard_source = scorecard_path or canonical_phase2_scorecard_path()
    return parse_phase2_audit(
        audit_source.read_text(encoding="utf-8"),
        scorecard_source.read_text(encoding="utf-8"),
        source_path=_repo_relative(audit_source),
        scorecard_source_path=_repo_relative(scorecard_source),
    )
