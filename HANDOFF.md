# Lane handoff — the `.antiek` return leg (HPRJ SPR-4)

Branch `lane/antiekleg-20260920`, cut from `origin/main` at `ebc5996ad`.

## The gap, re-checked before building

On `ebc5996ad`, `grep -rn "ingest_antiek" interfaces/` returned nothing: the
only callers of `services/ingestion/ingest_antiek.py` were its own two test
modules. Signature verification, quarantine-on-tamper, island-only reading and
the `returned_unmodified` / `traveled_and_changed` classification were all
built, and nothing in the product could reach them. The gap was open.

## What shipped

`POST /ingest/antiek` on `interfaces/research/api/doc_ingest_routes.py`.
It takes a multipart upload, resolves the owner through the same
`distinct_signed_owner` predicate the neighbouring `/ingest/asset` uses, and
keeps its size and empty-body limits. On a quarantine it answers 422 with a
typed reason; on success it stores the doc-model and hands back the URL that
opens it.

Three things the brief did not anticipate, each of which changed the shape:

**The registry had no production instance.** `ExportRegistry` was an in-memory
class populated only in tests, so passing `ingest_antiek` a bare one would have
classified every returning artifact as untracked — the same no-caller defect
one layer down. Exports are reproducible from the notebook rows, so
`_SubstrateExportRegistry` answers "what would we export for this document?"
from the substrate on demand, lazily, because the document_id is only known
after the artifact parses. `notebook_export_item` was lifted to module scope in
`notebook_artifact.py` so the export side and the return leg build that shape
from one place rather than two that agree by luck.

**A verified signature does not prove Antiek authored anything.** Both
verifiers check the artifact against the public key the artifact carries. So
the rights class is decided by the round-trip instead: only
`returned_unmodified` — matching document_id AND canonical content hash —
writes under the claimed id as `user_owned`. Everything else, including
`traveled_and_changed`, lands on a content-derived `doc-antiek-<hash>` id as
`personal_reading`. An uploaded body reaching the monetized read path because
it asserted an id is exactly the §9.0 leak the rights states exist to stop.

**A bound notebook could clobber its document's reader body.**
`notebooks.document_id` binds a wrestle notebook to a real document, and the
export path stamps that binding into the manifest — so a notebook attached to a
book exports an artifact claiming the BOOK's id. Honouring it on re-import
would have replaced the book's reader HTML with notebook prose, silently.
`_claimed_id_is_free_or_ours` honours the claimed id only when the id is
unoccupied in BOTH the `documents` table and the reader-HTML sidecar, or when
this route is what occupies it — which also keeps a second import of the same
artifact idempotent.

The first cut of that guard asked the sidecar alone, and that was not enough. A
document and its reader body are written as separate rows, so a book that has
not been projected yet has a `documents` row and no sidecar row; the sidecar-only
guard read it as "nothing is there" and handed the notebook's prose the book's
id, its title, its provenance footer and its `public_domain` rights class — an
uploaded body on the public serve path, reachable end to end through
`POST /notebooks` with a `document_id` binding. Adversarial verification caught
it and it is fixed here.
`test_a_bound_notebook_never_overwrites_its_documents_reader_body`,
`test_a_bound_notebook_never_takes_over_a_book_with_no_reader_body_yet` and
`test_a_reader_body_this_route_did_not_write_is_never_replaced` each fail
against a different half of the guard removed.

## Done-bar

1. **Round trip classifies `returned_unmodified`** —
   `test_round_tripped_container_classifies_returned_unmodified`. The artifact
   is produced by the real export route, not hand-assembled, and
   `test_the_returned_artifact_is_readable_where_the_response_says` opens the
   `render_url` the response returns and finds the content.
2. **Tampered quarantines with its typed reason, never rendered** —
   `test_tampered_container_quarantines_and_is_never_stored` asserts
   `disposition == "tampered"`, `reason_code == "container_signature_invalid"`,
   and that neither the documents table nor the reader-HTML table gained a row.
   Same for the single-file side.
3. **Malformed is distinguishable from tampered** — every quarantine carries a
   code from a closed vocabulary in `ingest_antiek.py` plus a disposition
   (`tampered` / `unsigned` / `not_antiek` / `malformed`). All seven codes are
   driven through the route.
   `test_a_validly_signed_file_with_a_broken_island_is_malformed` is the sharp
   case: signed, verifies, still unreadable, reported as malformed.
4. **Tests drive the route** — `tests/api/test_ingest_antiek_route.py` reaches
   `ingest_antiek` only over HTTP. Against the pre-lane tree every one of its
   sixteen tests 404s.

## Brief corrections

- The brief asked for a one-line registration in `app.py`. None was needed:
  the new route is on the existing `doc_ingest_router`, which
  `register_doc_ingest_routes(app)` already mounts at `app.py:1774-1775`.
  Adding a second inclusion would have double-mounted the router.
- The brief said to call `ingest_antiek(data, export_registry=...)` as if a
  registry were available. It was not; see above.

## Open, deliberately

The registry compares against what Antiek would export NOW, so a notebook
edited after its artifact left will classify that artifact's unmodified return
as `traveled_and_changed`. The verdict stays truthful about the content and
loses the ability to say which side moved. Closing it needs export hashes
recorded at emit time in a durable ledger, which is a table and a writer this
lane does not own.

## Commands run

    python -m pytest tests/api/test_ingest_antiek_route.py -q        16 passed
    python -m pytest tests/api tests/test_doc_to_html.py \
      tests/test_roundtrip_detector.py tests/test_style_api.py \
      tests/test_anti_ek_honesty_contracts.py services/ingestion/tests -q
                                                                    206 passed
    python -m ruff check <touched files>                             clean
    python -m mypy --strict interfaces/research/api/doc_ingest_routes.py \
      interfaces/research/api/notebook_artifact.py                   no errors
                                                                     in touched
    python -m tools.lints.no_blocking_write_in_async <touched>        exit 0
    python -m tools.lints.no_seam_call_under_write_lock <touched>     exit 0
    python -m tools.lints.no_unbounded_external_call <touched>        exit 0

The blocking-write baseline is empty, so any new violation reds. The write in
this route is in a nested sync `def` dispatched through `run_in_threadpool`,
with a 503 on `WriteLockTimeout` — the sanctioned shape. Verified the lint
still bites by running it against a deliberate violation.
