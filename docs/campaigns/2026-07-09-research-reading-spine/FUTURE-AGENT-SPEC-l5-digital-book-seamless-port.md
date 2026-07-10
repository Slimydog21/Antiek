# Future-agent executable brief — L5 digital book seamless port

**Campaign tip at write:** residual **ahf** · branch `campaign/research-reading-spine-2026-07-09-main` · PR **#465**  
**Bar:** Hawkins craft · five values · HTML-first · never invent live payment · offline-honest until dual-gate  
**Related offline ship:** residual **ahe** (`data-seamless-purchase-port` · manual receipt)

## Operator vision (binding)

> Buy a digital book if no PDF online; seamless port so the book is hosted in my Antiek account. Every human-viewable asset is HTML (not PDF view).

## Already shipped offline (do not rebuild)

| Piece | Residual / path |
|---|---|
| Catalog free PD HTML STEM spine | ags Fourier · earlier Faraday…Gödel |
| Host free book into account | marketplace_host product_path |
| Manual purchase + host demo | `purchaseAndHost` + UI residual bg |
| Purchase path honesty stamps | **ahe** seamless-purchase-port · L5 deferred |
| Twin seed after host/purchase | gj |
| Open Write HTML draft handoff | aeo · fl |
| Library rehydrate HTML open | do |

## L5 unlock conditions (all required)

1. Product/legal design for payment rails (not agent-invented).
2. Operator dual-gate enable (env + boot wire) documented in `DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l5-payment`.
3. Opaque receipt still valid fallback when live rails fail.
4. Purchased content always projected to **HTML** (`view_format=html`); PDF is ingest source only.
5. Account library lists purchased docs with `is_free=false` honesty (never free-count inflation).

## Execution plan for future agents (when L5 unlocked)

### Sprint 1 — Payment adapter boundary

- New module: `substrate/marketplace_host/payment_adapter.py` (interface only if still deferred).
- Methods: `create_checkout(book_id, owner_id) -> CheckoutSession` · `confirm_receipt(opaque_ref) -> Entitlement`.
- **Never** call live processor until dual-gate env true.
- Tests: disabled posture returns typed deferred error; zero upstream call.

### Sprint 2 — Purchase product path

- Extend `purchase_and_host` to accept either:
  - `opaque_reference` (manual — keep forever), or
  - `checkout_session_id` (live — gated).
- On success: same host pipeline as free books (HTML body · library · twin seed).
- Stamps: keep `data-seamless-purchase-port` · set `data-live-payment=true` only when real charge confirmed.

### Sprint 3 — UI

- MarketplaceHost: when live rails ready, show checkout CTA; else keep manual receipt (ahe honesty).
- Budget/settings: never claim free inventory for purchased titles.
- Dual-gate checklist deep-link remains until live green.

### Sprint 4 — Antiek-bench dogfood

- `book_qa` fixture for purchased HTML host path.
- Wrestle fixture for L5 deferred vs live honesty (propose≠promote).

## Invariants (hard to vary)

1. Human view = HTML; PDF never the reading surface.
2. Soft budget / payment: never invent $0 entitlement.
3. propose≠promote for any suite that learns purchase outcomes.
4. Offline-honest default; live is dual-gate only.
5. Agents never merge main/prod; PR #465 operator-gated.

## Proof bar for L5 ship

- pytest payment adapter disabled + enabled (gated) paths.
- vitest purchase UI live_payment false|true honesty.
- Manual receipt path never regresses.
- free_count identity still matches entry is_free flags.

## Anti-patterns

- Silencing L5 deferred copy when rails still off.
- Auto-hosting paid content without receipt or confirmed checkout.
- Counting purchased books as free_pd.
- Shipping live Stripe/etc. without operator dual-gate.
