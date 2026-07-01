"""Harvest Antiek trajectories into verifiers-compatible JSONL."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from substrate.event_log import default_events_dir, trajectory

TERMINAL_COMPLETED = "investigation.completed"
SYNTHESIS_ARCHIVED = "synthesis.archived"
CONSTRAINT_LOOP_RESOLVED = "constraint.loop_resolved"
OUTCOME_RECORDED = "outcome.recorded"

ROLE_DELIVERED_SUFFIXES = (".delivered", ".completed")
TELEMETRY_ACTION_TYPES = {
    "dispatch.call",
    "context_pack.assembled",
    "health.check",
}


@dataclass(frozen=True)
class QualityBreakdown:
    constraint_pass_rate: float
    synthesis_archived: float
    outcome_correlation: float | None = None
    composite: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint_pass_rate": self.constraint_pass_rate,
            "synthesis_archived": self.synthesis_archived,
            "outcome_correlation": self.outcome_correlation,
            "composite": self.composite,
        }


@dataclass(frozen=True)
class HarvestRecord:
    investigation_id: str
    task: dict[str, Any]
    rollout: dict[str, Any]
    reward: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "rollout": self.rollout,
            "reward": self.reward,
            "metadata": self.metadata,
        }


def load_events_from_jsonl(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row at {path}:{line_no} is not an object")
            rows.append(row)
    return rows


def load_events_from_dir(events_dir: str | os.PathLike[str]) -> list[dict[str, Any]]:
    root = Path(events_dir)
    if not root.exists():
        return []
    investigation_ids = sorted({
        path.stem
        for path in root.iterdir()
        if path.suffix in {".jsonl", ".parquet"}
    })
    rows: list[dict[str, Any]] = []
    for investigation_id in investigation_ids:
        rows.extend(trajectory(investigation_id, events_dir=str(root)))
    return rows


def group_by_investigation(events: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        investigation_id = str(event.get("investigation_id") or "")
        if not investigation_id:
            continue
        grouped[investigation_id].append(event)
    for rows in grouped.values():
        rows.sort(key=lambda r: (str(r.get("emitted_at") or ""), str(r.get("event_id") or "")))
    return dict(grouped)


def harvest_records(
    events: Iterable[dict[str, Any]],
    *,
    since: str | None = None,
    quality_threshold: float = 0.7,
    role_filter: str | None = None,
) -> list[HarvestRecord]:
    since_dt = _parse_since(since)
    records: list[HarvestRecord] = []
    for investigation_id, rows in group_by_investigation(events).items():
        completed = _terminal_completed_event(rows)
        if completed is None:
            continue
        if since_dt is not None and _event_dt(completed) < since_dt:
            continue
        quality = compute_quality(rows)
        if quality.composite < quality_threshold:
            continue
        records.append(_record_for_investigation(
            investigation_id,
            rows,
            completed,
            quality,
            role_filter=role_filter,
            quality_threshold=quality_threshold,
        ))
    return records


def compute_quality(events: list[dict[str, Any]]) -> QualityBreakdown:
    constraint_pass_rate = _constraint_pass_rate(events)
    synthesis_archived = 1.0 if any(
        _action_type(event) == SYNTHESIS_ARCHIVED for event in events
    ) else 0.0
    outcome_correlation = _outcome_correlation(events)
    components = [constraint_pass_rate, synthesis_archived]
    if outcome_correlation is not None:
        components.append(outcome_correlation)
    composite = sum(components) / len(components)
    return QualityBreakdown(
        constraint_pass_rate=constraint_pass_rate,
        synthesis_archived=synthesis_archived,
        outcome_correlation=outcome_correlation,
        composite=composite,
    )


def write_jsonl(records: Iterable[HarvestRecord], output: str | os.PathLike[str]) -> int:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record.to_jsonable(), sort_keys=True, separators=(",", ":")))
            f.write("\n")
            count += 1
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Harvest Antiek trajectories into verifiers-compatible JSONL.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--events-dir",
        default=None,
        help="Research event directory to scan; defaults to ANTIEK_RESEARCH_EVENTS_DIR.",
    )
    source.add_argument(
        "--input-jsonl",
        default=None,
        help="Fixture/source JSONL containing event rows from one or more investigations.",
    )
    parser.add_argument("--since", required=True, help="Keep investigations completed on/after DATE.")
    parser.add_argument(
        "--quality-threshold",
        type=float,
        default=0.7,
        help="Minimum composite quality score required for export.",
    )
    parser.add_argument("--role-filter", default=None, help="Optional role to keep in rollout steps.")
    parser.add_argument("--output", required=True, help="Output trajectories JSONL path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 0.0 <= args.quality_threshold <= 1.0:
        parser.error("--quality-threshold must be between 0 and 1")

    try:
        if args.input_jsonl:
            events = load_events_from_jsonl(args.input_jsonl)
        else:
            events = load_events_from_dir(args.events_dir or default_events_dir())
        records = harvest_records(
            events,
            since=args.since,
            quality_threshold=args.quality_threshold,
            role_filter=args.role_filter,
        )
        count = write_jsonl(records, args.output)
    except Exception as exc:
        print(f"tools.training.harvest failed: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "output": args.output,
                "records_written": count,
                "quality_threshold": args.quality_threshold,
            },
            sort_keys=True,
        )
    )
    return 0


def _record_for_investigation(
    investigation_id: str,
    events: list[dict[str, Any]],
    completed: dict[str, Any],
    quality: QualityBreakdown,
    *,
    role_filter: str | None,
    quality_threshold: float,
) -> HarvestRecord:
    steps = _rollout_steps(events, role_filter=role_filter)
    completed_payload = _payload(completed)
    task = {
        "task_id": investigation_id,
        "investigation_id": investigation_id,
        "target": completed_payload.get("thesis_summary", ""),
        "source": "antiek.event_log",
        "completed_at": completed.get("emitted_at"),
        "role_filter": role_filter,
    }
    rollout = {
        "policy_id": _dominant_policy_id(events),
        "steps": steps,
        "terminal_event": _event_ref(completed),
        "event_count": len(events),
    }
    reward = {
        "total": quality.composite,
        "passed": quality.composite >= quality_threshold,
        "breakdown": quality.to_dict(),
    }
    metadata = {
        "format": "antiek.verifiers.trajectory.v1",
        "quality_threshold": quality_threshold,
        "synthesis_id": completed.get("synthesis_id"),
        "document_id": completed.get("document_id"),
    }
    return HarvestRecord(
        investigation_id=investigation_id,
        task=task,
        rollout=rollout,
        reward=reward,
        metadata=metadata,
    )


def _rollout_steps(
    events: list[dict[str, Any]],
    *,
    role_filter: str | None,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    prior_payload: dict[str, Any] = {}
    for index, event in enumerate(events):
        action_type = _action_type(event)
        role = event.get("role")
        if role_filter and role != role_filter:
            prior_payload = _payload(event)
            continue
        if action_type in TELEMETRY_ACTION_TYPES:
            prior_payload = _payload(event)
            continue
        if not action_type.endswith(ROLE_DELIVERED_SUFFIXES):
            prior_payload = _payload(event)
            continue
        payload = _payload(event)
        steps.append({
            "observation": json.dumps(prior_payload, sort_keys=True),
            "action": json.dumps(payload, sort_keys=True),
            "reward": None,
            "info": {
                "event_id": event.get("event_id"),
                "action_type": action_type,
                "role": role,
                "policy_id": event.get("policy_id"),
                "step": index,
            },
        })
        prior_payload = payload
    return steps


def _constraint_pass_rate(events: list[dict[str, Any]]) -> float:
    resolved = [
        event for event in events
        if _action_type(event) == CONSTRAINT_LOOP_RESOLVED
    ]
    if not resolved:
        completed = _terminal_completed_event(events)
        if completed is None:
            return 0.0
        status = str(_payload(completed).get("constraint_loop_status") or "")
        return 1.0 if status in {"single_pass", "passed"} else 0.0

    passed = 0
    for event in resolved:
        status = str(_payload(event).get("final_status") or "")
        violation_count = _payload(event).get("final_violation_count")
        if status in {"single_pass", "passed"} and int(violation_count or 0) == 0:
            passed += 1
    return passed / len(resolved)


def _outcome_correlation(events: list[dict[str, Any]]) -> float | None:
    outcome_events = [
        event for event in events
        if _action_type(event) == OUTCOME_RECORDED
    ]
    if not outcome_events:
        return None

    scores: list[float] = []
    for event in outcome_events:
        payload = _payload(event)
        thesis = payload.get("thesis_outcomes") or []
        if thesis:
            scores.extend(_thesis_score(item) for item in thesis if isinstance(item, dict))
        alignment = payload.get("decision_alignment")
        if isinstance(alignment, dict):
            aligned = alignment.get("thesis_outcome_when_proceeded")
            if aligned and aligned != "not_observed":
                scores.append(_thesis_status_score(str(aligned)))
    if not scores:
        return None
    return sum(scores) / len(scores)


def _thesis_score(item: dict[str, Any]) -> float:
    return _thesis_status_score(str(item.get("outcome") or "unresolved"))


def _thesis_status_score(status: str) -> float:
    if status == "confirmed":
        return 1.0
    if status == "partially_confirmed":
        return 0.5
    if status == "disconfirmed":
        return 0.0
    return 0.25


def _terminal_completed_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    completed = [
        event for event in events
        if _action_type(event) == TERMINAL_COMPLETED
    ]
    return completed[-1] if completed else None


def _dominant_policy_id(events: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for event in events:
        policy_id = str(event.get("policy_id") or "")
        if policy_id:
            counts[policy_id] += 1
    if not counts:
        return "<unknown>"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _event_ref(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id"),
        "action_type": _action_type(event),
        "emitted_at": event.get("emitted_at"),
    }


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return {"raw_payload": payload}
    return payload if isinstance(payload, dict) else {}


def _action_type(event: dict[str, Any]) -> str:
    return str(event.get("action_type") or _payload(event).get("action_type") or "")


def _parse_since(value: str | None) -> datetime | None:
    if value is None:
        return None
    return _parse_dt(value)


def _event_dt(event: dict[str, Any]) -> datetime:
    return _parse_dt(str(event.get("emitted_at") or "1970-01-01T00:00:00Z"))


def _parse_dt(value: str) -> datetime:
    normalized = value
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        normalized = f"{value}T00:00:00+00:00"
    elif value.endswith("Z"):
        normalized = f"{value[:-1]}+00:00"
    return datetime.fromisoformat(normalized)


if __name__ == "__main__":
    raise SystemExit(main())
