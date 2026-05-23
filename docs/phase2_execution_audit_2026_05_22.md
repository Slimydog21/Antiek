# Phase 2 Execution Audit — 2026-05-22

**Verdict (one line):** Phase 2 is **not executed**. Roughly 35-40% of
Phase 2's substrate primitives are scaffolded locally (uncommitted);
the activation surfaces, gates, integration, and binding exit
criteria are all unmet. By the spec's own §1 status legend (sprint-
breakdown.html), none of Phase 2's four sprints have moved off "not
started" status.

**Source docs audited:**
- `docs/master-product-spec.md` §9.0-9.11, §13.2-13.10, §14.1, §14.3
- `docs/sprint-breakdown.html` Sprint 22, 23-24, 25+, 30+ sections
  (§1-§4 each)

**Repository state at audit time:** HEAD = `0514681` (`sprint-12:
release plumbing`); 106 modified files including all Phase 2 React
modes (linter-adjusted to project design tokens); cumulative session
scaffold landed locally but uncommitted.

---

## §1 Spec-binding definition of "executed"

Per `docs/sprint-breakdown.html` §1 status legend, four execution
states exist:

1. **Shipped & pushed** — committed to `main`, on GitHub, deployed
   to `antiek.ai` + `api.antiek.ai`. The strictest definition.
2. **Scaffold landed locally** — code, schema, tests in worktree;
   not committed; not visible on the website.
3. **Substrate landed, activation pending** — code exists but
   external decision, dataset, or operator action gates activation.
4. **Not started** — future sprint, no implementation yet.

"Executed" in the binding sense means state (1). State (2) is local
preparation; state (3) is gated; state (4) is unbuilt. The audit
below tags every deliverable with one of the four.

---

## §2 Sprint 22 — Multi-User Pivot & Two-Graph Architecture

**Spec source:** `docs/sprint-breakdown.html` Sprint 22 (lines 1468-1586);
`docs/master-product-spec.md` §13.2, §13.4, §13.6, §13.7.

**Spec status badge:** `Not started` (with `6-month compounding gate`).

**Binding gate (Sprint 22 §1 callout):** *"Sprint 22 ships ONLY after
six months of operator-graph accumulation demonstrates the compounding
curve. Premature multi-user destroys the moat via graph contamination."*

### 2.1 Specific deliverables — execution status

| Deliverable | Spec text | Status | Evidence |
|---|---|---|---|
| `substrate/multi_user/` | Clerk/Supabase auth integration | **Scaffold landed locally** | Exists from prior sessions: `auth.py`, `graph_router.py`, `partition.py`, `skill_accumulator.py`, `skill_propagation.py`, `skill_writer.py`. No Clerk/Supabase wired; the auth.py module is substrate-only. |
| `substrate/graph/per_user_storage.py` | per-user DuckDB + encryption keys | **NOT EXECUTED** | File does not exist. Per-user storage routing partly exists in `substrate/multi_user/partition.py` and `substrate/ducklake/`, but the canonical `per_user_storage.py` named in the deliverable list is unbuilt. KMS escrow for per-graph keys is **scaffold-only** (no KMS integration). |
| `substrate/cross_graph/` | writer-queue with DP shuffler in front | **Scaffold landed locally (partial)** | `substrate/cross_graph/` exists with `federation.py`, `federation_config_store.py`, `ask_expert.py`. The **writer-queue with DP shuffler in front** specifically is NOT present — `substrate/dp_shuffler/` exists separately, but the cross-graph writer-queue that consumes it does not. |
| `substrate/ducklake/` | catalog Postgres + per-user routing | **Scaffold landed locally (this session)** | Built: `catalog.py` (CatalogBackend protocol + InMemoryCatalogBackend + SqliteCatalogBackend), `routing.py` (NoSharding + HashPrefixSharding), `migration.py` (`plan_stage1_to_stage2`, `execute_migration_plan` dry-run default). Tests pass. **But: no actual Postgres backend is wired** — the catalog uses SQLite as a stand-in. The Stage 0 → Stage 1 transition matrix from §13.6 has not been triggered. |
| `apps/reading/src/modes/PrivacyDashboard/` | real-time telemetry view + delete-all | **Scaffold landed locally (pre-session)** | Component exists, consumes `/trust-center`. **The "toggles per category" affordance from §13.3 is NOT present** — current implementation displays ε budgets but does not let users toggle telemetry off per category. The "delete-all" path hits the existing `/trust-center/deletion-requests` endpoints; the 30-day SLA enforcement at the substrate level is not yet implemented (the API queues the request, but no substrate-side scheduler actually performs the deletion). |
| `apps/reading/src/modes/TrustCenter/` | public-facing trust documentation | **Scaffold landed locally (pre-session); endpoint partially wired** | Component exists. The backend `/trust-center` endpoint exists but the **registry-backed publication** wiring I added (`substrate/trust_center/build_publication`) does not stick to `interfaces/research/api/app.py` because that file gets reverted by parallel commits on the branch. So the endpoint currently still hardcodes the three baseline surfaces from §13.3. The contract gap with the React component's documented expectation remains open. |

### 2.2 Exit criteria — all unmet

Per Sprint 22 §4:

1. **Two real users live on independent personal graphs.** ❌ Zero
   users. Single-operator mode is the substrate's only mode today.
2. **Architectural-incapability claim holds under a cross-graph-leak
   attempt.** ❌ Not tested. The two-graph architecture is partial; no
   adversarial leak attempt has been run.
3. **Trust Center publicly published, accurately describes the
   architecture.** ❌ Not publicly published. The component renders
   the operator's local data only; nothing is on `antiek.ai/trust` as
   the public surface.
4. **Substrate in Stage 1 of the §13.6 transition matrix.** ❌ Stage
   0 (single DuckDB file with operator user_id) is the current state.
5. **SOC 2 Type II explicitly deferred.** ✓ The decision is documented
   in `docs/soc2_decision.md` (template only; no actual decision filed).

### 2.3 What's not executed in Sprint 22 — exhaustive

- **The 6-month compounding gate has not begun to clock.** Per memory
  `project_researchmaxx_phase_a.md` and the master-spec §13.4, the
  compounding loop has not closed once on real data. Sprint 11 was
  when the workstation became usable; six months from that date is
  the earliest Sprint 22 can legitimately ship. The clock has not
  started in any binding sense.
- **No auth integration.** Clerk or Supabase has not been selected.
  No sign-up, sign-in, or session management exists. The OAuth scope
  mapping for the Antiek Memory MCP server's per-user resources has
  not been designed.
- **No per-user encryption-key wiring.** §13.6 says encryption at rest
  with per-graph keys via KMS is a Stage 1+ requirement. Not built.
- **No collective-graph aggregation pipeline.** Per Sprint 22 §2
  phase 3, "every user's public-facing notes flow into the collective
  graph through the §13.9 quality gate." That pipeline does not exist.
- **No cross-graph writes through shared substrate.** §13.2's
  "discovered rule" propagation primitive is unbuilt. Skill-patch
  propagation exists in `substrate/multi_user/skill_propagation.py`
  but is not wired through the differential-privacy shuffler.
- **No DP shuffler enforcement live.** §13.3 says the DP shuffler
  enforces per-surface ε budgets in production. The substrate exists
  (`substrate/dp_shuffler/`); enforcement at production telemetry
  surfaces is not happening.
- **Trust Center not publicly published at `antiek.ai/trust`.** The
  React component exists but no public deploy is live.
- **No Stage 0 → Stage 1 substrate transition.** §13.6 requires the
  DuckLake catalog Postgres to be operational, per-user file routing
  in the app layer, per-user backup windows verified. None done.
- **The "architectural incapability" cross-graph leak test from
  Sprint 22 §2 phase 2 has not been run.** This is the load-bearing
  evidence for the §13.3 "we are architecturally incapable of
  leaking" claim. Without it, the privacy posture is a promise, not
  an architecture.

---

## §3 Sprints 23-24 — Lead-Gen Ads & Creator Rev-Share Infrastructure

**Spec source:** `docs/sprint-breakdown.html` Sprint 23-24 (lines 1589-1696);
`docs/master-product-spec.md` §9.0-9.11.

**Spec status badge:** `Not started`.

**Binding gate (Sprint 23-24 §1 callout):** *"Sprints 23-24 ship ONLY
after: (a) Sprint 22's multi-user pivot is stable; (b) at least one
creator and one publisher are accruing under the Sprint-22 attribution
pipeline with no rev-share routed yet; (c) the anti-gaming layer
passes a documented adversarial review."* All three are unmet.

### 3.1 Specific deliverables — execution status

| Deliverable | Spec text | Status | Evidence |
|---|---|---|---|
| `substrate/ad_inventory/` | ad slot table + manual-curation CRUD + topic-targeting rules | **Scaffold landed locally (pre-session, partial)** | Dir exists with `ad_bidding.py`, `attribution.py`, `event_emit.py`, `event_subscription.py`, `payout.py`, `transfer_initiator.py`. **No ad-slot CRUD endpoints**; no operator-mediated inventory entry path. The substrate's existing ad_inventory module is telemetry+attribution only. |
| `substrate/anti_gaming/` | click/view/attribution fraud detectors + red-team interface | **Scaffold landed locally (this session)** | Built: `click_fraud.py`, `view_fraud.py`, `attribution_fraud.py`, `detector.py`, `verdict.py`, `red_team.py`. **31 tests passing.** Red-team interface produces evidence file at `docs/sprint23_red_team_internal_baseline.md` showing 4/4 attack classes caught + 0/1000 FP. **This satisfies the operator-side substrate test; gate (c) STILL requires an external firm.** |
| `substrate/rev_share/` | 30/70 split + creator 70% + publisher 70% (opted-in) + rollover ledger | **Scaffold landed locally (this session)** | Built: `splits.py`, `mixed_attribution.py`, `rollover.py`. 14 tests passing. No double-spend verified by test. Rollover ledger with 12-month forfeit + month-9 notice implemented. **In-process only**; no DB persistence. |
| `tools/stripe_connect/payouts.py` | credit-only → payout-eligible flip + KYC trigger + 1099 export | **Scaffold landed locally (this session)** | Built: `RevSharePayoutRouter`, `route_impression_revenue`, `PayoutOutcome`, `export_tax_year`. 10 tests passing. KYC discipline enforced (PENDING accounts cannot transfer). **The `__init__.py` export wiring does NOT persist** — parallel commits revert it; tests import directly from `tools.stripe_connect.payouts`. **No real Stripe Connect activation** — MockStripeProvider only. |
| `apps/reading/src/components/AdSlot/` | page-border banner with §5.5-discipline feature flag | **Scaffold landed locally (this session)** | Built: `AdSlot.tsx`, `index.ts`, 4 Storybook stories. Caller-injected `shouldSuppress` predicate; `onImpression` / `onSuppressed` / `onClick` callbacks. **The §5.5 voice-rubric module is not wired** — `shouldSuppress` is a static `false` until something binds it to a real voice rubric. |
| `apps/reading/src/modes/CreatorPayouts/` | accrued + paid + rollover history; Stripe Connect onboarding | **Scaffold landed locally (this session)** | Built: `index.tsx`, Storybook story. Reads `/me/payouts`. **The `/me/payouts` API endpoint does NOT persist on `app.py` (parallel commits revert)**, so the UI sits in an error state (HTTP 404 from backend) in production. Stripe Connect onboarding flow is NOT implemented. |
| `apps/reading/src/modes/AdvertiserConsole/` | operator-only inventory + targeting + creative + reporting | **Scaffold landed locally (this session)** | Built: `index.tsx`, Storybook story. Reads `/operator/advertiser-campaigns`. **That endpoint does NOT exist** (backend stub never added; would also revert). UI sits in empty state. No CRUD; no creative upload; no per-campaign reporting backed by real data. |
| `docs/sprint23_red_team.md` | external adversarial review report (gate (c) artefact) | **NOT EXECUTED — template only** | Template exists (this session). The binding artefact requires an EXTERNAL firm to file a real report. None has been engaged. The internal baseline `docs/sprint23_red_team_internal_baseline.md` is OPERATOR-self-test, explicitly NOT a substitute. |

### 3.2 Exit criteria — all unmet

Per Sprint 23-24 §4:

1. **Creators are receiving real money** — at least one payout above
   §9.5 threshold cleared Stripe. ❌ Zero creators; zero payouts.
2. **Ad spend routing through substrate at non-trivial volume** —
   ≥ 3 paying advertisers, monthly run-rate > $5K. ❌ Zero advertisers.
3. **Attribution algorithm matches operator's qualitative read** —
   20-payout sampled audit shows no operator-reversed attributions.
   ❌ No payouts to audit.
4. **No fraud incident bypasses anti-gaming layer** — red-team
   report's three attack classes all caught pre-payout. **Partial**:
   the internal baseline catches the four documented attacks, but
   external firm has not engaged.
5. **Voice-and-style discipline holds at ad-page level** — voice-style
   audit shows < 5% regression vs non-ad baseline. ❌ Not measured;
   the voice rubric module that would do this audit isn't wired.
6. **§9.5 KYC + 1099 posture reviewed by legal counsel.** ❌ Legal
   counsel has not engaged.

### 3.3 What's not executed in Sprints 23-24 — exhaustive

- **No ads serve.** No real ad rendering on any production page;
  `AdSlot` exists only in Storybook.
- **No rev-share routes real money.** `RevSharePayoutRouter` exists
  but `Stripe Connect` activation is gated on the Sprint 18 legal
  gate (retrieval-time policy_tag gating in production + first
  opted-in publisher). Both unmet.
- **No publisher has been notified.** Sprint 19 first-cohort
  notification emails (MIT Press, Cambridge UP, Princeton UP per
  §9.10) have NOT been sent. The Kalshi-pattern notification
  template exists but is unsent.
- **No creator population.** Zero users have signed up under §13.9
  framing because Sprint 22 multi-user has not shipped.
- **No external red-team engagement.** The harness exists; the firm
  has not been retained. Gate (c) is unmet.
- **No advertiser onboarding.** Zero advertisers; the operator's
  manual sales motion has not started.
- **No KYC / 1099 plumbing.** Stripe Connect's KYC flow is mocked;
  no real KYC has been completed for anyone.
- **No rollover-state surface.** The substrate ledger exists; the
  React UI displays `current_balance_cents=0` because the endpoint
  doesn't read from the ledger (and the ledger is in-process anyway).
- **No legal counsel review** of the §9.5 KYC posture or the
  Kalshi-pattern notification template.

---

## §4 Sprint 25+ — Ad Inventory at Scale & Cross-Graph Network Effects

**Spec source:** `docs/sprint-breakdown.html` Sprint 25+ (lines 1698-1809);
`docs/master-product-spec.md` §9.6, §9.8 row 4, §13.9 cross-graph.

**Spec status badge:** `Not started`.

**Binding gate (Sprint 25+ §1 callout):** Requires (1) ≥ 30 creators
earning monthly rev-share above §9.5 threshold, (2) ≥ 5 publishers
opted in with non-trivial escrow, (3) anti-gaming incident rate
below tolerance (no payout reversal in prior 8 weeks). Zero / zero /
zero.

### 4.1 Specific deliverables — execution status

| Deliverable | Status | Evidence |
|---|---|---|
| `substrate/ad_inventory/scaling.py` | **NOT EXECUTED** | File does not exist. Inline-sponsor card pattern is NOT scaffolded. §5.5 voice-discipline suppression hook is NOT wired into anything beyond AdSlot's caller-injected predicate. |
| `substrate/rev_share/mixed_attribution.py` | **Scaffold landed locally (this session)** | Built: proportional split + recipient aggregation + unallocated-rounding to platform residual. Tests confirm no double-spend. **No production usage** — Sprint 23-24 didn't ship; no mixed sessions to audit. |
| `substrate/cross_graph/ask_an_expert.py` | **Scaffold landed locally (pre-session, partial)** | A file at `substrate/cross_graph/ask_expert.py` exists (note: spec name is `ask_an_expert.py`; existing file is `ask_expert.py` — naming drift). The cross-graph opt-in discovery primitive is partial. Payment-mediated interview path is NOT wired. |
| `apps/reading/src/modes/AdvertiserSelfService/` | **NOT EXECUTED** | Conditional on §9.6 threshold ($50K/mo aggregate spend). Sprint 25+ doc says skip unless triggered. Zero advertiser spend → correctly DEFER. UI module not built. |
| `apps/reading/src/modes/PayoutDashboard/` | **Scaffold landed locally (this session)** | Built: `index.tsx`, Storybook story. Reads `/operator/payouts/dashboard`. **That endpoint does NOT exist** (backend stub never added). UI sits in empty state. |
| `apps/reading/src/modes/MarketplaceMetrics/` | **Scaffold landed locally (this session)** | Built: `index.tsx`, Storybook story. Reads `/marketplace/snapshot`. **That endpoint does NOT persist on app.py** (parallel commits revert). UI gets HTTP 404 in production. |
| `antiek.ai/handbook` | **NOT EXECUTED** | Conditional on team-size > 1. Team is still 1 (operator). Correctly DEFER. |
| `docs/soc2_decision.md` | **Template only (this session)** | Template filed. The actual PURSUE/DEFER decision has not been made because the enterprise-procurement signal has not been measured (no enterprise prospects in pipeline). Per §13.7 default: DEFER. |

### 4.2 Exit criteria — all unmet

1. **Ad-supported public consumption is the dominant revenue line**
   (> 60% of monthly platform revenue). ❌ Zero ad revenue.
2. **Creator rev-share producing real take-home dollars for ≥ 10
   creators above §9.5 threshold.** ❌ Zero creators.
3. **Cross-graph "ask an expert" has produced ≥ 1 completed interview
   with a payment cleared.** ❌ Zero.
4. **Antiek recognisably a marketplace** — ≥ 1 external observer
   describes it that way unprompted. ❌ Not yet.
5. **Mixed-attribution rev-share cleared a sampled-month audit with
   no double-spend/under-payment.** ❌ No production attributions
   to audit. *Substrate-side tests pass.*
6. **§9.4 programmatic-display gate re-evaluated; decision documented.**
   ❌ Implicitly DEFER per current marketplace_metrics output (zero
   advertiser spend); explicit re-evaluation not filed.

### 4.3 What's not executed in Sprint 25+ — exhaustive

- The marketplace_metrics module exists; **the endpoint that exposes
  it does not persist**; the React surface displays empty.
- No advertiser self-service flow because there are no advertisers.
- No SOC 2 pursuit because there are no enterprise procurement
  conversations.
- No public handbook because there's no team to handbook.
- No cross-graph interviews because there are no cross-users.

---

## §5 Sprint 30+ — Cross-Graph Network Effects & Federation

**Spec source:** `docs/sprint-breakdown.html` Sprint 30+ (lines 1812-1915).

**Spec status badge:** `Not started`.

**Binding gate (Sprint 30+ §1 callout):** Each thread has its own
trigger; threads without cleared triggers stay DEFER. **The
documented rejection IS the deliverable.**

### 5.1 Specific deliverables — execution status

| Deliverable | Trigger | Status | Evidence |
|---|---|---|---|
| `substrate/federation/` | Partner instance willing | **Scaffold landed locally (this session)** | Built: `signing.py` (HMAC-SHA256 scaffold under Ed25519-shaped interface), `slice.py`, `protocol.py`. 13 tests passing. **No partner instance exists**; no signature exchange has happened. |
| `substrate/anti_gaming/long_tail.py` | > 200 monthly-earning creators | **Partial; not as named** | `detect_creator_cluster_collusion` lives in `substrate/anti_gaming/attribution_fraud.py` rather than a separate `long_tail.py`. Functionality exists; naming differs. **No long-tail population** (zero creators); the function has never run against production data. |
| `substrate/ad_inventory/programmatic.py` | Advertiser demand > manual-curation capacity | **NOT EXECUTED** | File does not exist. Programmatic SSP integration (Google Ad Manager / Magnite) not scaffolded. Correctly DEFER per the §9.4 default rejection. |
| `substrate/roles/vision_extractor/` | ≥ 30% non-text corpus | **NOT EXECUTED** | Dir does not exist. Explicitly DEFER per the Sprint 30+ thread-trigger discipline. Source corpus is < 5% non-text informally. |
| `substrate/autoresearch/wedge3_sweep.py` | ≥ 500 graded outcomes | **Scaffold landed locally (this session)** | Built: `proposal.py`, `wedge3_sweep.py`. 11 tests passing. Pure-functional `run_sweep` with cohort-too-small gate. **Cohort outcomes count is 0**; sweep correctly returns `cohort_too_small` status. |
| `substrate/ducklake/stage2_migration.py` | Per-user file count near OS limit | **Built as `substrate/ducklake/migration.py`** | Functionality lives at `migration.py` rather than `stage2_migration.py`. `plan_stage1_to_stage2` declarative; `execute_migration_plan` dry-run default. **Stage 0 still active** — Stage 1 hasn't transitioned, so Stage 2 migration is irrelevant. |
| `tools/stripe_connect/tax_export.py` | Long-tail rev-share active | **Built as `export_tax_year` in `tools/stripe_connect/payouts.py`** | Functionality exists at a different path. Produces accountant-review per-recipient roll-up. No tax data to export (zero transfers). |
| `docs/sprint30_thread_decisions.md` | Always (renewable) | **Template + 2026-05-22 snapshot filed** | Template at `docs/sprint30_thread_decisions.md`; current-quarter snapshot at `docs/sprint30_thread_decisions_2026_05_21.md` documents all six threads as DEFER with cited zero-state measurements. **Per the §1 callout discipline, this snapshot IS the Sprint 30+ deliverable for this quarter.** |

### 5.2 Exit criteria — partially met (in a degenerate way)

1. **Each thread either live or explicitly rejected with current-quarter
   numbers.** ✓ Per the 2026-05-21 thread-decisions snapshot, all six
   threads have documented DEFER verdicts with cited zero-state
   measurements. Per §1 callout: *"the documented rejection IS the
   deliverable."* **Met in the degenerate sense** that Phase 2 hasn't
   started, so DEFER is the correct answer for every thread.
2. **Substrate's compounding curve intact under federation.** N/A —
   federation not active.
3. **Voice and style discipline holds at federation boundary.** N/A.
4. **Long-tail creator economics support themselves.** ❌ Zero creators.
5. **Single-writer invariant per instance survives federation.** ✓ By
   construction in `substrate/federation/protocol.py`; no write-back
   primitive exists in the API surface.
6. **Stage 2 latency OR Stage 1 still adequate.** ✓ Stage 1 not even
   transitioned; Stage 0 (single operator file) still adequate.

### 5.3 What's not executed in Sprint 30+ — exhaustive

- **Federation handshake** with any external instance: 0/0/0 (partner
  candidates, negotiation drafts, fingerprint exchanges).
- **Long-tail anti-gaming forensics** never run against real data.
- **Programmatic auction**: correctly DEFER per the §9.4 default
  rejection.
- **Vision-capable role**: correctly DEFER.
- **Autoresearch Wedge 3 sweep**: correctly returns `cohort_too_small`
  (substrate is gate-respecting); no proposals generated.
- **Stage 2 migration**: correctly N/A.

---

## §6 Cross-cutting gaps that block multiple sprints

### 6.1 The Sprint 18 legal gate (§9.0) — binding for Sprint 23-24

Per master-spec §15.9: *"Retrieval-time gating must ship to
production AND first publisher must be opted in BEFORE Stripe Connect
activates any payout."*

- **Retrieval-time gating in production:** Substrate exists in
  `substrate/graph/search.py` SQL-WHERE level (per the Sprint 18
  exit criteria). Production deploy: NOT verified.
- **First publisher opted in:** Zero publishers have been notified;
  zero claimed.

This gate blocks Sprint 23-24 entirely. Until it clears, no real
money routes regardless of what the rev-share substrate supports.

### 6.2 The integration revert problem (this session-specific)

Three tracked files keep getting reverted by parallel commits on the
branch:
- `interfaces/research/api/app.py` — my additions for
  `/trust-center` registry wiring, `/marketplace/snapshot`,
  `/me/payouts`, `/operator/payouts/dashboard`,
  `/operator/advertiser-campaigns` never persist.
- `tools/stripe_connect/__init__.py` — re-exports for
  `RevSharePayoutRouter` etc. never persist.
- `apps/reading/src/App.tsx` — route registrations for the new
  React modes never persist.

**Diagnosis:** between session-start and audit-write, HEAD moved
from `dc05cde` to `0514681` (the `sprint-12: release plumbing` commit
plus subsequent design-token sync). Parallel-branch commits
overwrite the integration files. The substrate dirs (new files) are
left alone, which is why anti_gaming/, rev_share/, ducklake/,
federation/, trust_center/, marketplace_metrics/, autoresearch/ all
persist while the integration-points reset.

**Net effect:** the substrate is reachable only via direct Python
imports (tests pass); the API + UI surface cannot consume it in
production.

### 6.3 Demonstration-period gap (the substrate moat itself)

Per master-spec §13.4: *"The substrate compounding thesis has not
been demonstrated yet."* This is upstream of all of Phase 2 — without
demonstrated compounding, Sprint 22's six-month gate cannot start,
Sprint 23-24's "stable Sprint 22" gate cannot be met, Sprint 25+'s
creator-count threshold cannot accumulate, Sprint 30+'s outcomes
table cannot reach 500.

**This is the single highest-leverage block on Phase 2.** Six months
of operator-graph compounding is what unlocks everything else.

### 6.4 Phase 1 (Sprints 17-21) not pushed

Per the doc's own audit (sprint-breakdown.html cover §1):
*"Sprint 17 through Sprint 21 substrate is written and tested
locally, but as of the most recent audit it remains uncommitted in
the operator's working tree."*

Phase 2 cannot ship before Phase 1. Phase 1 ship is itself blocked.
This audit confirms the same status holds for the cumulative session
work: 106 modified + untracked files, none committed to `main`.

---

## §7 Tally

### 7.1 Phase 2 substrate scaffold — what exists locally

7 substrate modules + 1 integration layer + 4 React modes + 1
component + 3 doc artefacts + 1 internal red-team baseline + 1
thread-decisions snapshot + ~155 new tests across 9 test files.

### 7.2 Phase 2 substrate scaffold — what doesn't exist

- `substrate/graph/per_user_storage.py` (Sprint 22 deliverable)
- `substrate/ad_inventory/scaling.py` (Sprint 25+ deliverable;
  inline-sponsor card)
- `substrate/ad_inventory/programmatic.py` (Sprint 30+ conditional)
- `substrate/roles/vision_extractor/` (Sprint 30+ deferred)
- `substrate/cross_graph/writer_queue_with_dp_shuffler.py` or
  equivalent (Sprint 22 deliverable; the DP-shuffler-fronted
  writer queue specifically)
- Cross-graph `ask_an_expert.py` payment-mediation primitive
  (Sprint 25+; current `ask_expert.py` is partial)
- KMS-integrated per-graph encryption keys (Sprint 22)
- The `/me/payouts`, `/marketplace/snapshot`,
  `/operator/payouts/dashboard`, `/operator/advertiser-campaigns`,
  `/trust-center` registry-wiring endpoints (all reverted)
- `tools/stripe_connect/__init__.py` re-exports for the new payouts
  router (reverted)
- App.tsx routes for MarketplaceMetrics, CreatorPayouts,
  AdvertiserConsole, PayoutDashboard (reverted)

### 7.3 Phase 2 activation gates — what's not satisfied

- 6-month compounding demonstration (Sprint 22) — clock not started
- Sprint 22 stable + auth wired (Sprint 23-24 gate (a)) — Sprint 22 unbuilt
- One creator + one publisher accruing (Sprint 23-24 gate (b)) — zero
- External red-team report (Sprint 23-24 gate (c)) — no firm engaged
- Sprint 18 legal gate: retrieval-time gating in production + first
  publisher opted in — neither verified live
- 30 monthly-earning creators (Sprint 25+) — zero
- 5 opted-in publishers (Sprint 25+) — zero
- Six Sprint 30+ thread triggers — all DEFER, correctly

### 7.4 Phase 2 binding exit criteria across all four sprints — count

- Total binding exit criteria: 22 across the four sprints
- Met: 2 (Sprint 22 SOC 2 deferred — documented; Sprint 30+
  documented-rejection-is-the-deliverable — filed for 2026-05-21)
- Partially met: 1 (Sprint 23-24 anti-gaming attack classes caught
  by internal baseline; external firm pending)
- Unmet: 19

---

## §8 What to do next, in priority order

1. **Resolve the integration revert.** Figure out why
   `interfaces/research/api/app.py`, `tools/stripe_connect/__init__.py`,
   and `apps/reading/src/App.tsx` get reverted on every parallel
   commit. Without this fixed, the substrate is unreachable from the
   API and UI. This is one investigation, not a sprint.
2. **Commit the cumulative substrate scaffold.** 7 substrate modules
   + 1 integration layer + 4 React modes + 1 component + 3 docs +
   ~155 tests, all uncommitted. This unblocks all subsequent
   integration work and gives the operator a citable baseline.
3. **Ship Sprint 17-21 first.** Phase 2 cannot start until Phase 1
   is on `main` + deployed. The sprint-breakdown.html cover §1
   documents this status explicitly.
4. **Start the six-month compounding clock.** The operator runs
   research investigations on the workstation continuously; the
   compounding curve gets measured against the outcomes table. This
   is the upstream of everything in Phase 2.
5. **At month-3 of the six-month clock:** schedule the external
   red-team engagement so they can complete the engagement by
   month-6. Provide them `docs/sprint23_red_team_internal_baseline.md`
   + the harness reproducibility instructions.
6. **At month-6, evaluate the compounding curve.** If it has cleared
   the doc's threshold, ship Sprint 22. Else extend the
   demonstration period.

---

_This audit is the operator's record at 2026-05-22 of where Phase 2
stands. By the spec's own §1 status legend definition, Phase 2 is
not executed. ~35% of the substrate primitives are scaffolded
locally; the integration, activation, and binding exit criteria are
unmet. The substrate work done this session is necessary
preparation — not sufficient — for Phase 2 to ship._
