"""Readiness audit tests for Autoresearch Wedge 1."""

from __future__ import annotations

import json
from pathlib import Path

from tools.golden_traces import GoldenTrace, RoleCall, stable_json_hash
from tools.prompt_autoresearch import (
    audit_wedge1_readiness,
    render_readiness_markdown,
)


def test_wedge1_readiness_reports_current_tree_honestly():
    report = audit_wedge1_readiness(Path("."))
    statuses = {item.id: item.status for item in report.items}

    assert report.all_satisfied is False
    assert statuses["program"] == "operator_bound"
    assert statuses["tooling"] == "satisfied"
    assert statuses["calibration"] == "operator_bound"
    assert statuses["golden_traces"] == "operator_bound"
    assert statuses["budget"] == "satisfied"
    assert statuses["local_only"] == "satisfied"


def test_wedge1_readiness_markdown_names_operator_bound_items():
    report = audit_wedge1_readiness(Path("."))

    md = render_readiness_markdown(report)

    assert "# Prompt autoresearch Wedge 1 readiness" in md
    assert "`operator_bound`" in md
    assert "`golden_traces`" in md


def test_wedge1_readiness_cli_json_shape(capsys):
    from tools.prompt_autoresearch.readiness_cli import main

    rc = main(["--repo-root", ".", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["all_satisfied"] is False
    assert {item["id"] for item in payload["items"]} == {
        "program",
        "tooling",
        "calibration",
        "golden_traces",
        "budget",
        "local_only",
    }


def test_wedge1_readiness_counts_only_loadable_golden_traces(tmp_path):
    captured = tmp_path / "tools/golden_traces/captured"
    captured.mkdir(parents=True)
    for index in range(4):
        _write_valid_trace(captured / f"valid-{index}.json", index)
    (captured / "broken.json").write_text("{not-json", encoding="utf-8")

    report = audit_wedge1_readiness(tmp_path)
    golden = next(item for item in report.items if item.id == "golden_traces")

    assert golden.status == "operator_bound"
    assert "4 loadable golden trace(s)" in golden.evidence
    assert "invalid trace file(s): tools/golden_traces/captured/broken.json" in golden.evidence

    _write_valid_trace(captured / "valid-4.json", 4)

    report = audit_wedge1_readiness(tmp_path)
    golden = next(item for item in report.items if item.id == "golden_traces")

    assert golden.status == "satisfied"
    assert "5 loadable golden trace(s)" in golden.evidence


def _write_valid_trace(path: Path, index: int) -> None:
    input_payload = {"question": f"question-{index}"}
    output_payload = {"answer": f"answer-{index}"}
    trace = GoldenTrace(
        trace_id=f"trace-{index}",
        captured_at="2026-07-01T00:00:00Z",
        investigation_id=f"investigation-{index}",
        target_question=f"Question {index}?",
        role_calls=[
            RoleCall(
                sequence_index=0,
                role="decomposer",
                input_json=input_payload,
                output_json=output_payload,
                input_hash=stable_json_hash(input_payload),
                output_hash=stable_json_hash(output_payload),
            )
        ],
    )
    path.write_text(trace.model_dump_json(), encoding="utf-8")
