# SessionEvidencePack contract

**Date:** 2026-06-12
**Source spec:** ANT-DRL SPR-DRL-05
**Status:** Ratified at implementation

## Problem

Path A convergence needs a stable, typed handoff between DRW gather (cascade
merge) and Loop 1 phases 6–9. Raw ``StepEvent`` multiplex streams are the
wrong shape for the synthesizer constraint loop.

## Contract

``SessionEvidencePack`` (schema version 1) carries:

- ``session_id`` — parent investigation id (synthesis tail target)
- ``problem_question`` — plan root question
- ``chunks[]`` — each with ``chunk_id``, ``document_id``, ``ip_holder_id``
  (nullable), ``text``, ``source_investigation_id``, ``sub_question``
- ``documents[]`` — each chunk's document with matching ``ip_holder_id``
- ``leaf_investigation_ids`` — gather-only children
- ``content_hash`` — SHA-256 over canonical body (immutable artifact)

Empty pack is valid; it cannot satisfy ``DeepResearchComplete``.

Implementation: ``orchestration/session_evidence_pack.py``;
builder: ``build_session_evidence_pack`` / ``CascadeSession.build_evidence_pack``.

## Rejected alternative

**Pipe JSONL StepEvents into synthesizer** — rejected. The constraint loop
expects typed evidence + parameter artifacts, not a live step stream.

## Reconsider if

Exa adapter emits real document chunks — pack schema version bumps; builder
fills ``documents`` from substrate rows instead of provisional ``doc-gather-*``
ids.