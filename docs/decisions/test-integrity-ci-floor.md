# CI policy — test-integrity floor (three gates informational on shared runners)

**Decision date:** 2026-06-04
**Status:** ✅ Active (each carries a reconsider-if below)
**Owner:** operator + Antiek × Beck Test-Integrity spec (`~/specs/antiek-beck-test-integrity/`)

Three test-integrity checks from the Beck hardening spec (SPR-02 fake-gate
detector, SPR-03 desiderata lint, SPR-05 mock-budget gate) are wired in
`.github/workflows/test_integrity.yml` as **informational** — they still run,
print their full `path:line` findings to the log, and surface a `::warning::`
on a nonzero tool exit, but **do not fail the job** (every step ends `exit 0`).
The product's real gates stay **hard-blocking and green**: the full `pytest`
suite, the substrate-floor ruff/mypy/no-raise/bypass floor, the operator-side
inline-rubric latency lock, `tsc`, and the Cloudflare Pages build.

This is a deliberate, transparent call (not a silenced failure): nothing here
hides a product defect, and each gate remains visible so a real regression would
still surface. A gate that reds on an unsettled grandfathered backlog (survivors,
lint findings, freshly minted mock-ratio locks) trains the team to ignore CI —
worse than a loud warning. The steelman of blocking-from-day-1: "a warning-only
gate gets ignored, so make it block now and force cleanup." Rejected on the
record: the backlog is measured and owned (see the integration handoff), not a
product-code defect; failing CI on it would block the operator's merge and
corrupt trust in the floor before baselines prove stable.

## 1. Fake-gate detector — `tools.fake_gate_detector --enforce`

**Why informational.** The bounded mutation-lite run on the integrated tree
reports **8 killed / 1 survived** (88.9% kill-rate). The one grandfathered
survivor (`runtime/db_lock.py:89`, stale-lock-file hygiene) is a real fake gate
on a load-bearing line — the detector is doing its job — but clearing it
requires a new product behavior test (out of scope for the spec). `--enforce`
already exits 1 only on a **NEW** survivor not in `mutants/survivors_baseline.json`;
grandfathered entries exit 0 while still printing the full report. Flipping
`--enforce` to blocking before the survivor baseline has been at zero NEW
entries for a sustained period would red every PR on a known, documented
worklist item.

**Beck desideratum:** **behavior-sensitive** — *"if you change the behavior of
the code & a test doesn't break, then the test isn't doing anything."*

**Reconsider-if:** the survivor baseline has had **zero NEW survivors** (no
`--enforce` exit-1 finding) for **≥2 weeks** on `main`, AND the grandfathered
`db_lock.stale_pid_liveness_noop` entry has been removed via a real behavior
test (baseline shrink via `--capture` after kill). Then flip the workflow step
to blocking (remove the trailing `exit 0`; let the tool's exit code stand).

## 2. Test-desiderata lint — `tools.lint.test_desiderata_check --rule all`

**Why informational.** The lint's first dog-food on the real `tests/` tree
reports **2 hard violations** (isolation 1, determinism 1; structure 0) —
`tests/test_retrieval_gate_matrix.py:51` (shared mutable module fixture) and
`tests/test_magic_link_auth.py:93` (unfrozen `time()` in an assertion). These
are real Beck desiderata breaches, but fixing them is product-test work (fixture
refactor, clock freeze), not test-infra work. The lint has no grandfather
baseline yet; every run with the backlog present exits 1. Making it blocking
today would fail every PR touching `tests/` until the worklist is cleared.

**Beck desiderata:** **structure-insensitive** (structure-coupled mock
assertions), **isolated** (order-independent), **deterministic** (frozen
clock/RNG/network).

**Reconsider-if:** the lint finding backlog on `main` is **zero** for **≥2
weeks** (all three rule classes: structure, isolation, determinism). Then flip
the workflow step to blocking (remove the trailing `exit 0`; let exit 1 red the
job on any new `path:line` finding).

## 3. Mock-budget gate — `tools.lint.mock_budget_check enforce`

**Why informational.** The committed baseline (`tools/lints/baselines/mock_budget.json`)
locks **428 modules** at the measured suite-wide mock-ratio **0.4417** — an
honest, high number grandfathered from SPR-01's census, not capped at a
flattering target. `--enforce` exits 0 on the current tree (no upward
regression) and exits 1 only when a module's mock-ratio **increases** vs its
lock. The baseline was just minted; it needs time to prove stable on shared
runners and across parallel operator merges before a blocking flip. Silently
bumping the baseline to green-wash a regression is forbidden; re-mint is
operator-only via `capture` with a documented reason.

**Beck desideratum:** **predictive** — a mock-heavy suite can pass without
predicting production works; the gate prevents the ratio from **worsening**
module-by-module.

**Reconsider-if:** the baseline has been **stable** (no operator re-capture, no
`--enforce` exit-1 regression on `main`) for **≥2 weeks**, AND the operator has
run `stale` at least once and reviewed the tightening candidates. Then flip the
workflow step to blocking (remove the trailing `exit 0`; let exit 1 red on
upward mock-ratio moves only — improvements still pass).

## Source spec + tool map

| Sprint | Tool | Baseline / ledger |
|--------|------|-------------------|
| SPR-01 | `tools/test_census.py` | `tools/test_census_baseline.json` (shared input) |
| SPR-02 | `tools/fake_gate_detector.py` + `mutants/` | `mutants/survivors_baseline.json` |
| SPR-03 | `tools/lint/test_desiderata_check.py` | (no baseline — full backlog visible) |
| SPR-04 | `tools/flaky_quarantine.py` + opt-in plugin | `tests/quarantine.toml` (not a per-PR CI step — too heavy; candidate for nightly) |
| SPR-05 | `tools/lint/mock_budget_check.py` | `tools/lints/baselines/mock_budget.json` |

Master spec: `~/specs/antiek-beck-test-integrity/` (Kent Beck Test Desiderata
rubric). Integration handoff:
`~/specs/antiek-beck-test-integrity/handoffs/sprint-06-capstone-ci-floor.md`.

## What stays hard-blocking (unchanged)

- Full `pytest` suite in `.github/workflows/ci.yml` (any test failure reds).
- Substrate floor in `.github/workflows/substrate_floor.yml` (ruff, mypy,
  no_raise, bypass baselines).
- Operator-side inline-rubric latency lock (`benchmarks.rubric_latency
  --check-regression` — informational on CI per `ci-informational-gates.md`,
  authoritative enforcement operator-side per `CLAUDE.md`).
- `tsc` and Cloudflare Pages build gates.
- Existing AST boundary lints (`owner_boundary_check.py`, `serve_guard_check.py`,
  etc.) that already block in `ci.yml`.

This floor **adds** visibility; it does **not** relax any existing gate.