# Lane: connect the two halves of the HTML thesis

Branch `lane/htmlbridge-20260919`, commit `9bede522e`. SPR-1 and SPR-2 both
shipped. SPR-3 and SPR-4 were out of scope and were not touched.

## What is now true that was not

`GET /documents/{document_id}/render?style=academic-paper` returns an ingested
PDF, web page or `.docx` as a script-free Antiek artifact: headings at their
source levels, lists nested, tables as real `<table>` grids, an inert data
island carrying the doc-model, a provenance footer naming the document, and the
chosen style's stylesheet inlined. Switching `?style=` re-renders the same
bytes under a different stylesheet. That is the thesis, end to end.

Three files carry it:

- `services/html_projection/adapters/document.py` — parses the sanitized
  reader-HTML sidecar body into the TipTap-shaped doc-model.
- `services/html_projection/partials/_structural.py` plus six one-screen entry
  points — the document vocabulary the renderer did not have.
- `interfaces/research/api/style_routes.py` — the route.

## Where I contradicted the brief, and why

**The brief's SPR-1 mapping cannot satisfy the brief's own done-bar.** It asks
for "paragraphs/lists/tables to `antiek_prose`". The `antiek_prose` partial
renders through `partials/_common.inline_text`, which flattens a content array
to a run of escaped inline text inside one `<p>`. A table mapped to
`antiek_prose` comes out as `col a col b A-1 11.4 dry A-2 9.8 wet` — one
paragraph, no grid. Done-bar item 5 asks for "a real `<table>` in the projected
output". Those two instructions are incompatible.

I resolved it in favour of the done-bar, because the done-bar is describing the
outcome and the mapping was describing a route to it. A table flattened into a
sentence is not a formatting loss, it is a data loss: the reader can no longer
tell which mass belongs to which sample.

So the contract table grew six rows — `heading`, `list`, `table`, `code_block`,
`blockquote`, `horizontal_rule` — using the standard TipTap node names
(`heading` / `bulletList` / `orderedList` / `blockquote` / `codeBlock` /
`table` / `horizontalRule`), so the doc-model stays a genuine TipTap document
that an editor could round-trip. Each row cites the `file:line` in
`acquisition/snapshot/reader_html.py` that emits it and the `ALLOWED_TAGS` line
in `substrate/books/html_sanitizer.py` that lets it survive, as that module's
own convention requires. I checked those line numbers against the tree rather
than guessing them.

Headings keep their source level rather than being demoted by one to sit under
the artifact's `<h1>` title. A document with a title and a source `<h1>` now has
two `<h1>`s. That is deliberate: demoting everything would make the projected
outline disagree with the source outline, and the source outline is the thing
the reader is trying to read. The reasoning is inline in `partials/heading.py`.

**Everything else in the brief held up.** `style_routes._user_id` does accept
`"__operator__"` and I left it alone. `substrate/reader_html/store.py`
`serve_reader_html` is the right read path. `acquisition/snapshot/reader_html.py`
does now emit real GFM, and it was the right thing to adapt from.

## The rule that shaped the design

An unmapped construct becomes a node typed `source:<tag>`. That type is outside
the contract table *by construction*, so it renders through the contract's own
unsupported fallback as `unsupported block (source:dl)` — visible, named, and
impossible to confuse with absence. Its text rides along in the node's
`content`, so the island round-trips what the visible surface admits it could
not draw.

The tradeoff I took, and the one I am least certain about: the unmapped
construct's TEXT does not appear on the visible surface, only the marker. That
is `partials/unsupported.py`'s existing, documented decision — it deliberately
does not inline node JSON into the visible HTML — and I did not want to erode it
from the adapter side. The cost is that an ingested `<dl>` currently shows a
marker where a reader would rather see the definitions. If that reads badly in
practice, the fix is a `definition_list` contract row, not a change to the
fallback.

## Commands, with real output

All run from the worktree root with `/Users/slimydog/Antiek/platform/.venv/bin/python` (3.12.13).

```
$ python -m pytest services/html_projection/tests/ tests/test_style_api.py \
    tests/test_user_style_store.py tests/test_reader_html_store.py \
    tests/test_reader_html_api.py tests/test_reader_snapshot.py \
    tests/test_document_render_api.py tests/test_html_projection_contract.py -q
562 passed, 1 warning in 45.39s
```

Baseline before any edit, same command set minus the two new files: `472 passed`.

```
$ python -m pytest tests/api/test_deliverable_artifact.py tests/api/test_notebook_artifact.py \
    tests/api/test_synthesis_artifact.py tests/api/test_notebook_export_integration.py \
    tests/api/test_deliverable_export_integration.py tests/test_research_artifact_export.py \
    tests/test_feedback_artifact_anchor.py tests/test_derived_asset_evidence_boundary.py -q
47 passed, 1 warning in 5.36s
```

(The existing consumers of the projection engine — the export/artifact routes —
still pass, which is what makes the contract expansion safe rather than merely
additive-looking.)

```
$ python -m ruff check services/html_projection interfaces/research/api/style_routes.py tests/test_document_render_api.py
All checks passed!

$ python -m mypy services/html_projection/adapters/document.py services/html_projection/partials/_structural.py \
    services/html_projection/partials/heading.py services/html_projection/partials/table.py \
    services/html_projection/partials/list_block.py services/html_projection/partials/blockquote.py \
    services/html_projection/partials/code_block.py services/html_projection/partials/horizontal_rule.py
Success: no issues found in 8 source files

$ python -m mypy services/html_projection/renderer.py services/html_projection/contract.py services/html_projection/tokens.py
Success: no issues found in 3 source files
```

`mypy interfaces/research/api/style_routes.py` reports 252 errors across 54
files in its transitive import graph and **zero** in `style_routes.py` itself
(`grep -c '^interfaces/research/api/style_routes.py'` → `0`). Those 252 are the
pre-existing parked mypy debt, not this branch's.

Repo lints:

```
serve_guard_check -> exit=0        boundary_check -> exit=0
serve_invariants_check -> exit=0   owner_boundary_check -> exit=0
register_check -> exit=0           reachability_gate_py -> exit=0
source_gate -> exit=0              reading_physics_check -> exit=0
contact_guard_check -> exit=0      model_ref_validation_check -> exit=0
rate_governor_check -> exit=0      owner_privilege_check -> exit=0
retrieval_gate_check -> exit=0
uniqueness_registry -> exit=1      test_desiderata_check -> exit=1
```

Both reds are pre-existing. I verified that by `git stash -u` and re-running
them at the base commit: `uniqueness_registry at BASE -> exit=1`,
`test_desiderata_check at BASE -> exit=1`. The uniqueness failure is a missing
frontend component (`WernerIceCursorShell`); the desiderata failure is 99
wall-clock-in-assertion findings, none of them in either file I added
(`grep -E 'test_document_render_api|test_document_adapter'` over its output →
no hits).

## Done-bar, item by item

1. **Ingested document renders with a wheel style** —
   `tests/test_document_render_api.py::test_ingested_document_renders_with_a_wheel_style`.
   It seeds a real `documents` row, writes the sidecar through
   `store_reader_html` (which sanitizes inside the call, so the body under test
   is the body ingest would have stored), and asserts the rendered artifact
   carries `<h2 class="antiek-heading">Samples</h2>`, `<td>11.4</td>`,
   `<ul class="antiek-list">`, the academic theme's serif stack, and zero gate
   violations.
2. **Switching style, no model call** — two tests. One asserts that for two
   styles everything after `</style>` is byte-identical and the islands are
   equal. The other asserts two independent requests at the same style return
   identical bytes and identical `X-Content-SHA256`. Byte-identity across
   requests is the part a generation step could not give you; the structural
   argument is that the whole path is parse-plus-template over stored bytes.
3. **`extract_island(render(doc, style)) == doc` for every style** —
   `test_island_round_trips_for_every_style_in_the_wheel`, iterating
   `default_registry().list_styles()` (all five builtins).
4. **Unmapped renders visibly and is not dropped** —
   `test_unmapped_construct_renders_visibly` asserts the placeholder names the
   tag AND that the node with its text comes back out of the island.
   `test_unmapped_is_not_confusable_with_absence` is its red-proof: a document
   without the construct produces no placeholder, so the marker is evidence of
   the construct rather than of the renderer's mood.
   `test_inline_image_inside_a_paragraph_is_not_swallowed` covers the specific
   silent drop an inline flattener causes (an `<img>` contributes no text, so a
   naive flattener loses it without trace).
5. **Markdown table survives the round trip** —
   `test_markdown_table_reaches_a_real_table_element` runs markdown →
   `markdown_to_safe_html` → `sanitize_book_html` → adapter → `render` and
   asserts `<thead><tr><th>sample</th>`, `<td>11.4</td>`, `<td>wet</td>`.
   `test_table_survives_the_sanitizer_specifically` pins the middle step on its
   own, because the sanitizer is an allowlist and is the step most likely to be
   assumed rather than checked.
6. **Test files green** — above.

## What I did NOT do

- **SPR-3 (source-design retention) and SPR-4 (the `.antiek` return leg)** —
  out of scope per the brief. SPR-4 in particular is still a real hole:
  `services/ingestion/ingest_antiek.py` exists with signature verification,
  quarantine-on-tamper and the `returned_unmodified` classification, and still
  has no route.
- **`acquisition/doc_to_html/converter.py`'s CLI shell-out.** The spec is right
  that `firecrawl_anydoc`'s structured Python API is the higher-fidelity path,
  and the adapter that would receive it now exists. Changing the converter would
  have been a second lane.
- **The `CONVERTER_VERSION_ANYDOC = "anydoc/0.1.6"` vs installed 0.1.8 drift**
  at `substrate/research_bridge/extractors.py:31`. I confirmed the drift is real
  but left it: by the prior wave's own gate a `converter_version` change is a
  reindex trigger, so correcting the string without reindexing would trade one
  wrong claim for a different one. It needs an operator decision, not a patch.
- **I weakened, skipped, xfailed and deleted no existing test.** The only
  existing-behaviour change is additive: six new contract rows and six new CSS
  rules. `TOKENS_CSS` is described in `tokens.py` as byte-pinned by the
  determinism tests; I checked what that actually means before appending to it —
  `test_determinism.py` renders twice and compares, it does not compare against
  a stored golden, so appending rules is safe. The 47 downstream artifact/export
  tests passing is the confirmation.

## What I am unsure of

- **Reachability for the operator in practice.** The route gates the body
  through `serve_reader_html`, whose rights ring binds to
  `_owner_read_policy_tag` — which returns the privileged tag only on a real
  authenticated credential, never on `unauthenticated_local`. URL ingests are
  `personal_reading` by default. So on a local box with auth disabled, this
  route returns `403 rights_denied` for exactly the documents the operator most
  wants to see. That is the sibling `GET /sources/{id}/reader-html` route's
  existing behaviour and I deliberately matched it rather than carving an
  exception — a projection route that released a body the reader-html route
  refuses would be a rights bypass wearing a stylesheet. But it does mean
  "reachable today" requires `ANTIEK_OPERATOR_EMAIL`/`_TOKEN`/`_SECRET` set. If
  the operator expects to hit this with auth off, that is a decision to make
  deliberately, in `books.py`, for both routes at once.
- **The doc-model carries a `source` key** (`document_id`, `source_kind`,
  `source_url`) alongside `title` and `content`. The renderer ignores it and the
  island round-trip is unaffected, but it is a shape the export half has never
  seen. If `.antiek` emission later validates the doc-model against a closed
  schema, this is the field that will trip it.
- **Table header detection** promotes only the first all-`<th>` row into
  `<thead>`. A two-row header renders its second row inside `<tbody>` with
  `<th>` cells — correct content, imperfect semantics. I did not build a fuller
  heuristic because GFM cannot express one and I had no `.docx` sample to test
  against.
- **Nesting past `MAX_TREE_DEPTH` (24)** flattens the remainder to a paragraph
  of its text rather than showing a limit marker. The text survives; the
  structure does not, silently. I judged that acceptable because a 24-deep
  `<div>` nest carries no reading meaning, but it is the one place in the
  adapter where something is lost without saying so, and it is the place I would
  look first if that judgement turns out to be wrong.
