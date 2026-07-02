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


@dataclass(frozen=True)
class DogfoodScaffoldResult:
    root: Path
    template_path: Path
    operator_log_path: Path
    template_written: bool
    operator_log_written: bool


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

    template_written = False
    if overwrite_template or not template_path.exists():
        template_path.write_text(DOGFOOD_TEMPLATE, encoding="utf-8")
        template_written = True

    operator_log_written = False
    if not operator_log_path.exists():
        operator_log_path.write_text(OPERATOR_LOG_HEADER, encoding="utf-8")
        operator_log_written = True

    return DogfoodScaffoldResult(
        root=dogfood_root,
        template_path=template_path,
        operator_log_path=operator_log_path,
        template_written=template_written,
        operator_log_written=operator_log_written,
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

    args = parser.parse_args(argv)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
