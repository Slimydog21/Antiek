# acquisition/books/

Book ingestion via open-access libraries: Project Gutenberg, Internet
Archive (where licensed), OpenBooks, institutional repositories.

## Discipline

Only sources where the license permits research-pipeline ingestion.
Commercial e-book formats and DRM-locked sources are explicitly out
of scope.

## Output

Emits `ingest_chunk` events with payload metadata:
- `source_uri` — provider URL or local archive path
- `title`, `author`, `publication_year`
- `isbn` (when available)
- `license` — Public Domain, CC BY, etc.
- `content_hash` — SHA-256 of the canonical text
