## Sprint SPR-08 (ANTIEK-HPRJ) — Form-Factor Demand Gate — Handoff

### Env Card

| Field | Value |
|-------|-------|
| Date (UTC) | 2026-06-30 |
| Repo root (`pwd`) | `/Users/slimydog/Desktop/Antiek` |
| Branch | `html-projection/land-antiek` |
| Commit SHA | `47823d826368113a76c927f66544609bfcfebb7a` |
| Python | `/Users/slimydog/Desktop/Antiek/.venv/bin/python` (`Python 3.12.13`) |
| LLM contacted this session | `no` |
| Network required for gates | `no` |

### Not proved

| Row | Hermetic proof | Not proved |
|-----|----------------|------------|
| Pre-registered demand criteria | Criteria, window, admissible signals, and verdict mapping committed before detector/telemetry/UI work and pinned by analysis code | That any admissible demand signal has occurred |
| Round-trip detector | Real `.antiek` bytes classify `returned_unmodified`, `traveled_and_changed`, and `novel`; ingest wiring classifies only accepted born-Antiek artifacts | Browser/live production telemetry persistence for real user windows |
| Event privacy | Builders emit counts/choices/ids/hashes only; allowlist rejects content-bearing or unknown fields | A deployed analytics pipeline consuming these events end to end |
| Verdict analysis | Same event list maps reproducibly to `SUSTAIN` or `RETIRE`; downloads/share-link clicks do not count | Operator-run tester recruitment, N selection, window open/close, or signed final verdict |
| Neutral export offer | Shared component renders all three formats with equal-prominence labels and calls the selected route | Playwright/browser click-through against a running app for this exact branch state |

### Status

`done for measurement machinery; verdict data-dependent` — HPRJ SPR-08 closes the buildable part of the form-factor demand gate: pre-registration, round-trip detection, ingest integration, privacy-gated event taxonomy, neutral multi-format export affordance, reproducible verdict analysis, and both verdict templates. It does not claim demand exists; the operator still must run the tester window and sign either `SUSTAIN` or `RETIRE` from observed admissible signals.

### Files touched

- `docs/decisions/form-factor-demand-gate-PREREGISTERED.md` — immovable question, admissible evidence, neutrality rule, window, N, and verdict mapping.
- `services/demand_gate/roundtrip_detector.py` — deterministic export registry, canonical content hashing, and round-trip classification.
- `services/ingestion/ingest_antiek.py` — optional export-registry integration on the signature-checked born-Antiek ingest path.
- `services/demand_gate/events.py` — demand-gate event names, builders, and privacy allowlist.
- `services/demand_gate/analysis.py` — reproducible verdict computation pinned to the pre-registration commit.
- `docs/decisions/verdict-retire.md` — pre-written RETIRE verdict template.
- `docs/decisions/verdict-sustain.md` — pre-written SUSTAIN verdict template.
- `apps/reading/src/components/ArtifactExport.tsx` — shared equal-prominence export affordance for `html`, `antiek`, and `antiek_html`.
- `apps/reading/src/modes/ResearchWorkstation/MasterMdViewer.tsx`, `apps/reading/src/modes/Notebook/index.tsx`, and `apps/reading/src/modes/CreationStudio/index.tsx` — surfaces using the shared export component.
- `tests/test_roundtrip_detector.py`, `services/ingestion/tests/test_ingest_roundtrip.py`, `tests/test_demand_gate_events.py`, `tests/test_demand_gate_analysis.py`, and `apps/reading/src/components/ArtifactExport.test.tsx` — focused proof suite.

### Milestones (checkboxes)

- [x] M1: Pre-register the demand gate before telemetry/detector/UI work; make thresholds and verdict mapping immovable.
- [x] M2: Build a mechanical round-trip detector and wire it into ingest without changing quarantine/accept decisions.
- [x] M3: Define the demand-gate event contract and mechanically reject content-bearing telemetry.
- [x] M4: Offer synthesis/notebook/deliverable export formats neutrally through the shared artifact export affordance.
- [x] M5: Compute `SUSTAIN`/`RETIRE` reproducibly from raw events with the pre-registration commit pinned.
- [x] M6: Pre-write both verdict templates so the final decision is not authored under post-window motivation.

### Gate results

| gate | command | exit |
|------|---------|------|
| SPR-08 focused Python bundle | `./.venv/bin/python -m pytest tests/test_roundtrip_detector.py tests/test_demand_gate_events.py tests/test_demand_gate_analysis.py services/ingestion/tests/test_ingest_roundtrip.py tests/api/test_synthesis_artifact.py -q` | 0 (`32 passed, 1 warning in 1.23s`) |
| SPR-08 export component | `npm test -- ArtifactExport.test.tsx` from `apps/reading` | 0 (`1 passed`, `3 passed`, `Duration 1.48s`) |

The Python warning is the existing Starlette TestClient deprecation warning. The Vitest run also printed existing Vite deprecation warnings and jsdom's "navigation to another Document" notice from anchor-click download behavior; the test process exited 0.

### Decisions made mid-flight

- Counted only mechanical, third-party, unpromptable demand signals: non-operator round-trips, third-party readers, and agent-unprompted adoption.
- Treated downloads, opens, share-link clicks, and compliments as non-admissible because they measure "nicer app" behavior, not demand for a new file format.
- Kept the event payload deliberately narrow: counts, format choices, IDs, and hashes only.
- Put all format export buttons behind one shared component so neutrality is not reimplemented per surface.

### Assumptions surfaced

- The operator's own enthusiasm is the named n=1 confound and must never sustain the format thesis.
- `returned_unmodified` is weaker than `traveled_and_changed`, but still useful to detect and audit; the pre-registered organic signal must be non-operator.
- The two-week window and tester count are operator responsibilities, not agent-runnable work.
- `.antiek` can remain useful as a signed/offline artifact even if the new-format framing is retired.

### Steelman rejected alternative

Use download/open volume as a softer sustain signal. Steelman: it is easier to collect and may show that testers like the artifacts. Why it lost: high download counts can be manufactured by UI enthusiasm and polite testers; they do not prove anyone wants a distinct file format. The gate is intentionally harsh because a positive result should be believable.

### Open questions

- The operator still needs to pin N testers in `[5, 15]`, open the two-week window, close it, run the analysis, and sign one verdict document.
- Production telemetry storage and dashboarding for these event builders remains to be wired if the live window is run through a deployed app rather than a controlled fixture.
- Browser-level click-through of the export affordance against this exact branch state remains unproven; the component and backend route behavior are covered.

### Scope Map

**Investigation ID:** ANTIEK-HPRJ-SPR-08

**Next sprint:** Demand-window operation or the next HPRJ sprint after the measurement machinery, depending on the master ledger.

### Out-of-scope temptations encountered

- Wanted to call the sprint a validation of `.antiek`; resisted because this sprint only built the measuring instrument.
- Wanted to treat file downloads as partial evidence; resisted because the pre-registration explicitly maps them to non-admissible data.
- Wanted to move verdict language after seeing any future data; resisted by pre-writing both verdict paths now.
