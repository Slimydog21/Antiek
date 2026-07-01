#!/usr/bin/env python3
"""Read-only operator queries over the Loop-1 event log.

This CLI answers canonical debugging questions by scanning the append-only
event log at ``~/.antiek/research_events/{investigation_id}.jsonl`` or sealed
``.parquet`` files. ``ANTIEK_RESEARCH_EVENTS_DIR`` sets the default location;
``--events-dir`` overrides it per command.

It deliberately reuses ``substrate.event_log.events.trajectory()`` for all
event reading and follows the ``action_counts()`` full-directory scan pattern
for aggregate queries. It does not maintain a metrics store, index, daemon, or
dashboard.

Provider "fails" are defined as:

* a ``dispatch.call`` event whose payload has ``finish_reason == "error"``; or
* a paired ``role.call.failed`` event whose ``parent_event_id`` points at a
  ``dispatch.call`` event.

Unpaired ``role.call.failed`` events are not assigned to a provider/model,
because doing so would invent a denominator for the error rate.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from substrate.event_log import trajectory

PHASE_NAMES: dict[int, str] = {
    1: "Orient",
    2: "Round 1 broad landscape",
    3: "Round 1 self-critique",
    4: "Round 2 deep dive on gaps",
    5: "Round 2 self-critique",
    6: "Final synthesis",
    7: "Delivery",
    8: "Knowledge extraction",
    9: "Completion",
}


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else {}


def _phase_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _latency(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _investigation_ids(events_dir: str | None) -> list[str]:
    directory = events_dir or os.environ.get(
        "ANTIEK_RESEARCH_EVENTS_DIR",
        os.path.join(os.path.expanduser("~/.antiek"), "research_events"),
    )
    try:
        names = os.listdir(directory)
    except OSError:
        return []

    ids: set[str] = set()
    for name in names:
        if name.endswith(".jsonl"):
            ids.add(name[: -len(".jsonl")])
        elif name.endswith(".parquet"):
            ids.add(name[: -len(".parquet")])
    return sorted(ids)


def _safe_trajectory(investigation_id: str, events_dir: str | None) -> list[dict[str, Any]]:
    try:
        return trajectory(investigation_id, events_dir=events_dir)
    except Exception as exc:  # pragma: no cover - defensive parity with health probe.
        print(
            f"eventlog-query: skipping {investigation_id}: {exc!r}",
            file=sys.stderr,
        )
        return []


def _rows_for_scope(
    investigation_id: str | None,
    events_dir: str | None,
) -> list[dict[str, Any]]:
    if investigation_id:
        return _safe_trajectory(investigation_id, events_dir)

    rows: list[dict[str, Any]] = []
    for iid in _investigation_ids(events_dir):
        rows.extend(_safe_trajectory(iid, events_dir))
    return rows


def _p50(values: list[int]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _p95(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    # Nearest-rank p95 index; a 1-sample list returns that single sample.
    index = max(0, int(len(ordered) * 0.95 + 0.999999) - 1)
    return float(ordered[index])


def which_phase_slowest(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = _rows_for_scope(args.investigation_id, args.events_dir)
    exits = [row for row in rows if row.get("action_type") == "phase.exit"]

    if args.investigation_id:
        result: list[dict[str, Any]] = []
        for row in exits:
            phase = _phase_int(row.get("phase"))
            if phase is None:
                continue
            result.append(
                {
                    "investigation_id": row.get("investigation_id") or args.investigation_id,
                    "phase": phase,
                    "phase_name": PHASE_NAMES.get(phase, f"Phase {phase}"),
                    "latency_ms": _latency(_payload(row).get("latency_ms")),
                }
            )
        return sorted(
            result,
            key=lambda item: (
                item["latency_ms"] is None,
                -(item["latency_ms"] or -1),
                item["phase"],
            ),
        )

    by_phase: dict[int, list[int]] = defaultdict(list)
    unknowns: dict[int, int] = defaultdict(int)
    for row in exits:
        phase = _phase_int(row.get("phase"))
        if phase is None:
            continue
        latency = _latency(_payload(row).get("latency_ms"))
        if latency is None:
            unknowns[phase] += 1
        else:
            by_phase[phase].append(latency)

    phases = sorted(set(by_phase) | set(unknowns))
    result = []
    for phase in phases:
        values = by_phase.get(phase, [])
        result.append(
            {
                "phase": phase,
                "phase_name": PHASE_NAMES.get(phase, f"Phase {phase}"),
                "mean_latency_ms": float(statistics.fmean(values)) if values else None,
                "p50_latency_ms": _p50(values),
                "max_latency_ms": max(values) if values else None,
                "sample_count": len(values),
                "unknown_count": unknowns.get(phase, 0),
            }
        )
    return sorted(
        result,
        key=lambda item: (
            item["max_latency_ms"] is None,
            # -1 keeps all-unknown phases together after the explicit None key.
            -(item["mean_latency_ms"] or -1),
            item["phase"],
        ),
    )


@dataclass
class ProviderStats:
    calls: int = 0
    errors: int = 0
    latencies: list[int] | None = None

    def add_latency(self, latency: int | None) -> None:
        if latency is None:
            return
        if self.latencies is None:
            self.latencies = []
        self.latencies.append(latency)


def which_provider_fails(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = _rows_for_scope(args.investigation_id, args.events_dir)
    stats: dict[tuple[str, str], ProviderStats] = defaultdict(ProviderStats)
    dispatch_by_event_id: dict[str, tuple[str, str]] = {}
    failed_dispatch_event_ids: set[str] = set()

    for row in rows:
        if row.get("action_type") != "dispatch.call":
            continue
        payload = _payload(row)
        provider = str(payload.get("provider") or "unknown")
        model = str(payload.get("model") or "unknown")
        key = (provider, model)
        stats[key].calls += 1
        stats[key].add_latency(_latency(payload.get("latency_ms")))
        if payload.get("finish_reason") == "error":
            stats[key].errors += 1
            if row.get("event_id"):
                failed_dispatch_event_ids.add(str(row["event_id"]))
        if row.get("event_id"):
            dispatch_by_event_id[str(row["event_id"])] = key

    for row in rows:
        if row.get("action_type") != "role.call.failed":
            continue
        parent = row.get("parent_event_id")
        if not parent:
            continue
        key = dispatch_by_event_id.get(str(parent))
        if key is None or str(parent) in failed_dispatch_event_ids:
            continue
        stats[key].errors += 1

    result = []
    for (provider, model), item in stats.items():
        if item.calls <= 0:
            continue
        result.append(
            {
                "provider": provider,
                "model": model,
                "calls": item.calls,
                "errors": item.errors,
                "error_rate": item.errors / item.calls,
                "p95_latency_ms": _p95(item.latencies or []),
            }
        )
    return sorted(
        result,
        key=lambda item: (-item["error_rate"], -(item["p95_latency_ms"] or -1), item["provider"], item["model"]),
    )


def where_did_it_stall(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = _safe_trajectory(args.investigation_id, args.events_dir)
    last_completed_phase: int | None = None
    entered: dict[int, dict[str, Any]] = {}
    exited: set[int] = set()

    for row in rows:
        phase = _phase_int(row.get("phase"))
        action_type = row.get("action_type")
        if action_type == "phase.enter" and phase is not None:
            entered[phase] = row
        elif action_type == "phase.exit" and phase is not None:
            exited.add(phase)
            last_completed_phase = phase
        elif action_type == "investigation.failed":
            payload = _payload(row)
            failed_phase = _phase_int(payload.get("phase")) or phase
            return [
                {
                    "investigation_id": args.investigation_id,
                    "status": "failed",
                    "last_completed_phase": _phase_int(payload.get("last_completed_phase"))
                    or last_completed_phase,
                    "stalled_phase": failed_phase,
                    "phase_name": PHASE_NAMES.get(failed_phase, f"Phase {failed_phase}")
                    if failed_phase is not None
                    else "unknown",
                    "signature": "investigation.failed",
                    "diagnostic": payload.get("diagnostic") or payload.get("error") or "unknown",
                }
            ]

    if any(row.get("action_type") == "investigation.completed" for row in rows):
        return [
            {
                "investigation_id": args.investigation_id,
                "status": "completed",
                "last_completed_phase": last_completed_phase,
                "stalled_phase": None,
                "phase_name": None,
                "signature": "completed",
                "diagnostic": None,
            }
        ]

    unmatched = [phase for phase in entered if phase not in exited]
    if unmatched:
        stalled_phase = max(unmatched, key=lambda phase: entered[phase].get("emitted_at") or "")
        return [
            {
                "investigation_id": args.investigation_id,
                "status": "stalled",
                "last_completed_phase": last_completed_phase,
                "stalled_phase": stalled_phase,
                "phase_name": PHASE_NAMES.get(stalled_phase, f"Phase {stalled_phase}"),
                "signature": "phase.enter_without_phase.exit",
                "diagnostic": _payload(entered[stalled_phase]).get("note"),
            }
        ]

    return [
        {
            "investigation_id": args.investigation_id,
            "status": "unknown",
            "last_completed_phase": last_completed_phase,
            "stalled_phase": None,
            "phase_name": None,
            "signature": "no_open_phase_or_terminal_event",
            "diagnostic": None,
        }
    ]


def _fmt(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _print_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    if not rows:
        print("(no rows)")
        return
    widths = {
        column: max(len(column), *(len(_fmt(row.get(column))) for row in rows))
        for column in columns
    }
    print("  ".join(column.ljust(widths[column]) for column in columns))
    print("  ".join("-" * widths[column] for column in columns))
    for row in rows:
        print("  ".join(_fmt(row.get(column)).ljust(widths[column]) for column in columns))


def _display_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.command != "where-did-it-stall":
        return rows

    display: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if item.get("status") == "completed" and item.get("stalled_phase") is None:
            item["stalled_phase"] = "-"
            item["phase_name"] = "-"
            item["diagnostic"] = "-"
        display.append(item)
    return display


def _emit(rows: list[dict[str, Any]], args: argparse.Namespace, columns: list[str]) -> None:
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        _print_table(_display_rows(rows, args), columns)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--events-dir",
        default=None,
        help="Event log directory; overrides ANTIEK_RESEARCH_EVENTS_DIR/default.",
    )
    common.add_argument("--json", action="store_true", help="Emit the same data as a JSON list.")

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    slowest = sub.add_parser(
        "which-phase-slowest",
        parents=[common],
        help="Rank phase wall-clock latency from phase.exit payload latency_ms.",
    )
    slowest.add_argument("--investigation-id", default=None)
    slowest.set_defaults(func=which_phase_slowest)

    providers = sub.add_parser(
        "which-provider-fails",
        parents=[common],
        description=(
            "Rank provider/model failures. Fails are dispatch.call events with "
            'payload.finish_reason == "error" plus paired role.call.failed events '
            "whose parent_event_id points at a dispatch.call event."
        ),
        help=(
            "Rank provider/model failures. Fails = dispatch.call finish_reason=error "
            "or a paired role.call.failed with parent_event_id pointing at dispatch.call."
        ),
        epilog=(
            "Unpaired role.call.failed events are skipped because they cannot be "
            "assigned to a provider/model without inventing an error-rate denominator."
        ),
    )
    providers.add_argument("--investigation-id", default=None)
    providers.set_defaults(func=which_provider_fails)

    stall = sub.add_parser(
        "where-did-it-stall",
        parents=[common],
        help="Report terminal failure, completion, or the last phase.enter without phase.exit.",
    )
    stall.add_argument("--investigation-id", required=True)
    stall.set_defaults(func=where_did_it_stall)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    rows = args.func(args)
    if args.command == "which-phase-slowest" and args.investigation_id:
        columns = ["phase", "phase_name", "latency_ms"]
    elif args.command == "which-phase-slowest":
        columns = [
            "phase",
            "phase_name",
            "mean_latency_ms",
            "p50_latency_ms",
            "max_latency_ms",
            "sample_count",
            "unknown_count",
        ]
    elif args.command == "which-provider-fails":
        columns = ["provider", "model", "calls", "errors", "error_rate", "p95_latency_ms"]
    else:
        columns = [
            "investigation_id",
            "status",
            "last_completed_phase",
            "stalled_phase",
            "phase_name",
            "signature",
            "diagnostic",
        ]
    _emit(rows, args, columns)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
