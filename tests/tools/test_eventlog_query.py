from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "tools" / "eventlog_query.py"
FIXTURES = ROOT / "tests" / "fixtures" / "trajectories"


def _run_json(*args: str) -> list[dict]:
    proc = subprocess.run(
        [sys.executable, str(CLI), *args, "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _event(
    event_id: str,
    investigation_id: str,
    action_type: str,
    phase: int,
    emitted_at: str,
    payload: dict,
    parent_event_id: str | None = None,
) -> dict:
    return {
        "event_id": event_id,
        "investigation_id": investigation_id,
        "synthesis_id": None,
        "phase": phase,
        "role": None,
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


def test_which_phase_slowest_orders_single_trajectory_by_latency_desc() -> None:
    rows = _run_json(
        "which-phase-slowest",
        "--events-dir",
        str(FIXTURES),
        "--investigation-id",
        "healthy",
    )

    assert rows[0]["phase"] == 6
    assert rows[0]["phase_name"] == "Final synthesis"
    assert rows[0]["latency_ms"] == 15000
    assert rows[1]["phase"] == 4
    assert rows[-1]["phase"] == 1


def test_which_phase_slowest_reports_unknown_for_old_phase_exit(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    _write_jsonl(
        events_dir / "old_event.jsonl",
        [
            _event(
                "old-e1",
                "old_event",
                "phase.exit",
                1,
                "2026-07-01T00:00:01Z",
                {"action_type": "phase.exit", "exited_at": "2026-07-01T00:00:01Z"},
            ),
            _event(
                "old-e2",
                "old_event",
                "phase.exit",
                2,
                "2026-07-01T00:00:02Z",
                {
                    "action_type": "phase.exit",
                    "exited_at": "2026-07-01T00:00:02Z",
                    "latency_ms": 25,
                },
            ),
        ],
    )

    rows = _run_json(
        "which-phase-slowest",
        "--events-dir",
        str(events_dir),
        "--investigation-id",
        "old_event",
    )

    by_phase = {row["phase"]: row for row in rows}
    assert by_phase[1]["latency_ms"] is None
    assert by_phase[2]["latency_ms"] == 25

    aggregate = _run_json("which-phase-slowest", "--events-dir", str(events_dir))
    aggregate_by_phase = {row["phase"]: row for row in aggregate}
    assert aggregate_by_phase[1]["unknown_count"] == 1
    assert aggregate_by_phase[1]["sample_count"] == 0


def test_which_phase_slowest_accepts_whole_number_float_latency(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    _write_jsonl(
        events_dir / "float_latency.jsonl",
        [
            _event(
                "float-latency-e1",
                "float_latency",
                "phase.exit",
                1,
                "2026-07-01T00:00:01Z",
                {
                    "action_type": "phase.exit",
                    "exited_at": "2026-07-01T00:00:01Z",
                    "latency_ms": 1500.0,
                },
            ),
        ],
    )

    rows = _run_json(
        "which-phase-slowest",
        "--events-dir",
        str(events_dir),
        "--investigation-id",
        "float_latency",
    )

    assert rows[0]["latency_ms"] == 1500


def test_which_provider_fails_computes_error_rate_from_provider_error_fixture() -> None:
    rows = _run_json(
        "which-provider-fails",
        "--events-dir",
        str(FIXTURES),
        "--investigation-id",
        "provider_error",
    )

    assert rows[0] == {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "calls": 1,
        "errors": 1,
        "error_rate": 1.0,
        "p95_latency_ms": 2000.0,
    }
    assert rows[1]["provider"] == "anthropic"
    assert rows[1]["calls"] == 1
    assert rows[1]["errors"] == 0
    assert rows[1]["error_rate"] == 0.0


def test_where_did_it_stall_reports_completed_fixture() -> None:
    rows = _run_json(
        "where-did-it-stall",
        "--events-dir",
        str(FIXTURES),
        "--investigation-id",
        "healthy",
    )

    assert rows == [
        {
            "investigation_id": "healthy",
            "status": "completed",
            "last_completed_phase": 8,
            "stalled_phase": None,
            "phase_name": None,
            "signature": "completed",
            "diagnostic": None,
        }
    ]


def test_where_did_it_stall_table_marks_completed_stall_fields_not_applicable() -> None:
    proc = _run_cli(
        "where-did-it-stall",
        "--events-dir",
        str(FIXTURES),
        "--investigation-id",
        "healthy",
    )

    row = proc.stdout.strip().splitlines()[2].split()
    assert row == ["healthy", "completed", "8", "-", "-", "completed", "-"]
    assert "unknown" not in proc.stdout


def test_where_did_it_stall_detects_truncated_open_phase(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    _write_jsonl(
        events_dir / "truncated.jsonl",
        [
            _event(
                "truncated-e1",
                "truncated",
                "phase.enter",
                1,
                "2026-07-01T00:00:01Z",
                {"action_type": "phase.enter", "entered_at": "2026-07-01T00:00:01Z"},
            ),
            _event(
                "truncated-e2",
                "truncated",
                "phase.exit",
                1,
                "2026-07-01T00:00:03Z",
                {
                    "action_type": "phase.exit",
                    "exited_at": "2026-07-01T00:00:03Z",
                    "latency_ms": 2000,
                },
                "truncated-e1",
            ),
            _event(
                "truncated-e3",
                "truncated",
                "phase.enter",
                2,
                "2026-07-01T00:00:04Z",
                {
                    "action_type": "phase.enter",
                    "entered_at": "2026-07-01T00:00:04Z",
                    "note": "retrieval in progress",
                },
                "truncated-e2",
            ),
        ],
    )

    rows = _run_json(
        "where-did-it-stall",
        "--events-dir",
        str(events_dir),
        "--investigation-id",
        "truncated",
    )

    assert rows[0]["status"] == "stalled"
    assert rows[0]["last_completed_phase"] == 1
    assert rows[0]["stalled_phase"] == 2
    assert rows[0]["signature"] == "phase.enter_without_phase.exit"
    assert rows[0]["diagnostic"] == "retrieval in progress"

    proc = _run_cli(
        "where-did-it-stall",
        "--events-dir",
        str(events_dir),
        "--investigation-id",
        "truncated",
    )
    assert "stalled" in proc.stdout
    assert "Round 1 broad landscape" in proc.stdout


def test_malformed_trajectory_warns_and_exits_cleanly(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    malformed = events_dir / "malformed.jsonl"
    malformed.write_text(
        json.dumps(
            _event(
                "malformed-e1",
                "malformed",
                "phase.exit",
                1,
                "2026-07-01T00:00:01Z",
                {
                    "action_type": "phase.exit",
                    "exited_at": "2026-07-01T00:00:01Z",
                    "latency_ms": 10,
                },
            )
        )
        + "\n"
        + "[\"not\", \"a\", \"dict\"]\n"
        + '{"event_id":"truncated-final-line"',
        encoding="utf-8",
    )

    proc = _run_cli(
        "which-phase-slowest",
        "--events-dir",
        str(events_dir),
        "--investigation-id",
        "malformed",
    )

    assert proc.returncode == 0
    assert "(no rows)" in proc.stdout
    assert "eventlog-query: skipping malformed:" in proc.stderr
