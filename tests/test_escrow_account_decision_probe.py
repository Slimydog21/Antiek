from __future__ import annotations

import json

from tools.ops import escrow_account_decision_probe


def _decision_doc() -> str:
    return """# OA-014 Segregated Escrow Account

**Status:** Filed.

**Author:** operator

**Decided:** 2026-07-01

**Segregated account ref:** prod-secret://antiek/escrow/ip-holder-account

## Institution

The operator opened a segregated regulated escrow account at a fiduciary
institution. Funds are mechanically not commingled with operating cash.

## Production wiring

The production secret ref is injected as `segregated_account_ref` for
`RevSharePayoutRouter`. The guard in `StripeOperationsLog` and
`tools/stripe_connect/accounts.py` remains the payout completion boundary.

## Closure artifact

This file is `docs/decisions/oa-014-escrow-account.md`.
"""


def test_escrow_account_decision_probe_passes_complete_decision(tmp_path):
    decision = tmp_path / "docs/decisions/oa-014-escrow-account.md"
    decision.parent.mkdir(parents=True)
    decision.write_text(_decision_doc(), encoding="utf-8")

    result = escrow_account_decision_probe.probe_escrow_account_decision(decision)

    checks = {check.name: check for check in result.checks}
    assert result.status == "PASS"
    assert result.account_ref_present is True
    assert checks["missing_segregated_ref_escrows"].passed is True
    assert checks["missing_segregated_ref_blocks_transfer"].passed is True
    assert result.does_not_close_oa014 is True


def test_escrow_account_decision_probe_fails_missing_decision_but_checks_guard(tmp_path):
    result = escrow_account_decision_probe.probe_escrow_account_decision(
        tmp_path / "missing.md",
    )

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["decision_file_exists"].passed is False
    assert checks["missing_segregated_ref_escrows"].passed is True
    assert checks["missing_segregated_ref_blocks_transfer"].passed is True


def test_escrow_account_decision_probe_fails_missing_fragments(tmp_path):
    decision = tmp_path / "decision.md"
    decision.write_text(
        """# OA-014

**Author:** operator

**Decided:** 2026-07-01

**Segregated account ref:** prod-secret://antiek/escrow/ip-holder-account
""",
        encoding="utf-8",
    )

    result = escrow_account_decision_probe.probe_escrow_account_decision(decision)

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["decision_required_fragments"].passed is False
    assert "fiduciary institution" in checks["decision_required_fragments"].detail


def test_escrow_account_decision_probe_fails_without_account_ref(tmp_path):
    decision = tmp_path / "decision.md"
    decision.write_text(
        _decision_doc().replace(
            "**Segregated account ref:** prod-secret://antiek/escrow/ip-holder-account",
            "**Segregated account ref:** ",
        ),
        encoding="utf-8",
    )

    result = escrow_account_decision_probe.probe_escrow_account_decision(decision)

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["account_or_secret_ref_recorded"].passed is False


def test_escrow_account_decision_probe_json_cli(tmp_path, capsys):
    decision = tmp_path / "decision.md"
    decision.write_text(_decision_doc(), encoding="utf-8")

    exit_code = escrow_account_decision_probe.main([
        "--decision-path",
        str(decision),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["account_ref_present"] is True
    assert payload["does_not_close_oa014"] is True
