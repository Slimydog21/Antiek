## Sprint SPR-07 (ANTIEK-HPRJ) — Ingestion Boundary — Handoff

### Env Card

| Field | Value |
|-------|-------|
| Date (UTC) | 2026-06-30 |
| Repo root (`pwd`) | `/Users/slimydog/Desktop/Antiek` |
| Branch | `html-projection/land-antiek` |
| Commit SHA | `1eff550b59a7d648a31dd077abf4a55ae3e8a1e0` |
| Python | `/Users/slimydog/Desktop/Antiek/.venv/bin/python` (`Python 3.12.13`) |
| LLM contacted this session | `no` |
| Network required for gates | `no` |

### Not proved

| Row | Hermetic proof | Not proved |
|-----|----------------|------------|
| Born-Antiek artifact ingest | Signed `.antiek` and signed `.antiek.html` ingest only structured islands; tampered/unsigned/garbage quarantine | General §7 daemon data/instruction boundary |
| Injection canary | Prompt-injection text lands as a JSON text-node value with `framing="quoted_payload"` | All non-artifact context-pack/tool-output paths |
| Foreign HTML | Hostile corpus quarantines script/event/javascript/data/svg/srcdoc/spoofed marker vectors | Live acquisition path integration beyond the sanitizer decision function |
| CI wiring | Blocking workflow step runs `services/html_projection`, `services/antiek_format`, and `services/ingestion` suites | Remote CI run result for this exact branch state |

### Status

`done` — HPRJ SPR-07 closes the artifact-shaped ingest boundary: returning born-Antiek artifacts are signature-gated and island-only, foreign HTML has a quarantine sanitizer and hostile corpus, and projection/format/ingestion gates are wired into CI. The broader §7 daemon boundary remains explicitly out of scope.

### Files touched

- `services/ingestion/ingest_antiek.py` — signature-gated `.antiek` / `.antiek.html` ingest, island-only doc-model extraction, quarantine outcomes, and quoted-payload framing.
- `services/ingestion/sanitize_foreign_html.py` — foreign-HTML sanitizer that reuses the projection gate and adds foreign-only vector buckets.
- `services/ingestion/tests/test_ingest_island_only.py` — signed-structured ingest, injection canary, tampered shell, garbage, single-file, tampered single-file, and unsigned HTML quarantine tests.
- `services/ingestion/tests/test_sanitize_foreign_html.py` — hostile corpus with failing-before/passing-after vector checks plus clean controls.
- `.github/workflows/ci.yml` — blocking HTML-projection layer gate over `services/html_projection/`, `services/antiek_format/`, and `services/ingestion/`.
- `docs/ingestion_boundary_scope.md` — honest scope: closed artifact/foreign-HTML/CI slice, open daemon boundary.

### Milestones (checkboxes)

- [x] M1: Scope discipline — artifact-shaped ingest slice separated from the larger daemon data/instruction boundary.
- [x] M2: Island-only ingest — signed `.antiek` reads canonical `content.tiptap.json`; signed `.antiek.html` verifies then extracts the doc-model island; rendered HTML is never parsed as content.
- [x] M3: Injection canary — prompt-injection payload ingests as quoted structured data, not executable instructions.
- [x] M4: Foreign-HTML sanitizer — script/external-fetch gate reused and foreign-only vectors added.
- [x] M5: CI wiring — projection/format/ingestion services run as a blocking workflow step.
- [x] M6: Honest scope doc — remaining daemon boundary is named rather than implied closed.

### Gate results

| gate | command | exit |
|------|---------|------|
| SPR-07 focused ingest bundle | `./.venv/bin/python -m pytest services/ingestion/tests/test_ingest_island_only.py services/ingestion/tests/test_sanitize_foreign_html.py -q` | 0 (`23 passed in 0.46s`) |
| CI-equivalent services gate | `./.venv/bin/python -m pytest services/html_projection/ services/antiek_format/ services/ingestion/ -q -p no:cacheprovider` | 0 (`487 passed, 10 skipped in 4.53s`) |

The 10 skips are the existing sidecar/substrate-surface skips documented by the tests; they are not SPR-07 failures.

### Decisions made mid-flight

- Quarantined foreign HTML on any vector instead of attempting lossy stripping. This keeps the boundary auditable and avoids accidentally preserving active markup.
- Reused SPR-02/SRP-04 primitives (`find_violations`, `read_antiek`, `verify_single_file_html`, `extract_island`) rather than forking parser or signature behavior.
- Kept daemon context-pack/tool-output boundaries out of SPR-07 and documented them as not proved.

### Assumptions surfaced

- A bare projection HTML file, even with a doc-model island, is not a born-Antiek artifact unless it carries a verifiable signature island.
- Foreign HTML carrying `data-antiek` markers is spoofing a born-Antiek artifact and must be quarantined by the foreign sanitizer.
- Clean prose that mentions attack vocabulary should pass; the sanitizer is tag/attribute/vector-scoped, not substring panic.

### Steelman rejected alternative

Strip hostile foreign HTML into a sanitized subset. Steelman: more user content survives ingest. Why it lost: stripping creates a second renderer/parser semantics surface and makes it harder to prove what survived; quarantine-on-vector is more defensible for the ingestion boundary.

### Open questions

- The broader §7 daemon data/instruction boundary still needs its own spec and fixtures for tool outputs, web fetches outside acquisition, and model-generated text re-entering LLM contexts.
- Live acquisition integration should call the sanitizer at every foreign-HTML entry point and prove that wiring separately.

### Scope Map

**Investigation ID:** ANTIEK-HPRJ-SPR-07

**Next sprint:** SPR-08 demand gate / round-trip detector.

### Out-of-scope temptations encountered

- Wanted to claim the whole data/instruction boundary closed; resisted because only artifact and foreign-HTML sanitizer slices are verified here.
- Wanted to parse visible rendered HTML for convenience; resisted because signed structured content is the source of truth.
