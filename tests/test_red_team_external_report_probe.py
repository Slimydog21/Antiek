from __future__ import annotations

import json

from tools.ops import red_team_external_report_probe


def _external_report() -> str:
    return """# Sprint 23-24 — Anti-Gaming Layer Red-Team Report

**Status:** Filed by external red-team.

**Author:** Example Security Labs

**Reviewed:** 2026-07-01

**Substrate version under review:** abc123def

## §1 Scope and binding posture

External red-team review of `substrate/anti_gaming/` and
`tools/stripe_connect/payouts.py`; all attacks are evaluated pre-payout.

## §2 Attack classes the layer must catch

### Attack class A — Botnet view inflation

**Observed result:** BLOCK verdict, payout_blocked audit rows, zero transfers.

**Verdict:** PASS

### Attack class B — Attribution-graph injection

**Observed result:** REVIEW verdict with deep_attribution_chain; zero transfers.

**Verdict:** PASS

### Attack class C — Multi-account self-attribution

**Observed result:** REVIEW verdict with single_consumer_dominance; zero transfers.

**Verdict:** PASS

### Attack class D (optional but recommended) — Creator-cluster collusion

**Observed result:** REVIEW verdict with cluster_collusion; ring members queued.

**Verdict:** PASS

## §3 Calibration sensitivity

**Observed FP rate:** 0.00 review, 0.00 block
**Observed detection latency:** 14 seconds

## §4 Closing verdict

**All four attack classes caught pre-payout?** YES

**False-positive rate within target?** YES

**Detection latency within target?** YES

**Recommended go/no-go for Sprint 23-24 ship:** GO
"""


def test_red_team_external_report_probe_passes_complete_external_report(tmp_path):
    report = tmp_path / "docs/sprint23_red_team.md"
    report.parent.mkdir(parents=True)
    report.write_text(_external_report(), encoding="utf-8")

    result = red_team_external_report_probe.probe_red_team_external_report(report)

    assert result.status == "PASS"
    assert result.author_present is True
    assert result.reviewed_date_present is True
    assert result.substrate_version_present is True
    assert result.does_not_close_oa008 is True


def test_red_team_external_report_probe_fails_template_report():
    result = red_team_external_report_probe.probe_red_team_external_report()

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["report_file_exists"].passed is True
    assert checks["no_template_placeholders"].passed is False
    assert checks["internal_baseline_go"].passed is True


def test_red_team_external_report_probe_fails_missing_attack_verdict(tmp_path):
    report = tmp_path / "report.md"
    report.write_text(
        _external_report().replace("**Verdict:** PASS", "**Verdict:** FAIL", 1),
        encoding="utf-8",
    )

    result = red_team_external_report_probe.probe_red_team_external_report(report)

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["A_botnet_view_inflation_verdict_pass"].passed is False


def test_red_team_external_report_probe_fails_no_go(tmp_path):
    report = tmp_path / "report.md"
    report.write_text(
        _external_report().replace(
            "**Recommended go/no-go for Sprint 23-24 ship:** GO",
            "**Recommended go/no-go for Sprint 23-24 ship:** NO-GO",
        ),
        encoding="utf-8",
    )

    result = red_team_external_report_probe.probe_red_team_external_report(report)

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["recommended_go"].passed is False


def test_red_team_external_report_probe_json_cli(tmp_path, capsys):
    report = tmp_path / "report.md"
    report.write_text(_external_report(), encoding="utf-8")

    exit_code = red_team_external_report_probe.main([
        "--report-path",
        str(report),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["does_not_close_oa008"] is True
