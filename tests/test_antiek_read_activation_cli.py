"""Top-level Antiek Read activation CLI tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from antiek.cli import main
from tools.activation.read_dogfood import (
    REQUIRED_CITATION_TRACE_SESSIONS,
    REQUIRED_LIVE_PROVIDER_SESSIONS,
    REQUIRED_NON_LIBRARY_SESSIONS,
    REQUIRED_VALID_SESSIONS,
    load_jsonl,
)


def _session(
    idx: int,
    *,
    live: bool,
    citation: bool,
    entry_door: str,
) -> dict[str, Any]:
    steps: dict[str, dict[str, Any]] = {
        "1": {
            "status": "pass",
            "visible_content_note": "Visible heading/table/math/figure.",
        },
        "2": {
            "status": "pass",
            "selected_text": "Exact selected passage text.",
            "menu_labels": ["Note", "Dialogue", "Search", "Deep-research"],
        },
        "3": {"status": "pass" if live else "inert"},
        "4": {"status": "pass" if live else "inert"},
        "5": {"status": "pass"},
        "6": {
            "status": "pass",
            "return_context_note": "Returned to the same reading context.",
        },
        "7": {
            "status": "pass",
            "operator_note": "Read for 20+ minutes; no blocking friction.",
        },
    }
    if live:
        steps["3"]["first_answer"] = f"First useful answer for passage {idx}."
        steps["4"]["investigation_id"] = f"child-investigation-{idx}"
    else:
        steps["3"]["exact_no_key_copy"] = "Dialogue requires provider activation keys."
        steps["4"]["exact_no_key_copy"] = "Research spin-out requires provider activation keys."
    if citation:
        steps["5"].update(
            {
                "source_document_id": f"source-doc-{idx}",
                "chunk_id": f"chunk-{idx}",
                "result_url": (
                    f"https://app.example/read/source-doc-{idx}"
                    f"?chunk=chunk-{idx}&from=doc-{idx}&fromPage=0"
                ),
            }
        )
    return {
        "session_id": f"session-{idx}",
        "date": "2026-06-30",
        "build_sha": "0123456789abcdef",
        "url": f"https://app.example/read/doc-{idx}",
        "operator": "operator",
        "document_id": f"doc-{idx}",
        "entry_door": entry_door,
        "provider_status": "ready" if live else "absent",
        "live_provider_ai": live,
        "citation_traced": citation,
        "minutes_reading": 22,
        "steps": steps,
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def test_antiek_read_activation_status_reports_missing_log(
    tmp_path: Path,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    log_path = tmp_path / "missing-read-dogfood.jsonl"

    rc = main(["read", "activation", "status", "--log", str(log_path)])

    assert rc == 1
    out = capsys.readouterr().out
    assert f"source: {log_path}" in out
    assert "state: not_started" in out
    assert "closure_ready: false" in out
    assert f"valid sessions: 0/{REQUIRED_VALID_SESSIONS}" in out
    assert f"live provider sessions: 0/{REQUIRED_LIVE_PROVIDER_SESSIONS}" in out
    assert f"citation trace sessions: 0/{REQUIRED_CITATION_TRACE_SESSIONS}" in out
    assert f"non-library sessions: 0/{REQUIRED_NON_LIBRARY_SESSIONS}" in out
    assert "final verdict: missing" in out
    assert f"remaining: valid_sessions={REQUIRED_VALID_SESSIONS}" in out


def test_antiek_read_activation_status_json_is_scriptable(
    tmp_path: Path,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    log_path = tmp_path / "read-dogfood.jsonl"
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library") for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"
    records[-1]["verdict"] = "ACTIVATE"
    _write_jsonl(log_path, records)

    rc = main(["read", "activation", "status", "--log", str(log_path), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    view = payload["view"]
    assert view["source_path"] == str(log_path)
    assert view["state"] == "ready"
    assert view["closure_ready"] is True
    assert view["valid_sessions"] == 10
    assert view["required_counts"] == {
        "valid_sessions": REQUIRED_VALID_SESSIONS,
        "live_provider_sessions": REQUIRED_LIVE_PROVIDER_SESSIONS,
        "citation_trace_sessions": REQUIRED_CITATION_TRACE_SESSIONS,
        "non_library_sessions": REQUIRED_NON_LIBRARY_SESSIONS,
    }
    assert view["remaining_requirements"] == {
        "valid_sessions": 0,
        "live_provider_sessions": 0,
        "citation_trace_sessions": 0,
        "non_library_sessions": 0,
    }


def test_antiek_read_activation_append_template_creates_operator_log(
    tmp_path: Path,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    log_path = tmp_path / "operator" / "read-dogfood.jsonl"

    rc = main(
        [
            "read",
            "activation",
            "append-template",
            "--kind",
            "live-citation",
            "--log",
            str(log_path),
        ]
    )

    assert rc == 0
    records = load_jsonl(log_path)
    assert len(records) == 1
    assert records[0]["live_provider_ai"] is True
    assert records[0]["citation_traced"] is True
    assert records[0]["entry_door"] == "command_palette"
    out = capsys.readouterr().out
    assert "appended template: live-citation" in out
    assert f"log: {log_path}" in out
    assert "state: incomplete" in out
    assert "valid sessions: 0/10 (1 total, 1 invalid)" in out
    assert (
        "failure: 2026-06-30-operator-001: live provider step 3 still has template first_answer"
        in out
    )
    assert "failure: 2026-06-30-operator-001: citation step 5 still has template result_url" in out


def test_antiek_read_activation_append_template_json_reports_post_append_status(
    tmp_path: Path,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    log_path = tmp_path / "read-dogfood.jsonl"

    rc = main(
        [
            "read",
            "activation",
            "append-template",
            "--kind",
            "write-trace-citation",
            "--log",
            str(log_path),
            "--json",
        ]
    )

    assert rc == 0
    records = load_jsonl(log_path)
    assert len(records) == 1
    assert records[0]["entry_door"] == "write_trace_to_source"
    assert "from=" not in records[0]["steps"]["5"]["result_url"]
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["appended_template"] == "write-trace-citation"
    assert payload["log_path"] == str(log_path)
    view = payload["view"]
    assert view["source_path"] == str(log_path)
    assert view["state"] == "incomplete"
    assert view["total_sessions"] == 1
    assert view["valid_sessions"] == 0
    assert view["closure_ready"] is False
    assert any("template result_url" in failure for failure in view["failures"])


def test_antiek_read_activation_record_session_json_appends_valid_evidence(
    tmp_path: Path,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    log_path = tmp_path / "read-dogfood.jsonl"

    rc = main(
        [
            "read",
            "activation",
            "record-session",
            "--log",
            str(log_path),
            "--session-id",
            "session-1",
            "--date",
            "2026-07-03",
            "--build-sha",
            "0123456789abcdef",
            "--url",
            "https://app.example/read/doc-1",
            "--operator",
            "operator",
            "--document-id",
            "doc-1",
            "--entry-door",
            "command_palette",
            "--minutes-reading",
            "24",
            "--visible-content-note",
            "Structured heading and table were visible.",
            "--selected-text",
            "The exact highlighted passage.",
            "--return-context-note",
            "Back returned to the same passage.",
            "--operator-note",
            "Read for 24 minutes without blocking friction.",
            "--live-provider-ai",
            "--first-answer",
            "A useful live answer grounded in the selected passage.",
            "--investigation-id",
            "investigation-1",
            "--citation-traced",
            "--source-document-id",
            "source-doc-1",
            "--chunk-id",
            "chunk-1",
            "--result-url",
            "https://app.example/read/source-doc-1?chunk=chunk-1&from=doc-1",
            "--json",
        ]
    )

    assert rc == 0
    records = load_jsonl(log_path)
    assert len(records) == 1
    assert records[0]["session_id"] == "session-1"
    assert records[0]["live_provider_ai"] is True
    assert records[0]["citation_traced"] is True
    assert records[0]["steps"]["2"]["menu_labels"] == [
        "Note",
        "Dialogue",
        "Search",
        "Deep-research",
    ]
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["recorded_session_id"] == "session-1"
    assert payload["log_path"] == str(log_path)
    view = payload["view"]
    assert view["state"] == "incomplete"
    assert view["total_sessions"] == 1
    assert view["valid_sessions"] == 1
    assert view["invalid_session_count"] == 0
    assert view["live_provider_sessions"] == 1
    assert view["citation_trace_sessions"] == 1
    assert view["non_library_sessions"] == 1


def test_antiek_read_activation_record_session_rejects_incomplete_live_evidence(
    tmp_path: Path,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    log_path = tmp_path / "read-dogfood.jsonl"

    rc = main(
        [
            "read",
            "activation",
            "record-session",
            "--log",
            str(log_path),
            "--session-id",
            "session-1",
            "--date",
            "2026-07-03",
            "--build-sha",
            "0123456789abcdef",
            "--url",
            "https://app.example/read/doc-1",
            "--operator",
            "operator",
            "--document-id",
            "doc-1",
            "--entry-door",
            "command_palette",
            "--minutes-reading",
            "24",
            "--visible-content-note",
            "Structured heading and table were visible.",
            "--selected-text",
            "The exact highlighted passage.",
            "--return-context-note",
            "Back returned to the same passage.",
            "--operator-note",
            "Read for 24 minutes without blocking friction.",
            "--live-provider-ai",
        ]
    )

    assert rc == 2
    assert not log_path.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "record-session: first_answer is required" in captured.err


def test_antiek_read_activation_next_session_recommends_citation_for_missing_log(
    tmp_path: Path,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    log_path = tmp_path / "missing-read-dogfood.jsonl"

    rc = main(["read", "activation", "next-session", "--log", str(log_path)])

    assert rc == 0
    out = capsys.readouterr().out
    assert f"source: {log_path}" in out
    assert "state: not_started" in out
    assert "next action: collect_session" in out
    assert "recommended template: live-citation" in out
    assert "append command: antiek read activation append-template --kind live-citation" in out
    assert f"remaining: valid_sessions={REQUIRED_VALID_SESSIONS}" in out


def test_antiek_read_activation_next_session_json_prioritizes_live_gap(
    tmp_path: Path,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    log_path = tmp_path / "read-dogfood.jsonl"
    records = [
        _session(i, live=True, citation=i <= 3, entry_door="library") for i in range(1, 5)
    ]
    records[0]["entry_door"] = "command_palette"
    _write_jsonl(log_path, records)

    rc = main(["read", "activation", "next-session", "--log", str(log_path), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["state"] == "incomplete"
    assert payload["recommended_template"] == "live"
    assert payload["append_command"] == "antiek read activation append-template --kind live"
    assert payload["remaining_requirements"]["live_provider_sessions"] == 1
    assert payload["remaining_requirements"]["citation_trace_sessions"] == 0
    assert payload["remaining_requirements"]["non_library_sessions"] == 0
    assert payload["view"]["source_path"] == str(log_path)


def test_antiek_read_activation_next_session_stops_when_only_verdict_missing(
    tmp_path: Path,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    log_path = tmp_path / "read-dogfood.jsonl"
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library") for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"
    _write_jsonl(log_path, records)

    rc = main(["read", "activation", "next-session", "--log", str(log_path), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["next_action"] == "fix_log"
    assert payload["recommended_template"] is None
    assert payload["append_command"] is None
    assert payload["remaining_requirements"] == {
        "valid_sessions": 0,
        "live_provider_sessions": 0,
        "citation_trace_sessions": 0,
        "non_library_sessions": 0,
    }
    assert "final verdict" in payload["rationale"]


def test_antiek_read_activation_next_session_ready_has_no_recommendation(
    tmp_path: Path,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    log_path = tmp_path / "read-dogfood.jsonl"
    records = [
        _session(i, live=i <= 5, citation=i <= 3, entry_door="library") for i in range(1, 11)
    ]
    records[-1]["entry_door"] = "command_palette"
    records[-1]["verdict"] = "ACTIVATE"
    _write_jsonl(log_path, records)

    rc = main(["read", "activation", "next-session", "--log", str(log_path), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "ready"
    assert payload["next_action"] == "none"
    assert payload["recommended_template"] is None
    assert payload["view"]["closure_ready"] is True


def test_antiek_read_activation_next_session_rejects_malformed_log(
    tmp_path: Path,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    log_path = tmp_path / "read-dogfood.jsonl"
    log_path.write_text("{bad json\n", encoding="utf-8")

    rc = main(["read", "activation", "next-session", "--log", str(log_path), "--json"])

    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "invalid_log"
    assert payload["next_action"] == "fix_log"
    assert payload["recommended_template"] is None
    assert "malformed JSONL" in payload["rationale"]
