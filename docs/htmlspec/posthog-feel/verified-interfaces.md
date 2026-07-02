# PostHog Feel — verified interfaces ledger

> Anti-fiction paths for `docs/htmlspec/posthog-feel/sprint-feel-s*.html`.  
> UI shell truth also in `docs/ams-v2/verified-interfaces.md` — do not duplicate AMS rows here.

**Baseline:** `origin/main` @ programme start; re-verify on dispute.

## Legend

| Verdict | Meaning |
|---------|---------|
| `VERIFIED` | Path exists on baseline |
| `NEW-to-build` | Created by a Feel sprint; cite with `NEW:` in sprint HTML |

## Load-bearing (pre-existing)

| Concern | Path | Verdict |
|---------|------|---------|
| Panel orchestrator | `apps/reading/src/workspace/PanelLayout.tsx` | VERIFIED |
| Floating panel | `apps/reading/src/workspace/PanelLayoutPanel.tsx` | VERIFIED |
| Panel store | `apps/reading/src/workspace/WorkspaceStore.ts` | VERIFIED |
| Window store | `apps/reading/src/workspace/windowsStore.ts` | VERIFIED |
| Window frame | `apps/reading/src/components/windows/WorkspaceWindow.tsx` | VERIFIED |
| Window layer | `apps/reading/src/components/windows/WindowsLayer.tsx` | VERIFIED |
| Window policy | `apps/reading/src/components/windows/openWindow.ts` | VERIFIED |
| Motion tokens | `apps/reading/src/design/motion.ts` | VERIFIED |
| Shadow tokens | `apps/reading/src/design/tokens.css` | VERIFIED |
| AMS windows e2e | `apps/reading/e2e/windows-default.spec.ts` | VERIFIED |
| Panel Storybook | `apps/reading/src/workspace/WorkspaceDemo.stories.tsx` | VERIFIED |

## NEW-to-build (Feel programme)

| Concern | Path | Sprint |
|---------|------|--------|
| Elevation helper | `NEW: apps/reading/src/design/elevation.ts` | FEEL-S1 |
| Elevation tests | `NEW: apps/reading/src/design/elevation.test.ts` | FEEL-S1 |
| Feel contract doc | `NEW: docs/htmlspec/posthog-feel/FEEL_CONTRACT.md` | FEEL-S1 |
| Panel cascade e2e | `NEW: apps/reading/e2e/feel-panels-cascade.spec.ts` | FEEL-S2 |
| Windows cascade e2e | `apps/reading/e2e/windows-default.spec.ts` + `NEW: apps/reading/e2e/feel-experience-matrix.spec.ts` | FEEL-S3/FEEL-S6 |
| RW exempt e2e | `NEW: apps/reading/e2e/feel-rw-ide-exempt.spec.ts` | FEEL-S4 |
| Focus ring e2e | `NEW: apps/reading/e2e/feel-focus-ring.spec.ts` | FEEL-S4 |
| Feel matrix e2e | `NEW: apps/reading/e2e/feel-experience-matrix.spec.ts` | FEEL-S6 |
| e2e:feel script | `NEW: apps/reading/package.json` script | FEEL-S6 |

## Confirmed absent (do not cite)

| Fictional | Real |
|-----------|------|
| `apps/reading/src/components/FloatingSurface.tsx` | `components/windows/` |
| PostHog `panel-layout` as floating OS | Fixed nav + side panel only (OSS) |
