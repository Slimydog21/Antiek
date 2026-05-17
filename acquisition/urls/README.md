# acquisition/urls/

General URL fetch and content extraction. The catch-all for sources
that don't have a dedicated path.

## Two modes

- **Static fetch** — for server-rendered pages. Raw HTTP via the
  dispatch HTTP client; readability extraction via the standard
  content-extraction library.
- **Rendered fetch** — for JS-heavy pages. Routes through the Chrome
  MCP path so JavaScript executes before content extraction.

## Output

Emits `ingest_chunk` events with payload metadata:
- `source_uri` — full URL
- `fetched_at` — retrieval timestamp
- `render_mode` — `static` or `rendered`
- `title`, `byline`, `published_at` (where extractable)
- `content_hash` — SHA-256 of the extracted text
