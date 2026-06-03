# ASR SR-05: adapter migration to register_source_document

**Date:** 2026-06-02  
**Sprint:** SR-05  
**Depends on:** SR-04 (P1 chokepoint on `caffen/SR-04`)

## Decision

Every acquisition adapter in `register_check`'s former P1b allowlist now calls
`register_source_document` immediately after `insert_document` in the same
`connect_write` transaction, with an explicit `content_class` whenever the row
is not the academic NULL→gated path.

| Adapter | `SourceKind` | `content_class` at register |
|---------|--------------|-----------------------------|
| `arxiv/adapter.py` (`ingest_paper`) | `ACADEMIC_PREPRINT` | omitted → gated floor |
| `interview/adapter.py` | `USER_CONTENT` | omitted → gated floor |
| `voice/adapter.py` | `USER_CONTENT` | omitted → gated floor |
| `podcasts/adapter.py` | `WEB` | `PERSONAL_READING_CONTENT_CLASS` |
| `twitter/adapter.py` | `USER_CONTENT` | caller `content_class` (default personal lane) |
| `urls/adapter.py` | `WEB` | `PERSONAL_READING_CONTENT_CLASS` |
| `youtube/adapter.py` | `WEB` | `resolved_content_class` |
| `substack/adapter.py` | `WEB` | `PERSONAL_READING_CONTENT_CLASS` (fresh rows only) |

`tools/lint/register_check.py` `_MIGRATION_PENDING` is now empty.

## Invariants preserved

- `insert_document` third-party guard unchanged (dual path per `asr-p1-write-home.md`).
- Substack idempotent skip: register runs only when `already_present` is false.
- No weakening of `retrieval_gate_check` or `serve_guard_check`.

## Verification

- `python tools/lint/register_check.py` → exit 0
- `pytest` acquisition + `test_register_source` cluster