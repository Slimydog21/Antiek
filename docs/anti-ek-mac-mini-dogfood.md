# Anti-Ek Mac Mini dogfood (shared DuckDB + isolated events)

## Why

The personal library lives in `~/.antiek/research_graph.duckdb` (~GB-scale
event history can hang a fresh worktree if events are shared). Boot the API
with:

- **Shared DuckDB** — `ANTIEK_DUCKDB_PATH=$HOME/.antiek/research_graph.duckdb`
  so Library / books / uploads persist across worktrees.
- **Isolated events** — `ANTIEK_RESEARCH_EVENTS_DIR=<worktree>/.antiek-home/research_events_isolated`
  plus `ANTIEK_DISABLE_EVENT_PROJECTOR_RECOVERY=1` so a 2GB event log does not
  block boot.

## Start

```bash
./scripts/start-shared-duckdb-mac-mini.sh
```

Script defaults target the `anti-ek-use-main-*` worktree and
`/Users/slimydog/Antiek/platform/.env` (never commit that file). Vite on
`:5173` is reused if already listening; API on `:8000` is restarted carefully.

## Owned upload → BookReader vertical slice

1. Open `http://127.0.0.1:5173/sources`.
2. Upload a file you authored; choose **I authored this (notes / drafts)**
   (`user_owned`) and confirm.
3. **Open in reader** → `/read/:id` (BookReader). Uploads now register a
   `book_assets` row so `GET /books/{id}` resolves (previously 404 while
   reader-html alone worked).
4. Highlight a passage → Research this → spin-research → notebook with
   citations.

`personal_reading` uploads also bind into BookReader metadata, but full text
stays owner-only (gated snippet on the public path). Use `user_owned` for the
polished local dogfood path when auth is not enforcing an operator session.

## Curl smoke (user_owned)

```bash
curl -sS -F "file=@note.html;type=text/html" \
  -F "acquisition_attestation=user_owned" \
  -F "title=Dogfood Note" \
  http://127.0.0.1:8000/sources/upload
# → document_id
curl -sS "http://127.0.0.1:8000/books/\$DOC_ID"
curl -sS "http://127.0.0.1:8000/books/\$DOC_ID/full-text"
curl -sS -X POST "http://127.0.0.1:8000/books/\$DOC_ID/spin-research" \
  -H "content-type: application/json" \
  -d page_index:0
```
