# Evidence Archive Atlas — design evidence

## Outcome

DocumentsIndex now reads as Antiek's polar evidence archive rather than a generic administrative table. The plate supplies atmosphere while all tier counts, filters, record metadata, and reader navigation remain accessible live HTML.

## Proof surfaces

- Storybook: `Documents / Evidence Archive Atlas` with Surveying, Empty Range, Charted, Filtered, Needs Attention, and Production Raster states.
- Visual matrix: five deterministic fixture states at 768, 1024, and 1280 pixels; production raster retained for human inspection.
- Asset provenance: `apps/reading/src/brand/werner/documents/README.md`.

## Authority and safety

- Query parameters, `limit=500`, tier bucketing, row metadata, and encoded `/wrestle/:documentId` navigation remain authoritative.
- The frame is a `div`; PanelLayout retains the route-level `main` landmark.
- Generated art is empty-alt, assistive-hidden, non-interactive, and semantically empty.
- Fetch failures use fixed recovery copy and never expose raw HTTP or exception details.

## Verification

- Focused behavior suite: 4/4 passing, including exact query construction, trimmed investigation filtering, encoded reader navigation, and private error copy.
- Accessibility: 0 axe violations across all six lifecycle stories at 1280px.
- Responsive visual proof: 15 deterministic baselines across 768px, 1024px, and 1280px.
- Production and component builds: green; bundle budget retains 104.94 KB of primary-chunk headroom.
- Design-system gates: token lint and type-scale lint green.
