"""Operator log scaffold tests for the Deep Research Bridge."""

from __future__ import annotations

from pathlib import Path

from substrate.research_bridge.dogfood_log import (
    DOGFOOD_TEMPLATE,
    WAVE4_CANDIDATES_TEMPLATE,
    main,
    validate_dogfood_log,
    validate_wave4_candidates,
    write_dogfood_scaffold,
)

PROJECT_NAMES = (
    "Sell-side AI infra memo",
    "Anthropic market scan",
    "AlphaSense earnings read",
    "Mixed-provider author brief",
    "Operator status-quo replacement",
)


def _complete_project_entry(name: str, idx: int, session_id: str | None = None) -> str:
    session = session_id if session_id is not None else f"sess-{idx}"
    return f"""## Project name

{name}

## Goal

Produce dogfood project {idx}.

## Session ID

{session}

## Provider mix

Grok and Claude.

## Block count at start / end

- Start: {idx}
- End: {idx + 2}

## Mode(s) used

A and B.

## Draft produced

runs/adrb/drafts/project-{idx}.md

## Did mode A produce something I'd send / publish?

with-edits. It needed a pass but preserved the outline.

## Did mode B's prompts cause me to actually run prompts?

Yes. Prompt {idx} was run manually.

## What failed?

The first outline was too broad.

## What surprised me?

The gap prompts found a missing comparison.

## Would I open this again tomorrow?

Yes.
"""


def _write_operator_log(
    root: Path,
    *,
    planned: tuple[str, ...] = PROJECT_NAMES,
    entries: tuple[str, ...],
) -> None:
    planned_lines = "\n".join(
        f"{idx}. {name}" for idx, name in enumerate(planned, start=1)
    )
    (root / "operator-log.md").write_text(
        f"""# Antiek Deep Research Bridge Operator Log

## Five projects chosen up front

{planned_lines}

## Project entries

"""
        + "\n".join(entries),
        encoding="utf-8",
    )


def test_dogfood_scaffold_creates_template_and_operator_log(tmp_path: Path) -> None:
    result = write_dogfood_scaffold(tmp_path)

    assert result.root == tmp_path
    assert result.template_path == tmp_path / "_template.md"
    assert result.operator_log_path == tmp_path / "operator-log.md"
    assert result.wave4_candidates_path == tmp_path / "wave4_candidates.md"
    assert result.template_written is True
    assert result.operator_log_written is True
    assert result.wave4_candidates_written is True

    template = result.template_path.read_text(encoding="utf-8")
    for label in (
        "Project name",
        "Goal",
        "Session ID",
        "Provider mix",
        "Block count at start / end",
        "Mode(s) used",
        "Draft produced",
        "Did mode A produce something I'd send / publish?",
        "Did mode B's prompts cause me to actually run prompts?",
        "What failed?",
        "What surprised me?",
        "Would I open this again tomorrow?",
    ):
        assert f"## {label}" in template

    log = result.operator_log_path.read_text(encoding="utf-8")
    assert "# Antiek Deep Research Bridge Operator Log" in log
    assert "## Five projects chosen up front" in log
    assert "## Project entries" in log

    wave4 = result.wave4_candidates_path.read_text(encoding="utf-8")
    assert "# ADRB Wave 4 Candidates" in wave4
    assert "Log the impulse here instead of fixing code mid-dogfood." in wave4


def test_dogfood_scaffold_preserves_operator_owned_log(tmp_path: Path) -> None:
    first = write_dogfood_scaffold(tmp_path)
    first.operator_log_path.write_text("operator-owned content\n", encoding="utf-8")
    first.template_path.write_text("local template edits\n", encoding="utf-8")
    first.wave4_candidates_path.write_text("wave 4 notes\n", encoding="utf-8")

    second = write_dogfood_scaffold(tmp_path)

    assert second.operator_log_written is False
    assert second.template_written is False
    assert second.wave4_candidates_written is False
    assert second.operator_log_path.read_text(encoding="utf-8") == (
        "operator-owned content\n"
    )
    assert second.template_path.read_text(encoding="utf-8") == "local template edits\n"
    assert second.wave4_candidates_path.read_text(encoding="utf-8") == "wave 4 notes\n"


def test_dogfood_scaffold_can_refresh_template_only(tmp_path: Path) -> None:
    result = write_dogfood_scaffold(tmp_path)
    result.operator_log_path.write_text("operator-owned content\n", encoding="utf-8")
    result.template_path.write_text("stale template\n", encoding="utf-8")
    result.wave4_candidates_path.write_text("wave 4 notes\n", encoding="utf-8")

    refreshed = write_dogfood_scaffold(tmp_path, overwrite_template=True)

    assert refreshed.template_written is True
    assert refreshed.operator_log_written is False
    assert refreshed.wave4_candidates_written is False
    assert refreshed.template_path.read_text(encoding="utf-8") == DOGFOOD_TEMPLATE
    assert refreshed.operator_log_path.read_text(encoding="utf-8") == (
        "operator-owned content\n"
    )
    assert refreshed.wave4_candidates_path.read_text(encoding="utf-8") == (
        "wave 4 notes\n"
    )


def test_dogfood_scaffold_wave4_template_matches_spec_parking_lot(
    tmp_path: Path,
) -> None:
    result = write_dogfood_scaffold(tmp_path)

    assert result.wave4_candidates_path.read_text(encoding="utf-8") == (
        WAVE4_CANDIDATES_TEMPLATE
    )


def test_dogfood_scaffold_cli_init(tmp_path: Path) -> None:
    rc = main(["init", "--root", str(tmp_path)])

    assert rc == 0
    assert (tmp_path / "_template.md").exists()
    assert (tmp_path / "operator-log.md").exists()
    assert (tmp_path / "wave4_candidates.md").exists()


def test_dogfood_log_validate_reports_missing_log(tmp_path: Path) -> None:
    result = validate_dogfood_log(tmp_path)

    assert result.ok is False
    assert result.operator_log_path == tmp_path / "operator-log.md"
    assert result.missing_requirements == ("operator-log.md is missing",)
    assert result.complete_project_entries == ()
    assert result.project_entries == ()


def test_dogfood_log_validate_rejects_unfilled_scaffold(tmp_path: Path) -> None:
    write_dogfood_scaffold(tmp_path)

    result = validate_dogfood_log(tmp_path)

    assert result.ok is False
    assert result.planned_projects == ()
    assert result.filled_project_entries == ()
    assert result.missing_requirements == (
        "expected 5 planned projects, found 0",
        "expected 5 filled project entries, found 0",
        "expected 5 complete project entries, found 0",
    )


def test_dogfood_log_validate_rejects_entries_without_required_fields(
    tmp_path: Path,
) -> None:
    write_dogfood_scaffold(tmp_path)
    (tmp_path / "operator-log.md").write_text(
        """# Antiek Deep Research Bridge Operator Log

## Five projects chosen up front

1. Sell-side AI infra memo
2. Anthropic market scan
3. AlphaSense earnings read
4. Mixed-provider author brief
5. Operator status-quo replacement

## Project entries

## Project name

Sell-side AI infra memo

## Goal

Write a memo.

## Project name

Anthropic market scan

## Goal

Compare vendors.

## Project name

AlphaSense earnings read

## Goal

Extract risks.

## Project name

Mixed-provider author brief

## Goal

Combine sources.

## Project name

Operator status-quo replacement

## Goal

Replace the old workflow.
""",
        encoding="utf-8",
    )

    result = validate_dogfood_log(tmp_path)

    assert result.ok is False
    assert result.planned_projects == (
        "Sell-side AI infra memo",
        "Anthropic market scan",
        "AlphaSense earnings read",
        "Mixed-provider author brief",
        "Operator status-quo replacement",
    )
    assert result.filled_project_entries == result.planned_projects
    assert result.complete_project_entries == ()
    assert result.project_entries == ()
    assert result.missing_requirements == ("expected 5 complete project entries, found 0",)


def test_dogfood_log_validate_accepts_five_complete_project_entries(
    tmp_path: Path,
) -> None:
    write_dogfood_scaffold(tmp_path)
    _write_operator_log(
        tmp_path,
        entries=tuple(
            _complete_project_entry(name, idx)
            for idx, name in enumerate(PROJECT_NAMES, start=1)
        ),
    )

    result = validate_dogfood_log(tmp_path)

    assert result.ok is True
    assert result.complete_project_entries == result.planned_projects
    assert tuple(entry.session_id for entry in result.project_entries) == (
        "sess-1",
        "sess-2",
        "sess-3",
        "sess-4",
        "sess-5",
    )


def test_dogfood_log_validate_rejects_entries_for_unplanned_projects(
    tmp_path: Path,
) -> None:
    write_dogfood_scaffold(tmp_path)
    entries = tuple(
        _complete_project_entry(name, idx)
        for idx, name in enumerate(PROJECT_NAMES[:-1] + ("Unplanned project",), start=1)
    )
    _write_operator_log(tmp_path, entries=entries)

    result = validate_dogfood_log(tmp_path)

    assert result.ok is False
    assert result.complete_project_entries[-1] == "Unplanned project"
    assert (
        "complete entries missing planned projects: Operator status-quo replacement"
        in result.missing_requirements
    )
    assert (
        "complete entries include unplanned projects: Unplanned project"
        in result.missing_requirements
    )


def test_dogfood_log_validate_rejects_duplicate_session_ids(tmp_path: Path) -> None:
    write_dogfood_scaffold(tmp_path)
    entries = tuple(
        _complete_project_entry(name, idx, session_id="sess-dup" if idx <= 2 else None)
        for idx, name in enumerate(PROJECT_NAMES, start=1)
    )
    _write_operator_log(tmp_path, entries=entries)

    result = validate_dogfood_log(tmp_path)

    assert result.ok is False
    assert "project session ids must be unique; duplicates: sess-dup" in (
        result.missing_requirements
    )


def test_dogfood_log_cli_validate(tmp_path: Path, capsys) -> None:
    write_dogfood_scaffold(tmp_path)

    rc = main(["validate", "--root", str(tmp_path)])

    assert rc == 1
    out = capsys.readouterr().out
    assert "planned projects: 0/5" in out
    assert "filled project entries: 0/5" in out
    assert "complete project entries: 0/5" in out
    assert "project session ids: 0/5" in out


def test_wave4_candidates_validate_allows_empty_scaffold(tmp_path: Path) -> None:
    write_dogfood_scaffold(tmp_path)

    result = validate_wave4_candidates(tmp_path)

    assert result.ok is True
    assert result.candidates == ()


def test_wave4_candidates_validate_rejects_partial_candidate(tmp_path: Path) -> None:
    write_dogfood_scaffold(tmp_path)
    (tmp_path / "wave4_candidates.md").write_text(
        """# ADRB Wave 4 Candidates

## Candidates

### Prompt provenance view

- Observed during project: Sell-side AI infra memo
- Mode: B
- Severity: paper-cut
- Evidence from operator log:
- One-paragraph proposal: Show which dogfood prompt came from which gap.
- Kill criteria / what would prove this is not worth building:
""",
        encoding="utf-8",
    )

    result = validate_wave4_candidates(tmp_path)

    assert result.ok is False
    assert result.candidates == ()
    assert result.missing_requirements == (
        "Prompt provenance view: missing Evidence from operator log, Kill criteria",
    )


def test_wave4_candidates_validate_accepts_complete_candidate(tmp_path: Path) -> None:
    write_dogfood_scaffold(tmp_path)
    (tmp_path / "wave4_candidates.md").write_text(
        """# ADRB Wave 4 Candidates

## Candidates

### Prompt provenance view

- Observed during project: Sell-side AI infra memo
- Mode: B
- Severity: paper-cut
- Evidence from operator log: Project 1 prompt A was rerun manually.
- One-paragraph proposal: Show which dogfood prompt came from which gap.
- Kill criteria / what would prove this is not worth building: Operator never opens it.
""",
        encoding="utf-8",
    )

    result = validate_wave4_candidates(tmp_path)

    assert result.ok is True
    assert len(result.candidates) == 1
    assert result.candidates[0].title == "Prompt provenance view"
    assert result.candidates[0].mode == "B"


def test_wave4_candidates_cli_validate(tmp_path: Path, capsys) -> None:
    write_dogfood_scaffold(tmp_path)

    rc = main(["wave4-validate", "--root", str(tmp_path)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "valid candidates: 0" in out
    assert "WAVE4_CANDIDATES_OK" in out
