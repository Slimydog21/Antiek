# CI policy — shared-runner gate decisions and one operational alarm

**Decision date:** 2026-05-25
**Status:** ✅ Active (each carries a reconsider-if below)
**Owner:** operator + the unified-main product consolidation (PR #9)

Sections 1–3 record three CI checks on the four-workflow product PR
(`release/unified-main → main`) that were initially informational because their
failures were not product-code defects. Sections 1–2 remain warning-only. The
§3 reconsideration condition later fired, so lostpixel is now blocking.

Section 4 records a different surface: a schedule/manual-only production alarm.
It is not a PR gate, but its blocking checker failures intentionally make that
operational run red.

This is a deliberate, transparent register, not a blanket permission to silence
failures: each section states its current enforcement and reconsideration rule.

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

## 3. lostpixel — visual regression → NOW BLOCKING (AGH SPR-04, 2026-07-03)

**Was informational** because no visual baselines existed for the new
four-workflow shell. **The reconsider-if has fired:** 381 baseline PNGs are now
committed under `apps/reading/.lostpixel/baseline/`, and `lostpixel.config.ts`
sets `imagePathBaseline: ".lostpixel/baseline"` + `generateOnly: false`, so the
job compares current renders against a real committed baseline. AGH SPR-04
un-swallowed the step (removed the `|| echo ::warning`): its exit code is now
lost-pixel's own, so a real visual regression reds the PR. A legitimate visual
change lands its updated baseline PNGs in the same PR (`npm run
visualtest:update`).

## 4. prod_parity — scheduled prod-drift probe (NOT A PR GATE; FAILS HONESTLY)

**Why it is not a PR gate.** `prod_parity.yml` runs only on a schedule and by
manual dispatch; it has no `pull_request` trigger. It therefore cannot block a
merge based on an external endpoint or ordinary merge→deploy lag. The
**blocking deploy-time enforcement** remains in
`infrastructure/ansible/playbooks/deploy.yml`.

**Why scheduled failures remain failures.** The scheduled/manual workflow is
an operational alarm, not a merge gate. Its exit status must stay truthful:
SHA drift, an empty provider registry, or an unreachable endpoint makes the
run red. Masking those failures with `continue-on-error` or `|| echo` makes the
Actions history report success precisely when operator attention is needed.
The checker still treats flywheel maturity as warning-only by default, per the
separate flywheel decision.

**Reconsider-if:** a dedicated post-deploy GitHub job is added; keep this
scheduled alarm as defense in depth, but avoid duplicating notifications.
