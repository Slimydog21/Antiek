# processing/

Source-agnostic. The same chunking, embedding, and extraction logic
runs on arXiv papers, open-access books, fetched URLs, captured
interviews, and YouTube transcripts. The processing layer does not
care where content came from; it cares about the shape of the content.

## Modules

- **`chunking/`** — Content-addressed chunking. Chunk IDs are derived
  from content hash, so re-ingesting the same source produces the same
  chunk IDs and does not duplicate downstream work.
- **`embedding/`** — Vector embedding generation. Embeddings feed the
  cross-domain connector (which finds links via actual proximity, not
  LLM imagination — see architecture_notes §4).
- **`extraction/`** — LLM-structured node and edge extraction. Outputs
  conform to the schemas in `substrate/schemas/`. Bulk work; routes
  through Flash-tier models in the dispatch router.
- **`note_taking/`** — Per-page or per-chunk note generation. Highest
  token-volume role in the system; deliberately routed to Flash-tier
  models to keep cost manageable.
- **`distillation/`** — Consolidated document generation. Takes
  ingested + extracted material and produces longer-form distillations
  suitable for downstream synthesis.

## Cost discipline

This is the layer where token-volume management matters most.
Note-taking and extraction dominate ingestion-phase spend. Routing
these correctly through Flash-tier models is what makes the rental
path economically viable — see architecture_notes §2.5 for the
Pro/Flash split.
