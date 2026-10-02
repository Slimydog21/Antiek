# Verdict

**ACCEPT the pinned final source at `43b78db86ff60e5b327327318d267bc604cbfcd9a0f`** — correction, exact immutable SHA:

**`43b78db86ff60e5b327318d267bc604cbfcd9a0f`**

This is final independent source acceptance only. It is not current-head CI approval, visual approval, full accessibility certification, or production approval.

- **Comparison base:** `0fa478338d4950dd8c0c10890f7c50b0d20454fd`
- **Previously accepted source/receipt head:** `250cf14f722edfbfd189155177d4d601c8555476`
- **Worktree:** clean at the reviewed immutable HEAD
- **Review mode:** read-only; no edit, checkout, commit, push, merge, deploy, or human contact

## Production-source delta

Exactly two production files change from `250cf14f7` to `43b78db8`:

1. `apps/reading/src/components/reader/ReadingTypography.tsx`
2. `apps/reading/src/design/readingTypography.css`

No API, store, font, license, manifest, reader geometry, manuscript geometry, palette theme, appearance boot, or rights-related production source changes.

### Keyboard-focusable preview

`ReadingTypography.tsx:78` correctly changes the scrollable preview to:

- `role="region"`
- `tabIndex={0}`
- `aria-label="Reading font preview"`

This is the appropriate repair for axe’s Serious `scrollable-region-focusable` finding: the overflowing preview is now both programmatically named and directly keyboard-focusable.

`readingTypography.css:62-65` adds:

- `:focus-visible`
- two-pixel `var(--focus)` outline
- two-pixel offset

The focus style uses the existing theme token rather than a hard-coded color. The supplied native observation records a visible `rgb(169, 255, 23) solid 2px` outline in the tested dark Softer context.

### Specimen semantics

`ReadingTypography.tsx:80-82` retains the actual specimen text, including the readable `Il1 · O0 · rn m · é ö ñ · 0123456789` comparison string, while removing the unsupported `aria-label` from the generic paragraph. The enclosing preview remains the named accessible region. This is a semantic improvement and does not remove the specimen itself.

## Integrity verification

- `keyboard-source.json` contains **79 pins**.
- All **79/79** hashes match the current worktree.
- The 79-path set is identical to the accepted `250cf14f7` source snapshot.
- Exactly two hashes differ from `250cf14f7`:
  - `ReadingTypography.tsx`
  - `readingTypography.css`
- The other **77 source/context pins are unchanged**.
- The reviewed HEAD is descended from both actual main `0fa478338d` and prior accepted head `250cf14f7`.
- No conflict markers or source whitespace defects were found.
- Offline font integrity remains unchanged and passes:
  `FONT_ASSETS_OK files=52 woff2_bytes=2065532 latin_bytes=604720`.

## Evidence and logs

The following are tracked at the immutable HEAD:

- `keyboard-browser.json`
- `keyboard-source.json`
- `keyboard-tests.log`
- `keyboard-typecheck.log`
- `keyboard-build-check.log`
- `keyboard-security.json`
- `preview-keyboard.jpg`
- latest README section
- prior independent review records

All **61 local README links resolve** at `43b78db8`.

The retained logs record:

- focused tests: 9/9 passing
- type checking: pass
- production build and bundle budgets: pass
- strict security: **0 REAL**, **18 LOW advisories**

`keyboard-browser.json:14-21` records the concrete repaired behavior:

- `tabIndex: 0`
- content height 294px in a 238px viewport
- PageDown scroll position changed from `0` to `55.5px`
- focus remained on the region
- visible two-pixel focus outline

The final settings scan records zero violations, 29 passes, and one incomplete rule. The portfolio dark scan records zero violations, nine passes, and no incomplete results. The remaining incomplete rule is appropriately limited to the existing decorative Theme/Motion select arrows and is not attributed to the typography repair.

## Composition and visual preservation

The Aa/Type composition is preserved:

- BookReader retains `ReadingAppearance` followed by conditional `ReadingTypography`.
- The reader story retains both entry points.
- Source-link-only arXiv views still omit the Type control.

All 828 Lost Pixel baseline files are byte-identical between `250cf14f7` and `43b78db8`. This is expected because:

- `tabIndex` and ARIA changes do not alter unfocused pixels;
- removing the paragraph’s unsupported ARIA label does not alter pixels;
- the new outline applies only on focus.

Therefore the accepted ordinary unfocused baseline pixels remain preserved. Nevertheless, the authenticated 30-image artifact predates this source repair, so it cannot be substituted for exact-current-head visual CI.

## Non-blocking observation

The focused nine-test run passes, but the existing automated component test does not directly assert the new named region, `tabIndex`, or keyboard scrolling. The direct native browser receipt supplies the immediate proof, and the source change is small and explicit, so this does not block source acceptance. It remains a useful future regression-test addition and must not be described as automated keyboard-scroll coverage.

## Remaining operational gates

Merge and deploy still require, on the exact current published head:

1. **Exact-current-head CI**, including all live required contexts. The successful `250cf14f7` visual/e2e results cannot be substituted.
2. **Exact-current-head visual CI** for the final source. The prior authenticated artifact predates the focus repair.
3. **Required e2e/pytest contexts** where mandated by the live ruleset.
4. **Do not count the existing CI axe job as enforcement**; it remains informational. The native scans are bounded observations, not full assistive-technology certification.
5. **Production appearance-boot and live reader validation.**
6. **Direct production proof**, including served Cloudflare assets and backend build SHA matching the published head.

No present defect in the two-file final source delta blocks acceptance.