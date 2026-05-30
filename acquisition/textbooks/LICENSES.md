# Open-textbook connectors — license-mapping note (SPR-05 M1)

Four connectors, one rights chokepoint. Every connector resolves the item's
**declared** license string from the source's own metadata and hands it —
together with a `source_declaration` mapping and a `legitimate_source=True`
judgment — to the SINGLE classification function:

    acquisition.licenses_core.classify(
        license: Optional[str],
        source_declaration: Mapping[str, Any],
        *,
        legitimate_source: bool,
    ) -> ClassificationResult

`ClassificationResult` carries `content_class`, `servable` (DERIVED from
`content_class in substrate.constants.SERVABLE_CONTENT_CLASSES`, never an
independent flag), `ingest`, `accrual_eligible`, `license_basis`, `rationale`.
No connector assigns a `content_class` by any other route — that is the
load-bearing invariant this wave exists to enforce. (The legacy
`acquisition/books/public_domain.py` route that passes
`content_class="public_domain"` straight to `ingest_servable_book` is exactly
the route being retired; the textbook connectors do NOT copy it.)

The servable ingest entrypoint is
`acquisition.books.adapter.ingest_servable_book(...)`, which takes the resolved
`content_class` + `license_basis` and delegates the legal-gate registration to
`substrate.books.ingest.register_book`. Connectors do NOT call `register_book`
directly.

## What classify() returns for each CC family (read from `_CLASSIFY_TABLE`)

These are recorded from SPR-02's map, not invented here. classify() resolves
the license string against the canonical CC table (URI rows + compact
short-code rows), NC/ND BEFORE BY so a `by-nc` URI never matches the bare `by`
row.

| Declared license            | content_class                | servable | notes |
|-----------------------------|------------------------------|----------|-------|
| CC-BY (`.../licenses/by/`)  | `source_declared_open`       | yes      | attribution; NOT public_domain, NOT a §9.10 opt-in |
| CC-BY-SA (`.../by-sa/`)     | `source_declared_open`       | yes      | share-alike obligation inherited |
| CC0 (`.../publicdomain/zero`)| `public_domain`             | yes      | dedication, no rights holder |
| CC-PDM (`.../publicdomain/mark`)| `public_domain`          | yes      | already public domain |
| CC-BY-NC (`.../by-nc`)      | `restricted_pending_opt_in`  | NO (gated) | NC forbids commercial reuse; Antiek's ad-funded serving is commercial |
| CC-BY-NC-SA (`.../by-nc-sa`)| `restricted_pending_opt_in`  | NO (gated) | matches the `by-nc` row first → gated |
| CC-BY-ND (`.../by-nd`)      | `restricted_pending_opt_in`  | NO (gated) | ND bars derivative (chunked/reflowed) presentation |
| unresolved / missing / ARR  | `restricted_pending_opt_in`  | NO (gated) | deny-by-default safety branch |

`restricted_pending_opt_in` is `substrate.constants.GATED_DEFAULT_CONTENT_CLASS`
— gated (chunked/embedded for private search, body never served full-text). It
is NEVER flattened to `public_domain`.

## Per-source declared licenses + where the license is read

### OpenStax (`openstax.py`)
- **Declared:** uniformly **CC-BY** (a few titles CC-BY-NC-SA / CC-BY-SA;
  always per-book metadata).
- **Where read:** the OpenStax open catalog record's `license` block —
  `license.url` (the canonical `creativecommons.org/licenses/by/4.0` URI) with
  `license.name` / `license.version` as the human label. We pass `license.url`
  to classify().
- **Routing:** a CC-BY book → `source_declared_open` (servable). A CC-BY-NC-SA
  title → gated, by the table above.

### LibreTexts (`libretexts.py`)
- **Declared:** **per-page / per-book mixed** CC variants (-BY, -BY-SA, -BY-NC,
  -BY-ND, -BY-NC-SA). LibreTexts does NOT carry a uniform source license, so
  each discovered item's license is resolved individually.
- **Where read:** the page/book metadata `tags` / `properties` carry a
  `license` code (`ccby`, `ccbysa`, `ccbync`, `ccbynd`, ...) plus a
  `licenseurl`. We prefer the URL when present, else the code; both reach
  classify() through the same CC table.
- **Routing:** CC-BY / CC-BY-SA → `source_declared_open`; CC-BY-NC / -ND /
  -NC-SA → gated (the SPR-02 class); no resolvable license → gated default.

### DOAB / OAPEN (`doab.py`)
- **Declared:** **per-book** (CC variants differ book to book).
- **Where read:** the DOAB book record's `dc.rights` / license field (a
  `creativecommons.org/licenses/...` URI). We also prefer the structured OA
  full-text URL the record advertises; if that "PDF" link resolves to an HTML
  landing page (bytes start `b'<!DO'`), the SPR-03 extraction-quality gate
  (`acquisition.openaccess.pdf_detect.assert_pdf`) REJECTS it — it is never
  ingested as a book body (the 6/15-OA-landing-pages lesson).
- **Routing:** per-book license → classify(); CC-BY books servable, NC/ND /
  unresolved gated.

### MIT OpenCourseWare (`mit_ocw.py`)
- **Declared:** uniformly **CC-BY-NC-SA**. This is the canonical NC test.
- **Where read:** the OCW course metadata `license` field (the
  `creativecommons.org/licenses/by-nc-sa/4.0` URI).
- **Routing:** CC-BY-NC-SA → whatever SPR-02 assigns NC-SA. Per the table that
  is `restricted_pending_opt_in` (gated) — the connector OBEYS this; it does
  not decide the policy. The test asserts whatever classify() actually returns
  and fails if it is ever `public_domain`.

## Spine composition (no reimplementation)
- **SPR-01 staging write** — the orchestrator routes to a staging DB via
  `--staging-db`; connectors write through `ingest_servable_book` →
  `runtime.db_lock.connect_write` only (never the live DB directly).
- **SPR-02 rights** — `licenses_core.classify` (above).
- **SPR-03 throttle + ban + extraction gate** — `substrate.source_throttle`
  (cross-process ban sentinel) fronts the throttled HTTP client; the
  `acquisition.openaccess.pdf_detect.assert_pdf` PDF-vs-HTML gate runs before
  any body reaches the reader.
- **SPR-04 dedup** — `substrate.dedup` (DOI > ISBN-13 > arXiv-id > source-id >
  content-hash > title+author) via the orchestrator's `CandidateRef`.
