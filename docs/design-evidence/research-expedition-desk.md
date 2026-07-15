# Research Expedition Desk — design evidence

## Outcome

The canonical research entry now reads as a polar expedition desk rather than a generic glass form. A generated ice-and-brass chart supplies atmosphere while every question, estimate, attachment, tier, phase, failure, and action remains accessible live HTML.

## Proof surfaces

- Production render: `renders/research-expedition-desk-production-1280.webp`
- Storybook: `Research / Expedition Desk` with Ready, Attachment Ready, Starting, Cascade, Failure, and Production Raster states.
- Visual matrix: five deterministic HTML fixture states at 768, 1024, and 1280 pixels (15 LostPixel baselines). The production-raster story is deliberately excluded from pixel gating and retained for human inspection.
- Asset provenance: `apps/reading/src/brand/werner/research/expedition/README.md` records generation, conversion, dimensions, and SHA-256.

## Authority and safety

- Existing research hooks remain authoritative; this slice changes presentation and closed-copy boundaries only.
- The frame is a `div`, preserving PanelLayout's sole route-level `main` landmark.
- The generated raster is empty-alt, hidden from assistive technology, non-interactive, and contains no fake controls or semantic text.
- Raw start exceptions, ingest API bodies, and research-event failure reasons never enter rendered HTML.
- Local question validation uses a specific fixed alert; backend failures use a fixed retry surface.

## Verification

- ResearchWorkstation suite: 16 files, 228 tests passed.
- TypeScript, token lint, and type-scale lint: passed.
- Production build and bundle budgets: passed.
- Axe: six whole-surface states, zero violations.
- hardenx 1.4.0 strict: LOW, zero real findings (14 advisory).
