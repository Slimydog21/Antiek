# caffenagent run — ANT-AUTH-DIAG

- **Spec dir:** `docs/htmlspec/auth-diagnostic-precision`
- **Target branch:** `main`
- **Run mode:** fully autonomous · worktree-per-sprint · merge-on-green · ≥1 sharpen round

## How to monitor this run (operator)

Open **Tasks pane (Ctrl+T)** for recursive subagent tree, styles, and lineage. Main chat stays quiet per Invocation Contract; progress lives here + `state.json` + todo list.

## Sprint roster

| Sprint | Title | Wave | Status | Rounds | Merge SHA |
|--------|-------|------|--------|--------|-----------|
| SPR-01 | Failure-mode matrix | 1 | in-progress | 1 | — |
| SPR-02 | Login error taxonomy | 1 | pending | — | — |
| SPR-03 | Callback error surface | 2 | pending | — | — |
| SPR-04 | Auth probe | 2 | pending | — | — |
| SPR-05 | Playwright login e2e | 3 | pending | — | — |
| SPR-06 | Multi-email allowlist | 3 | pending | — | — |

### SPR-01 — Failure-mode matrix
- **Worktree:** `.caffenagent/wt/SPR-01` · **Branch:** `caffen/SPR-01`
- **Round 1:** Builder delivered matrix (147 lines), authDiagnosticCodes.ts, operator_gate_actions pointer