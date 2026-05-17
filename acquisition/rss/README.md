# acquisition/rss/

RSS feed ingestion via the blogwatcher pattern. Per-theme feed lists
drive what gets pulled at the daily heartbeat.

## Discipline

Feed entries are deduplicated by GUID. Re-fetching an unchanged entry
is idempotent — same content hash, same chunk IDs, no duplicate
downstream work.

## Output

Emits `ingest_chunk` events with payload metadata:
- `source_uri` — entry permalink
- `feed_uri` — source feed URL
- `guid`, `published_at`, `title`, `author`
- `content_hash`
