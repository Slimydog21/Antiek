#!/usr/bin/env python3
"""dr_quality_score — score a deep-research artifact on the quality rubric.

Reads a ``ResearchArtifactBody`` JSON document (from a file or stdin) and prints
its falsifiable quality score: per-axis verdicts + the measured-only overall.

This is the operator-facing way to *measure* deep-research quality today — the
seed of the DR-quality benchmark (see
``.infinite/sprint-briefs/deep-research-quality-competitive-spec.md``).

Read-only and pure: loads one artifact, scores it, prints, exits. Never writes,
dispatches a model, or touches the network.

Usage:
    python tools/dr_quality_score.py path/to/artifact.json
    cat artifact.json | python tools/dr_quality_score.py --
    python tools/dr_quality_score.py path/to/artifact.json --json   # machine-readable

Exit codes:
    0  scored successfully
    1  the artifact failed schema validation (not a valid ResearchArtifactBody)
    2  the input could not be read or parsed as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo-root on sys.path so `substrate.*` resolves when run as a plain script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from substrate.deep_research_quality.rubric_scorer import (  # noqa: E402
    DRQualityScore,
    score_deep_research_quality,
)
from substrate.research_artifact.schema import ResearchArtifactBody  # noqa: E402


def _load_artifact(path: str) -> ResearchArtifactBody:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"dr_quality_score: input is not valid JSON ({exc})", file=sys.stderr)
        sys.exit(2)
    try:
        return ResearchArtifactBody.model_validate(data)
    except Exception as exc:  # pydantic ValidationError
        print(f"dr_quality_score: not a valid ResearchArtifactBody ({exc})", file=sys.stderr)
        sys.exit(1)


def _format_human(score: DRQualityScore) -> str:
    lines = [
        f"investigation: {score.investigation_id}",
        f"overall: {score.overall:.3f}  ({score.measured_count}/{len(score.axes)} axes measured)",
        "",
        "axes:",
    ]
    for axis in score.axes:
        flag = "measured " if axis.measured else "unmeasrd "
        lines.append(f"  {flag} {axis.axis:<24} {axis.score:.3f}  {axis.reason}")
    if score.notes:
        lines.append("")
        lines.extend(f"  note: {n}" for n in score.notes)
    lines.append(f"\nauthority: {score.authority}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score a deep-research artifact JSON on the quality rubric.",
    )
    parser.add_argument(
        "path",
        help="path to a ResearchArtifactBody JSON file, or '-' for stdin",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the full score as JSON (machine-readable)",
    )
    args = parser.parse_args()

    body = _load_artifact(args.path)
    score = score_deep_research_quality(body)

    if args.json:
        out = {
            "investigation_id": score.investigation_id,
            "overall": score.overall,
            "measured_count": score.measured_count,
            "axes": [
                {
                    "axis": a.axis,
                    "score": a.score,
                    "measured": a.measured,
                    "reason": a.reason,
                }
                for a in score.axes
            ],
            "notes": list(score.notes),
            "authority": score.authority,
        }
        print(json.dumps(out, indent=2))
    else:
        print(_format_human(score))
    return 0


if __name__ == "__main__":
    sys.exit(main())
