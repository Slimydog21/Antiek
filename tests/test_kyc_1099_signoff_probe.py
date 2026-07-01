from __future__ import annotations

import json

from substrate.billing.kyc import KYC_PAYOUT_FLOOR_USD_CENTS
from substrate.billing.tax_reports import IRS_1099_NEC_THRESHOLD_USD_CENTS
from tools.ops import kyc_1099_signoff_probe


def _signoff_doc() -> str:
    return """# OA-017 KYC + 1099 Counsel Signoff

**Counsel:** Jane Example

**Firm:** Example Tax LLP

**Signed:** 2026-07-01

## Scope

Counsel reviewed US tax, KYC, 1099, and Terms of Service posture for creator
accounts. The review covered Stripe Connect onboarding and the substrate
contracts in `substrate/billing/kyc.py` and `substrate/billing/tax_reports.py`.

## Thresholds

The KYC payout floor is $10.00. The IRS 1099-NEC reporting threshold is
$600.00 for annual non-employee compensation.
"""


def test_kyc_1099_signoff_probe_passes_complete_artifact(tmp_path):
    path = tmp_path / "docs/decisions/oa-017-kyc-1099-signoff.md"
    path.parent.mkdir(parents=True)
    path.write_text(_signoff_doc(), encoding="utf-8")

    result = kyc_1099_signoff_probe.probe_kyc_1099_signoff(path)

    checks = {check.name: check for check in result.checks}
    assert result.status == "PASS"
    assert result.counsel_name_present is True
    assert result.firm_present is True
    assert result.signed_date_present is True
    assert result.kyc_payout_floor_usd_cents == KYC_PAYOUT_FLOOR_USD_CENTS
    assert result.irs_1099_nec_threshold_usd_cents == (
        IRS_1099_NEC_THRESHOLD_USD_CENTS
    )
    assert checks["above_floor_requires_kyc"].passed is True
    assert checks["completed_kyc_allows_above_floor"].passed is True
    assert result.does_not_close_oa017 is True


def test_kyc_1099_signoff_probe_fails_missing_artifact_but_checks_gate(tmp_path):
    result = kyc_1099_signoff_probe.probe_kyc_1099_signoff(
        tmp_path / "missing.md",
    )

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["signoff_file_exists"].passed is False
    assert checks["kyc_floor_rollover_allowed"].passed is True
    assert checks["above_floor_requires_kyc"].passed is True


def test_kyc_1099_signoff_probe_fails_missing_counsel_fields(tmp_path):
    path = tmp_path / "signoff.md"
    path.write_text(
        _signoff_doc().replace("**Counsel:** Jane Example\n\n", ""),
        encoding="utf-8",
    )

    result = kyc_1099_signoff_probe.probe_kyc_1099_signoff(path)

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["counsel_name_present"].passed is False


def test_kyc_1099_signoff_probe_fails_missing_thresholds(tmp_path):
    path = tmp_path / "signoff.md"
    path.write_text(
        _signoff_doc()
        .replace("The KYC payout floor is $10.00. ", "")
        .replace(
            "The IRS 1099-NEC reporting threshold is\n$600.00 for annual "
            "non-employee compensation.",
            "",
        ),
        encoding="utf-8",
    )

    result = kyc_1099_signoff_probe.probe_kyc_1099_signoff(path)

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["kyc_payout_floor_named"].passed is False
    assert checks["irs_1099_threshold_named"].passed is False


def test_kyc_1099_signoff_probe_json_cli(tmp_path, capsys):
    path = tmp_path / "signoff.md"
    path.write_text(_signoff_doc(), encoding="utf-8")

    exit_code = kyc_1099_signoff_probe.main([
        "--signoff-path",
        str(path),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["does_not_close_oa017"] is True
