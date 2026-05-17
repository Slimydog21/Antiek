# acquisition/youtube/

YouTube transcript ingestion. Talks, lectures, conference recordings,
podcast video.

## Source

Auto-captions when available; commercial ASR (Whisper API or
equivalent) as fallback. Audio is not stored beyond the transcription
step unless explicitly flagged.

## Output

Emits `ingest_chunk` events with payload metadata:
- `source_uri` — YouTube URL
- `video_id`, `channel`, `published_at`, `duration_seconds`
- `transcript_source` — `auto_captions` or `asr`
- `content_hash`
