"""Loop 3 open-weight deployment-justification audit.

Criterion 4 in ``docs/loop_3_unlock_criteria.md`` requires a written reason to
deploy an open-weight Antiek model instead of continuing closed-weight routing,
with at least one measured argument. This audit validates the evidence shape; it
does not judge whether the business or product argument is persuasive.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_JUSTIFICATION_PATH = Path("docs/decisions/loop3-open-weight-justification.md")
DEFAULT_MEASUREMENTS_PATH = Path("reports/loop3/open-weight-justification.json")
ALLOWED_CATEGORIES = ("cost", "latency", "policy_control", "privacy", "capability")
MIN_JUSTIFICATION_WORDS = 350
CATEGORY_NUMERIC_FIELDS = {
    "cost": ("closed_weight_monthly_usd", "open_weight_monthly_usd"),
    "latency": ("closed_weight_p95_ms", "open_weight_p95_ms"),
    "policy_control": ("blocked_closed_weight_routes",),
    "privacy": ("sensitive_events_count",),
    "capability": ("closed_weight_eval_score", "open_weight_eval_score"),
}


@dataclass(frozen=True)
class OpenWeightJustificationAudit:
    status: str
    justification_path: str
    measurements_path: str
    measured_categories: list[str]
    justification_word_count: int
    checks: list[dict[str, Any]]
    does_not_unlock_loop3: bool = True


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _word_count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    return len([word for word in text.split() if word.strip()])


def _has_decision_marker(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8").lower()
    except OSError:
        return False
    affirmative_markers = (
        "decision: deploy open-weight",
        "decision: use open-weight",
        "decision: switch to open-weight",
        "decision: route to open-weight",
    )
    return any(marker in text for marker in affirmative_markers)


def _measurement_is_valid(category: str, value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    metric = value.get("metric")
    measured_at = value.get("measured_at")
    source = value.get("source")
    required_numeric_fields = CATEGORY_NUMERIC_FIELDS[category]
    return (
        isinstance(metric, str)
        and bool(metric.strip())
        and isinstance(measured_at, str)
        and bool(measured_at.strip())
        and isinstance(source, str)
        and bool(source.strip())
        and all(isinstance(value.get(field), int | float) for field in required_numeric_fields)
    )


def _valid_measured_categories(payload: dict[str, Any] | None) -> list[str]:
    if payload is None:
        return []
    measurements = payload.get("measurements")
    if not isinstance(measurements, dict):
        return []
    valid: list[str] = []
    for category in ALLOWED_CATEGORIES:
        if _measurement_is_valid(category, measurements.get(category)):
            valid.append(category)
    return valid


def audit_open_weight_justification(
    *,
    justification_path: Path = DEFAULT_JUSTIFICATION_PATH,
    measurements_path: Path = DEFAULT_MEASUREMENTS_PATH,
    min_justification_words: int = MIN_JUSTIFICATION_WORDS,
) -> OpenWeightJustificationAudit:
    justification_abs = justification_path.expanduser().resolve()
    measurements_abs = measurements_path.expanduser().resolve()
    payload = _load_json_object(measurements_abs) if measurements_abs.is_file() else None
    word_count = _word_count(justification_abs)
    measured_categories = _valid_measured_categories(payload)
    checks = [
        {
            "name": "justification_exists",
            "passed": justification_abs.is_file(),
            "detail": str(justification_abs),
        },
        {
            "name": "justification_has_decision_marker",
            "passed": _has_decision_marker(justification_abs),
            "detail": "requires 'Decision:' and 'open-weight'",
        },
        {
            "name": "justification_length",
            "passed": word_count >= min_justification_words,
            "detail": f"{word_count} >= {min_justification_words} words",
        },
        {
            "name": "measurements_exists",
            "passed": measurements_abs.is_file(),
            "detail": str(measurements_abs),
        },
        {
            "name": "measurements_json_object",
            "passed": payload is not None,
            "detail": "top-level JSON object with measurements",
        },
        {
            "name": "at_least_one_measured_category",
            "passed": bool(measured_categories),
            "detail": ", ".join(measured_categories) or "<none>",
        },
    ]
    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return OpenWeightJustificationAudit(
        status=status,
        justification_path=str(justification_abs),
        measurements_path=str(measurements_abs),
        measured_categories=measured_categories,
        justification_word_count=word_count,
        checks=checks,
    )


def format_text(result: OpenWeightJustificationAudit) -> str:
    lines = [
        f"loop3-open-weight-justification: {result.status}",
        f"justification_path: {result.justification_path}",
        f"measurements_path: {result.measurements_path}",
        f"measured_categories: {', '.join(result.measured_categories) or '<none>'}",
        f"justification_word_count: {result.justification_word_count}",
    ]
    for check in result.checks:
        marker = "PASS" if check["passed"] else "FAIL"
        lines.append(f"{marker} {check['name']}: {check['detail']}")
    lines.append("loop3_unlocked_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Loop 3 open-weight deployment justification evidence. "
            "This is read-only and does not unlock Loop 3 by itself."
        )
    )
    parser.add_argument(
        "--justification",
        type=Path,
        default=DEFAULT_JUSTIFICATION_PATH,
        help=f"Justification markdown. Default: {DEFAULT_JUSTIFICATION_PATH}.",
    )
    parser.add_argument(
        "--measurements",
        type=Path,
        default=DEFAULT_MEASUREMENTS_PATH,
        help=f"Measurement JSON. Default: {DEFAULT_MEASUREMENTS_PATH}.",
    )
    parser.add_argument(
        "--min-justification-words",
        type=int,
        default=MIN_JUSTIFICATION_WORDS,
        help=f"Minimum justification word count. Default: {MIN_JUSTIFICATION_WORDS}.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.min_justification_words < 1:
        parser.error("--min-justification-words must be >= 1")
    result = audit_open_weight_justification(
        justification_path=args.justification,
        measurements_path=args.measurements,
        min_justification_words=args.min_justification_words,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
