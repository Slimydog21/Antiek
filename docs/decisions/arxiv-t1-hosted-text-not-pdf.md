# arXiv T1 hosted body — extracted TEXT, not a PDF; PDF.js deferred

**Decision date:** 2026-05-30 (SPR-05, arxiv-ingest, tiered reader surface)
**Status:** ✅ Implemented — the T1 reader renders the gate-served extracted
text through the EXISTING markdown reading column
(`apps/reading/src/components/reader/ReadingColumn.tsx`), with the ad rails. No
new reader component (no `PdfReader.tsx`, no PDF.js on the reading route).
**Owner:** SPR-05 reader surface
**Gate:** literal PDF.js-over-hosted-PDF fidelity is the future state — it is
DEFERRED, contingent on a PDF binary being persisted + a guarded bytes-serving
endpoint + a redistribution/compliance review. None exist today.

## The decision

When the reader opens a redistributable arXiv T1 paper, the body it hosts is
the **extracted text**, served as the same gated markdown every other servable
book serves. It renders through the existing `ReadingColumn` markdown reader
(paginated on `## Page N`) plus the SPR-05 ad rails (T1 is ad-eligible). There
is NO PDF reader and NO PDF.js bundle added to the reading route.

## Why text and not a PDF — it follows from already-shipped code

The choice is not a reader-side preference; it is forced by what SPR-04 stored
and what the serve layer exposes:

1. **SPR-04 persisted only extracted text — no PDF blob.**
   `acquisition/arxiv/store.py::store_pdf_for_arxiv_row` fetches the PDF on
   demand, extracts its body, and writes that text to `documents.raw_text`:

   ```python
   "UPDATE documents SET raw_text = ? WHERE document_id = ?"
   ```

   The PDF binary is fetched, hashed (`sha256` / `byte_size` / `page_count`
   recorded in `documents.metadata.pdf_acquisition` for audit), and then
   discarded — it is never persisted as a blob. There is therefore no PDF
   binary in storage for a reader to render. (See
   `docs/decisions/arxiv-t1-only-storage.md` for the T1-only storage tiering.)

2. **There is no `application/pdf` / bytes-serving endpoint.**
   The book body reaches the client through
   `GET /books/{document_id}/full-text`, whose `FullTextResponse` carries
   `full_text: Optional[str]` — text, gated through
   `substrate.books.serve` + `serve_full_text_guarded`. No route in
   `interfaces/` streams or returns PDF bytes (`media_type="application/pdf"`,
   `FileResponse(...pdf)`, a pdf-bytes route): the only `StreamingResponse` in
   the API is the cascade SSE `text/event-stream`. So even if a PDF blob
   existed, the reader has no endpoint to fetch its bytes from.

Given (1) + (2), the only body a T1 paper can render is its extracted text, and
the existing markdown reader already renders exactly that. Building a PDF.js
reader would render nothing — there are no hosted PDF bytes to point it at.

## What literal PDF.js fidelity would require — DEFERRED, out of SPR-05 scope

"Render the original PDF with its figures/layout" is a real future enhancement,
but it is a multi-layer change well outside a reader sprint. It would require,
in order:

- **(a) persisting the PDF binary** in SPR-04's store path (a new blob column
  or object store + the storage/retention cost + a re-derivation of the audit
  metadata), where today the bytes are deliberately discarded after extraction;
- **(b) a NEW guarded bytes-serving endpoint** that re-runs the same
  rights/serve guard as `full-text` (so a T2/T3 body can never leak as bytes),
  plus the per-second ad-attention seam adapted to a PDF canvas;
- **(c) a redistribution / compliance review** — hosting and serving the
  original PDF binary (not just extracted text) is a distinct redistribution
  posture from serving extracted text, and is a §9.0 / counsel question, not a
  reader decision.

None of (a)–(c) exist. Until they do, T1 renders extracted text + ads, which is
both correct against the shipped storage/serve layer and the honest surface for
what Antiek actually holds the right to host.

## What this does NOT change

T2 (CC-BY-NC, gated — no hosted body) and T3 (unknown/default — never hosted)
do not host a body at all; they render the link-back surface to the arXiv
canonical page with no ads (`ArxivFrame`), per the binding rights law that
body-serving + ad-eligibility are {T1}-only. See
`docs/decisions/arxiv-t2-noncommercial-serving.md` for the body-emission ceiling
and `docs/decisions/arxiv-t1-only-storage.md` for the storage tiering. This note
only records that the {T1} body Antiek DOES host is extracted text rendered
through the existing markdown reader, and that PDF.js-over-hosted-PDF is the
deferred future state.
