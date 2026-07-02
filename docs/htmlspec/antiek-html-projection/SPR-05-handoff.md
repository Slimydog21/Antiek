## Sprint SPR-05 (ANTIEK-HPRJ) — Synthesis Artifact Export — Handoff

### Env Card

| Field | Value |
|-------|-------|
| Date (UTC) | 2026-06-30 |
| Repo root (`pwd`) | `/Users/slimydog/Desktop/Antiek` |
| Branch | `html-projection/land-antiek` |
| Commit SHA | `888b7043bfa37a6587f9ee3979cbefb259545b1d` |
| Python | `/Users/slimydog/Desktop/Antiek/.venv/bin/python` (`Python 3.12.13`) |
| LLM contacted this session | `no` |
| Network required for gates | `no` |

### Not proved

| Row | Hermetic proof | Not proved |
|-----|----------------|------------|
| Synthesis adapter | Servable text embeds; personal/restricted text is cite-only and absent from serialized doc-model | Live graph resolver with production data |
| Export route | 200/403/404/500 paths, in-path zero-script refusal, and multi-format route behavior | Browser-clicked UI flow in a running app |
| Rights filter | Secret personal-reading text absent from HTML and `.antiek` bytes | Jurisdiction-specific legal review |
| Format routing | HTML, `.antiek`, and `.antiek.html` outputs verified in route tests | Long-term public sharing policy |

### Status

`done` — synthesis exports render as script-free artifacts with rights-aware source treatment, in-path gate refusal, and later route support for HTML, signed `.antiek`, and signed `.antiek.html` formats.

### Files touched

- `docs/decisions/spr-05-export-eligibility-contract.md` — synthesis artifact export eligibility and rights policy.
- `services/html_projection/adapters/synthesis.py` — synthesis-to-doc-model adapter, claim/source blocks, cite-only restricted source handling, and provenance manifest.
- `services/html_projection/tests/test_synthesis_adapter.py` — adapter fidelity, no-leak, refusal, island round-trip, and gate-clean tests.
- `services/html_projection/tests/test_provenance_gate.py` — provenance/rights edge cases around synthesis exports.
- `interfaces/research/api/synthesis_artifact.py` — export route, 403-with-reason, in-path zero-script gate, and routing-map backed multi-format output.
- `tests/api/test_synthesis_artifact.py` — route tests for allowed/restricted/mixed/poisoned/not-found and multi-format outputs.
- `apps/reading/src/modes/ResearchWorkstation/MasterMdViewer.tsx` — synthesis artifact export affordance using the shared export control.

### Milestones (checkboxes)

- [x] M1: Eligibility contract — synthesis export policy recorded before route implementation.
- [x] M2: Adapter — synthesis claims convert to doc-model blocks with servable text embedded and restricted/personal sources cite-only.
- [x] M3: Route — `/api/syntheses/{id}/artifact.html` serves gate-clean HTML, refuses restricted exports with reason, and never serves poisoned render output.
- [x] M4: Provenance gate — doc-model and visible HTML omit restricted text while preserving titles/IP-holder/cite-only markers.
- [x] M5: Read app affordance — synthesis artifacts are offered from the Research Workstation via the shared artifact export component.
- [x] M6: Routing map continuation — same synthesis route can emit HTML, signed `.antiek`, or signed `.antiek.html` with rights filter preserved.

### Gate results

| gate | command | exit |
|------|---------|------|
| SPR-05 synthesis artifact focused bundle | `./.venv/bin/python -m pytest services/html_projection/tests/test_synthesis_adapter.py services/html_projection/tests/test_provenance_gate.py tests/api/test_synthesis_artifact.py -q` | 0 (`22 passed, 1 warning in 0.57s`) |

Warning observed: Starlette TestClient deprecation warning from FastAPI’s test client import; not a SPR-05 behavioral failure.

### Decisions made mid-flight

- Applied rights filtering inside the adapter so the serialized doc-model island is safe, not just the visible HTML.
- Kept route gate enforcement in-path: a render that produces script is refused instead of relying on upstream renderer assumptions.
- Used 403-with-reason for restricted synthesis exports so operator/product surfaces can explain refusal without leaking withheld text.

### Assumptions surfaced

- `personal_reading` and unrecognized content classes are deny-by-default for embedded body text.
- Titles, locators, and IP-holder identifiers may remain as cite-only attribution metadata even when source body text is withheld.
- Multi-format routing inherits the adapter’s rights filter; tests assert the `.antiek` bytes do not contain withheld personal-reading text.

### Steelman rejected alternative

Export only plain HTML first and defer signed formats. Steelman: smaller first route and easier manual inspection. Why it lost: the projection stack already has signed container and single-file primitives, and route tests can prove parity without widening the rights surface.

### Open questions

- Live graph-backed resolver behavior should be smoke-tested with production-like synthesis records.
- Product copy for user-facing export refusal can be refined without changing the route contract.

### Scope Map

**Investigation ID:** ANTIEK-HPRJ-SPR-05

**Next sprint:** SPR-06 notebook and deliverable artifact exports.

### Out-of-scope temptations encountered

- Wanted to embed all cited chunk text for a richer artifact; resisted because the serialized island would leak restricted/personal-reading text.
- Wanted to treat route gate as redundant with renderer tests; resisted because route-level refusal is the production boundary.
