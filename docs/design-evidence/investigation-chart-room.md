# My Research Chart Room — design evidence

## Outcome

The canonical standalone `/my-research` monitor now lives in an authored polar Chart Room. The earlier concept targeting `InvestigationsIndex` was rejected after hostile review proved that component is intentionally retired; `/investigations` continues to redirect to `/my-research`. The embedded research log beneath the root composer remains unframed and keeps the one-door architecture.

## Authority and safety

- Existing `useInvestigationList({ limit: 200 })`, budget concurrency, aggregate cost, lineage reconstruction, status language, suggestions, auth gates, and root launch navigation remain authoritative.
- No composer or POST path was added.
- Encoded workstation and replay links are preserved.
- The frame is a `div`; the application shell retains route-level landmark authority.
- Generated art is empty-alt, assistive-hidden, lazy-loaded, async-decoded, non-draggable, pointer-inert, and semantically empty.
- List failure recovery is fixed copy; raw hook/API reasons do not enter visible HTML.

## Proof surfaces

- Storybook: `ResearchWorkstation / MyResearch / ChartRoom` with Ready, Loading, Empty, Needs Attention, Standalone, Production Raster, and Overflow Stress stories.
- Visual matrix: five deterministic states at 768, 1024, and 1280 pixels (15 baselines).
- Production proof: `docs/design-evidence/renders/investigation-chart-room-production-1280.webp`.
- Asset provenance: `apps/reading/src/brand/werner/investigations/README.md`.

## Verification

- Focused MyResearch Vitest/RTL: 25 tests passed.
- TypeScript project check: passed with zero errors.
- Token lint, type-scale lint, token parity, and explicit CSS-variable audit: passed; zero undefined variables.
- Storybook production build: passed; all seven Chart Room stories compiled.
- axe-core: 0 violations across all seven Chart Room stories.
- Overflow proof at a 720px viewport: `clientHeight=720`, `scrollHeight=2204`, maximum reached `scrollTop=1484`.
- Production build and bundle budget: passed with 104.04 KB main-bundle and 8.65 KB lemon-chunk gzip headroom.
- Hardenx 1.4.0 strict: LOW, 0 real findings, 14 advisory; corpus certification unavailable, so the gate is advisory by contract.
- Heterogeneous Codex review: initial P1 fixed-height scroll finding repaired; final review reported no actionable correctness regressions.
