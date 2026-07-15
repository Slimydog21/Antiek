# ThinkingStream field journal — design evidence

Date: 2026-07-15

Branch: `goal/thinking-field-journal`

Exact base: `goal/suggested-research-thread-cards@23ef06de8440fa1179967723b1afa6b1132be49d` / PR #2436

## Verified gap and bounded decision

`ThinkingStream` already told the truth: narration came only from the deduplicated event stream, raw activity remained available, cost was real, Stop appeared only where wired, and failures did not masquerade as work. Its default presentation was still a generic bullet feed.

This cycle changes presentation only. The live surface is now a labelled research field journal with a quiet chronological spine, zero-padded rendered-order observations, explicit non-colour tone labels, a 72ch prose measure, folio-style operational chrome, and a restrained completion rule. On narrow screens the full spine collapses to a left observation rule while indices and tone words remain visible. No event, narration, socket, steering, spend, backend, routing, mascot, or research-claim authority changed.

Raw audit remains one explicit disclosure away. The control exposes `aria-expanded` and `aria-controls`; the existing `TrajectoryView` remains the disclosed content. All new styling uses existing tokens. The stylesheet includes a reduced-motion guard and adds no animation.

## Files

- `ThinkingStream.tsx`: semantic field-journal region/header/list, order markers, tone registers, raw disclosure state, closing folio.
- `ThinkingStream.test.tsx`: existing behavioral contract plus semantic, ordering, tone, disclosure, busy-Stop, completion, and long-copy coverage.
- `ThinkingStream.stories.tsx`: nine deterministic, network-free states including raw audit.
- `thinking-field-journal.css`: authored spine, responsive collapse, legible measure, and reduced-motion behavior.
- Nine committed baselines: in-progress, reconnecting, and completed at 1280/1024/768.

## Verification actually run

- Focused Vitest: `ThinkingStream.test.tsx` + `narrateEvent.test.ts` — **2 files, 39 tests, 0 failed**.
- TypeScript: `npm run typecheck` — **0 errors**.
- Token lint: **0 new hardcoded hex**.
- Type-scale lint: **0 new oversized chrome**.
- Production build + bundle budgets: **green**; index headroom 108.24 KB, lemon headroom 8.65 KB.
- Storybook production build: **green**, 1,016 modules transformed.
- Direct Storybook visual inspection: 1280px and 390px; no horizontal clipping, control loss, or long-copy truncation.
- Direct axe 4.12 scans after critic repair: in-progress **0 violations / 34 passes**; failed-with-reason and failed-without-reason **0 violations / 30 passes each**.
- Hardenx strict scan: **LOW**, 0 real findings; 14 repository-wide dependency-floor advisories and 9 filtered findings.
- Fresh Codex final refuter: **ACCEPT** after independently rerunning the 39 focused tests, TypeScript, token lint, type-scale lint, and staged-diff checks.
- `git diff --check`: **clean**.

## Engine honesty

- Fable 5 planning unavailable: subscription credits exhausted.
- Opus 4.8 fallback produced no result and was terminated without edits.
- Codex GPT-5.6 supplied the read-only implementation contract.
- Grok returned before editing; no delta accepted.
- MiMo produced the initial five-file build; the orchestrator repaired four test-harness defects and one real contrast defect before acceptance.
- A fresh Codex ship critic blocked duplicate disclosure IDs, dishonest `not_found` copy, and false shape differentiation; all three findings were repaired with direct regressions before the final review.

The broad Lost Pixel updater attempted all 783 repository shots even when filtered; both bounded attempts were terminated before baseline update. The nine committed baselines were therefore captured directly from the same built Storybook with Playwright at the configured widths, then inspected rather than accepting an opaque bulk rewrite.
