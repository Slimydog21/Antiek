# acquisition/twitter/

X/Twitter ingestion. Used primarily for subject tracking — when a
tracked subject posts, the heartbeat orchestrator checks whether their
tier classification should be re-evaluated (architecture_notes §3.3,
external-event-triggered behaviors).

## Source tier

Twitter content lands at `social_media` tier by default. Specific
verified-account threads may be promoted manually but the LLM cannot
adjust upward.

## Output

Emits `ingest_chunk` events with payload metadata:
- `source_uri` — tweet URL
- `tweet_id`, `author_handle`, `author_verified`, `posted_at`
- `reply_to`, `quote_of` — for thread reconstruction
- `content_hash`
