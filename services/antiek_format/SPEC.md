# `.antiek` native container format

**Status:** SPR-09 / Wave 3 of Wrestle Evolution. Locked 2026-05-21.
**Scope:** notebooks (per-doc, theme), deliverables. Single-creator only;
multi-author signatures are out of scope.

This document is the on-disk wire format. It is normative: writers MUST
produce bytes that match, readers MUST validate against this shape.

---

## 1. Why this exists (the political and technical thesis)

Born-Antiek content (notebooks, deliverables, public-graph contributions)
is a richer object than any PDF: claim cards, region embeds, voice notes,
user-asserted edges. Exporting to PDF is the lossy projection. Making PDF
the source of truth would calcify that loss into the substrate. The native
container aligns the file with the agentic artifact while keeping a
**markdown projection** as the universal-fallback shield: a reader without
Antiek installed still sees the prose.

**Master-spec invariant (do not violate):** substrate-derived artifacts —
chunks, embeddings, graph edges from the substrate's interpretation,
attribution weights — are **NEVER** written into the file. They are
recomputable from canonical text. Shipping them inside the file would
freeze substrate evolution. The file carries the **canonical text**, the
**user's blocks**, **user-asserted edges**, and a **creator signature**.

If you find yourself adding chunks / embeddings / substrate-derived edges
"for completeness", you are off-spec. See the `_FORBIDDEN_SUBSTRATE_FIELDS`
list at the top of `native_writer.py` — M7 greps the bytes against it.

---

## 2. File layout (zip archive)

A `.antiek` file is a ZIP archive (uncompressed file order is deterministic;
see §6). Top-level entries:

```
<container>.antiek            ← zip archive
├── manifest.json             ← schema-versioned metadata (REQUIRED)
├── content.tiptap.json       ← TipTap document body (REQUIRED)
├── edges.jsonl               ← user-asserted cross-content edges (OPTIONAL)
├── blocks/                   ← block-level binaries (OPTIONAL)
│   └── <block_id>.audio      ←     voice-block audio (1 per voice block)
└── signature.bin             ← detached Ed25519 signature (REQUIRED)
```

No other entries are permitted. Readers MUST reject (or ignore — see §7
"version policy") any unexpected entry.

### 2.1 manifest.json

UTF-8 JSON, validates against `manifest.schema.json` (in this directory).

Required keys:

| Key                  | Type                    | Notes                                           |
| -------------------- | ----------------------- | ----------------------------------------------- |
| `schema_version`     | semver string "M.m.p"   | This document defines "1.0.0".                  |
| `content_class`      | enum                    | `notebook`, `theme_notebook`, or `deliverable`. |
| `document_id`        | string                  | Substrate-resident id; matches `notebook_documents.document_id` for notebooks. |
| `parent_document_id` | string \| null          | Source PDF for a per-doc notebook. `null` for theme/deliverable. |
| `created_at`         | ISO 8601 UTC            | First-save time.                                |
| `creator_user_id`    | string                  | Substrate user id.                              |
| `creator_pubkey`     | base64-encoded 32 bytes | Ed25519 public key of the creator at write time. |

Optional keys:

| Key                | Type   | Notes                                                                                       |
| ------------------ | ------ | ------------------------------------------------------------------------------------------- |
| `title`            | string | Display title; falls back to source-document title on read.                                  |
| `notebook_id`      | string | Substrate-resident notebook id. Carried so the reader can route back to substrate rows.      |
| `format_version`   | int    | `services.notebooks.blocks.BLOCK_TAXONOMY_VERSION` at write time.                            |
| `blocks_index`     | array  | Manifest of block_id + block_type + position + source_event_ids + audio? (REQUIRED for `notebook` and `theme_notebook` — the source-of-truth list for the structured block index when the reader re-hydrates substrate rows. **Not the same as the TipTap body — see §2.2.**) |
| `edges_present`    | bool   | Hint flag — does `edges.jsonl` exist? (Reader can skip the zip-entry probe.)               |

`blocks_index` rows look like:

```json
{
  "block_id":         "blk-...",
  "block_type":       "voice_block",
  "position":         1.0,
  "source_event_ids": ["evt-..."],
  "audio_path":       "blocks/blk-....audio"
}
```

The same data lives inside `content.tiptap.json` (TipTap nodes carry
`attrs.block_id` and `attrs.block_type`). The `blocks_index` denormalises
it so the reader doesn't have to walk the TipTap tree just to enumerate
blocks. On read, **if `blocks_index` and the TipTap body disagree, the
TipTap body wins** (it is the canonical text). The reader logs a warning
and reconciles by re-walking the body.

### 2.2 content.tiptap.json

UTF-8 JSON. The canonical TipTap document. A TipTap doc is:

```json
{
  "type": "doc",
  "content": [<node>, ...]
}
```

Each block is a TipTap node whose `attrs.block_id` matches a row in the
substrate's `per_doc_notebook_blocks` table. The closed block taxonomy (six
types, see `services/notebooks/blocks.py`) maps 1:1 to TipTap node types
named `antiek_<block_type>` (e.g. `antiek_highlight_card`).

**This file is the source of truth for the document body.** The
`blocks_index` in the manifest is a denormalisation; substrate-resident
data (`per_doc_notebook_blocks.content_json`) is rebuildable from this file.

### 2.3 edges.jsonl

One JSON object per line. Each entry is a **user-asserted** cross-content
edge:

```json
{"edge_id": "edg-...", "from_block_id": "blk-A", "to_content_hash": "<hex>",
 "to_document_id": "doc-...", "kind": "supports|contradicts|extends|references",
 "asserted_at": "2026-...", "operator_note": "string|null"}
```

`to_content_hash` is the SHA-256 of the target `.antiek` file's
`content.tiptap.json` (lowercase hex). This is how a cross-content edge
addresses a target by **content** (not by mutable id), surviving
graph-rebuilds and re-publishes.

Substrate-derived edges (auto-discovered cross-doc links, semantic
nearest neighbours, citation graph) MUST NOT appear here. The substrate
recomputes those.

### 2.4 blocks/*

Binary payloads referenced by a block. Today (SPR-09): voice-block audio
under `blocks/<block_id>.audio`. Filename = block_id; extension = `.audio`
(format-detection on read; no extension lookup table). Other block-binary
types (image regions, sketch SVG) would land here in future sprints.

**Substrate gap (M2 honest flag, 2026-05-21):** the substrate today
stores **transcripts** for voice notes (Sprint 13 ASR pipeline), not the
underlying audio bytes. The writer is implemented to embed audio when it
is reachable via a `content_json["audio_bytes"]` or
`content_json["audio_blob_path"]` hint, and to skip silently when neither
is available. The reader extracts to substrate-managed storage and
rewrites the block's `audio_blob_path` accordingly. Wiring an audio-bytes
store into the substrate is **not** SPR-09 work — it is flagged in the
SPR-09 handoff.

### 2.5 signature.bin

64 raw bytes — an Ed25519 detached signature. See §3 ("Signing input").

---

## 3. Signing input (canonical bytes)

The signature is computed over a concatenation of three canonicalised
sections in this fixed order:

```
canonical(manifest.json)        ← bytes
0x1F                            ← unit separator (1 byte)
content.tiptap.json bytes       ← raw bytes from the zip entry
0x1F                            ← unit separator
edges.jsonl bytes               ← raw bytes; empty when no edges
```

Canonicalisation rules (the writer applies these; the reader recomputes
to verify):

1. **JSON files** (`manifest.json`): keys sorted, `ensure_ascii=False`,
   no trailing whitespace, no insignificant whitespace, UTF-8 LF line
   endings (one trailing newline).
2. **TipTap body** (`content.tiptap.json`): keys sorted, same rules.
3. **edges.jsonl**: per-line objects with sorted keys; lines sorted by
   `edge_id`; LF line endings; trailing newline.
4. **Unit separator** is the single byte `0x1F` (US, ASCII unit
   separator). This is to prevent length-extension confusion between
   sections without inventing a length prefix.
5. **Binary block payloads** (`blocks/*.audio`) are **not** included in
   the signing input. Their integrity is covered by SHA-256 hashes in
   `blocks_index[*].audio_sha256` (the writer fills this; the reader
   verifies against the extracted bytes). The rationale is that audio
   bytes can be very large and we don't want signature verification to
   require streaming them, but we do need integrity. The hashes are
   inside the signed manifest, so a tampered audio file fails the
   reader's per-block integrity check.

Verification proceeds: read the file, recompute canonical bytes,
compute SHA-256 over each `blocks/<id>.audio` and compare to manifest's
`blocks_index[].audio_sha256`, then `ed25519.verify(signature_bin,
canonical_bytes, creator_pubkey)`. Failure on any sub-check → return the
notebook with `signature_valid: false`.

### 3.1 Key management

User has a long-lived Ed25519 keypair generated on first `.antiek` save.
The private key lives in substrate user-settings storage; it never
leaves the substrate-resident database. The public key is stamped into
the manifest at every save.

**Open question (documented in `SIGNATURE_NOTES.md`):** what happens
when a user re-generates a keypair? Answer: old files retain their old
signature (verified against the old `creator_pubkey` carried in the
file). They are **not** invalidated. The substrate-side user-settings
table is append-only on key rotation.

---

## 4. Round-trip identity

A writer's output must satisfy:

```
write(notebook)  →  bytes
read(bytes)      →  notebook'
canonical_tiptap(notebook.content_json) == canonical_tiptap(notebook'.content_json)
```

`canonical_tiptap` is defined in `native_reader.canonical_tiptap` and
described in §5. Naive `==` may fail on whitespace, key ordering, or
attribute order differences that TipTap considers equivalent.

---

## 5. TipTap canonicalisation (`canonical_tiptap`)

TipTap documents have an idiosyncratic JSON shape. The canonicalisation
used for **equality** (not signing — signing canonicalises the full file)
is:

1. Walk the doc tree depth-first.
2. At each node, sort keys: the canonical order is
   `[type, attrs, marks, content, text]` then any other keys
   alphabetically. Unknown keys preserved.
3. `attrs` objects: keys sorted alphabetically. `null`-valued attrs are
   dropped (TipTap treats absent and null as equivalent for many marks
   per its serialization docs).
4. `marks` arrays: sorted by `(type, JSON-stringified attrs)`.
5. Text nodes: `text` is preserved byte-for-byte (no whitespace
   collapsing — TipTap does not collapse).
6. Empty `content` arrays dropped (TipTap omits them on serialise).
7. The result is JSON-serialised with sorted keys, no extra whitespace,
   UTF-8. Two documents are TipTap-equal iff their canonical bytes are
   `==`.

This matches the rules in TipTap's "JSON serialization" docs (TipTap v2:
nodes with no content omit the `content` key; marks order is unspecified
by the editor and stabilised here).

---

## 6. Deterministic zip writing

To make "same notebook → byte-identical `.antiek`" mechanically testable,
the writer:

1. **Sorts files** by full path before adding to the archive. Order:
   `manifest.json`, `content.tiptap.json`, `edges.jsonl` (if present),
   `blocks/<sorted>...`, `signature.bin`.
2. **Fixed timestamps** — every zip entry has `date_time = (1980, 1, 1,
   0, 0, 0)`. (zip's minimum representable timestamp.) Modification time
   is **not** semantic content.
3. **Fixed `create_system` = 3** (UNIX) and **`external_attr` = 0o644
   << 16**.
4. **No compression** (`ZIP_STORED`). Compression is non-deterministic
   across `zlib` versions and would make the byte-identical claim brittle.
   Size-overhead is small; .antiek files are not a streaming format.
5. **No extra fields**, no comments.

Determinism is a load-bearing property: the signature is computed over
**canonical bytes**, not over the zip envelope, so zip non-determinism
does not break signature verification — but if two writers produce two
different-byte `.antiek` files for the same notebook, downstream content
addressing (the `to_content_hash` in `edges.jsonl`) breaks. We test
byte-equality at the zip level to catch this regression early.

---

## 7. Version policy

`manifest.schema_version` is semver. The reader's policy:

- **Major-version mismatch** (`reader_major != file_major`) → raise
  `UnsupportedVersion`. The reader refuses to parse. Caller may fall back
  to markdown projection.
- **Minor-version mismatch** (`file_minor > reader_minor`) → log a
  warning, proceed. Unknown manifest keys are preserved on a round-trip
  (the reader does not strip them).
- **Patch-version mismatch** → silent. Patch bumps are documentation /
  test-suite changes.

The reader's supported version is `services.antiek_format.SCHEMA_VERSION`
in `native_reader.py`. Today: `"1.0.0"`.

### 7.1 Unknown zip entries

If the file contains a top-level entry that isn't in the §2 list (e.g.
`embeddings.parquet`, `chunks.jsonl`), the reader logs a warning and
ignores it on a same-major-version file. On a different-major-version
file it is part of `UnsupportedVersion`'s refusal.

This is deliberate: it lets future major versions add files, while
forbidding the **current** major version from sneaking substrate data in.

---

## 8. Markdown projection (one-way)

`project_to_markdown(bytes) -> str` produces a fallback `.md` for tools
without Antiek installed. The projection is **lossy and one-way**:

- Highlight cards → blockquote (`> ...`) prefixed with the source passage.
- Voice blocks → `(voice note: <duration>)` text + a markdown link to the
  extracted audio file (sibling `blocks/` directory).
- AI Q&A → `**Q:** ... \n\n**A:** ...` with the source attribution as
  italicised text on the next line.
- Cite links → standard markdown link `[label](deeplink)`.
- Cross-doc jumps → markdown link-reference `[label][doc-id]`.
- Prose → passthrough.
- User-asserted edges (`edges.jsonl`) → an "Asserted edges" appendix
  section at the bottom of the document.
- The signature is **not** projected (markdown has no canonical-bytes
  primitive; signing would be meaningless).

The projection's first line is the header comment:

```
<!-- Projected from .antiek (SPR-09 universal-fallback). Lossy: blocks,
     voice playback, and signed edges are rendered as best-effort prose.
     Round-trip is NOT supported. Open the .antiek in Antiek to edit. -->
```

---

## 9. What MUST NOT appear in a `.antiek` file

(See `_FORBIDDEN_SUBSTRATE_FIELDS` in `native_writer.py`. M7 greps bytes
against this list.)

- `chunks` / `document_chunks` / `chunk_text` / `chunk_embedding`
- `embedding` / `embeddings` / `embedding_vector`
- `graph_edges_auto` (substrate-derived edges)
- `attribution_weights` / `attribution_scores`
- `reward_proxy_*` / `reward_signal`
- Anything else the substrate computes from canonical text

This list is checked by `tests/test_e2e.py::test_no_substrate_data`.
If a future block type needs to carry substrate-derived metadata, the
right move is to **not** carry it — it is recomputable.

---

## 10. Out of scope for SPR-09

- Round-trip Markdown ↔ `.antiek` (projection is one-way).
- Federated handshake between Antiek instances (Sprint 30+).
- Schema migration tooling for future format versions (handle inline
  when needed; the version policy in §7 covers the common case).
- EPUB / MOBI / DOCX exports.
- Mobile reading.
- Embedding chunks / embeddings / graph edges — explicitly forbidden
  (see §9).
- Multi-author signatures.

---

## 11. Sidecar Variant (SPR-10)

A **`.antiek` sidecar** carries user-derived data for an imported PDF
that the substrate does NOT own (the PDF is the source of truth; the
sidecar travels alongside on share / re-import). The PDF stays a plain
PDF — any reader on any platform handles it natively. The sidecar
restores the user's annotations when re-imported into Antiek.

Same zip envelope as §2, same signing scheme as §3, same determinism
rules as §6 — only the content shifts. The discriminator is
`manifest.content_class == "pdf_sidecar"`.

### 11.1 Manifest delta

Sidecar manifests share the §2.1 required keys (schema_version,
content_class, document_id, parent_document_id, created_at,
creator_user_id, creator_pubkey) and add THREE required keys when
`content_class == "pdf_sidecar"`:

| Key                         | Type             | Notes                                                                                       |
| --------------------------- | ---------------- | ------------------------------------------------------------------------------------------- |
| `parent_pdf_sha256`         | lowercase hex 64 | SHA-256 of the parent PDF bytes. The reader refuses to apply the sidecar if this does not match the imported PDF's hash. |
| `parent_pdf_size_bytes`     | non-negative int | Byte length of the PDF at write time. Surfaces a faster "this is the wrong PDF" warning before the full hash compute. |
| `parent_pdf_filename_hint`  | string \| null   | Original basename. INFORMATIONAL — never used for matching; only shown to the user when the hash check fails so they can recognise the intended PDF. |

`content_class` enum is extended: `notebook` | `theme_notebook` |
`deliverable` | `pdf_sidecar`. `document_id` for a sidecar is the
imported-PDF document_id (matches the substrate's `documents.document_id`
of the parent PDF; SPR-03's pipeline derives this as
`doc-pdf-<sha256_prefix>`). `parent_document_id` is the same value
(a sidecar IS its parent; the field is preserved for shape symmetry
with notebooks).

`blocks_index` is NOT used by sidecars — the data lives in
`highlights.jsonl` and `anchors.jsonl` (see §11.2). A sidecar SHOULD
omit `blocks_index` or set it to `[]`.

Optional sidecar-only manifest keys:

| Key                       | Type           | Notes                                                                |
| ------------------------- | -------------- | -------------------------------------------------------------------- |
| `highlights_present`      | bool           | Hint flag — does `highlights.jsonl` exist?                          |
| `anchors_present`         | bool           | Hint flag — does `anchors.jsonl` exist?                             |
| `chunker_version_at_write`| string \| null | Substrate's `CHUNKER_VERSION` at write time. **Informational only** — the receiving substrate re-resolves each `(page, bbox)` under its own chunker; see §11.3. |

### 11.2 Zip layout

```
<basename>.antiek                ← zip archive (sidecar)
├── manifest.json                ← REQUIRED — content_class: "pdf_sidecar"
├── content.tiptap.json          ← REQUIRED — empty {"type":"doc","content":[]}
├── edges.jsonl                  ← OPTIONAL — user-asserted edges (same shape as §2.3)
├── highlights.jsonl             ← OPTIONAL — one user highlight per line
├── anchors.jsonl                ← OPTIONAL — voice-anchor rows (one per line)
├── blocks/                      ← OPTIONAL — voice-block audio bytes
│   └── <voice_note_id>.audio
└── signature.bin                ← REQUIRED — detached Ed25519 signature
```

Rationale for the empty `content.tiptap.json`: keeping it required
across both variants lets the reader use one zip-validation path and
keeps the signing input shape stable (manifest + content + edges are
always the first three signed sections). The sidecar's user data
lives in two **additional** signed sections (highlights.jsonl,
anchors.jsonl); see §11.4.

#### highlights.jsonl

One JSON object per line. Each row:

```json
{"highlight_id":"hl-...","document_id":"doc-pdf-<hex>","page":3,
 "bbox":{"x0":40.5,"y0":120.0,"x1":480.0,"y1":160.0},
 "passage_text":"selected text","color":"yellow","tag":null,
 "created_at":"2026-05-21T12:30:00+00:00","operator_note":null}
```

`bbox` mirrors the SPR-02 `BBox` shape (PDF user-space, origin
bottom-left). `passage_text` is the canonical text the user selected
(carried so a hash-mismatch sidecar still surfaces the user's words —
even if coordinates land elsewhere on a different PDF, the operator
note remains legible).

Substrate landing point: highlights restore as `behavior_events` of
type `highlight_created` (the substrate has no `highlights` table —
it persists them as events; see `substrate/behavior/schemas/
highlight_created.json`). Lines are sorted by `highlight_id` for
deterministic signing.

#### anchors.jsonl

One JSON object per line. Each row is the carrier for one voice
note + its anchor:

```json
{"anchor_id":"vna-...","voice_note_id":"doc-vn-<hex>","document_id":"doc-pdf-<hex>",
 "page":3,"bbox":{"x0":50.0,"y0":80.0,"x1":300.0,"y1":140.0},
 "chunk_id":"chk-...","chunker_version":"v1.0.0",
 "transcript":"voice transcript text",
 "audio_path":"blocks/doc-vn-<hex>.audio",
 "created_at":"2026-05-21T12:32:00+00:00"}
```

`chunk_id` and `chunker_version` are **informational only on read**.
The receiving substrate re-resolves the chunk_id by calling
`substrate.voice.anchor_api.resolve_chunk_for_bbox(con, document_id,
page, bbox)` against the LOCAL chunker (see §11.3). The
chunker_version field is carried so the reader can surface a "writer
used chunker v1.2; this substrate is on v1.0; some anchors may move"
warning if a delta is detected.

Lines are sorted by `anchor_id` for deterministic signing. The
`voice_note_id` field is the document_id of the voice-note row in
the receiving substrate's `documents` table (voice notes live as
`documents` with `document_type='voice_note'` — there is NO
`voice_notes` table; the SPR-02 spec page mis-stated this and the
authoritative location is `substrate.voice.anchor_schema`).

#### blocks/<voice_note_id>.audio

Same as §2.4. Audio bytes for a voice note, when reachable.
SHA-256 hashes for integrity are stamped into the manifest's
`audio_blobs_index` (sidecar-only field analogous to `blocks_index`'s
audio_sha256 — see §11.4). When the substrate audio-store gap (SPR-05
/ SPR-09) closes, audio rides along; until then the writer skips
silently. The reader extracts to substrate-managed storage.

### 11.3 Re-resolving anchors under the receiving chunker (rigor #3)

The writer records `chunker_version` for each anchor row. The reader
**does NOT trust it**. For each (page, bbox) the reader calls
`resolve_chunk_for_bbox(con, document_id=<imported PDF doc_id>,
page=row.page, bbox=row.bbox)` against the receiving substrate's
chunker. The returned `chunk_id` is what gets written into
`voice_note_anchor.chunk_id`; the writer's value is discarded.

Why this design: chunkers evolve. Freezing chunk_ids inside the file
would put the receiving substrate in an impossible position when its
chunker version differs from the writer's — either trust a stale id
(wrong) or refuse to import (worse). The coordinate is the durable
key; the chunk_id is a derived join column that re-derives cleanly.

The current substrate's `resolve_chunk_for_bbox` returns `None`
(geometry gap — chunks don't carry per-chunk page+bbox columns yet;
see `substrate/voice/anchor_api.py` docstring). That doesn't break
the contract: the anchor row still writes (chunk_id=NULL is valid
per SPR-02 schema), and the re-chunk worker will populate chunk_id
when chunks gain geometry.

### 11.4 Signing input for sidecars

Same scheme as §3, extended with two trailing sections:

```
canonical(manifest.json)
0x1F
content.tiptap.json bytes  (typically the empty-doc bytes)
0x1F
edges.jsonl bytes          (b"" when absent)
0x1F                       ← sidecar-only separator
highlights.jsonl bytes     (b"" when absent)
0x1F                       ← sidecar-only separator
anchors.jsonl bytes        (b"" when absent)
```

For non-sidecar variants the signing input ends after the edges
section (no trailing separators). The reader chooses signing-input
shape by the manifest's `content_class`: `pdf_sidecar` → 5-section
input; everything else → 3-section input. This is the one place the
reader uses `content_class` as a control variable rather than a
data field.

Canonical bytes for `highlights.jsonl` and `anchors.jsonl` follow
the same rules as `edges.jsonl` (per-line sorted-key JSON, lines
sorted by their primary id — `highlight_id` and `anchor_id`
respectively — trailing LF, ASCII-safe).

Audio integrity for sidecars uses the same per-file SHA-256 stamped
into manifest pattern as §3 rule 5. The manifest field is
`audio_blobs_index` (sidecar-only): an array of
`{voice_note_id, audio_path, audio_sha256}` rows. The hashes are
inside the signed manifest, so audio tampering is caught without
streaming the bytes into the top-level signature scope.

### 11.5 Reading + restore

`read_sidecar(data: bytes, *, imported_pdf_sha256: str | None) ->
RestoredSidecar` parses the bytes, validates manifest, verifies
signature, then:

1. If `imported_pdf_sha256` is supplied and differs from
   `manifest.parent_pdf_sha256` → return `RestoredSidecar` with
   `hash_mismatch=True` and `applied=False`. The caller decides
   whether to surface as a warning or hard refusal; the
   substrate-write helper (`apply_sidecar`) refuses by default.
2. Else, the caller invokes `apply_sidecar(restored, con=..., user_id=...)`
   which:
   - Re-resolves each anchor's `chunk_id` under the receiving
     substrate's chunker (rigor #3).
   - Inserts highlights as `behavior_events` of type
     `highlight_created` (idempotent on `highlight_id` via the
     event's action payload — see `_apply_highlights_idempotent`).
   - Inserts voice-note documents + anchor rows (idempotent on
     `voice_note_id`).
   - Inserts user-asserted edges (idempotent on `edge_id`).
   - Extracts audio bytes to substrate-managed storage (idempotent
     on path).
3. If signature verification failed, the caller still proceeds with
   `apply_sidecar` but every inserted row is flagged with
   `imported_from_unsigned_sidecar: true` in its event payload /
   metadata. See §11.6 for the rationale.

### 11.6 Signature-invalid restore proceeds (rigor #5)

A "friend sends a sidecar over WhatsApp" flow is the canonical share
path. The friend's signing pubkey is not in the receiving user's
known-key set. The conservative choice — refuse — would break the
share flow that motivates the sidecar in the first place. The chosen
behavior: **restore proceeds, rows are flagged**. The user can
inspect the imported state under a clearly-marked "unsigned import"
ribbon. Future hardening (if friend-pubkey-authorisation becomes a
product surface) replaces the flag with a per-key trust decision
inside `apply_sidecar`; the trail of which rows came from which
sidecar is preserved on the inserted rows' metadata.

The integrity-of-bytes layer (per-audio SHA-256 inside the signed
manifest) does NOT change. A sidecar whose audio bytes are tampered
fails the per-blob hash check and is treated as tampered for that
blob; the rest of the sidecar still restores.

### 11.7 Hash-mismatch UX (rigor #1)

If `imported_pdf_sha256 != manifest.parent_pdf_sha256`, the sidecar
was made for a different PDF. Coordinates will likely land on the
wrong text. The UI text MUST be honest about the failure mode:

> "This `.antiek` sidecar was made for a different version of the
> PDF you imported (file hash differs). Restoring would place
> annotations at coordinates from the original PDF; on this PDF
> they may land on the wrong text. The sidecar was NOT applied."

Optional refinement (when surfaced): if both PDFs share at least one
page (which is trivially true for any non-empty PDFs), the reader
can report `len(sidecar_pages_used) - len(receiving_pdf_pages)` so
the user knows whether the sidecar is "close" (one revision later)
or "wildly off". For SPR-10 we surface the boolean only — page-
count delta is documented as a follow-up.

### 11.8 What MUST NOT appear in a sidecar

Same invariant as §9. The forbidden substrate-derived field list
applies identically to a sidecar. A sidecar carries USER data — the
substrate-derived chunk_ids it references in `anchors.jsonl` are
informational only (the reader re-derives them under its own
chunker). Per the master-spec invariant, the byte-grep over
forbidden field names from `_FORBIDDEN_SUBSTRATE_FIELDS` is run on
every sidecar write; the test for it is the same M6 test path that
guards notebooks.

### 11.9 Idempotency

A sidecar may be applied multiple times. The reader's `apply_sidecar`
is idempotent:

- Highlights: keyed on `highlight_id`. Repeated apply → no new
  `behavior_events` row (the event's action.highlight_id is the
  idempotency key).
- Voice anchors: keyed on `voice_note_id` (the SPR-02 UNIQUE
  constraint).
- User-asserted edges: deduped on `edge_id` against any prior import
  trail. (Substrate today has no user-edges table; the dedupe is
  against the same-process metadata trail per restore — when an
  edges table lands, the dedupe joins that table.)
- Audio bytes: written to `<storage_root>/<voice_note_id>.audio`;
  pre-existing files with matching sha256 are left alone.

Mechanically tested by M6 (`test_idempotent_apply`).
