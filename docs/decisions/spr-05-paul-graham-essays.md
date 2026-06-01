# SPR-05 — Paul Graham essays via `acquisition/urls` (Personal-Reading Lane)

Status: implemented (engineering). The one-time live discover+ingest run against
`paulgraham.com` is operator-only (production network); CI/tests are fully
offline against checked-in fixtures.

## What landed

- `acquisition/urls/paulgraham.py` — a thin, operator-invoked **driver** over
  the already-hardened `acquisition/urls` connector. It owns discovery
  (parse `articles.html`, robots, throttle), drives `ingest_url` per essay,
  detects unchanged/changed essays for an incremental re-run, and emits an
  honest per-essay extraction-quality report. It is NOT a new acquisition
  package and does NOT re-implement fetch/extract/chunk/identity.
- `acquisition/urls/__main__.py` — `python -m acquisition.urls {discover,run}`
  CLI (routes to `paulgraham._main`).
- `tests/fixtures/paulgraham/{articles.html,greatwork.html,degraded_essay.html}`
  — offline fixtures (no live network in any test).
- `tests/test_acquisition_paulgraham.py` — discover / owner_read / attribution /
  incremental / extraction_quality + binding-audit coverage.

## Decisions (defensibility — rigor #5)

### D1 — Reuse `acquisition/urls`, do NOT build `acquisition/web/`

Per the master-spec decision. A second package would duplicate the canonical
URL identity (`url_doc_id(final_url)`), the `url_alias` incremental
short-circuit, and the `connect_write` single-writer discipline, and split the
maintenance surface. The only PG-specific code is the discover/ingest driver,
living **inside** `acquisition/urls/`.

**Reconsider-if:** if the generic `html_to_markdown` extractor flags >10% of
essays as mis-extracted on a real run, the defensible next step is a PG-specific
extractor *shim inside `acquisition/urls/`* (not a sibling package). The flag
rate is recorded in `artifacts/paulgraham/extraction_quality.json` so this
threshold is measurable.

### D2 — Polite spacing = 3.0s, sourced not invented

`MIN_REQUEST_SPACING_S = 3.0`, modeled on
`acquisition/arxiv/throttle.MIN_REQUEST_SPACING_S` (arXiv's stated "one request
per three seconds"). PG's essays are on his own hand-run static site; a
single-operator tool has no reason to go faster, and the cost of being impolite
(an IP block) dwarfs per-essay latency. The driver's `PoliteThrottle` is
deliberately simpler than `ArxivThrottle` — no cross-process ban sentinel,
because a static site does not 429-IP-ban like the arXiv API, and the run is the
only writer. `now`/`sleep` are injectable so tests never block.

### D3 — Identity is URL-stable; a re-titled essay stays one document

The connector keys identity on `url_doc_id(final_url)` (a sha256[:16] of the
final URL). A changed essay at the SAME URL is detected by comparing the
DocumentLoadedPayload content-hash to the stored one and is re-ingested as an
**update** under the same `document_id` — never forked to a second doc. An
unchanged essay short-circuits via `lookup_url_alias`
(`skipped_reason="alias_resolved_to_existing_document"`), so a second run over an
unchanged corpus adds zero `documents`/`chunks` rows.

### D4 — `personal_reading` is the connector's job, not the driver's

The driver passes **no** `content_class` to `ingest_url`. SPR-02 hardened the
connector so a `web_article` lands `content_class=personal_reading` (the
imported `PERSONAL_READING_CONTENT_CLASS` constant, never a string literal — so
`corpus_audit.assert_no_content_class_bypass` stays green). Hardcoding the class
in the driver would (a) introduce a second classification chokepoint and (b)
trip the literal-content_class bypass scanner. **Diligence note (rigor #4):**
SPR-02's default was verified present in this tree at
`acquisition/urls/adapter.py` (`insert_document(..., content_class=PERSONAL_READING_CONTENT_CLASS)`)
before relying on it — the sprint is not blocked.

### D5 — Extraction-quality honesty (rigor #1)

A degraded essay is NEVER reported as a clean read. The verdict flags:
- the connector skipped graph writes for low word count (body never landed);
- the extracted body is below `MIN_INGEST_WORD_COUNT` (=50);
- a residual *layout* HTML tag (`<table>`/`<td>`/`<tr>`/`<font>`/`<div>`/
  `<span>`/`<img>`) leaked into the markdown body (PG's table-as-layout markup
  defeated the extractor). **Note:** `<br>` is excluded — html2text leaves it as
  a literal benign artifact, not a sign of failure.

The run summary separates `ingested_clean` / `ingested_flagged` /
`skipped_flagged` / `skipped_unchanged` / `changed_reingested` /
`robots_disallowed` / `errored`. A genuinely short-but-clean essay (some PG
essays are short) that clears the floor with no markup leakage is `ok`.

## Invariants honored

- **personal_reading never serves publicly.** The driver does not touch the
  SPR-01 read-side gates. `personal_reading` is excluded from
  `SERVABLE_CONTENT_CLASSES`, present in `NON_ATTRIBUTABLE_CONTENT_CLASSES`,
  absent from `PUBLIC_GRAPH_CONTENT_CLASSES`; the owner reads the full body via
  the `PERSONAL_READABLE_CONTENT_CLASSES` allowlist.
- **Lawful acquisition.** Discovery is only `paulgraham.com/articles.html` → its
  on-host essay links; `robots.txt` is honored (`urllib.robotparser` +
  `DEFAULT_USER_AGENT` `can_fetch`); off-host / look-alike-host / subdir / index
  links are dropped. PG's "link, don't mirror" is respected: the body lives in
  the owner's personal lane, never re-published.
- **§16 box-bounded.** Every graph write funnels through the connector's single
  `runtime.db_lock.connect_write` writer; the driver is an in-process loop, not a
  daemon/queue/second-runtime.
- **Money path untouched.** No read/import/modify of `payout.py` /
  `stripe_connect/`; `personal_reading` accrues zero ad attribution + zero IP
  escrow by construction.

## Out-of-scope temptations encountered

- A generic web crawler — declined; discovery is the single `articles.html`
  index only.
- Serving PG publicly / promoting to a servable class — declined; PG holds
  copyright and granted no positive license basis.
- A bespoke PG extractor or `acquisition/web/` — declined now; gated behind the
  >10% flag-rate threshold (D1) and would be a urls-internal shim if reached.
