# Campaign ledger — research/reading spine residual (2026-07-09 rebased)

**Honest scope statement:** Finite residual slice rebased onto `origin/main` after #440/#442/#443. Does **not** claim infinite platform finish.

| Field | Value |
|---|---|
| Branch | `campaign/research-reading-spine-2026-07-09-main` |
| Base SHA | `b3875724` (`origin/main`) |
| Prior unmerged campaign | `campaign/research-reading-spine-2026-07-09` @ `835757f1` (spine source) |
| Worktree | `platform/worktrees/campaign-rrs-main` |
| Orchestrator | Grok Build /infinite goal 019f4744 |
| Lane claim | `ANTIEK-AGENT-LANES.md` · campaign/research-reading-spine-2026-07-09-rebased |

## Finite slice status

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Research↔reading engagement spine | **done** | `substrate/engagement_spine/**`; `tests/test_engagement_spine.py` (9) |
| 2 | HTML-first projection for spine assets | **done** | `project_to_html` → `services.html_projection.render`; `tests/test_engagement_html_projection.py` (3) |
| 3 | Model driver/budget | **reconciled** | #440 on main (inventory/usage/projection). Residual only: `substrate/model_registration/**` add-model + select_driver → `model_override` (4 tests). No duplicate settings stack. |
| 4 | Midnight oil (chosen deferred package A) | **done** | `substrate/midnight_oil/**`; `tests/test_midnight_oil.py` (11) — ceiling math, approve gate, budget halt, timeout, HTML+twin deposit |
| 5 | Book marketplace host-into-account | **deferred-with-spec** | `docs/htmlspec/marketplace-host/` |
| 6 | Recursive Antiek-bench | **deferred-with-spec** | `docs/htmlspec/antiek-bench-recursive/` |
| 7 | NotDiamond usefulness | **verdict** | `docs/htmlspec/notdiamond-verdict/VERDICT.md` — advisory GO / authority REJECT |

## Non-claims

- Not infinite completion of Antiek.
- Not full floating-window multi-select collective chat chrome.
- Not live multi-provider deep research over network.
- Not commercial payment rails / DRM.
- Not NotDiamond as authoritative dispatch.

## Inventory

See `inventory.txt` in this directory and `{SCRATCH}/inventory/inventory.txt`.
