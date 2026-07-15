# Research index sidebar cycle — 2026-07-15

## Anchor and scope

- Stacked base: `85f9a9939c991977a2b3eb0944a927b53eef97dd` (`goal/thinking-field-journal`, PR #2456).
- Seam: the existing Research Workstation investigation sidebar.
- Invariants: canonical investigation hooks and routes remain authoritative; the view does not invent status, cost, or timestamps; lineage remains semantic and operable with ordinary links and buttons.

## Authored result

- Reframed the sidebar as a compact **Research index** with visible lineage rails, literal statuses, exact four-decimal costs, deterministic age formatting, route-current emphasis, and narrow-width behavior.
- Added honest loading, empty, terminal-error/retry, and stale-cache states.
- Added semantic navigation/list structure, link-level `aria-current`, stable disclosure targets, 44px controls, and reduced-motion protection.
- Extracted `ResearchIndexView` as a deterministic fixture seam while leaving production data and lineage in `useInvestigationList()` and `useInvestigationTree()`.

## Adversarial review and repairs

Two independent read-only Codex reviews blocked earlier drafts. Their findings were repaired before publication:

1. Removed a fictional refresh-busy state and made lineage indentation structural rather than overlapping.
2. Removed a nondeterministic dark fixture, made the active-child fixture use a real route, stopped inventing in-progress/zero values for missing summaries, removed bespoke pulsing motion, and trimmed decorative implementation commentary.

## Proof

- Focused and adjacent tests: 48/48 passing (`InvestigationSidebar.test.tsx` and `MyResearch.test.tsx`).
- TypeScript: `npm run typecheck` passing.
- Design-token lint: passing; no new hardcoded hex values.
- Type-scale lint: passing; no new oversized chrome type.
- Production build and bundle budgets: 2,476 modules; index headroom 108.59 KB; lemon headroom 8.65 KB.
- Diff hygiene: `git diff --check` passing.
- Visual regression: 21 native LostPixel baselines, covering seven literal stories at 768, 1024, and 1280 px. A temporary kind-only filter was used to bound capture, then restored; all 438 prior baselines were preserved.
- Direct raster inspection: full-lineage 1280, narrow 768, and route-active-child 1280 renders inspected. The 320px authored rail stays visually stable, lineage advances at each generation, truncation remains legible, and the active route treatment is distinct without changing layout.
- Security: strict hardenx scan of `apps/reading` reported LOW, with zero real findings, four framework-generic advisories, and three filtered findings.

## Engine and environment honesty

- Codex GPT-5.6 supplied the architecture contract and adversarial reviews.
- MiMo V2.5 Pro produced the initial implementation draft.
- Fable could not run because credits were exhausted.
- Opus produced no output and was terminated after hanging.
- GLM-CC was invoked with `/ultracode` and returned HTTP 429.
- The in-app browser exposed no controllable browser surface, so no interactive browser or direct axe pass is claimed. Native Storybook/LostPixel capture and local raster inspection provide the visual proof for this cycle; remote CI remains the accessibility authority at publication time.

## Next recursive seam

Connect the authored index to a workstation-wide research activity model: live child-run progress, grouped swarm sessions, keyboard traversal, and a deliberate collapsed-rail behavior, while preserving the canonical route/data boundary established here.
