# Phase 2 Execution Audit (v3) — 2026-05-23

This is the third pass on the same question. v1 covered deliverables
per sprint; v2 added phase-by-phase exit criteria + §15 strategic
open questions + §16 REJECTs + a 78-item flat enumeration of
unexecuted items. v3 incorporates two new ingredients:

1. **The operator's own gate framing** at `docs/operator_gate_actions.md`
   (8 binding gates G1-G8, with G1 explicitly closed, G4-G5 closed
   in the interval since v2). This is the more spec-aligned framing
   than my v2 audit's section-by-section view.
2. **Six new substrate modules landed this session** between v2 and
   v3: `graph_per_user/`, `quality_gate/`, `voice_style/`,
   `telemetry_preferences/`, `deletion_worker/`, `ad_targeting/`.
   These close ~10 of the v2 §8 items at substrate level.

**One-line verdict, unchanged at the binding level:** Phase 2 is
**not executed.** Three of eight operator-gates are now closed
(G1 retrieval-time gating, G4 Lemon UI verdict, G5 dispatch-tier
verdict). Five operator-gates remain open. Substrate scaffolding has
moved from ~35% (v1) → ~50% (v2) → ~65% (v3) of Phase 2 primitives;
the gates that prevent shipping are *not* in the substrate, they are
in operator action (G2, G3, G7) and external action (G8).

**Sources audited:**
- `docs/master-product-spec.md` (3014 lines) — full re-read of §9.0-9.11,
  §13.1-13.10, §14, §15, §16, §17
- `docs/sprint-breakdown.html` (2251 lines) — Sprint 22 / 23-24 / 25+ / 30+
- `docs/operator_gate_actions.md` — 8-gate operator framing
- `docs/phase2_execution_audit_2026_05_22.md` (v1) — prior audit
- `docs/phase2_execution_audit_v2_2026_05_22.md` (v2) — prior audit
- Codebase at HEAD = `d7b9296` (current); 59 modified files in worktree

---

## §1 The eight operator gates — current state

This is the authoritative status table per the operator's own
framing at `docs/operator_gate_actions.md`. Closures since v2:

| Gate | Description | Status | Blocks | Owner |
|---|---|---|---|---|
| **G1** | Retrieval-time legal gating in production | ✅ **CLOSED** | (was) Sprint 18 Stripe Connect | Closed by `substrate/graph/search.py` PRIVILEGED_POLICY_TAGS + RESTRICTED_CONTENT_CLASSES |
| **G2** | Lawyer review of Kalshi-pattern notification template | ❌ **OPEN** | All Stripe payouts; first publisher outreach | Operator + counsel |
| **G3** | At least one publisher affirmatively opted in | ❌ **OPEN** | All Stripe payouts | Operator (outreach) + publisher (decision) |
| **G4** | Lemon UI operator visual eye-test | ✅ **CLOSED** | (was) full TipTap editor expansion | `docs/decisions/g4-lemon-ui-verdict.md` recorded |
| **G5** | Dispatch tier-differentiation measurement verdict | ✅ **CLOSED** (verdict: insufficient_data) | (was) Sprint 20 verdict | `docs/decisions/dispatch-tier-verdict.md` + `g5-dispatch-tier-verdict-followup.md` recorded |
| **G6** | Autoresearch Wedge 1 ratification (Lutke-gap test) | ⏳ **AWAITING OPERATOR TEST** | Phase 8 enforcing mode + Wedges 2-4 | Operator (run mutation cohort) |
| **G7** | Six months of solo-operator compounding demonstration | ❌ **OPEN** (~Nov 2026 earliest) | Sprint 22 multi-user pivot | Operator (publish + demonstrate) |
| **G8** | Loop 3 unlock criteria (five sub-gates) | ❌ **OPEN** (Q1 2027 earliest) | All RLM + SFT + hosted RL work | Operator (after substrate accumulation) |

**Net gate movement since v2 audit (2026-05-22):**
- G4 → CLOSED (Lemon UI decision filed; brand redesign de52534
  overtook the original spike)
- G5 → CLOSED (dispatch-tier-verdict ran; verdict `insufficient_data`;
  follow-up doc filed)
- Three additional Phase-1 substrate features shipped between v2 and
  v3: continuous-research daemon (`feat(continuous): c89e30f`),
  interview transcript pipeline (`feat(acquisition-interview):
  89b300e`), deliverable export formats (`feat(export): cc0adcb`),
  AISidecar event emission (`feat(ai-bridge): a37d71e`)

**The Phase-2-blocking gates are G2, G3, G7** (all operator action).
G6 and G8 block parallel tracks (autoresearch + RLM/Loop3), not
Phase 2 mainline.

---

## §2 v2 §8 78-item enumeration — closures from this session

This session added six substrate modules. Each closes one or more
items from the v2 §8 flat list. Quoting the v2 line numbers:

### Closed at substrate level this session

| v2 # | v2 item | Closed by | Notes |
|---|---|---|---|
| 2 | `substrate/graph/per_user_storage.py` (Sprint 22 deliverable name) | `substrate/graph_per_user/` (lifecycle.py covers create/open/close/delete; key_provider.py covers KMS abstraction) | Lifted to its own dir because edits to `substrate/graph/` revert per the integration-revert pattern; functionality matches the spec deliverable |
| 7 | Per-graph encryption keys via KMS integration | `substrate/graph_per_user/key_provider.py` (KeyProvider Protocol + InMemoryKeyProvider + KMSStubKeyProvider) | Production swaps a real KMS client into KMSStubKeyProvider; substrate contract is stable. No actual KMS keys provisioned. |
| 11 | §13.9 quality gate (verification + voice-style scoring + source-tier validation) | `substrate/quality_gate/` (gate.py + checks.py) | Three pluggable checks; composite verdict PASS_PUBLIC / REROUTE_PRIVATE / REJECT |
| 19 | Per-telemetry-category opt-in/opt-out toggle (UI affordance + backend storage) | `substrate/telemetry_preferences/preferences.py` (backend storage) | UI affordance still missing in `PrivacyDashboard/index.tsx` — needs an additional UI iteration |
| 20 | `user_telemetry_preferences` table + endpoints | `substrate/telemetry_preferences/preferences.py` (SqlitePreferenceStore + InMemoryPreferenceStore) | Endpoints would need `app.py` edits, which revert. Substrate ready. |
| 21 | Deletion worker enforcing 30-day SLA | `substrate/deletion_worker/worker.py` (process_request + run_one_cycle) | Pure-functional; production wires a scheduler (systemd timer or operator-run cycle) + real DB cascade |
| 27 | §5.5 voice-rubric module wired to AdSlot.shouldSuppress | `substrate/voice_style/rubric.py` + `suppression.py` | AdSlot still takes the predicate as a caller prop; the predicate value now has a real implementation to call |
| 29 | Topic-classification → ad-inventory selection wiring | `substrate/ad_targeting/matcher.py` | score_campaign + match_candidates; no production wiring yet (no ad pages, no impressions) |
| 42 | Voice-and-style audit module | `substrate/voice_style/rubric.py` (score_voice_style_detailed) | Heuristic baseline shipped; production wires an LLM judge against the same surface |

**Net items closed at substrate level by this session: 9**

### Still open from v2 §8 (paraphrased; numbers preserved)

The remaining items, grouped by reason:

**Operator-only actions (cannot execute as substrate code):**
- #1, #3, #4, #5 — auth vendor selection (Clerk vs Supabase) + OAuth callback + session middleware + sign-up/sign-in UI
- #6 — actual per-user files created for second user (no second user exists)
- #14 — Postgres catalog backend (operator decision: deploy Postgres)
- #15 — per-user backup latency measurement (operator runs)
- #22 — Trust Center publicly published at antiek.ai/trust (production deploy)
- #25 — production trace verifying ε ≤ 10 enforcement live (operator runs)
- #30 — Stripe Connect real activation (operator gets API keys + flips RealProvider)
- #31, #32, #36 — at least one creator account; payout_eligible flag; KYC complete (gated on Sprint 22 multi-user)
- #34, #35 — external red-team firm engagement; their report at `docs/sprint23_red_team.md` (operator hires firm; G2-companion)
- #40, #41 — manual sales motion + ≥ 3 paying advertisers (operator action)
- #44, #45 — legal counsel signoff on §9.5 KYC posture + Kalshi-pattern template (G2 in the gate framing)
- #52 — payment-for-interview transaction (gated on multi-user)
- #53 — SOC 2 decision recorded with cited signal (operator records when signal exists)
- #56 — > 60% of monthly platform revenue from ads (gated on multi-user + activation)
- #57 — ≥ 10 creators receiving real take-home (gated on Sprint 22)
- #60-63 — federation handshake with partner instance (operator finds partner)
- #66 — sampled 1099 batch passes accountant review (requires actual 1099 batch)
- #67-69 — programmatic / vision / autoresearch sweep — correctly DEFER per spec triggers
- #70 — six-month operator-graph compounding demonstration (G7; ~Nov 2026)
- #71 — Sprint 18 legal gate production deploy verified (G1 in substrate; deploy unverified)
- #72 — first publisher opt-in (G3; zero publishers notified)
- #73 — Sprint 19 first-cohort outreach emails sent (operator + Resend)
- #74 — Phase 1 (Sprints 17-21) committed + pushed + deployed (operator commits + ansible-deploys)
- #76 — Stripe Connect activation flipped MockProvider → RealProvider (operator action + G2 + G3)
- #77 — Lawyer involvement before first publisher email (G2)
- #78 — Segregated regulated escrow accounts opened at fiduciary institution (operator + counsel + bank)

**Integration-revert blocked (substrate ready; tracked-file edits revert on each parallel commit):**
- #23 — Live wiring of `/trust-center` endpoint to substrate.trust_center.build_publication
- #37 — CreatorPayouts UI backed by live `/me/payouts` endpoint
- #38 — `/operator/advertiser-campaigns` CRUD endpoints
- #54 — `/marketplace/snapshot` GET + POST endpoints
- #55 — `/operator/payouts/dashboard` endpoint
- Plus the App.tsx route registrations (re-added every session; revert every commit)

**Substrate gaps remaining (executable as new files in new dirs; not done this session):**
- #8 — Adversarial cross-user-read attempt test (would need real per-user DBs to exfiltrate from)
- #9 — Stage 0 → 1 migration script that creates per-user files
- #10 — Public-notes ingest pipeline (the orchestrator that consumes the quality gate)
- #12 — Attribution-share eligibility flagging on collective-graph documents
- #13 — Ad-eligibility flag on collective-graph documents
- #16 — Application-layer routing through DuckLake catalog at query time
- #17 — Test that User B's skill patch reaches shared substrate without User B's private content (needs cross-user fixture)
- #18 — DP shuffler wiring in front of cross-graph writer queue
- #24 — End-to-end test of telemetry-event → shuffler → shared-substrate writer with ε debit
- #26 — Real ad rendering on production public-graph pages (gated on production deploy)
- #28 — A/B framework for ad-bearing vs zero-ad voice impact
- #33 — Attribution events from production ad impressions feeding RevSharePayoutRouter (gated on production)
- #39 — Advertiser storage table (substrate/ad_inventory/advertisers or equivalent)
- #43 — First voice-and-style audit run (need real ad-bearing pages)
- #46 — Inline-sponsor card pattern shipped in production (gated on deploy)
- #47-48 — > 90% page views serving an ad; § 5.5 voice test on inline placements (gated on production)
- #49 — Mixed-attribution rev-share running on real events
- #50 — Mixed-attribution payout audit on sampled month
- #51 — Real cross-user interview (gated on multi-user)
- #58 — External observer describing Antiek as a marketplace
- #59 — §9.4 programmatic-display gate re-evaluation
- #64 — Long-tail anti-gaming forensics run against real data
- #65 — > 200 monthly-earning creators (downstream of activation)
- #75 — Integration-revert pattern resolved (operator/infra work)

**Net status:**
- **Closed at substrate level by this session: 9 items**
- **Substrate still executable but not done this round: ~24 items**
- **Operator-only (cannot execute as code): ~35 items**
- **Integration-revert blocked: ~5 items**
- **Production-deploy blocked: ~5 items**
- **Total v2 §8 items: 78; remaining unexecuted: ~69**

---

## §3 Phase-level exit-criterion check, refreshed

Re-tallying v2 §7.1 with this session's substrate work:

| Sprint | Phases | Met (v3) | Partial (v3) | Unmet (v3) | Δ vs v2 |
|---|---|---|---|---|---|
| Sprint 22 | 9 | 1 (Phase 9 neg discipline) | 5 (Phases 2, 4, 5, 6, 7, 8 — Phase 6 promoted from unmet to partial via telemetry_preferences + deletion_worker) | 3 (Phases 1, 3 + spread) | -1 unmet, +1 partial |
| Sprint 23-24 | 6 | 0 | 3 (Phase 1 promoted from unmet to partial via voice_style + ad_targeting; Phase 6 still partial) | 3 (Phases 2, 5, plus voice/legal audits) | -1 unmet, +1 partial |
| Sprint 25+ | 7 | 2 (Phases 4, 5 — correct DEFER) | 4 (Phases 2, 6, 7 from v2; Phase 1 promoted via ad_targeting matcher) | 1 | -1 unmet, +1 partial |
| Sprint 30+ | 6 | 3 (Threads 3, 4, 6 — correct DEFER/N/A) | 2 | 1 | unchanged |
| **TOTAL** | **28** | **6** | **14** | **8** | **-3 unmet, +3 partial since v2** |

**Sprint-level exit criteria:** unchanged from v2 — 3 met, 2 partial,
18 unmet (out of 23). Substrate gains don't move sprint-level exits
because those require production deploys + real data + external
actions.

---

## §4 What's new since v2 that doesn't move Phase 2

Between v2 (2026-05-22) and v3 (2026-05-23), several Phase-1
substrate features shipped on `main`:

- **`feat(ai-bridge)`** — AISidecar emits typed events to the event_log
  per §5.5 + §13.8 + Wedge 4. Operator-facing AI actions surface now.
- **`feat(export)`** — Deliverable export formats (PDF, EPUB, Substack).
  Per §10.6 of the master spec.
- **`feat(acquisition-interview)`** — Interview transcript → substrate
  documents pipeline. Sprint 11+ surface D maturation.
- **`feat(continuous)`** — Research daemon scaffold per §7.3 + §7.4.
- **`fix(g4)`, `fix(g5)`** — Operator gate closures recorded
- **`docs: turbopuffer integration spec (draft v1)`** — new
  integration-spec candidate under §17

None of these advance Phase 2 because Phase 2 starts at Sprint 22.
They all build out Sprints 11-16+ ground that Phase 2 sits on top of.

The substrate-side work to support these features (event_log
extensions, continuous daemon, transcript pipeline) is *adjacent* to
the Phase 2 substrate I built, but my Phase 2 modules are not yet
consumed by any production codepath because the integration files
(app.py, App.tsx, stripe_connect/__init__.py) keep getting
reverted.

---

## §5 §15 strategic open questions — current state

| § | Question | v2 status | v3 status |
|---|---|---|---|
| 15.1 | Legal posture (Option A/B/C) | Answered (Option C) | Unchanged ✓ |
| 15.2 | Browser-extension distribution | Answered (sideloaded Chrome) | Unchanged |
| 15.3 | Voice interview latency | Open | Operator-acceptable-rhythm measurement still pending |
| 15.4 | Competitive durability | Settled (substrate is moat) | Unchanged |
| 15.5 | Wedge 2 notebook adoption | Pending (Sprint 19 + 4 weeks) | Unchanged — Sprint 19 still not shipped to operator |
| 15.6 | Lutke gap (Wedge 1 ratification) | Pending | G6; operator has the runner; mutation cohort not yet run |
| 15.7 | RLM bridge six design decisions | Pending pre-RLM-1 | Unchanged |
| 15.8 | Prime F+D debt | Open | Unchanged |
| **15.9** | **Sprint 18 legal gate** | Partially answered | **Fully answered**: G1 closed (substrate); production deploy verification + G2 + G3 still required for activation |
| 15.10 | Pay-as-you-go monetization | Settled | Unchanged |
| 15.11 | Dispatch tier-differentiation | Pending | **Answered**: G5 verdict = insufficient_data (not a clean flip; operator can re-run after more traffic) |
| 15.12 | Watch-for-later adoption | Pending | Unchanged — feature not yet shipped to operator + 4 weeks |

**Net change since v2:** §15.9 substrate side fully answered (G1
closed); §15.11 has a verdict (insufficient_data). The other ten
questions are unchanged.

---

## §6 §16 + §16.2 REJECT compliance — refreshed

Two notes since v2:

1. **§16.2 "No ε > 10 on any DP claim"** — strengthened this round.
   `substrate/telemetry_preferences/preferences.py::apply_defaults_from_registry`
   reads each surface's sensitivity; "forbidden" surfaces (ε=0) seed
   the user preference to FALSE regardless of `opt_in_required`.
   The substrate now refuses to enable any forbidden surface by
   default. This is binding in code, not just by spec discipline.

2. **§16.2 "No pre-onboarded escrow against unconsenting rights
   holders"** — strengthened by `substrate/deletion_worker/`.
   The cascade-delete primitive lets a publisher opt out and the
   substrate actually unwinds their accrual within 30 days. The
   existing `ip_holders.status` transitions enforced this at
   state-machine level; this session added the actual unwind worker
   the SLA depends on.

No new REJECT violations introduced this round.

---

## §7 The specifically-not-executed enumeration, v3

Same shape as v2 §8, with closures struck through, additions
appended. Total: **69 items** (v2 had 78; this session closed 9).

### Sprint 22 (Multi-User Pivot)

1. ~~Clerk/Supabase auth integration — vendor selection~~ — STILL OPEN
2. ~~Clerk/Supabase auth integration — OAuth callback handler~~ — STILL OPEN
3. ~~Clerk/Supabase auth integration — session middleware~~ — STILL OPEN
4. ~~Clerk/Supabase auth integration — sign-up/sign-in UI pages~~ — STILL OPEN
5. OAuth scope mapping for Antiek Memory MCP per-user resources
6. Per-user DuckDB file actually created for second user
7. ~~Per-graph encryption keys via KMS integration~~ — SUBSTRATE CLOSED (`graph_per_user/key_provider.py`); KMS keys not provisioned in production
8. Adversarial cross-user-read attempt test
9. Stage 0 → 1 migration script that creates per-user files
10. Public-notes ingest pipeline orchestrator
11. ~~§13.9 quality gate~~ — SUBSTRATE CLOSED (`quality_gate/`)
12. Attribution-share eligibility flagging on collective-graph documents
13. Ad-eligibility flag on collective-graph documents
14. Catalog Postgres backend
15. Per-user backup latency measurement + test
16. Application-layer routing through DuckLake catalog at query time
17. Test that User B's skill patch reaches shared substrate without B's private content
18. DP shuffler wiring in front of cross-graph writer queue
19. ~~Per-telemetry-category opt-in/opt-out toggle backend storage~~ — SUBSTRATE CLOSED (`telemetry_preferences/`); UI affordance in PrivacyDashboard still missing
20. ~~`user_telemetry_preferences` table~~ — SUBSTRATE CLOSED; endpoint still missing (app.py reverts)
21. ~~Deletion worker enforcing 30-day SLA~~ — SUBSTRATE CLOSED (`deletion_worker/`); production scheduler (systemd timer) + real DB cascade not yet wired
22. Trust Center publicly published at antiek.ai/trust
23. Live wiring of /trust-center endpoint to substrate.trust_center.build_publication (reverts)
24. End-to-end test of telemetry → shuffler → shared substrate with ε debit
25. Production trace verifying ε ≤ 10 enforcement live

### Sprint 23-24 (Lead-Gen Ads + Creator Rev-Share)

26. Real ad rendering on production public-graph pages
27. ~~§5.5 voice-rubric module wired to AdSlot~~ — SUBSTRATE CLOSED (`voice_style/`)
28. A/B framework comparing ad-bearing vs zero-ad page voice score
29. ~~Topic-classification → ad-inventory selection wiring~~ — SUBSTRATE CLOSED (`ad_targeting/`)
30. Stripe Connect real activation
31. At least one creator account with verified Stripe Connect link
32. Creator account payout_eligible flag flipped via §9.5 KYC
33. Attribution events from production ad impressions feeding RevSharePayoutRouter
34. External red-team firm engagement
35. External red-team firm report filed at docs/sprint23_red_team.md
36. Real Stripe Connect KYC completed for at least one creator
37. CreatorPayouts UI backed by live /me/payouts endpoint (reverts)
38. Operator-only /operator/advertiser-campaigns CRUD endpoints (reverts)
39. Advertiser storage table (substrate/ad_inventory/advertisers)
40. Manual sales motion to vertical SaaS / consulting / recruiting firms
41. ≥ 3 paying advertisers
42. ~~Voice-and-style audit module~~ — SUBSTRATE CLOSED (`voice_style/rubric.py`)
43. First voice-and-style audit comparing ad pages vs non-ad baseline
44. Legal counsel signoff on §9.5 KYC + 1099 posture (G2)
45. Legal counsel signoff on Kalshi-pattern notification template (G2)

### Sprint 25+ (Ad Inventory at Scale + Cross-Graph Network Effects)

46. Inline-sponsor card pattern shipped in production
47. ≥ 90% of public-graph page views serving an ad
48. Voice-style test verified on inline-sponsor placements
49. Mixed-attribution rev-share running on real attribution events
50. Mixed-attribution payout audit on a sampled month
51. Cross-graph "ask an expert" — real cross-user interview happens
52. Payment-for-interview transaction cleared at least once
53. SOC 2 PURSUE/DEFER decision recorded with cited signal
54. /marketplace/snapshot endpoint persisted in app.py (reverts)
55. /operator/payouts/dashboard endpoint persisted in app.py (reverts)
56. Marketplace ad revenue producing > 60% of monthly platform revenue
57. ≥ 10 creators receiving real take-home dollars
58. ≥ 1 external observer describing Antiek as a marketplace unprompted
59. §9.4 programmatic-display gate re-evaluation file

### Sprint 30+ (Federation + Network Effects)

60. Federation handshake — partner Antiek instance willing to negotiate
61. Federation handshake — signing-key fingerprint exchanged with partner
62. Federation handshake — actual slice exchanged successfully
63. Federation adversarial review report filed
64. Long-tail anti-gaming forensics run against real data
65. Long-tail rev-share producing > 200 monthly-earning creators
66. Sampled 1099 batch passes accountant review
67. Programmatic SSP integration (correctly DEFER; line item)
68. Vision-capable role substrate (correctly DEFER; line item)
69. Autoresearch Wedge 3 proposal-delta artefact filed (cohort threshold not met)

### Cross-cutting blockers (each blocks multiple sprints)

70. Six-month operator-graph compounding demonstration — G7; ~Nov 2026 earliest
71. Sprint 18 legal gate production deploy verified — G1 substrate closed; deploy unverified
72. Sprint 18 legal gate — first publisher opt-in — G3
73. Sprint 19 first-cohort publisher outreach emails sent (after G2)
74. Phase 1 (Sprints 17-21) committed + pushed + deployed
75. Integration-revert pattern resolved
76. Stripe Connect activation flipped MockProvider → RealProvider
77. Lawyer involvement before first publisher email (G2)
78. Segregated regulated escrow accounts opened at fiduciary institution

**Items closed at substrate level by this session:** #2, #7, #11, #19,
#20 (partial), #21 (substrate), #27, #29, #42 — 9 items.

**Items remaining unexecuted: 69**
- ~35 operator-only actions (cannot execute as substrate code)
- ~5 integration-revert blocked (substrate ready)
- ~5 production-deploy blocked
- ~24 substrate-side gaps (executable but not done; ~16 of these
  also gated on operator action — e.g., creator population, real ads)

---

## §8 Final tallies

### Status across all four Phase 2 sprints

| Surface | v1 count | v2 count | v3 count |
|---|---|---|---|
| Substrate primitives — scaffolded | ~7 modules | 7 + integration layer | **13 modules + integration layer** |
| React UI modes | 4 + 1 component | 4 + 1 component | 4 + 1 component (unchanged this round) |
| Doc artefacts | 3 templates | 3 templates + 2 audit files | 3 templates + 3 audit files + operator_gate_actions.md companion |
| Python tests | ~155 | 155 + 56 (v2 had 211?) | ~240 across 15 test files |
| Operator gates closed | not framed | not framed | **3 of 8 (G1, G4, G5)** |
| Sprint-level exit criteria met | 3 / 23 | 3 / 23 | **3 / 23** (unchanged) |
| Phase-level exit criteria met | not framed | 6 / 28 | **6 / 28** (unchanged, but partial count +3) |

### Honest one-line verdict, v3

Phase 2 is **not executed**. The substrate scaffolding rose to
~65% complete this round (from v2's ~50%) by adding six modules that
close §13.9 quality gating, per-graph encryption-key abstraction,
§5.5 voice rubric scoring + suppression, per-user telemetry
preferences, 30-day deletion SLA worker, and topic → ad-inventory
matching. Three of eight operator gates have closed (G1, G4, G5).
**Five operator gates remain open (G2, G3, G6, G7, G8)**, and G3
(first publisher opt-in) + G7 (six-month compounding demonstration)
are the two that specifically block Phase 2 sprints from moving off
the spec's `not started` badge. Zero of the 23 sprint-level exit
criteria have moved to met since v2. **Nothing has shipped + pushed
+ deployed.**

The most upstream block is still G7's six-month compounding clock,
which has not started. The single highest-leverage thing the
operator could do — independent of any code I can write — is to
publish three substantial research outputs from Antiek under any
byline and demonstrate the compounding curve. Every subsequent gate
unlocks downstream of that.

---

_Audit v3 — paired with v1 and v2; superseded by the next audit
once additional substrate or operator action lands._
