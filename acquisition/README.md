# acquisition/

Source-specific ingestion. Each source has different mechanics —
arXiv exposes an API, books arrive as PDFs from open-access libraries,
URLs need fetching and content extraction, interviews require ASR and
diarization, X/Twitter has its own API, RSS uses standard feed parsing.

The acquisition layer is path-specific by design. Everything downstream
(chunking, embedding, extraction) is uniform across paths and lives in
`processing/`.

## Paths

- **`arxiv/`** — arXiv paper ingestion (API + PDF download).
- **`books/`** — Open-access book sources (Project Gutenberg, OpenBooks,
  Internet Archive where licensed).
- **`urls/`** — General URL fetch and content extraction. Use the
  Chrome MCP path for JS-heavy sites; raw fetch for the rest.
- **`twitter/`** — X/Twitter ingestion (subject tracking).
- **`gmail/`** — Gmail ingestion (subscribed newsletters, research
  correspondence).
- **`youtube/`** — YouTube transcript ingestion.
- **`rss/`** — RSS feed ingestion via the blogwatcher pattern.
- **`interview/`** — Interview capture (DeepBlu lineage). Voice + text.
  Uses commercial ASR (Whisper API equivalent) and commercial
  diarization for multi-party interviews. Do not roll our own.

## Contract

Every acquisition path emits a stream of `ingest_chunk` events into the
substrate event log with consistent metadata: source URI, retrieval
timestamp, content hash, raw payload reference. Downstream processing
does not need to know which path produced the event.
