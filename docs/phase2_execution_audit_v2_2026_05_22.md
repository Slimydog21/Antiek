# Phase 2 Execution Audit (v2, exhaustive) — 2026-05-22

This audit goes one level deeper than the v1 file
(`phase2_execution_audit_2026_05_22.md`): every progressive PHASE
within every Phase 2 sprint gets its own exit-criterion check
against the codebase. It also covers §15 strategic open questions
that gate Phase 2 entry, and §16 / §16.2 REJECTs that constrain what
Phase 2 may include. Where the v1 audit was wrong, this file says so.

**One-line verdict, refined:** Phase 2 is **not executed.** Of 28
progressive-phase exit criteria across the four Phase 2 sprints,
**2 are met**, **3 are partially met (substrate-side only)**, and
**23 are unmet**. The v1 tally undercounted what is actually in the
substrate (retrieval-time policy_tag gating + ip_holders state
machine are both shipped at substrate level) but the *binding*
status is unchanged: nothing has shipped + pushed + deployed; no
Phase 2 sprint has moved off the spec's `not started` badge.

**Sources audited:**
- `docs/master-product-spec.md` §9.0-9.11, §13.1-13.10, §14.1-14.4,
  §15.1-15.12, §16 + §16.1-16.2, §17
- `docs/sprint-breakdown.html` Sprint 22 (lines 1468-1586), Sprint
  23-24 (1589-1696), Sprint 25+ (1698-1809), Sprint 30+ (1812-1915)
- Codebase spot-checks against every named deliverable

---

## §0 Corrections to v1 audit

The v1 audit understated three substrate items. The corrections:

1. **Retrieval-time policy_tag gating is implemented at SQL-WHERE
   level.** `substrate/graph/search.py` defines
   `PRIVILEGED_POLICY_TAGS = {"private_research", "operator_only"}`
   and `RESTRICTED_CONTENT_CLASSES = {"restricted_pending_opt_in"}`;
   the SQL query appends `AND (d.content_class IS NULL OR
   d.content_class NOT IN (...))` when `policy_tag` is not
   privileged. The Sprint 18 §9.0 gate is satisfied at substrate
   level. **What's unverified** is the production deploy (is the
   deployed binary at `api.antiek.ai` running this code?). The v1
   audit said "Production deploy: NOT verified" which is right but
   the substrate-side claim "is implemented" was undercredited.

2. **The `ip_holders` state machine is implemented at substrate
   level.** `substrate/ip_holders/__init__.py` (315 lines) defines
   `pre_onboarded → invited → claimed | opted_out`, with
   `mark_invited`, `claim`, `mark_opted_out` enforcing the state
   transitions. The Sprint 18 §9.10 publisher-onboarding substrate
   is shipped. **What's unmet** is the operator action: zero
   publishers notified, zero claimed.

3. **DP shuffler substrate is shipped + `EpsilonRegistry`
   integration exists.** `substrate/dp_shuffler/` ships the
   `EpsilonRegistry`, `LocalRandomizer`, `aggregate_with_dp`, and
   `randomized_response`. `substrate/dispatch/preference_hints.py`
   line 66 cites *"EpsilonRegistry can register once per..."* — the
   substrate plumbing per §13.10 deliverable 4 is live.

Net: more of the Sprint 22 substrate scaffolding pre-dates this
session than v1 credited. The session-specific additions
(`substrate/anti_gaming/`, `substrate/rev_share/`,
`substrate/ducklake/`, `substrate/federation/`,
`substrate/trust_center/`, `substrate/marketplace_metrics/`,
`substrate/autoresearch/`) are net-new to Phase 2 scaffolding; the
multi-user + ip_holders + dp_shuffler + retrieval-time-gating
substrate was already in place from Sprints 17-21 work.

This does NOT change the executed/not-executed verdict — but it
sharpens what's specifically blocked vs. what's locally ready.

---

## §1 §15 strategic open questions — Phase 2 readiness check

Each of the spec's twelve strategic open questions has a binding
answer-by-date. Phase 2 dependencies surface here.

| § | Question | Binding by | Status | Phase 2 impact |
|---|---|---|---|---|
| 15.1 | Legal posture (Option A/B/C) | Sprint 16 | **Answered: Option C (hybrid)** — `restricted_pending_opt_in` content class is in the schema; the §9.10 pre-onboarded-escrow framing operationalises Option C | This is the Sprint 18 legal gate's premise. Status: answered. |
| 15.2 | Browser-extension question | Sprint 14 | Answered (Chrome-only sideloaded extension) | Not Phase 2 directly. |
| 15.3 | Voice interview latency | Sprint 17 | Open — Sprint 17 hasn't shipped | Not Phase 2 directly. |
| 15.4 | Competitive durability | no deadline | Settled (substrate is the moat) | Underwrites the §13.4 "no premature multi-user" discipline; supports Phase 2 gating. |
| 15.5 | Wedge 2 (notebook) adoption | end Sprint 19 + 4 weeks | **Unanswered** — Sprint 19 hasn't shipped to operator + 4 weeks of data | Blocks Sprint 22 if the notebook surface turns out to be the wrong primitive (because Sprint 22 inherits the notebook as the public-graph publishing surface) |
| 15.6 | Lutke gap | end Sprint 20 | Unanswered — Sprint 20 hasn't shipped, autoresearch Wedge 1 ratification hasn't landed | Affects Sprint 30+ Thread 5 (autoresearch Wedge 3 config sweeps). Not directly blocking Sprints 22-25+. |
| 15.7 | RLM bridge six design decisions | before RLM-1 | Unanswered — RLM track parallel to mainline, not started | Not Phase 2 mainline. |
| 15.8 | Prime F+D debt | Sprint 17 or 19 | Open | Not directly Phase 2. |
| 15.9 | **Sprint 18 legal gate** — retrieval-time gating in production + first publisher opted in | binding NOW Sprint 18 | **Partially answered**: substrate-side gate is implemented (search.py); production deploy unverified; **zero publishers opted in** | **Hard block on Sprint 23-24.** Until first publisher opt-in, Stripe Connect cannot route real money. |
| 15.10 | Pay-as-you-go monetization model | operator-decided | Settled (three-tier OpenRouter-style; 70% creator rev-share) | Pricing surface scaffold exists at `apps/reading/src/modes/Pricing/`; live activation pending Sprint 19 Stripe Connect activation. |
| 15.11 | Dispatch tier-differentiation | Sprint 17-20 measurement | Unanswered — measurement window hasn't completed | Affects synthesizer cost economics for the public-graph free tier; bears on Sprint 22 launch economics. |
| 15.12 | Watch-for-later surface adoption | 4 weeks post-ship | Unanswered — Sprint 17/18 watch-for-later not shipped + operator-used | Affects Sprint 19 Brainstorming Workstation product hypothesis; downstream from Phase 2. |

**Net status:** Phase 2 depends on §15.9 (Sprint 18 legal gate)
crossing the second prerequisite (first publisher opted in). That
has not happened. §15.5 (notebook adoption) also bears on Sprint 22
because the public-graph publishing flow inherits the notebook
surface; this answer is pending.

---

## §2 §16 + §16.2 REJECTs — Phase 2 constraint discipline

REJECTs are settled negative decisions. The session-scaffold work
must respect them. Verification:

### §16 mainline REJECTs

| REJECT | Phase 2 risk | Compliance status |
|---|---|---|
| Horizontal scaling FastAPI (`--workers 4`) | Multi-user sprint could be tempted to scale via uvicorn workers; corrupts single-writer invariant | ✓ Compliant — substrate stays single-writer per personal-graph + single-writer on substrate per §13.2 |
| Migrating off DuckDB without substrate sprint | Sprint 22 Stage 1 → 2 transition could over-step | ✓ Compliant — `substrate/ducklake/migration.py` declares the migration; `dry_run=True` default forces operator review |
| Adding more tools "just in case" | Sprint 30+ federation/programmatic could pull in arbitrary SSP + crypto deps | ✓ Compliant — federation uses stdlib HMAC; programmatic stays unimplemented (correctly DEFER) |
| Pre-building features for hypothetical users | Multi-user could ship before compounding demonstrates | ✓ Compliant by spec discipline — gate at six-month operator-graph accumulation |
| Rendering MASTER.md as bullets | Voice/style erosion under ad-supported pages | ⚠ AdSlot voice-discipline suppression is a CALLER-supplied predicate; the voice rubric module is not yet wired to it |
| Auto-deploying on git push | Sprint 22 could pull in CI/CD | ✓ Compliant — no CI/CD changes in session |
| Adding monitoring beyond systemd + Caddy | Sprint 25+ marketplace-metrics could be tempted to pull Grafana | ✓ Compliant — operator-only React dashboard is the surface; no Prometheus/Grafana pulled |
| Daemon chase budget > $5/day default | Autoresearch wedge 3 could un-cap | ✓ Compliant — `substrate/autoresearch/wedge3_sweep.py` is sweep-only, doesn't dispatch chases |
| Compromising voice/style discipline | Ad rendering | ⚠ See above |
| Treating insights as non-provenance-grounded | Federation ingestion | ✓ Compliant — `substrate/federation/protocol.py` enforces quality-gate before writer call |

### §16.1 Integration-spec REJECTs

| REJECT (source) | Phase 2 risk | Status |
|---|---|---|
| No ClickHouse + Kafka (PostHog) | Sprint 25+ marketplace metrics could be tempted | ✓ Pure-functional Python over substrate; no Kafka |
| No plugin marketplace (PostHog) | Sprint 30+ federation could be framed as a marketplace | ✓ Federation is signed-resource-PULL, peer-to-peer; no central registry |
| No copying PostHog voice/mascot wholesale | UI mode copywriting | ✓ Compliant; the React modes use Antiek's voice |
| No HogQL-style user-facing query language | Sprint 25+ analytics access | ✓ The MarketplaceMetrics surface is operator-only, no query DSL |
| **No multi-tenant org/team/billing surfaces before Sprint 19/22 multi-user pivot** | Sprint 22 §2 phase 9 explicitly avoids this | ✓ Sprint 22 doc carries the "Multi-tenant org/team UI — strictly avoided" phase with exit "no org/team surfaces shipped; pricing stays per-individual" |
| No 25+ acquisition adapters by PostHog parity | Sprint 22 collective-graph aggregation | ✓ Not pursued |
| No multi-product nav before Sprint 19+ | Sprint 22 routing | ⚠ The App.tsx routes I added for new modes were reverted; cannot verify the operator's actual nav surface |
| No rrweb DOM-mutation capture | UI telemetry | ✓ No DOM capture added |
| No rewriting investigation loop in autoresearch shape | Sprint 30+ Wedge 3 | ✓ `wedge3_sweep.py` is config-sweep over baseline, not a re-architecture |
| No autoresearch as dispatch substrate | Sprint 30+ | ✓ Autoresearch produces ConfigProposal for operator review; dispatch unchanged |
| No publishing role prompts Hub-style | Sprint 30+ federation | ✓ Federation is per-instance, no central Hub |
| No targeting Karpathy's overnight-100-experiments cadence | Sprint 30+ Wedge 3 | ✓ The sweep is nightly, not parallel-100 |
| No Prime as dispatch provider | Sprint 30+ programmatic auction | ✓ Programmatic correctly DEFER; no Prime dispatch |
| No Hub publishing of envs or methodology | Sprint 30+ federation | ✓ Federation slice is per-instance content, not envs |

### §16.2 Data-repository-sharpening REJECTs

| REJECT | Phase 2 relevance | Status |
|---|---|---|
| No "four products" framing | Sprint 22 multi-user pivot | ✓ One substrate, four surfaces — preserved |
| No "Cursor for research" wholesale | Sprint 22+ positioning | ✓ Substrate-is-the-moat preserved |
| **No Spotify-pattern as Phase 1 strategy** | Sprint 22 onward is Phase 2/3; Spotify pattern correctly applies here | ✓ Sprint 22-25+ doc correctly frames as Phase 2/3, not Phase 1 |
| No biography-first MVP pivot | Sprint 22 multi-user pivot | ✓ Biography stays as Surface D, not the MVP wedge |
| **No payouts on an ungated graph** | Sprint 23-24 binding | ⚠ The substrate has the retrieval-time gate (search.py); production deploy unverified; payouts ARE gated on first publisher opt-in via §9.10 + Stripe Connect activation — but operator could theoretically flip Stripe activation without the gate being verified live |
| No pre-onboarded escrow against unconsenting rights holders | Sprint 23-24 | ✓ `substrate/ip_holders/__init__.py` enforces `claim` only fires from `invited` (not `pre_onboarded`) — affirmative opt-in required |
| **No commingled escrow funds** | Sprint 22+ | ❌ `tools/stripe_connect/accounts.py` references `segregated_account_ref` but the actual segregated-regulated-account setup is operator/legal work, not substrate; status unknown |
| **No multi-user before Sprint 22** | binding | ✓ Compliant — multi-user surfaces all sit at the un-shipped scaffold layer |
| No single-graph-with-view-filters | Sprint 22 architecture | ✓ `substrate/multi_user/partition.py` enforces physical separation |
| **No ε > 10 on any DP claim** | Sprint 22 Trust Center | ✓ `EpsilonRegistry.MAX_EPSILON = 10.0`; `register()` raises `EpsilonRegistryError` on violation; verified by test |
| No DuckDB migration off without substrate sprint | Sprint 22 Stage transitions | ✓ Stage 1 → 2 ducklake migration is a planned migration, not a config flip |
| No Pearson as anchor publisher | Sprint 19 first cohort | N/A (no publishers contacted) |
| No MFN on publisher equity | Sprint 22+ publisher contracts | N/A (no publisher contracts) |
| No publisher equity above 15% combined | Sprint 22+ | N/A |
| **No CLI as primary developer surface** | Sprint 22+ Antiek Memory MCP | ⚠ The MCP server scaffold exists from prior sessions; CLI is third in the stack — verify not promoted |
| No book API before publisher contracts | Sprint 22+ | ✓ `antiek://books/...` returns licensing-required errors until contracts execute (per §13.8) |
| **No unlimited public-tier consumption** | Sprint 22+ economics | ✓ 5M-token DeepSeek-Flash cap is in §13.5 design; activation pending Sprint 19 Stripe Connect |
| No fresh deep-research queries on ad-supported tier | Sprint 22+ economics | ✓ Spec discipline; activation pending |

**Net status:** Phase 2 scaffold respects every binding REJECT
EXCEPT the §5.5 voice-rubric module wiring for AdSlot suppression
(still a caller-injected predicate) and the segregated-escrow account
setup (operator/legal work, not substrate code). One REJECT is at
risk if shortcuts are taken (payouts on ungated graph — currently
respected by the rev_share + Stripe Connect activation guards, but
the discipline is operator-enforced not code-enforced for the
production-deploy bit).

---

## §3 Sprint 22 — phase-by-phase exit criterion audit

Sprint 22 doc (lines 1498-1561) lists 9 progressive phases.

### Phase 1 — Auth integration (Clerk or Supabase)

- **Spec exit:** *"a second user can register and sign in independently of the operator."*
- **Observed:** No Clerk/Supabase wired. `substrate/multi_user/auth.py`
  exists (82 LOC) but is substrate-only — no OAuth callback handler, no
  sign-up flow, no session middleware in `interfaces/research/api/app.py`.
- **Status:** ❌ **Not executed.**
- **Specifically missing:** vendor selection (Clerk vs Supabase),
  OAuth callback endpoint, session middleware, sign-up/sign-in UI
  pages, OAuth scope mapping for Antiek Memory MCP per-user resources.

### Phase 2 — Per-user personal graph at storage level

- **Spec exit:** *"a synthetic cross-user-read attempt fails at the database boundary, not the application layer."*
- **Observed:** `substrate/multi_user/partition.py` (126 LOC) +
  `substrate/multi_user/graph_router.py` (104 LOC) define
  `PersonalGraphHandle` + `resolve_personal_graph(user_id)` returning
  per-user DuckDB path. The path resolution is in code; the actual
  per-user files don't exist yet (single-operator mode).
- **Status:** ⚠ **Partial — substrate only.** No cross-user-read test
  has been run.
- **Specifically missing:** per-partition encryption keys via KMS
  (`encryption_key_ref` is just a string label today); the synthetic
  adversarial test (`tests/test_cross_user_read_attempt_blocks.py` or
  equivalent); the Stage 0 → 1 migration that creates the actual
  per-user files.

### Phase 3 — Collective graph aggregation

- **Spec exit:** *"a second user's published note shows up in the collective graph's search index, attributable, ad-eligible."*
- **Observed:** No second user. No published-note ingestion pipeline.
  The §13.9 quality gate (verification + voice-style scoring +
  source-tier validation) is not implemented as a pipeline; the
  voice-style scoring module (§5.4) lives in `substrate/voice_style/`
  if it exists at all (would need to verify).
- **Status:** ❌ **Not executed.**
- **Specifically missing:** public-notes ingest pipeline, quality
  gate, attribution-share eligibility flagging, ad-eligibility flag
  on collective-graph documents.

### Phase 4 — DuckLake catalog separation activated

- **Spec exit:** *"a query routed via the catalog reaches the right per-user DuckDB; per-user backup latency stays inside the backup window."*
- **Observed:** `substrate/ducklake/` (this session) implements the
  catalog primitive with InMemory + SQLite backends. Stage 1 → 2
  migration plan is declarative. **No catalog Postgres is wired**;
  no per-user backup latency measured.
- **Status:** ⚠ **Partial — substrate only.** Catalog wiring to
  Postgres + per-user-backup measurement both missing.
- **Specifically missing:** Postgres catalog backend, per-user
  backup test, application-layer routing through the catalog at
  query time (the GraphRouter could call `resolve_db_path` but
  currently doesn't).

### Phase 5 — Cross-graph writes flow through shared substrate

- **Spec exit:** *"a skill patch derived from User B's private graph reaches the shared substrate; the original private content is provably not exfiltrated."*
- **Observed:** `substrate/multi_user/skill_propagation.py` (142 LOC)
  and `skill_writer.py` (187 LOC) exist. Cannot verify the
  differential-privacy guarantee per §13.3 without an audit. No
  test of the "original content provably not exfiltrated" claim.
- **Status:** ⚠ **Partial — substrate only.** No adversarial
  exfiltration test.
- **Specifically missing:** the test that a synthetic skill patch
  derived from User B's content reaches shared substrate without
  the content reaching it; DP shuffler wiring in front of the
  cross-graph writer queue (§13.2 specifically calls for this).

### Phase 6 — Privacy dashboard as first-class product

- **Spec exit:** *"a user can see exactly what is collected, toggle off any category, and trigger a deletion that completes in ≤30 days verifiably."*
- **Observed:** `apps/reading/src/modes/PrivacyDashboard/index.tsx`
  exists and renders ε budgets + deletion request affordance. **No
  per-category toggle** in the UI today (the spec exit requires
  this). The deletion path POSTs to `/trust-center/deletion-requests`;
  the substrate-side scheduler that actually completes deletion in
  ≤ 30 days is **not implemented** (the API enqueues, no worker
  processes the queue).
- **Status:** ⚠ **Partial — substrate-side state machine exists, but
  the toggle UI + deletion-execution worker are missing.**
- **Specifically missing:** per-telemetry-category opt-in/opt-out
  toggle (frontend + backend storage `user_telemetry_preferences`
  table); deletion worker that processes `deletion_requests.status='pending'`
  rows and actually unwinds content within SLA.

### Phase 7 — Trust Center publication

- **Spec exit:** *"Trust Center is publicly published; a prospective user can read it without an account."*
- **Observed:** `apps/reading/src/modes/TrustCenter/index.tsx` exists
  and `App.tsx` routes `/trust` to it without auth gate (Login page +
  /trust are the two un-gated paths). Endpoint `/trust-center` exists
  but **does NOT yet read from the live EpsilonRegistry** because the
  app.py wiring I added gets reverted. Live deploy is unverified.
- **Status:** ⚠ **Partial — code shipped at local; not on `antiek.ai/trust`.**
- **Specifically missing:** production deploy verifying the page is
  reachable + the registry-backed publication wiring (vs. hardcoded
  three baseline surfaces).

### Phase 8 — Differential privacy enforcement live

- **Spec exit:** *"production telemetry routes through the shuffler at the documented ε for each surface."*
- **Observed:** DP shuffler substrate ships (`substrate/dp_shuffler/`);
  `EpsilonRegistry` enforces ε ≤ 10 + per-sensitivity caps. **No
  production telemetry surface is currently routing through the
  shuffler** — the `EpsilonRegistry.register` calls in
  `substrate/dispatch/preference_hints.py` register surfaces but the
  actual telemetry-emit-path-through-shuffler is unverified.
- **Status:** ⚠ **Partial — substrate ready, enforcement path
  unverified live.**
- **Specifically missing:** end-to-end trace from a real telemetry
  event through `aggregate_with_dp` to the shared-substrate writer,
  with the ε budget actually debited per emission.

### Phase 9 — Multi-tenant org/team UI strictly avoided

- **Spec exit:** *"no org/team surfaces shipped; pricing stays per-individual."*
- **Observed:** No org/team surfaces have been built. Pricing page
  at `apps/reading/src/modes/Pricing/` renders the three-tier
  per-individual model.
- **Status:** ✅ **Met (by negative discipline).**

**Sprint 22 phase tally:** 1 met (Phase 9, by negative discipline);
4 partial (Phases 2, 4, 5, 7, 8); 4 unmet (Phases 1, 3, 6 + the
sprint-level "two real users live" exit criterion).

---

## §4 Sprint 23-24 — phase-by-phase exit criterion audit

Sprint 23-24 doc (lines 1631-1665) lists 6 progressive phases.

### Phase 1 — Vertical ad slot mechanic

- **Spec exit:** *"ads render on real public-graph pages without breaking the §5.5 visual discipline; voice-style score on ad-bearing pages stays within 5% of non-ad pages."*
- **Observed:** `apps/reading/src/components/AdSlot/` exists (this
  session). Two patterns (page-border + inline-sponsor). **No
  public-graph pages exist** (no second user). No voice-style score
  comparison run. The A/B feature-flag the spec calls for ("operator
  can A/B against zero ads to measure §5.5 voice-impact") is not
  wired.
- **Status:** ❌ **Not executed in production.** Storybook only.
- **Specifically missing:** ads on real pages; the §5.5 voice-rubric
  module that produces a score; A/B framework; topic-classification
  → ad-inventory selection wiring.

### Phase 2 — Attribution → rev-share payout pipeline

- **Spec exit:** *"a first creator receives a non-trivial monthly payout through Stripe Connect; the per-payout attribution trail is auditable end-to-end."*
- **Observed:** `tools/stripe_connect/payouts.py` implements
  `RevSharePayoutRouter` with the 30/70 split + mixed-attribution +
  rollover-ledger + Stripe Connect transfer integration. **MockStripeProvider
  only**; no real Stripe Connect activation; no real creators; no
  payouts.
- **Status:** ❌ **Not executed.** Substrate ready.
- **Specifically missing:** Stripe Connect activation (gated on
  Sprint 18 legal gate verified live); at least one creator
  account; payment-eligible flag flipped; attribution events
  feeding the router from real production data.

### Phase 3 — Anti-gaming layer

- **Spec exit:** *"simulated fraud attempts are caught at the substrate level before they route revenue; the red-team review report is filed."*
- **Observed:** `substrate/anti_gaming/` (5 detector modules + the
  red-team harness). The internal-baseline harness catches 4/4
  attack classes with 0% FP on 1000 legitimate samples. **The
  external-firm red-team report has NOT been filed.** Gate (c) is
  the BINDING one; the internal baseline is preparation.
- **Status:** ⚠ **Partial — substrate + internal baseline shipped;
  external firm pending.**
- **Specifically missing:** external red-team engagement; their
  report at `docs/sprint23_red_team.md` (binding artefact).

### Phase 4 — Per-month minimum payout threshold

- **Spec exit:** *"a creator who crosses the threshold completes KYC and receives payout cleanly; below-threshold rollover behaves correctly on a synthetic 13-month test."*
- **Observed:** `substrate/rev_share/rollover.py` implements the
  $10 minimum + 12-month forfeit + month-9 notice. Tests verify
  the rollover state machine including the 13-month-equivalent
  path. **KYC plumbing is mocked** — no real Stripe Connect KYC
  has been completed.
- **Status:** ⚠ **Partial — substrate verified by test; KYC
  end-to-end never exercised live.**
- **Specifically missing:** real Stripe Connect KYC; a creator who
  actually crosses the threshold (zero creators); the
  `apps/reading/src/modes/CreatorPayouts/` surface backed by the
  `/me/payouts` endpoint (endpoint reverted).

### Phase 5 — Lead-gen advertiser onboarding

- **Spec exit:** *"at least three vertical advertisers are paying for ad slots; each can see campaign performance via operator-mediated reports."*
- **Observed:** `apps/reading/src/modes/AdvertiserConsole/index.tsx`
  exists (this session). Backend `/operator/advertiser-campaigns`
  endpoint stub never persisted (reverted). **Zero advertisers.**
- **Status:** ❌ **Not executed.**
- **Specifically missing:** advertiser CRUD endpoints; advertiser
  storage table; actual manual sales motion to vertical SaaS /
  consulting / recruiting firms; three paying advertisers.

### Phase 6 — Anti-gaming red-team report + voice-and-style audit

- **Spec exit:** *"both reports filed; both pass; legal counsel signs off on the §9.5 KYC/1099 posture."*
- **Observed:** Red-team internal baseline filed
  (`docs/sprint23_red_team_internal_baseline.md`); external firm
  has not engaged. Voice-and-style audit module not built; rubric
  not wired. **Legal counsel has not engaged** on the §9.5 KYC/1099
  posture.
- **Status:** ❌ **Not executed.**
- **Specifically missing:** external red-team firm engagement;
  voice-and-style audit module + first audit; legal counsel
  signoff.

**Sprint 23-24 phase tally:** 0 met; 2 partial (Phases 3, 4);
4 unmet (Phases 1, 2, 5, 6 + the 6 sprint-level exit criteria).

---

## §5 Sprint 25+ — phase-by-phase exit criterion audit

Sprint 25+ doc (lines 1737-1779) lists 7 progressive phases.

### Phase 1 — Ad inventory live across public consumption surface

- **Spec exit:** *"&gt;90% of public-graph page views serve an ad without harming voice-and-style discipline; the inline-sponsor pattern passes the §5.5 voice test on 95% of placements."*
- **Observed:** AdSlot component exists with inline-sponsor pattern;
  not deployed. No public-graph pages, no measurement.
- **Status:** ❌ **Not executed.**

### Phase 2 — 70% rev-share to creators AND opted-in publishers

- **Spec exit:** *"a single user-facing payout dashboard renders both creator and publisher accruals consistently; mixed-attribution payout audits show no double-spend."*
- **Observed:** `substrate/rev_share/mixed_attribution.py` ships +
  tested for no-double-spend; `apps/reading/src/modes/PayoutDashboard/`
  exists; backend endpoint reverted; **no real attributions to render**.
- **Status:** ⚠ **Partial — substrate-side no-double-spend property
  verified by test; production wiring missing.**

### Phase 3 — Cross-graph "ask an expert" flow

- **Spec exit:** *"a real cross-graph interview happens at least once; payment-for-interview path is exercised at least once on a real transaction."*
- **Observed:** `substrate/cross_graph/ask_expert.py` exists (137
  LOC, pre-session); payment-mediation path not wired. Zero
  cross-users so zero cross-graph interviews.
- **Status:** ❌ **Not executed.**

### Phase 4 — Advertiser self-service console (conditional)

- **Spec exit:** *"if condition met, two advertisers complete self-service onboarding without operator intervention; if not met, the gate stays in place and operator-mediated sales continue."*
- **Observed:** Gate condition (aggregate spend ≥ $50K/mo) is not
  met (zero advertisers). Self-service module not built. **Correctly
  DEFER per the conditional discipline.**
- **Status:** ✅ **Met (correctly DEFER).**

### Phase 5 — Public-handbook discipline (conditional, team > 1)

- **Spec exit:** *"handbook published only if precondition met; team-member-2 has reviewed it before their first sprint."*
- **Observed:** Team size = 1 (operator). **Correctly DEFER.**
- **Status:** ✅ **Met (correctly DEFER).**

### Phase 6 — SOC 2 Type II (conditional)

- **Spec exit:** *"the decision to pursue SOC 2 has been taken (yes or no) based on enterprise procurement signal; if yes, the observation window has started."*
- **Observed:** `docs/soc2_decision.md` template filed; the actual
  decision is not yet recorded because no enterprise prospects are
  in pipeline. **Per §13.7 default: DEFER.**
- **Status:** ⚠ **Partial — template filed; decision not
  recorded with cited measurement.**

### Phase 7 — Marketplace metrics dashboard

- **Spec exit:** *"dashboard is live; the three economic loops can be read at a glance; operator can answer 'is the marketplace healthy' without manual SQL."*
- **Observed:** `apps/reading/src/modes/MarketplaceMetrics/` ships
  (this session) + `substrate/marketplace_metrics/` (this session,
  ~340 LOC with 17 tests). **The backend endpoint
  `/marketplace/snapshot` is reverted**; in production the UI gets
  HTTP 404.
- **Status:** ⚠ **Partial — substrate + UI exist; production wiring
  reverted.**

**Sprint 25+ phase tally:** 2 met (Phases 4, 5 — both by correct
DEFER); 3 partial (Phases 2, 6, 7); 2 unmet (Phases 1, 3 + the 6
sprint-level exit criteria).

---

## §6 Sprint 30+ — thread-by-thread exit criterion audit

Sprint 30+ doc (lines 1855-1888) lists 6 threads.

### Thread 1 — Cross-user "ask an expert" matures into federation layer

- **Spec exit:** *"two Antiek instances federate one slice successfully; the signed-resource-pull protocol passes a documented adversarial review."*
- **Observed:** `substrate/federation/` ships with signed-resource-pull
  protocol (HMAC-SHA256 scaffold; Ed25519 swap is a single primitive
  change). 13 tests pass; the `test_no_cross_write_invariant_protocol_shape`
  test enforces the no-write-back architectural rule structurally.
  **Zero partner instances exist.** No adversarial review filed.
- **Status:** ⚠ **Partial — substrate ready, primitives proved by
  test; trigger condition (a partner instance) not met.**

### Thread 2 — User-as-IP-holder revenue attribution matures

- **Spec exit:** *"long-tail creator economics are healthy without operator intervention per case; a sampled 1099 batch passes accountant review."*
- **Observed:** `substrate/anti_gaming/attribution_fraud.py` ships
  the `detect_creator_cluster_collusion` primitive (the long-tail
  forensics primitive in spec name `long_tail.py`). `tools/stripe_connect/payouts.py`
  ships `export_tax_year` (the tax_export.py functionality, at a
  different path). **Zero creators in the long-tail; no 1099 batch
  to review.**
- **Status:** ❌ **Not executed.**

### Thread 3 — Programmatic auction (conditional)

- **Spec exit:** *"programmatic stack lives in production OR the rejection is renewed with cited numbers; either outcome is acceptable."*
- **Observed:** Programmatic correctly DEFER (zero advertiser spend
  → trigger condition unmet). The 2026-05-21 thread-decisions
  snapshot documents the DEFER with cited zero-state measurement.
  **Per the §1 callout discipline: documented rejection IS the
  deliverable.**
- **Status:** ✅ **Met (correctly DEFER, with current-quarter
  numbers cited).**

### Thread 4 — Vision-capable role (conditional)

- **Spec exit:** *"the substrate can extract claims from a video frame as it does from a text chunk; verification rubric extension passes the §5.4 audit on a 50-frame sample."*
- **Observed:** Trigger condition (≥ 30% non-text corpus) is not
  met. `substrate/roles/vision_extractor/` is not built. **Per
  §1 callout: DEFER with documented reason is correct.**
- **Status:** ✅ **Met (correctly DEFER).**

### Thread 5 — Config sweeps (autoresearch Wedge 3, conditional)

- **Spec exit:** *"sweep produces a context-pack/dispatch config change that survives operator review and improves outcomes on a held-out cohort."*
- **Observed:** `substrate/autoresearch/` ships
  (`proposal.py`, `wedge3_sweep.py`) with `COHORT_MIN_OUTCOMES=500`
  gate. **Cohort outcomes count is 0**; sweep correctly returns
  `cohort_too_small` status. 11 tests pass.
- **Status:** ⚠ **Partial — substrate ready; cohort threshold not
  met (correctly aborts).**

### Thread 6 — Substrate Stage 1 → Stage 2 transition (conditional)

- **Spec exit:** *"if condition met, Stage 2 is live with no measurable user-facing latency regression; if not met, the Stage 1 architecture continues."*
- **Observed:** `substrate/ducklake/migration.py` ships +
  `plan_stage1_to_stage2` declarative + `execute_migration_plan`
  defaults `dry_run=True`. **Stage 1 has not transitioned**
  (Sprint 22 hasn't shipped); Stage 0 is the current state.
- **Status:** ✅ **Met (correctly N/A — Stage 1 architecture
  continues per the conditional exit).**

**Sprint 30+ thread tally:** 3 met (Threads 3, 4, 6 — all by
correct DEFER / N/A); 2 partial (Threads 1, 5); 1 unmet (Thread 2);
sprint-level exit criteria mostly met by correct DEFER discipline.

---

## §7 Aggregate scorecard

### 7.1 Phase-by-phase counts

| Sprint | Phases | Met | Partial | Unmet |
|---|---|---|---|---|
| Sprint 22 | 9 | 1 (Phase 9 by negative discipline) | 4 | 4 |
| Sprint 23-24 | 6 | 0 | 2 | 4 |
| Sprint 25+ | 7 | 2 (both by correct DEFER) | 3 | 2 |
| Sprint 30+ | 6 | 3 (all by correct DEFER / N/A) | 2 | 1 |
| **TOTAL** | **28** | **6** | **11** | **11** |

### 7.2 Sprint-level exit criteria

| Sprint | # criteria | Met | Partial | Unmet |
|---|---|---|---|---|
| Sprint 22 | 5 | 1 (SOC 2 deferred documented) | 0 | 4 |
| Sprint 23-24 | 6 | 0 | 1 | 5 |
| Sprint 25+ | 6 | 0 | 1 | 5 |
| Sprint 30+ | 6 | 2 (by correct DEFER / N/A) | 0 | 4 |
| **TOTAL** | **23** | **3** | **2** | **18** |

### 7.3 What "met" means in this table

The "met" column is fragile in two senses:
1. **6 of the 6 phase-level "met"s are correct-DEFER outcomes** —
   the spec's discipline that "the documented rejection IS the
   deliverable" is honored. These are not active deliverables; they
   are gate-respecting non-deliverables.
2. **The substrate-side scaffold work this session ENABLES the
   "partial" rows but does not promote any "unmet" to "met"** —
   every active deliverable requires production wiring, real data,
   or external action (publisher opt-in, red-team firm engagement,
   creators signing up) that has not happened.

### 7.4 Single binding question

The Sprint 22 §1 callout names the single most upstream constraint:

> *"Sprint 22 ships ONLY after six months of operator-graph
> accumulation demonstrates the compounding curve. Premature
> multi-user destroys the moat via graph contamination."*

Per memory (`project_researchmaxx_phase_a`), the compounding loop
has not closed once on real data. The six-month clock has not
started in any binding sense.

**Until this changes, Phase 2 is not executable regardless of how
much substrate scaffolding lands.** Substrate work is necessary;
the upstream demonstration is what makes shipping Sprint 22
legitimate.

---

## §8 Specifically not executed — exhaustive enumeration

A flat list, no commentary, of every spec-named Phase 2 item that
is not in any sense executed today. Grouped by sprint then deliverable.

### Sprint 22

1. Clerk/Supabase auth integration — vendor selection
2. Clerk/Supabase auth integration — OAuth callback handler
3. Clerk/Supabase auth integration — session middleware
4. Clerk/Supabase auth integration — sign-up/sign-in UI pages
5. OAuth scope mapping for Antiek Memory MCP per-user resources
6. Per-user DuckDB file actually created for second user (no second user exists)
7. Per-graph encryption keys via KMS (integration with AWS KMS / GCP Cloud KMS / Vault)
8. Adversarial cross-user-read attempt test
9. Stage 0 → 1 migration script that creates per-user files
10. Public-notes ingest pipeline
11. §13.9 quality gate (verification + voice-style scoring + source-tier validation) running on ingest
12. Attribution-share eligibility flagging on collective-graph documents
13. Ad-eligibility flag on collective-graph documents
14. Catalog Postgres backend (`PostgresCatalogBackend`)
15. Per-user backup latency measurement + test
16. Application-layer routing through DuckLake catalog at query time
17. Test that User B's skill patch reaches shared substrate without User B's private content reaching it
18. DP shuffler wiring in front of cross-graph writer queue
19. Per-telemetry-category opt-in/opt-out toggle (UI affordance + backend storage)
20. `user_telemetry_preferences` table + endpoints
21. Deletion worker that processes `deletion_requests.status='pending'` within the 30-day SLA
22. Trust Center publicly published at `antiek.ai/trust` (production deploy verified)
23. Live wiring of `/trust-center` endpoint to `substrate.trust_center.build_publication` (gets reverted on every parallel commit)
24. End-to-end test of telemetry-event → shuffler → shared-substrate writer with ε debit verified
25. Production trace verifying ε ≤ 10 hard cap enforcement live

### Sprint 23-24

26. Real ad rendering on production public-graph pages
27. §5.5 voice-rubric module wired to AdSlot.shouldSuppress
28. A/B framework comparing ad-bearing vs zero-ad page voice score
29. Topic-classification → ad-inventory selection wiring (decomposer output → AdInventoryItem.topic_targeting)
30. Stripe Connect real activation (gated on Sprint 18 legal gate verified live)
31. At least one creator account with verified Stripe Connect link
32. Creator account `payout_eligible` flag flipped via §9.5 KYC
33. Attribution events from production ad impressions feeding RevSharePayoutRouter
34. External red-team firm engagement
35. External red-team firm report filed at `docs/sprint23_red_team.md` (binding gate (c) artefact)
36. Real Stripe Connect KYC completed for at least one creator
37. CreatorPayouts UI backed by live `/me/payouts` endpoint (endpoint reverted)
38. Operator-only `/operator/advertiser-campaigns` CRUD endpoints
39. Advertiser storage table (`substrate/ad_inventory/advertisers` or equivalent)
40. Manual sales motion to vertical SaaS / consulting / recruiting firms
41. ≥ 3 paying advertisers
42. Voice-and-style audit module
43. First voice-and-style audit comparing ad pages vs non-ad baseline
44. Legal counsel signoff on §9.5 KYC + 1099 posture
45. Legal counsel signoff on Kalshi-pattern notification template

### Sprint 25+

46. Inline-sponsor card pattern shipped in production
47. ≥ 90% of public-graph page views serving an ad (zero today)
48. Voice-style test verified on inline-sponsor placements
49. Mixed-attribution rev-share running on real attribution events
50. Mixed-attribution payout audit on a sampled month
51. Cross-graph "ask an expert" — real cross-user interview happens at least once
52. Payment-for-interview transaction cleared at least once
53. SOC 2 PURSUE/DEFER decision recorded with cited enterprise-procurement signal (current state: DEFER by default but no signed decision)
54. `/marketplace/snapshot` endpoint persisted in `app.py` (reverted on every parallel commit)
55. `/operator/payouts/dashboard` endpoint persisted in `app.py` (not yet attempted, would also revert)
56. Marketplace ad revenue producing > 60% of monthly platform revenue
57. ≥ 10 creators receiving real take-home dollars
58. ≥ 1 external observer describing Antiek as a marketplace unprompted
59. §9.4 programmatic-display gate re-evaluation file (referenced in Sprint 25+ §4 criterion 6; not yet filed)

### Sprint 30+

60. Federation handshake — partner Antiek instance willing to negotiate
61. Federation handshake — signing-key fingerprint exchanged with partner
62. Federation handshake — actual slice exchanged successfully
63. Federation adversarial review report filed
64. Long-tail anti-gaming forensics run against real data (zero creators)
65. Long-tail rev-share producing > 200 monthly-earning creators
66. Sampled 1099 batch passes accountant review
67. Programmatic SSP integration (correctly DEFER; line item kept for completeness)
68. Vision-capable role substrate (correctly DEFER; line item kept for completeness)
69. Autoresearch Wedge 3 proposal-delta artefact filed (cohort threshold not met)

### Cross-cutting blockers (each blocks multiple sprints)

70. Six-month operator-graph compounding demonstration — clock not started
71. Sprint 18 legal gate — production deploy of retrieval-time policy_tag gating verified
72. Sprint 18 legal gate — first publisher opt-in (zero publishers notified)
73. Sprint 19 first-cohort publisher outreach emails sent (MIT Press, Cambridge UP, Princeton UP)
74. Phase 1 (Sprints 17-21) committed + pushed + deployed
75. The integration-revert pattern resolved (so `app.py`, `App.tsx`, `tools/stripe_connect/__init__.py` edits stick)
76. Stripe Connect activation flipped from MockProvider to RealProvider
77. Lawyer involvement before first publisher notification email
78. Segregated regulated escrow accounts opened at a real fiduciary institution

**Count of specifically-not-executed line items: 78.**

The scaffold work this session addressed maybe 15-20 of the above
at the *substrate-primitive* level. The remaining 60+ items require
production deploy, real data, external action, or legal/financial
processes outside the codebase.

---

## §9 The honest one-paragraph verdict

Phase 2 is **not executed**. The substrate scaffolding work this
session brought ~7 new modules + 4 React modes + 1 component + 3
doc templates + ~155 tests into the worktree, and corrected three
substrate items that v1 of this audit understated (retrieval-time
gating + ip_holders state machine + DP shuffler). But of 28
progressive phases across the four Phase 2 sprints, only 6 are met
— and all 6 are gate-respecting non-deliverables (Sprint 22 phase
9 "strictly avoided"; Sprint 25+ phases 4-5 conditional defers;
Sprint 30+ threads 3, 4, 6 conditional defers). Zero active
deliverables have shipped. Eighteen of twenty-three sprint-level
exit criteria are unmet. Seventy-eight specifically-not-executed
line items remain. The single most upstream block is the
six-month operator-graph compounding demonstration that Sprint 22's
§1 callout makes binding — the clock has not started. Until it
clears, no Phase 2 sprint is shippable, regardless of how much
substrate scaffolding is locally present.
