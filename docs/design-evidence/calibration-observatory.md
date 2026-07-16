# Calibration Observatory — design evidence

## Scope and authority

The canonical `/outcomes` index remains a read-only record of existing operator judgments. This change does not add outcome semantics, charts, scores, grading controls, API fields, routes, or policy. Blank and filtered queries retain their exact ordering, and rows retain encoded synthesis navigation.

## Authored environment

The production frame uses `calibration_observatory_environment_v1.webp`, generated with ChatGPT Image and documented beside the asset. It is empty-alt, aria-hidden, non-draggable, and pointer-inert. It contains no text, controls, grades, verdict marks, facts, or mascot. Story fixtures replace it with a token-only gradient so visual baselines are deterministic.

## State and viewport proof

Eight stories cover loading, empty, populated, filtered, private-safe failure, long identifiers, a shell-constrained long record, and the production raster. Each has a baseline at 768, 1024, and 1280 pixels (24 images total). At 1280 × 900, every story measured `clientWidth === scrollWidth`. The constrained proof measured `clientHeight: 320`, `scrollHeight: 1659`, and `overflow: auto`; its final row was programmatically scrolled into view and remained visible.

The reviewed production render is in `renders/calibration-observatory-production-1280.webp`.

## Accessibility and behavior proof

- Axe-core: 0 violations across all eight stories in forced light and forced dark schemes; 0 serious or critical.
- Focus-visible treatment is explicit for the observer input and retry action.
- The AppShell retains the sole route-level `main`; the Outcomes surface renders no nested main.
- Thirteen focused tests cover exact blank and trimmed/encoded queries, complete row facts (including long observer identities), focusable encoded navigation, stale-response suppression, empty explanation, rejected and non-OK privacy, retry, decorative art, landmark ownership, and the constrained shell boundary.

## Build proof

- TypeScript, token lint, type-scale lint, and token parity: green.
- Storybook and production build: green.
- Bundle budget: main 579.79 KB gzip against 683.59 KB (103.81 KB headroom); Lemon chunk 49.95 KB against 58.59 KB (8.65 KB headroom).
- Generated production asset: 113.62 KB WebP, 1536 × 1024.
