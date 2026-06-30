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

    report = validate_sessions(records)

    assert report.closure_ready is True
    assert report.valid_sessions == 10
    assert report.live_provider_sessions == 5
    assert report.citation_trace_sessions == 10  # step 5 passed in every session
    assert report.non_library_sessions == 1
    assert report.failures == ()


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
    assert any("step 7 has failure/irritation without followup_issue" in f for f in report.failures)


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
