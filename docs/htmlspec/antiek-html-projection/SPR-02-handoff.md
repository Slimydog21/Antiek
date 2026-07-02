## Sprint SPR-02 (ANTIEK-HPRJ) — Projection renderer — Handoff

### Status
done

### Files touched
- `services/html_projection/__init__.py` (new) — package init + re-exports.
- `services/html_projection/renderer.py` (new) — `render(doc_model, ctx) -> str`; pure, deterministic, script-free; one partial per block type; provenance footer; no wall-clock.
- `services/html_projection/island.py` (new) — inert `<template data-antiek="doc-model" data-schema-version="1">` data island + `extract_island(html)` round-trip; typed-error rejection of unknown schema versions.
- `services/html_projection/gate.py` (new) — stdlib-only zero-script gate. Catches: script tags (any casing/whitespace), `on*=` event handlers, `javascript:`/`vbscript:` hrefs (incl. NUL/C0 control-char + entity obfuscation), external `src`/`srcset` (img/audio/video/source/iframe/embed/track), external CSS `url()`/`@import`, meta-refresh + base-href external nav, AND (orchestrator follow-up) `<object data>`, `<link href>`, `<svg><use href>`, `<form action>`/`<button formaction>` external fetch.
- `services/html_projection/contract.py`, `tokens.py`, `escape.py`, `context.py` (new) — block taxonomy contract table, CSS tokens, HTML escaping, render context.
- `services/html_projection/partials/` (new) — one template partial per block type.
- `services/html_projection/tests/` (new) — `test_renderer.py`, `test_island.py`, `test_gate.py`, `test_determinism.py`, `test_tombstone.py`, `test_contract.py` + `fixtures/` (golden corpus ≥5 doc-models).
- `services/html_projection/tests/test_determinism.py` — orchestrator fixed the dict-iteration-order pin (was a no-op: rendered the same object twice; now renders two distinct doc-models with same content but different attrs dict insertion order → actually proves order-independence).

### Milestones
- [x] M1: Block taxonomy survey + rendering contract — contract table covers every TipTap/ProseMirror + structured-block type, cited file:line; unknown-block fallback = visible placeholder.
- [x] M2: Renderer core — `render(doc_model, ctx) -> str`; golden corpus (≥5 doc-models, incl. unknown-only) renders; fully self-contained (no external src/href); provenance footer; grep proves no wall-clock.
- [x] M3: Data island + round-trip — `extract_island(render(d)) == d` over golden corpus + adversarial escaping edge cases (`</template>` in strings, nested templates, unicode, quotes); extractor rejects unknown schema versions with typed error.
- [x] M4: Zero-script gate — red on each class (script, uppercase SCRIPT, onload=, javascript: href, external img src, srcset, @import/url(), meta refresh, base href, object data, link href, svg use href, form action); green on golden corpus; stdlib-only.
- [x] M5: Determinism proof — 3-way byte-identity (twice in one process + once in fresh subprocess); nondeterminism sources pinned (dict-order [fixed to be non-no-op], hash-seed, import-order, tempfile paths, no uuid/random).
- [x] M6: Tombstone + ref-resolution — deleted ref renders the same tombstone as the live notebook; never a crash, never a silent drop.

### Verification gate results
- goldenCorpusRenders: **pass**
- selfContained: **pass**
- islandRoundtrip: **pass**
- zeroScriptGateRed: **pass** (every class has a seeded red test)
- zeroScriptGateGreen: **pass** (full golden corpus)
- crossProcessDeterminism: **pass** (real subprocess leg)
- refTombstone: **pass**
- noRegressions: **273 passed, 10 skipped** (183 html_projection + 62 format + 28 runner/drwl/parent; 10 honestly-scoped skips)
- testCount: 183 (html_projection)
- Adversarial verify (workflow `wf_18e4f235-cde`, 3 lenses, 2 rounds): **zero-script** found 4 MAJOR defects round 1 (srcset, CSS @import/url(), NUL/C0 javascript:, meta-refresh/base-href) — all fixed in sharpen round; round 2 found 2 MINOR residuals (object/link/svg-use/form-action vectors, dict-order no-op) — **both fixed by orchestrator**. **island-roundtrip** CLEAN both rounds. **determinism** round 2 found 1 MINOR (dict-order no-op) — **fixed by orchestrator**.

### Decisions made mid-flight
- Gate scope broadened from strictly-script to the self-contained/no-external-nav invariant (the gate docstring names "fetches code" as the threat; the §7 autonomous-ingest RCE model covers redirect/relative-URL-hijack). Additive violation classes; no existing golden-corpus projection emits these.
- Kept gate stdlib-only (`re` only) so SPR-07 can reuse it on the ingest side.
- Orchestrator added `<object data>`, `<link href>`, `<svg><use href>`, `<form action>`/`<button formaction>` to the external-fetch gate (the zero-script lens round-2 residual) — these are real external-fetch/nav vectors the self-contained invariant forbids.
- Orchestrator fixed the dict-iteration-order determinism pin (was a no-op; now exercises two distinct doc-models with different attrs insertion order).

### Assumptions surfaced (rigor #1)
- The 10 sidecar_e2e skips are pre-existing intentional skips (Wave-2 substrate modules absent on this branch), not regressions.
- `data:` URIs are permitted in the gate (inline, self-contained) for forward-compat with SPR-03 widgets, though the renderer doesn't emit them.
- The renderer takes the SAME doc-model shape `services/antiek_format` stores (verified during M1 taxonomy survey) — the projection renders what the container persists.

### Steelman of rejected alternative (rigor #2)
- Client-side rendering (ship JSON + a JS renderer in the artifact). Steelman: halves the template surface (one JSON + one JS vs N partials), lets the browser render. Why it lost: the SCRIPT-FREE invariant (master-spec key invariant 1) is non-negotiable — the §7 daemon ingests artifacts autonomously, so a script in an artifact is an RCE vector. A JS renderer ships executable script by definition. The pure server-side renderer + inert data island gives the same "artifact carries its model" property without any executable script.

### Open questions discovered
- SPR-03 (widget library) will add charts/sparklines/dep-graphs as rendered SVG/CSS — the gate's external-fetch check must continue to flag any widget that tries to load an external asset. The widget-call seam (tokens module) is this sprint's contract; widgets themselves are SPR-03.
- The `data-schema-version="1"` on the island is the contract that outlives the renderer — future parsers read it. A v2 island shape would need a migration + version bump.

### Next sprint can start when
- SPR-03 (widget library) can begin: the renderer + tokens module + widget-call seam are landed. SPR-03 builds charts/sparklines/dep-graphs as script-free SVG/CSS widgets that render through `render()`.
- SPR-04 (projection.html shell) can begin once the operator ratifies the shell — it amends the `.antiek` container (SPR-01) with a signature-covered `projection.html` entry.

### Out-of-scope temptations encountered
- Wanted to build widgets (charts/sparklines); resisted (SPR-03; this sprint ships the seam + placeholders).
- Wanted to wire the renderer into export routes; resisted (SPR-05/06).
- Wanted to add the projection.html shell; resisted (SPR-04, operator-ratified).
- Wanted to fix the pre-existing stale-test collection errors; resisted (unrelated prior work).
