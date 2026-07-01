import json

from compounding.verification.open_weight_justification import (
    audit_open_weight_justification,
    format_text,
    main,
)


def _long_justification() -> str:
    paragraph = (
        "Decision: deploy open-weight Antiek model routing only if measured evidence "
        "shows that open-weight routing is necessary. The argument must compare "
        "closed-weight dispatch against the proposed open-weight path and must "
        "name the specific deployment reason, the metric, the measurement date, "
        "and the source artifact. "
    )
    return "# Loop 3 Open-Weight Justification\n\n" + paragraph * 18


def test_open_weight_justification_fails_with_placeholders(tmp_path):
    justification = tmp_path / "missing.md"
    measurements = tmp_path / "open-weight-justification.json"
    measurements.write_text(json.dumps({"measurements": {}}), encoding="utf-8")

    result = audit_open_weight_justification(
        justification_path=justification,
        measurements_path=measurements,
    )

    assert result.status == "FAIL"
    assert result.measured_categories == []
    assert "loop3_unlocked_by_this_probe: no" in format_text(result)


def test_open_weight_justification_passes_with_one_measured_category(tmp_path):
    justification = tmp_path / "justification.md"
    justification.write_text(_long_justification(), encoding="utf-8")
    measurements = tmp_path / "open-weight-justification.json"
    measurements.write_text(
        json.dumps(
            {
                "measurements": {
                    "cost": {
                        "metric": "monthly_token_cost_delta_usd",
                        "closed_weight_monthly_usd": 2750.0,
                        "open_weight_monthly_usd": 930.0,
                        "measured_at": "2026-07-01T00:00:00Z",
                        "source": "reports/loop3/cost-benchmark-20260701.json",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = audit_open_weight_justification(
        justification_path=justification,
        measurements_path=measurements,
    )

    assert result.status == "PASS"
    assert result.measured_categories == ["cost"]
    assert result.justification_word_count >= 350


def test_open_weight_justification_rejects_assertion_only_measurement(tmp_path):
    justification = tmp_path / "justification.md"
    justification.write_text(_long_justification(), encoding="utf-8")
    measurements = tmp_path / "open-weight-justification.json"
    measurements.write_text(
        json.dumps(
            {
                "measurements": {
                    "latency": {
                        "metric": "p95_latency",
                        "measured_at": "2026-07-01T00:00:00Z",
                        "source": "reports/loop3/latency.md",
                        "notes": "faster in practice",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = audit_open_weight_justification(
        justification_path=justification,
        measurements_path=measurements,
    )

    assert result.status == "FAIL"
    assert result.measured_categories == []


def test_open_weight_justification_rejects_arbitrary_numeric_field(tmp_path):
    justification = tmp_path / "justification.md"
    justification.write_text(_long_justification(), encoding="utf-8")
    measurements = tmp_path / "open-weight-justification.json"
    measurements.write_text(
        json.dumps(
            {
                "measurements": {
                    "cost": {
                        "metric": "monthly_token_cost_delta_usd",
                        "foo": 1.0,
                        "measured_at": "2026-07-01T00:00:00Z",
                        "source": "reports/loop3/cost.json",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert audit_open_weight_justification(
        justification_path=justification,
        measurements_path=measurements,
    ).status == "FAIL"


def test_open_weight_justification_rejects_negative_decision_marker(tmp_path):
    justification = tmp_path / "justification.md"
    text = (
        "# Loop 3 Open-Weight Justification\n\n"
        "Decision: do not deploy open-weight routing. "
        + "This document mentions open-weight but rejects the deployment. " * 80
    )
    justification.write_text(text, encoding="utf-8")
    measurements = tmp_path / "open-weight-justification.json"
    measurements.write_text(
        json.dumps(
            {
                "measurements": {
                    "capability": {
                        "metric": "section_d_eval_score",
                        "closed_weight_eval_score": 0.81,
                        "open_weight_eval_score": 0.86,
                        "measured_at": "2026-07-01T00:00:00Z",
                        "source": "reports/loop3/section-d-eval.json",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = audit_open_weight_justification(
        justification_path=justification,
        measurements_path=measurements,
    )

    assert result.status == "FAIL"
    assert any(
        check["name"] == "justification_has_decision_marker" and not check["passed"]
        for check in result.checks
    )


def test_open_weight_justification_accepts_policy_control_key(tmp_path):
    justification = tmp_path / "justification.md"
    justification.write_text(_long_justification(), encoding="utf-8")
    measurements = tmp_path / "open-weight-justification.json"
    measurements.write_text(
        json.dumps(
            {
                "measurements": {
                    "policy_control": {
                        "metric": "blocked_closed_weight_routes",
                        "blocked_closed_weight_routes": 17,
                        "measured_at": "2026-07-01T00:00:00Z",
                        "source": "reports/loop3/policy-control.json",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = audit_open_weight_justification(
        justification_path=justification,
        measurements_path=measurements,
    )

    assert result.status == "PASS"
    assert result.measured_categories == ["policy_control"]


def test_open_weight_justification_rejects_policy_slash_control_key(tmp_path):
    justification = tmp_path / "justification.md"
    justification.write_text(_long_justification(), encoding="utf-8")
    measurements = tmp_path / "open-weight-justification.json"
    measurements.write_text(
        json.dumps(
            {
                "measurements": {
                    "policy/control": {
                        "metric": "blocked_closed_weight_routes",
                        "blocked_closed_weight_routes": 17,
                        "measured_at": "2026-07-01T00:00:00Z",
                        "source": "reports/loop3/policy-control.json",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = audit_open_weight_justification(
        justification_path=justification,
        measurements_path=measurements,
    )

    assert result.status == "FAIL"
    assert result.measured_categories == []


def test_cli_returns_nonzero_until_justification_exists(tmp_path, capsys):
    measurements = tmp_path / "open-weight-justification.json"
    measurements.write_text(json.dumps({"measurements": {}}), encoding="utf-8")

    exit_code = main([
        "--justification",
        str(tmp_path / "missing.md"),
        "--measurements",
        str(measurements),
    ])

    assert exit_code == 1
    assert "loop3-open-weight-justification: FAIL" in capsys.readouterr().out
