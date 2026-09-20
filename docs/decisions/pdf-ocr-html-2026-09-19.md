# Decision: OCR scanned PDF→HTML for reader sidecars

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** #3186 / `pdf-html-pypdf-fallback-2026-09-19.md`;
`acquisition/doc_to_html/converter.py`; `store_reader_html`.

## Context

#3186 shipped text-layer pypdf after empty anydoc/docling. Scanned / image-only
PDFs still produced no `document_reader_html` sidecar. Mini already has
Homebrew `tesseract`, `ocrmypdf`, and `pdftoppm`; DeepSeek-OCR-2
(`substrate.research_bridge.ocr`) is a separate VLM service and was **not**
reachable at ship time (`ocr_available=False`).

## Decision

1. After pypdf returns empty **or thin** (`word_count` <
   `ANTIEK_PYPDF_THIN_WORDS`, default 15), try local OCR:
   - Prefer **`ocrmypdf --force-ocr --output-type none --sidecar`**
   - Else **`pdftoppm` + `tesseract`** per page (capped by
     `ANTIEK_PDF_OCR_MAX_PAGES`, default 40)
2. Stamp `converter_engine` as `ocrmypdf` or `tesseract`.
3. Refuse empty OCR output (same as other engines) before `store_reader_html`.
4. Gate with `ANTIEK_PDF_OCR` (default on) and binary presence — **no fake OCR**.
   When tools are missing, `ConversionError` names the deferred install path.

## Install (Mac Mini / Homebrew)

```bash
brew install tesseract ocrmypdf poppler
# optional language packs: brew install tesseract-lang
```

Env knobs: `OCRMYPDF_BIN`, `TESSERACT_BIN`, `PDFTOPPM_BIN`,
`ANTIEK_PDF_OCR_TIMEOUT_S` (default 120), `ANTIEK_PDF_OCR_LANG` (default eng),
`ANTIEK_PDF_OCR=0` to disable.

## Non-goals

- Requiring the DeepSeek-OCR-2 daemon for reader-HTML ingest.
- Dollar billing / cloud OCR vendors.
- Claiming OCR accuracy; engine stamp is the honesty marker.

## Consequences

Scanned PDF uploads on Mini get an honest OCR→HTML path when brew tools are
present. Hosts without tools get a clear deferred error instead of a silent
empty sidecar.

## Supersession

Prefer-DeepSeek order: see `pdf-deepseek-ocr-html-prefer-2026-09-19.md`.
