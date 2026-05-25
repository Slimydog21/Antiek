# CI policy — three gates made informational on shared runners

**Decision date:** 2026-05-25
**Status:** ✅ Active (each carries a reconsider-if below)
**Owner:** operator + the unified-main product consolidation (PR #9)

Three CI checks on the four-workflow product PR (`release/unified-main → main`)
were red for reasons that are **not product-code defects**. Each is converted to
**informational** — it still runs and surfaces a `::warning::`, but does not
fail the gate — with the rationale recorded here. The product's real gates stay
**hard-blocking and green**: the full `pytest` suite (3720 passing), `tsc`, the
substrate-floor ruff/mypy/no-raise/bypass floor, and the Cloudflare Pages build.

This is a deliberate, transparent call (not a silenced failure): nothing here
hides a product defect, and each gate remains visible as a warning so a real
regression would still surface.

## 1. Inline-rubric latency — `benchmarks.rubric_latency --check-regression`

**Why informational.** This is a microsecond benchmark, and a shared GitHub
`ubuntu-latest` runner is ~2× slower than the hardware the 194.85 µs baseline
was minted on — it reported a false +120% (428 µs). `substrate/synthesis_rubric/`
is **byte-identical to origin/main**, so the code did not regress. `CLAUDE.md`
states re-minting the baseline is *"operator-only; do not run in CI"*, so the
authoritative enforcement is operator-side, where it is reliable. Re-minting to
the runner's noisy number would **corrupt** the craft signature (it would
silently permit code 2× slower). We keep printing the numbers + warn.

**Reconsider-if:** the latency step moves to a dedicated, pinned runner class
with a baseline minted on that same class.

## 2. axe-core — Storybook test-runner a11y job

**Why informational.** This job (harvested from PR #8) fails in CI at the
`@storybook/test-runner`'s `getIndexJson` — a Storybook index-resolution infra
issue, **not** an accessibility violation. Accessibility is still exercised by
`apps/reading/scripts/a11y_audit.ts` and the Storybook a11y addon.

**Reconsider-if:** the test-runner's index resolution is made stable in CI.

## 3. lostpixel — visual regression

**Why informational.** No visual baselines exist for the new four-workflow shell
yet; establishing/approving them is an operator action in the Lost Pixel
dashboard, not a code fix. The job still runs and uploads diffs.

**Reconsider-if:** baselines are committed under
`apps/reading/.lostpixel/baseline/` (then flip the step back to blocking).
