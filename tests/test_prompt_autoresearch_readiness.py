"""Readiness audit tests for Autoresearch Wedge 1."""

from __future__ import annotations

import json
from pathlib import Path

from tools.golden_traces import GoldenTrace, RoleCall, stable_json_hash
from tools.prompt_autoresearch import (
    CalibrationReport,
    ReadinessItem,
    ReadinessReport,
    audit_wedge1_readiness,
    render_calibration_markdown,
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


def test_wedge1_readiness_markdown_escapes_table_cells():
    report = ReadinessReport(
        items=[
            ReadinessItem(
                id="golden|traces",
                label="unused label",
                status="operator|bound",
                evidence="tools/golden_traces/captured/broken|trace.json\nneeds review",
            )
        ]
    )

    md = render_readiness_markdown(report)

    assert "`golden\\|traces`" in md
    assert "`operator\\|bound`" in md
    assert "broken\\|trace.json needs review" in md
    assert "broken|trace.json" not in md


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


def test_wedge1_readiness_cli_rejects_missing_repo_root(tmp_path, capsys):
    from tools.prompt_autoresearch.readiness_cli import main

    missing_root = tmp_path / "missing"

    rc = main(["--repo-root", str(missing_root)])

    captured = capsys.readouterr()
    assert rc == 2
    assert "must be an existing directory" in captured.err
    assert str(missing_root) in captured.err


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


def test_wedge1_readiness_requires_generated_calibration_report(tmp_path):
    calibration_path = tmp_path / "reports/autoresearch/synthesizer-calibration.md"
    calibration_path.parent.mkdir(parents=True)
    calibration_path.write_text("operator note only\n", encoding="utf-8")

    report = audit_wedge1_readiness(tmp_path)
    calibration = next(item for item in report.items if item.id == "calibration")

    assert calibration.status == "operator_bound"
    assert "exists but is not a generated calibration report" in calibration.evidence

    calibration_path.write_text(
        render_calibration_markdown(
            CalibrationReport(
                role="synthesizer",
                iteration_count=5,
                mean_delta=0.0,
                sigma=0.01,
                two_sigma=0.02,
                floor_epsilon=0.05,
                recommended_epsilon=0.05,
                rationale="test calibration report",
            )
        ),
        encoding="utf-8",
    )

    report = audit_wedge1_readiness(tmp_path)
    calibration = next(item for item in report.items if item.id == "calibration")

    assert calibration.status == "satisfied"
    assert "contains calibration summary fields" in calibration.evidence


def test_wedge1_readiness_requires_operator_program_review_note(tmp_path):
    program_path = tmp_path / "roles/synthesizer/program.md"
    program_path.parent.mkdir(parents=True)
    program_path.write_text(
        "Voice discipline and style discipline for synthesizer.\n",
        encoding="utf-8",
    )
    review_path = tmp_path / "reports/autoresearch/synthesizer-program-review.md"
    review_path.parent.mkdir(parents=True)

    report = audit_wedge1_readiness(tmp_path)
    program = next(item for item in report.items if item.id == "program")

    assert program.status == "operator_bound"
    assert "synthesizer-program-review.md" in program.evidence

    review_path.write_text("reviewed informally\n", encoding="utf-8")

    report = audit_wedge1_readiness(tmp_path)
    program = next(item for item in report.items if item.id == "program")

    assert program.status == "operator_bound"
    assert "does not record the required operator review fields" in program.evidence

    review_path.write_text(
        "\n".join(
            [
                "# Synthesizer program review",
                "",
                "- Reviewer: Operator",
                "- Reviewed_at: 2026-07-01T00:00:00Z",
                "- Verdict: operator_approved",
                "- Reviewed artifact: roles/synthesizer/program.md",
                "",
            ]
        ),
        encoding="utf-8",
    )

    report = audit_wedge1_readiness(tmp_path)
    program = next(item for item in report.items if item.id == "program")

    assert program.status == "satisfied"
    assert "records operator review" in program.evidence


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
