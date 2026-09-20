# Antiek Ad Infrastructure — v1 Scalable Implementation Plan

**Date:** 2026-08-12  
**Status:** Gap-ranked plan; no code changes in this audit  
**Source of truth:** `docs/master-product-spec.md` §9.8 phased sequence + §9.3 algorithm design + `docs/integration_applovin.md` wedge matrix  
**Predecessor audit:** `/tmp/antiek-wt-ad-audit/REPORT.md`

---

## Executive summary

The per-second frame-attribution pipeline is substantially implemented (1,224 lines across `frame_attention.py` + `frame_attention_accrual.py`, HTTP surface in `ad_routes.py`, verification harness in `verify_ad_economics.py`). All three §9.3 attribution algorithms (A/B/C) are live in `substrate/attribution/compute.py` and exposed via `GET /attribution/synthesis/{id}?emit_event=true`. The anti-gaming layer is implemented (8 modules, 1,367 lines).

However, six named gaps prevent the pipeline from supporting revenue-bearing money flow. This plan ranks implementation work by dependency order, anchored to the master spec's phased sequence (§9.8) and the AppLovin integration spec's wedge matrix. Every item carries exact files to touch and an honest deferral disposition where applicable.

---

## Gap-ranked implementation order

### Rank 0 — Prerequisites (must ship before any revenue flows)

These are not gaps in the ad pipeline itself, but preconditions for v1 to be "ad-ready."

#### 0.1 Ad pricing (non-zero revenue)

**What:** Today all `revenue_usd_cents` in the frame pipeline are $0. The `ad_routes.py` frame-telemetry route hardcodes zero value. Until at least one advertiser is ACTIVE with a budget, the entire pipeline is telemetry-only.

**Files to touch:**
- `interfaces/research/api/ad_routes.py` — `resolve_window_value_cents()` function (currently stubbed at 0; must join fill/pricing record by window_id)
- `substrate/ad_inventory/fill_decisions.py` — `price_status` column is `'unpriced'` for all rows; needs `'settled'` path
- `substrate/ad_inventory/advertiser_onboarding.py` — already implemented; needs first real advertiser
- `substrate/ad_inventory/ad_bidding.py` — `AdInventoryItem.cpm_usd` field exists; needs non-zero values in persisted inventory

**Deferral:** None. This is gating for v1.

#### 0.2 Legal-gate assertion (§9.0)

**What:** `advertiser_onboarding.py` `activate_advertiser()` already requires `legal_gate_passed=True`. The `__main__.py` CLI requires `--legal-gate-passed` flag. The operator must actually pass the legal gate before any advertiser goes ACTIVE. No code change required — this is an operational gate.

**Files to touch:** None (already enforced in code at `advertiser_onboarding.py:activate_advertiser` and `__main__.py:_cmd_activate`).

**Deferral:** None. Binding per §9.0: "The gate is not negotiable."

---

### Rank 1 — Trust hardening (must ship before revenue-bearing telemetry)

These correspond to AppLovin W2 gaps S1–S2. Without them, frame-attention revenue cannot be trusted.

#### 1.1 Server-minted value (W2-S1)

**What:** `POST /api/ad/frame-telemetry` passes client-supplied `ad_value_usd_cents` into `accrue_window`. The shipped emitter hard-codes 0 today, but the architecture must not trust the client. Fix: server resolves window value from fill/pricing records; client field becomes an ignored legacy hint under a bumped `FRAME_TELEMETRY_SCHEMA_VERSION`. Add session authentication matching the rest of the authenticated surface.

**Files to touch:**
- `substrate/ad_inventory/frame_attention.py` — bump `FRAME_TELEMETRY_SCHEMA_VERSION`; add `ad_value_usd_cents` deprecation comment on `WindowFrameBatch`
- `interfaces/research/api/ad_routes.py` — add auth dependency; implement `resolve_window_value_cents()` joining fill_decisions table by window_id; ignore client-supplied value field
- `apps/reading/src/components/ad/frameTelemetryClient.ts` — stop sending `ad_value_usd_cents` (or send 0 with new schema version)
- `tests/test_ad_routes.py` — add `test_frame_telemetry_ignores_client_supplied_value` (already stubbed per docstring at `ad_routes.py`)

**Estimated effort:** 1–2 days. **Dependencies:** Rank 0.1 (pricing must exist to have non-zero server-minted values).

#### 1.2 Anti-gaming mediation for frame batches (W2-S2)

**What:** `substrate/anti_gaming/frame_ivt.py` already implements GIVT + SIVT classification. The remaining work: (a) integrate `classify_batch` as a pre-accrual filter in `frame_attention_accrual.accrue_window` so invalid seconds are excluded from BOTH numerator and denominator (filter-before-allocate per MRC IVT model); (b) implement per-identity saturation caps — countable dwell per (user, asset, day) saturates at a published cap.

**Files to touch:**
- `substrate/ad_inventory/frame_attention_accrual.py` — add `classify_batch()` call before accrual; exclude GIVT-invalid seconds; count and report exclusions
- `substrate/anti_gaming/frame_ivt.py` — add per-identity saturation cap constants and a `saturate_dwell()` function
- `tests/test_frame_attention_accrual.py` — add test: GIVT-invalid second excluded from both numerator and denominator; saturation cap test

**Estimated effort:** 2–3 days. **Dependencies:** None (classification logic already exists; integration is mechanical).

---

### Rank 2 — Composition (must ship to pay the drivers of content value)

#### 2.1 Frame→synthesis→chunk composition (W2-S3)

**What:** Today a frame showing a synthesis artifact monetizes the artifact's own `document_id`. The sources that *drove* the synthesis earn nothing. Fix: when a monetized asset is a synthesis artifact, resolve its recorded §9.3 share vector (Option B weighting per SPR-10 precedent) and split the per-window value into the constituent documents' escrow using the same largest-remainder cent conservation primitive.

**Files to touch:**
- `substrate/ad_inventory/frame_attention_accrual.py` — add `_resolve_synthesis_shares()` that queries the synthesis's attribution record; apply share split before escrow routing
- `substrate/attribution/compute.py` — ensure attribution records are queryable by synthesis_id (already the case; verify index)
- `substrate/ad_inventory/attribution_explain.py` — reuse `_largest_remainder_cents` (already a public wrapper `apportion_cents` in `frame_attention.py`)
- `tests/test_frame_attention_accrual.py` — add synthesis-composition test with hand-computed splits

**Estimated effort:** 2–3 days. **Dependencies:** Rank 0.1 (synthesis attribution records must exist for the relevant syntheses).

#### 2.2 One payable truth across ledgers (W2-S4)

**What:** Three accrual ledgers coexist: `frame_attention_accruals`, `marketplace_metrics/book_escrow.py`, `substrate/payouts/ledger.py`. Declare `frame_attention_accruals` the single payable source for reading-surface attention value. Measure what writes to book_escrow; either reconcile-and-retire or make it derived/reporting.

**Files to touch:**
- `substrate/ad_inventory/frame_attention_accrual.py` — add docstring declaration: "This is the single payable source for reading-surface attention value"
- `substrate/marketplace_metrics/book_escrow.py` — audit all write paths; add deprecation warning if still written
- `substrate/payouts/ledger.py` — audit; confirm it's downstream splitter, not parallel ledger
- `tests/test_seam_single_escrow_writer.py` — add assertion: no revenue-bearing write outside `frame_attention_accruals` (extend existing `_SANCTIONED_ESCROW_CALLERS` set)
- `tools/verify_ad_economics.py` — add reconciliation job: prove per window that no cent appears in two payable ledgers

**Estimated effort:** 1–2 days. **Dependencies:** None (audit-only; no new logic).

#### 2.3 Split composition in published order (W2-S5)

**What:** `payout.py` applies 70/30 with $50/day cap; `payouts/split.py` applies author-split-equal-v1; `rights/ad_eligibility.py` allows ads on T1 arXiv licenses only. Nothing composes them into a single published pipeline. Fix: define and version-stamp the composition order (pool → carve-outs → 70/30 → per-frame split → per-document resolution → residuals → `UNATTRIBUTED_RIGHTS_BUCKET`). Golden test walks a synthetic month end-to-end.

**Files to touch:**
- `substrate/ad_inventory/payout.py` — add `SPLIT_COMPOSITION_VERSION`; implement `compose_split_pipeline()` that chains all stages; document the order per W2-S5 spec
- `substrate/payouts/split.py` — expose version stamp (`AUTHOR_SPLIT_POLICY_VERSION`)
- `substrate/rights/ad_eligibility.py` — expose version stamp
- `substrate/ad_inventory/frame_attention.py` — add `UNATTRIBUTED_RIGHTS_BUCKET` sentinel if not already present
- `tests/test_split_composition.py` — new golden test: synthetic month, all stages, cent conservation at every boundary

**Estimated effort:** 2–3 days. **Dependencies:** Ranks 1.1, 2.1, 2.2 (pipeline cannot compose what doesn't yet feed into it).

---

### Rank 3 — Auditability (ships before first publisher payout)

#### 3.1 Per-payee monthly statements with inclusion proofs (W2-S6)

**What:** Monthly attribution close computes a canonical statement per IP holder (decomposable to per-window aggregates), plus a tamper-evidence layer — append-only hash chain over the month's accrual rows with a published month root and per-payee inclusion proofs (certificate-transparency pattern, Merkle tree over canonical-JSON rows). No new dependencies (stdlib only).

**Files to touch:**
- `substrate/ad_inventory/attribution_audit.py` — add `build_monthly_statement()` and `build_merkle_proof()` functions
- `substrate/ad_inventory/attribution_explain.py` — add per-payee statement generation
- New file: `tools/generate_monthly_statements.py` — CLI for monthly close
- `tests/test_monthly_close.py` — golden test: known accrual rows → verifiable statement

**Estimated effort:** 2–3 days. **Dependencies:** Ranks 1–2 complete (statements describe a working pipeline).

---

### Rank 4 — Close the Axon loop (improves fill quality; not gating for v1)

#### 4.1 Fill-decision record (W1-step 0)

**What:** Today `GET /api/ad/fill` returns `AdFillResponse` and records nothing. Persist the serving decision: window_id → chosen fill with candidate set, per-candidate features/scores, ranker version. Without this, the label join for learned retraining has nothing to join to.

**Files to touch:**
- `interfaces/research/api/ad_routes.py` — add `_persist_fill_decision()` call in fill handler
- `substrate/ad_inventory/fill_decisions.py` — already has `decide_fills()` and `ensure_table`; verify it's called from the fill path
- `substrate/schemas/events.py` — add `AD_FILL_DECIDED` event type if desired

**Estimated effort:** 0.5–1 day. **Dependencies:** None.

#### 4.2 Label extraction + retrain + flag-gated serving (W1-steps 1–3)

**What:** Offline batch job derives per-impression value labels from `frame_attention_accruals` (attention-weighted value), joined to fill-decision records. Retrain the `auction_model.py` calibrated logistic. Serve behind `ANTIEK_LEARNED_AD_RANKER` flag with rule-based fallback.

**Files to touch:**
- New file: `tools/extract_auction_labels.py` — batch job
- `substrate/ad_inventory/auction_model.py` — already has `train()` function; just feed it real labels
- `substrate/ad_inventory/auction_ranker.py` — already flag-gated; no change needed
- `tests/test_auction_retrain.py` — golden test: same data → same artifact

**Estimated effort:** 2–4 days. **Dependencies:** Rank 4.1 (fill-decision records) + Ranks 1.1–1.2 (trustworthy labels require server-minted value + anti-gaming filter).

---

### Rank 5 — Manual sponsor slot (v1 operator sales motion)

#### 5.1 Implement `BiddingPolicy.MANUAL_SPONSOR` code paths

**What:** The `MANUAL_SPONSOR` enum exists in `ad_bidding.py:20` but no code exercises it. v1 per §9.8 Phase 2: "Single sponsorship slot in MASTER.md viewer footer. Manual sponsor onboarding via direct sales. Sponsor pays flat monthly fee."

**Files to touch:**
- `substrate/ad_inventory/ad_bidding.py` — add `ManualSponsor` dataclass; add `select_manual_sponsor()` function
- `substrate/ad_inventory/reader_slots.py` — extend `fill_slot()` to try manual sponsor before lead-gen matching when `BiddingPolicy.MANUAL_SPONSOR` is active
- `substrate/ad_inventory/fill_decisions.py` — handle sponsor fill kind
- `interfaces/research/api/ad_routes.py` — wire sponsor fill into GET /api/ad/fill

**Estimated effort:** 1–2 days. **Dependencies:** Rank 0.1 (pricing — sponsor pays a flat monthly fee, so CPM→cents conversion is different from lead-gen auction).

---

## What is deferred (per §9.8 phases)

| Phase | Sprint | What | Deferral rationale | Re-evaluation trigger |
|-------|--------|------|-------------------|----------------------|
| 3. Publisher dashboard | Sprint 20–22 | `publisher.antiek.ai`, Stripe Connect automated payouts, KYC + 1099 compliance | §9.8 row 3: "~3 sprints because compliance + KYC + UX is substantial." The transfer_initiator exists but Stripe Connect provider needs audit. | After first advertiser is ACTIVE and revenue is non-zero |
| 4. Lead-gen ad inventory at scale | Sprint 23+ | Curated vertical ad slots replacing manual sponsor | The lead-gen infrastructure is already built (`intent_targeting.py`, `auction_ranker.py`). Scaling means more inventory items, not new code. | When manual sponsor hits capacity ceiling |
| 5. Programmatic auction | Sprint 30+ | Header-bidding-style auction | Two recorded deferral gates (D7 + Thread 3) unfired. D7 requires multi-user pivot closure + first creator cohort live. Thread 3 requires aggregate advertiser spend > ~$50K/mo. | Both gates fire |
| AppLovin W3 — Demand-side Ads | — | AppLovin Ads as advertiser for Antiek growth | Gated on growth-doctrine overturn in writing + live conversion event + identifier-minimization resolution + contract terms. If identifier conflict (§8.3) is unresolvable → REJECT permanently. | Growth doctrine overturn |
| AppLovin W4 — Supply-side MAX | — | Monetization via MAX SDK | No web publisher SDK exists; requires native app Antiek doesn't have. Recorded SSP candidates are Google Ad Manager or Magnite, not AppLovin. | Native app ships AND programmatic auction gates fire |
| Pre-onboarded IP holder notification emails | Sprint 19 | First batch to MIT Press, Cambridge UP, Princeton UP | §9.10: "Lawyer involved before the first notification email is sent." Binding legal gate; not an engineering task. | Operator's lawyer approves |

---

## Dependency graph (summary)

```
Rank 0 (prerequisites)
├── 0.1 Ad pricing ─────────────────────────────────────┐
├── 0.2 Legal-gate assertion (operational, no code)      │
                                                        │
Rank 1 (trust hardening)                                 │
├── 1.1 Server-minted value ─────── depends on 0.1 ──────┤
└── 1.2 Anti-gaming for frames ──── no dependencies      │
                                                        │
Rank 2 (composition)                    ◄── depends on Rank 1 ──┤
├── 2.1 Frame→synthesis composition ─── depends on 0.1          │
├── 2.2 One payable truth ──────────── no dependencies          │
└── 2.3 Split composition ──────────── depends on 1.1, 2.1, 2.2 │
                                                                  │
Rank 3 (auditability)                  ◄── depends on Rank 2 ────┤
└── 3.1 Monthly statements ─────────── depends on Ranks 1-2     │
                                                                  │
Rank 4 (Axon loop)                     ◄── depends on Rank 1 ────┤
├── 4.1 Fill-decision record ───────── no dependencies          │
└── 4.2 Label extraction + retrain ─── depends on 4.1 + 1.1-1.2 │
                                                                  │
Rank 5 (manual sponsor)                                       │
└── 5.1 Manual sponsor code paths ──── depends on 0.1 ─────────┘
```

---

## What is NOT in this plan (explicitly rejected)

- **AppLovin pixel on any Antiek surface** — REJECT R2. Identifier/data-practice collision with rights posture (`integration_applovin.md` §10).
- **Any external auction as a serving gate** — REJECT R5. Serving decisions stay in-process and explainable (`integration_applovin.md` §3).
- **Programmatic display ads before gates fire** — DEFER D7 + Thread 3. Both gates unfired; no re-litigation.
- **Stripe Connect live transfers before G2/G3 gates** — Binding per §9.0: "disbursement stays behind G2/G3." The transfer_initiator exists but is not yet activated.
- **Publisher notification emails without lawyer** — Binding per §9.10: "Lawyer involved before the first notification email is sent."

---

## Verification: what the capstone harness proves today

`tools/verify_ad_economics.py` composes the real modules end-to-end and asserts:

1. Cent conservation: Σ per-asset accrual + house == window ad value (largest-remainder).
2. Escrow accrual: `ip_holders.accrue_escrow` is called for eligible assets; private `user_owned` assets earn $0.
3. Gated-but-public assets (`restricted_pending_opt_in`) earn to escrow while their body never renders.
4. House seconds are recorded explicitly, never silently dropped.
5. Disbursement is BLOCKED: `Speak contributor.attempt_disbursement` returns blocked; G2/G3 gates hold.
6. Attribution explanation traces a cent back to second→chunk→asset with exact conservation.

Run: `python tools/verify_ad_economics.py` (read-only; idempotent).

---

## Key file:line reference

| File | Key content |
|------|------------|
| `substrate/ad_inventory/frame_attention.py` | `weigh_second()`, `WindowFrameBatch`, `apportion_cents` |
| `substrate/ad_inventory/frame_attention_accrual.py` | `accrue_window()`, `ensure_tables`, escrow routing |
| `substrate/attribution/compute.py` | `compute_attribution_for_synthesis()`, all three algorithms |
| `substrate/ad_inventory/payout.py` | `PayoutRouter`, `distribute_session_ad_revenue()`, `distribute_with_gates()`, $50 cap |
| `substrate/anti_gaming/` (8 files) | Click/view/attribution fraud, frame IVT, composite detector, red-team harness |
| `interfaces/research/api/ad_routes.py` | `POST /api/ad/frame-telemetry`, `GET /api/ad/fill` |
| `interfaces/research/api/ad_impressions.py` | `GET /ad-inventory/select`, `POST /ad-impressions` |
| `interfaces/research/api/app.py:3764-3801` | `GET /attribution/synthesis/{id}?emit_event=true` |
| `docs/integration_applovin.md` | Wedge matrix, 6 gaps, architectural decisions |
| `tools/verify_ad_economics.py` | End-to-end capstone harness |
| `substrate/ad_inventory/advertiser_onboarding.py` | Advertiser state machine (PENDING_REVIEW→ACTIVE) |
| `substrate/ad_inventory/transfer_initiator.py` | Stripe Connect transfer initiation (idempotent) |
| `substrate/ad_inventory/attribution_audit.py` | Append-only audit trail, replay |
| `substrate/ad_inventory/attribution_explain.py` | "Why did this asset earn this?" trace |
