# Werner Ice Fishing Cursor — Operator acceptance

**Spec:** `docs/htmlspec/werner-ice-fishing-cursor/index.html`  
**Branch:** `caffen/SPR-13` (SPR-13–16 combined)  
**PR:** https://github.com/Slimydog21/Antiek/pull/54  
**Date:** 2026-06-02

Sign each row after manual verification on a deployed or local `apps/reading` build with ice mode on (`VITE_WERNER_ICE_FISHING` unset or `1`).

| # | Criterion | Pass | Notes |
|---|-----------|------|-------|
| 1 | System cursor hidden on reading shell; bait worm tracks live pointer with no perceptible delay | ☐ | |
| 2 | Fishing line visible from rod tip on Werner to bait while moving | ☐ | |
| 3 | Werner reels toward **lagged** hook (~0.5s behind), not the live cursor | ☐ | |
| 4 | Perceived handoff lag ≤ ~1s (not multi-second hop roam) | ☐ | |
| 5 | Idle pointer → slow hop roam (not snappy 800ms stroll) | ☐ | |
| 6 | Drag mascot → reel pauses; position follows pointer | ☐ | |
| 7 | `prefers-reduced-motion` → no involuntary follow; mascot still clickable | ☐ | |

**Automated gates (agent):**

```bash
cd apps/reading
npx vitest run src/werner/ src/shell/PenguinMascot
rg '5s-lagged' ../../docs/ --glob '!**/operator-acceptance.md'   # expect 0 matches
```

**Merge:** Approve PR #54 → `main`, then manual deploy per Antiek workflow.