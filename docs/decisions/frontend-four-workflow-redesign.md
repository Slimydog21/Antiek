# Frontend redesign — unified behind four workflows (Research · Read · Write · Speak)

**Decision date:** 2026-05-25
**Status:** ⏳ Decided + built; PENDING MERGE — on PRs #2 / #3 / #4 / #7 / #8, not yet on `origin/main`. Flip to ✅ Closed with merge SHAs when the stack lands.
**Scope:** UI/frontend only (`apps/reading/`). No substrate / legal / payout change; **no operator gate (G1–G8) and no engineering deferral was affected** by this work.

## Decision

Unify the product's frontend behind the four crystallized workflows — **Research · Read · Write · Speak** — using PostHog's 2025 **content-first** information architecture in Antiek's **Werner skin**. Per master-spec §5.6: *the pattern transfers, the tone does not* — sun-yellow edge, chunky offset shadow, Charter-serif prose stay; no SaaS-startup register, no PostHog palette/voice. Every design decision is justified by function: form follows function until the design is *hard to vary*; decoration is what's left when an element does no work. This builds on the prior custom-Lemon-primitives decision in [`g4-lemon-ui-verdict.md`](./g4-lemon-ui-verdict.md) (no PostHog component is imported).

The four-zone shell: a rail of the four workflows + Search/New/launcher; a content-first project tree of the active workflow's *nouns*; a scene with per-workflow chrome (action bar + in-scene tabs) hosted in the Topbar; a context-aware Max. The ~35 self-registering modes collapse into the four workflows + a shared/operator bucket, reachable via the products launcher + ⌘K.

## Spec

The htmlspec bundle `specs/frontend-design/` (master + 8 sprint pages + a "why the product is displayed this way" functional-design-philosophy section). Peer to the integration capstone `specs/antiek-unified/`. The execution ledger is `specs/frontend-design/.caffenagent/` (these spec dirs are working artifacts; the PRs below are the durable, reviewable record).

## What was built (on PRs — NOT yet on `origin/main`)

| PR | Sprint(s) | What | Key files (per PR — resolve on `main` once that PR merges) |
|---|---|---|---|
| #2 | SPR-02/03/04 | four-workflow IA spine | `apps/reading/src/shell/workflowTaxonomy.ts` (35 modes → 4 + shared, CI-checked) · `activeWorkflow.ts` · reshaped `components/navigation/{NavRail,ProjectTree,ProductsLauncher}.tsx` · `AppShell.tsx` |
| #4 | SPR-01 | design-system + "pattern not tone" token lint | `apps/reading/scripts/lint_tokens.ts` (+ baseline; fails on new hardcoded hex) · `src/design/DESIGN_LANGUAGE.md` · `tokens.css` drift reconcile |
| #3 | SPR-06 | ⌘K workflow facet + context-aware Max | `components/CommandPalette.tsx` · `components/AISidecar.tsx` |
| #7 | SPR-05 | Topbar-hosted scene chrome (route-linked tabs) + honest stubs | `components/navigation/Topbar.tsx` · `src/shell/{sceneRegistry,WorkflowStub}.ts(x)` |
| #8 | SPR-08 | conformance gate | `.storybook/test-runner.ts` (real axe postVisit hook — the CI step was theater) · `e2e/four-workflow-ia.spec.ts` · `src/shell/CONFORMANCE.md` |

**SPR-07** (per-workflow scenes) was **absorbed** by SPR-05's scene registry; its residual (entity-id-carrying cross-workflow routing) defers to when the product specs build real scene bodies — recorded, not manufactured.

Verification on each branch: `tsc -b --noEmit` clean · `vitest run` green (123 on the SPR-05/08 branches) · `vite build` green · bundle within budget · e2e 17 passed.

## Why this is the right call

The flywheel only reads as one product if the surface does: four workflows on the rail + a content tree where one research insight is the *same node* when it becomes a Write block and a Read paragraph is the visual proof of "one substrate." A flat 35-mode list would present 35 unrelated screens and hide the flywheel. PostHog's IA is the reference because its forms are functionally determined (hard to vary), not stylistic; the Werner skin is itself functional — it reports what kind of work this is.

## Open operator follow-ups (not code)

1. **Merge the PR stack** to `main` (deploys the four-workflow IA to `antiek.ai`; the merge is operator-gated). Suggested order: #2 + #4 (independent) first, then #3 / #7 retarget to main, then #8.
2. **lost-pixel baseline re-mint in CI** (SPR-08 finding) — macOS≠ubuntu Chromium font-AA diffs exceed the 0.004 threshold, and the prior Topbar baselines were minted against a now-fixed error-screen render. Baselines were left **byte-untouched**; the gate stays a visible CI red until re-minted in the CI environment. A CI step, not a code change.
3. The `/redesign.html` static **mock** (commit `94aba7a`) is live on `main` from an earlier mistaken push; **PR #2 removes it**.

## Why this is recorded pre-merge

Memento normally records closures with merge SHAs. This is recorded now — folded into PR #2 so it lands atomically with the IA — because `docs/` otherwise has no pointer to this initiative (the execution ledger lives under `specs/`). On merge, flip Status to ✅ Closed and add the merge SHAs.
