#!/usr/bin/env python3
"""Generate a blinded HTML/JSON weekly recursive-context replay report."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from substrate.context_pack.recursive_feedback import (  # noqa: E402
    FileRecursiveFeedbackStore,
)
from substrate.context_pack.recursive_ranking import (  # noqa: E402
    ReplaySession,
    build_ranking_snapshot,
    replay_report_html,
    weekly_replay,
)


def _sessions(path: Path) -> list[ReplaySession]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("sessions input must be a JSON list")
    return [
        ReplaySession(
            session_id=str(item["session_id"]),
            task_class=str(item["task_class"]),  # type: ignore[arg-type]
            baseline_unit_ids=tuple(str(value) for value in item["baseline_unit_ids"]),
            baseline_text_digests=tuple(str(value) for value in item["baseline_text_digests"]),
            relevant_unit_ids=tuple(str(value) for value in item["relevant_unit_ids"]),
        )
        for item in raw
        if isinstance(item, dict)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feedback-dir", type=Path, required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--sessions-json", type=Path, required=True)
    parser.add_argument("--task-class", default="research_reasoning")
    parser.add_argument("--week-id", required=True)
    parser.add_argument("--output-html", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    store = FileRecursiveFeedbackStore(args.feedback_dir)
    snapshot = build_ranking_snapshot(
        owner_user_id=args.owner_id,
        task_class=args.task_class,
        receipts=store.list(args.owner_id),
        now_ms=int(time.time() * 1000),
    )
    report = weekly_replay(
        week_id=args.week_id,
        task_class=args.task_class,
        sessions=_sessions(args.sessions_json),
        snapshot=snapshot,
    )
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.write_text(replay_report_html(report), encoding="utf-8")
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(asdict(report), sort_keys=True, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
