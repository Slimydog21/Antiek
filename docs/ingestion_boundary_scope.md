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
- **Foreign-HTML sanitizer + hostile corpus (M3).**
  `services/ingestion/sanitize_foreign_html.py` wraps the foreign-HTML
  decision point with quarantine-on-any-vector semantics. It reuses the
  SPR-02 zero-script/external-fetch gate and adds foreign-only buckets:
  executable/navigable `data:` payloads, SVG `foreignObject`, iframe
  `srcdoc`, and spoofed `data-antiek` markers. The hostile corpus has one
  failing-before/passing-after fixture per vector, plus clean-prose and inert
  raster-data-image controls (`services/ingestion/tests/test_sanitize_foreign_html.py`).
- **CI wiring (M4).** `.github/workflows/ci.yml` now runs
  `python -m pytest services/html_projection/ services/antiek_format/ services/ingestion/ -q -p no:cacheprovider`
  as a blocking "HTML-projection layer gates" job step, covering zero-script,
  palette, determinism, signature, shell integrity, island-only ingest, and
  foreign-HTML sanitizer quarantine.

## Open — NOT closed by this slice

- **The §7 daemon data/instruction boundary at large.** Every non-artifact path
  by which text can enter an LLM role's context — tool outputs, web fetches
  outside `acquisition`, model-generated text re-entering context-packs — is
  **out of scope and stays open**. The karpathy-lens canon flags this as the
  highest-priority unverified gap; this slice addresses only the born-Antiek
  artifact path, and only for files that carry a verifiable signature.

## What would close the remaining items

The daemon boundary is a separate, larger effort (its own spec), not closeable
inside HPRJ SPR-07. Closing it requires a context-pack / tool-output boundary
spec with fixtures for non-artifact text entering LLM roles.
