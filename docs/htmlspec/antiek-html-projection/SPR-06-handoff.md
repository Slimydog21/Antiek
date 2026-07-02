## Sprint SPR-06 (ANTIEK-HPRJ) — Notebook and Deliverable Artifact Exports — Handoff

### Env Card

| Field | Value |
|-------|-------|
| Date (UTC) | 2026-06-30 |
| Repo root (`pwd`) | `/Users/slimydog/Desktop/Antiek` |
| Branch | `html-projection/land-antiek` |
| Commit SHA | `a3d905f02c5b7f1cd73eb655e5ab15f70d51e788` |
| Python | `/Users/slimydog/Desktop/Antiek/.venv/bin/python` (`Python 3.12.13`) |
| LLM contacted this session | `no` |
| Network required for gates | `no` |

### Not proved

| Row | Hermetic proof | Not proved |
|-----|----------------|------------|
| Notebook adapter | Resolver-aware and self-contained export adapters, no personal-reading leak in HTML/doc-model/container | Full production notebook corpus sweep |
| Deliverable adapter | Known block mapping, unsupported block surfacing, cite-only non-servable blocks | Rich Write surface formatting beyond current section/block model |
| Routes | HTML, `.antiek`, `.antiek.html`, 400/404 behavior for notebook and deliverable routes | Browser-clicked UI flow against a running app |
| Real resolver wiring | Notebook and deliverable integration tests seed DuckDB graph rows and resolve real refs | Live multi-user auth path |

### Status

`done` — Read notebooks and Write deliverables export portable artifacts in HTML, signed `.antiek`, and signed `.antiek.html` formats, with rights filters preserving no-leak behavior through doc-models, rendered HTML, and signed container bytes.

### Files touched

- `docs/decisions/hprj-spr06-codec-share-route.md` — codec/share-route decision for the export surfaces.
- `services/html_projection/adapters/notebook.py` — resolver-backed notebook rendering path with rights-aware ref handling and tombstones.
- `services/html_projection/adapters/notebook_export.py` — self-contained notebook export adapter that pre-resolves refs and removes runtime ref IDs.
- `services/html_projection/adapters/deliverable.py` — Write deliverable-to-doc-model adapter with known block mapping, unsupported block metadata, and cite-only non-servable source handling.
- `services/html_projection/routing_map.py` — single surface/format table and deterministic `emit()` dispatch to HTML, `.antiek`, and `.antiek.html` writers.
- `interfaces/research/api/notebook_artifact.py` — notebook artifact route and real-ref resolver.
- `interfaces/research/api/deliverable_artifact.py` — deliverable artifact route and real-ref resolver.
- `interfaces/research/api/app.py` — route registration for notebook and deliverable artifact exports.
- `tests/api/` and `services/html_projection/tests/` — adapter, route, integration, and share-parity gates.

### Milestones (checkboxes)

- [x] M1: Codec/share-route decision recorded before route wiring.
- [x] M2: Notebook artifact adapter — Tier-2/3 notebook refs render through a rights-aware resolver, with deleted/missing refs as visible tombstones.
- [x] M3: Deliverable artifact adapter — Write deliverable sections map to doc-model blocks, unsupported kinds surface visibly, and non-servable source text is withheld.
- [x] M4: Routing map — one table owns allowed formats per share surface and `emit()` dispatches deterministically to existing writers.
- [x] M5: Notebook route — `/api/notebooks/{id}/artifact?format=...` emits HTML, signed `.antiek`, and signed `.antiek.html`.
- [x] M6: Deliverable route — `/api/deliverables/{id}/artifact?format=...` emits the same format trio with rights filters preserved.
- [x] M7: Real resolver wiring — notebook and deliverable integration tests seed real graph rows and prove resolved refs reach adapters correctly.

### Gate results

| gate | command | exit |
|------|---------|------|
| SPR-06 notebook/deliverable focused bundle | `./.venv/bin/python -m pytest services/html_projection/tests/test_notebook_artifact.py services/html_projection/tests/test_notebook_export.py services/html_projection/tests/test_deliverable_artifact.py services/html_projection/tests/test_notebook_export.py tests/api/test_notebook_artifact.py tests/api/test_deliverable_artifact.py tests/api/test_notebook_export_integration.py tests/api/test_deliverable_export_integration.py services/html_projection/tests/test_share_parity.py -q` | 0 (`41 passed, 1 warning in 1.56s`) |

Warning observed: Starlette TestClient deprecation warning from FastAPI’s test client import; not a SPR-06 behavioral failure.

### Decisions made mid-flight

- Kept surface/format policy in `SURFACE_FORMATS` and writer dispatch in `emit()`, so format choice has one table and emission does not reimplement writers.
- Made notebook export self-contained for signed formats: refs are pre-resolved before container emission, and personal-reading body text is withheld before serialization.
- Treated unsupported deliverable block kinds as visible placeholders plus metadata, not silent drops.

### Assumptions surfaced

- Exported notebook containers should not depend on live ref resolution when opened offline; the exported doc-model carries safe resolved content or cite-only markers.
- Unknown share surfaces default to unsigned HTML only until explicitly added to the routing table.
- `personal_reading` text remains cite-only across Read and Write surfaces unless a later rights decision changes that policy.

### Steelman rejected alternative

Give each route its own format branching and writer calls. Steelman: each route is easier to read in isolation. Why it lost: it creates drift risk across notebook, synthesis, deliverable, and future share surfaces; the routing map is the harder-to-vary single decision point.

### Open questions

- Product acceptance still needs live UI smoke for notebook and deliverable export menus.
- Deliverable formatting can grow after the current section/block model is ratified by real Write workflows.

### Scope Map

**Investigation ID:** ANTIEK-HPRJ-SPR-06

**Next sprint:** SPR-07 ingest boundary and foreign-HTML sanitizer.

### Out-of-scope temptations encountered

- Wanted to make exported artifacts resolve refs lazily at open time; resisted because portable artifacts need offline, rights-safe content.
- Wanted to hide unsupported deliverable block kinds for prettier output; resisted because visible unsupported placeholders preserve authoring fidelity.
