# Engineering deferrals — the items NO ONE should re-implement yet

**Generated 2026-05-23 as a companion to `docs/operator_gate_actions.md`.**

`operator_gate_actions.md` covers the eight gates that **engineering cannot
close** (legal, calendar, external party). **This document covers the
inverse**: the spec items that **engineering deliberately has NOT shipped**
because the spec itself defers them behind an explicit ratification or
unlock criterion. The substrate primitives may already exist; the
**activation, the production-grade implementation, or the next-layer
build-out is what's deferred**.

The risk this document mitigates: a future agent (Claude or human) sees an
empty file path in the spec and assumes it's a gap to fill. It is not — it
is a deferral with a specific unlock event. Building it prematurely either
(a) violates a §14.3 sequencing-discipline rule, (b) wastes engineering
effort on a path the operator may reject at ratification, or (c) destroys
the moat that the deferral is protecting (§13.4 graph contamination is the
canonical case).

Each entry below carries:
- **Status** — Deferred / Substrate prep done / Partial / Superseded
- **Unlock criterion** — what specific event makes the deferral closeable
- **Spec reference** — the master-spec section or integration-spec that
  owns the deferral
- **Blocks-what** — downstream work that cannot start until this unlocks
- **Action when unlocked** — what an agent should do the day the criterion
  fires

The thirteen deferrals, by unlock criterion category:

---

## D1 — Sprint 22 multi-user pivot cluster

**Status:** ❌ Deferred. Substrate prep is partial (h6-auth magic-link
login + Login mode landed via `18ba98a` + `00d5cac`; PrivacyDashboard mode
exists as a UI scaffold; cross_graph federation primitives landed via
`e59c4e2`).
**Unlock criterion:** G7 (six-month solo-operator compounding window per
master-spec §13.4) closes — earliest ~Nov 2026. **Premature activation
destroys the moat that multi-user is supposed to monetize.**
**Spec reference:** master-spec §14.1 row 22 + §13.2 + §13.4 + §13.6 + §13.10.
**Blocks-what:** D8 (Sprint 25+ ads at scale), D9 (Sprint 30+ federation
activation), every "second-user" exit criterion in Sprints 22–24.

This is the largest deferral by lines-of-code-not-yet-written. The cluster
contains:

- **Trust Center UI mode** (`apps/reading/src/modes/TrustCenter/`). Public-
  facing trust documentation per §13.7 — privacy architecture description,
  DP ε-registry per surface, retention policy, deletion SLA, incident-
  response process, privacy-dashboard tutorial. Lives at `antiek.ai/trust`.
- **DuckLake catalog activation.** The catalog Postgres design landed
  Sprint 18 §13.10; activation (per-user file routing, Postgres mediation,
  Stage 1→2 transition path) ships only when per-user DBs exist.
- **Per-user personal-graph storage** (`substrate/graph_per_user/` —
  scaffolded; activation deferred). Physical separation, not tagging.
  Per-user DuckDB files with per-partition encryption keys. The §13.2
  architectural-incapability claim is what makes the privacy posture
  load-bearing; cannot be tested before two users exist.
- **Per-graph encryption keys with KMS escrow shape.** Design landed Sprint
  18 §13.10; the actual KMS integration ships at multi-user activation.
- **Privacy dashboard production enforcement.** The UI mode (PrivacyDashboard)
  exists; the live telemetry pipeline (DP shuffler routing real traffic +
  toggles wired to substrate, 30-day verifiable deletion) only fires once
  multi-user traffic exists.
- **Full Antiek Memory MCP rollout.** Server scaffold landed Sprint 19 via
  `tools/antiek_memory/`; per-user OAuth scoping + signed-manifest rug-pull
  defense at production scale is gated on multi-user activation.
- **Cross-graph writer queue.** `substrate/cross_graph/` lands the
  federation primitives; the §13.2 mechanism that propagates a skill patch
  as a *discovered rule* (not the patched private content) activates with
  multi-user.

**Action when unlocked:** read `docs/sprint30_thread_decisions.md` first
(the operator has already pre-decided several Sprint 30+ items); then
sequence Sprint 22 work per master-spec §14.1; each sub-item above gets
its own implementation PR.

---

## D2 — Autoresearch Wedge 3: config sweeps

**Status:** ❌ Deferred. Substrate primitive (autoresearch runner) exists
at `tools/prompt_autoresearch/`; Wedge 1 + Wedge 2 (shadow-mode gate)
shipped. Wedge 3 not started.
**Unlock criterion:** **≥500 graded outcomes** in the cohort + Wedge 1
ratified at G6.
**Spec reference:** `docs/integration_autoresearch.md` Wedge 3;
master-spec §3.4 (`Context-pack + dispatch config sweeps (Wedge 3, DEFER
until ≥500 graded outcomes in cohort)`).
**Blocks-what:** systematic dispatch-config tuning that goes beyond
single-prompt mutations.

Why ≥500: below that volume the gradient between configs is dominated by
noise. The substrate's `outcomes` table is the ground-truth source; query
it for the cohort count before considering Wedge 3 work.

**Action when unlocked:** extend `tools/prompt_autoresearch/` to sweep
context-pack assembly strategies + dispatch-tier routing decisions
(currently only prompts mutate). Reuse the budget-cap discipline from
Wedge 1. Composite-score logic from `tools/prompt_autoresearch/score.py`
applies directly.

---

## D3 — Autoresearch Wedge 4: local SFT loop

**Status:** ❌ Deferred. Not started.
**Unlock criterion:** G8 (Loop 3 unlock criteria all True). The Wedge 4
local SFT loop is one of the things G8 unlocks.
**Spec reference:** `docs/integration_autoresearch.md` Wedge 4;
`docs/loop_3_unlock_criteria.md`; master-spec §3.4.
**Blocks-what:** nothing else in Phase 1–3; this is the on-ramp to the
RL track via Prime Intellect.

The §14.3 sequencing-discipline rule is explicit: *"No work on Loop 3
unlock criteria until the criteria themselves pass."* That includes Wedge
4. The five unlock criteria live in `docs/loop_3_unlock_criteria.md`.

**Action when unlocked:** the comparison gate per `integration_autoresearch.md`
Wedge 4 vs `integration_prime_intellect.md`'s hosted `prime rl run`
happens at unlock time, not before — that comparison itself is deferred.

---

## D4 — RLM-1 through RLM-5 implementations

**Status:** ❌ Deferred. RLM-1 has a stub at `orchestration/rlm/`; RLM-2
through RLM-5 not started.
**Unlock criterion:** ratification of the **six design decisions** in
`rlm_integration_spec.md` §6.
**Spec reference:** `docs/rlm_integration_spec.md` §6 (six decisions) +
master-spec §14.2 (RLM parallel track) + §15.7 (ratification gate).
**Blocks-what:** nothing on the mainline; RLM is a parallel track per
§14.2.

The six decisions per §6 of the RLM integration spec must be ratified by
the operator before RLM-1 implementation proceeds. RLM-1's stub at
`orchestration/rlm/` ships with the `ANTIEK_RLM_RATIFIED=1` env gate — it
refuses to operate unratified.

**Action when unlocked:** sequence is documented in
`rlm_integration_spec.md` — RLM-1 long-doc wrestling bridge (~600 LOC),
then RLM-2 long-corpus synthesizer mode (~250 LOC), then RLM-3
`investigation_kind="rlm"` orchestrator (~500 LOC, net-new), then RLM-4
verifiers envs (~2000 LOC), then RLM-5 trajectory harvest CLI for
`prime-rl`. Tool-isolation invariant (tools NEVER attach to root REPL)
must be enforced throughout.

---

## D5 — Prime Intellect items A and B

**Status:** ❌ Deferred. Items F + D shipped (trajectory→verifiers compat
test + parameter_extractor fixture at 50 examples). Items A + B not
started.
**Unlock criterion:** G8 (Loop 3 unlock) — items A + B are Phase 2 of
the Prime track, behind the Loop 3 gate per §14.2.
**Spec reference:** `docs/integration_prime_intellect.md` items A + B;
master-spec §3.4.
**Blocks-what:** item E (hosted `prime rl run`).

Item A: GEPA on `parameter_extractor`. Item B: `verifiers` env stub for
`parameter_extractor` (substrate only — training forbidden until unlock).

**Action when unlocked:** integration_prime_intellect.md §A and §B
contain the exact contracts. Hub publishing is REJECTED per the spec —
keep the env stubs substrate-only.

---

## D6 — Prime Intellect item E: hosted prime rl run

**Status:** ❌ Deferred (explicit per §14.3 sequencing discipline).
**Unlock criterion:** G8 (Loop 3 unlock) + the Wedge-4-vs-hosted-RL
comparison resolved at unlock time.
**Spec reference:** `docs/integration_prime_intellect.md` item E;
`docs/loop_3_unlock_criteria.md`; master-spec §14.3.
**Blocks-what:** any actual training-time work.

Strictest deferral in the spec: §16.1 forbids pre-building the SFT loop,
the verifiers envs, or the hosted RL infrastructure. Violating this
deferral is what §16 explicitly prohibits.

**Action when unlocked:** Loop 3 unlock fires; the comparison between
Wedge 4 local SFT and `prime rl run` happens; whichever wins gets built.
Loser is closed.

---

## D7 — Sprint 25+ programmatic ad inventory at scale

**Status:** ❌ Deferred. Substrate prep landed via `e59c4e2 feat(phase-3)`
(`substrate/ad_inventory/` 10 modules: ad_bidding, advertiser_onboarding,
attribution, event_emit, event_subscription, intent_targeting, payout,
transfer_initiator + KYC/1099 wiring via `1b512e7`).
**Unlock criterion:** D1 (multi-user pivot) closes + first creator cohort
is live and accruing.
**Spec reference:** master-spec §9.4 (§9.4 Option A — programmatic display
ads — explicitly REJECTED for Phase 1/2/3); master-spec §14.1 row 25+;
`apps/reading/src/modes/AdvertiserConsole` (operator-only console exists,
self-service advertiser deferred).
**Blocks-what:** the §13.9 monetization path beyond Sprint 23-24's
lead-gen / vertical ads.

Spec §9.4 deliberately rejects programmatic display for Phase 1–3.
Sprint 23-24 ships **lead-gen ads only** (higher CPMs, audience-intent
aligned, brand-safety tractable at operator's audience scale). Sprint
25+ programmatic kicks in only **if scale demands it** — i.e., the
audience grew beyond what lead-gen + vertical targeting can monetize.

**Action when unlocked:** §9.4 Option C transition — programmatic
auction infrastructure, brand-safety pipeline, click-fraud rate-limiting
at the scale anti-gaming substrate (`substrate/anti_gaming/`) was
designed for.

---

## D8 — Sprint 30+ federation activation

**Status:** ❌ Deferred. Substrate prep landed:
`substrate/cross_graph/{__init__, ask_expert, event_emit, partner_identity,
outbound_transport}.py` + Federation/CrossGraphCitations UI modes via
`e59c4e2` + `1b512e7`.
**Unlock criterion:** D1 (multi-user pivot) closes + ≥1 publisher opted in
+ first cross-graph "ask an expert" use case validated single-graph.
**Spec reference:** master-spec §13.9 + §14.1 row 30+ + `docs/sprint30_thread_decisions.md`.
**Blocks-what:** the network-effect monetization tail.

Federation is the *last* engineering deferral by spec sequencing —
everything else closes first. The substrate-side scaffold lets a Sprint
30+ activation be a configuration flip + outreach motion, not a
re-implementation.

**Action when unlocked:** activate the HttpxOutboundTransport in
production (currently MockOutboundTransport runs); partner identity
handshake protocol with first federation partner; cross-graph attribution
routing for ad-revenue rev-share to opted-in publishers via the §9.10
escrow.

---

## D9 — Substack publishing live integration

**Status:** ❌ Deferred. Substack export format shipped via `cc0adcb`
(markdown variant per §8.5); live OAuth-based publishing flow not shipped.
**Unlock criterion:** **Operator decision.** Spec does not specify a hard
trigger; the operator publishes to Substack manually using the export
format until volume justifies automation.
**Spec reference:** master-spec §8.5 ("Substack / paywalled journalism")
+ §14.1 row 15 (`deliverable export formats (PDF, EPUB, Substack)`).
**Blocks-what:** nothing — the export format satisfies the spec's
literal deliverable requirement.

This deferral is genuinely operator-discretion. Manual export-and-paste
into Substack works today; an OAuth-mediated direct publish is a polish
item if the operator publishes to Substack regularly enough that the
manual step becomes annoying.

**Action when unlocked:** if the operator says "automate it," extend
`tools/stripe_connect/`'s OAuth pattern to Substack's publishing API.
Otherwise leave deferred.

---

## D10 — Synchronous voice interview model

**Status:** ❌ Deferred. Async voice via WebRTC + streaming whisper +
OpenAI TTS shipped Sprint 17 (`acquisition/voice/webrtc.py`); latency
~3–5s end-to-end accepted per §15.3.
**Unlock criterion:** Sprint 23+ per §15.3 decision; operator's
willingness to depend on a different cost/availability model
(OpenAI Realtime API, Anthropic voice mode when available).
**Spec reference:** master-spec §15.3 (voice interview latency
question — decided async for Sprint 17, evaluate sync at Sprint 23+).
**Blocks-what:** nothing — async voice is the working baseline.

The 3–5s round-trip is awkward but acceptable per the §15.3 verdict.
Switching to a synchronous voice API trades latency for a single-provider
dependency that compromises the dispatch posture per §14.4.

**Action when unlocked:** at Sprint 23+ the operator runs a 5-minute
voice interview (§15.3 formal measurement still open per
`docs/operator_gate_actions.md` §15 list). If acceptable-rhythm rating
< 4/5, integrate OpenAI Realtime API as a dispatch tier.

---

## D11 — Dedicated chase-tree visualization mode

**Status:** ⚠️ Partial. `ChaseSlideOver.tsx` at
`apps/reading/src/modes/ResearchWorkstation/` ships a slide-over chase
visualization; a dedicated full-screen chase-tree mode is **not** shipped.
**Unlock criterion:** Operator-discretion polish — only if the SlideOver
proves insufficient for real multi-step investigations.
**Spec reference:** master-spec §2.2 (recursive chase loop) — requires
the chase tree be UI-surfaced; **the SlideOver may already satisfy this**.
**Blocks-what:** nothing.

This may not be a real deferral. §2.2 requires the chase be reachable;
the SlideOver delivers it. A dedicated full-mode "ChaseTree" view is an
optional polish item, not a spec gap.

**Action when unlocked:** if the operator decides the SlideOver is
insufficient, ship `apps/reading/src/modes/ChaseTree/` with the full
tree-graph rendering. The `useInvestigationTree` hook already exposes
the data shape.

---

## D12 — `highlight_removed` event UI affordance

**Status:** ❌ Deferred. Schema only.
**Unlock criterion:** Operator design decision on whether highlight
deletion is a first-class user action (e.g., a remove-X button on
hover, a keyboard Delete on a focused highlight, or a right-click menu
entry). No UI affordance exists today; highlights persist as
`behavior_events` rows once created.
**Spec reference:** Wrestle Evolution spec, taxonomy v2 (added
2026-05-22 on the `wrestle-evolution/integration` branch). The
`highlight_removed` entry was added to `BehaviorEventType` because the
RL trajectory benefits from negative-signal events; but the source UI
that should produce them does not exist.
**Blocks-what:** completeness of the SPR-04/SPR-07 behavior-event funnel
(currently 18 of 19 taxonomy types emit at real call sites; the 19th
is this one).

This is the only schema-defined event type without a wired emit call
site. Future agents reading
`substrate/behavior/schemas/highlight_removed.json` (which lives on the
`wrestle-evolution/integration` branch until the operator pushes — not
yet on `origin/main`) will be tempted to grep for a UI hook and add
one; **do not invent the UI without operator design ratification**. The operator may decide
highlights are append-only by design (the substrate already supports
"demote-noise" at the notebook layer; perhaps highlight removal should
go through the same demote semantics rather than a destructive UI).

**Action when unlocked:** wire the emit at whatever surface the operator
ratifies — `PdfViewer.tsx::onMouseUp` is the natural sibling location
(it already emits `highlight_created`); the remove path would be a new
keymap or context-menu binding. Mirror the rigor #5 documentation
pattern SPR-04 used for the "Cmd+R vs page-reload" decision: comment
the decision with operator-rationale so a future maintainer doesn't
"fix" it by adding a different removal affordance.

**Where this is recorded:** `docs/decisions/wrestle-evolution-spec-2026-05-23.md`
"Open follow-ups" table, "highlight_removed UI affordance" row.

---

## D13 — Physics of Reading: live surface integrations (the augmentations ship dormant-correct)

**Status:** ❌ Deferred. The full Physics of Reading substrate shipped to prod
via PR #14 (`origin/main` `76c2002`; 8 sprints `944b93e`→`0935590`): the facet
engine, the CI boundary guard, and the augmentation roster (servability,
ip-holder, quality-cue, skim, sitesee, collapse, minimap, marginalia, review-due)
— built, tested, and composing. Most are **dormant-correct on the real engine**:
they run on the actual facet / layout-map seams but their live data or geometry
feeds are not yet wired. Only servability, ip-holder, and QualityCue render live
today; the rest light up when the integrations below land. No augmentation invents
its own data (PR-2 / PR-6) — each reads a surface-resolved view that does not
exist yet, so this is a deferral, **not** a code gap to fill by inventing the feed.
**Unlock criterion:** per sub-item below — each is a distinct surface/backend
integration with its own decision file in `docs/decisions/`. None is closeable by
writing the missing feed inside an augmentation; each waits on a named surface
integration (and the canon ratification is a separate operator action).
**Spec reference:** `docs/philosophy/physics-of-reading.md` (the binding canon,
PR-1..PR-8; status: **draft** — operator ratification pending) + the four
`docs/decisions/spr-0{5,6,7,8}-*.md` files + `reading-physics-boundary-guard.md`.
**Blocks-what:** the fully-live Read surface (collapse, minimap, AccrualView /
ChaseThread re-home, Skim/SiteSee `read` tint, voice marginalia, the
spaced-repetition review cue). Nothing on the substrate / payout / multi-user / RL
paths — this cluster is Read-surface-local.

The cluster contains:

- **The geometry-measurement pass** (`docs/decisions/spr-05-geometry-pass-gap.md`)
  — the run's largest deferred item. One `useLayoutEffect`
  (`getBoundingClientRect` per anchor → `baseGeometryFromMap` → `createLayoutMap`)
  replaces `EMPTY_LAYOUT_MAP` in `MasterMdViewer` and lights up collapse + minimap
  + AccrualView + ChaseThread **at once** (O(facets) payoff). Unlock: an
  agent/operator builds the pass.
- **The `source.read` event** (`docs/decisions/spr-06-source-read-event-gap.md`)
  — SiteSee's `cited` / `saved` tints resolve today; the `read` tint waits on a
  net-new `source.read` typed event the surface must emit (`postTypedEvent` →
  `/events/typed` → `runtime/db_lock`, single-writer) plus a `CitationHistoryState`
  resolver. Unlock: the surface emits + resolves it.
- **The marginalia note/voice persistence**
  (`docs/decisions/spr-07-marginalia-voice-storage.md`) — the margin-note + voice
  augmentation reads resolved views; the note/anchor write path and the audio-blob
  object storage (keyed by event, reusing the Speak path) are a surface/backend
  integration the augmentation cannot perform (PR-2 / PR-6). Unlock: the surface
  wires the note-author write path + blob storage.
- **The review-state resolver**
  (`docs/decisions/spr-08-review-state-resolution-gap.md`) — review-due is mounted
  **live** in `MasterMdViewer` behind a default-off toggle (`REVIEW_DUE_ENABLED`)
  but reads an empty `dueClaims`; resolving the per-reader spaced-repetition
  schedule from the substrate (likely a review-history typed event, like
  `source.read`) is deferred. Unlock: the surface resolves the schedule, hands a
  populated `dueClaims`, and flips the toggle.

A fifth, **operator-only** item gates the guard's strictness rather than an
augmentation: ratifying the canon (`physics-of-reading.md` `status: draft →
ratified`) flips the CI boundary guard `tools/lint/reading_physics_check.py` from
advisory to **blocking** (then add `--enforce` to its `ci.yml` `tsc`-job step). See
`docs/decisions/reading-physics-boundary-guard.md` + `ci-informational-gates.md`.
Until then the guard runs green-advisory, printing any findings without blocking.

**Action when unlocked:** each sub-item ships its own integration PR per its
decision file. The geometry pass is the highest-leverage (one pass unblocks four
widgets); the three data feeds are independent and can land in any order. The canon
ratification is an operator action independent of the integrations — it can happen
any time and changes only CI strictness, not behavior.

---

## Cross-reference: unlock criterion → deferrals it gates

| Unlock criterion | Deferrals that close |
|---|---|
| G7 (six-month compounding window, master-spec §13.4) | D1 (Sprint 22 cluster) + transitively D7, D8 |
| ≥500 graded outcomes in cohort | D2 (Autoresearch Wedge 3) |
| G8 (Loop 3 unlock — `loop_3_unlock_criteria.md` 5 sub-gates) | D3 (Wedge 4), D5 (Prime A+B), D6 (Prime E) |
| RLM 6 design-decisions ratified (`rlm_integration_spec.md` §6) | D4 (RLM-1..5) |
| D1 (multi-user) + creator cohort live | D7 (Sprint 25+ ads at scale) |
| D1 (multi-user) + ≥1 publisher opted in | D8 (Sprint 30+ federation activation) |
| Operator-discretion polish | D9 (Substack publish), D10 (sync voice), D11 (chase-tree mode) |
| Operator UI-design ratification (highlight removal semantics) | D12 (`highlight_removed` event) |
| Read-surface integration sprints (geometry pass / `source.read` emit / marginalia persistence / review-state resolver; each its own `docs/decisions/spr-0{5,6,7,8}-*.md`) | D13 (Physics of Reading live surface integrations) |
| Operator ratifies the Physics of Reading canon (`physics-of-reading.md` draft→ratified) | D13's CI-guard advisory→blocking flip |

---

## Calendar

Realistic-earliest unlock dates assuming everything else moves on schedule:

- **D2 (Wedge 3 config sweeps)** — gated on outcome volume; ≥3 months out
  even with aggressive operator usage
- **D5/D6 (Prime A/B/E)** — D5/D6 close with G8; Q1 2027 at the earliest
  per `operator_gate_actions.md` G8 calendar
- **D3 (Wedge 4)** — same as G8; Q1 2027 earliest
- **D4 (RLM-1..5)** — depends on operator ratification cadence on the 6
  design decisions; could close earlier than G8 if ratified
- **D1 (Sprint 22 cluster)** — ~Nov 2026 earliest (G7 calendar)
- **D7 (Sprint 25+ ads at scale)** — D1 + first creator cohort accruing;
  earliest 2027 H1
- **D8 (Sprint 30+ federation activation)** — D1 + ≥1 publisher opt-in
  (G3); earliest 2027 H2
- **D9, D10, D11, D12** — operator-discretion; no calendar binding
- **D13 (Physics of Reading live integrations)** — no calendar binding; each
  Read-surface integration ships when the surface is built out (the geometry pass
  is the highest-leverage, unblocking four widgets at once). The canon ratification
  is an independent operator-discretion action that only flips CI strictness.

**Bottom line:** of the 13 deferrals, **none can be closed this week**;
**0 close this month** (every deferral is gated on either time, volume,
ratification, or D1); **3 close in late 2026 to mid-2027** (D1, then D7,
D8 trail); **3 close in 2027+ at the earliest** (D3, D5, D6 all gated on
G8); **D4 depends on operator's ratification cadence**; **D9, D10, D11,
D12 are operator-discretion items with no spec-binding deadline**; **D13
(Physics of Reading live integrations) is Read-surface engineering with no
spec-binding deadline — the augmentations ship dormant-correct until wired**.

The pattern matches `operator_gate_actions.md`'s G7→G8 chain:
**multi-user is the keystone**. D1 closing unblocks the largest cluster
of downstream engineering work. Any agent considering work on Phase 2/3
substrate that isn't already on `origin/main` should check D1's status
first — premature activation is the failure mode the spec was designed
to prevent.

---

## How to update this document

When a deferral closes:
1. Change Status to ✅ CLOSED with the commit that closed it.
2. Add a one-line **Closed by:** field with the commit SHA + brief reason.
3. Update the Calendar section if the close was earlier or later than predicted.
4. Move the entry to a "Closed deferrals" appendix at the bottom (preserve
   the history rather than deleting — future agents may need to know what
   the operator chose and why).

When the spec adds a new deferral (e.g., a Sprint 25+ item the operator
explicitly defers in a new commit):
1. Add a new D-numbered entry following the convention above.
2. Cross-reference its unlock criterion in the table.
3. Update the Calendar with a realistic-earliest date.

When in doubt about whether something is a deferral or a gap:
- If the spec explicitly defers it (with words like "DEFER," "gated on,"
  "behind," "ONLY after"), it belongs here.
- If the spec describes it as a deliverable that should exist now but
  doesn't, it belongs in a sprint-execution audit instead.
- If you're not sure: don't implement it; ask the operator first.
