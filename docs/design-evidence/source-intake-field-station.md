# Source Intake Field Station — design evidence

## Outcome

The Sources door now reads as an authored polar intake station rather than a generic administrative form. The environment communicates collection and filing while every operational and semantic surface remains accessible live HTML.

## Proof surfaces

- Storybook: `Sources / Source Intake Field Station` with Idle, Detected Input, Receiving, Filed, Mixed Result, and Production Raster states.
- Visual matrix: five deterministic fixture states at 768, 1024, and 1280 pixels. The production raster is retained for human inspection rather than pixel gating.
- Asset provenance: `apps/reading/src/brand/werner/sources/README.md`.

## Authority and safety

- Existing detection, request shape, serial sequencing, and result/count rendering remain authoritative.
- The frame is a `div`; PanelLayout keeps the route-level `main` landmark.
- Generated art is empty-alt, assistive-hidden, non-interactive, and semantically empty.
- Thrown exceptions and adapter error messages are replaced with one fixed recovery sentence at the UI boundary.
- Curated adapter skip reasons remain visible because they explain an intentional non-ingest outcome rather than an exception.

## Verification

- Sources behavior suite: 4 tests passed.
- TypeScript, token lint, type-scale lint, production build, and bundle budgets: passed.
- Axe: six whole-surface states, zero violations.
- hardenx 1.4.0 strict: LOW, zero real findings (14 advisory).
- MiMo hostile review found one scope regression; curated skip detail was restored. GLM-CC returned HTTP 429 and Codex review was stopped after an over-broad inspection without a concrete finding; those engine gaps are recorded rather than presented as green verdicts.
