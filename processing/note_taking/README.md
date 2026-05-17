# processing/note_taking/

Per-page or per-chunk note generation. The highest token-volume role
in the system; deliberately routed to Flash-tier models in
`substrate/dispatch/`.

## Purpose

Notes are short, structured per-chunk summaries that feed:

- Faster downstream retrieval (the retriever can read notes before
  loading full chunks).
- The cross-domain connector (notes are denser than raw text).
- Distillation passes (`processing/distillation/`).

## Discipline

Notes are schema-constrained: each note has a `chunk_id`, a
`note_text`, a list of extracted `themes`, and a list of `entities`.
No free-form output. See `substrate/schemas/`.
