# PDF-inside-floating-panel · performance budget

**Spec:** `docs/ui_redesign_posthog/sprint_06_wrestle.html` WP-6.6.
**Status:** real Playwright harness landed in this commit
(`apps/reading/scripts/bench_pdf_panel.ts`). Operator-runnable via
`npm run bench:pdf-panel` after `npx playwright install chromium`
(one-shot). Results append below as a history table.

## Acceptance criteria

The PDF surface, rendered inside a workspace floating panel at
**1200 × 900 px** on **M1 baseline**, while the operator scrolls
through a **200-page document**, must hit:

| metric | target |
|--------|--------|
| `fps` p50 | **≥ 45** |
| `fps` p10 | **≥ 30** |
| `pdf.worker` memory growth over 5-second scroll | **≤ 80 MB** |

## Why this matters

pdf.js renders pages into `<canvas>` at a viewport-scale derived from CSS
pixel dimensions. If the panel resizes during a drag, naive re-mounting
triggers re-rasterisation every frame. S6's `usePanelSizeStable` hook
(120 ms debounce) keeps the previous canvas mounted during the gesture
and re-rasterises once after settle. That's the only thing standing
between pdf.js and a frame-storm.

## Runbook (when run)

```bash
cd apps/reading
npm run storybook                          # storybook ready on :6006
tsx scripts/bench_pdf_panel.ts --pdf big.pdf
# results printed and appended below
```

## Results

| date | branch | p50 fps | p10 fps | pass | notes |
|------|--------|---------|---------|------|-------|
| _pending SDET pass_ | _main_ | _–_ | _–_ | _–_ | scaffold-only |

When the first real run lands, prepend the row above and link the
commit hash + the SHA of the PDF used.

## Failure modes worth watching

1. **Resize-storm during drag** — fix: `usePanelSizeStable` (already landed).
2. **Worker memory leak across multiple floating PDFs** — pdf.js worker
   is a singleton; document references release on panel close.
   Verify with two simultaneous PDF panels + 10-minute scroll loop.
3. **Canvas blanks mid-resize** — the previous canvas should remain
   mounted with CSS-scaling until the new one finishes rasterising.
   Visual regression in S12 catches this if it regresses.
