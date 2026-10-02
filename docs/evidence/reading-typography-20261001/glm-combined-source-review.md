# Verdict

**ACCEPT for the concrete combined source at `b9c4ae35772d006b61f2e70402e2f604d837605a`.** This is source-review acceptance only. It is not visual acceptance, CI acceptance, security acceptance, or production approval.

- **Reviewed SHA:** `b9c4ae35772d006b61f2e70402e2f604d837605a`
- **Exact comparison base:** `0fa478338d4950dd8c0c10890f7c50b0d20454fd`
- **Review mode:** read-only; no edit, checkout, commit, push, merge, deploy, or human contact
- **Worktree:** clean at the reviewed SHA

## Source resolution review

### `ReadingColumn.tsx`

`apps/reading/src/components/reader/ReadingColumn.tsx:171-188` resolves the conflict correctly:

- Retains palette treatment through `reading-page`.
- Retains typography treatment through `reading-prose`.
- Applies validated inline preferences through `readingTypographyStyle(typography)`.
- Preserves attribution markers, trusted-HTML path, markdown rendering, and the forwarded article ref.

The palette rule `.reading-page.prose-antiek` supplies the Softer reading ink, while typography controls only font, size, leading, width, and tracking. The inline maximum width overrides the older prose cap, so the reader’s 52/66/78ch choices remain effective.

### `BookReader`

`apps/reading/src/modes/Reading/index.tsx:999-1019` preserves the palette’s responsive title layout:

- `flex-wrap`
- title area `flex-1 basis-48`
- controls area `ml-auto`
- palette **Aa** `ReadingAppearance`
- conditional typography **Type** `ReadingTypography`
- source-link-only arXiv views still omit **Type**

The accessible names remain distinct: “Reading appearance” and “Reading type”. The visible labels are also distinct: **Aa** and **Type**.

`apps/reading/src/modes/Reading/index.tsx:293-301` still remeasures islands after typography changes and completed font loads, with observer/listener cleanup. Palette Softer changes color variables only and does not alter glyph metrics, so no additional geometry dependency is required for that preference.

The reading body wrapper remains `w-full` at `index.tsx:1067`; the article’s inline `ch` maximum controls prose width without restoring the old fixed outer cap.

### `MasterMdViewer`

`apps/reading/src/modes/ResearchWorkstation/MasterMdViewer.tsx:293-301` resolves the surface correctly:

- Outer `<div>` retains `reading-page`.
- Article retains `reading-prose` and inline typography preferences.
- Fixed article-level `text-ink dark:text-bright` utilities are removed, allowing the main thesis and claim body to inherit Softer reading ink.
- Compact audit/citation labels retain their existing palette utility colors.
- `MasterMdViewer.tsx:283-291` preserves font-loading and typography-driven geometry refresh.

This is the right separation: palette owns reading color; typography owns reading metrics.

### `AppearancePanel`

`apps/reading/src/modes/Settings/AppearancePanel.tsx:30-57` preserves both control families:

- Theme and motion remain in the original settings grid.
- Reading type spans the grid and mounts `ReadingTypographyControls`.
- Page light remains in the palette-owned section and mounts `ReadingLightControl`.

The auto-merge did not overwrite either feature or duplicate a control.

### Reader story

`apps/reading/src/components/reader/ReadingTypography.stories.tsx:10,16-20` now exposes both **Aa** and **Type**. Changing the fixture from `##` to `#` is correct for the story only: the fixture `h1` is followed by `ReadingColumn`’s `h2`, avoiding a skipped heading level. Product markdown semantics in `ReadingColumn.renderBlocks` remain unchanged.

## Independent integrity checks

- **Combined source/context hashes:** all **79/79** entries in `docs/evidence/reading-typography-20261001/combined-source.json` match the current worktree.
- **Palette context comparison:** the palette merge changed 917 paths from `f22046662` to `0fa478338d`. At `b9c4ae357`, 913 of those paths are byte-identical to palette main. The only four changed palette paths are the intentionally resolved consumers:
  - `ReadingColumn.tsx`
  - `Reading/index.tsx`
  - `MasterMdViewer.tsx`
  - `AppearancePanel.tsx`
- **Seven pinned main-context files** were separately confirmed identical to `0fa478338d`:
  - `index.html`
  - `appearance-boot.js`
  - `ReadingAppearance.tsx`
  - `theme.ts`
  - `tokens.css`
  - `useTheme.ts`
  - `index.css`
- **Core typography source:** the preference store, controls, generated font CSS, typography CSS, font manifest, and vendor script are byte-identical to standalone head `5a50d764`.
- **Offline font integrity:** independently rerun:
  `FONT_ASSETS_OK files=52 woff2_bytes=2065532 latin_bytes=604720`.
- **Combined logs:** retained logs report 389/389 files and 3,690/3,690 tests passing, type checking passing, and production build/bundle budgets passing.
- **Conflict hygiene:** no conflict markers remain in the reviewed source.

## Visual placeholder state

I verified the disclosed placeholder state exactly:

- The 12 conflicted existing references are byte-identical to approved palette main `0fa478338d`.
- The 12 unique typography references are byte-identical to standalone head `5a50d764`, not to a combined render.
- Therefore none of these 24 references is an accepted combined baseline.

`docs/evidence/reading-typography-20261001/README.md:179-183` states this honestly and does not claim combined visual approval.

## Remaining merge blockers

The source is acceptable, but merge must wait for all of the following on the eventual published head:

1. **Current exact-head CI** with the live required contexts.
2. **Fresh combined visual artifact and intentional visual review**, followed by a baseline-only repair. That repair must prove all 79 combined source/context hashes remain unchanged and receive a bounded receipt review.
3. **Completion of the announced browser checks**, especially Softer plus font changes and 320px layout with both controls present.
4. **Exact-head security scan**; the standalone scan is not combined proof.
5. **Exact-main production proof:** dependent pytest rollup, served Cloudflare assets, and backend build SHA.
6. **Do not describe the existing informational axe workflow as blocking accessibility proof.** The combined stories are tagged, but the workflow still swallows test-runner failure. A direct blocking axe result or explicit “unproved accessibility” wording remains necessary.

## Limits

- I did not rerun the broad frontend suite, typecheck, build, browser checks, visual tests, security scan, or production checks.
- I reviewed source, hashes, logs, merge composition, and declared baseline provenance.
- I did not download external artifacts or contact any human.
- Native-browser visual judgment, accepted combined screenshots, security, CI, and production remain pending.