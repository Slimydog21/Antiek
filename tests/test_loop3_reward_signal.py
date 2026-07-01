import json

import duckdb

from compounding.verification.reward_signal import (
    audit_reward_signal,
    format_text,
    main,
)


def _write_parquet(events_dir, investigation_id, rows):
    con = duckdb.connect(":memory:")
    try:
        con.execute(
            """
            CREATE TABLE events (
              event_id VARCHAR,
              investigation_id VARCHAR,
              synthesis_id VARCHAR,
              action_type VARCHAR,
              payload VARCHAR
            )
            """
        )
        for index, row in enumerate(rows):
            con.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                [
                    f"evt-{investigation_id}-{index}",
                    investigation_id,
                    row.get("synthesis_id"),
                    row["action_type"],
                    json.dumps(row.get("payload", {"action_type": row["action_type"]})),
                ],
            )
        con.execute(
            f"COPY events TO '{events_dir / f'{investigation_id}.parquet'}' "
            "(FORMAT PARQUET)"
        )
    finally:
        con.close()


def _write_jsonl_event(path, *, action_type, synthesis_id=None):
    row = {
        "event_id": f"evt-{action_type}",
        "investigation_id": path.stem,
        "synthesis_id": synthesis_id,
        "action_type": action_type,
        "payload": json.dumps({"action_type": action_type}),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def test_reward_signal_passes_on_sealed_parquet_counts(tmp_path):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_parquet(
        events_dir,
        "inv-a",
        [
            {"action_type": "dispatch.call"},
            {"action_type": "dispatch.call"},
            {"action_type": "rubric.scored", "synthesis_id": "syn-a"},
            {"action_type": "rubric.scored", "synthesis_id": "syn-b"},
            {"action_type": "outcome.recorded", "synthesis_id": "syn-a"},
        ],
    )

    result = audit_reward_signal(
        events_dir=events_dir,
        min_llm_events=2,
        min_rubric_scored_events=2,
    )

    assert result.status == "PASS"
    assert result.llm_event_count == 2
    assert result.rubric_scored_event_count == 2
    assert result.outcome_recorded_event_count == 1
    assert result.rubric_scored_synthesis_count == 2
    assert result.outcome_recorded_synthesis_count == 1
    assert "proves_correlation_or_noise_floor: no" in format_text(result)


def test_reward_signal_fails_when_rubric_volume_missing(tmp_path):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_parquet(
        events_dir,
        "inv-a",
        [
            {"action_type": "dispatch.call"},
            {"action_type": "dispatch.call"},
            {"action_type": "rubric.scored", "synthesis_id": "syn-a"},
        ],
    )

    result = audit_reward_signal(
        events_dir=events_dir,
        min_llm_events=2,
        min_rubric_scored_events=2,
    )

    assert result.status == "FAIL"
    assert result.rubric_scored_event_count == 1


def test_live_jsonl_is_diagnostic_only(tmp_path):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    live = events_dir / "inv-live.jsonl"
    _write_jsonl_event(live, action_type="dispatch.call")
    _write_jsonl_event(live, action_type="rubric.scored", synthesis_id="syn-a")

    result = audit_reward_signal(
        events_dir=events_dir,
        include_live_jsonl=True,
        min_llm_events=1,
        min_rubric_scored_events=1,
    )

    assert result.status == "FAIL"
    assert result.live_jsonl_included is True
    assert any(
        check["name"] == "sealed_only_evidence_mode" and not check["passed"]
        for check in result.checks
    )


def test_cli_returns_nonzero_until_reward_gate_passes(tmp_path, capsys):
    events_dir = tmp_path / "events"
    events_dir.mkdir()

    exit_code = main([
        "--events-dir",
        str(events_dir),
        "--min-llm-events",
        "1",
        "--min-rubric-scored-events",
        "1",
    ])

    assert exit_code == 1
    assert "rubric_scored_event_count: 0" in capsys.readouterr().out
