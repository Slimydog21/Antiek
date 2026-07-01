from __future__ import annotations

import json

from tools.activation.read_dogfood import load_jsonl, validate_sessions


def _session(
    idx: int,
    *,
    live: bool = False,
    citation: bool = False,
    entry_door: str = "library",
) -> dict:
    return {
        "session_id": f"session-{idx}",
        "date": "2026-06-30",
        "build_sha": "abc123",
        "url": "https://app.example/read/doc-1",
        "operator": "operator",
        "document_id": f"doc-{idx}",
        "entry_door": entry_door,
        "provider_status": "ready" if live else "absent",
        "live_provider_ai": live,
        "citation_traced": citation,
        "minutes_reading": 22,
        "steps": {
            "1": {"status": "pass"},
            "2": {"status": "pass"},
            "3": {"status": "pass" if live else "inert"},
            "4": {"status": "pass" if live else "inert"},
            "5": {"status": "pass"},
            "6": {"status": "pass"},
            "7": {"status": "pass"},
        },
    }


def test_closure_ready_when_golden_path_rule_is_satisfied() -> None:
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library")
        for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"
    records[-1]["verdict"] = "ACTIVATE"

    report = validate_sessions(records)

    assert report.closure_ready is True
    assert report.valid_sessions == 10
    assert report.live_provider_sessions == 5
    assert report.citation_trace_sessions == 3
    assert report.non_library_sessions == 1
    assert report.final_verdict == "ACTIVATE"
    assert report.failures == ()


def test_mechanically_complete_log_requires_final_verdict() -> None:
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library")
        for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert report.final_verdict is None
    assert any("final verdict required" in f for f in report.failures)


def test_final_verdict_must_be_allowed_value() -> None:
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library")
        for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"
    records[-1]["verdict"] = "ship it"

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert report.final_verdict == "ship it"
    assert any("final verdict must be one of" in f for f in report.failures)


def test_repair_verdict_requires_blocking_issue_ids() -> None:
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library")
        for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"
    records[-1]["verdict"] = "REPAIR"

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert report.final_verdict == "REPAIR"
    assert any(
        "REPAIR verdict requires blocking_issue_ids to be a list" in f
        for f in report.failures
    )


def test_repair_verdict_rejects_empty_blocking_issue_ids() -> None:
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library")
        for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"
    records[-1]["verdict"] = "REPAIR"
    records[-1]["blocking_issue_ids"] = []

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert report.final_verdict == "REPAIR"
    assert any(
        "REPAIR verdict requires at least one blocking_issue_ids entry" in f
        for f in report.failures
    )


def test_repair_verdict_rejects_blank_blocking_issue_ids() -> None:
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library")
        for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"
    records[-1]["verdict"] = "REPAIR"
    records[-1]["blocking_issue_ids"] = ["READ-421", "   "]

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert report.final_verdict == "REPAIR"
    assert any(
        "blocking_issue_ids entries must be non-empty strings" in f
        for f in report.failures
    )


def test_repair_verdict_rejects_non_string_blocking_issue_ids() -> None:
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library")
        for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"
    records[-1]["verdict"] = "REPAIR"
    records[-1]["blocking_issue_ids"] = [123]

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert report.final_verdict == "REPAIR"
    assert any(
        "blocking_issue_ids entries must be non-empty strings" in f
        for f in report.failures
    )


def test_repair_verdict_with_blocking_issue_ids_is_explicit_non_closure() -> None:
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library")
        for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"
    records[-1]["verdict"] = "REPAIR"
    records[-1]["blocking_issue_ids"] = ["READ-421", "  READ-422  "]

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert report.final_verdict == "REPAIR"
    assert any(
        "closure requires final verdict ACTIVATE; found REPAIR" in f
        for f in report.failures
    )
    assert not any(
        "REPAIR verdict requires at least one blocking_issue_ids entry" in f
        for f in report.failures
    )


def test_final_verdict_accepts_normalized_roll_back_claim() -> None:
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library")
        for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"
    records[-1]["verdict"] = "roll_back_claim"

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert report.final_verdict == "ROLL BACK CLAIM"
    assert any(
        "closure requires final verdict ACTIVATE; found ROLL BACK CLAIM" in f
        for f in report.failures
    )


def test_citation_tracing_requires_explicit_session_evidence() -> None:
    records = [
        _session(i, live=i <= 5, citation=i <= 2, entry_door="library")
        for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert report.valid_sessions == 10
    assert report.citation_trace_sessions == 2
    assert any(
        ">=3 valid sessions with citation/source tracing" in f
        for f in report.failures
    )


def test_citation_trace_flag_requires_citation_step_to_pass() -> None:
    record = _session(1, citation=True)
    record["steps"]["5"] = {
        "status": "fail",
        "followup_issue": "citation marker opened the wrong source",
    }

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.citation_trace_sessions == 0
    assert any(
        "citation_traced=true requires step 5 to pass" in f
        for f in report.failures
    )


def test_non_library_entry_accepts_human_spelled_command_palette() -> None:
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library")
        for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "Command Palette"
    records[-1]["verdict"] = "ACTIVATE"

    report = validate_sessions(records)

    assert report.closure_ready is True
    assert report.non_library_sessions == 1


def test_non_library_entry_accepts_write_trace_to_source_label() -> None:
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library")
        for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "Write trace-to-source"
    records[-1]["verdict"] = "ACTIVATE"

    report = validate_sessions(records)

    assert report.closure_ready is True
    assert report.non_library_sessions == 1


def test_not_enough_live_provider_sessions_blocks_closure() -> None:
    records = [_session(i, live=i <= 4, citation=True) for i in range(1, 11)]
    records[0]["entry_door"] = "search"

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert any(">=5 valid sessions with live_provider_ai=true" in f for f in report.failures)


def test_live_provider_sessions_require_dialogue_and_research_steps_to_pass() -> None:
    records = [_session(i, live=i <= 5, citation=True) for i in range(1, 11)]
    records[0]["entry_door"] = "search"
    records[0]["steps"]["3"] = {"status": "inert"}

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert report.live_provider_sessions == 4
    assert any(
        "live_provider_ai=true requires provider-backed steps 3 and 4 to pass" in f
        for f in report.failures
    )
    assert any(">=5 valid sessions with live_provider_ai=true" in f for f in report.failures)


def test_live_provider_session_requires_ready_provider_status() -> None:
    records = [_session(i, live=i <= 5, citation=True) for i in range(1, 11)]
    records[0]["entry_door"] = "search"
    records[0]["provider_status"] = "absent"

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert any(
        "live_provider_ai=true requires provider_status=ready" in f
        for f in report.failures
    )


def test_live_provider_flag_must_be_explicit_boolean() -> None:
    record = _session(1)
    del record["live_provider_ai"]

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert any("missing required fields: live_provider_ai" in f for f in report.failures)


def test_citation_traced_flag_must_be_explicit_boolean() -> None:
    record = _session(1)
    record["citation_traced"] = "false"

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.citation_trace_sessions == 0
    assert any("citation_traced must be a boolean" in f for f in report.failures)


def test_malformed_live_provider_flag_does_not_inflate_report_counter() -> None:
    record = _session(1, live=True)
    record["live_provider_ai"] = "false"

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.live_provider_sessions == 0
    assert any("live_provider_ai must be a boolean" in f for f in report.failures)


def test_whitespace_only_required_string_is_missing() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["session_id"] = "   "
    record["operator"] = "   "

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert any(
        "<record-1>: missing required fields: session_id, operator" in f
        for f in report.failures
    )


def test_deployed_build_date_must_be_iso_day() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["date"] = "June 30, 2026"

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert any("date must be YYYY-MM-DD" in f for f in report.failures)


def test_deployed_build_sha_must_be_git_sha_shaped() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["build_sha"] = "latest"

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert any("build_sha must be a 6-40 character git SHA" in f for f in report.failures)


def test_deployed_build_sha_accepts_full_git_sha() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["build_sha"] = "0123456789abcdef0123456789abcdef01234567"

    report = validate_sessions([record])

    assert not any("build_sha must" in f for f in report.failures)


def test_deployed_build_url_must_be_http_url() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["url"] = "/read/doc-1"

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert any("url must be an http(s) URL" in f for f in report.failures)


def test_invalid_session_does_not_inflate_evidence_counters() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["date"] = "June 30, 2026"

    report = validate_sessions([record])

    assert report.valid_sessions == 0
    assert report.live_provider_sessions == 0
    assert report.citation_trace_sessions == 0
    assert report.non_library_sessions == 0
    assert any("date must be YYYY-MM-DD" in f for f in report.failures)
    assert not any(
        "live_provider_ai=true requires provider-backed steps 3 and 4 to pass" in f
        for f in report.failures
    )
    assert not any(
        "citation_traced=true requires step 5 to pass" in f
        for f in report.failures
    )


def test_unknown_step_status_is_rejected_explicitly() -> None:
    record = _session(1)
    record["steps"]["7"] = {"status": "passed"}

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert any("step 7 status must be one of" in f for f in report.failures)


def test_only_provider_backed_steps_can_be_inert() -> None:
    record = _session(1)
    record["steps"]["5"] = {"status": "inert"}

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert any("step 5 cannot be inert" in f for f in report.failures)


def test_reading_session_must_last_at_least_twenty_minutes() -> None:
    records = [_session(i, live=i <= 5, citation=True) for i in range(1, 11)]
    records[0]["entry_door"] = "search"
    records[0]["minutes_reading"] = 19

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert report.valid_sessions == 9
    assert any("minutes_reading must be at least 20" in f for f in report.failures)
    assert any(">=10 valid sessions" in f for f in report.failures)


def test_zero_reading_minutes_is_present_but_invalid() -> None:
    record = _session(1)
    record["minutes_reading"] = 0

    report = validate_sessions([record])

    assert any("minutes_reading must be at least 20" in f for f in report.failures)
    assert not any("missing required fields: minutes_reading" in f for f in report.failures)


def test_failure_or_irritation_requires_concrete_followup_issue() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["steps"]["7"] = {
        "status": "pass",
        "irritation": "return-to-reading lost context",
    }

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert any("step 7 has failure/irritation without followup_issue" in f for f in report.failures)


def test_malformed_session_issue_excludes_session_from_valid_count() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["issues"] = [{"summary": "latency spike while opening citation"}]

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert report.live_provider_sessions == 0
    assert report.citation_trace_sessions == 0
    assert report.non_library_sessions == 0
    assert any("issues[1] lacks concrete followup_issue" in f for f in report.failures)


def test_jsonl_loader_accepts_comments_and_blank_lines(tmp_path) -> None:
    path = tmp_path / "read-dogfood.jsonl"
    first = _session(1)
    second = _session(2, live=True)
    path.write_text(
        "\n# activation log\n"
        + json.dumps(first)
        + "\n\n"
        + json.dumps(second)
        + "\n",
        encoding="utf-8",
    )

    assert load_jsonl(path) == [first, second]
