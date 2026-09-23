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

## Amendment — no provisional ids (2026-09-23, audit wave 5 W03)

The reconsider-if condition above has been met: the Exa loop ingests real
documents, and production runs it. The builder no longer mints provisional
ids. A pack chunk is admitted only when the insight node's `chunk_id` resolves
to a `chunks` row whose document exists in `documents`; the pack's
`document_id`, `ip_holder_id` and title are read from those rows, never from
node metadata. A node with no such chunk (the contract stub's placeholder
note, an Exa "no servable source" note) is left out of the pack.

Before this, the builder invented `chunk-<node_id>` / `doc-gather-*` ids and
matching documents, so the pack satisfied its own provenance validator by
construction, the tail turned the stub's placeholder note into a "direct"
supporting claim, and a `proceed` synthesis citing a chunk that exists nowhere
reached DeepResearchComplete. The field shape is unchanged, so
`schema_version` stays 1.

A stub-only gather now yields an empty pack, and the tail answers with
`insufficient_evidence`. Whether an `insufficient_evidence` session should
count as DeepResearchComplete (the Contract line above says an empty pack
cannot) is an open operator decision; the tail's empty-pack path in
`orchestration/loop_one/orchestrator.py` still completes it.

