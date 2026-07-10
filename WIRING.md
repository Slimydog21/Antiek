# WIRING.md — book-import SPR-01/SPR-02 honest boundary map

Branch: `bi/book-import-spr01-02` (based on campaign branch @ `ccfd2b1f6`).
This file records, per the spec's grounded corrections, every place where the
new security floor / conversion engine is NOT yet wired into an existing code
path — and exactly where the wire goes when the owning path lands or is
touched by its owner. Nothing here is a receipt: each entry names a concrete
call site and the one-line change it needs.

## Grounded finding (verified on this branch)

- The #496 `book_html_publish_job` — the stored-XSS site the parent spec
  (`~/Antiek/specs/antiek-book-import-real-port/`) targets — is **not on this
  branch**. `grep -rn "book_html_publish_job\|html_body" interfaces/ substrate/`
  finds no books publish job — the only `html_body` on the branch is the auth
  email provider's field (`substrate/auth/email_provider.py`), unrelated. The
  publish job exists only in unmerged legacy PRs.
- Consequently there is **no client-HTML write path into `documents` today**:
  the native books path (`acquisition/books/adapter.ingest_pdf`) stores
  *markdown* extracted from PDFs, not HTML. SPR-01 therefore ships the
  ADDITIVE floor (`substrate/books/html_sanitizer.py`) and SPR-02
  (`substrate/book_import/`) is its **first real consumer** — a genuine
  sanitize-on-write path, not a retrofit.

## SPR-01 wiring points (sanitize-on-write + trusted-HTML contract)

### W1 — the future `book_html_publish_job` (#496, when it lands)

The publish job's `insert_document(..., raw_text=req.html_body, ...)` must
become:

```python
from substrate.books.html_sanitizer import sanitize_book_html, sanitized_html_provenance

body = sanitize_book_html(req.html_body)
insert_document(..., raw_text=body, metadata={**existing_md, **sanitized_html_provenance()}, ...)
```

Owner: whichever lane merges the #496 lineage. Do NOT re-open that PR from
this branch; the sanitizer is here waiting for it.

### W2 — serve-side trusted-HTML enforcement (`substrate/books/serve.py`)

`serve_full_text` returns `full_text=raw_text` verbatim on the servable and
owner-personal-reading branches (`substrate/books/serve.py:158-162` and
`:174-178`). Today every stored book body is markdown/plain text and the
Reader paginates it as TEXT (`apps/reading` uses `paginate()`, no
`dangerouslySetInnerHTML`), so there is no live XSS on this branch. The
moment any serve surface renders a stored body AS HTML, the gate must be:

```python
from substrate.books.html_sanitizer import is_trusted_sanitized

# in the SELECT: also fetch d.metadata
# before returning full_text as HTML:
if not is_trusted_sanitized(metadata):
    # serve as plain text / bounded snippet — NEVER as HTML
```

Not wired now because (a) `serve.py` is a read path, not a write path — the
correction authorizes only a write-path wiring diff; (b) wiring it today
would change the serve contract for every existing markdown book (none of
which carry the bit) without any HTML renderer existing to protect. The
predicate is deliberately shaped so this is a two-line enforcement when the
HTML render lands. `substrate.book_import.publish.publish_converted_book`
already stamps the bit on every row it writes, so rows are ready for the
gate before the gate exists (sanitize-on-write makes the stored bytes safe
for every consumer either way).

### W3 — `acquisition/snapshot/reader_html.py` is a regex denylist (known-weak)

`sanitize_html_fragment` strips only paired `<script>`/`<style>` via regex:
`onerror=` handlers, `javascript:` hrefs, `<iframe>` all pass it into the
snapshot HTML written to `~/.antiek/reader-snapshots/*.html`. The upgrade is
one line — delegate to the allowlist floor:

```python
def sanitize_html_fragment(raw: str, *, max_chars: int = 200_000) -> str:
    return sanitize_book_html(raw[:max_chars])
```

Not done in this lane: the function is shared by the URL-ingest snapshot path
(outside `substrate/books/`), has its own test file
(`tests/test_reader_snapshot.py`) asserting current behaviour, and is owned
by the acquisition snapshot lane. Flagged here as a real, live weakness of a
disk-artifact path (operator-opened HTML files), not of the substrate.

### W4 — talk-to-book grounding

`substrate/books/book_qa.py` grounds on `chunks.text` via the §9.0-gated
`substrate.graph.search.search`. Chunks written by
`substrate.book_import.publish` come from the sanitized markdown projection,
so script bodies can never reach a prompt from an imported book (verified by
`test_book_import_convert.py::test_hostile_epub_chunks_carry_no_script`).
Chunks from OTHER ingest paths inherit those paths' guarantees — out of this
lane's scope.

## SPR-02 wiring points (epub → Antiek-HTML engine)

### W5 — the import-funnel endpoints (#490/#492/#493, when they land)

The receipt-only stubs (`/books/import/html-preflight`, `/conversion-review`,
`/conversion-result`) are NOT on this branch either. When that lineage lands,
the real job behind `/books/import/conversion-job` is a thin composition that
already exists here:

```python
from substrate.book_import import convert_epub_to_antiek_html, publish_converted_book

converted = convert_epub_to_antiek_html(operator_file_path)   # typed failures
published = publish_converted_book(con, converted, investigation_id=..., content_class=<operator-declared>)
```

Keep the operator-file boundary: the converter takes a LOCAL path/bytes, never
a URL fetch.

### W6 — `document.loaded` event: no `epub` media_type in the schema

`DocumentLoadedPayload.media_type` is a closed Literal
(`"pdf" | "pasted_text" | "url_extracted" | "markdown"`,
`substrate/schemas/events.py:1003`). Emitting the reading-surface load signal
for an epub import honestly requires adding `"epub"` to that Literal —
a schema change owned by the events-schema lane, not made here. Until then
`publish_converted_book` emits no `document.loaded` event (the
`book.servability_changed` audit event from `register_book` still fires when
registration moves the class). Lying with `media_type="markdown"` was
considered and rejected.

### W7 — PDF conversion is NOT implemented

SPR-02's spec text names pdf/docx too, backed by the `file-ingest`/markitdown
skill. That skill is a Claude-Code skill on the operator's machine, not a
repo dependency; `pypdf`/`pdfplumber` are optional extras (`[pdf]`) not in
core deps. This lane ships the epub engine only (epub = zip of XHTML, fully
parseable with stdlib — no new dependency). A PDF arm belongs behind the same
`ConvertedBook` contract; the honest entry point is a new
`substrate/book_import/pdf.py` gated on the `[pdf]` extra, mirroring
`acquisition/books/reader.read_pdf` which already exists for native ingest.
A scanned/no-text-layer PDF must map to the existing typed failure
`NoTextContentError` (`substrate/book_import/errors.py`).

### W8 — embeddings at publish time

`publish_converted_book(..., embedder=None)` writes chunks WITHOUT embeddings
by default (same posture as `substrate/research_bridge/ingest.py`); callers
that want immediate vector retrieval pass an embedder (the API surface passes
`processing.embedding.default_embedding_provider()`, exactly as
`acquisition/books/adapter.ingest_pdf` does). Retrieval-gate parity with an
embedder is proven in the test suite with the stub embedding model.
