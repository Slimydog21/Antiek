# acquisition/gmail/

Gmail ingestion. Subscribed research newsletters, paper alerts,
correspondence with subjects.

## Discipline

OAuth scope is read-only. The pipeline never sends mail. Sensitive
correspondence is filtered before reaching the graph; see the
classifier in this module's `filters.py` (planned).

## Output

Emits `ingest_chunk` events with payload metadata:
- `message_id` — Gmail message ID
- `from`, `to`, `subject`, `received_at`
- `labels` — Gmail labels at ingestion time
- `content_hash`
