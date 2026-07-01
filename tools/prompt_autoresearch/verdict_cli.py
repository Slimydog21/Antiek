"""CLI for rendering the Autoresearch Wedge 1 verdict from JSON outcomes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.prompt_autoresearch.outcomes_io import load_outcomes_json
from tools.prompt_autoresearch.verdict import compute_verdict, render_verdict_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render an Autoresearch Wedge 1 verdict markdown from JSON mutation outcomes.",
    )
    parser.add_argument(
        "--role",
        default=None,
        help="Role name for the verdict. Overrides role in the JSON file when both are present.",
    )
    parser.add_argument(
        "--outcomes",
        required=True,
        type=Path,
        help="JSON file containing mutation outcomes.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Markdown output path. Defaults to stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        json_role, outcomes = load_outcomes_json(args.outcomes)
        role = args.role or json_role
        if not role:
            raise ValueError("--role is required when the JSON file does not include role")
        markdown = render_verdict_markdown(compute_verdict(role, outcomes))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(markdown, encoding="utf-8")
        except OSError as exc:
            print(
                f"error: could not write verdict markdown: {args.output}: {exc}",
                file=sys.stderr,
            )
            return 2
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
