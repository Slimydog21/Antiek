# Auth Diagnostic Precision — verification report

**Programme:** `docs/htmlspec/auth-diagnostic-precision/`<br>
**Repo:** `reader/integration`<br>
**Reverified:** 2026-07-01

## Current closure

| Sprint | Status | Evidence |
|--------|--------|----------|
| SPR-01 failure-mode matrix | Done | `docs/diagnostics/auth-failure-mode-matrix.md` is 143 lines and includes immutable Layer A/B/OPS rows plus the allowlist-vs-fetch impossibility lemma. |
| SPR-02 login error taxonomy | Done | `npm test -- auth.test --run` passed 1 file / 11 tests. |
| SPR-03 callback error surface | Done | `tests/test_magic_link_auth.py` callback cases passed inside the auth pytest set. |
| SPR-04 composed auth probe | Done | `tests/test_auth_probe.py` and `tests/test_prod_parity.py` passed inside the auth pytest set. |
| SPR-05 login-real Playwright | Done | `LOGIN_E2E=1 npx playwright test --project=login-real` passed 2 tests. |
| SPR-06 multi-email allowlist | Done through M2; M3 operator-gated | `tests/test_magic_link_auth.py` and `tests/test_api_auth_state.py` passed; production SSH/prod-email verification remains in `docs/operator_gate_actions.md`. |

## 2026-07-01 gates

- `wc -l docs/diagnostics/auth-failure-mode-matrix.md` — 143 lines.
- `npm test -- auth.test --run` — 11 tests passed.
- `./.venv/bin/python -m pytest tests/test_magic_link_auth.py tests/test_api_auth_state.py tests/test_auth_probe.py tests/test_prod_parity.py -q` — 74 passed, 1 warning.
- `LOGIN_E2E=1 npx playwright test --project=login-real` — 2 passed.
- Auth diagnostic local HTML link audit — passed.

## Not proven by automation

- Production allowlist contains `the@faisalnazer.com`.
- Production `auth_probe` exits 0 after any live allowlist edit.
- Real Resend inbox delivery; the browser e2e uses the hermetic mock-email path.

The remaining production checks require operator approval for SSH/prod-secret inspection and are tracked under `docs/operator_gate_actions.md`.
