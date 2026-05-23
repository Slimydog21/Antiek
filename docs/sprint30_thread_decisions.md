# Sprint 30+ — Per-Thread Evaluation and Go/Defer Decisions

**Status:** Template — to be filled in at the open of Sprint 30+ planning,
re-evaluated quarterly while Sprint 30+ is active.

**Discipline:** Per the Sprint 30+ doc §1 callout, *"threads without
cleared triggers stay explicitly deferred — the documented rejection IS
the deliverable."* This file IS that deliverable. A thread is either
live with a citable trigger-condition measurement OR deferred with the
current-quarter measurement that shows it isn't ready.

**Author:** _[operator]_

**Reviewed:** _[YYYY-MM-DD]_

**Marketplace snapshot referenced:** _[link to a stored
/marketplace/snapshot output at review time, or the
substrate/marketplace_metrics/ SHA]_

---

## §1 Decision summary

| Thread | Trigger condition | Current measurement | Verdict |
|--------|-------------------|---------------------|---------|
| Federation (signed-resource-pull) | A partner Antiek instance willing to negotiate a slice exchange | _[fill in]_ | _[GO / DEFER]_ |
| Long-tail rev-share | > 200 active monthly-earning creators | _[fill in]_ | _[GO / DEFER]_ |
| Programmatic auction | Aggregate advertiser demand > manual-curation capacity | _[fill in]_ | _[GO / DEFER]_ |
| Vision-capable role | ≥ 30% of citable source-corpus material is non-text | _[fill in]_ | _[GO / DEFER]_ |
| Autoresearch Wedge 3 (config sweeps) | ≥ 500 graded outcomes in cohort per §14.1 | _[fill in]_ | _[GO / DEFER]_ |
| Substrate Stage 1 → 2 (DuckLake sharded) | Per-user file count approaches OS handle limit OR catalog Postgres is contention point | _[fill in]_ | _[GO / DEFER]_ |

---

## §2 Per-thread evaluation

### Thread 1 — Federation (signed-resource-pull)

**Trigger:** a partner Antiek instance has expressed willingness to negotiate
a slice exchange and pin our verifying key against their substrate.

**Substrate readiness:** `substrate/federation/` shipped and tested
(signing.py, slice.py, protocol.py). HMAC-SHA256 scaffold; Ed25519 swap is a
single primitive change when the cryptography library is added.

**Current measurement:**
- Partner candidates: _[list institutions / orgs that have expressed
  interest, with the conversation reference]_
- Negotiation drafts filed: _[count, with neg_id refs]_
- Verifying-key fingerprints exchanged: _[count]_

**Verdict:** _[GO / DEFER]_

**If DEFER:** documented reason _[fill in]_; renewal date _[fill in]_.

**If GO:** first slice exchange scoped to _[topic_scope]_ between
_[partner substrate_id]_ and Antiek on _[scheduled date]_.

---

### Thread 2 — Long-tail user-as-IP-holder rev-share

**Trigger:** > 200 active monthly-earning creators above the §9.5 $10
threshold. Below 200, the long-tail mechanics aren't load-bearing yet.

**Substrate readiness:** `substrate/rev_share/`, `substrate/anti_gaming/`,
`tools/stripe_connect/payouts.py` shipped. Per-cluster collusion detection
in place. Tax-export helper (`export_tax_year`) produces accountant-review
format.

**Current measurement:** _[pull from /marketplace/snapshot →
creators.creator_count above bucket ≥ $10]_

**Verdict:** _[GO / DEFER]_

**If DEFER:** typical reason — creator population still in scaling phase
post-Sprint 23-24. Re-evaluate at next quarterly checkpoint.

**If GO:** anti-gaming layer scales up; 1099 export schedule activated;
tax-tooling integration (Drake / TaxJar) onboarding begins.

---

### Thread 3 — Programmatic auction

**Trigger:** aggregate advertiser monthly spend exceeds operator's
manual-curation capacity (default §9.4 threshold: $50K/mo per advertiser
× operator-decided headcount). Below the trigger, lead-gen manual curation
continues; programmatic infrastructure cost + brand-safety overhead are
not justified.

**Substrate readiness:** NOT shipped — `substrate/ad_inventory/programmatic.py`
is on the Sprint 30+ punch list (conditional on this verdict). SSP
candidates: Google Ad Manager OR Magnite.

**Current measurement:**
- Manual curation hours per week: _[fill in]_
- Aggregate advertiser monthly spend: _[pull from advertiser_retention
  total_spend_current_cents]_
- Self-service threshold already crossed? _[YES / NO; pull from
  crosses_self_service_threshold]_

**Verdict:** _[GO / DEFER]_

**If DEFER (default):** the rejection is renewed with this measurement.
Per the Sprint 30+ doc Thread 3, *"if not triggered: the rejection is
renewed in writing with current-quarter numbers."* THIS is the renewal.

**If GO:** SSP onboarding starts; brand-safety classifier scaffolds
against the §5.5 voice rubric extension.

---

### Thread 4 — Vision-capable role

**Trigger:** ≥ 30% of citable source-corpus material is non-text
(image + video + multimodal). Below 30%, text-only extraction is
adequate.

**Substrate readiness:** NOT shipped — `substrate/roles/vision_extractor/`
is on the Sprint 30+ punch list (conditional on this verdict). Model
candidates: DeepSeek-VL or Gemini-Vision via the existing tier-measurement
infrastructure.

**Current measurement:**
- Total citable chunks: _[fill in]_
- Non-text citable chunks: _[fill in]_
- Non-text share: _[fill in]_%

**Verdict:** _[GO / DEFER]_

**If DEFER (default):** source corpus is still predominantly text; vision
expansion not load-bearing.

**If GO:** vision_extractor role scaffolds; §5.4 verification rubric
extends for frame-level claims.

---

### Thread 5 — Autoresearch Wedge 3 (config sweeps)

**Trigger:** ≥ 500 graded outcomes in cohort per §14.1. Below 500, the
sweep doesn't have enough signal to produce a config delta operator review
will trust.

**Substrate readiness:** NOT shipped — `substrate/autoresearch/wedge3_sweep.py`
is on the Sprint 30+ punch list (conditional on this verdict). Operator-
gated promotion ensures no auto-config-changes ever (per the Loop 3
unlock criteria).

**Current measurement:**
- Graded outcomes in current cohort: _[fill in]_
- Cohort window: _[fill in]_

**Verdict:** _[GO / DEFER]_

**If DEFER (default):** outcomes table still scaling. Re-evaluate when
Sprint 23-24 + 25+ rev-share is producing graded outcomes at volume.

**If GO:** nightly sweep activates; first proposed config delta filed at
`docs/sprint30_proposed_config_delta_001.md` for operator review.

---

### Thread 6 — Substrate Stage 1 → Stage 2 (DuckLake sharded)

**Trigger:** per-user DuckDB file count approaches OS handle limit
(default macOS ulimit ~ 10,240) OR catalog Postgres becomes contention
point (CPU > 70% sustained or p95 latency > 100ms).

**Substrate readiness:** `substrate/ducklake/migration.py` shipped;
`plan_stage1_to_stage2` declarative-only; `execute_migration_plan` defaults
`dry_run=True` so operator review is mandatory.

**Current measurement:**
- Per-user file count: _[fill in]_
- Catalog Postgres CPU (sustained): _[fill in]_
- Catalog Postgres p95 latency: _[fill in]_

**Verdict:** _[GO / DEFER]_

**If DEFER (default):** Stage 1 still adequate.

**If GO:** operator schedules a maintenance window; migration plan is
generated; dry-run + review precedes any disk movement; rollback path
(reverse migration via NoSharding strategy) documented.

---

## §3 Cross-thread synthesis

Health of the marketplace at review time:
- _[link to /marketplace/snapshot output and the MarketplaceHealth verdict]_

If the marketplace is UNHEALTHY: all GOs are reconsidered. Compounding
on a broken loop is worse than waiting.

If WATCH: the failing axis is documented; threads gated on that axis
stay DEFER until the axis becomes HEALTHY.

If HEALTHY: each thread is evaluated against its own trigger; threads
without cleared triggers stay DEFER per the §1 discipline.

---

## §4 Renewal cadence

This file is re-filed quarterly while Sprint 30+ is active. Each renewal:
1. Updates the measurements in §1 + §2 with current-quarter numbers
2. Re-states every DEFER with the cited measurement (no "we'll get to it" —
   either the trigger condition cleared or it didn't)
3. Adds a new section for any GO threads that have shipped since last review,
   tracking their post-ship health

---

_Template: paired with `docs/sprint-breakdown.html` Sprint 30+ section.
Activation of any thread is binding on this file being current._
