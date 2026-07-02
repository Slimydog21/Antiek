from __future__ import annotations

import json
import re
from pathlib import Path

from tools.activation.read_dogfood import (
    append_session_template,
    load_jsonl,
    main,
    session_template,
    validate_sessions,
)


def _session(
    idx: int,
    *,
    live: bool = False,
    citation: bool = False,
    entry_door: str = "library",
) -> dict:
    steps = {
        "1": {
            "status": "pass",
            "visible_content_note": f"Visible heading and structured block for session {idx}.",
        },
        "2": {
            "status": "pass",
            "selected_text": f"Selected passage text for session {idx}.",
            "menu_labels": ["Ask", "Investigate", "Trace source"],
        },
        "3": {"status": "pass" if live else "inert"},
        "4": {"status": "pass" if live else "inert"},
        "5": {"status": "pass"},
        "6": {
            "status": "pass",
            "return_context_note": f"Return preserved reader context in session {idx}.",
        },
        "7": {"status": "pass", "operator_note": f"Read for continuity in session {idx}."},
    }
    if citation:
        steps["5"].update({
            "source_document_id": f"source-doc-{idx}",
            "chunk_id": f"chunk-{idx}",
            "result_url": (
                f"https://app.example/read/source-doc-{idx}"
                f"?chunk=chunk-{idx}&from=doc-{idx}&fromPage=0"
            ),
        })
    if live:
        steps["3"]["first_answer"] = f"First useful answer for passage {idx}."
        steps["4"]["investigation_id"] = f"child-investigation-{idx}"
    else:
        steps["3"]["exact_no_key_copy"] = "Dialogue requires provider activation keys."
        steps["4"]["exact_no_key_copy"] = "Research spin-out requires provider activation keys."
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
        "steps": steps,
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
    assert report.remaining_requirements() == {
        "valid_sessions": 0,
        "live_provider_sessions": 0,
        "citation_trace_sessions": 0,
        "non_library_sessions": 0,
    }
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


def test_partial_log_reports_remaining_requirements() -> None:
    records = [
        _session(1, live=True, citation=True, entry_door="search"),
        _session(2, live=True, citation=False, entry_door="library"),
        _session(3, live=False, citation=False, entry_door="library"),
    ]

    report = validate_sessions(records)

    assert report.remaining_requirements() == {
        "valid_sessions": 7,
        "live_provider_sessions": 3,
        "citation_trace_sessions": 2,
        "non_library_sessions": 0,
    }
    assert report.as_dict()["remaining_requirements"] == report.remaining_requirements()


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


def test_citation_trace_requires_source_chunk_and_result_url() -> None:
    record = _session(1, citation=True)
    record["steps"]["5"] = {"status": "pass"}

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert report.citation_trace_sessions == 0
    assert any("citation step 5 requires source_document_id" in f for f in report.failures)
    assert any("citation step 5 requires chunk_id or anchor" in f for f in report.failures)
    assert any("citation step 5 requires result_url" in f for f in report.failures)


def test_citation_trace_accepts_anchor_instead_of_chunk_id() -> None:
    record = _session(1, citation=True)
    step = record["steps"]["5"]
    del step["chunk_id"]
    step["anchor"] = "nearest-heading-7"

    report = validate_sessions([record])

    assert not any("citation step 5 requires chunk_id or anchor" in f for f in report.failures)


def test_citation_trace_result_url_must_be_http_url() -> None:
    record = _session(1, citation=True)
    record["steps"]["5"]["result_url"] = "/read/source-doc-1"

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.citation_trace_sessions == 0
    assert any("citation step 5 result_url must be an http(s) URL" in f for f in report.failures)


def test_citation_trace_result_url_must_open_recorded_source_in_reader() -> None:
    record = _session(1, citation=True)
    record["steps"]["5"]["result_url"] = "https://app.example/read/other-doc?chunk=chunk-1"

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.citation_trace_sessions == 0
    assert any(
        "citation step 5 result_url must open /read/{source_document_id}" in f
        for f in report.failures
    )


def test_citation_trace_result_url_must_carry_recorded_chunk_or_anchor() -> None:
    record = _session(1, citation=True)
    record["steps"]["5"]["result_url"] = "https://app.example/read/source-doc-1?from=doc-1"

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.citation_trace_sessions == 0
    assert any(
        "citation step 5 result_url must include the recorded chunk_id or anchor" in f
        for f in report.failures
    )


def test_citation_trace_result_url_must_carry_return_origin() -> None:
    record = _session(1, citation=True)
    record["steps"]["5"]["result_url"] = "https://app.example/read/source-doc-1?chunk=chunk-1"

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.citation_trace_sessions == 0
    assert any(
        "citation step 5 result_url must include from={document_id} return context" in f
        for f in report.failures
    )


def test_citation_trace_result_url_accepts_encoded_source_and_highlight_anchor() -> None:
    record = _session(1, citation=True)
    record["steps"]["5"] = {
        "status": "pass",
        "source_document_id": "source/doc 1",
        "anchor": "block:7",
        "result_url": (
            "https://app.example/read/source%2Fdoc%201"
            "?hl=source%2Fdoc%201%3Ablock%3A7&from=doc-1"
        ),
    }

    report = validate_sessions([record])

    assert not any("citation step 5 result_url must open" in f for f in report.failures)
    assert not any("citation step 5 result_url must include" in f for f in report.failures)


def test_citation_trace_return_origin_accepts_encoded_document_id() -> None:
    record = _session(1, citation=True)
    record["document_id"] = "doc/original 1"
    record["steps"]["5"]["result_url"] = (
        "https://app.example/read/source-doc-1?chunk=chunk-1&from=doc%2Foriginal%201"
    )

    report = validate_sessions([record])

    assert not any("from={document_id}" in f for f in report.failures)


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


def test_live_provider_steps_require_answer_and_research_id_evidence() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["steps"]["3"] = {"status": "pass"}
    record["steps"]["4"] = {"status": "pass"}

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert report.live_provider_sessions == 0
    assert any("live provider step 3 requires first_answer" in f for f in report.failures)
    assert any(
        "live provider step 4 requires investigation_id or session_id" in f
        for f in report.failures
    )


def test_live_provider_step_4_accepts_session_id_evidence() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    del record["steps"]["4"]["investigation_id"]
    record["steps"]["4"]["session_id"] = "research-session-1"

    report = validate_sessions([record])

    assert not any("live provider step 4 requires" in f for f in report.failures)


def test_inert_dialogue_step_requires_exact_no_key_copy() -> None:
    record = _session(1, live=False, citation=True, entry_door="search")
    record["steps"]["3"] = {"status": "inert"}

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert any(
        "inert provider step 3 requires exact no-key boundary copy" in f
        for f in report.failures
    )


def test_inert_research_step_requires_exact_no_key_copy() -> None:
    record = _session(1, live=False, citation=True, entry_door="search")
    record["steps"]["4"] = {"status": "inert"}

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert any(
        "inert provider step 4 requires exact no-key boundary copy" in f
        for f in report.failures
    )


def test_inert_provider_steps_accept_boundary_copy_alias() -> None:
    record = _session(1, live=False, citation=True, entry_door="search")
    record["steps"]["3"] = {
        "status": "inert",
        "activation_boundary_copy": "Dialogue requires provider activation keys.",
    }
    record["steps"]["4"] = {
        "status": "inert",
        "boundary_copy": "Research spin-out requires provider activation keys.",
    }

    report = validate_sessions([record])

    assert not any("inert provider step" in f for f in report.failures)


def test_reader_open_step_requires_screenshot_or_visible_content_note() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["steps"]["1"] = {"status": "pass"}

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert any(
        "step 1 requires screenshot reference or visible_content_note" in f
        for f in report.failures
    )


def test_reader_open_step_accepts_screenshot_reference() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["steps"]["1"] = {
        "status": "pass",
        "screenshot_path": "reports/read/session-1-open.png",
    }

    report = validate_sessions([record])

    assert not any("step 1 requires" in f for f in report.failures)


def test_selection_step_requires_selected_text_and_menu_labels() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["steps"]["2"] = {"status": "pass"}

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert any("step 2 requires selected_text" in f for f in report.failures)
    assert any("step 2 requires menu_labels" in f for f in report.failures)


def test_selection_step_accepts_action_menu_labels_alias() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["steps"]["2"] = {
        "status": "pass",
        "selected_text": "A passage selected from the reader.",
        "action_menu_labels": ["Ask", "Investigate"],
    }

    report = validate_sessions([record])

    assert not any("step 2 requires menu_labels" in f for f in report.failures)


def test_selection_menu_labels_must_be_non_empty_strings() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["steps"]["2"]["menu_labels"] = ["Ask", "   "]

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert any("step 2 requires menu_labels" in f for f in report.failures)


def test_reading_work_step_requires_operator_note() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["steps"]["7"] = {"status": "pass"}

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert any("step 7 requires operator_note" in f for f in report.failures)


def test_reading_work_step_accepts_reading_note_alias() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["steps"]["7"] = {
        "status": "pass",
        "reading_note": "Could return to the selected passage after asking.",
    }

    report = validate_sessions([record])

    assert not any("step 7 requires operator_note" in f for f in report.failures)


def test_return_context_step_requires_return_context_note() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["steps"]["6"] = {"status": "pass"}

    report = validate_sessions([record])

    assert report.closure_ready is False
    assert report.valid_sessions == 0
    assert any("step 6 requires return_context_note" in f for f in report.failures)


def test_return_context_step_accepts_context_note_alias() -> None:
    record = _session(1, live=True, citation=True, entry_door="search")
    record["steps"]["6"] = {
        "status": "pass",
        "context_note": "Back preserved the original selected passage.",
    }

    report = validate_sessions([record])

    assert not any("step 6 requires return_context_note" in f for f in report.failures)


def test_live_provider_session_requires_ready_provider_status() -> None:
    records = [_session(i, live=i <= 5, citation=True) for i in range(1, 11)]
    records[0]["entry_door"] = "search"
    records[0]["provider_status"] = "absent"

    report = validate_sessions(records)

    assert report.closure_ready is False
    assert report.valid_sessions == 9
    assert report.live_provider_sessions == 4
    assert report.non_library_sessions == 0
    assert any(
        "live_provider_ai=true requires provider_status=ready" in f
        for f in report.failures
    )
    assert any(">=10 valid sessions" in f for f in report.failures)
    assert any(">=5 valid sessions with live_provider_ai=true" in f for f in report.failures)


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


def test_inert_template_is_jsonl_safe_and_validator_compatible(capsys) -> None:
    assert main(["--template", "inert"]) == 0
    out = capsys.readouterr().out

    assert out.count("\n") == 1
    record = json.loads(out)
    report = validate_sessions([record])

    assert report.valid_sessions == 1
    assert report.live_provider_sessions == 0
    assert report.citation_trace_sessions == 0
    assert all(failure.startswith("closure requires ") for failure in report.failures)


def test_live_citation_template_carries_non_library_trace_evidence() -> None:
    record = session_template("live-citation")
    report = validate_sessions([record])

    assert report.valid_sessions == 1
    assert report.live_provider_sessions == 1
    assert report.citation_trace_sessions == 1
    assert report.non_library_sessions == 1
    assert all(failure.startswith("closure requires ") for failure in report.failures)


def test_template_rejects_unknown_kind() -> None:
    try:
        session_template("finished")
    except ValueError as exc:
        assert "template kind must be one of" in str(exc)
    else:
        raise AssertionError("session_template accepted an unknown kind")


def test_append_template_creates_log_file_and_parent_dirs(tmp_path, capsys) -> None:
    path = tmp_path / "operator" / "read-dogfood.jsonl"

    assert main(["--template", "live-citation", "--append", str(path)]) == 0
    out = capsys.readouterr().out

    records = load_jsonl(path)
    assert len(records) == 1
    assert records[0]["citation_traced"] is True
    assert records[0]["steps"]["5"]["result_url"].endswith(
        "?chunk=chunk-1&from=doc-1&fromPage=0"
    )
    assert "read-dogfood: 1/1 valid sessions" in out
    assert "remaining:" in out


def test_append_template_adds_line_to_existing_log(tmp_path) -> None:
    path = tmp_path / "read-dogfood.jsonl"
    append_session_template(path, session_template("inert"))

    assert main(["--template", "live", "--append", str(path)]) == 0

    records = load_jsonl(path)
    assert len(records) == 2
    assert records[0]["live_provider_ai"] is False
    assert records[1]["live_provider_ai"] is True


def test_append_template_can_print_json_report(tmp_path, capsys) -> None:
    path = tmp_path / "read-dogfood.jsonl"

    assert main(["--template", "live", "--append", str(path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["total_sessions"] == 1
    assert report["valid_sessions"] == 1
    assert report["live_provider_sessions"] == 1
    assert report["remaining_requirements"]["valid_sessions"] == 9


def test_append_requires_template(tmp_path) -> None:
    path = tmp_path / "read-dogfood.jsonl"

    try:
        main(["--append", str(path)])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("--append without --template did not fail")


def test_activation_spec_minimal_record_shape_is_validator_compatible() -> None:
    spec_path = Path("specs/activation/golden-path.md")
    spec = spec_path.read_text(encoding="utf-8")
    match = re.search(r"Minimal record shape:\n\n```json\n(?P<json>.*?)\n```", spec, re.S)
    assert match is not None

    record = json.loads(match.group("json"))
    report = validate_sessions([record])

    assert report.valid_sessions == 1
    assert all(failure.startswith("closure requires ") for failure in report.failures)
    assert not any("missing required fields" in failure for failure in report.failures)
