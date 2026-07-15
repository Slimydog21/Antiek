# Research index keyboard tree — 2026-07-15

## Outcome

The Research Index now behaves as a real keyboard tree without changing its existing routes or visual hierarchy. One row is tabbable at a time; Arrow Up/Down, Home/End, Arrow Right/Left, and Enter follow the WAI-ARIA tree interaction model. Parent disclosure remains independently clickable, active ancestry is revealed, and polling preserves a usable focus target.

This is stacked on `goal/research-index-sidebar` at `c0f707833e335199c6fca251b59128677201a085` (PR #2480).

## Scope decision

The cycle began by auditing the research surface rather than assuming that a new activity monitor was missing. `MyResearch` already owns swarm/activity monitoring, and duplicating it would have weakened the workstation. The residual design gap was the Research Index's mouse-only hierarchy, so the cycle stayed inside `InvestigationSidebar`, its story, tests, CSS, and visual baselines.

## Interaction contract

- `tree`, `group`, `treeitem`, `aria-level`, and parent-only `aria-expanded` semantics mirror the rendered hierarchy.
- Roving focus exposes exactly one tree item in the tab order.
- Right expands or enters the first child; Left collapses or returns to the parent.
- Up/Down traverse the visible preorder; Home/End jump to its bounds; Enter activates the existing route link.
- Disclosure controls remain sibling buttons and do not accidentally activate the route.
- Equivalent rerenders preserve deliberate user collapse.
- A newly active route reveals only its ancestor chain, including disappearance/reappearance during polling.
- Collapse and polling removal recover DOM focus to a visible ancestor or fallback.
- The ink focus frame is visually distinct from the sun-colored active-route treatment.

## Verification

- Focused Vitest suite: 60/60 passing across `InvestigationSidebar` and adjacent `MyResearch` coverage.
- TypeScript project check: passing.
- Token lint and type-scale lint: passing.
- Production build and bundle budget: passing; index headroom 108.58 KB and lemon headroom 8.65 KB.
- Storybook production build: passing.
- LostPixel: three new keyboard-focus baselines at 768, 1024, and 1280 px; the existing 21 captured baselines were unchanged when the new story was generated.
- Visual inspection of the 1280 px baseline confirmed a clear focus frame and separate active-route state.
- `git diff --check`: passing.
- Hardenx strict scan: LOW, zero concrete findings; four generic advisories and three filtered findings.

The in-app browser was unavailable in this environment, so this evidence does not claim a fresh interactive browser or direct axe run. The Storybook build includes the repository's axe tooling, while authoritative remote accessibility checks remain part of PR CI.

## Independent review and repairs

A fresh Codex critic first blocked on two lifecycle defects: DOM focus was not restored after polling removed the focused row, and Enter could bubble from disclosure into link activation. Both received regression tests and repairs. A second critic found that an active node removed and restored with the same ancestry could remain hidden behind a collapsed parent; the reveal signature is now cleared while the route is absent, with a polling regression test.

## Engine record

- Fable planning was attempted but unavailable because its credits were exhausted.
- Opus planning and MiMo implementation were attempted but stalled without edits and were terminated.
- Grok Composer was invoked as a workhorse but returned without edits.
- Codex produced the architecture contract and independent critical reviews.
- GLM-CC was invoked with `/ultracode` for criticism but returned HTTP 429.
- The host implemented and verified the bounded seam directly after the workhorses failed to produce a patch.

## Next seam

Monitor the stacked PR gates, then re-audit the research workstation against the existing product specs before selecting another non-duplicative design seam. Preserve the Research Index's new tree contract when adding virtualization, richer node status, or live polling behavior.
