# Decision: PDF→HTML pypdf fallback for reader-HTML sidecars

**Date**: 2026-09-19 (Asia/Riyadh)
**Status**: accepted
**Cite**: `acquisition/doc_to_html/converter.py`; `acquisition/books/reader.read_pdf`;
`store_reader_html`; HTML-native residual (PDF→HTML coverage).

## Context

Upload/URL ingest converted via anydoc → docling only. Empty CLI stdout was
treated as success; hosts without working CLIs (or text PDFs that anydoc
blanked) never reached the in-process pypdf path already used by books ingest,
so `document_reader_html` sidecars were missing for common PDF uploads.

## Decision

1. Treat whitespace-only anydoc/docling output as failure.
2. For PDF paths (`fmt=pdf` or `.pdf` suffix), fall back to
   `acquisition.books.reader.read_pdf` (text layer only — no OCR claim).
3. Stamp `converter_engine` (`anydoc`|`docling`|`pypdf`) on document metadata.
4. Refuse empty sanitized HTML before `store_reader_html`.

## Non-goals

- OCR for scanned/image-only PDFs — shipped in pdf-ocr-html-2026-09-19.
- Replacing anydoc/docling when they produce real markdown.
- EPUB/DOCX pypdf (PDF-only arm).

## Consequences

PDF uploads more reliably produce sanitized reader-HTML sidecars. Dual
structure unchanged (DuckDB SoT + `document_reader_html`). Next: composite
100 rollup or OCR lane if needed.
