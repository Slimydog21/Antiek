# Publisher opt-in catalog manifest (§9.10)

This is the documented, versioned format a publisher fills to submit **their
own catalog** with an **explicit serving grant**. It is the one legitimate lane
by which *in-copyright* material becomes **servable** on Antiek: not by scraping
it, but because the rights-holder themselves grants Antiek the right to serve
it (master-spec §9.10).

The intake script (`acquisition/opt_in/intake.py`, wired into
`tools/run_corpus_ingest.py --oa-source opt_in`) parses this manifest, validates
each work's grant, and ingests granted works as `opt_in_licensed` (servable)
with the grant recorded as the `license_basis`. **The grant is the single field
that flips a work servable.** A work with an absent / empty / out-of-scope /
withdrawn / expired grant is ingested `restricted_pending_opt_in` (gated) —
deny-by-default; its body is still chunked and embedded for private search but
its full text is **never served**.

This is script-first and operator-run; there is no submission UI in v1.

## Schema

`schema_version` must be `opt_in/1`.

```jsonc
{
  "schema_version": "opt_in/1",

  // WHO is granting. publisher_id is the STABLE identity the publisher's
  // ip_holder is keyed on — the same publisher_id across submissions resolves
  // to ONE ip_holder (escrow never fans out into duplicate accounts). Never
  // key on display_name: it is mutable.
  "publisher": {
    "publisher_id": "mit-press",                 // REQUIRED, stable
    "display_name": "MIT Press",                  // human-facing
    "legal_contact_email": "legal@mitpress.edu"   // optional
  },

  // OPTIONAL catalog-level grant covering EVERY work in this manifest. Must be
  // scoped "full_catalog" to apply broadly. A per-work grant on an entry
  // overrides it for that work.
  "catalog_grant": {
    "rights_holder": "MIT Press",
    "scope": "full_catalog",
    "granted_at": "2026-05-30",
    "statement": "MIT Press authorizes Antiek to serve the full text of every work in this manifest, under the per-second ad-border revenue-share terms, effective 2026-05-30."
  },

  "works": [
    {
      "title": "Example Granted Work",          // REQUIRED
      "author": "A. Author",                     // optional
      "isbn": "978-0-262-04630-5",               // content-stable id (preferred)
      "doi": "10.7551/mitpress/12345.001.0001",  // content-stable id (preferred)
      "body_text": "...the full body text...",   // body source (see below)
      "body_path": "/abs/path/to/body.txt",      // OR a file path to the body

      // OPTIONAL per-work grant. Overrides catalog_grant for THIS work.
      "grant": {
        "rights_holder": "MIT Press",
        "scope": "per_work",                     // "per_work" | "full_catalog"
        "granted_at": "2026-05-30",
        "expires_at": "2030-01-01",              // optional; past => gated
        "withdrawn": false,                      // true => gated (revoked)
        "statement": "MIT Press grants Antiek the right to serve the full text of this work."
      }
    }
  ]
}
```

### Body source

Each work needs exactly one of:

- `body_text` — the work's body inline, OR
- `body_path` — an absolute path to a UTF-8 text file with the body.

The body is rendered to a deterministic PDF (via the existing
`acquisition.books.public_domain.text_to_pdf`) and ingested through the shared
servable-book path. Determinism is what makes re-submission **idempotent**: the
same body renders to the same bytes, so the document's content-stable id is
stable across runs and a resubmission updates the same document instead of
duplicating it.

## Grant validation rules (deny-by-default)

A grant is **valid** (work ingests servable) only when **all** hold:

1. It is present as an object (a bare `true` boolean is **rejected** — a
   boolean is a claim, not a recorded basis the audit can read).
2. It carries a non-empty `statement` (the verbatim authorization text recorded
   as the `license_basis`).
3. It carries a parseable `granted_at` date.
4. Its `scope` is recognised (`per_work` | `full_catalog`) **and covers this
   work**. A catalog grant scoped `per_work` does **not** cover an arbitrary
   work — only `full_catalog` covers the whole catalog.
5. It is **not** flagged `withdrawn` and **not** past its `expires_at`.

Every failure mode lands the work **gated** (`restricted_pending_opt_in`),
never servable and never silently dropped. The intake summary reports, per
work, whether it went servable or gated **and why each gated one failed** —
ambiguous grants are gated, not stretched into a serving right.

## Why a grant statement, not a `servable: true` boolean

A boolean leaves no recorded `license_basis` the SPR-10 rights audit can inspect
months later in front of counsel; it cannot express scope or withdrawal; it
makes "by whose grant is this servable?" unanswerable. §9.0 demands a
positively-established, recorded basis. The grant statement **is** that basis.
The recorded basis names the publisher, the grant text, and the scope — the
paper trail that distinguishes this legitimate lane from scraped intake.

## What ingest records

For each servable work the `book_assets.license_basis` row carries
`publisher_opt_in (<rights holder>) -- grant: <verbatim statement>`, the work
links to the publisher's `ip_holder_id`, and escrow begins **accruing** to that
holder. Accrual only — disbursement stays operator-gated on G2/G3, and the
money-path / disbursement modules under `substrate/ad_inventory/` are never
touched by this lane.
