"""Verdict document scaffolding for Deep Research Bridge dogfood."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

VERDICT_TEMPLATE = """# Antiek Deep Research Bridge Post-Dogfood Verdict

This document is not complete until `antiek research bridge verdict validate`
passes. Replace every TODO before committing the final verdict.

## Evidence Sources

- Operator log: TODO cite `runs/adrb/operator-log.md`
- Metrics report: TODO cite `runs/adrb/dogfood_metrics.md`

## Mode A Verdict

Verdict: TODO choose SHIP, KILL, or ITERATE.

Evidence:
- TODO cite operator-log.md project evidence.
- TODO cite dogfood_metrics.md Mode A draft-export count.

Salvage if killed or iterated:
- TODO name salvageable parts, or write none with reason.

## Mode B Verdict

Verdict: TODO choose SHIP, KILL, or ITERATE.

Evidence:
- TODO cite operator-log.md project evidence.
- TODO cite dogfood_metrics.md would-run evidence.

Salvage if killed or iterated:
- TODO name salvageable parts, or write none with reason.

## Next 3 Sharp Questions

1. TODO
2. TODO
3. TODO

## Wave 4

Decision: TODO propose Wave 4, decline Wave 4, or list conditional Wave 4.

Candidates:
1. TODO
2. TODO
3. TODO
"""

_VERDICT_RE = re.compile(r"^Verdict:\s*(SHIP|KILL|ITERATE)\b", re.MULTILINE)
_TODO_RE = re.compile(r"\bTODO\b", re.IGNORECASE)


@dataclass(frozen=True)
class DogfoodVerdictScaffoldResult:
    path: Path
    written: bool


@dataclass(frozen=True)
class DogfoodVerdictValidation:
    path: Path
    mode_a_verdict: str | None
    mode_b_verdict: str | None
    next_questions: tuple[str, ...]
    missing_requirements: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_requirements


def default_verdict_path() -> Path:
    return Path.home() / "Desktop" / "Antiek" / "docs" / "adrb_post_dogfood_verdict.md"


def write_verdict_scaffold(
    path: str | Path | None = None,
    *,
    overwrite: bool = False,
) -> DogfoodVerdictScaffoldResult:
    verdict_path = Path(path).expanduser() if path is not None else default_verdict_path()
    verdict_path.parent.mkdir(parents=True, exist_ok=True)

    written = False
    if overwrite or not verdict_path.exists():
        verdict_path.write_text(VERDICT_TEMPLATE, encoding="utf-8")
        written = True

    return DogfoodVerdictScaffoldResult(path=verdict_path, written=written)


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


def _section_verdict(text: str, heading: str) -> str | None:
    match = _VERDICT_RE.search(_section_after_heading(text, heading))
    if match is None:
        return None
    return match.group(1)


def _next_questions(text: str) -> tuple[str, ...]:
    section = _section_after_heading(text, "Next 3 Sharp Questions")
    questions: list[str] = []
    for raw in section.splitlines():
        stripped = raw.strip()
        if "." not in stripped:
            continue
        prefix, value = stripped.split(".", 1)
        if not prefix.isdigit():
            continue
        question = value.strip()
        if question and not _TODO_RE.search(question):
            questions.append(question)
    return tuple(questions)


def validate_verdict_doc(path: str | Path | None = None) -> DogfoodVerdictValidation:
    verdict_path = Path(path).expanduser() if path is not None else default_verdict_path()
    if not verdict_path.exists():
        return DogfoodVerdictValidation(
            path=verdict_path,
            mode_a_verdict=None,
            mode_b_verdict=None,
            next_questions=(),
            missing_requirements=("verdict document is missing",),
        )

    text = verdict_path.read_text(encoding="utf-8")
    mode_a = _section_verdict(text, "Mode A Verdict")
    mode_b = _section_verdict(text, "Mode B Verdict")
    questions = _next_questions(text)
    wave4 = _section_after_heading(text, "Wave 4")

    missing: list[str] = []
    if _TODO_RE.search(text):
        missing.append("replace all TODO placeholders")
    if mode_a is None:
        missing.append("Mode A Verdict must declare SHIP, KILL, or ITERATE")
    if mode_b is None:
        missing.append("Mode B Verdict must declare SHIP, KILL, or ITERATE")
    if "operator-log.md" not in text:
        missing.append("cite operator-log.md evidence")
    if "dogfood_metrics.md" not in text:
        missing.append("cite dogfood_metrics.md evidence")
    if len(questions) < 3:
        missing.append(f"expected 3 next sharp questions, found {len(questions)}")
    if not wave4.strip():
        missing.append("Wave 4 section is missing")
    elif not re.search(r"\b(propose|decline|conditional|candidate|no wave 4)\b", wave4, re.I):
        missing.append("Wave 4 section must propose, decline, or make candidates conditional")

    return DogfoodVerdictValidation(
        path=verdict_path,
        mode_a_verdict=mode_a,
        mode_b_verdict=mode_b,
        next_questions=questions,
        missing_requirements=tuple(missing),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold or validate the Deep Research Bridge dogfood verdict.",
    )
    subparsers = parser.add_subparsers(dest="command")

    scaffold = subparsers.add_parser("scaffold", help="Create a verdict scaffold.")
    scaffold.add_argument(
        "--path",
        default=None,
        help="Verdict path. Defaults to ~/Desktop/Antiek/docs/adrb_post_dogfood_verdict.md.",
    )
    scaffold.add_argument(
        "--overwrite",
        action="store_true",
        help="Rewrite the verdict scaffold if it already exists.",
    )

    validate = subparsers.add_parser("validate", help="Validate the verdict document.")
    validate.add_argument(
        "--path",
        default=None,
        help="Verdict path. Defaults to ~/Desktop/Antiek/docs/adrb_post_dogfood_verdict.md.",
    )

    args = parser.parse_args(argv)
    if args.command == "scaffold":
        result = write_verdict_scaffold(args.path, overwrite=args.overwrite)
        print(f"verdict: {result.path} ({'written' if result.written else 'kept'})")
        return 0
    if args.command == "validate":
        result = validate_verdict_doc(args.path)
        print(f"verdict: {result.path}")
        print(f"Mode A: {result.mode_a_verdict or 'missing'}")
        print(f"Mode B: {result.mode_b_verdict or 'missing'}")
        print(f"next questions: {len(result.next_questions)}/3")
        if result.ok:
            print("DOGFOOD_VERDICT_OK")
            return 0
        for missing in result.missing_requirements:
            print(f"missing: {missing}")
        return 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
