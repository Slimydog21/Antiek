# compounding/benchmark/

The **falsifiable compounding benchmark** (AFF SPR-09 — the keystone). Measures
**cost-to-resolve** on a frozen question set across a cold-graph control arm and a
warm-graph arm, and reports a **signed warm−cold delta with a confidence
interval** over n runs. It is allowed — by design — to come back null, zero,
negative, or invalid, and it reports that verbatim.

> **A result that can only ever come back positive is a failed benchmark.**

## What this measures vs `compounding/verification/`

These are different questions and live side by side, cross-referenced, never
merged:

- [`compounding/verification/`](../verification/README.md) measures that skill
  **growth happened** — a diff added content after a Phase-8 merge. Its own
  README is explicit that it does NOT measure whether the growth was *good*, and
  defers outcome measurement as "a separate problem."
- `compounding/benchmark/` (here) is **that separate problem**: did the *outcome
  get cheaper*? Does cost-to-resolve fall as the graph accumulates RELEVANT
  reuse? Size-vs-quality (verification) vs **cost-got-cheaper** (this).

## The keystone finding (read this before trusting any number)

The reuse path IS wired into the host-local runner: `HostLocalRunner.start`
retrieves prior units, assembles a reuse context pack, and emits a
`knowledge.reused` event (`runtime/research_runner/host_local.py`). **But the
deterministic demo loop (`make_demo_loop`) does NOT consume that pack** — it
charges a fixed cost per step regardless of reuse, and makes no provider
`dispatch.call`. **Consequence: the mock run honestly reports a token-cost delta
of 0 — there is no dispatch cost to differ between arms.**

This is the result to hand the operator, not a defect to re-roll: **the
instrument can measure compounding, but compounding is UNPROVEN on the current
real loop** because that loop does not consume the reuse layer. A live
`mock_run=false` run with a reuse-CONSUMING browse loop + provider credentials is
the operator-window measurement that would move the number off 0.

The instrument's *falsifiability* — that the scale responds to a real signal in
either direction — is proven independently of the loop by
`tests/test_falsifiability.py`, which injects synthetic measurements into the
aggregator + validity layer:

- warm > cold → a strictly **positive** delta is reported (never clamped);
- warm < cold → a strictly **negative** delta;
- pure noise → every delta CI straddles 0;
- a non-zero irrelevant-control delta → the run is flagged `validity: invalid`.

## The three arms

| Arm | Graph | Reuse | Role |
|-----|-------|-------|------|
| **cold** | empty | `retrieval_substrate=None` | the baseline |
| **warm** | seeded with the question's ON-TOPIC prior units | live substrate | the arm the flywheel claim is about |
| **irrelevant** | seeded with the SAME COUNT of OFF-TOPIC units | live substrate | the validity control: isolates *relevance* from *graph-presence/noise* |

Each arm acquires an **isolated `PersonalGraphHandle`** (a distinct
`{user_id}.duckdb` via `substrate/multi_user/graph_router.py`), so the
single-writer-per-graph invariant holds and arms cannot contaminate each other.
The warm/irrelevant arms are seeded **only** through the real
deposit→retrieve→reuse surface (`promote_insight` → `BruteForceSubstrate` →
`retrieve_prior_units` → SPR-08 `filter_reusable`) — never by hand-injecting an
answer.

## Metrics (sourced from the shipped accounting, never re-derived)

- **token_cost_usd** (HEADLINE) — Σ `cost_usd` over `dispatch.call` events,
  produced by the single `_compute_cost_usd` at `substrate/dispatch/router.py:228`
  ("One place computes cost. Adapters do not."). **No `tokens × price` math
  lives here** — the no-home-grown-meter grep gate over this package is empty.
- **sources_fetched** — count of `connector.delivered` +
  `evidence.retrieve.delivered` events.
- **wall_ms** — `max(emitted_at) − min(emitted_at)` over the trajectory,
  cross-checked against summed `latency_ms`.
- **novel_insight_yield** — count of `graph.node.inserted` whose id is NOT
  already seeded.
- **redundant_rederivations** — node ids are content-addressed, so a re-emit of
  an already-seeded node yields the same id and no new insert; an emitted insert
  whose id is in the seeded set is the re-derivation signal.

## n, the CI method, and the validity tolerance

The spec **forbids choosing `n` a priori** and forbids the grader self-certifying
the bar (OPERATOR_INPUTS §0.2). So the parameters are **derived from a pilot**,
not asserted, and the **operator ratifies** them before any scored run.

- **Pilot:** `python -m compounding.benchmark.run --pilot` runs 5 runs/cell on
  2–3 representative questions, reports the realized per-metric **coefficient of
  variation (CV)**, and proposes `{n, material_floor, control_tolerance}` via the
  pure `propose_parameters(pilot_cv)`:
  - `n` from a target CI half-width: `n ≈ (z·CV / target)²` (z=1.96, 95%);
  - `material_floor` = `2·CV·|cold_mean|` — strictly OUTSIDE the cold-arm noise
    band;
  - `control_tolerance` = `floor / 2` — TIGHTER than the floor, so the control
    cannot "pass as flat" an effect big enough to count as compounding.
- **CI method:** a **bias-corrected percentile bootstrap**, 95%, 10 000
  resamples, seeded for reproducibility. The bootstrap is the default; a
  Student-t interval is available for the small-n case. The **same seed
  reproduces the same deltas**.
- **Mock-artifact defaults only:** `n=20`, 10k-resample bootstrap. These are the
  *mock* numbers; the **live `n` is operator-ratified** after the pilot.

On the deterministic mock path the headline CV is 0 (no provider cost varies), so
the pilot honestly clamps `n` to its minimum and says so in the derivation — the
operator must not mistake a zero-variance mock for a powered run.

## The 5-state verdict (validity-gate-FIRST)

1. **Validity** (assessed on the irrelevant-vs-cold control FIRST):
   - `invalid` — the control delta CI does not straddle 0 within tolerance, OR a
     single control domain's |delta| exceeds the material floor while others are
     flat → "the instrument measures graph-presence/noise, not relevance";
     **reporting STOPS** and the warm−cold result is withheld.
   - `underpowered` — the control CI straddles 0 but its half-width > tolerance
     (it straddles 0 because it is *noisy*) → widen `n`; do NOT report "valid".
   - `valid` — control straddles 0 AND half-width ≤ tolerance.
2. **Headline** (only if valid; pooled over the high-overlap external+synthesis
   questions; the internal-mechanism probe `Q-HI-I1` is reported **alongside,
   not pooled in**):
   - `valid_compounds` — headline `token_cost_usd` CI_high < 0 AND |delta| ≥
     floor AND `sources_fetched` corroborates AND the **load-bearing
     dose-response** holds (high-overlap saves more than partial, non-overlapping
     CIs);
   - `null` — CI straddles 0 or below the floor (reported verbatim, never
     re-rolled);
   - `negative` — CI_low > 0 (warm MORE expensive; a legitimate falsification —
     the aggregator emits the positive number).

**Dual-cache (§2):** a scored run reports both a `cache-disabled` arm (isolates
reuse-of-reasoning; drives the validity headline) and a
`cache-enabled-arm-isolated` arm (production-realistic saving), never collapsed
into one number. On the mock path the demo loop makes no provider calls, so the
cache mode is recorded as provenance on each `ArmResult` rather than an active
prompt cache.

## Running it

```bash
# the pilot (proposes n / floor / tolerance from observed CV; operator ratifies)
python -m compounding.benchmark.run --pilot

# the mock run → results/spr09_run.json (the Phase-1 path; CI-safe, no creds)
python -m compounding.benchmark.run --n 20 --out compounding/benchmark/results/spr09_run.json
```

The artifact carries, per metric, `delta` / `ci_low` / `ci_high`, plus the
top-level `frozen_sha`, `seed`, `n`, `ci_method`, `validity`, `mock_run`, and
`git_sha`. `git_sha` is the placeholder `PENDING_COMMIT` until the commit that
lands the artifact re-stamps it (the artifact is written *before* the commit
exists).

## Mock vs live

The committed `results/spr09_run.json` is a `mock_run: true` artifact. A **live**
delta needs an **operator window**:

1. a real reuse-**consuming** `BrowseLoop` (the host-local default demo loop is
   reuse-blind — `host_local.py` `make_demo_loop`), so the loop actually does
   *less work* when the reuse pack primes it;
2. provider credentials configured for the host-local `ResearchRunner` (so
   `dispatch.call` events carry real `cost_usd`);
3. operator-ratified `n` / `material_floor` / `control_tolerance` from the pilot
   (decision 0.2);
4. **both §2 cache modes exercised** — the live run invokes a `cache-disabled`
   arm (isolates reuse-of-reasoning; drives the validity headline) AND a
   `cache-enabled-arm-isolated` arm (production-realistic saving), emitting the
   two deltas distinctly, never collapsed into one number. The mock cannot
   exercise this — the demo loop makes no provider calls, so there is no prompt
   cache to populate (the `cache_enabled` flag is provenance only).

Until all four hold, the honest finding stands: **compounding is unproven on the
real loop, and the mock delta is ≈ 0.** The benchmark passed its own test — it
ran honestly and reported a real number — which is the pass criterion, not a
negative delta.
