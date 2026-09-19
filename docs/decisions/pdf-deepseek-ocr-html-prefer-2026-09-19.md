# Decision: Prefer DeepSeek OCR for scanned PDF→HTML

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** #3190 / `pdf-ocr-html-2026-09-19.md`; `acquisition/doc_to_html/pdf_ocr.py`;
`substrate/research_bridge/ocr.py`.

## Context

#3190 shipped brew `ocrmypdf` / `pdftoppm`+`tesseract` for thin/scanned
PDF→reader-HTML. Mini now has DeepSeek-OCR-2 reachable
(`ocr_available=True` on `:1235`), and the research_bridge arm already
speaks the verified request format. Preferring the VLM when up improves
layout/table fidelity for scans without inventing a cloud OCR vendor.

## Decision

1. After empty/thin pypdf, try OCR in this order:
   1. **DeepSeek-OCR-2** (`substrate.research_bridge.ocr`) when
      `ocr_available()` and `ANTIEK_PDF_OCR_DEEPSEEK` is on (default).
      Stamp `converter_engine=deepseek_ocr`. Page-capped via
      `ANTIEK_PDF_OCR_MAX_PAGES`.
   2. Else **`ocrmypdf`** → `converter_engine=ocrmypdf`
   3. Else **`pdftoppm`+`tesseract`** → `converter_engine=tesseract`
2. Soft-fail DeepSeek (empty/timeout/OcrError) → fall through to brew CLIs.
3. Refuse empty OCR output before `store_reader_html` (unchanged).
4. `ANTIEK_PDF_OCR=0` disables every OCR arm; `ANTIEK_PDF_OCR_DEEPSEEK=0`
   skips only DeepSeek.

## Non-goals

- Requiring DeepSeek daemon on every host (brew path remains the portable fallback).
- Dollar billing / cloud OCR vendors.
- Changing research_bridge ingest extractors (already DeepSeek-first).

## Consequences

Scanned PDF uploads on Mini prefer DeepSeek when the local VLM is up;
hosts without it keep the #3190 brew path. Engine stamp remains the
honesty marker.
