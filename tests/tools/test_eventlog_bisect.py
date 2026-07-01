from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.eventlog_bisect import bisect

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "tools" / "eventlog_bisect.py"
FIXTURES = ROOT / "tests" / "fixtures" / "trajectories"


def _event(
    event_id: str,
    investigation_id: str,
    action_type: str,
    phase: int,
    emitted_at: str,
    payload: dict,
    parent_event_id: str | None = None,
    role: str | None = None,
) -> dict:
    return {
        "event_id": event_id,
        "investigation_id": investigation_id,
        "synthesis_id": None,
        "phase": phase,
        "role": role,
        "action_type": action_type,
        "payload": payload,
        "parent_event_id": parent_event_id,
        "policy_id": "orchestrator-deterministic",
        "param_version": "test",
        "schema_version": 28,
        "emitted_at": emitted_at,
        "document_id": None,
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_empty_retrieval_localizes_to_data() -> None:
    verdict = bisect("empty_retrieval", events_dir=str(FIXTURES))

    assert verdict.cause == "DATA"
    assert verdict.evidence == [
        {
            "event_id": "empty_retrieval-e004",
            "action_type": "evidence.retrieve.delivered",
        }
    ]


def test_provider_error_localizes_to_dispatch_and_names_provider() -> None:
    verdict = bisect("provider_error", events_dir=str(FIXTURES))

    assert verdict.cause == "DISPATCH"
    assert "openai/gpt-4.1-mini" in verdict.reason
    assert {"event_id": "provider_error-e002", "action_type": "dispatch.call"} in verdict.evidence
    assert {"event_id": "provider_error-e003", "action_type": "role.call.failed"} in verdict.evidence


def test_code_bug_localizes_to_code_from_empty_synthesis() -> None:
    verdict = bisect("code_bug", events_dir=str(FIXTURES))

    assert verdict.cause == "CODE"
    assert {"event_id": "code_bug-e010", "action_type": "synthesize.delivered"} in verdict.evidence


def test_healthy_is_inconclusive_when_there_is_nothing_to_localize() -> None:
    verdict = bisect("healthy", events_dir=str(FIXTURES))

    assert verdict.cause == "INCONCLUSIVE"
    assert "no DATA, CODE, or DISPATCH failure signal" in verdict.reason
    assert verdict.evidence == []


def test_dispatch_ordering_wins_over_empty_retrieval(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    _write_jsonl(
        events_dir / "dispatch_and_empty.jsonl",
        [
            _event(
                "dispatch_and_empty-e001",
                "dispatch_and_empty",
                "dispatch.call",
                1,
                "2026-07-01T04:00:01Z",
                {
                    "action_type": "dispatch.call",
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "finish_reason": "error",
                },
            ),
            _event(
                "dispatch_and_empty-e002",
                "dispatch_and_empty",
                "evidence.retrieve.delivered",
                2,
                "2026-07-01T04:00:02Z",
                {
                    "action_type": "evidence.retrieve.delivered",
                    "sub_question": "What evidence exists?",
                    "answer": "",
                    "supporting_claims": [],
                    "evidentiary_gaps": [],
                    "insufficient_evidence": True,
                    "chunk_count": 0,
                    "latency_ms": None,
                },
                role="evidence_retriever",
            ),
        ],
    )

    verdict = bisect("dispatch_and_empty", events_dir=str(events_dir))

    assert verdict.cause == "DISPATCH"
    assert verdict.evidence == [{"event_id": "dispatch_and_empty-e001", "action_type": "dispatch.call"}]


def test_truncated_trajectory_is_inconclusive_and_names_missing_events(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    _write_jsonl(
        events_dir / "truncated.jsonl",
        [
            _event(
                "truncated-e001",
                "truncated",
                "phase.enter",
                1,
                "2026-07-01T05:00:01Z",
                {"action_type": "phase.enter", "entered_at": "2026-07-01T05:00:01Z"},
            )
        ],
    )

    verdict = bisect("truncated", events_dir=str(events_dir))

    assert verdict.cause == "INCONCLUSIVE"
    assert "evidence.retrieve.delivered" in verdict.reason
    assert "synthesize.delivered" in verdict.reason
    assert "investigation.completed or investigation.failed" in verdict.reason


def test_cli_prints_cause_reason_and_evidence() -> None:
    proc = _run_cli("--events-dir", str(FIXTURES), "--investigation-id", "empty_retrieval")

    assert "CAUSE: DATA" in proc.stdout
    assert "REASON:" in proc.stdout
    assert "empty_retrieval-e004 evidence.retrieve.delivered" in proc.stdout


def test_missing_synthesis_text_localizes_to_code(tmp_path: Path) -> None:
    """A synthesize.delivered whose synthesis text field is MISSING (None) is a
    structurally-broken synthesis and must localize to CODE (regression: the
    check previously required text is not None, silently passing a missing field)."""
    events_dir = tmp_path / "events"
    _write_jsonl(
        events_dir / "missing_synth.jsonl",
        [
            _event(
                "missing_synth-e001", "missing_synth", "evidence.retrieve.delivered", 2,
                "2026-07-01T04:00:01Z", {"action_type": "evidence.retrieve.delivered", "chunk_count": 5},
            ),
            _event(
                "missing_synth-e002", "missing_synth", "dispatch.call", 6,
                "2026-07-01T04:00:02Z",
                {"action_type": "dispatch.call", "provider": "openai", "model": "gpt-4.1-mini", "finish_reason": "stop"},
            ),
            _event(
                "missing_synth-e003", "missing_synth", "synthesize.delivered", 6,
                "2026-07-01T04:00:03Z", {"action_type": "synthesize.delivered"},  # NO synthesis text field
            ),
            _event(
                "missing_synth-e004", "missing_synth", "investigation.completed", 7,
                "2026-07-01T04:00:04Z", {"action_type": "investigation.completed"},
            ),
        ],
    )
    verdict = bisect("missing_synth", events_dir=str(events_dir))
    assert verdict.cause == "CODE"
    assert {"event_id": "missing_synth-e003", "action_type": "synthesize.delivered"} in verdict.evidence
