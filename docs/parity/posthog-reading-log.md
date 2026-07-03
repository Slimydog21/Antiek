# PostHog reading log — SPR-03 PostHog parity harness

**Sprint:** ALC SPR-03 (Antiek Living Caliber, PostHog parity harness)
**Read date:** 2026-06-13
**Reader pattern:** fan-out-and-synthesize — four dimension readers (visual crispness, motion & life, product character, evidence-backed craft) each read disjoint PostHog terrain at the pinned SHA; this log is the synthesis.

---

## Pinned source — the citeable artifact

- **Repository:** `github.com/PostHog/posthog` (PostHog/posthog)
- **Pinned commit SHA:** `9c06e96956f68b6cd67e39e30df8ff736e1fcaad`
- **HEAD subject at pin:** `feat(workflows): block deleting integrations used by active workflows (#63015)`
- **Clone form:** shallow / blob-limited sparse clone at `/tmp/posthog-pin`, scoped to `frontend/src/lib/lemon-ui`, `frontend/src/styles`, `common/storybook`, and `frontend/__snapshots__`. **Every** `path@SHA` citation in `posthog-craft-rubric.md` is verified against THIS tree with `git -C /tmp/posthog-pin cat-file -e <SHA>:<path>` and line-resolved with `git -C /tmp/posthog-pin show <SHA>:<path>`.

### SHA normalization decision (defensibility)

Two dimension readers (visual crispness, motion & life) initially recorded citations against ancestor SHA `d966425dc37d3bd8cf6c9202f1a0b5538c2551d2`; the other two (product character, evidence-backed craft) recorded against `9c06e96…`. During synthesis **every** cited path and line number from the `d966425` reads was re-resolved against the canonical pin `9c06e96…` and confirmed to hold (`frontend/src/styles/base.scss` is byte-identical at the cited token lines; `LemonInput.scss`, `LemonBanner.scss`, `LemonButton.scss`, `LemonModal.scss`, `LemonDrawer.scss`, `Popover.scss`, `Spinner.scss` all resolve at the cited lines). **The rubric pins one SHA only: `9c06e96956f68b6cd67e39e30df8ff736e1fcaad`.** `d966425` appears nowhere in the rubric. This guards against the monorepo-drift hazard the spec warns about (§ milestone 4 diligence).

---

## License boundary (MIT-core only)

Root `LICENSE@9c06e96` (verbatim, head):

> Copyright (c) 2020-2025 PostHog Inc.
> Portions of this software are licensed as follows:
> * All content that resides under the "ee/" directory of this repository, if that directory exists, is licensed under the license defined in "ee/LICENSE".
> * … Content outside of the above mentioned directories or restrictions above is available under the "MIT Expat" license …

**Every path read for this harness is outside `ee/` and outside any enterprise directory — i.e. MIT-core (MIT Expat).** No `ee/` path, no enterprise-licensed directory, was read or cited. Each cited path was checked: `frontend/src/styles/base.scss`, `frontend/src/lib/lemon-ui/**`, `common/storybook/.storybook/**` — none match `^ee/` or `.*/ee/` or `enterprise`. There is no non-MIT directory to flag-and-exclude in this read because none was touched.

---

## Zero PostHog code copied into Antiek

**Zero PostHog code copied into Antiek.** The rubric anchors describe *qualities* and *counts* (token discipline, border state-pairs, `:focus-visible` rings, choreographed enter/exit, per-component reduced-motion, named-story state coverage, image-snapshot regression, role-based behavior tests) — never component source, never CSS, never microcopy, never identity. The brand firewall in `posthog-craft-rubric.md` makes this mechanical and enumerates the prohibited transfers.

---

## Paths read, by dimension (≥3 each, 14 total)

### Dimension 1 — Visual crispness (token discipline, focus rings, state-pair borders)

| # | Path @ `9c06e96` | What it evidences |
|---|------------------|-------------------|
| 1 | `frontend/src/styles/base.scss` (`:579-585` radius+opacity scale; `:753` `--modal-transition-time`; `:1138-1142` global `:focus-visible` accent ring; `:1156-1177` `.input-like` tokenized ring) | Source of truth: 5-level `--radius*` scale, `--opacity-disabled:0.65`, 541 `--color-*` tokens, designed keyboard focus ring keyed on `:focus-visible` (not bare `:focus`). |
| 2 | `frontend/src/lib/lemon-ui/LemonInput/LemonInput.scss` (`:18-19` border-primary + radius via `var()`; `:26-27` focused → border-**secondary** state pair; `:50` `opacity:var(--opacity-disabled)`) | Per-control border STATE PAIR (primary→secondary on focus) and disabled as a single sourced opacity token — the level-3 refinement. |
| 3 | `frontend/src/lib/lemon-ui/LemonBanner/LemonBanner.scss` (`:11-12` border-primary + `border-radius:var(--radius)`; `:50` nested radius) | Radius + border consumed via tokens, not literals, on a non-control surface. |
| 4 | `frontend/src/lib/lemon-ui/LemonButton/LemonButton.scss` (`:18,53` `--lemon-button-radius:var(--radius)`; `:84,289` consumed; `:139` `opacity:var(--opacity-disabled)`) | Local radius token derived from the global scale; disabled opacity token reused. |

### Dimension 2 — Motion & life (timing tokens, choreographed enter/exit, reduced-motion, GPU-cheap)

| # | Path @ `9c06e96` | What it evidences |
|---|------------------|-------------------|
| 5 | `frontend/src/lib/lemon-ui/LemonModal/LemonModal.scss` (`:8-10` tokenized overlay transition; `:48-69` paired opacity+transform `scale(0.85→1)` on `ReactModal__Content--after-open`) | Overlay lifecycle choreography (fade+scale) driven by the shared `--modal-transition-time` token. |
| 6 | `frontend/src/lib/lemon-ui/LemonDrawer/LemonDrawer.scss` (`:8-10,47-49` token reuse; `:31-33,89-91` per-component `@media (prefers-reduced-motion: reduce)`) | Reduced-motion handled — but PER-COMPONENT (PostHog's actual bar: 2 of 53 lemon-ui components). |
| 7 | `frontend/src/lib/lemon-ui/Popover/Popover.tsx` (`:224` `requestAnimationFrame` enter commit; `:241,249` `setTimeout(delayMs)` exit before unmount; `:389` emits `Popover--enter-active`) | Hand-built enter AND exit — exit transition plays out before portal unmount (timing matched JS↔CSS). |
| 8 | `frontend/src/lib/lemon-ui/Popover/Popover.scss` (`:42,49-50,59-60,69-70,79-80` directional `transform-origin`+`rotateX/Y` per placement; `:91-95` settled state on `--enter-active/--enter-done`) | Directional, contextual motion keyed to placement; settled state declared. |
| 9 | `frontend/src/lib/lemon-ui/Spinner/Spinner.scss` (`:2` `--spinner-speed:1s` local token; `:43` consumed; `:46` derived `calc(... * 1.5)`) | Named, derived motion token — single local source of truth for a load indicator. |

### Dimension 3 — Product character (intentionality of state coverage via Storybook authorship — NOT voice/brand)

| # | Path @ `9c06e96` | What it evidences |
|---|------------------|-------------------|
| 10 | `frontend/src/lib/lemon-ui/LemonButton/LemonButton.stories.tsx` (23 named exports; `:107` `Sizes`, `:141` `DisabledWithReason`, `:148` `Loading`, `:159` `Active`) | Stateful control authors its NON-DEFAULT states (loading/disabled-reason/active/size-spread) as distinct named stories. |
| 11 | `frontend/src/lib/lemon-ui/LemonBanner/LemonBanner.stories.tsx` (10 named exports; `:53/59/65/71` all type variants Info/Warning/Error/Success; `:86` Closable, `:96` Dismissable, `:107` Narrow, `:116` WarningWithAction) | All variants + dismiss/close/narrow states authored. |
| 12 | `frontend/src/lib/lemon-ui/LemonModal/LemonModal.stories.tsx` (4 named exports; `:16` `_LemonModal`, `:69` `WithoutContent` [authored empty state], `:98` `Inline`, `:123` `WithCustomContent`) | The level-2 floor: ≥2 named stories with ≥1 authored non-default (empty-content) state. |

> **Co-location spread (derived metric, my computation over their tree):** 47 of 53 lemon-ui component dirs carry ≥1 `*.stories.tsx` (~89%) at this pin, via `git ls-files`. Reproducible against the pin; flagged as a derived count, not a published PostHog number.

### Dimension 4 — Evidence-backed craft (enforced, not asserted: visual regression + behavior contracts)

| # | Path @ `9c06e96` | What it evidences |
|---|------------------|-------------------|
| 13 | `common/storybook/.storybook/test-runner.ts` (`:4` `toMatchImageSnapshot` import; `:11` `VIEWPORT_WIDTHS`; `:84` `LOADER_SELECTORS`; `:96` `customSnapshotsDir=frontend/__snapshots__`; `:117` `retryTimes`) | RAIL A: a test-runner walks stories and asserts committed image snapshots, with loader-settle + retry determinism. |
| 14 | `frontend/src/lib/lemon-ui/LemonButton/LemonButton.test.tsx` (`:4,44` `userEvent`; `:14` `it.each`; `:55` `getByRole`; `:60` `disabledReason` click-block test) | RAIL B: role-based behavior contract (real userEvent) proving `disabledReason` blocks click/submit while enabled submits. |
| 15 | `common/storybook/.storybook/preview.tsx` (deterministic decorators `withMockDate`/`withFeatureFlags`/`withTheme`; light/dark `globalTypes`) | The determinism substrate that makes story-DOM assertions stable across runs — the level-2 single-axis-gate evidence and what RAIL A asserts against. |

> **Committed snapshot corpus (materialized):** `frontend/__snapshots__` carries **154** `*.png` files at this pin (paired light/dark per story) — the materialized evidence for RAIL A. The full upstream set is larger than what this blob-limited clone materialized; the rubric cites the *mechanism* + the materialized paired-theme evidence, not a grand total.

---

## Antiek-side machinery confirmed present (diligence — read before writing evidence-craft anchors)

Read in `apps/reading` of this worktree so the rubric *recognizes* craft Antiek already has rather than duplicating it:

- `apps/reading/e2e/feel-experience-matrix.spec.ts` (`:42` F6 asserts no `hedgehog`/`posthog.com` in built shell — the firewall, machine-checked), `feel-focus-ring.spec.ts`, `feel-panels-cascade.spec.ts`, `ams-v2-experience-matrix.spec.ts`, `ams-v2-resilience-matrix.spec.ts`, `glass-reduced-motion.spec.ts` (scene freezes + opaque fallback under emulated reduced-motion).
- `apps/reading/src/design/motion/motion.guard.test.ts` + `motion_guard_baseline.json` — baseline-ratchet test failing on any NEW raw `@keyframes` outside sanctioned homes (a design-system enforcement lemon-ui does NOT have).
- `apps/reading/src/design/tokens.css` / `tokens.ts` (radius scale `:148-150`, shadow scale `:142-145`), `tokens.contrast.test.ts` (automated WCAG-AA over token pairs), `feel-focus.css` (`:9-11` `.feel-focusable:focus-visible`; `:18-19` ring variant), `motion.css` (`:23-28` UNIVERSAL `prefers-reduced-motion` guard), `motion.ts` (named duration/easing tokens).
- `apps/reading/src/components/lemon/` — 11 primitives, 11 `*.stories.tsx`, `lemon.test.tsx`; `LemonButton.stories.tsx` = 4 named exports (vs PostHog's 23). App-wide: 99 `*.stories.tsx`, 87 `*.test.tsx` (live tree, `node_modules`/`.caffenagent` excluded — the unfiltered ~986/828 figures are worktree-inflated and must not be used).

These are pointers for the auditor and rubric, not grades — SPR-03 does not grade (baseline is M5, a later phase).

---

## Reproduce this read

```sh
PIN=/tmp/posthog-pin
SHA=9c06e96956f68b6cd67e39e30df8ff736e1fcaad
git -C "$PIN" rev-parse HEAD                       # -> 9c06e96…
git -C "$PIN" cat-file -e "$SHA:frontend/src/styles/base.scss"   # exit 0
git -C "$PIN" show "$SHA:frontend/src/lib/lemon-ui/LemonButton/LemonButton.stories.tsx" | grep -cE '^export const '  # -> 23
git -C "$PIN" ls-tree -r --name-only "$SHA" -- frontend/__snapshots__ | grep -c '\.png$'  # -> 154
```

The clone is disposable: delete `/tmp/posthog-pin` after the rubric is final; this log + the `path@SHA` citations are sufficient to re-derive every anchor.
