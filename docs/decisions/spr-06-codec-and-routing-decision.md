# SPR-06 M1 — codec decision + routing survey (Read/Write projections)

**Status: DECISION (M1 done).** Records the shared-codec-vs-adapter decision,
the share-route survey, and the M2 rights design — so M2/M3 build against
evidence and the M4/M5 blocker is on the record, not discovered twice.

## Codec decision

- **Notebooks (Tier-2/3) render through the SPR-02 renderer directly — no new
  codec.** `substrate/notebooks/tiptap_codec.py` decomposes a TipTap doc into
  blocks whose node types (`claim_card`, `region_embed`, `note_block`,
  `cross_doc_link`, `master_md_section`, `question_card`, `chat_exchange`,
  `image`, `math_block`) are **exactly** the set the renderer's partials
  already handle (`services/html_projection/partials/`). So a notebook's
  `content.tiptap.json` is already a valid renderer doc-model — the same path
  the SPR-04 shell uses. The notebook "adapter" (M2) is therefore not a
  doc-model transform but a **rights-aware resolver** (see below).
- **Write deliverables use a dedicated adapter** (`adapters/deliverable.py`),
  NOT the shared codec. The Write substrate (`substrate/write/`:
  `outline_block.py`, `brainstorm_blocks.py`, `draft_generation.py`,
  `outline.py`, `promote_context.py`) is a separate block model built in the
  2026-05-25 stream; its block types are not in the notebook taxonomy. Mapping
  them in an adapter (mirroring SPR-05's synthesis adapter) keeps Write-only
  block types rendering a **visible unsupported-placeholder**, never a silent
  drop. *What would reverse it:* if a survey of the Write serializer shows it
  already emits TipTap nodes in the notebook taxonomy, the adapter collapses to
  the direct path — record the flip, don't bridge with lossy glue.

## M2 rights design (the leak surface differs from SPR-05)

In SPR-05 the adapter **built** the doc-model, so the rights filter dropped
chunk text from the serialized doc-model (the island). A notebook is different:
its `content.tiptap.json` carries **ref_ids**, not inline third-party text, and
the chunk text is resolved **live at render time** by `ctx.resolver`
(`services/html_projection/context.py`, protocol `(ref_id, block_type) ->
ResolvedRef | Tombstone`). Therefore:

- The **leak surface for notebooks is the resolver output (the rendered HTML)**,
  not the island — the island carries ref_ids. M2's rights gate is a
  **rights-aware resolver** that resolves `ref_id → chunk → document →
  content_class` and, for a non-servable source (`personal_reading` /
  `restricted_pending_opt_in` / NULL per the SPR-05 contract,
  `SERVABLE_CONTENT_CLASSES`), returns a **cite-only payload** (title +
  ip_holder, text withheld) instead of the passage. A deleted/missing ref
  returns a `Tombstone` (the renderer already renders it).
- The M2 rights test asserts on BOTH: the resolved payload for a
  `personal_reading` ref carries no passage text, AND the rendered HTML omits
  it. (If any notebook node type is found to store inline passage text in its
  TipTap attrs, that node ALSO needs island-level stripping in the adapter — a
  per-node-type audit M2 must run before freezing goldens.)

## Share-route survey — M4/M5 BLOCKED on this branch

**`api/themes.py` and `api/share_bundle.py` do not exist on
`html-projection/land-antiek`.** The spec assumed they "landed with the format
in SPR-01"; a tree search (excluding `.venv`/tests) finds neither. The actual
route layer is `interfaces/research/api/` and contains no themes/share_bundle
module. This is the same class of cross-branch gap as the SPR-04 sidecar tests
and the SPR-07 ingestion surface — features that land on other branches.

Consequence: **M4 (container emission through the share routes + the single
`routing_map.py`) and M5 (rights parity across routes) are blocked** — you
cannot wire emission into routes that do not exist, and *creating* the share
routes is explicitly out of scope (the spec extends existing routes; minting a
new share surface is a different sprint's transport). When the share routes
land on this branch, M4 wires them to the SPR-04 shell writer through one
routing map (the `.html` / `.antiek` / `.antiek.html` table), with the
byte-compare parity gate; M5 reuses the SPR-05 contract identically on every
path. The SPR-04 writer (`services/antiek_format/native_writer.write_antiek`)
and single-file variant (`single_file.build_single_file`) are ready to call.

## Buildable plan (this branch)

- **M2** — `adapters/notebook.py`: the rights-aware resolver + the direct
  doc-model path; Tier-2/3 goldens, deleted-ref tombstone, `personal_reading`
  cite-only (asserted on resolver output + HTML).
- **M3** — `adapters/deliverable.py`: Write blocks → doc-model, unsupported
  placeholder for Write-only types (enumerate them), rights filter applied.
- **M4/M5** — deferred until the share routes exist on this branch.

## Out of scope (recorded)

Tier-1 behavior-event export stays out (privacy-gated RL data); the user loses
in-artifact replay of their own reading session — a future operator decision,
not this sprint's.
