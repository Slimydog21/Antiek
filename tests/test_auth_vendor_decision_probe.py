from __future__ import annotations

import json

from tools.ops import auth_vendor_decision_probe


def _decision_doc(vendor: str = "Clerk") -> str:
    return f"""# OA-006 Auth Vendor Decision

**Status:** Filed.

**Author:** operator

**Decided:** 2026-07-01

**Decision: {vendor}**

**Sign-up date: 2026-07-01**

## Rationale

The selected vendor owns OAuth providers, hosted identity, and session
bootstrap. The downstream Antiek boundary remains the trusted external-claims
adapter in `interfaces/research/api/app.py`.

## Integration checklist

1. Sign up to the selected vendor account.
2. Configure OAuth providers.
3. Wire the callback endpoint into `interfaces/research/api/app.py`.
4. Add the session middleware.
5. Wire the sign-up/sign-in UI into `apps/reading/src/modes/Login/`.

## Trusted claims boundary

The HTTP adapter verifies issuer, audience, expiry, and key-rotation before
handing already-verified claims to
`substrate.multi_user.auth.normalize_verified_claims()`. The origin hop is
protected with `ANTIEK_EXTERNAL_AUTH_VENDOR`,
`ANTIEK_EXTERNAL_AUTH_HEADER_SECRET`, and `X-Antiek-Verified-Claims`.

## Rollback

Rollback disables the external-auth environment variables and returns traffic
to existing operator auth while preserving the filed vendor namespace.
"""


def test_auth_vendor_decision_probe_passes_complete_clerk_decision(tmp_path):
    decision = tmp_path / "docs/decisions/oa-006-auth-vendor.md"
    decision.parent.mkdir(parents=True)
    decision.write_text(_decision_doc("Clerk"), encoding="utf-8")

    result = auth_vendor_decision_probe.probe_auth_vendor_decision(decision)

    assert result.status == "PASS"
    assert result.decision == "Clerk"
    assert result.signup_date == "2026-07-01"
    assert result.does_not_close_oa006 is True


def test_auth_vendor_decision_probe_passes_complete_supabase_decision(tmp_path):
    decision = tmp_path / "decision.md"
    decision.write_text(_decision_doc("Supabase"), encoding="utf-8")

    result = auth_vendor_decision_probe.probe_auth_vendor_decision(decision)

    assert result.status == "PASS"
    assert result.decision == "Supabase"


def test_auth_vendor_decision_probe_fails_missing_decision_file(tmp_path):
    result = auth_vendor_decision_probe.probe_auth_vendor_decision(
        tmp_path / "missing.md",
    )

    assert result.status == "FAIL"
    assert result.checks[0].name == "decision_file_exists"


def test_auth_vendor_decision_probe_fails_non_binary_vendor(tmp_path):
    decision = tmp_path / "decision.md"
    decision.write_text(_decision_doc("Homegrown"), encoding="utf-8")

    result = auth_vendor_decision_probe.probe_auth_vendor_decision(decision)

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["vendor_choice_binary"].passed is False


def test_auth_vendor_decision_probe_fails_missing_security_boundary(tmp_path):
    decision = tmp_path / "decision.md"
    decision.write_text(
        _decision_doc().replace("issuer, audience, expiry, and key-rotation", ""),
        encoding="utf-8",
    )

    result = auth_vendor_decision_probe.probe_auth_vendor_decision(decision)

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["security_boundary_covered"].passed is False
    assert "issuer" in checks["security_boundary_covered"].detail


def test_auth_vendor_decision_probe_json_cli(tmp_path, capsys):
    decision = tmp_path / "decision.md"
    decision.write_text(_decision_doc("Supabase"), encoding="utf-8")

    exit_code = auth_vendor_decision_probe.main([
        "--decision-path",
        str(decision),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["decision"] == "Supabase"
    assert payload["does_not_close_oa006"] is True
