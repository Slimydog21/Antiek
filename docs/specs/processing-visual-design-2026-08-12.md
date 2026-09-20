# Processing (Casey Reas & Ben Fry) — Visual Design Integration Spec (2026-08-12)

**Status**: operator-brief response — "use Processing by Casey Reas and Ben Fry
for visual design that may get placed in the html assets (other than AI generated
image and video that I may tie in later on)". This spec defines where Processing
earns its place in Antiek's HTML-first artifact pipeline and where it does not.

---

## 1. What Processing is (short version)

Processing (processing.org) is the open-source language/environment for
generative visual design: a Java-based core (Processing 4.x) + p5.js (the
JavaScript sibling) + processing.py (Python mode). For a web-first product,
**p5.js is the operative surface**: deterministic(ish) canvas drawing, 2D/3D,
typography, data visualization, particle systems — all rendered in the browser,
no build step beyond a script include. Python mode (processing.py) is the right
shape for server-side generated SVGs/PNGs when a visual must be rendered
offline (e.g., during document ingestion).

## 2. The Antiek-shaped role for Processing

Antiek's thesis: every research/reading/writing artifact is self-contained
HTML. Visuals today come from Krea (AI image/video) + static brand assets.
Processing adds a third lane the AI-image lane cannot do well:

1. **Deterministic data-visualization skins** — charts, distributions,
   knowledge-graph layouts, attribution bars, temporal spines — generated from
   substrate data (DuckDB query → JSON → p5.js render). AI images are
   non-deterministic and cannot be re-rendered from data; p5.js can.
2. **Generative ambient visuals for artifact styles** — the style wheel
   (docs/design-system.md) can carry procedural backgrounds/headers/footers
   (fields, particle systems, typographic treatments) defined as p5.js
   sketches, forkable like any style token.
3. **Processing.py offline renders** — during ingestion, a Python-mode sketch
   can render a static SVG/PNG cover visual from the document's structure
   (section tree, citation graph) into the artifact HTML — deterministic,
   licensable, reproducible (Processing is LGPL — safe to embed outputs).

## 3. Where it is REJECTED (discipline, mirroring §16)

- **No Processing as the primary artifact renderer** — HTML/CSS + Antiek chrome
  (design-system.md) remains the artifact's skeleton; Processing is a visual
  *lane inside* the HTML, never the document itself.
- **No heavy p5.js on every page** — sketches are lazy-loaded per artifact
  style, degrade to a static SVG/CSS fallback when JS is disabled (honest
  state chips must not depend on canvas).
- **No server-side Java Processing** in the substrate process — the
  single-writer DuckDB host does not run a JVM; processing.py renders run in
  the remote-exec sandbox lane (docs/specs/scalability-roadmap-2026-08-12.md
  §3), never in-process.

## 4. Integration plan (v1 scope, 3 slices)

**Slice A — p5.js style lane (frontend, ~1 sprint)**
- Add p5.js as an optional artifact dependency (apps/reading, lazy `import()`).
- Extend the style registry (substrate/styles/) with a `sketch` token type:
  a style may carry a p5.js sketch URL or inline sketch + seed + palette
  (deterministic given seed — reproducible renders, matching the render
  determinism invariant I3 of style_routes.py).
- Style wheel UI: "generative skin" toggle per style with preview.

**Slice B — data-visualization lane (frontend+backend, ~1-2 sprints)**
- New route `GET /artifacts/{id}/viz/{kind}` returning a JSON data projection
  from the substrate (DuckDB query, read-only) for kinds: citation_graph,
  source_tier_distribution, attribution_bar (from substrate/ad_inventory),
  temporal_spine.
- `VizSketch.tsx` renders the projection via p5.js with the artifact's style
  seed; every viz carries a provenance footer (data source + query + style
  seed) per frontend-craft provenance discipline.

**Slice C — Processing.py offline cover lane (backend, ~1 sprint)**
- In the ingestion pipeline (upload_routes / reader_html_routes), an optional
  step: if `processing.py` is available in the sandbox, render a structural
  cover SVG (section tree + citation count) into the artifact HTML `<header>`.
- Deterministic + reproducible; hash-stamped like other artifact assets.

## 5. Guardrails

- p5.js is MIT-licensed (bundling fine); Processing is LGPL (outputs are
  yours; the runtime is not linked into Antiek). Add to THIRD_PARTY.md.
- Every sketch is seeded and style-bound: re-rendering an artifact with the
  same style+seed must produce the same visual (I3 determinism).
- Sketches never execute during server-side rendering of untrusted artifacts
  (sandboxed iframe with `sandbox=""` — same rule as style previews).
- No canvas = honest fallback (static SVG/CSS), never a broken chip.

## 6. Decisions needed from operator

1. Approve p5.js as the browser lane (vs raw canvas 2D — p5.js recommended for
   forkability + the Processing family connection).
2. Approve processing.py in the sandbox lane for offline cover renders.
3. Which viz kinds matter most first (citation_graph / attribution_bar /
   source_tier_distribution / temporal_spine) — default order above.
