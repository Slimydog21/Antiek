# Decision: Prod OCR fallback CLIs via apt (#3190)

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** #3190 (ocrmypdf/tesseract PDF→HTML); #3196 (DeepSeek prefer order);
`acquisition/doc_to_html/pdf_ocr.py`.

## Context

Prod (Hetzner Ubuntu 24.04) had no DeepSeek-OCR-2 daemon and no brew OCR
tools, so thin/scanned PDF→reader-HTML fell through after pypdf with a
deferred error. Mini already had Homebrew `tesseract` / `ocrmypdf` / `poppler`.

## Decision

1. Install on prod via apt (system PATH `/usr/bin` is already on the antiek
   unit PATH):
   - `ocrmypdf`
   - `tesseract-ocr` + `tesseract-ocr-eng`
   - `poppler-utils` (`pdftoppm`)
2. **Do not** change converter order: DeepSeek → ocrmypdf → tesseract
   (#3196). On prod today `deepseek_ocr_available=False`; brew/apt path wins.
3. Document in Ansible `setup.yml` packages list so rebuilds reinstall.

## Verified (2026-09-19)

```
ocrmypdf_bin=/usr/bin/ocrmypdf
tesseract_bin=/usr/bin/tesseract
pdftoppm_bin=/usr/bin/pdftoppm
deepseek_ocr_available=False
ocr_cli_available=True
run_pdf_ocr smoke → engine=ocrmypdf
```

## Non-goals

- Running DeepSeek-OCR-2 on the Hetzner VM (GPU/MPS; stays Mini-local).
- Cloud OCR vendors / dollar billing.
