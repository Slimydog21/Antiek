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
  (nullable), ``text`` (the chunk's substrate text; the generated note is not
  carried), ``source_investigation_id``, ``sub_question``
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
row, and it is the only text a pack chunk carries. The generated note is not
in the pack. A first version of this fix kept the note in a `note` field when
it cleared the lexical groundedness bar and every one of its words occurred in
the chunk. That check treats words as an unordered set: against "Alpha
acquired Beta for cash." it scored "Beta acquired Alpha for cash." 1.0, and it
passed figures reassigned between years. Presenting a note as a supporting
claim needs evidence that the chunk entails it, and this path has none (the
offline NLI backend in `substrate/eval/groundedness/nli_backend.py` is not
wired here and hard-stops when its model is not cached). So every supporting
claim the tail builds is a verbatim excerpt of the chunk it cites, typed
`direct`. `PackChunk` forbids extra fields, so a pack carrying a `note` is
refused. Without the note, two notes of one leaf citing the same chunk would
repeat one excerpt, so the builder keeps one chunk per (leaf, chunk). A stored
`groundedness_score` is never read. The field meaning changed, so
`schema_version` is 2 and a v1 pack is refused.

The funnel still cites the substantive chunk that best supports a note
lexically, not the longest chunk. That picks which excerpt the pack quotes; it
does not certify the note.

Reconsider if: an entailment verifier that fails closed is wired onto this
path. A note it accepts could then ride beside its source excerpt, typed
`inferred`.

## Amendment — the whole chunk reaches the synthesizer (2026-09-24, audit wave 5 provenance, round 2)

The tail built each answer and each supporting claim from the first 500
characters of the chunk. A source whose measurement followed its introduction
lost the measurement on the way to the synthesizer, while the sub-question
still reported `insufficient_evidence=false` with no evidentiary gap.

`_investigation_context_from_pack` now passes every chunk's full text. The one
bound is the synthesizer's context window: `context_budget_tokens` less
`max_tokens` of the dispatch tier the `synthesizer` role runs on, of which the
evidence block may use half, at three characters per token, with each shown
character counted twice because it appears in the answer and in its claim. For
the production `synthesis` tier that is 179,712 characters of chunk text, about
45 of the funnel's largest (4,000-character) citable chunks. When the pack
exceeds it, the budget is split max-min fairly so only the longest chunks are
cut, each cut backs off to a word boundary so no figure is split, and every
truncated or omitted chunk gets an `evidentiary_gaps` entry naming the chunk,
its document, the characters shown and the characters dropped. The claim's
`confidence_basis` and an inline marker in the answer say the same. A
sub-question left with no shown chunk is `insufficient_evidence`.

Reconsider if: the operator's AI Role Lineup routes the synthesizer onto a
model whose window is smaller than the tier's declared `context_budget_tokens`.
The budget reads the tier, not the lineup override, so it would then overstate
the room; the fix is a per-model window on the lineup entry.
