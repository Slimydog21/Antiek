# HTML-first design thesis

Antiek’s product thesis, stated without ceremony:

> **Every research, reading, and writing artifact is self-contained HTML.**

Not “HTML as an export.” Not “Markdown with a pretty preview.” The artifact
*is* the HTML document: addressable, restylable, script-free, provenance-bearing,
and durable under content-addressed versions.

This document is the thesis. The companion design system
([`design-system.md`](./design-system.md)) is how the surfaces that present those
artifacts look and behave.

---

## 1. Why HTML

| Property | Why it matters for Antiek |
| --- | --- |
| Self-contained | One file carries structure, style, and the hidden data island. No app shell required to *read*. |
| Deterministic restyle | `extract_island(html) → doc model → render(style)` is pure. “Regenerate in style X” is not a model call. |
| Provenance-native | Footers, claim chips, and version receipts are first-class DOM, not metadata bolted on later. |
| Agent-readable | Agents already speak HTML/DOM; a stored artifact is both a human reading surface and a machine memory unit. |
| Sandboxable | `sandbox=""` previews and a zero-script gate make untrusted content presentable without executing it. |
| Versionable | SHA-256 of the HTML bytes *is* the content identity of a version. |

Markdown, PDF, DOCX, and the open web are **sources**. HTML is the **house form**.

---

## 2. The pipeline: source → stylable HTML artifact

```
  PDF / website / office / image
            │
            ▼
   ┌─────────────────────┐
   │  Ingest extractors  │  substrate/research_bridge/extractors.py
   │  + OCR arm          │  DeepSeek-OCR-2 for scanned/image-only
   │  + AnyDoc arm       │  firecrawl-anydoc for office/ODF/RTF/CSV
   └─────────┬───────────┘
             │  sanitized intermediate (Markdown / structured text)
             ▼
   ┌─────────────────────┐
   │  Projection engine  │  services/html_projection/
   │  render(doc, style) │  inlined CSS, provenance footer, data island
   └─────────┬───────────┘
             │  zero-script gate
             ▼
   ┌─────────────────────┐
   │  Research artifact  │  substrate/research_artifact/
   │  store + versions   │  selected_style, content_hash, source_hash
   └─────────┬───────────┘
             │
             ▼
        Style wheel ── restyle_artifact (no model) ──► new version
```

### 2.1 Ingest arms (honesty rules)

Documented in `docs/decisions/ingest-deepseek-ocr-2.md` and the runbooks under
`docs/runbooks/` (when present for the DeepSeek-OCR-2 / anydoc pipeline):

- **Text PDFs / web / structured office** → text extraction or AnyDoc → GFM-ish intermediate.
- **Scanned / image-only PDFs and images** → local **DeepSeek-OCR-2** VLM
  (`Convert the document to markdown.`, temperature 0). OCR output is flagged
  `degraded=True` because VLM OCR can drop layout or hallucinate.
- **Service down** → honest failure with config hint. Never a fake success.
- **Sanitization** is mandatory before anything is projected: no script, no
  external asset pull, bounded read sizes on stored HTML.

### 2.2 Projection invariants

From `services/html_projection/`:

1. **Zero-script.** Output fails the gate if it carries `<script>`, `javascript:`,
   or CSS constructs that pull external bytes (`@import`, `url()`, …).
2. **Data island.** The canonical doc model is embedded so
   `extract_island(render(d)) == d`. Restyle never re-asks a model for structure.
3. **Style = base + theme.** Antiek structural chrome is always present; theme CSS
   appends. See the design system §2.
4. **Determinism.** No wall-clock, no randomness in render. Same `(doc, style)` →
   same bytes.

---

## 3. Agent-facing memory and queryable storage

HTML artifacts are not only a reading surface. They are units of **memory**:

- **Artifact store** (`substrate/research_artifact/`) keys artifacts by id, owner,
  source path/hash, selected style, and version chain.
- **Versions** are durable HTML files with content hashes. `POST …/render` appends
  a version; `GET …/versions/{n|latest}` serves it with receipt headers.
- **Query / retrieval** layers (graph, turbopuffer, corpus search) index *from*
  the artifact and its island — claims, citations, and structure remain
  addressable after restyle because restyle does not rewrite the island’s
  semantic content.
- **Agents** interact by:
  - reading the HTML or the extracted island,
  - proposing edits as structured patches / prompts that re-project,
  - never by free-form mutation of stored HTML that bypasses the gate.

The operator-facing rule: if it is not in an artifact (or an explicitly named
store derived from one), it is not part of the investigation’s durable memory.

---

## 4. Interaction and edit via prompts

Editing is not “open a rich-text surface and hope.” The preferred loop:

1. **Read** the artifact (or a style-preview of it) in the workstation.
2. **Prompt** a change — cascade proposal, note, distill, chase — against the
   investigation and the artifact’s island.
3. **Project** the result back through the renderer under a chosen style.
4. **Apply** only when the operator accepts; apply creates a hashed version.

The style wheel is the presentation half of that loop: the same island, many
readings. Forking a style is how an operator encodes a preferred reading
philosophy (source-first paper, slate for night sessions, a personal field-notes
theme) without forking the underlying research.

---

## 5. Style wheel as the presentation control plane

- **Builtins** (Antiek, Academic paper, Book, Blog, Slate) are stable anchors.
- **Forks** are per-user, validated, deletable, never able to override a builtin name.
- **Preview** is side-effect-free; **Apply** is the only mutation of the version chain.
- **Receipts** (`X-Artifact-*`, `X-Content-SHA256`) are how the UI proves what it
  just wrote — and how it refuses a bad response.

Full UX contract and craft rules: [`design-system.md`](./design-system.md) §3.

---

## 6. What this thesis refuses

- **App-shell-only research.** If the research dies when the SPA dies, it was never
  an artifact.
- **Silent degradation.** OCR unavailable, island missing, hash mismatch, style
  unknown — each is a typed failure with a readable reason.
- **Style as identity theft.** Themes re-skin; they do not strip Antiek provenance
  chrome or the data island.
- **Scripted artifacts.** Interactivity belongs in the workstation chrome, not in
  the stored document. The document remains printable, greppable, and archivable.
- **Provenance as a footer afterthought.** Sources and version identity live next
  to the claims they support.

---

## 7. Practical checklist for new work

When adding a research/reading/writing feature, ask:

1. Is the durable output a self-contained HTML artifact (or a pure derivation of one)?
2. Does restyle still work without a model call?
3. Does the zero-script gate still pass?
4. Are empty / error / degraded states named in the UI?
5. Can an agent recover structure from the island alone?
6. Does Apply produce a receipt the client can verify?

If any answer is no, the work is not yet on-thesis.

---

## 8. Related

- [`design-system.md`](./design-system.md) — frontend-craft system + style wheel UX
- `docs/decisions/ingest-deepseek-ocr-2.md` — OCR + AnyDoc ingest arm
- `docs/decisions/ingest-reader-snapshot.md` — reader snapshot boundary
- `docs/ingestion_boundary_scope.md` — what ingest will and will not do
- `services/html_projection/` — renderer, styles, gate, island
- `interfaces/research/api/style_routes.py` — HTTP contract for the wheel
- `substrate/styles/store.py` — per-user fork persistence
- `substrate/research_artifact/` — artifact + version store
