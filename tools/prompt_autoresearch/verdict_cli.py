"""CLI for rendering the Autoresearch Wedge 1 verdict from JSON outcomes."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from tools.prompt_autoresearch.runner import PromptMutationOutcome
from tools.prompt_autoresearch.score import CompositeScore
from tools.prompt_autoresearch.verdict import compute_verdict, render_verdict_markdown


def _as_float(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number")
    return float(value)


def _as_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _as_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _composite_from_json(raw: Any, *, index: int) -> CompositeScore:
    if not isinstance(raw, dict):
        raise ValueError(f"outcomes[{index}].composite_breakdown must be an object")
    return CompositeScore(
        rubric=_as_float(raw.get("rubric"), field=f"outcomes[{index}].composite_breakdown.rubric"),
        voice_style=_as_float(raw.get("voice_style"), field=f"outcomes[{index}].composite_breakdown.voice_style"),
        sector_vocab=_as_float(raw.get("sector_vocab"), field=f"outcomes[{index}].composite_breakdown.sector_vocab"),
        grounding=_as_float(raw.get("grounding"), field=f"outcomes[{index}].composite_breakdown.grounding"),
        total=_as_float(raw.get("total"), field=f"outcomes[{index}].composite_breakdown.total"),
    )


def outcome_from_json(raw: Any, *, index: int) -> PromptMutationOutcome:
    """Convert one JSON object into the runner's verdict input type."""
    if not isinstance(raw, dict):
        raise ValueError(f"outcomes[{index}] must be an object")
    try:
        cost = Decimal(str(raw.get("cost_usd", "0")))
    except Exception as exc:  # pragma: no cover - Decimal's exception type is version-specific.
        raise ValueError(f"outcomes[{index}].cost_usd must be decimal-compatible") from exc

    return PromptMutationOutcome(
        mutation_id=_as_str(raw.get("mutation_id"), field=f"outcomes[{index}].mutation_id"),
        accepted=_as_bool(raw.get("accepted"), field=f"outcomes[{index}].accepted"),
        baseline_score=_as_float(raw.get("baseline_score"), field=f"outcomes[{index}].baseline_score"),
        candidate_score=_as_float(raw.get("candidate_score"), field=f"outcomes[{index}].candidate_score"),
        delta=_as_float(raw.get("delta"), field=f"outcomes[{index}].delta"),
        epsilon_required=_as_float(raw.get("epsilon_required"), field=f"outcomes[{index}].epsilon_required"),
        composite_breakdown=_composite_from_json(raw.get("composite_breakdown"), index=index),
        cost_usd=cost,
        notes=str(raw.get("notes", "")),
    )


def load_outcomes(path: Path) -> tuple[str | None, list[PromptMutationOutcome]]:
    """Load either ``[{...}]`` or ``{"role": "...", "outcomes": [{...}]}``."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    role: str | None = None
    if isinstance(raw, dict):
        if "role" in raw:
            role = _as_str(raw["role"], field="role")
        raw_outcomes = raw.get("outcomes")
    else:
        raw_outcomes = raw
    if not isinstance(raw_outcomes, list):
        raise ValueError("input must be a JSON array or an object with an outcomes array")
    return role, [
        outcome_from_json(item, index=i)
        for i, item in enumerate(raw_outcomes)
    ]


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
        json_role, outcomes = load_outcomes(args.outcomes)
        role = args.role or json_role
        if not role:
            raise ValueError("--role is required when the JSON file does not include role")
        markdown = render_verdict_markdown(compute_verdict(role, outcomes))
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
