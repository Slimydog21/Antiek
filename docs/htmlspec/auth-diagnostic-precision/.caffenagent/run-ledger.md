# caffenagent run — ANT-AUTH-DIAG

- **Spec dir:** `docs/htmlspec/auth-diagnostic-precision`
- **Target branch:** `main`
- **Run mode:** fully autonomous · worktree-per-sprint · merge-on-green · ≥1 sharpen round

## How to monitor this run (operator)

Open **Tasks pane (Ctrl+T)** for recursive subagent tree, styles, and lineage. Main chat stays quiet per Invocation Contract; progress lives here + `state.json` + todo list.

## Sprint roster

| Sprint | Title | Wave | Status | Rounds | Merge SHA |
|--------|-------|------|--------|--------|-----------|
| SPR-01 | Failure-mode matrix | 1 | done | 2 | 59ee895e |
| SPR-02 | Login error taxonomy | 1 | done | 2 | 59ee895e |
| SPR-03 | Callback error surface | 2 | done | 2 | 9caba16e |
| SPR-04 | Auth probe | 2 | done | 2 | 9caba16e |
| SPR-05 | Playwright login e2e | 3 | done | 2 | 9caba16e |
| SPR-06 | Multi-email allowlist | 3 | blocked | 2 | dc79ceeb |

### SPR-01 — Failure-mode matrix
- **Status:** done.
- **Merge SHA:** `59ee895e` (`feat(auth-diag): SPR-01/02 failure-mode matrix and login error taxonomy`)
- **Round 1:** Builder delivered matrix, `authDiagnosticCodes.ts`, and operator-gate pointer.
- **Round 2:** Sharpened by `dc79ceeb` (`fix(auth-diag): sharpen — callback tests, matrix, prod_parity auth_probe hook`).
- **Verification:** `docs/diagnostics/auth-failure-mode-matrix.md` is 143 lines and carries 13 immutable failure-id rows; `apps/reading/src/lib/authDiagnosticCodes.ts` points to matrix commit `59ee895ec78c69ab06ccdbbdd5927fcdff866432`.

### Remaining operator block
- **SPR-06 M3:** production SSH allowlist update for `the@faisalnazer.com` remains blocked on operator approval. Local multi-email middleware behavior is covered by tests per `state.json`.
