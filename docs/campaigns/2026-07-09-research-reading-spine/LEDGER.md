# Campaign ledger — research/reading residual (2026-07-09+)

**Honest scope:** Finite residual slices only. Not infinite platform finish.

| Field | Value |
|---|---|
| Branch | `campaign/research-reading-spine-2026-07-09-main` |
| PR | https://github.com/Slimydog21/Antiek/pull/465 |
| Base | `origin/main` @ `b3875724` |

## Cycle 1 (spine + midnight oil) — shipped on branch

| Item | Status | SHA |
|---|---|---|
| Engagement spine | done | `34036aa1` + `ensure_spawn` @ `8c1cdc0e` |
| HTML projection path | done | engagement_spine.project_to_html |
| Model residual | done | model_registration (no #440 duplicate) |
| Midnight oil | done | `8c1cdc0e` |
| NotDiamond verdict | done | advisory GO / authority REJECT |

## Cycle 2 (package B host-into-account) — this cycle

| Item | Status | Evidence |
|---|---|---|
| Catalog + license_class | **done** | `substrate/marketplace_host/catalog.py` |
| host_into_account idempotent | **done** | content-addressed `hdoc_*` per owner |
| Account library membership | **done** | `AccountLibrary.load` |
| Manual purchase receipt | **done** | `ManualPurchaseReceipt` (no Stripe/card) |
| HTML view (not PDF) | **done** | `project_hosted_book_html`; PDF source → HTML placeholder |
| Antiek-bench | **deferred-with-spec** | `docs/htmlspec/antiek-bench-recursive/` |

## Non-claims

- No live Stripe/DRM; no operator merge to main required for this pass.
- No rebuild of living-roadmap SPR-01..14.
