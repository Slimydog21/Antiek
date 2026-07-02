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

## 4. prod_parity — scheduled prod-drift probe (STAYS informational — documented, not a swallow)

**Why informational, and why that is correct.** `prod_parity.yml` runs
`tools/prod_parity/check.py` against live `api.antiek.ai/health` on a schedule
with `continue-on-error: true` + a `::warning::`, so the scheduled probe cannot
red a run. That is deliberate: the **real blocking parity enforcement is at
deploy time** in `infrastructure/ansible/playbooks/deploy.yml`, which sets the
`antiek_build_sha` fact from the just-pulled SHA and fails the play on a missing
build / unregistered providers / bad health (the prod-parity check asserts
against that SHA). A *scheduled* probe of live prod must NOT hard-block CI: a
normal merge→deploy lag or a transient prod blip would red the board on
something no PR changed. So the split is: **block at deploy (Ansible),** **inform
on schedule (this probe).** AGH SPR-04 verified the cited Ansible surface exists
and is genuinely blocking, and added this entry so the register is complete —
the workflow's inline rationale was correct but this decision doc had not
recorded it.

**Reconsider-if:** a dedicated post-deploy GitHub job (not a schedule) is added
that asserts parity immediately after a deploy — that job should be blocking;
this scheduled probe stays informational.
