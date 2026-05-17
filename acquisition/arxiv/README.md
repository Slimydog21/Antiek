# acquisition/arxiv/

arXiv paper ingestion.

Uses the arXiv API for metadata and the bulk PDF mirror for full text.
Per-theme tracking lists drive what gets ingested daily (heartbeat
behavior; see `orchestration/heartbeat/`).

## Output

Emits `ingest_chunk` events with payload metadata:
- `source_uri` — arxiv.org abs URL
- `arxiv_id` — canonical paper ID
- `version` — paper revision number
- `themes` — list of theme tags that matched this paper
- `content_hash` — SHA-256 of the PDF bytes

PDFs land in the chunking pipeline (`processing/chunking/`) regardless
of which path acquired them.
