"""Operator log scaffolding for Deep Research Bridge dogfood runs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

DOGFOOD_TEMPLATE = """# ADRB Dogfood Project Entry Template

Copy this template once per real dogfood project into `operator-log.md`.

## Project name

One line.

## Goal

One sentence.

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
class DogfoodLogValidation:
    operator_log_path: Path
    planned_projects: tuple[str, ...]
    filled_project_entries: tuple[str, ...]
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


def validate_dogfood_log(root: str | Path | None = None) -> DogfoodLogValidation:
    dogfood_root = Path(root).expanduser() if root is not None else default_dogfood_dir()
    operator_log_path = dogfood_root / "operator-log.md"
    if not operator_log_path.exists():
        return DogfoodLogValidation(
            operator_log_path=operator_log_path,
            planned_projects=(),
            filled_project_entries=(),
            missing_requirements=("operator-log.md is missing",),
        )

    text = operator_log_path.read_text(encoding="utf-8")
    planned = _planned_project_names(text)
    entries = _filled_project_entries(text)
    missing: list[str] = []
    if len(planned) < 5:
        missing.append(f"expected 5 planned projects, found {len(planned)}")
    if len(entries) < 5:
        missing.append(f"expected 5 filled project entries, found {len(entries)}")
    return DogfoodLogValidation(
        operator_log_path=operator_log_path,
        planned_projects=planned,
        filled_project_entries=entries,
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

    args = parser.parse_args(argv)
    if args.command == "validate":
        result = validate_dogfood_log(args.root)
        print(f"operator-log: {result.operator_log_path}")
        print(f"planned projects: {len(result.planned_projects)}/5")
        print(f"filled project entries: {len(result.filled_project_entries)}/5")
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
