# Ingest OCR arm — DeepSeek-OCR-2 + Firecrawl AnyDoc

**Status:** Implemented (`substrate/research_bridge/ocr.py`, `extractors.py`)

Universal file ingest (`substrate/research_bridge/extractors.py`) now has an
OCR arm for scanned/image content and a verified AnyDoc (Firecrawl) path:

- **Images** (png/jpg/jpeg/webp/bmp/tif/tiff/gif) and **scanned/image-only
  PDFs** (no text layer) escalate to the local **DeepSeek-OCR-2** VLM through
  an OpenAI-compatible endpoint (`substrate/research_bridge/ocr.py`):
  image-first chat completion with the official model-card prompt
  "Convert the document to markdown.", temperature 0, 8192 max tokens;
  PDFs are rasterized page-by-page with pypdfium2 and OCR'd with
  `## Page N` anchors. Opportunistic by design: when the service is
  unreachable the result is the historical honest failure (reason says
  OCR was unavailable + how to configure), never a fake success.
- **Office/ODF/RTF/CSV** convert through the **firecrawl-anydoc** Python
  binding (`docs` extra, pyproject), already wired by SPR-08 M1; this
  change adds the `docs` extra to the prod deploy and verifies the
  real binding end-to-end (docx → GFM).

**Config (env):** `ANTIEK_OCR_ENABLED` (default on), `ANTIEK_OCR_BASE_URL`
(default `http://127.0.0.1:1235/v1` — llama.cpp v2 server), `ANTIEK_OCR_MODEL`
(auto-pick prefers deepseek-ocr-2 q8_0), `ANTIEK_OCR_API_KEY`,
`ANTIEK_OCR_TIMEOUT_S` (300), `ANTIEK_OCR_RASTER_DPI` (200),
`ANTIEK_OCR_IMAGE_FIRST` (image-first, required by llama.cpp).

**Honesty:** all OCR output is flagged `degraded=True` (VLM OCR can drop
layout/hallucinate); failures carry the service + config hint.

**Reconsider if:** the reader doc→HTML lane (`upload_routes.py` /
`acquisition.books.reader`) should get the same OCR fallback (tracked as a
follow-up; the ingest lane is the first consumer).
