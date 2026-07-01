"""Loop 3 reward-signal volume audit.

This read-only audit covers the first measurable sub-gate of
``docs/loop_3_unlock_criteria.md`` criterion 3: production trajectories must
contain enough ``rubric.scored`` events before RL can train against reward.

It deliberately does not claim the deeper correlation or noise-floor criteria.
Those require notebooks / repeated evals that this count-only probe cannot
substitute for.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .trajectory_volume import _read_jsonl_rows, _read_parquet_rows

DEFAULT_MIN_LLM_EVENTS = 1_000
DEFAULT_MIN_RUBRIC_SCORED_EVENTS = 1_000


@dataclass(frozen=True)
class RewardSignalAudit:
    status: str
    events_dir: str
    sealed_investigation_count: int
    llm_event_count: int
    min_llm_events: int
    rubric_scored_event_count: int
    min_rubric_scored_events: int
    outcome_recorded_event_count: int
    rubric_scored_synthesis_count: int
    outcome_recorded_synthesis_count: int
    live_jsonl_included: bool
    checks: list[dict[str, Any]]
    proves_correlation_or_noise_floor: bool = False
    does_not_unlock_loop3: bool = True


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload")
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _is_action(row: dict[str, Any], action_type: str) -> bool:
    if row.get("action_type") == action_type:
        return True
    return _payload(row).get("action_type") == action_type


def _synthesis_id(row: dict[str, Any]) -> str | None:
    value = row.get("synthesis_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    payload_value = _payload(row).get("synthesis_id")
    if isinstance(payload_value, str) and payload_value.strip():
        return payload_value.strip()
    return None


def audit_reward_signal(
    *,
    events_dir: Path,
    include_live_jsonl: bool = False,
    min_llm_events: int = DEFAULT_MIN_LLM_EVENTS,
    min_rubric_scored_events: int = DEFAULT_MIN_RUBRIC_SCORED_EVENTS,
) -> RewardSignalAudit:
    root = events_dir.expanduser().resolve()
    parquet_paths = sorted(root.glob("*.parquet")) if root.is_dir() else []
    rows = _read_parquet_rows(parquet_paths)
    if include_live_jsonl and root.is_dir():
        for path in sorted(root.glob("*.jsonl")):
            rows.extend(_read_jsonl_rows(path))

    llm_event_count = sum(1 for row in rows if _is_action(row, "dispatch.call"))
    rubric_rows = [row for row in rows if _is_action(row, "rubric.scored")]
    outcome_rows = [row for row in rows if _is_action(row, "outcome.recorded")]
    rubric_synthesis_ids = {
        sid for sid in (_synthesis_id(row) for row in rubric_rows) if sid
    }
    outcome_synthesis_ids = {
        sid for sid in (_synthesis_id(row) for row in outcome_rows) if sid
    }
    checks = [
        {
            "name": "events_dir_exists",
            "passed": root.is_dir(),
            "detail": str(root),
        },
        {
            "name": "sealed_investigations_present",
            "passed": len(parquet_paths) > 0,
            "detail": f"{len(parquet_paths)} sealed parquet file(s)",
        },
        {
            "name": "llm_event_count",
            "passed": llm_event_count >= min_llm_events,
            "detail": f"{llm_event_count} >= {min_llm_events}",
        },
        {
            "name": "rubric_scored_event_count",
            "passed": len(rubric_rows) >= min_rubric_scored_events,
            "detail": f"{len(rubric_rows)} >= {min_rubric_scored_events}",
        },
        {
            "name": "sealed_only_evidence_mode",
            "passed": not include_live_jsonl,
            "detail": (
                "live JSONL excluded"
                if not include_live_jsonl
                else "live JSONL included for diagnostics only"
            ),
        },
    ]
    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return RewardSignalAudit(
        status=status,
        events_dir=str(root),
        sealed_investigation_count=len(parquet_paths),
        llm_event_count=llm_event_count,
        min_llm_events=min_llm_events,
        rubric_scored_event_count=len(rubric_rows),
        min_rubric_scored_events=min_rubric_scored_events,
        outcome_recorded_event_count=len(outcome_rows),
        rubric_scored_synthesis_count=len(rubric_synthesis_ids),
        outcome_recorded_synthesis_count=len(outcome_synthesis_ids),
        live_jsonl_included=include_live_jsonl,
        checks=checks,
    )


def format_text(result: RewardSignalAudit) -> str:
    lines = [
        f"loop3-reward-signal: {result.status}",
        f"events_dir: {result.events_dir}",
        f"sealed_investigation_count: {result.sealed_investigation_count}",
        f"llm_event_count: {result.llm_event_count}",
        f"min_llm_events: {result.min_llm_events}",
        f"rubric_scored_event_count: {result.rubric_scored_event_count}",
        f"min_rubric_scored_events: {result.min_rubric_scored_events}",
        f"outcome_recorded_event_count: {result.outcome_recorded_event_count}",
        f"rubric_scored_synthesis_count: {result.rubric_scored_synthesis_count}",
        f"outcome_recorded_synthesis_count: {result.outcome_recorded_synthesis_count}",
        f"live_jsonl_included: {str(result.live_jsonl_included).lower()}",
        "proves_correlation_or_noise_floor: no",
    ]
    for check in result.checks:
        marker = "PASS" if check["passed"] else "FAIL"
        lines.append(f"{marker} {check['name']}: {check['detail']}")
    lines.append("loop3_unlocked_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Loop 3 rubric.scored reward-signal volume. This is read-only "
            "and does not prove reward correlation or unlock Loop 3 by itself."
        )
    )
    parser.add_argument(
        "--events-dir",
        type=Path,
        default=Path("~/.antiek/research_events"),
        help="Trajectory event directory. Defaults to ~/.antiek/research_events.",
    )
    parser.add_argument(
        "--include-live-jsonl",
        action="store_true",
        help="Include live JSONL rows for diagnostics. Gate evidence stays sealed-only.",
    )
    parser.add_argument(
        "--min-llm-events",
        type=int,
        default=DEFAULT_MIN_LLM_EVENTS,
        help=f"Minimum dispatch.call events. Default: {DEFAULT_MIN_LLM_EVENTS}.",
    )
    parser.add_argument(
        "--min-rubric-scored-events",
        type=int,
        default=DEFAULT_MIN_RUBRIC_SCORED_EVENTS,
        help=(
            "Minimum rubric.scored events. "
            f"Default: {DEFAULT_MIN_RUBRIC_SCORED_EVENTS}."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.min_llm_events < 1:
        parser.error("--min-llm-events must be >= 1")
    if args.min_rubric_scored_events < 1:
        parser.error("--min-rubric-scored-events must be >= 1")
    result = audit_reward_signal(
        events_dir=args.events_dir,
        include_live_jsonl=args.include_live_jsonl,
        min_llm_events=args.min_llm_events,
        min_rubric_scored_events=args.min_rubric_scored_events,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
