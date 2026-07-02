# Egghead-2 — ANT-AHT execution review

**Thesis:** Did exec meet the htmlspec + Hawkins bar for Thariq-style HTML transport?

**Verdict:** **Proceed** — SPR-AHT-01..06 are mechanically gated (P-18 `canonical_verify.sh html-transport`). Residual product surface (Write drag-drop, book ingest HTML, dedicated `ArtifactKind`) is explicitly out of scope and listed in matrix "Not proved".

## Evidence

| Claim | Proof |
|-------|--------|
| Graph canonical, HTML lens | `docs/decisions/research-artifact-v0.md`; export reads `distillation_for` |
| Per-investigation HTML | `export_research_artifact` + optional post-complete hook |
| Merge compose | `compose_artifacts` + hash conflict section |
| Ingest reader HTML | `ANTIEK_READER_SNAPSHOT` + `reader_html.py` |
| Cross-window transport | `RESEARCH_ARTIFACT_TRANSPORT.md`, copy button, `import_agent_notes` |
| Landscape inventory | `docs/html/html-landscape.html` (73 assets) |
| API surface | `artifact_routes.py` export / import-notes / blocks |

## Steelman rejected

- **HTML-primary substrate:** faster for agents, collapses provenance — rejected per §9.0 + single-writer.
- **Git-tracked artifacts:** better sharing — rejected for diff noise; operator store under `~/.antiek/`.

## Open (not blocking ledger)

- Write UI Lego blocks (P-18 not proved row).
- EPUB/PDF reader snapshots (acquisition extension).
- `ArtifactKind` literal bump.

## Loop decision

`proceed-no-ship` unless operator requests PRcrouch.