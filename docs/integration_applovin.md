# Antiek × AppLovin — Ads, Axon, and Per-Frame Attribution Integration Spec

**Status:** Draft v1, 2026-07-02 (session 8d5beda6, /infinite ads lane).
All external product facts verified 2026-07-02 via WebSearch/WebFetch of
primary sources (support.applovin.com, developers.axon.ai,
legal.applovin.com, dated press/analyst coverage); each carries its date
inline. AppLovin's self-serve surface changed materially in June 2026 —
re-verify §11 pricing/eligibility before any sprint commit and quarterly
thereafter.

**Scope:** Decide where AppLovin (Axon, the AppLovin Ads self-serve
platform, MAX/ALX, Adjust) integrates with Antiek's ad economics, where
integration is deferred behind explicit unlock criteria, and which
adoption shapes are rejected as category errors or substrate violations.
Because the operator's mandate pairs the AppLovin question with
"perfect the revenue-split attribution per frame," this spec also fixes
the scope and acceptance bar of the per-frame attribution program (§7)
that any Axon-inspired learning must stand on. Defensible verdicts, not
consensus hedging.

**Predecessor docs (precedence order):**
1. `docs/architecture_notes.md`
2. `docs/master-product-spec.md` — §9 (ad economics + attribution),
   §9.0 (legal gate), §15.10 (monetization shape), §16/§16.1 (REJECTs)
3. `strategy/voice-and-style-discipline.md`
4. Peer integration specs — `docs/integration_exa_browserbase.md` is the
   discipline model (wedge matrix, REJECT form, named-Plan-B, trigger
   conditions); `docs/integration_posthog.md`,
   `docs/integration_turbopuffer.md` are structural peers.

**Operator quality bar:** intellectual honesty, rigor, defensibility.
Explicit REJECT verdicts where warranted. No "AppLovin is hot, ship it"
framings. Two lenses the operator named for this domain, made concrete:
the *Bernays lens* — advertising as credibility infrastructure matched
to declared interest, never covert manipulation (§1.4); and the
*Sutskever/Radford auditability bar* — no learned or money-bearing
component ships without a logged, replayable, evaluable decision trail
(§7.2). Where the two conflict with a vendor's design, the vendor loses.

---

## Honest preamble — an operator-named vendor, and what honesty owes it

The turbopuffer spec introduced the discipline that a wedge without an
operator-request signal must be SPIKE-gated. This spec has the opposite
condition: the operator named AppLovin directly and with admiration
("AppLovin has done an amazing job in building Axon and it would be
intelligent to use it"). That raises the honesty bar rather than
lowering it, because the investigation's central finding is:

**AppLovin sells nothing that Antiek's supply side can adopt.** There is
no web-publisher SDK, no web ad-serving product, and no path to AppLovin
demand for a browser-based reading platform (§2.1). And **Axon is not a
product** — it is not licensable, not callable, and not inspectable; the
only way to touch it is to spend advertising budget on AppLovin's own
demand surfaces (§2.2).

What IS true — and the reason this spec is not a bare rejection — is
that the thing the operator admires about Axon (a closed self-learning
loop from real outcomes to expected-value ranking) is a *posture*, and
that posture is already encoded in this repo:
`substrate/ad_inventory/auction_model.py` opens with "The Axon-style
learned core" and implements it as a pure-Python, in-process,
explainable re-ranker with a rule-based fallback, per §16's
no-new-heavy-dep constraint. The settled house relationship to AppLovin
is **copy the loop, never adopt the network** — this spec's job is to
finish that loop honestly (§6) and to build the one thing no ad network
will ever build for us: a per-frame revenue-split attribution rail that
pays the drivers of content value and can prove every cent (§7).

---

## Table of contents

1. What AppLovin actually is (and what's reusable)
2. What AppLovin is NOT — the misreadings to avoid
3. The single architectural decision that drives every wedge
4. Mapping AppLovin primitives to Antiek's substrate
5. Verdict matrix
6. Wedge 1 — Close the in-substrate Axon loop (INTEGRATE NOW)
7. Wedge 2 — Per-frame revenue-split attribution program (INTEGRATE NOW)
8. Wedge 3 — Demand-side AppLovin Ads for growth (DEFER)
9. Wedge 4 — Supply-side monetization via MAX (DEFER — possibly REJECT)
10. Explicit rejections (don't re-litigate)
11. Cost, legal, and safety envelope
12. Risks and mitigations
13. Unlock criteria for promoting wedges
14. Sprint placement
15. Open questions (genuinely unresolved)
16. What to do now
17. Final note for the implementing agent

---

## 1. What AppLovin actually is (and what's reusable)

### 1.1 The corporate arc, dated

- **Axon 1.0 → Axon 2** (announced 2023-08-07, live from ~Q2 2023): a
  ground-up rebuild of the bidding/targeting engine, described publicly
  only as "the latest AI techniques." AppLovin is deliberately opaque
  about architecture (Foroughi: "It's just better"). The only primary
  disclosure of training signal is legal.applovin.com's Axon page:
  models train continually on device/engagement data, MAX win/loss bid
  notifications, and optionally advertiser-shared first-party data,
  using contextual/probabilistic rather than user-identifier targeting
  — a characterization contested by three 2025 short-seller reports and
  a reported SEC probe (§11.2).
- **Games divestiture:** the entire Apps business (10 studios) sold to
  Tripledot, closed 2025-06-30 ($400M cash + ~20% Tripledot equity).
  AppLovin is now a pure ad platform with no first-party game supply.
- **E-commerce/web expansion (demand side only):** managed pilot
  revealed 2024-11-06 → "Axon Ads Manager" referral-gated self-serve
  2025-10-01 ($10M+ GMV brands) → claimed ~$1B e-commerce run-rate
  (Feb 2026) → open self-serve GA June 2026, rebranded **"AppLovin
  Ads"** (2026-06-30 coverage; §15 OQ-1 on the exact GA date), ending
  what the company called "14 years as a closed platform."
- **Scale:** Q1 2026 revenue $1.84B (+59% YoY) at ~85% adjusted-EBITDA
  margin; added to the S&P 500 effective 2025-09-22 over a short
  seller's public objection.
- **2026 adjacencies:** GenAI creative tools (interactive page
  generator GA, video generator pre-GA); a social push announced
  2026-02-19 after the failed April-2025 TikTok bid, with lifestyle app
  "Gist" quietly launched May 2026 as a first-party data source.

### 1.2 The product family, and which side of the market each serves

| Product | Side | What it is | Relevance to a web reading platform |
|---|---|---|---|
| AppDiscovery | demand | app-install UA engine (Axon-powered) | none (Antiek has no app to promote) |
| **AppLovin Ads** (ex-Axon self-serve) | demand | web/e-commerce advertiser platform: Axon pixel + S2S Conversion API + reporting API | the ONLY offered surface — Antiek as *advertiser* (§8) |
| MAX | supply | SDK mediation for iOS/Android/Fire OS apps | requires a native app Antiek doesn't have (§9) |
| ALX | supply/exchange | RTB exchange whose supply IS the MAX SDK footprint | same — no web supply exists |
| Adjust | measurement | MMP, acquired 2021 | owned by the seller — rejected as measurement (§10 R4) |
| Wurl | supply | CTV distribution ($430M, 2022) | out of domain |
| Array | distribution | carrier/OEM app delivery | **shut down Q3 2025** amid allegations (§11.2); rejected as a class (§10 R7) |

### 1.3 What is genuinely reusable (and the form reuse must take)

Reusable **conceptually** — and already partially reused on `main`:

1. **The closed loop.** Axon's edge is not a psychological trick; it is
   feedback-loop engineering: every impression outcome (win/loss,
   engagement, conversion) flows back into the expected-value model
   with no human in the retrain path. Antiek's equivalent substrate
   exists: `auction_features.py` (≈9-dim feature vector, no-target-
   leakage guard), `auction_model.py` (calibrated logistic, offline
   batch GD, canonical-JSON artifact), `auction_ranker.py` (flag-gated
   re-ranker, rule-based fallback, MIN_MATCH_SCORE never bypassed).
   What is missing is the *label supply*: realized attention-weighted
   value per impression. §6 closes exactly that gap.
2. **Expected-value ranking over declared candidates.** Rank the
   operator-curated inventory by predicted value — never expand the
   candidate set by surveillance. Compatible with the targeting
   allowlist (`substrate/ad_inventory/targeting.py`: page/book
   metadata only; never gated body text, reader notes, or queries).
3. **Self-serve simplicity as craft.** The June-2026 GA reduced
   advertiser onboarding to pixel + budget + creative. The lesson for
   Antiek's own advertiser onboarding (Sprints 23-24 substrate,
   `advertiser_onboarding.py`) is form, not vendor.

Reusable **literally**: nothing on the supply side (no product exists);
on the demand side only the Axon pixel / Conversion API / reporting
API, all gated behind Wedge 3's unlocks (§8).

### 1.4 The Bernays reading — which half of Bernays we take

Bernays' *Crystallizing Public Opinion* / "engineering of consent"
tradition contains two separable ideas. The half Antiek **rejects** is
covert preference manipulation — surveillance-derived targeting,
third-party identity graphs, persuasion that works because the subject
doesn't see it. That half is structurally impossible here by prior
decision, not by taste: targeting inputs are allowlisted metadata only
(ε=0 on query content; DP claims hard-capped ε≤10,
`trust_center_public.md:77-92`), and `personal_reading` content can
never be served, attributed, monetized, or trained on
(`substrate/constants.py:548-631`, import-time asserts).

The half Antiek **keeps** is Bernays' actual operational insight:
credibility is infrastructure. An ad is believed when the medium is
dignified and the endorsement is real. Concretely: (a) the
Times-Square border monetizes the *margin* of the reading surface and
is forbidden from monetizing attention to itself
(`useFrameAttention.ts:6-8` — the border excludes itself from
sampling); (b) intent targeting matches ads to what a page is *about*
and what its audience declared they want — sector/sub-sector/audience-
intents (`intent_targeting.py`), which is Bernays' "align with an
existing want," minus the covert half; and (c) **paying the drivers of
content value is itself the credibility mechanism** — a platform that
can prove, per frame, which sources earned the reader's attention and
route 70% of ad revenue to them (§9.1's structural split) is doing
third-party endorsement with receipts. That is the Bernays lens this
spec operationalizes: §7 is its engineering.

---

## 2. What AppLovin is NOT — the misreadings to avoid

### 2.1 NOT a monetization option for a web reading platform

Verified 2026-07-02 across support.applovin.com's platform list and
product docs: MAX supports iOS, Android/Fire OS, and engine wrappers
(Unity et al.) — **there is no JavaScript/web publisher SDK and no web
ad-serving product anywhere in the portfolio.** ALX's supply is the MAX
SDK footprint (in-app), Wurl's is CTV. Q1-2026 earnings named CTV — not
web — as the supply priority. "Adopt AppLovin Ads to monetize Antiek"
is therefore a category error: the phrase "AppLovin Ads" (June 2026
rebrand) names their *advertiser* platform, not an ad network a website
can join. Any future reversal (§13 W4) requires a product that does not
exist today plus a native app Antiek does not have.

### 2.2 NOT a licensable model, an API, or an inspectable system

Axon cannot be licensed, called, fine-tuned, or audited. Access is
exclusively via ad spend on AppLovin's demand surfaces. Advertisers get
no demographic targeting, no placement-level control, no user-level
export, click-window attribution only (0/7-day; no view-through), and
no explanation surface — the CEO's own framing is "We can't see into a
black-box algorithm." For a platform whose recorded discipline requires
explainable selection in the early revenue regime
(`intent_targeting.py:22-28`; learned ranking only as a flag-gated
in-process *preference* with a rule fallback), a black-box external
auction is not a shortcut — it is a violation.

### 2.3 NOT a neutral measurement stack

Adjust (the MMP) is AppLovin-owned: measurer and seller are the same
company. Self-reported incrementality is contested — Muddy Waters
(2025-03-27) estimated only ~25-35% of e-commerce conversions were
incremental vs AppLovin's >100% ROAS claims; the June-2026
Google/Meta/Moloco/Unity investment in AppsFlyer was publicly framed as
keeping measurement neutral in exactly this environment. If Wedge 3
ever unlocks, measurement is holdout/geo-test + neutral MMP, never the
vendor dashboard (§12 R-W3-2).

### 2.4 NOT reputationally settled

As of 2026-07-02: an SEC probe into data-collection practices is active
(Bloomberg 2025-10-06; confirmed "still active and ongoing"
2026-02-20); securities class actions remain live in N.D. Cal.; a Dutch
class action by The Privacy Collective — publicly backed by Amnesty
International (May 2026) — alleges unlawful tracking of millions
including ~1.5M children via AppLovin SDKs; and AppLovin quietly shut
down Array in Q3 2025, a de facto partial confirmation of the one
short-seller claim (consent-ambiguous installs) that named a concrete
mechanism, followed by a code-evidence SEC complaint from Ben Edelman
(2025-10-15). Balance requires noting: no Apple/Google enforcement
occurred, one short report (CapitalWatch) was retracted with an apology
(2026-02-09), and the market shrugged (S&P 500 inclusion, +59% Q1-2026
revenue). The honest posture: the *business* is thriving; the *data
practices* are unresolved. A rights-respecting reading platform treats
that as a counterparty risk to be contracted around (§12), not a
disqualifier of the engineering ideas (§6).

---

## 3. The single architectural decision that drives every wedge

> **Copy the loop, never the network. The substrate is the only
> auction, attribution, and payout brain; anything external is at most
> a demand input that arrives through the same gated rail as every
> other dollar.**

Consequences, each anchored to an existing binding surface:

1. **Serving decisions stay in-process and explainable.** The learned
   ranker is a preference, not a gate (`auction_ranker.py`; rule
   fallback; MIN_MATCH_SCORE floor). No external auction ever decides
   what renders on a reading surface (§10 R5).
2. **Attribution truth is substrate-computed.** Chunk-level attribution
   is the moat (§9.9); the 70/30 split is structural (§9.1:1345,
   §13.9:2342). A vendor whose reporting granularity cannot feed
   `route_impression_revenue` cannot carry the product thesis (§10 R6).
3. **Money touches one rail.** All contributor value routes through the
   single audited accrual mechanism — `ip_holders.accrue_escrow` is the
   only escrow writer (guard: `tests/test_seam_single_escrow_writer.py`)
   and disbursement stays behind G2/G3 (§9.0: "The gate is not
   negotiable"). An ad-network payout would be a second *input* to this
   mechanism, never a second mechanism
   (`docs/decisions/spr-10-ai-graded-payout.md`).
4. **The monetization shape is settled.** §15.10 makes pay-as-you-go
   the "non-negotiable substrate-level commitment"; network-mediated ad
   revenue as a primary monetization shape would be a substrate-level
   escalation to the operator, and §9.0.1 already records that ad
   revenue ($0.05-$0.20/session) structurally cannot fund token costs.
   Ads pay *IP holders and creators*; they do not fund compute.
5. **Programmatic display remains rejected until BOTH of its recorded
   gates fire.** Two separate recorded decisions, both unfired: (a)
   engineering_deferrals **D7** — unlock is D1 (multi-user pivot)
   closing plus a first creator cohort live and accruing; (b)
   sprint30_thread_decisions **Thread 3** — the quarterly-renewed
   DEFER whose trigger is aggregate advertiser spend exceeding
   ~$50K/mo manual-curation capacity (currently $0), with the only
   SSP candidates ever named being Google Ad Manager or Magnite.
   Nothing in this spec re-opens either.

---

## 4. Mapping AppLovin primitives to Antiek's substrate

| AppLovin primitive | Antiek seam | Disposition |
|---|---|---|
| Axon closed learning loop (outcomes → EV model, no human in retrain path) | `auction_features.py` / `auction_model.py` / `auction_ranker.py` + labels from `frame_attention_accruals` | **Wedge 1** — finish the in-substrate loop |
| Axon expected-value ranking | `auction_ranker.py` flag-gated re-rank over operator-curated inventory | already on `main`; W1 feeds it real labels |
| Axon pixel (web JS) | — | **REJECT R2** — identifier/data-practice collision with rights posture |
| Conversion API (S2S, `POST b.applovin.com/v1/event`, mandatory `dedupe_id`, `user_data` requires ≥1 user identifier) | would require a new egress seam + hashed-identifier release | **Wedge 3 (DEFER)**; identifier requirement may be fatal (§8.3) |
| Reporting API (`GET r.applovin.com/report`, 45-day window) | warehouse pull, ≤40-day poll cadence | only within W3 if unlocked |
| MAX mediation / ALX supply | none — mobile-app SDK only | **Wedge 4 (DEFER — possibly REJECT)** |
| Adjust MMP | — | **REJECT R4** — measurer=seller |
| GenAI creative tools | house creative stays under §5 voice/style discipline | observe only; no adoption |
| Array-class distribution | — | **REJECT R7** (product itself already shut down) |
| Self-serve onboarding UX | `advertiser_onboarding.py` (operator-manual state machine) | design reference only, post-OA-016 |

---

## 5. Verdict matrix

| # | Wedge / shape | Verdict | Sprint |
|---|---|---|---|
| W1 | Close the in-substrate Axon loop (attention-labeled retraining of the learned auction, in-process, flag-gated) | **INTEGRATE NOW** — after W2's S1 lands (trustworthy labels require server-minted value) | next substrate sprint window |
| W2 | Per-frame revenue-split attribution program (six named gaps; companion execution spec) | **INTEGRATE NOW** — substrate-native, no vendor contact, no gate crossed | next substrate sprint window |
| W3 | Demand-side "AppLovin Ads" paid acquisition for Antiek growth | **DEFER — gated** on §13.3 (growth-doctrine overturn in writing + live conversion event + identifier-minimization resolution + contract terms). If the identifier conflict (§8.3) is unresolvable → convert to REJECT permanently | — |
| W4 | Supply-side monetization via MAX (requires a native mobile app) | **DEFER — possibly REJECT permanently** (no app exists; §9.4/D7/Thread-3 trigger unfired; recorded SSP candidates are GAM/Magnite, not AppLovin) | — |
| R1 | AppLovin as a dispatch provider | **REJECT** | — |
| R2 | Axon pixel on any Antiek surface | **REJECT** | — |
| R3 | Sharing first-party reader/advertiser data into Axon training | **REJECT** | — |
| R4 | Adjust as the measurement layer | **REJECT** | — |
| R5 | Any external auction as a serving gate | **REJECT** | — |
| R6 | AppLovin-reported metrics as attribution/revenue truth | **REJECT** | — |
| R7 | Array-class distribution mechanics | **REJECT** | — |
| R8 | Replacing per-frame attribution with network-level revenue granularity | **REJECT** | — |

---

## 6. Wedge 1 — Close the in-substrate Axon loop (INTEGRATE NOW)

**What it does.** Supplies the missing label stream to the existing
Axon-style learned auction and turns on measured, flag-gated,
explainable re-ranking of house/lead-gen fills:

0. **Fill-decision record (precursor, ~1 day).** Persist the serving
   decision at fill time: one typed record linking window_id → chosen
   fill (kind, inventory_id, candidate set, per-candidate features and
   scores, ranker/artifact version). Today the `ad_fill` handler
   returns its `AdFillResponse` and records NOTHING (verified
   2026-07-02: no emission or persistence anywhere in the fill path,
   `interfaces/research/api/ad_routes.py`), so without this precursor
   the label join below has nothing to join to. Ships under the
   standing schema discipline: EVENT_SCHEMA_VERSION bump + bump-log +
   same-commit TS regen on python 3.14.
1. **Label extraction (offline).** A batch job derives per-impression
   value labels in [0,1] from `frame_attention_accruals` — realized
   attention-weighted value of the fill's window (area × (1+prominence)
   × (1+dwell/1000) blend already normalized by `weigh_second`) —
   joined to the fill-decision record from step 0. Labels are
   computed ONLY from batches that pass W2's trust hardening (S1
   server-minted value + S2 anti-gaming filter); pre-hardening rows are
   excluded by version stamp (`frame-telemetry-v1` rows with
   client-supplied nonzero value do not exist in practice — the shipped
   emitter hard-codes 0 — but exclusion is by rule, not by hope).
2. **Retrain (offline).** `auction_model.py`'s batch GD over the
   existing ≈9-dim feature vector; artifact serialized as
   canonical-JSON with a version stamp and committed like any other
   reviewed artifact. No new deps (§16 no-new-heavy-dep holds; the
   module's own docstring records the trade and its flip condition).
3. **Serve (online, flag-gated).** `ANTIEK_LEARNED_AD_RANKER` stays the
   opt-in; rule-based fallback and MIN_MATCH_SCORE floor are untouched;
   the no-target-leakage guard in `auction_features.py` remains the
   contract test surface.
4. **Explainability record (the Sutskever/Radford bar, §7.2).** Every
   learned-ranked fill decision logs: feature vector, model artifact
   version, score, rank position, and the rule-ranking it displaced —
   enough to replay any serving decision byte-for-byte offline. An
   inspection CLI renders "why this fill won" from the log alone.

**What this wedge does NOT do.** No vendor contact. Exactly ONE
schema change — the step-0 fill-decision record (honestly declared;
an earlier draft claimed fill decisions were already event-logged,
which verification refuted). No serving-gate change. No pricing
change (ad_value stays $0 until SPR-10 pricing + OA-016 advertisers
exist). No touching `synthesis_rubric` hot paths (194.85μs p95 lock).

**Sequencing constraint.** Hard-after W2-S1/S2 (label trust). Ships
dark behind the existing flag; A/B harness (already stubbed per
`auction_model.py` docstring: "the A/B harness owns turning recorded
sessions into labels") decides promotion.

**Acceptance criteria.**
- [ ] Label job is deterministic: same accrual rows + same version ⇒
      byte-identical label set (golden test).
- [ ] Retrained artifact beats the rule ranking on held-out sessions on
      the recorded value metric, measured by the A/B harness — or the
      wedge honestly reports it doesn't and the flag stays off.
- [ ] Every learned decision replayable from logs alone (inspection CLI
      output matches served decision in a regression test).
- [ ] Guards green: no-target-leakage contract tests, rule fallback
      exercised in tests, MIN_MATCH_SCORE floor test unchanged.
- [ ] hardenx 0 REAL; ruff/mypy declared bar; no baseline edits.

**Estimated effort.** 2-4 agent-days after W2-S1/S2. All in-substrate.

---

## 7. Wedge 2 — Per-frame revenue-split attribution program (INTEGRATE NOW)

This is the operator mandate's engineering core: "perfect the revenue
split attribution per frame so that I can pay the drivers of content
value." The frame-attention pipeline on `main` is real and good — 1Hz
per-asset sampling with honest units (`useFrameAttention.ts`), one
batch per window (`frameTelemetryClient.ts`), server-side rights
resolution, exact cent conservation via largest-remainder
(`frame_attention.py`, `frame_attention_accrual.py`), single escrow
writer, accrual-≠-disbursement. The investigation (10 lanes + critic,
2026-07-02, all claims re-verified line-level on `origin/main`) found
**six named gaps** between that pipeline and a payout system that can
defensibly pay people. This wedge fixes them. A companion execution
spec (`~/Antiek/specs/antiek-frame-attribution/`, htmlspec form,
authored by this lane as the execution vehicle) carries the sprint
pages; the scope and acceptance bar below are binding on it.

### 7.1 The six gaps (each verified, each with its fix)

**S1 — Server-minted value + endpoint authentication.**
`POST /api/ad/frame-telemetry` is registered with no auth dependency
and passes client-supplied `ad_value_usd_cents` straight into
`accrue_window` (`ad_routes.py`, verified on `origin/main` 2026-07-02).
Today this is bounded — the shipped emitter hard-codes 0, escrow is
non-disbursable, no pricing exists — but it means *no existing or
future accrual row derived from client-priced input may ever be treated
as trusted revenue*. Fix: value becomes server-minted at accrual time
(joined from the fill/pricing record by window_id; client field
demoted to an ignored legacy hint under a bumped
FRAME_TELEMETRY_SCHEMA_VERSION), and the route gains the same session
auth as the rest of the authenticated surface plus per-session rate
limits. Wire-shape change ⇒ version bump on BOTH sides (contract
source of truth stays the Python dataclasses → TS codegen).

**S2 — Anti-gaming mediation for frame batches (filter-before-
allocate).** `substrate/anti_gaming/` has zero coverage of frame
batches (grep verified: impression/click fraud only), yet §9.7 requires
every impression-revenue path to pass the composite anti-gaming verdict
before transfer. Fix, applying the MRC IVT model (invalid traffic is
non-billable, not merely flagged): a pre-accrual filter stage that
excludes invalid seconds from numerator AND denominator — GIVT-class
(known-bot UA, datacenter IP, impossible cadence: >1 batch/window,
second_index gaps/replays, dwell>1000ms) and SIVT-class heuristics
(implausible constant-attention signatures) — plus **per-identity
saturation**: countable dwell per (user, asset, day) saturates at a
published cap, so a sybil's maximum influence is bounded (the $10M
DOJ-prosecuted bot-streaming fraud is the precedent for what uncapped
units invite). Post-hoc detection triggers recomputation/clawback of
*escrow* (never of disbursed funds — clawback risk is one more reason
disbursement waits for G2/G3). Every filtered second is counted and
reported (honesty-over-coverage, same posture as the sampler's
`unresolved` counter).

**S3 — Frame→synthesis→chunk composition ("pay the DRIVERS of content
value").** Today a frame showing a synthesis artifact monetizes the
artifact's own `document_id`; the §9.3 chunk-level share math
(`supporting_chunk_ids` → chunk → document → ip_holder, Options A/B/C)
exists but composes with frame value nowhere — so the sources that
*drove* the synthesis earn nothing from its reading. This is the gap
between "pay whoever owns what was on screen" and the operator's
"pay the drivers of content value." Fix: when a monetized asset is a
synthesis artifact, its per-window value splits through the recorded
§9.3 share vector (Option B weighting per spr-10 precedent) into the
constituent documents' escrow — one composition function, unit-tested
against hand-computed splits, using the SAME largest-remainder
primitive so cents still conserve exactly. Reading-physics anchorKeys
(`chunk:/claim:/passage:`) remain the render-side identity; the
composition happens server-side at accrual, keyed by the artifact's
recorded share vector version. Two "frame" vocabularies exist in the
repo (render-pass anchor frames vs per-second attention FrameSeconds);
this spec fixes the money meaning: **the billable unit is the
FrameSecond sample, and anchor frames are its provenance resolution
path** — recorded here so no future sprint re-derives it.

**S4 — One payable truth across three ledgers.** Three accrual ledgers
coexist on `main`: `frame_attention_accruals` (per-window/asset),
`marketplace_metrics/book_escrow.py` (per-impression, hanging off the
legacy reader-rail route), and `substrate/payouts/ledger.py` (per-
author, arXiv, keyed (arxiv_id, author_position)). They may hold
overlapping value only while nothing disburses. Fix: declare
`frame_attention_accruals` the payable source for reading-surface
attention value; book_escrow becomes derived/reporting or is
reconciled-and-retired (decision recorded in the companion spec after
measuring what writes to it); the per-author ledger remains the
DOWNSTREAM splitter for multi-author works (see S5). A reconciliation
job proves, per window, that no cent appears in two payable ledgers.

**S5 — Split composition: platform cut, author split, license tiers,
carve-outs — in a published order.** The frame pipeline conserves 100%
of window value to contributors+house; `payout.py` applies 70/30 with
a $50/day per-document cap and a $10 KYC floor; `payouts/split.py`
applies author-split-equal-v1; `rights/ad_eligibility.py` allows ads on
T1 arXiv licenses only (re-derived from immutable `license_uri`, never
a stored tier). Nothing composes them. Fix — the published, versioned
pipeline order (each stage its own version stamp, composing into one
`attribution-math-v2` identifier):
  1. pool = Σ server-minted window values (S1);
  2. **deterministic carve-outs first** (licensed third-party content
     embedded in a frame takes its fixed fraction pre-pooling — the
     YouTube-Shorts-music precedent);
  3. platform cut 70/30 at the pool boundary (§9.1 structural);
  4. per-frame split of the creator pool by filtered attention weights
     (S2) with synthesis composition (S3);
  5. per-document → per-holder resolution: license-tier gate (T1-only
     for arXiv), rights-state gate (`monetization_eligible`,
     deny-by-default), author split via SPLIT_POLICY_VERSION;
  6. residuals: any value that resolves to no eligible holder routes to
     the EXISTING `UNATTRIBUTED_RIGHTS_BUCKET` sentinel (held, never
     misattributed, disposition disclosed) — the repo already has the
     idiom; reuse it, never invent a second residual bucket.
  Every stage conserves exactly (largest-remainder only, one shared
  primitive); a golden test walks a synthetic month end-to-end.

**S6 — Auditability: replayable statements (the bar in §7.2).** The
pipeline already version-stamps math and snapshots inputs
(`attr-math-v1`, `frame-telemetry-v1`, `frame-weight-v1`, replay
functions in `frame_attention_accrual.py`). Fix completes it into
per-payee proof: a monthly attribution close computes a canonical
statement per IP holder (decomposable to per-window aggregates), plus a
tamper-evidence layer — an append-only hash chain over the month's
accrual rows with a published month root and per-payee inclusion
proofs (certificate-transparency pattern, implemented with the stdlib —
a Merkle tree over canonical-JSON rows; no new deps). "Trust the
dashboard" is the failure mode of every production rev-share system
surveyed (Medium's undisclosed weights, X's opaque formula, music's
$426.9M unmatched black box); Antiek's differentiator is the formula
fully published + the statement independently checkable.

### 7.2 The auditability bar (Sutskever/Radford, made checkable)

Named for the discipline, not the celebrity: Radford's habit of
radical simplicity in the loop (one model, one objective, measured
end-to-end) and Sutskever's insistence that capability claims be
backed by evaluation. Binding form, inherited by W1 and by every
companion-spec sprint:

1. **Deterministic replay.** Payout is a pure function of (append-only
   event/accrual log, published formula version, published
   parameters). Any stochastic component commits seed + sample count +
   value-function version to the log first. No `Date.now()`-class
   nondeterminism inside split math.
2. **Measured, not modeled, at the payout layer.** Vendor/ML attention
   *scores* may inform pricing or ranking (W1); an individual's payout
   rests only on events the payee could audit (S6 statements).
3. **Published mechanism.** Formula, weights version, caps, and
   thresholds are public artifacts. Gaming resistance comes from
   robust units, saturation caps, and IVT filtering (S2) — never from
   secrecy (Medium's opacity got gamed anyway; ~1.7% of partner
   accounts suspended).
4. **No silent thresholds.** Any minimum-payout rule carries balances
   forward rather than zeroing long-tail earnings (Spotify's
   1,000-stream rule demonetizing ~87% of tracks is the anti-pattern);
   redistribution destinations are disclosed.
5. **Every learned component ships with its eval harness** (W1's A/B
   gate) and logs enough to reproduce each decision.

### 7.3 What this wedge does NOT do

No disbursement — G2 (lawyer) + G3 (publisher opt-in) + OA-007 (Stripe
real-mode) + OA-008 (anti-gaming external red-team) remain untouched
operator gates; everything accrues to escrow with `disbursable=False`
pinned. No pricing — window values stay 0 until SPR-10 auction pricing
plus OA-016 advertisers exist; S1 simply makes the zero server-minted.
No new external vendors. No DuckDB second writer (all writes through
`runtime/db_lock.connect_write` inside the --workers-1 uvicorn). No
per-second rows or requests (batching rule is binding). No new heavy
deps (Merkle layer is stdlib hashlib over canonical JSON).

**Acceptance criteria (program-level).**
- [ ] The §7.1 six gaps each closed with red-proven tests (each fix's
      test fails on pre-fix `main`).
- [ ] End-to-end golden month: synthetic sessions → filtered →
      composed → statements; Σ statements + house + unattributed ==
      pool, to the cent, twice (replay determinism).
- [ ] Adversarial fixtures: sybil farm, replayed batches, forged
      value, NC-licensed (T2) content, personal_reading content — each
      provably earns zero and is REPORTED, not silently dropped.
- [ ] CI: codegen staleness green (py3.14 regen), declared bar green,
      latency lock untouched, hardenx 0 REAL.
- [ ] `docs/master-product-spec.md` §9.7 OPEN item updated to cite the
      shipped mechanism (attribution-gaming risk narrows from "open"
      to "mitigated pre-disbursement; red-team OA-008 still required").

**Estimated effort.** 6 sprints, fleet-executable in 2-3 waves;
S1+S2 first (they gate W1), S3-S5 second, S6 third.

---

## 8. Wedge 3 — Demand-side AppLovin Ads for growth (DEFER — gated)

**What it would be.** Antiek as an *advertiser*: Axon pixel or (more
plausibly) S2S Conversion API events for a defined conversion
(subscription purchase / qualified signup), buying performance
campaigns (ROAS / cost-per-purchaser / cost-per-lead) inside
AppLovin's ~140k-app mobile inventory to acquire readers.

**Why DEFER, not INTEGRATE.** Four independent blockers, each
sufficient:

1. **Recorded growth doctrine forecloses it.** master-product-spec
   L1339: growth is "organic discovery through artifact quality, not
   paid acquisition or enterprise sales" (reaffirmed in the Sprint-20
   visible-artifact motion). A paid-UA wedge requires the operator to
   overturn a recorded doctrine in writing — an operator decision, not
   an unlock an agent can engineer toward.
2. **Nothing to optimize.** Performance-only buying needs a measurable
   conversion; Antiek pre-G2/G3/OA-007 has no live purchase event and
   is single-user by design until Sprint 22 (G7). A campaign today has
   no objective function.
3. **The identifier conflict (§8.3) may be fatal.**
4. **Counterparty risk terms (§12) must be contracted first.**

**§8.3 The identifier conflict, stated precisely.** The Conversion API
requires `user_data` to contain at least one user identifier per event
(client_id / axwrt / alart / user_id / email-SHA256 / phone-SHA256,
plus IP/UA; developers.axon.ai, verified 2026-07-02). The risk-audit's
binding data-minimization posture — aligned with the rights states and
the live SEC-probe context — is that reading behavior and user-level
identifiers must be architecturally incapable of entering AppLovin's
ingestion path, and AppLovin's own Axon legal page grants ingested
partner data continual-training use with no stated retention limits or
opt-out. **These are mutually exclusive as the API stands.** Possible
resolutions, in decreasing acceptability: a contractual no-train/
retention/deletion addendum (available only at negotiated tiers, if at
all); consent-scoped hashed-email release for the single conversion
event, never for reading behavior; or AppLovin shipping an
identifier-free conversion mode. If none materializes by the time the
other unlocks fire, W3 converts to REJECT permanently and joins §16.1.

**Even if unlocked:** audience fit is unproven (game-dominant
inventory driving out-clicks to a research reading product;
third-party analyses report heavy last-click misattribution for
game-sourced traffic), so the entry shape is a capped spike —
30 days, hard daily budget (`APPLOVIN_DAILY_BUDGET_USD`), neutral-MMP
+ geo-holdout measurement, pre-registered success metric — graded by
the operator, with a losing spike recorded as a dated REJECT.

---

## 9. Wedge 4 — Supply-side monetization via MAX (DEFER — possibly REJECT permanently)

Requires, in order: (a) a native Antiek mobile app — none exists or is
planned; (b) the programmatic unlock: BOTH D7 (D1 multi-user close +
live accruing creator cohort) AND Thread 3 (advertiser spend >
~$50K/mo manual-curation capacity; currently $0; DEFER renewed
quarterly in writing); (c) G2/G3 and the §9.0 quadruple
gate; (d) overturning Thread 3's recorded SSP candidate list (Google Ad
Manager or Magnite — AppLovin has never been on it) with a written
rationale; (e) AppLovin publisher policy fit (substantive original
content, moderated UGC, Better Ads Standards) and payment mechanics
(first-Monday eligibility, $100 minimum, Tipalti). Each of (a)-(d) is
independently unfired. This wedge exists in the matrix so the rejection
of *today's* adoption is precise rather than absolute; it should be
promoted to a permanent REJECT if the app question is still closed when
the Thread-3 trigger first fires.

---

## 10. Explicit rejections (don't re-litigate)

Stated once. The verdicts are settled. Re-open only if the underlying
substrate or product state changes meaningfully. Flag each for
consolidation into master-product-spec §16.1 so they cannot be quietly
re-opened by a sprint-level decision.

### REJECT R1: AppLovin as a dispatch provider

`substrate/dispatch/providers/` is the LLM provider abstraction —
OpenAI-shaped chat-completions adapters behind Hermes-primary routing.
AppLovin is not an LLM; Axon is not callable at all. Abstraction
mismatch; same rejection logic as Exa spec §12.1 and every peer spec.
Dispatch stays Hermes-primary per §16. Reversibility: none foreseeable.

### REJECT R2: The Axon pixel on any Antiek surface

The pixel exists to build conversion identity for Axon training.
Installing third-party surveillance JS on a reading surface whose
rights model includes `personal_reading` (never serve / attribute /
train) and whose targeting doctrine forbids behavioral signal
collection is a direct philosophy violation — and it would occur under
an active SEC probe into precisely this data-practice class.
Server-side S2S (W3) exists as the strictly-more-controlled
alternative; the pixel is never it. Reversibility: none while the
rights states exist.

### REJECT R3: Sharing first-party reader or advertiser data into Axon training

AppLovin's Axon legal page: models "train and optimize on a continual
basis" on partner-shared data, no retention limits, no opt-out stated.
Data shared is a one-way donation to a model that serves competitors.
Violates the substrate-as-moat premise and the trust-center posture.
Reversibility: a signed no-train/retention/deletion addendum with
audit rights would move *specific, enumerated* conversion events (not
reader behavior — never reader behavior) into W3's scope; nothing more.

### REJECT R4: Adjust as the measurement layer

Measurer owned by seller. Independent verification is the entire point
of measurement. If W3 ever runs: neutral MMP (e.g. AppsFlyer) +
partner-run geo-holdouts. Reversibility: divestiture of Adjust, plus
still preferring neutral tooling.

### REJECT R5: Any external auction as a serving gate

Recorded discipline: learned ranking is an in-process, flag-gated
*preference* with a rule fallback and an explainability record
(`intent_targeting.py:22-28`, `auction_ranker.py`, §7.2). An external
black-box that decides what renders — even "just for the paid slice" —
inverts the control relationship and is unauditable by construction
(the vendor's own CEO says so). Reversibility: none; this is
architecture, not vendor choice.

### REJECT R6: AppLovin-reported metrics as attribution or revenue truth

Click-window-only self-reporting (0/7-day, no view-through, no
user-level export, 45-day retention), contested incrementality
(25-35% independent estimate vs >100% claimed), and a structural
conflict of interest. Antiek's attribution truth is substrate-computed
(§3.2); if W3 runs, vendor numbers are a *reconciliation input* against
holdout-measured lift, never the ledger. Reversibility: none.

### REJECT R7: Array-class distribution mechanics

Consent-ambiguous install/distribution flows are the one short-seller
allegation with a de facto partial confirmation (product shut down
Q3 2025, code-evidence SEC complaint filed). No Antiek distribution
path may ever depend on install mechanics a user did not explicitly
initiate through an official store. Reversibility: none.

### REJECT R8: Replacing per-frame attribution with network-level revenue granularity

The temptation once any network revenue exists: book it at
campaign/day granularity and skip the frame math. That deletes the
product thesis — chunk-level attribution IS the moat (§9.9), and the
70/30 split routes through it (§9.1). Any external revenue enters the
pool at window granularity or is held unallocated in the house bucket;
it never coarsens the split. Reversibility: none.

---

## 11. Cost, legal, and safety envelope

### 11.1 Cost

Committed spend under this spec: **$0.** W1/W2 are in-substrate
engineering. If W3 ever unlocks: billing at self-serve GA is prepaid
credit-card, charged daily at 0:00 UTC for the next day's budget
(support.axon.ai, verified 2026-07-02; the invite-era wire/ACH-only
rail appears superseded — §15 OQ-2); budget control via
`APPLOVIN_DAILY_BUDGET_USD` with a hard monthly ceiling in config;
reporting pulled ≤ every 40 days against the 45-day retention window.
Practitioner guidance treats ~10 conversions/day as the practical
optimization floor — Antiek is nowhere near it pre-Stripe; a spike
below that floor measures nothing (one more reason W3 waits). Confirm
current pricing before any sprint commit. Re-verify quarterly.

### 11.2 Legal

Live, dated, unresolved as of 2026-07-02: SEC probe into
data-collection practices (opened per Bloomberg 2025-10-06;
"still active and ongoing" 2026-02-20); N.D. Cal. securities class
actions; Dutch Privacy Collective action (May 2026, ~1.5M children,
Amnesty-backed, multi-billion-euro exposure); Edelman SEC complaint
(2025-10-15, Array). Balanced by: no Apple/Google enforcement, one
retracted short report (2026-02-09), S&P 500 inclusion. Consequence:
any W3 contract must carry the §12 counterparty terms, and any
public association is an explicit operator decision (R-W3-4). None of
this touches W1/W2, which involve no AppLovin relationship.

### 11.3 Safety / rights

The §9.0 quadruple gate is unaffected and unaffectable by this spec:
retrieval-time gating (G1, closed) + lawyer review (G2, open) + first
publisher affirmative opt-in (G3, open) — the G-gates live in
`docs/operator_gate_actions.md` — plus Stripe real-mode (OA-007),
OA-008 (external anti-gaming red-team — precondition for Sprints
23-24 shipping), OA-016 (3 signed advertisers >$5K/mo), and OA-017
(KYC/1099 counsel) — the OA items live in `docs/OPERATOR_ACTIONS.md`. W2 makes the eventual crossing of those gates
*safer* (server-minted value, anti-gaming filter, provable
statements); it does not move them. Rights states remain deny-by-
default; `personal_reading` produces zero ad attribution, zero escrow,
zero training exposure, always.

---

## 12. Risks and mitigations

**R-W1-1 — Goodhart on the learned ranker.** Attention-derived labels
create an incentive to rank fills that farm attention. Mitigations:
labels only from S2-filtered batches; saturation caps bound any single
identity's influence; the A/B harness measures against held-out value,
not raw dwell; §9.7's composite anti-gaming verdict mediates before
any transfer; OA-008 red-team is the external check. Residual risk
recorded honestly: a heuristic filter is not a solved detector (same
posture as spr-10's `gamed_risk` flag).

**R-W1-2 — Label sparsity ($0 pricing era).** Until SPR-10 pricing +
real advertisers, "value" labels reduce to attention-weighted zeros.
Mitigation: W1's model trains on the attention *signal* as a value
proxy with the proxy-ness recorded in the artifact metadata; promotion
to real-value labels is a named re-train trigger, not a silent drift.

**R-W2-1 — Attribution-formula disputes.** A published formula invites
published disagreement (author-split, carve-out fractions).
Mitigation: every stage versioned and operator-contestable (the
author-split default is already recorded as contestable in
`docs/decisions/arxiv-author-split-equal-default.md`); disputes change
a version, never rewrite history (append-only ledgers + statements).

**R-W3-1 — Audience mismatch burns spend.** Game-inventory out-clicks
vs a research reading product. Mitigation: capped pre-registered
spike, neutral measurement, losing-spike-converts-to-REJECT.

**R-W3-2 — Vendor-graded homework.** Mitigation: R4/R6 — neutral MMP +
geo-holdouts; AppLovin numbers reconcile, never decide.

**R-W3-3 — Counterparty data practices.** Mitigation: the contract
terms are unlock criteria (§13.3): no-train clause with audit rights,
retention/deletion SLAs, fingerprinting/identifier-bridging warranty
(ATT/Play-policy compliance), children's-data firewall + indemnity,
regulatory-action termination trigger with mandatory disclosure.

**R-W3-4 — Reputational transfer.** Public association with an
SEC-probed, Amnesty-sued adtech vendor onto a rights-respecting
reading brand. Mitigation: operator-explicit acceptance required; no
co-marketing; no vendor branding on any Antiek surface.

**Named Plan B (mono-vendor discipline).** If W3 unlocks and AppLovin
fails its terms: **Google Ads** (search/PMax) and **Meta** are the
named alternates — boring, better-audited, identifier-consent flows
mature. Trigger conditions for activating Plan B: (1) any §13.3
contract term refused or breached; (2) SEC probe → charges/settlement;
(3) any Apple/Google enforcement against AppLovin SDKs; (4) spike
fails its pre-registered metric; (5) ≥2× effective-CPA degradation
sustained 30 days; (6) TOS change incompatible with the rights states.
When a trigger fires: pause spend same-day (prepaid daily billing
makes this clean — the one integration-friendly property of their
billing model), export the 45-day report window, run the same spike
protocol on the alternate.

---

## 13. Unlock criteria for promoting wedges

Each wedge has explicit gates. Crossing them is the ratification event.

### 13.1 W1 (Axon-loop) — promote from dark to flag-on
- [ ] W2-S1 (server-minted value + auth) merged to `main`
- [ ] W2-S2 (frame anti-gaming filter + caps) merged to `main`
- [ ] A/B harness shows learned ≥ rule on held-out recorded value
- [ ] Explainability record verified by replay regression test
- [ ] Operator flips `ANTIEK_LEARNED_AD_RANKER` (operator action)

### 13.2 W2 (attribution program) — declare "perfected"
- [ ] All six §7.1 sprints merged with red-proven tests
- [ ] Golden-month replay: exact conservation, twice, byte-identical
- [ ] Adversarial fixture suite green (sybil/replay/forge/T2/personal)
- [ ] §9.7 OPEN item updated with the shipped-mechanism citation
- [ ] OA-008 external red-team scheduled against the NEW surface
      (operator action; precondition for any disbursement era)

### 13.3 W3 (demand-side) — open a spike
- [ ] Operator overturns the L1339 growth doctrine in writing (dated
      decision doc; quarterly-renewed like Thread 3)
- [ ] Live conversion event exists (Stripe real-mode OA-007 + G2/G3
      era; multi-user per G7/Sprint 22 for any scale beyond dogfood)
- [ ] §8.3 identifier conflict resolved by contract or product change
      (else convert W3 → REJECT and consolidate into §16.1)
- [ ] All five §12 R-W3-3 contract terms signed
- [ ] Spike protocol pre-registered (metric, cap, duration, neutral
      measurement) — losing spike = dated permanent REJECT

### 13.4 W4 (supply-side) — reconsider at all
- [ ] A native Antiek mobile app exists and has organic traction
- [ ] Thread-3 trigger fired (> ~$50K/mo manual-curation overflow)
      and the quarterly DEFER overturned in writing
- [ ] §9.0 quadruple gate + OA-016/OA-017 closed
- [ ] Written rationale for preferring AppLovin over the recorded
      GAM/Magnite candidates
- else at first Thread-3 firing with no app: promote to REJECT

---

## 14. Sprint placement

| Work | Where | When |
|---|---|---|
| W2-S1 server-minted value + auth | companion spec sprint 1 | next substrate window (gates W1) |
| W2-S2 frame anti-gaming + caps | companion spec sprint 2 | with S1 (wave 1) |
| W2-S3 synthesis composition | companion spec sprint 3 | wave 2 |
| W2-S4 ledger reconciliation | companion spec sprint 4 | wave 2 |
| W2-S5 split composition (70/30 + tiers + carve-outs) | companion spec sprint 5 | wave 2 |
| W2-S6 statements + month root | companion spec sprint 6 | wave 3 |
| W1 label job + retrain + explainability | after W2 wave 1 | 2-4 agent-days |
| W3 / W4 | none | gated (§13.3/§13.4), no sprint |

All substrate-only precursors (schema/codegen bumps) follow the
standing rule: EVENT_SCHEMA_VERSION bump + bump-log + same-commit TS
regen on python 3.14, or CI reds.

---

## 15. Open questions (genuinely unresolved)

**OQ-1 — Exact self-serve GA date/terms.** Sources conflict between
~June 1 and June 30, 2026 for the open-GA/rebrand boundary; immaterial
to any verdict here, but pin it (and current eligibility floors)
before any W3 spike. **OQ-2 — Billing rails at GA:** prepaid CC per
support.axon.ai vs the pilot era's wire/ACH-only; re-verify at spike
time. **OQ-3 — Identifier-free conversion mode:** does the Conversion
API (or a negotiated tier) ever accept eventless/aggregate conversions?
This single product fact decides whether W3 is ever possible (§8.3).
**OQ-4 — cost-per-lead maturity:** still "early testing" per launch
coverage; a subscription product would more plausibly buy
cost-per-purchaser. **OQ-5 — book_escrow disposition (W2-S4):** derived
vs retired — measure its writers first. **OQ-6 — user-centric vs
global pooling for the frame split:** the design-space evidence favors
user-centric denominators for sybil-boundedness (each reader's
subscription/ad value splits only across frames *they* attended;
SoundCloud fan-powered precedent), but Antiek's pool is ad-value-per-
window today; the companion spec must choose explicitly and publish
the choice (S5 stage-4 parameter, operator-ratifiable).

---

## 16. What to do now

1. **Execute W2** via the companion htmlspec
   (`~/Antiek/specs/antiek-frame-attribution/`) — six sprints, fleet-
   executable, S1+S2 first. This is the operator mandate's engineering
   core and it is unblocked today: substrate-only, no vendor, no gate.
2. **Then W1** (2-4 agent-days): close the in-substrate Axon loop dark,
   measure via the A/B harness, hand the operator a flag decision with
   an evidence page — the honest version of "use Axon."
3. **File the §10 REJECTs into master-product-spec §16.1** in the same
   PR series, so they are one-line citable forever.
4. **Do nothing on W3/W4** until their §13 gates move — and record in
   the quarterly Thread-3 renewal that AppLovin was evaluated and
   deferred with this spec as the citation.

Settled negative: **8 REJECTs** (R1-R8). The wedges in §6-§7 are the
integration. The rejections in §10 are the guardrails. The unlock
criteria in §13 are the ratchet.

---

## 17. Final note for the implementing agent

Precedence if this spec conflicts with anything: (1) the operator's
explicit words, (2) `docs/architecture_notes.md`,
(3) `docs/master-product-spec.md` — §9.0's gate language wins every
tie touching money, (4) this spec, (5) peer integration specs. The
operator's mandate was "explore adopting AppLovin" — the exploration
was done honestly, and the defensible adoption is: *adopt the loop
in-substrate (W1), perfect the attribution rail no vendor sells (W2),
and let the network wait behind gates it has not earned through.*
An agent who ships a pixel, a hidden identifier release, an
unauthenticated money write, or an unpublished formula because it was
faster has substituted the end for the means.

Never substitute the end for the means.
