# Seam inventory — `substrate/seams/`

The cross-workflow handoffs, direction-pinned and one-way, each carrying a
graph **entity by reference** (an id + a provenance ref) — never a copy.
Authored for antiek-unified SPR-03. Every implementing-sprint citation below
was cross-checked against the actual product-spec sprint pages
(`specs/{read,write,speak,deep-research-workspace}/`) — no invented dependency.

## The seven seams

| Seam (contract) | Direction | Payload carries (SPR-01 contract) | Implements: from-side | Implements: to-side | Status |
|---|---|---|---|---|---|
| `ResearchToReadSeam` | research → read | `InsightNodeContract` ref (`insight_node` id) | DRW SPR-01 (promote insight) | Read corpus / living-note surface | committed |
| `ReadToResearchSeam` | read → research | `document_region` ref (a `DocumentRegionSelected` anchor) | **Read SPR-08** (research-from-passage) | DRW SPR-05 (cascade planner seed) | committed |
| `ReadToWriteSeam` | read → write | `InsightNodeContract` ref → `OutlineBlockContract` (`graph_node`) | Read (drag from folders) | **Write SPR-03** (block repository / folders) | committed |
| `WriteToReadSeam` | write → read | `OutlineBlockContract` ref → resolved source span | **Write SPR-07** (trace-to-source) | shared reading surface (DRW SPR-10 / Read SPR-03 reader) | committed |
| `SpeakToWriteSeam` | speak → write | `speak_claim` ref → `OutlineBlockContract` (`synthesized`) | **Speak SPR-08** (biography authoring) | Write SPR-01 (OutlineComposer) | committed |
| `SpeakToReadSeam` | speak → read | `ServableEntryContract` ref (`platform_authored` + `speak_derived`) | **Speak SPR-09** (publishing) | Read servable corpus (seam #4 gate) | committed |
| `WriteToSpeakSeam` | write → speak | `question_node` ref (an outline gap's open question) | Write outline commission endpoint | Speak reference-resolving interview guide | committed |

### `WriteToSpeakSeam` is committed

The stated promotion criterion is satisfied: the operator explicitly wants
Write gaps to commission Speak research, and both product sides now exist. The
Write endpoint validates a node-backed open question and creates one private
Speak project with a reference-only guide. Speak resolves that node into the
live must-cover question at interview time. The no-copy guard is load-bearing.

## Implementing-sprint citation audit (diligence — verified against the real spec pages)

| Seam | Verified against spec page | What the page actually says |
|---|---|---|
| read→research | `specs/read/sprint-08-research-from-passage.html` | "the cross-workflow seam between Read and Research"; select a section → pre-seed DRW SPR-05's cascade planner with passage + book context; "completed research links back to the originating passage (two-way provenance)"; gated book → "seed carries only metadata/snippet". |
| read→write | `specs/write/sprint-03-block-repository-folders.html` | block repository / folders — dragging insight/question/claim **graph nodes** into outlines (node-backed blocks, provenance resolvable). |
| write→read | `specs/write/sprint-07-trace-to-source.html` | "open its source-of-truth document in the shared reading surface … highlights … rabbit holes"; "reuses the shared reading surface (DRW SPR-10 / Read SPR-03)"; "respect Read's servability gate — gated book shows metadata/snippet, never bypassing the corpus gate"; "builds no reader of its own". |
| speak→write | `specs/speak/sprint-08-biography-authoring.html` + `substrate/speak/write_composer.py` | "outline via Write … Write SPR-01 (OutlineBlock) + SPR-06 (generation)"; the live composer maps a **speak_claim** (not a graph node) to a **`synthesized`** outline block carrying `source_block_id = claim_id` — promoting to a shared node is operator-gated G2/G3. |
| speak→read | `specs/speak/sprint-08-biography-authoring.html` (`substrate/speak/publish_gate.py`) + `substrate/speak/publish.py` | publishing reuses Read's servable corpus as `platform_authored`, "only after passing every SPR-01 gate (consent + verification + subject consent + G2/G3)". |

## The voice single-owner note (collision #2)

The voice capture→ASR→distill pipeline has **one owner**: `acquisition/voice/`
(`WhisperTranscriber`, `webrtc.py`, `ingest_voice_note()`). Read SPR-06 and
Speak SPR-02 both **call** it.

- **Read SPR-06's "reusable service" framing is demoted to "calls the existing
  service."** Verified: `specs/read/sprint-06-voice-notes.html` says "build the
  capture→ASR→distill pipeline as a reusable service, not a Read-only one" —
  phrasing that invites a second owner. The master spec and
  `docs/decisions/tech-stack-ledger.md` close this: `acquisition/voice/` is the
  sole owner; Read SPR-06 calls it and builds no parallel pipeline.
- Verified: `specs/speak/sprint-02-async-voice-interview.html` already says
  "Reuse `ingest_voice_note()`" and "the net-new part is the async session
  lifecycle, not a second interview engine." Speak SPR-02 is already correct.

The greppable invariant: exactly one `def ingest_voice_note` (in
`acquisition/voice/adapter.py`), and it is the only producer of
`document_type='voice_note'` documents
(`tests/test_seam_voice_single_owner.py`).

## The reading-surface ownership note (collision #1)

`ReaderSurfaceContract` (SPR-01, **provisional** — DRW SPR-10 unbuilt) is the
single composition surface. **DRW SPR-10 owns** it; **Read SPR-03 specializes by
composition** and **Write SPR-07 traces into it** via the same contract;
**neither forks** a second reading surface. Until DRW SPR-10 lands, Read/Write
compose against the conformance-tested stub
(`tests/test_seam_reader_surface_contract.py`).

## What this package is NOT

Seam contracts + the two collision-fix adapters only. No product internals — it
does not build Read's `serve.py`, Write's editor, Speak's interviewer, or DRW's
reading surface. The real implementations live in the product sprints; these are
the handoff shapes those sprints implement and the collision invariants a guard
test enforces. Implementing a product's side here would be the duplication the
master spec's "integration, not duplication" rule forbids.
