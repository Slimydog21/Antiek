# Verdict

**ACCEPT the pinned final source and authentic combined-baseline receipt at `250cf14f722edfbfd189155177d4d601c8555476`.** This is not merge or deployment approval: exact-current-head CI, enforceable accessibility confirmation, current visual validation of the post-artifact contrast delta, required production contexts, and direct production proof remain gating.

- **Reviewed SHA:** `250cf14f722edfbfd189155177d4d601c8555476`
- **Comparison base:** `0fa478338d4950dd8c0c10890f7c50b0d20454fd`
- **Previously accepted source:** `b9c4ae35772d006b61f2e70402e2f604d837605a`
- **Worktree:** clean at `250cf14f722edfbfd189155177d4d601c8555476`
- **Review mode:** read-only; no edit, checkout, commit, push, merge, deploy, or human contact

## Bounded source delta

The only production-source change from accepted `b9c4ae357` is `apps/reading/src/modes/ResearchWorkstation/MasterMdViewer.tsx`.

`MasterMdViewer.tsx:846-853` changes the high and moderate confidence foregrounds to `text-1` while retaining `bg-success/15` and `bg-sun/20`. `MasterMdViewer.tsx:865-872` makes the same correction for `proceed`, `pass`, and `conditional` recommendation badges. Low-confidence and unknown states remain unchanged.

This is a focused repair for the real Softer-light contrast failure:

- old foreground: `#237242`
- composited ground: `#d0dbc2`
- measured contrast: 4.1:1 at 11px
- axe severity: Serious

Using theme `text-1` preserves the semantic tinted fills while switching label ink to the light/dark theme foreground. The supplied native scans report zero violations after the repair in settled Softer light and dark manuscripts. The transient initial dark sample is disclosed rather than hidden.

No storage, API, font, license, manifest, geometry, rights, or appearance-boot source changed from `b9c4ae357`.

## Source/context integrity

- `docs/evidence/reading-typography-20261001/final-source.json` contains **79 pins**.
- All **79/79** hashes match the current worktree.
- Compared with the accepted combined-source pins, the path set is identical and exactly one hash changes: `MasterMdViewer.tsx`.
- The seven palette/theme/boot context files remain unchanged from actual main.
- Offline font integrity independently passes:
  `FONT_ASSETS_OK files=52 woff2_bytes=2065532 latin_bytes=604720`.
- Focused logs record 44/44 tests in three files, type checking, build, and bundle budgets passing.
- The broad 389-file/3,690-test result belongs to `b9c4ae357`; it is useful context but must not be represented as current-head CI for `250cf14f7`.

## Combined baseline receipt

`docs/evidence/reading-typography-20261001/combined-baselines.json` records:

- source artifact head: `b9c4ae35772d006b61f2e70402e2f604d837605a`
- run: `36846004630`
- job: `110316179763`
- artifact: `11153741693`
- ZIP SHA-256: `7c18a765f0434062272e04ad14df1c78aa4a4f0c0f17bd4944420a3d2db493fe`
- decoded inventory: 828 PNGs
- above-threshold differences: 30
- unchanged references: 798
- threshold: `0.004`

I independently verified:

- Current and before baseline inventories both contain exactly 828 references.
- The receipt lists exactly 30 unique accepted names.
- All 30 `before_sha256` values match the `b9c4ae357` blobs.
- All 30 `accepted_sha256` values match the `250cf14f7` blobs.
- Exactly 30 PNGs changed from `b9c4ae357` to `250cf14f7`.
- The remaining 798 references are byte-identical between those heads.
- Exactly those same 30 references changed from actual main `0fa478338d` to `250cf14f7`.
- `lostpixel.config.ts` and `.github/workflows/visualtest.yml` are byte-identical to actual main; threshold and workflow behavior were not weakened.

The six references beyond the previously expected 24 are the three-width `ReadingColumn--empty-body` and `ReadingColumn--gated-preview` sets. Their inclusion is coherent: those surfaces now render against the selected centered measure and warm reading ground. The source retains the existing rights/gating distinction; no source gate or attribution behavior changed.

The receipt explicitly says the authenticated artifact predates the five badge-foreground corrections and that no image was synthesized to represent the later source. That limitation is truthful.

I could not independently re-download GitHub’s artifact under the read-only/no-contact constraint; I verified the receipt, artifact identity fields, and every committed before/accepted hash.

## Security and browser evidence

- `final-security.json` summarizes **0 REAL** findings and **18 LOW** advisories.
- The focused final type/build logs pass.
- `combined-browser.json` truthfully limits its observations:
  - native Chrome, not production;
  - Literata 24px and Softer composition observed;
  - 320px has no horizontal overflow and retains 44px targets;
  - font persistence was a new local tab;
  - Storybook resets theme globals and does not run production appearance-boot;
  - native Softer scans pass;
  - CI axe index loading remains informational rather than enforcement;
  - settings/portfolio final scans remain pending.
- All 53 local README links resolve at the pinned head.

## Remaining release blockers

Merge/deploy must still wait for:

1. **Exact-current-head CI on `250cf14f722edfbfd189155177d4d601c8555476`**, including all live required contexts.
2. **Current-head visual validation of the badge foreground delta** against the authentic pre-repair references. Do not edit or synthesize images if the delta exceeds threshold; obtain and review a new authentic artifact.
3. **Enforceable accessibility confirmation**. The native scans are useful bounded evidence, but the existing workflow’s axe job remains informational; settings/portfolio combined-final checks are also still pending.
4. **Required production contexts and dependent pytest rollup**.
5. **Direct production proof**: served Cloudflare assets and backend build SHA matching the published head.
6. **No production-boot claim until appearance persistence is verified in the real application boot path**, not merely Storybook.

No present source or baseline-receipt defect blocks this final pinned revision.