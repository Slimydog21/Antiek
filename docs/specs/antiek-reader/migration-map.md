# The Unified Reader — migration map (SPR-01 M5)

**Authoritative downstream checklist.** Every current document renderer, every
open-a-document door, and every ingest emitter that must conform to the one
`<Reader>` + the document-model schema (`substrate/contracts/document_model.py`).
Each row is verified at `file:line` against the worktree tree
(`/Users/slimydog/specs/antiek-reader/.caffenagent/wt/RDR-SPR-01`) on 2026-06-04
by reading the file, not from memory.

This map is the source of truth the conformance harness consumes. The OPEN-door
set here is kept in **lockstep** with `EXPECTED_OPEN_DOORS` in
`substrate/contracts/__tests__/test_reader_conformance.py` and the
TS-bundle stub `apps/reading/src/__tests__/oneReader.conformance.test.ts`; the
renderer-deletion set is kept in lockstep with `FORBIDDEN_PROD_RENDERERS` in the
same Python file. **Dropping a row from either set is a weakened gate** — SPR-09
asserts against exactly these.

Conventions:
- All `file:line` are relative to `apps/reading/src/` (frontend) or the repo
  root (backend `substrate/…`, `acquisition/…`).
- **OPEN** = an open-a-document target. After SPR-05 it MUST route through
  `openDocument(documentId, opts)` → the one `<Reader>`. It must NOT keep a
  bespoke renderer and must NOT `navigate('/wrestle/...')`.
- **INGEST** = an entry point that survives as ingest, NEVER as open. `/wrestle`
  upload + PDF region-selection survives as the ingest/annotation surface; it is
  not a second reader.
- **RENDERER** = a document renderer that SPR-05 folds into / deletes in favor of
  the one `<Reader>`. SPR-09 asserts none is importable in the prod bundle.
- "conforms via SPR-NN" names the sprint that lands the conformance, per the
  master spec sprint sequence (SPR-02 ingest, SPR-03 the Reader, SPR-05 one door
  / `openDocument`, SPR-07 provenance/citation open, SPR-09 conformance test).

---

## 1 · Document renderers (RENDERER — fold into / delete for the one `<Reader>`)

These are the redundant renderers. SPR-03 builds the one `<Reader>`; SPR-05
re-points every OPEN door at it and removes the second renderers. SPR-09 asserts
none of the `FORBIDDEN_PROD_RENDERERS` entries is importable in the prod bundle.

| Artifact | file:line | conforms via |
|---|---|---|
| `ReadingColumn` markdown-flattener (`renderBlocks`) — the 24-line splitter that turns a page body into `<h*>`/`<p>` | `components/reader/ReadingColumn.tsx:62` (fn `renderBlocks`, lines 62–85); mounted by `modes/Reading/index.tsx` (`BookReader` at `/read/:documentId`) | **SPR-03** built the one `<Reader>` for the rich path; **SPR-05 reconciliation (§5a #4):** `ReadingColumn` is the SANCTIONED legacy fallback (NULL-`structured_blocks` path + `ReaderErrorBoundary` fallback + converged MetaReading report), reachable only behind the one `/read/:id` route — **REMOVED from `FORBIDDEN_PROD_RENDERERS`** (not a second open-a-document renderer). |
| `PdfViewer` — pdf.js canvas renderer (`page.render`) | `components/PdfViewer.tsx:114` (canvas render); mounted by `modes/WrestleApp/index.tsx:137` (ingest) **and** `modes/Reading/index.tsx:649` (the one Reader's "view original" secondary view of the ALREADY-OPEN doc — renders `pdfBytes`, not a by-id open) | **Survives as INGEST + the Reader's own preserved-original view**, never as an open-a-document-by-id target (see §3). NOT in `FORBIDDEN_PROD_RENDERERS` — it is the annotation/region-selection surface + the secondary original view, not a second body reader. The by-id OPEN seam was `openPdfPanel` / `open("PdfViewer", {documentId})`; that is what is forbidden (sharpen r2 §5a #9), not the `<PdfViewer pdfBytes>` mount. |
| `MasterMdViewer` — research master-markdown SYNTHESIS reader (takes a `ParsedSynthesis` prop; never opens a doc by id) | `modes/ResearchWorkstation/MasterMdViewer.tsx:191` (default export); cmd-click open seam `:762`→`:774` (was `openPdfPanel`) | **SPR-05 (DONE):** folded the cmd-click by-id open seam into `openDocument`. MasterMdViewer SURVIVES as a synthesis-summary view (§5a #5). Forbidden entry sharpened to `MasterMdViewer.tsx::openByIdSeam`. **NOTE (corrected by sharpen r2 §5a #9):** SPR-05 routed THIS caller, but `openPdfPanel` was NOT gone tree-wide — `RegionEmbedBlock.tsx` survived as a live caller. r2 routed that last one + the `openHouse` direct-navigate; see §5a #9. |
| `MetaReading` bespoke `<article>` body | `modes/Reading/MetaReading/index.tsx:251` (was `<article … whitespace-pre-wrap>`) | **SPR-05 (DONE):** the bespoke `<article>` report body was CONVERGED to the sanctioned `ReadingColumn` (§5a #6); no second document `<article>`. Forbidden entry kept: `modes/Reading/MetaReading/index.tsx::article`. |
| DRW canvas ad-hoc text div — `{node.text}` rendered in a `font-serif` div | `modes/DeepResearchWorkspace/BlockDetail.tsx:87`–`88` (`<div … leading-relaxed>{node.text}`) | **SPR-05 (DONE):** the div renders a GRAPH NODE (not a document); its OPEN-the-source seam (`onCiteSource`) was wired live → `openDocument(node.source_document_id)` (§5a #7). **NOTE (discrepancy):** `FORBIDDEN_PROD_RENDERERS` locates this in `index.tsx::canvasTextDiv`; the div lives in sibling `BlockDetail.tsx:87` — same surface, bridged here. |

---

## 2 · Open-a-document doors (OPEN — must route through `openDocument` → the one `<Reader>`)

Exact lockstep with `EXPECTED_OPEN_DOORS` in `test_reader_conformance.py`. Every
row's door identifier matches a member of that set. SPR-05 routes each call site
through `openDocument`; SPR-09 asserts each.

| Door (id in `EXPECTED_OPEN_DOORS`) | Artifact | file:line | Today routes to | conforms via |
|---|---|---|---|---|
| `Library.openWork` | Library mode `open` callback / `BookCard onOpen` | `modes/Library/index.tsx:145`–146 (`open` → `navigate('/read/:id')`); also `:163`; card wired `:333` | **`/read/:id` already** (not `/wrestle`) | **SPR-05** swaps `navigate('/read/…')` for `openDocument(id)`; **SPR-09** asserts. |
| `LibraryView.open` | paginated browse view open | `components/library/LibraryView.tsx:71` (`navigate('/read/:id')`) | **`/read/:id` already** | **SPR-05** → `openDocument`; **SPR-09** asserts. |
| `Reading.openDoc` | the current book reader surface (`BookReader`) at `/read/:documentId` | `modes/Reading/index.tsx:41` (`export default function BookReader`), reads `documentId` from params `:42`, renders via `ReadingColumn` `:14` | this IS the `/read/:id` target today (renders with the flattener) | **SPR-03** replaces its body with the one `<Reader>`; **SPR-09** asserts. (No literal `openDoc` symbol — the id names this surface.) |
| `DocumentsIndex.open` | substrate-attached sources index, open row | `modes/DocumentsIndex/index.tsx:158` (`navigate('/wrestle/:id')`) | **`/wrestle/:id` — MIS-ROUTE** | **SPR-05** re-routes to `openDocument`; **SPR-09** asserts (one of the 3 convergence targets). |
| `CommandPalette.openDocument` | palette "Documents" result open | `components/CommandPalette.tsx:390` (result `path: '/wrestle/:id'`) | **`/wrestle/:id` — MIS-ROUTE** | **SPR-05** → `openDocument`; **SPR-09** asserts (convergence target). |
| `ChunkModal.openInDocument` | research chunk modal "open in document" deep-link | `modes/ResearchWorkstation/ChunkModal.tsx:176`–177 (`/wrestle/:id?page=N`) | **`/wrestle/:id` — MIS-ROUTE** | **SPR-05** → `openDocument(id, {page})`; **SPR-09** asserts (convergence target). |
| `MasterMdViewer.cmdClick` | ⌘/Ctrl-click a source in the master-md viewer | `modes/ResearchWorkstation/MasterMdViewer.tsx:762` (cmd-click guard) → `:774` `openPdfPanel({documentId})` | opens a PDF panel (bespoke) | **SPR-05** → `openDocument(id, {page})`; **SPR-09** asserts. |
| `DRW.citeSource` | "cite source" affordance on a canvas BlockCard / its detail | door: `modes/DeepResearchWorkspace/Canvas/BlockCard.tsx:117`–118 (`onCiteSource` button); wired from `index.tsx:185`/`:234`; provenance resolved in `BlockDetail.tsx:48` (`documentId: node.source_document_id`) | overlay panel, no real open | **SPR-07** resolves provenance to a real source open via `openDocument`; **SPR-09** asserts. (`EXPECTED_OPEN_DOORS` attributes it to `index.tsx (BlockCard detail)`; the button lives in `Canvas/BlockCard.tsx`, the host wiring in `index.tsx` — see §4.) |
| `Write.traceToSource` | citation-chip trace-to-source in the Write editor | emit: `modes/Write/Editor/Citation.tsx:38` (`emitTraceIntent`); bus: `modes/Write/Editor/traceIntent.ts:28`; resolve+open: `modes/Write/WriteHome.tsx:101` (`navigate('/read/:id')` when servable); provenance chain view: `modes/Write/Xray.tsx:3` (`getTraceTarget`) | `/read/:id` when servable, honest fallback when gated | **SPR-07** routes through `openDocument` with the §9.0 gate; **SPR-09** asserts. (`EXPECTED_OPEN_DOORS` lists `Citation.tsx + Xray.tsx + WriteHome.tsx`; the OPEN action is `WriteHome.tsx:101`. `Xray.tsx` is the provenance-chain VIEW, not the open call — see §4.) |
| `MetaReading.openCitation` | click a citation in a meta-reading deliverable | `modes/Reading/MetaReading/index.tsx:95` (`openCitation` cb) → `:104` `navigate('/read/:id')` (sets scroll pos `:99`); chip wired `:266` | `/read/:id` | **SPR-05/07** → `openDocument(id, {highlight})`; **SPR-09** asserts. |
| `Route./read/:documentId` | the canonical Reader route | `App.tsx:161` (`<Route path="/read/:documentId" element={<BookReader />}>`) | mounts `BookReader` (the current flattener reader) | **SPR-03** mounts the one `<Reader>` here; **SPR-05** makes it `openDocument`'s mount target; **SPR-09** asserts every OPEN door lands here. |

**Door count: 11 — matches `len(EXPECTED_OPEN_DOORS) == 11`.** Reconciled 1:1, no
door dropped or added.

The three TODAY-mis-routing-to-`/wrestle` doors (the convergence target named in
`test_expected_open_door_set_is_pinned_and_nonempty`): `DocumentsIndex.open`,
`CommandPalette.openDocument`, `ChunkModal.openInDocument`. All three verified
above pointing at `/wrestle/:id`.

---

## 3 · Ingest entry points (INGEST — survive as ingest, never as open)

`/wrestle` upload + PDF region-selection is the ingest/annotation surface, not a
second reader. It must EMIT into the document model (via SPR-02's emitter), not
become an open door.

| Artifact | file:line | Role | conforms via |
|---|---|---|---|
| `/wrestle` + `/wrestle/:documentId` routes → `WrestleApp` | `App.tsx:113`–114 | the PDF wrestling / region-selection ingest surface | **Survives as INGEST.** SPR-05 must NOT turn it into an open door; the OPEN doors above stop routing here. |
| `WrestleApp` mounting `PdfViewer` + region selection | `modes/WrestleApp/index.tsx:33` (export), `:137` (`<PdfViewer>`) | annotate / select regions on a PDF; emits `DocumentRegionSelectedPayload` | INGEST; region selection feeds the document model. |
| `PdfViewer` region-selected emit | `components/PdfViewer.tsx:197` (`DocumentRegionSelectedPayload`) | produces the region/anchor signal | **SPR-02** maps regions into the document model's `Region`/anchors. |

---

## 4 · Ingest EMITTERS (must produce the document model)

The schema's reason to exist: today the served body is a **flat `raw_text`
string** (`documents.raw_text`), which `ReadingColumn` re-flattens. Every emitter
that writes that flat body must, post-SPR-02, emit a structured `Document`
(`substrate/contracts/document_model.py`). The single column they all funnel into
is `documents.raw_text`, written by `insert_document`.

| Emitter | file:line | What it emits today | conforms via |
|---|---|---|---|
| `insert_document` — the single document-write chokepoint | `substrate/graph/ops.py:127` (def), `raw_text` param `:138`, persisted `:211`/`:216` | flat `raw_text: str \| None` | **SPR-02** — the structured `Document` becomes the stored body (or a sibling column); `insert_document` stays the §9.0-gated single writer. |
| `serve_full_text` — the serve-gate read side | `substrate/books/serve.py:89` (def), returns `full_text: str \| None` `:76` | flat `full_text` string behind the §9.0 gate | **SPR-02/03** — serve a structured `Document` through the SAME gate (`serve_full_text` / `serve_full_text_guarded`). The model's `DocumentAttribution.content_class` already records the gate's `ContentClass`. |
| Book ingest — `register_book` | `substrate/books/ingest.py:64` | registers a book row (title/author/class) | **SPR-02** emits the `Document` body alongside the row. |
| URL ingest — HTML→markdown extractor | `acquisition/urls/extract.py:55` (`markdown: str` field of `ExtractedDocument`) | a flat markdown string | **SPR-02** — parse markdown → typed blocks instead of storing the flat string. The richest near-term win (markdown already has structure to preserve). |
| arXiv PDF ingest — `store_pdf_for_arxiv_row` | `acquisition/arxiv/store.py:198` (def), `UPDATE … raw_text` `:328` | sets `raw_text` from extracted PDF text | **SPR-02** — emit a `Document` from the PDF extraction; this is the emitter rigor #1 flags (figures/math optional until validated against a real arXiv extraction here). |
| Research cascade ingest — `extract_paste` | `substrate/research_bridge/extractor.py:402` (def `extract_paste`; entry described in module docstring `:3`), reads stored `d.raw_text` `:240`/`:253`, prompt-renders it `render_prompt(raw_text)` `:99` | insight/question nodes from a paste's stored `raw_text` | **SPR-07** — wired in its OWNING sprint (provenance ingestion), NOT SPR-02 (see §4a). |

### 4a · SPR-02 wiring scope — what SPR-02 wired, and what it deliberately deferred (recorded scoping decision, NOT a spec amendment)

SPR-02's named file scope (per `sprint-02-document-model-ingest.html` M2/M3
milestone `files`) is the **urls + arxiv** ingest paths. SPR-02 round 2 (D2) wired
exactly those two RUNNING ingest paths to emit `structured_blocks` at ingest:

- **arXiv** (`acquisition/arxiv/adapter.py` `ingest_paper`) — now passes
  `structured_blocks=` into its `insert_document` call (`acquisition/arxiv/adapter.py`),
  built via the governed `acquisition/arxiv/source_document.py::fetch_arxiv_document`
  (ar5iv structured source → tex math, PDF fallback) through the **existing**
  host-global rate governor / 429 ban-sentinel — no second fetcher. Best-effort:
  a fetch/parse/ban failure stores NULL blocks + logs (backfill upgrades later),
  never breaks ingest.
- **PDF-URL** (`acquisition/urls/adapter.py` `ingest_url`) — now detects a PDF
  body (Content-Type `application/pdf` OR the `%PDF-` magic-byte floor) and routes
  the bytes to `processing/extraction/pdf_to_document_model.py::pdf_bytes_to_document`,
  emitting its `structured_blocks` instead of force-flattening binary through
  `html_to_markdown`.

**Deliberately deferred (still on the additive NULL-fallback + backfill path):**

- **`register_book`** (`substrate/books/ingest.py:64`) and the book ingest adapter
  (`acquisition/books/adapter.py` `ingest_book`/`ingest_servable_book`) — OUT of
  SPR-02's named file scope. They continue to call `insert_document` with NO
  `structured_blocks` (the column lands NULL), which the M5
  `backfill_structured_blocks` run upgrades from the stored `raw_text` WITHOUT
  re-fetch. The store-both column + the deny-by-default stamping they already use
  are untouched. (Note: the arXiv **full-text** path `ingest_paper_with_rights`
  routes PDF bytes through `ingest_servable_book` → this same book adapter; that
  full-text leg is therefore also on the backfill path. The arXiv wiring above is
  on the abstract `ingest_paper` path, which SPR-02 scoped.)
- **Cascade `extract_paste`** (`substrate/research_bridge/extractor.py:402`) — wired
  in its OWNING sprint, **SPR-07** (provenance ingestion), which the master sprint
  sequence assigns the research-source persistence and which REUSES this same
  extractor. SPR-02 builds the extractor; it does not wire the research loop (the
  SPR-02 spec's Out-of-scope list says so verbatim).

This is a **recorded scoping decision** consistent with the SPR-02 spec's own file
scope + Out-of-scope section — NOT a change to the spec's goal wording. The
deferred emitters are safe because the column is additive (NULL ⇒ the read side
flattens `raw_text` exactly as today) and the M5 backfill upgrades any pre-existing
or NULL-blocks row idempotently from stored text.

### 4b · SPR-02 round-4 (DA) — closing the API-arXiv goal gap (preferred path taken, NOT the fallback)

A round-3 re-critique caught that the **`POST /sources/ingest`** arXiv branch
(`interfaces/research/api/app.py`) passes `emit_structured_blocks=False` and leaned on
the M5 backfill — but backfill reconstructs blocks from `raw_text`, which for arXiv is
the **abstract only** (`acquisition/arxiv/adapter.py:314` stores the formatted abstract
as `raw_text`). Backfill can therefore NEVER produce the full ar5iv/PDF document for an
API-ingested paper, and no timer/cron/in-process trigger invokes backfill in prod —
so the API path silently degraded to abstract-only blocks forever. The
"the corpus still gets typed blocks" comment was misleading.

**Resolved (round 4, preferred = close it properly):** the inline insert stays fast
(abstract row + immediate 202, **no** inline governed egress — the DN2 event-loop fix is
preserved), and the **full-document** structured fetch is offloaded to a FastAPI
`BackgroundTasks` job that runs AFTER the response in FastAPI's threadpool:

- `interfaces/research/api/app.py` — `post_ingest_source` now takes
  `background_tasks: BackgroundTasks` and, in the arXiv branch, `add_task(...)`s
  `_upgrade_arxiv_structured_blocks(document_id, arxiv_id, title)` once the abstract row
  lands. That sync task calls the SAME governed full-document fetcher the inline
  `emit=True` (batch/CLI) path uses — `acquisition/arxiv/source_document.py::fetch_arxiv_document`
  (via the injectable `_fetch_arxiv_document` indirection) — then
  `substrate/graph/ops.py::set_structured_blocks` persists the FULL typed-block document.
  Exactly one governed seam (no second fetcher; rigor #4). Best-effort: a ban/network/
  parse/persist failure logs and leaves `structured_blocks` NULL, so M5 backfill stays a
  safety-net; it never raises (a raised background task would surface nowhere useful and
  must not poison an already-202'd ingest).
- FastAPI runs the **sync** `add_task` callable in a threadpool, so the 202 is still
  immediate and the async event loop is never blocked. The full-doc fetcher is INJECTABLE
  (`_fetch_arxiv_document`) so tests populate blocks with NO live network (the SPR-02 CI
  socket guard would block real arXiv egress).
- Reuse, not a new queue: there was no pre-existing in-process job queue / async
  note-taker job-row in `infrastructure/` — `BackgroundTasks` is the framework primitive
  already available to the FastAPI app, so the offload uses it rather than inventing a
  queue.

Proof: `tests/test_sources_ingest.py::test_arxiv_endpoint_background_task_upgrades_to_full_blocks`
(202 immediate + full multi-section blocks via the injected fetcher, zero sockets) and
`::test_arxiv_endpoint_background_failure_leaves_null_for_backfill` (a raised background
fetch → 202 + abstract landed + `structured_blocks` NULL for the backfill net). The M5
backfill remains the safety-net for the failure case; this is **not** the documented
fallback (which would have left abstract-only blocks + a tracked gap) — the gap is
**closed**, not merely recorded.

---

## 5 · Reconciliation note (intellectual honesty)

Three places where the verified `file:line` diverges from what
`EXPECTED_OPEN_DOORS` / `FORBIDDEN_PROD_RENDERERS` assumed — surfaced so SPR-05/09
fix the call site, not the map:

1. **`DRW.canvasTextDiv` lives in `BlockDetail.tsx:87`, not `index.tsx`.**
   `FORBIDDEN_PROD_RENDERERS` names `modes/DeepResearchWorkspace/index.tsx::canvasTextDiv`.
   The ad-hoc `{node.text}` div is actually in the sibling `BlockDetail.tsx`
   (the overlay panel `index.tsx:231` mounts). Same surface; SPR-09's
   forbidden-import check should target `BlockDetail.tsx` (or both). The Python
   set string is kept as-is for lockstep; this note is the bridge.
2. **`DRW.citeSource` button is in `Canvas/BlockCard.tsx:117`, host-wired from `index.tsx`.**
   `EXPECTED_OPEN_DOORS` attributes it to `index.tsx (BlockCard detail)`. The
   affordance (`onCiteSource`) is defined on `BlockCard`; `index.tsx` supplies
   the handler. Both files are load-bearing for this door.
3. **`Write.traceToSource`'s OPEN action is `WriteHome.tsx:101`; `Xray.tsx` is a VIEW, not the open call.**
   `EXPECTED_OPEN_DOORS` lists `Citation.tsx + Xray.tsx + WriteHome.tsx`.
   `Citation.tsx:38` emits the intent, `traceIntent.ts:28` is the bus,
   `WriteHome.tsx:101` does the `navigate('/read/…')` (the actual open).
   `Xray.tsx:3` renders the paragraph↔blocks provenance chain (`getTraceTarget`);
   it does not itself open a document. SPR-07 routes `WriteHome.tsx:101` through
   `openDocument`.

Everything else in `EXPECTED_OPEN_DOORS` (8 of 11 doors) and the renderer set
reconciles cleanly to a verified `file:line` above. Door count is exactly 11 on
both sides.

### 5a · SPR-05 execution reconciliation (renderer set sharpened, NOT weakened)

SPR-05 implemented `openDocument`, routed every door, and reconciled
`FORBIDDEN_PROD_RENDERERS` to the truth the verified tree showed. The set was
**sharpened to name the document-OPEN seams** (the thing the convergence
forbids), not the sanctioned fallback. Recorded here + kept in lockstep with the
new TS/Python sets:

4. **`ReadingColumn.tsx::renderBlocks` is the SANCTIONED legacy fallback — REMOVED
   from the forbidden set.** Verified: `ReadingColumn` is the body renderer the
   one `/read/:id` Reader degrades to when `structured_blocks` is NULL
   (`modes/Reading/index.tsx` — the `structuredDoc ? <Reader> : <ReadingColumn>`
   branch + the `ReaderErrorBoundary` fallback). It is reachable ONLY behind the
   one gated route, never as a SECOND open-a-document renderer. Deleting it would
   break the legacy/un-backfilled read path. So the forbidden set now EXCLUDES it
   and instead names the open-a-document seams (below). `renderBlocks` stays as
   the fallback's body builder.
5. **`MasterMdViewer.tsx` SURVIVES as a synthesis-summary view (NOT forbidden as a
   whole renderer).** Verified: `MasterMdViewer({ synthesis }: { synthesis:
   ParsedSynthesis })` takes a PARSED SYNTHESIS object as a prop and renders a
   research master-markdown synthesis — it never fetches/opens a document by id.
   Its ONLY by-id open was the cmd-click `openPdfPanel({documentId})` seam
   (`:774`). SPR-05 routed that seam to `openDocument` (so it now mounts the one
   Reader, not a bespoke PDF panel). MasterMdViewer therefore never opens a
   document by id → the spec's survivor carve-out applies. The forbidden entry is
   now `MasterMdViewer.tsx::openByIdSeam` (the routed seam), not the file.
   **Reverses if** MasterMdViewer ever opens a document by id again.
6. **`MetaReading/index.tsx::article` CONVERGED to `ReadingColumn`.** The bespoke
   `<article whitespace-pre-wrap>` report body (`:254`) was replaced with the
   sanctioned `ReadingColumn` body (the report is a generated SYNTHESIS, not a
   served document by id, so `assetId={null}` — never attributed as a monetized
   asset). No second bespoke document `<article>` survives.
7. **`DRW.canvasTextDiv` (`BlockDetail.tsx:87`) renders a GRAPH NODE, not a
   document — its OPEN-the-source capability is now `openDocument`.** The
   `{node.text}` div is the FloatMenu selection scope for a graph node; it has no
   SPR-02 `Document` (a node is not a document). SPR-05 wired the previously-dead
   `onCiteSource` button (`Canvas/BlockCard.tsx:117`) live through
   Canvas → DraggableBlock → BlockCard, with the host handler in
   `DeepResearchWorkspace/index.tsx` calling
   `openDocument(node.source_document_id)`. So opening the node's SOURCE document
   goes through the one door; the node-text div stays (it is not a document
   renderer). Forbidden entry kept as the open-source SEAM, bridged here.
8. **FIFTH DOOR found + routed (out-of-scope warn honored): `ProjectTree`
   document node.** `shell/ProjectTree.tsx` routed a `document` tree node to
   `/wrestle/${n.id}` (open) on plain click and opened a `PdfViewer` floating
   panel on cmd-click — an open-a-document door NOT on the 11. Per the spec's
   fifth-door rule it is now routed through `openDocument` (plain → read register,
   cmd-click → `{mode:'inspect'}`); the `/wrestle/:id` string + the PdfViewer
   document panel are gone. (Note: the tree's node list is still `MOCK_RECENT`
   fixture data, so this door is wired-but-not-live-data-backed — recorded.)
9. **SPARSE-r2 CORRECTION — `openPdfPanel` was NOT "gone" tree-wide; two live
   open-a-document forks survived the SPR-05 convergence (the file-scoped guard
   hid them). Both are now routed + a DURABLE tree-wide guard added.** The
   original SPR-05 §5a #5 + handoff over-claimed "no more `openPdfPanel`"; it had
   only routed the MasterMdViewer caller. Two forks remained:
   - **`modes/Notebook/blocks/RegionEmbedBlock.tsx:34`** — the notebook
     "Open at page" block (registered live at `Editor.tsx:128`, slash-creatable
     at `SlashMenu.tsx:94`) still called `openPdfPanel({ documentId, page })`, a
     bespoke pdf.js floating panel = a SECOND open-a-document renderer. r2 routed
     it through `useOpenDocument()` → `openDocument(documentId, { page })`, with
     the 1-based page LABEL → 0-based reader index conversion (`Math.max(0, n-1)`,
     the SAME conversion `ChunkModal` uses); the now-unused `openPdfPanel` import
     was deleted from that file.
   - **`modes/Reading/index.tsx:374` `openHouse`** — the in-reader
     recommended-next ("house fill") affordance called `navigate('/read/:id')`
     directly: the CORRECT gated route, but it BYPASSED the single resolver. r2
     routed it through `const openDocument = useOpenDocument(); openHouse =
     useCallback((docId) => openDocument(docId), …)` — and removed the now-dead
     `useNavigate`/`navigate` binding from the file.
   No other live `openPdfPanel(` caller or by-id `open("PdfViewer", …)` seam
   survives anywhere outside the ingest surface (verified by tree-wide grep). The
   only remaining reference to `openPdfPanel` is its DEAD definition in
   `workspace/actions.ts` (exported, zero callers) + the panel-kind scaffold
   (`PanelRegistry`/`panel.types`/`aiActions` doc-comment) — none of which OPENS a
   document by id. **Durable guard:** the conformance test
   (`apps/reading/src/__tests__/oneReader.conformance.test.ts`) gained a
   TREE-WIDE describe block ("no second open-a-document seam survives") that walks
   EVERY `.ts/.tsx` under `apps/reading/src/`, exempts only ingest
   (`WrestleApp/**`) + the seam's own definition/registry/typedef/story, and
   asserts ZERO non-ingest file calls `openPdfPanel(` or `open("PdfViewer", …)`.
   The previous guard (~`:268`) was FILE-SCOPED to `MasterMdViewer.tsx`, which is
   exactly why RegionEmbedBlock slipped through green. A catch-test proves the
   tree-wide guard goes RED on a re-introduced caller (and stays green for the
   exempt ingest files + clean non-ingest files). `<PdfViewer pdfBytes>` mounts of
   already-resolved bytes inside a sanctioned host (WrestleApp ingest; the
   Reader's own "view original" secondary view) are NOT by-id opens and are
   deliberately not matched.

**`/wrestle/:documentId` OPEN route REMOVED** from both `App.tsx` and
`AppLegacy.tsx`. The bare `/wrestle` (no id) survives as the PDF upload / region-
selection INGEST surface (migration-map §3), reachable from Library's "bring your
own PDF". The forbidden entry `PdfViewer.tsx::asOpenTarget` names the killed
open-target use; the PdfViewer module itself survives behind the ingest door.

**Door-routing note:** the §2 `conforms via` column attributed three doors to
SPR-07 (`DRW.citeSource`, `Write.traceToSource`, `MetaReading.openCitation`); the
SPR-05 spec (M2 routes every door, M5 wires Write trace) assigns the
`openDocument`-routing of all 11 doors to SPR-05, which this execution landed. All
11 now route through `openDocument` / the canonical `/read/:id` Reader route (the
`CommandPalette` document result navigates `/read/:id` directly via its generic
`entry.path` navigator — the same target `openDocument(id)` resolves to). SPR-07's
remaining job on `DRW.citeSource` / `Write.traceToSource` is the deeper
provenance/region resolution (the exact-`Region` highlight), not the door routing,
which is done. The source-level conformance for door (a) + forbidden (b) is filled
+ green in `apps/reading/src/__tests__/oneReader.conformance.test.ts`; SPR-09
lifts it to the built bundle.

---

## 6 · Why §4 names a chokepoint, not all 12 `insert_document` callers (defensibility)

§4 lists `insert_document` (`substrate/graph/ops.py:127`) as the single
document-write chokepoint and then names the few emitters that BUILD the body
(`register_book`, the URL markdown extractor, the arXiv PDF store, the cascade
`extract_paste`, the serve-gate read side). It deliberately does NOT enumerate all
twelve per-source adapters that call `insert_document` — `acquisition/{arxiv,urls,
books,twitter,substack,youtube,podcasts,voice,interview}/adapter.py` and
`substrate/research_bridge/{ingest,ingest_file,versioning}.py` (each verified to
call `insert_document(` at its adapter, e.g. `acquisition/arxiv/adapter.py:240`,
`acquisition/urls/adapter.py:364`). Rationale: all twelve funnel through the ONE
sink, so SPR-02's conformance work is "make the chokepoint store a `Document` + fix
the handful of extractors that produce the flat body upstream of it" — not twelve
parallel edits. Listing all twelve would pad the map with rows that converge on the
same fix. The adapters are recorded here so SPR-02 can confirm none mints a body by
a path that bypasses the chokepoint.

---

## 7 · Round-2 verification log (rigor #3 / diligence #4)

This map was produced in round 1 and **re-verified line-by-line in round 2**
(2026-06-04) by opening every cited `file:line` in the worktree, not from memory.
Re-verified and confirmed accurate: all 5 RENDERER rows; all 11 OPEN doors (incl.
the three `/wrestle` mis-routes); the 3 INGEST entry rows; all EMITTER rows incl.
`ReadingColumn.tsx:62`, `LibraryView.tsx:71`, `BlockDetail.tsx:87`,
`Canvas/BlockCard.tsx:117`, `serve.py:89`, `books/ingest.py:64`,
`urls/extract.py:55`, `arxiv/store.py:198`/`:328`. One correction applied in
round 2: the `extract_paste` emitter line was `:3` (the module docstring) — fixed
to the function def at `:402`. The door/renderer sets remain in exact lockstep with
`EXPECTED_OPEN_DOORS` (11) and `FORBIDDEN_PROD_RENDERERS` (4) in
`test_reader_conformance.py`; no row was added, dropped, or weakened.

---

*Generated SPR-01 M5, 2026-06-04 (round 2 re-verified). Source of truth for
SPR-02/03/05/07 conformance and the definition of "done" for SPR-09 door (a). Kept
in lockstep with `substrate/contracts/__tests__/test_reader_conformance.py` and
`apps/reading/src/__tests__/oneReader.conformance.test.ts`.*
