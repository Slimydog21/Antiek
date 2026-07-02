"""Guards for the auth-diagnostic verification handoff.

The auth diagnostic program intentionally has two proof classes:
hermetic tests that agents can rerun, and production-only checks that require
operator approval. This file keeps the closure report honest about that split.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "htmlspec" / "auth-diagnostic-precision" / "AUTH_VERIFICATION.md"
MATRIX = ROOT / "docs" / "diagnostics" / "auth-failure-mode-matrix.md"
OPERATOR_GATES = ROOT / "docs" / "operator_gate_actions.md"


def _compact(text: str) -> str:
    return " ".join(text.split())


def test_auth_verification_report_pins_hermetic_gates_and_matrix_line_count() -> None:
    report = REPORT.read_text(encoding="utf-8")
    line_count = MATRIX.read_text(encoding="utf-8").count("\n")

    assert f"`docs/diagnostics/auth-failure-mode-matrix.md` is {line_count} lines" in report
    assert "`npm test -- auth.test --run` — 11 tests passed." in report
    assert (
        "`./.venv/bin/python -m pytest tests/test_magic_link_auth.py "
        "tests/test_api_auth_state.py tests/test_auth_probe.py "
        "tests/test_prod_parity.py -q`"
    ) in report
    assert "`LOGIN_E2E=1 npx playwright test --project=login-real` — 2 passed." in report
    assert "Auth diagnostic local HTML link audit — passed." in report


def test_auth_verification_report_does_not_overclaim_production_proof() -> None:
    report = REPORT.read_text(encoding="utf-8")
    compact = _compact(report)

    assert "## Not proven by automation" in report
    assert "Production allowlist contains `the@faisalnazer.com`." in report
    assert "Production `auth_probe` exits 0 after any live allowlist edit." in report
    assert "Real Resend inbox delivery; the browser e2e uses the hermetic mock-email path." in report
    assert (
        "The remaining production checks require operator approval for "
        "SSH/prod-secret inspection and are tracked under "
        "`docs/operator_gate_actions.md`."
    ) in compact

    forbidden_overclaims = [
        "Production allowlist contains `the@faisalnazer.com` | Done",
        "Production `auth_probe` exits 0 | Done",
        "Real Resend inbox delivery | Done",
    ]
    for phrase in forbidden_overclaims:
        assert phrase not in compact


def test_operator_auth_gate_keeps_concrete_probe_command_and_boundary() -> None:
    operator_doc = OPERATOR_GATES.read_text(encoding="utf-8")
    compact = _compact(operator_doc)

    assert "## Auth Diagnostic Operator Action — Multi-email magic-link allowlist" in operator_doc
    assert "**Status:** ⏳ operator-gated production verification" in operator_doc
    assert "not a new G1-G12 product/legal gate" in compact
    assert (
        "tests/test_magic_link_auth.py::"
        "test_multi_email_allowlist_middleware_accepts_both_operators"
    ) in operator_doc
    assert (
        "ssh <antiek-vm> \"grep '^ANTIEK_OPERATOR_EMAIL=' "
        "/etc/antiek/secrets.env | sed 's/=.*/=<redacted>/'\""
    ) in operator_doc
    assert "python tools/auth_probe.py --base-url https://api.antiek.ai" in operator_doc
