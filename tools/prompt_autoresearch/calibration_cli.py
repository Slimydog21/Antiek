"""CLI for rendering prompt-autoresearch no-op calibration reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.prompt_autoresearch.calibration import (
    calibrate_epsilon,
    render_calibration_markdown,
)
from tools.prompt_autoresearch.outcomes_io import load_outcomes_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a prompt-autoresearch epsilon calibration report from no-op outcomes.",
    )
    parser.add_argument(
        "--role",
        default=None,
        help="Role name for the calibration. Overrides role in the JSON file when both are present.",
    )
    parser.add_argument(
        "--outcomes",
        required=True,
        type=Path,
        help="JSON file containing no-op mutation outcomes.",
    )
    parser.add_argument(
        "--floor-epsilon",
        type=float,
        default=0.05,
        help="Minimum epsilon floor. Defaults to the Wedge 1 verdict floor.",
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
        markdown = render_calibration_markdown(
            calibrate_epsilon(role, outcomes, floor_epsilon=args.floor_epsilon)
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
