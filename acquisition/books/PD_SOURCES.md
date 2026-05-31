# PD book sources — establishment method, dedup identity, failure mode (SPR-06)

This note is the reproducible record of HOW each Wave-2 public-domain book
source positively establishes public-domain status, what identifier drives the
cross-source dedup key (`substrate.dedup`), and what breaks if the source is
down. It is the SPR-10 standing-audit's reference for "why is this servable?"

## Why a second, third, … PD source (the gutendex lesson)

On the first prod corpus run (2026-05-29) Project Gutenberg via **gutendex**
intermittently **503/timed-out under real-run load**, and only small chunked
batches got through. Gutenberg was — and remains — Antiek's *only* PD book
source, so that flakiness was a corpus-breadth ceiling AND a single point of
failure. **Adding Standard Ebooks, Wikisource, Internet Archive, HathiTrust,
and the Library of Congress reduces single-source dependence: when one PD
source 503s or bans, the other four still discover and ingest, so a corpus run
never collapses to zero on one endpoint's bad day.**

## The binding (load-bearing, this run's reason to exist)

Every connector derives `content_class` ONLY by calling
`acquisition.licenses_core.classify(license, source_declaration, *,
legitimate_source=...)`. That returns a `ClassificationResult` carrying
`content_class` + `license_basis`; the connector passes THAT result's
`content_class` + `license_basis` to `acquisition.books.adapter.ingest_servable_book`.
No connector assigns `content_class` by any other route. The legacy direct
route (`public_domain.py` passing `content_class="public_domain"` straight to
ingest) is exactly what this wave retires — it is NOT copied.

Deny-by-default (§9.0): a body is servable ONLY if `classify()` returns a class
in `substrate.constants.SERVABLE_CONTENT_CLASSES`. Anything unresolved /
ambiguous / NC / ND / closed routes to `GATED_DEFAULT_CONTENT_CLASS`
(`restricted_pending_opt_in`) — gated (chunked/embedded/graph-resident for
private search) but body NEVER served. "No copyright flag" is NOT "public
domain"; it is undetermined → gated.

## Spine functions each connector calls (no reinvention)

- **SPR-02 rights gate** — `acquisition.licenses_core.classify(...)` (the
  chokepoint). PD-mark / CC0 → `public_domain`; CC-BY/-SA → `source_declared_open`;
  unknown/NC/ND/missing → gated. The `source_declaration={"public_domain": "<basis>"}`
  signal carries a positive, item-specific PD assertion string.
- **SPR-03 resilience** — `substrate.source_throttle.SourceThrottle`
  (`before_request(source)` raises `SourceBanned` while banned + spaces
  requests; `note_response(source, status, headers)` arms the ban sentinel).
  Every connector fetch routes through a small `ThrottledFetcher` that consults
  these. The extraction-quality gate is `read_pdf` + the substrate
  `assess_extraction_quality` reused by the orchestrator's
  `_assert_pdf_body_quality` — connectors hand PDF bytes to
  `ingest_servable_book`, whose `read_pdf` word-count floor + the orchestrator's
  body-quality gate reject OCR garbage / near-empty extracts.
- **SPR-04 dedup** — `substrate.dedup.identity_key` / `dedup_key` /
  `IdentityRecord`. The connector emits the identity-bearing fields; the
  orchestrator's `dedup_candidates` collapses the same work across sources to
  one document via the single precedence ladder
  (DOI > ISBN-13 > arXiv > source-id > content-hash > title+author LOW).
- **SPR-01 staging write** — `acquisition.books.adapter.ingest_servable_book`
  → `substrate.books.ingest.register_book` → `runtime.db_lock.connect_write`
  (the single writer). Connectors never open a write connection or touch the
  live DB; the orchestrator's `--staging-db` routes the write off the hot path.

## Per-source establishment + dedup identity + failure mode

| Source | PD-establishment method (positive) | License string handed to classify() | Dedup identifier (`KeyType`) | What breaks if down |
|---|---|---|---|---|
| **Standard Ebooks** | Source publishes ONLY US-public-domain works; each OPDS entry carries a `dc:rights`/`<rights>` PD dedication. Establishment = source-level PD guarantee + per-item rights field, recorded (not assumed). | The entry's CC0/PDM-style rights URI when present, else the `source_declaration={"public_domain": "Standard Ebooks: source publishes US-PD only; <entry rights>"}` positive signal. | `source_id` = `standard_ebooks:<book-slug>` (the SE URL slug; stable within SE). Content-hash above it when body extracted. | The well-formatted-epub channel; the other four still run. |
| **Wikisource** | The work's license **category/template** is a PD/PD-equivalent category (e.g. `PD-old`, `PD-US`, `PD-1923`, `No restrictions`). A non-PD category (e.g. CC-BY-SA-only, or `Copyrighted`) is NOT marked PD → gated/skip. | The PD-category-mapped URI (`https://creativecommons.org/publicdomain/mark/1.0/` for `PD-*`), CC-BY-SA URI for free-licensed → `source_declared_open`, else gated. | `source_id` = `wikisource:<canonical-page-name>` + content-hash of the proofread body. | The transcribed-PD channel; others run. |
| **Internet Archive** | `possible-copyright-status = NOT_IN_COPYRIGHT`, OR a `licenseurl` pointing at a CC0/PDM/`/publicdomain/` mark, OR a `rights` field explicitly asserting PD (no negation, no ©+year). **IA hosts in-copyright works too**, so absence of a flag → undetermined → gated, never servable. | The PD `licenseurl` when present (→ classify resolves PDM/CC0 → `public_domain`); else the `source_declaration={"public_domain": "Internet Archive metadata possible-copyright-status=NOT_IN_COPYRIGHT"}` positive signal. Unestablished → empty license + no PD signal → gated. | `source_id` = `internet_archive:<ia-identifier>`. | The mixed-corpus PD subset; others run. |
| **HathiTrust** | Bibliographic API **rights code**: `pd` / `pdus` establish public domain → servable; `ic` / `icus` / `und` (in-copyright / undetermined) and any UNRECOGNIZED code → gated/skip, never servable. | `pd`/`pdus` → `source_declaration={"public_domain": "HathiTrust rights=<code>"}`; others → no PD signal + empty license → gated. | `oclc`/`isbn` from the bib record when present (ISBN-13 `KeyType.ISBN`); else `source_id` = `hathitrust:<htid>`. | The HathiTrust PD subset; others run. |
| **Library of Congress** | The item **rights statement** (loc.gov JSON `rights`/`rights_information`) explicitly asserts no known copyright / public domain / a PD mark. Unclear/blank → gated/skip. | The PD/PDM/CC0 `rights` URI when present → classify → `public_domain`; else `source_declaration={"public_domain": "Library of Congress rights statement: <statement>"}`. Unclear → gated. | `lccn` (treated as a `source_id`-level id `library_of_congress:<lccn>`); content-hash above it when body extracted. | The LoC digital-collections PD subset; others run. |

## Failure modes enumerated (rigor #3)

- HTML landing page instead of epub/PDF → extraction-quality gate / word floor
  rejects it as a counted skip; never a silent servable.
- Missing rights code / missing copyright-status field → undetermined → gated
  (NOT rounded up to PD).
- Rights code present but unrecognized (Hathi) / unknown license URI → classify
  resolves to gated (deny-by-default), never servable.
- Discovery query returns a stale or mis-tagged record → the **per-item
  re-check** (layer 2) re-runs classify on the item's own fields before ingest,
  so a discovery-query false positive cannot reach a servable ingest.

## Connector registry (SPR-09 rotation)

`PD_CURATED_SOURCES` in `acquisition/books/registry.py` lists the five module
import paths + their discovery entrypoints so SPR-09 can rotate over them. The
orchestrator's `--pd-curated` flag drives the curated PD spine across them.
