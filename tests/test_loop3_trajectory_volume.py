import json

import duckdb

from compounding.verification.trajectory_volume import (
    audit_trajectory_volume,
    format_text,
    load_open_weight_policy_ids,
    main,
)


def _write_jsonl_event(path, *, policy_id, action_type="dispatch.call"):
    row = {
        "event_id": "evt-" + policy_id.replace("/", "-"),
        "investigation_id": path.stem,
        "action_type": action_type,
        "policy_id": policy_id,
        "payload": {
            "action_type": action_type,
            "provider": policy_id.split("/", 1)[0],
            "model": policy_id.split("/", 1)[1] if "/" in policy_id else policy_id,
        },
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def test_live_jsonl_diagnostic_counts_open_weight_only_from_allowlist(tmp_path):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    live = events_dir / "inv-a.jsonl"
    _write_jsonl_event(live, policy_id="openrouter/deepseek/deepseek-v4-pro")
    _write_jsonl_event(live, policy_id="openrouter/anthropic/claude-opus-4.7")

    result = audit_trajectory_volume(
        events_dir=events_dir,
        include_live_jsonl=True,
        open_weight_policy_ids={"openrouter/deepseek/deepseek-v4-pro"},
        min_sealed_investigations=1,
        min_open_weight_policy_fraction=0.5,
    )

    assert result.status == "FAIL"
    assert result.sealed_investigation_count == 0
    assert result.llm_event_count == 2
    assert result.open_weight_llm_event_count == 1
    assert result.open_weight_policy_fraction == 0.5
    assert result.closed_or_unknown_policy_ids == {
        "openrouter/anthropic/claude-opus-4.7": 1
    }
    assert "loop3_unlocked_by_this_probe: no" in format_text(result)


def test_sealed_parquet_default_path_can_pass_thresholds(tmp_path):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    con = duckdb.connect(":memory:")
    try:
        for investigation_id in ("inv-a", "inv-b"):
            con.execute(
                """
                CREATE OR REPLACE TABLE events AS
                SELECT
                  ? AS event_id,
                  ? AS investigation_id,
                  'dispatch.call' AS action_type,
                  'provider/model-a' AS policy_id,
                  ? AS payload
                """,
                [
                    f"evt-{investigation_id}",
                    investigation_id,
                    json.dumps({"action_type": "dispatch.call"}),
                ],
            )
            con.execute(
                f"COPY events TO '{events_dir / f'{investigation_id}.parquet'}' "
                "(FORMAT PARQUET)"
            )
    finally:
        con.close()

    result = audit_trajectory_volume(
        events_dir=events_dir,
        open_weight_policy_ids={"provider/model-a"},
        min_sealed_investigations=2,
        min_open_weight_policy_fraction=1.0,
    )

    assert result.status == "PASS"
    assert result.sealed_investigation_count == 2
    assert result.llm_event_count == 2
    assert result.open_weight_policy_fraction == 1.0


def test_policy_ids_are_not_inferred_from_model_names(tmp_path):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_jsonl_event(
        events_dir / "inv-a.jsonl",
        policy_id="openrouter/deepseek/deepseek-v4-pro",
    )

    result = audit_trajectory_volume(
        events_dir=events_dir,
        include_live_jsonl=True,
        open_weight_policy_ids=set(),
        min_sealed_investigations=1,
        min_open_weight_policy_fraction=0.8,
    )

    assert result.open_weight_llm_event_count == 0
    assert result.open_weight_policy_fraction == 0.0
    assert result.closed_or_unknown_policy_ids == {
        "openrouter/deepseek/deepseek-v4-pro": 1
    }


def test_load_open_weight_policy_ids_from_supported_file_shapes(tmp_path):
    json_list = tmp_path / "list.json"
    json_list.write_text(json.dumps(["provider/model-a"]), encoding="utf-8")
    json_object = tmp_path / "object.json"
    json_object.write_text(
        json.dumps({"open_weight_policy_ids": ["provider/model-b"]}),
        encoding="utf-8",
    )
    json_boolean_object = tmp_path / "boolean-object.json"
    json_boolean_object.write_text(
        json.dumps({"provider/model-d": True, "provider/closed": False}),
        encoding="utf-8",
    )
    text_file = tmp_path / "policies.txt"
    text_file.write_text("# comment\nprovider/model-c\n\n", encoding="utf-8")

    assert load_open_weight_policy_ids(
        [json_list, json_object, json_boolean_object, text_file]
    ) == {
        "provider/model-a",
        "provider/model-b",
        "provider/model-c",
        "provider/model-d",
    }


def test_cli_returns_nonzero_until_gate_thresholds_pass(tmp_path, capsys):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    _write_jsonl_event(events_dir / "inv-a.jsonl", policy_id="provider/model-a")

    exit_code = main([
        "--events-dir",
        str(events_dir),
        "--include-live-jsonl",
        "--open-weight-policy-id",
        "provider/model-a",
        "--min-sealed-investigations",
        "1",
    ])

    assert exit_code == 1
    assert "sealed_investigation_count: 0" in capsys.readouterr().out
