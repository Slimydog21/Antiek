# DeepSeek-OCR-2 + Firecrawl AnyDoc — operation

Universal ingest (`substrate/research_bridge/extractors.py`) extracts:

- **text PDFs** — pypdf text layer;
- **scanned/image-only PDFs + images** — local **DeepSeek-OCR-2** VLM via an
  OpenAI-compatible endpoint (client: `substrate/research_bridge/ocr.py`);
- **Office/ODF/RTF/CSV** — the **firecrawl-anydoc** binding (`docs` extra).

## OCR service (DeepSeek-OCR-2)

Reference serving on the operator machine: llama.cpp `llama-server` on
`127.0.0.1:1235` with the DeepSeek-OCR-2 Q8_0 GGUF (see the `deepseek-ocr`
agent skill for the verified setup, including the native MPS backend).
LM Studio on :1234 also works.

On the prod box (`antiek-prod-fsn1`) there is NO OCR service — the substrate
there must either reach one (`ANTIEK_OCR_BASE_URL` set to a reachable
endpoint, e.g. through a VPN/tunnel) or leave the default: scanned PDFs and
images then fail honestly with the actionable message (never fake success).

Env config (all optional):

| Env | Default | Meaning |
|---|---|---|
| `ANTIEK_OCR_ENABLED` | `1` | `0` disables the OCR path |
| `ANTIEK_OCR_BASE_URL` | `http://127.0.0.1:1235/v1` | OpenAI-compatible endpoint |
| `ANTIEK_OCR_MODEL` | auto | explicit model id (auto-pick prefers deepseek-ocr-2 q8_0) |
| `ANTIEK_OCR_API_KEY` | — | bearer token for authenticated endpoints |
| `ANTIEK_OCR_TIMEOUT_S` | `300` | per-request timeout |
| `ANTIEK_OCR_RASTER_DPI` | `200` | PDF rasterization DPI |
| `ANTIEK_OCR_IMAGE_FIRST` | `1` | image-first content order (llama.cpp requires it) |

Verify from the box: `python -c "from substrate.research_bridge import ocr; print(ocr.ocr_available(), ocr.resolve_model())"`.

## AnyDoc (Firecrawl)

Python binding `firecrawl-anydoc` (MIT) — install via the `docs` extra:
`uv pip install -e ".[docs]"` (deploy.yml already installs `[pdf,urls,embedding,docs]`).
Verify: ingest a `.docx`/`.xlsx` through `extract_text` and confirm
`extractor == "anydoc"` with clean GFM output.

## Honesty contract

OCR output is flagged `degraded=True` (VLM OCR can drop layout/hallucinate);
unreachable services produce failures that say exactly what is missing and
how to configure it — never silent fallbacks or fabricated text.
