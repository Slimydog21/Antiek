# G4 — Lemon UI verdict (overtaken)

**Decision date:** 2026-05-23
**Status:** ✅ Closed
**Original gate:** Operator visual eye-test of `@posthog/lemon-ui` against the four §5.5 criteria (bundle size, TypeScript strict, Tailwind interop, researcher's-notebook aesthetic fit).

## Verdict — REJECTED direct adoption of `@posthog/lemon-ui`

Closed by the 2026-05-21 brand-redesign commit `de52534`. The
operator chose custom Lemon-flavored primitives (`apps/reading/src/
components/lemon/`) with the Werner / Antarctic palette + sun-yellow
outline rather than adopting PostHog's package wholesale.

Rationale captured in `de52534`'s commit message:

> The prior integration_posthog.md §5.3 verdict ("serif notebook
> aesthetic is load-bearing — adopting yellow accent would hurt the
> product") is explicitly reversed; the new yellow is sharper +
> cooler than PostHog's, and the serif feel survives in MasterMdViewer
> prose (Charter) rather than the chrome.

## What shipped instead

10 custom primitives at `apps/reading/src/components/lemon/`:
LemonButton, LemonCard, LemonModal, LemonInput, LemonTextarea,
LemonTag, LemonSelect, LemonDropdown, LemonTable, LemonToast.
Each sun-yellow-outlined per the brand bible
(`docs/ui_redesign_posthog/brand_werner.html`), day/night ready,
strict-TS, Tailwind-native (no CSS-in-JS dep).

The TipTap notebook editor + the Login surface + the PanelLayout
shell all consume these primitives directly. No PostHog component
is imported anywhere in the codebase.

## Why this is closure, not deferral

The G4 gate exists to prevent shipping a notebook surface that
either (a) drags the UX toward SaaS-dashboard aesthetic or (b)
forces a future rip-and-replace when operator taste solidifies.
Both risks are now retired: (a) custom primitives ARE the
aesthetic; (b) the rip-and-replace happened in advance via
de52534 — the rest of the spec has been refactored around the
new brand.

The `docs/sprint_track_reconciliation.md` document already
records that this verdict is binding under the master spec's
new precedence ordering. No further operator action required.
