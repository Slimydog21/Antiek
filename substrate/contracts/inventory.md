# Contract inventory — `substrate/contracts/`

The shared contracts the four product workflows build against, who owns each,
who consumes it, and whether its shape is pinned. Authored for antiek-unified
SPR-01. Every consumer relationship below was cross-checked against the actual
product-spec sprint pages (`specs/{deep-research-workspace,read,write,speak}/`)
— no invented dependency.

| Contract | Owning spec + sprint | Consumers | Status | Mirrors (verified) |
|---|---|---|---|---|
| `InsightNodeContract` | DRW SPR-01 | Research, Read, Write, Speak | committed | `substrate/graph/insight_question.py` (content-addressed id, `node_type='insight'`) |
| `QuestionNodeContract` | DRW SPR-01 | Research, Read, Write, Speak | committed | `substrate/graph/insight_question.py` (`asks_about`/`resolved_by` edges) |
| `NoteTakerOutputContract` | DRW SPR-03 | Research, Read, Write | committed | `roles/note_taker/parser.py::ExtractedNote` (L31-41) |
| `ContextPackContract` / `AssembledLayerContract` | DRW SPR-04 | Research, Read | committed | `substrate/context_pack/` (`ContextPack`, `AssembledLayer`) |
| `ReaderSurfaceContract` | antiek-reader SPR-01 | Research, Read, Write | committed | `substrate/contracts/reading_surface.py` (PINNED; concrete `Region`/`RenderedRegion`/`AnchoredNote` over `document_model`; ownership moved off DRW SPR-10, never built there); seam #1 |
| `ResearchRunner` (+ `StepEvent`) | DRW SPR-02 | Research (+ unified SPR-02 remote-exec) | committed | re-export of `runtime/research_runner/protocol.py` |
| `OutlineBlockContract` | Write SPR-01 | Write (+ Speak via Write authoring) | committed | `substrate/write/outline_block.py` (L76-93) |
| `ServableEntryContract` | Read SPR-01 (+ `provenance_class` from this sprint) | Read, Speak | committed | `constants.BOOK_SERVABILITY_STATUSES` (L545-551); seam #4 |
| `AccrualContract` | Read SPR-09 / Speak SPR-07 | Read, Speak | committed | `speak/contributor.py::AccrualLine`; single escrow-balance writer = `ip_holders.accrue_escrow` (NOT publisher_escrow.py — reporting only; corrected post-SPR-03); seam #3 |
| `InterviewerResultContract` | Speak interviewer | Speak, Write | provisional | (Speak interviewer shape not fully pinned) |
| `ConsentContract` | Speak SPR-01 | Speak, Read (seam #4) | provisional | `substrate/speak/` consent + rights gate |
| `EconomicsCellContract` | Speak SPR-07 | Speak, cost surface (SPR-07 unified) | committed | economics matrix (`CREATOR_REV_SHARE` 70% public) |

## DRW citation audit (the seam-#6 risk surface)

The reverse index in `drw_sprint_lock.py` is grounded in these spec-body
citation counts (`grep -ohiE "DRW SPR-?[0-9]+"` across each product spec's
sprint HTML, 2026-05-25):

| DRW sprint | Deliverable | Cited by | Count (read / write / speak) |
|---|---|---|---|
| SPR-01 | insight/question nodes | read, write | 4 / 7 / — |
| SPR-03 | async note-taker | read, write | 11 / 3 / — |
| SPR-04 | max context pack | read | 6 / — / — |
| SPR-05 | cascade planner | read | 11 / — / — |
| SPR-06 | parallel orchestration | read | 4 / — / — |
| SPR-07 | structural gap detection | speak | — / — / 10 |
| SPR-10 | reading surface | read, write | 18 / 5 / — |

The master spec's claim that the specs cite DRW SPR-01/03/04/05/06/07/(08)/10
is confirmed. The critical path is **DRW SPR-01 → SPR-03 → SPR-10** — the three
shared primitives Read/Write/Speak all rest on (`dependency_map.critical_path()`).

## What this package is NOT

Interfaces only. No DB calls, no I/O, no business logic, no product internals.
The real writers live in the products (`promote_insight`, `accrue_contributions`,
the serving layer); these are the shapes those writers conform to and the
consumers compose against. Implementing a product's internals here would be
the cardinal sin (duplication → future divergence). See the SPR-01 "Out of
scope" list.
