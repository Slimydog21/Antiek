# Single-root workflow verification (goal harness)

| Role | Path |
|------|------|
| Canonical implementation | `~/Desktop/Antiek` (this repo) |
| Harness CLI only | `~/Antiek/antiek_check.py` (thin wrapper, no workflow mirror) |

Verification: `cd ~/Antiek && python3 antiek_check.py all`  
Steps: `scripts/run_goal_verification_plan.sh` — workflows×2, 9-phase evidence, reading **4a** pytest + **4b** vitest, shared `tests/fixtures/kb_artifact_minimal.html`.