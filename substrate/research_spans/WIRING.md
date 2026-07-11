# WIRING.md — Frozen-file adoption sites for SPR-03

SPR-03 is **additive new-files-only** inside its owned seam
(`substrate/research_spans/`).  This document names the frozen
research-loop call sites that **should adopt** the span-based
assembler when SPR-03's seam is wired into the production loop.
Each entry names the exact file, function, and line — no guessing.

---

## 1. Orchestrator Phase 6 — synthesis evidence block

**File:** `orchestration/loop_one/orchestrator.py`
**Function:** `_run_phase_6` (line ~994)
**What it does today:** Serializes `ctx.evidence` (a list of
`EvidenceRetrieveDeliveredPayload`) into `evidence_block` as JSON
(text, line ~1013).  The synthesizer prompt receives this as a raw
string block.

**What SPR-03 wiring would do:** Before Phase 6 dispatch, convert
the evidence payloads into `ExtractiveSpan` instances (using the
chunk text, chunk_id, document_id from the
`EvidenceRetrieveDeliveredPayload.supporting_claims`).  Run
create and park a `DocumentRecord`, then call `extract_select` with
the tier-derived budget.  Pass its `SelectionResult` to
`assemble_or_refuse`, which applies the retrieval floor and assembles
only the canonically budgeted spans.  Use the resulting
`AssembledContext.text` as the evidence block instead of raw JSON.

**Why:** The synthesizer currently sees arbitrary JSON; the span
boundary ensures it sees only verbatim, attributed, budgeted
extractive content.

---

## 2. Cascade session — SessionEvidencePack → synthesis tail

**File:** `orchestration/cascade_session.py`
**Function:** `CascadeSession.run_synthesis_tail` (line ~385)
**What it does today:** Calls `run_synthesis_tail_from_pack(pack,
broadcaster, coordinator)` which converts `SessionEvidencePack`
chunks into `InvestigationContext.evidence` via
`_investigation_context_from_pack` (orchestrator.py line ~1494).

**What SPR-03 wiring would do:** In
`_investigation_context_from_pack`, convert `PackChunk` instances
into parked `DocumentRecord` instances, then run `extract_select` +
`assemble_or_refuse`.  Feed the assembled text into the synthesis
evidence block, or handle `Requery` / `InsufficientSources` without
dispatching synthesis.

**Why:** The cascade path is the second entry point into synthesis;
it must go through the same span boundary as the single-investigation
path.

---

## 3. Orchestrator Path A — `_investigation_context_from_pack`

**File:** `orchestration/loop_one/orchestrator.py`
**Function:** `_investigation_context_from_pack` (line ~1494)
**What it does today:** Builds `InvestigationContext` from
`SessionEvidencePack`, converting chunks to evidence payloads.

**What SPR-03 wiring would do:** Convert pack chunks into parked
documents, then use `extract_select` and `assemble_or_refuse`.
Replace raw chunk serialization with the successful
`AssembledContext.text`; preserve the returned floor trace on every
outcome.

**Why:** Same as #2 — this is the concrete function that bridges
the pack to the synthesis context.

---

## 4. Evidence retriever — chunks_block rendering

**File:** `orchestration/loop_one/orchestrator.py`
**Function:** `_render_chunks_block_for_sub_question` (line ~290)
**What it does today:** Renders chunks from the graph DB into a
text block for the evidence retriever role.  Each chunk is rendered
with `[chunk_id]` header, source tier, similarity score.

**What SPR-03 wiring would do:** Construct `ExtractiveSpan`
instances from the chunk text + offsets (the graph search returns
the full chunk text; the span is the full chunk).  Run
`extract_select` to extract and budget spans from the parked source.
Send the `SelectionResult` through `assemble_or_refuse`. The lower-level
assembler is private and absent from the package export surface, so a product
caller cannot bypass the retrieval floor or budget binding by convention.

**Why:** The evidence retriever's input quality directly affects
synthesis quality.  Span selection + floor gating improves the
signal-to-noise of what the retriever sees.

---

## 5. Context pack assembler — graph_evidence layer

**File:** `substrate/context_pack/assembler.py`
**Function:** `assemble_context_pack` (line ~390)
**What it does today:** Accepts `LayerSource` instances and
assembles them into a prompt.  The `graph_evidence` layer kind
carries retrieved facts as raw text.

**What SPR-03 wiring would do:** For `graph_evidence` layers
sourced from research retrieval, park source documents and use the
`extract_select` + `assemble_or_refuse` boundary to render them with
attribution.
The existing `LayerSource` API is preserved; the span assembly is
an internal improvement to the evidence layer's content quality.

**Why:** The context pack is the third place where retrieved
content surfaces.  Consistent span discipline across all three
paths (direct synthesis, cascade synthesis, context pack) prevents
gaps where raw content leaks through.

---

## Non-goals (things this WIRING.md does NOT change)

- **No edits to frozen files.** All entries above are adoption
  guidance for a future wiring sprint — SPR-03 itself only creates
  the new `substrate/research_spans/` package.
- **No provider changes.** The dispatch router, provider registry,
  and config.yaml are untouched.
- **No UI/API changes.** The React app, API routes, and PR #712
  surfaces are out of scope.
- **No citation rendering.** SPR-04 owns the citation binder; the
  attribution shape here is the binding surface.
