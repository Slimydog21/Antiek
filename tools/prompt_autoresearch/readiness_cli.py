"""CLI for auditing Autoresearch Wedge 1 readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.prompt_autoresearch.readiness import (
    audit_wedge1_readiness,
    render_readiness_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit current-tree readiness for Autoresearch Wedge 1.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Antiek repo root. Defaults to current directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of markdown.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = audit_wedge1_readiness(args.repo_root)
    if args.json:
        print(json.dumps({
            "all_satisfied": report.all_satisfied,
            "items": [
                {
                    "id": item.id,
                    "label": item.label,
                    "status": item.status,
                    "evidence": item.evidence,
                }
                for item in report.items
            ],
        }, indent=2, sort_keys=True))
    else:
        print(render_readiness_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
