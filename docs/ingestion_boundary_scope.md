# Ingestion boundary — honest scope (HPRJ SPR-07)

What the ingestion-boundary work has and has NOT closed. This document exists
so no test name, docstring, or sentence elsewhere claims more than is true —
**the §7 daemon's general data/instruction boundary is NOT verified.**

## Closed — the artifact-shaped slice

- **Island-only ingest (M2).** `services/ingestion/ingest_antiek.py`. A
  returning born-Antiek artifact is ingested via its **signed structured
  doc-model only**:
  - a `.antiek` container → `read_antiek`'s `content.tiptap.json` (the signed
    canonical content); the rendered `projection.html` is **never parsed for
    content**;
  - a single-file `name.antiek.html` → the whole-file signature is verified,
    then the doc-model island is extracted (`island.extract_island`).
  - A signature that does not verify, or a malformed/unsigned artifact,
    **quarantines** with a logged reason — never silently ingested.
  - Proven by the **injection canary**: an artifact carrying
    `"Ignore previous instructions…"` ingests to a JSON **text-node value**
    (quoted data, `framing="quoted_payload"`), not an instruction; the
    ingested doc-model carries no rendered-HTML chrome. Tampered shell /
    tampered single-file / unsigned HTML / garbage all quarantine
    (`services/ingestion/tests/test_ingest_island_only.py`).
  - No second ingestion fork: it reuses SPR-04 (`read_antiek`,
    `single_file.verify_single_file_html`) + SPR-02 (`extract_island`).

## Open — NOT closed by this slice

- **M3 — foreign-HTML sanitizer + hostile corpus.** HTML that never came from
  Antiek (`acquisition/urls`, the universal ingest) is **not yet** wrapped by a
  sanitizer with the failing-before/passing-after hostile corpus (script
  vectors in all casings/encodings, event handlers, `javascript:`/`data:` URIs,
  remote-fetch beacons, SVG `foreignObject`, `srcdoc`, D9 bucket-C markers).
  This is the larger half of the boundary and remains TODO. **Until it lands,
  foreign HTML entering through acquisition is not sanitized by this work.**
- **M4 — CI wiring.** The projection gates (zero-script, palette, determinism,
  signature, ingest quarantine) are green locally but are **not yet wired into
  CI** as a blocking check.
- **The §7 daemon data/instruction boundary at large.** Every non-artifact path
  by which text can enter an LLM role's context — tool outputs, web fetches
  outside `acquisition`, model-generated text re-entering context-packs — is
  **out of scope and stays open**. The karpathy-lens canon flags this as the
  highest-priority unverified gap; this slice addresses only the born-Antiek
  artifact path, and only for files that carry a verifiable signature.

## What would close the remaining items

M3: a single sanitizer wrapping the existing `acquisition` ingest path (grep-
proven no second fork), driven by a decision table, with one hostile-corpus
fixture per category and a failing-before/passing-after pair each. M4: add the
`services/html_projection` + `services/antiek_format` + `services/ingestion`
suites + the zero-script/palette/determinism gates to the CI workflow as a
required check. The daemon boundary is a separate, larger effort (its own
spec), not closeable here.
