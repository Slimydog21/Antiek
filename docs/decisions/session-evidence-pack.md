# SessionEvidencePack contract

**Date:** 2026-06-12
**Source spec:** ANT-DRL SPR-DRL-05
**Status:** Ratified at implementation

## Problem

Path A convergence needs a stable, typed handoff between DRW gather (cascade
merge) and Loop 1 phases 6–9. Raw ``StepEvent`` multiplex streams are the
wrong shape for the synthesizer constraint loop.

## Contract

``SessionEvidencePack`` (schema version 2; see the second amendment) carries:

- ``session_id`` — parent investigation id (synthesis tail target)
- ``problem_question`` — plan root question
- ``chunks[]`` — each with ``chunk_id``, ``document_id``, ``ip_holder_id``
  (nullable), ``text`` (the chunk's substrate text), ``note`` (nullable),
  ``source_investigation_id``, ``sub_question``
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

A stub-only gather now yields an empty pack, and the tail enforces the
Contract line above: `run_synthesis_tail_from_pack` in
`orchestration/loop_one/orchestrator.py` checks `pack.chunks` before phase 6,
and on an empty pack emits `investigation.failed` (phase 6, reason naming the
empty substrate-grounded evidence pack) and returns. No synthesis call is made,
no `investigation.completed` is written, and DeepResearchComplete stays false.
The check is scoped to the pack tail; the ordinary Loop 1 Ask path keeps its
own `insufficient_evidence` completion.

## Amendment — the chunk's text, not the note (2026-09-24, audit wave 5 provenance)

After the first amendment a pack chunk cited a real chunk but carried the
insight node's label as `text`. A forged remote note ("the moon is made of
green cheese") naming a real document was grounded by the funnel on that
document's chunk, and the tail handed it to the synthesizer as a `direct`
claim citing a chunk that says something else.

`text` is now the cited chunk's own substrate text, read from the `chunks`
row. The gather note moves to a separate `note` field and is set only when
that chunk supports it: the note clears the groundedness bar against the one
chunk and every word of the note, stopwords included, occurs in it. The bar
alone admits a note that is half source words and half invention, or flips
meaning through a stopword the scorer ignores. `PackChunk` re-checks this on
construction, so no pack can carry an unsupported note. The tail presents the
chunk excerpt as `direct` evidence and a supported note as `inferred`, beside
the source text. A stored `groundedness_score` is never read. The field
meaning changed, so `schema_version` is 2 and a v1 pack is refused.

Reconsider if: the lexical bar is replaced by an entailment verifier, at which
point a supported note could be presented as `direct`. A note built only by
recombining its chunk's own words still passes the word check; that residue
is why the note is typed `inferred` and never shown without its source.
