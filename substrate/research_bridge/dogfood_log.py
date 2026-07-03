"""Operator log scaffolding for Deep Research Bridge dogfood runs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

DOGFOOD_PROJECT_COUNT = 5

DOGFOOD_TEMPLATE = """# ADRB Dogfood Project Entry Template

Copy this template once per real dogfood project into `operator-log.md`.

## Project name

One line.

## Goal

One sentence.

## Session ID

Bridge session id used for this project.

## Provider mix

Which external LLMs or research providers did the operator use?

## Block count at start / end

- Start:
- End:

## Mode(s) used

A, B, or both.

## Draft produced

Link to exported `.md`, or write `none` and explain under What failed.

## Did mode A produce something I'd send / publish?

Yes, no, or with-edits. Add two sentences explaining why.

## Did mode B's prompts cause me to actually run prompts?

Yes or no. If yes, list which prompts.

## What failed?

Free text.

## What surprised me?

Free text.

## Would I open this again tomorrow?

Yes or no.
"""


OPERATOR_LOG_HEADER = """# Antiek Deep Research Bridge Operator Log

Operator-owned dogfood log. Engineering may create this scaffold before the
first project starts; during dogfood, the operator owns all project entries.

## Five projects chosen up front

1.
2.
3.
4.
5.

## Project entries

Duplicate `_template.md` below this heading for each real project.
"""


WAVE4_CANDIDATES_TEMPLATE = """# ADRB Wave 4 Candidates

Operator-owned parking lot for bugs, feature ideas, and product pain observed
during SPR-06 dogfood. Log the impulse here instead of fixing code mid-dogfood.

## Candidates

### Candidate title

- Observed during project:
- Mode: A | B | both | substrate
- Severity: paper-cut | blocker | existential
- Evidence from operator log:
- One-paragraph proposal:
- Kill criteria / what would prove this is not worth building:
"""


@dataclass(frozen=True)
class DogfoodScaffoldResult:
    root: Path
    template_path: Path
    operator_log_path: Path
    wave4_candidates_path: Path
    template_written: bool
    operator_log_written: bool
    wave4_candidates_written: bool


@dataclass(frozen=True)
class DogfoodProjectEntry:
    project_name: str
    session_id: str


@dataclass(frozen=True)
class DogfoodLogValidation:
    operator_log_path: Path
    planned_projects: tuple[str, ...]
    filled_project_entries: tuple[str, ...]
    complete_project_entries: tuple[str, ...]
    project_entries: tuple[DogfoodProjectEntry, ...]
    missing_requirements: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_requirements


@dataclass(frozen=True)
class Wave4Candidate:
    title: str
    mode: str
    severity: str
    observed_during_project: str
    evidence_from_operator_log: str
    proposal: str
    kill_criteria: str


@dataclass(frozen=True)
class Wave4CandidatesValidation:
    wave4_candidates_path: Path
    candidates: tuple[Wave4Candidate, ...]
    missing_requirements: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_requirements


def default_dogfood_dir() -> Path:
    return Path.home() / "Desktop" / "Antiek" / "runs" / "adrb"


def write_dogfood_scaffold(
    root: str | Path | None = None,
    *,
    overwrite_template: bool = False,
) -> DogfoodScaffoldResult:
    dogfood_root = Path(root).expanduser() if root is not None else default_dogfood_dir()
    dogfood_root.mkdir(parents=True, exist_ok=True)

    template_path = dogfood_root / "_template.md"
    operator_log_path = dogfood_root / "operator-log.md"
    wave4_candidates_path = dogfood_root / "wave4_candidates.md"

    template_written = False
    if overwrite_template or not template_path.exists():
        template_path.write_text(DOGFOOD_TEMPLATE, encoding="utf-8")
        template_written = True

    operator_log_written = False
    if not operator_log_path.exists():
        operator_log_path.write_text(OPERATOR_LOG_HEADER, encoding="utf-8")
        operator_log_written = True

    wave4_candidates_written = False
    if not wave4_candidates_path.exists():
        wave4_candidates_path.write_text(WAVE4_CANDIDATES_TEMPLATE, encoding="utf-8")
        wave4_candidates_written = True

    return DogfoodScaffoldResult(
        root=dogfood_root,
        template_path=template_path,
        operator_log_path=operator_log_path,
        wave4_candidates_path=wave4_candidates_path,
        template_written=template_written,
        operator_log_written=operator_log_written,
        wave4_candidates_written=wave4_candidates_written,
    )


def _section_after_heading(text: str, heading: str) -> str:
    needle = f"## {heading}"
    start = text.find(needle)
    if start < 0:
        return ""
    start += len(needle)
    next_heading = text.find("\n## ", start)
    if next_heading < 0:
        return text[start:]
    return text[start:next_heading]


def _project_section_after_heading(text: str, heading: str) -> str:
    needle = f"## {heading}"
    start = text.find(needle)
    if start < 0:
        return ""
    start += len(needle)
    next_heading = text.find("\n## ", start)
    if next_heading < 0:
        return text[start:]
    return text[start:next_heading]


def _planned_project_names(text: str) -> tuple[str, ...]:
    section = _section_after_heading(text, "Five projects chosen up front")
    names: list[str] = []
    for raw in section.splitlines():
        stripped = raw.strip()
        if not stripped or "." not in stripped:
            continue
        prefix, value = stripped.split(".", 1)
        if not prefix.isdigit():
            continue
        cleaned = value.strip()
        if cleaned:
            names.append(cleaned)
    return tuple(names)


def _filled_project_entries(text: str) -> tuple[str, ...]:
    entries: list[str] = []
    parts = text.split("\n## Project name")
    for part in parts[1:]:
        body = part.strip()
        if not body:
            continue
        first_lines = [line.strip() for line in body.splitlines() if line.strip()]
        if not first_lines:
            continue
        name = first_lines[0]
        if name.lower() in {"one line.", "one line"}:
            continue
        entries.append(name)
    return tuple(entries)


_REQUIRED_PROJECT_FIELDS = (
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
)


def _non_placeholder_section(section: str) -> bool:
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    if not lines:
        return False
    placeholders = {
        "one line.",
        "one sentence.",
        "free text.",
        "yes or no.",
        "a, b, or both.",
    }
    for line in lines:
        lowered = line.lower()
        if lowered in placeholders:
            continue
        if lowered.startswith("which external llms"):
            continue
        if lowered.startswith("link to exported"):
            continue
        if lowered.startswith("yes, no, or with-edits"):
            continue
        if lowered.startswith("- start:") or lowered.startswith("- end:"):
            value = line.split(":", 1)[1].strip() if ":" in line else ""
            if not value:
                continue
        return True
    return False


def _complete_project_entries(text: str) -> tuple[str, ...]:
    return tuple(entry.project_name for entry in _complete_project_entry_records(text))


def _complete_project_entry_records(text: str) -> tuple[DogfoodProjectEntry, ...]:
    complete: list[DogfoodProjectEntry] = []
    parts = text.split("\n## Project name")
    for part in parts[1:]:
        body = part.strip()
        if not body:
            continue
        first_lines = [line.strip() for line in body.splitlines() if line.strip()]
        if not first_lines:
            continue
        name = first_lines[0]
        if name.lower() in {"one line.", "one line"}:
            continue
        missing_field = False
        for field in _REQUIRED_PROJECT_FIELDS:
            field_section = _project_section_after_heading(body, field)
            if not _non_placeholder_section(field_section):
                missing_field = True
                break
        if not missing_field:
            session_id = _project_section_after_heading(body, "Session ID").strip()
            complete.append(
                DogfoodProjectEntry(project_name=name, session_id=session_id)
            )
    return tuple(complete)


def _candidate_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    for raw in text.splitlines():
        if raw.startswith("### "):
            if current_title is not None:
                sections.append((current_title, "\n".join(current_lines)))
            current_title = raw.removeprefix("### ").strip()
            current_lines = []
            continue
        if current_title is not None:
            current_lines.append(raw)
    if current_title is not None:
        sections.append((current_title, "\n".join(current_lines)))
    return sections


def _candidate_field(body: str, label: str) -> str:
    prefix = f"- {label}:"
    for raw in body.splitlines():
        stripped = raw.strip()
        if stripped.startswith(prefix):
            return stripped.removeprefix(prefix).strip()
    return ""


def _is_placeholder(value: str) -> bool:
    return not value or value.lower() in {"candidate title", "todo"}


def validate_wave4_candidates(root: str | Path | None = None) -> Wave4CandidatesValidation:
    dogfood_root = Path(root).expanduser() if root is not None else default_dogfood_dir()
    wave4_path = dogfood_root / "wave4_candidates.md"
    if not wave4_path.exists():
        return Wave4CandidatesValidation(
            wave4_candidates_path=wave4_path,
            candidates=(),
            missing_requirements=("wave4_candidates.md is missing",),
        )

    text = wave4_path.read_text(encoding="utf-8")
    candidates: list[Wave4Candidate] = []
    missing: list[str] = []
    for title, body in _candidate_sections(text):
        if _is_placeholder(title):
            continue
        mode = _candidate_field(body, "Mode")
        severity = _candidate_field(body, "Severity")
        observed = _candidate_field(body, "Observed during project")
        evidence = _candidate_field(body, "Evidence from operator log")
        proposal = _candidate_field(body, "One-paragraph proposal")
        kill_criteria = _candidate_field(
            body,
            "Kill criteria / what would prove this is not worth building",
        )
        candidate_missing: list[str] = []
        if _is_placeholder(observed):
            candidate_missing.append("Observed during project")
        if mode not in {"A", "B", "both", "substrate"}:
            candidate_missing.append("Mode must be A, B, both, or substrate")
        if severity not in {"paper-cut", "blocker", "existential"}:
            candidate_missing.append(
                "Severity must be paper-cut, blocker, or existential"
            )
        if _is_placeholder(evidence):
            candidate_missing.append("Evidence from operator log")
        if _is_placeholder(proposal):
            candidate_missing.append("One-paragraph proposal")
        if _is_placeholder(kill_criteria):
            candidate_missing.append("Kill criteria")
        if candidate_missing:
            missing.append(f"{title}: missing {', '.join(candidate_missing)}")
            continue
        candidates.append(
            Wave4Candidate(
                title=title,
                mode=mode,
                severity=severity,
                observed_during_project=observed,
                evidence_from_operator_log=evidence,
                proposal=proposal,
                kill_criteria=kill_criteria,
            )
        )
    return Wave4CandidatesValidation(
        wave4_candidates_path=wave4_path,
        candidates=tuple(candidates),
        missing_requirements=tuple(missing),
    )


def validate_dogfood_log(root: str | Path | None = None) -> DogfoodLogValidation:
    dogfood_root = Path(root).expanduser() if root is not None else default_dogfood_dir()
    operator_log_path = dogfood_root / "operator-log.md"
    if not operator_log_path.exists():
        return DogfoodLogValidation(
            operator_log_path=operator_log_path,
            planned_projects=(),
            filled_project_entries=(),
            complete_project_entries=(),
            project_entries=(),
            missing_requirements=("operator-log.md is missing",),
        )

    text = operator_log_path.read_text(encoding="utf-8")
    planned = _planned_project_names(text)
    entries = _filled_project_entries(text)
    project_entries = _complete_project_entry_records(text)
    complete_entries = tuple(entry.project_name for entry in project_entries)
    missing: list[str] = []
    if len(planned) < DOGFOOD_PROJECT_COUNT:
        missing.append(
            f"expected {DOGFOOD_PROJECT_COUNT} planned projects, found {len(planned)}"
        )
    if len(entries) < DOGFOOD_PROJECT_COUNT:
        missing.append(
            f"expected {DOGFOOD_PROJECT_COUNT} filled project entries, found {len(entries)}"
        )
    if len(complete_entries) < DOGFOOD_PROJECT_COUNT:
        missing.append(
            "expected "
            f"{DOGFOOD_PROJECT_COUNT} complete project entries, "
            f"found {len(complete_entries)}"
        )
    if (
        len(planned) >= DOGFOOD_PROJECT_COUNT
        and len(complete_entries) >= DOGFOOD_PROJECT_COUNT
    ):
        planned_set = set(planned)
        complete_set = set(complete_entries)
        missing_projects = tuple(sorted(planned_set.difference(complete_set)))
        extra_projects = tuple(sorted(complete_set.difference(planned_set)))
        if missing_projects:
            missing.append(
                "complete entries missing planned projects: "
                + ", ".join(missing_projects)
            )
        if extra_projects:
            missing.append(
                "complete entries include unplanned projects: "
                + ", ".join(extra_projects)
            )
    session_ids = [entry.session_id for entry in project_entries]
    duplicate_session_ids = tuple(
        sorted({session_id for session_id in session_ids if session_ids.count(session_id) > 1})
    )
    if duplicate_session_ids:
        missing.append(
            "project session ids must be unique; duplicates: "
            + ", ".join(duplicate_session_ids)
        )
    return DogfoodLogValidation(
        operator_log_path=operator_log_path,
        planned_projects=planned,
        filled_project_entries=entries,
        complete_project_entries=complete_entries,
        project_entries=project_entries,
        missing_requirements=tuple(missing),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create Deep Research Bridge dogfood operator-log scaffolding.",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Create dogfood log files.")
    init_parser.add_argument(
        "--root",
        default=None,
        help="Dogfood directory. Defaults to ~/Desktop/Antiek/runs/adrb.",
    )
    init_parser.add_argument(
        "--overwrite-template",
        action="store_true",
        help="Rewrite _template.md. operator-log.md is never overwritten.",
    )
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate operator-owned dogfood log readiness.",
    )
    validate_parser.add_argument(
        "--root",
        default=None,
        help="Dogfood directory. Defaults to ~/Desktop/Antiek/runs/adrb.",
    )
    wave4_validate_parser = subparsers.add_parser(
        "wave4-validate",
        help="Validate operator-owned Wave 4 candidate notes.",
    )
    wave4_validate_parser.add_argument(
        "--root",
        default=None,
        help="Dogfood directory. Defaults to ~/Desktop/Antiek/runs/adrb.",
    )

    args = parser.parse_args(argv)
    if args.command == "wave4-validate":
        result = validate_wave4_candidates(args.root)
        print(f"wave4-candidates: {result.wave4_candidates_path}")
        print(f"valid candidates: {len(result.candidates)}")
        if result.ok:
            print("WAVE4_CANDIDATES_OK")
            return 0
        for missing in result.missing_requirements:
            print(f"missing: {missing}")
        return 1

    if args.command == "validate":
        result = validate_dogfood_log(args.root)
        print(f"operator-log: {result.operator_log_path}")
        print(
            f"planned projects: {len(result.planned_projects)}/{DOGFOOD_PROJECT_COUNT}"
        )
        print(
            "filled project entries: "
            f"{len(result.filled_project_entries)}/{DOGFOOD_PROJECT_COUNT}"
        )
        print(
            "complete project entries: "
            f"{len(result.complete_project_entries)}/{DOGFOOD_PROJECT_COUNT}"
        )
        print(
            f"project session ids: {len(result.project_entries)}/{DOGFOOD_PROJECT_COUNT}"
        )
        if result.ok:
            print("DOGFOOD_LOG_OK")
            return 0
        for missing in result.missing_requirements:
            print(f"missing: {missing}")
        return 1

    if args.command != "init":
        parser.print_help()
        return 2

    result = write_dogfood_scaffold(
        args.root,
        overwrite_template=args.overwrite_template,
    )
    print(f"root: {result.root}")
    print(
        "template: "
        f"{result.template_path} "
        f"({'written' if result.template_written else 'kept'})"
    )
    print(
        "operator-log: "
        f"{result.operator_log_path} "
        f"({'written' if result.operator_log_written else 'kept'})"
    )
    print(
        "wave4-candidates: "
        f"{result.wave4_candidates_path} "
        f"({'written' if result.wave4_candidates_written else 'kept'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
