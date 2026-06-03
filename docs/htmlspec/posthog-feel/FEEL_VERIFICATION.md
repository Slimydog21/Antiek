# PostHog Feel — verification report (FEEL-S6)

**Programme:** `docs/htmlspec/posthog-feel/`  
**Repo:** `apps/reading` on `main`  
**Date:** 2026-06-03

## Operator sign-off question

When three floating panels and three glass windows are open, can you read stack depth at a glance without clicking? If no, reopen FEEL-S2/S3 — not this document.

## Matrix

| ID | Criterion | Proof |
|----|-----------|-------|
| F1 | `elevation.ts` unit-tested | `npm run test -- elevation` |
| F2 | Panel cascade + z-shadow | `e2e/feel-panels-cascade.spec.ts` (Storybook harness) |
| F3 | Glass windows cascade | `e2e/windows-default.spec.ts` + `e2e/feel-experience-matrix.spec.ts` |
| F4 | RW IDE exempt | `ResearchWorkstation.feel.test.tsx` + `e2e/feel-rw-ide-exempt.spec.ts` |
| F5 | Focus rings | `feel-focus.test.ts` + `e2e/feel-focus-ring.spec.ts` |
| F6 | No PostHog mascot clone | `feel-experience-matrix` grep guard |
| F7 | AMS non-regression | `npm run e2e:ams` (37 passed, 1 operator-only skip) |
| F8 | Spec refs | `tsx tools/specs/verify_spec_refs.ts docs/htmlspec/posthog-feel/sprint-feel-s*.html` |

## Not proven by automation

- Safari / Firefox manual pass
- VoiceOver focus order on dense RW IDE
- “Daily driver” subjective stack legibility (operator eyes)

## Honest scope note

PostHog MIT `panel-layout/` is a **fixed** shell, not a floating OS. This programme shipped **interaction physics** (elevation, cascade, hover-lift, focus) on Antiek’s dual stores — not PostHog nav IA or mascot assets.