# Recursive Notebook Conservatory — design evidence

## Outcome

The canonical Notebooks index becomes a cultivated entry to Antiek's working-note substrate while list, create, filter, and notebook-navigation authority remain unchanged. The generated conservatory plate supplies atmosphere; every user fact and action remains live HTML.

## Proof surfaces

- Storybook: `Notebooks / Recursive Notebook Conservatory` with Surveying, Empty Beds, Ready, Filtered, Planting, Needs Attention, and Production Raster stories.
- Visual matrix: six deterministic fixture states at 768, 1024, and 1280 pixels; production raster retained for human inspection.
- Asset provenance: `apps/reading/src/brand/werner/notebooks/README.md`.

## Authority and safety

- GET and POST endpoint authority, trimmed payloads, content-class semantics, LemonTable rows, and encoded `/notebook/:notebookId` navigation remain exact.
- The frame is a `div`; PanelLayout retains the route-level `main` landmark.
- Generated art is empty-alt, assistive-hidden, non-interactive, and semantically empty.
- Boundary failures use fixed recovery copy and never expose raw HTTP or exception details.

## Verification

- Focused behavior suite: 6/6 passing, including exact list/create authority, trimmed payloads, content-class filtering, encoded navigation, and private GET/POST failures.
- Accessibility: 0 axe violations across all seven lifecycle stories at 1280px.
- Responsive visual proof: 18 deterministic baselines across 768px, 1024px, and 1280px.
- Production and component builds: green; bundle budget retains 104.18 KB of primary-chunk headroom.
- Design-system gates: token lint and type-scale lint green.
