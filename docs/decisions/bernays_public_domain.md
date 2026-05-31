# Decision — Edward Bernays titles: what is servable public domain, what is refused

**Date:** 2026-05-31
**Sprint:** SPR-04 (Antiek Personal-Reading Lane & Ambient Ingest) —
[`specs/antiek-personal-lane/sprint-04-bernays-public-domain.html`](../../specs/antiek-personal-lane/sprint-04-bernays-public-domain.html)
**Status:** binding. This note is the artifact a future maintainer (or counsel)
reads to answer "why is *Public Relations* not servable?" — so it carries the
**evidence**, not just the verdict. Every `license_basis` string below is a
hardcoded legal claim; its origin is commented at the curated catalog entry in
[`tools/ingest_public_domain.py`](../../tools/ingest_public_domain.py).

A decision cached only in a session's chat has failed defensibility. This is
the durable record.

---

## The two SERVABLE titles (ingested as `content_class=public_domain`)

Both flow through the EXISTING curated servable-books path
(`tools/ingest_public_domain.py` → `acquisition/books/public_domain.ingest_work`
→ the ONE `acquisition.licenses_core.classify()` chokepoint →
`acquisition/books/adapter.ingest_servable_book`). The rights DECISION is
routed through classify() off the **source's positive public-domain signal**,
never a hardcoded `"public_domain"` literal (this is the exact anti-pattern
`substrate.corpus_audit.assert_no_content_class_bypass()` scans for). The
curated precise `license_basis` is applied by
`acquisition.books.public_domain._apply_curated_basis` **only after** the source
has positively asserted PD — it refines the wording of an already-positive
basis; it never manufactures a public-domain claim from memory.

### 1. *Crystallizing Public Opinion* (1923)

- **Basis:** `US PD pre-1929 (public domain); Project Gutenberg #61364`
- **Why PD:** published **pre-1929**, so it is US public domain by copyright-term
  expiry — renewal is irrelevant for a pre-1929 work (the 95-year term and the
  renewal question only matter for 1929+ works). The legitimate full text is
  **Project Gutenberg ebook #61364**, which carries Gutenberg's per-book
  `copyright=false` flag (Gutenberg's explicit, machine-readable US-public-domain
  assertion).
- **Provenance URL:** <https://www.gutenberg.org/ebooks/61364>
- **Source assertion gate:** if the live #61364 record does NOT carry
  `copyright=false` at ingest time, the work is skipped — we do not stamp
  `public_domain` from memory (rigor #1).

### 2. *Propaganda* (1928)

- **Basis:** `US PD: 95-yr term; entered PD 2024-01-01 (public domain); Internet
  Archive PDM (1928 first ed.)`
- **Why PD:** a 1928 work entered the US public domain on **2024-01-01** under the
  **95-year term** (1928 + 95 = 2023; works enter PD on Jan 1 of the following
  year). *Propaganda* is not on Gutenberg as a clean PD item; the legitimate
  copy is the **Internet Archive Public-Domain-Mark (PDM)** item carrying the
  1928 first-edition text. Ingest is gated on the item's `rights`/`licenseurl`
  PDM assertion (`acquisition.books.public_domain._archive_pd_basis`): an
  ambiguous or copyright-asserting item is denied, not served.
- **Provenance URL:** <https://archive.org/details/propaganda_201804>
  — **⚠ identifier UNVERIFIED at build time.** This archive identifier was
  **not confirmed to resolve to a live item with a PDM rights field** when the
  sprint shipped. The offline tests prove the *wording* + the PDM-gating
  *behaviour* against a canned `FakeSourceClient` record — **not** that the live
  item exists. **Confirm the live PDM rights field (or substitute the correct
  IA identifier / a Wikisource copy of the 1928 first edition) before the SPR-08
  prod ingest.** If the named id is dead, `archive_candidate()` returns `None`
  on the empty metadata response and the work is safely dropped: the failure
  mode is the **silent absence of *Propaganda***, never an unsafe ingest of a
  copyrighted item. (`tools/ingest_public_domain.py` `CURATED_ARCHIVE_IDENTIFIERS`
  carries the same caveat at the catalog entry.)
- **Source assertion gate:** archive.org is resolved **per-identifier**, never by
  free-text rights search. If the named item's rights field does not yield a PDM
  / "no known copyright restrictions" basis, the item is skipped.

---

## How each title is ingested (which command lands which title)

The two titles land via **different discovery surfaces**, so the operator running
the SPR-08 corpus-ingest window must run the right command(s):

| Title | Source | Curated list | `tools.ingest_public_domain --curated` | `tools/run_corpus_ingest.py` |
|---|---|---|---|---|
| *Crystallizing Public Opinion* | Gutenberg #61364 | `CURATED_GUTENBERG_IDS` | ✅ lands it | ✅ lands it (reads `CURATED_GUTENBERG_IDS`) |
| *Propaganda* | archive.org PDM item | `CURATED_ARCHIVE_IDENTIFIERS` | ✅ lands it (`discover()` iterates the archive ids) | ❌ **does NOT** land it |

The canonical SPR-08 orchestrator `tools/run_corpus_ingest.py` only reads
`CURATED_GUTENBERG_IDS` and calls `gutenberg_candidates` — it has **no
archive.org discovery surface**, so it never iterates `CURATED_ARCHIVE_IDENTIFIERS`
and never lands an archive identifier. To land *Propaganda* the operator must run

```
python -m tools.ingest_public_domain --curated --db-path <LOCAL/TEMP db>
```

which is the only path whose `discover()` resolves the archive identifiers
(each still PDM-gated by `archive_candidate`). Running ONLY the
`run_corpus_ingest` orchestrator would silently land *Crystallizing* but not
*Propaganda*. (This is a wiring boundary, not a rights gap: both paths route
the rights decision through the same `classify()` chokepoint.)

---

## DO-NOT-INGEST-AS-PD — the in-copyright Bernays catalogue (refused)

These titles are **in copyright** and MUST NEVER be ingested as
`content_class=public_domain`. None is wired into the curated ingest lists
(`CURATED_GUTENBERG_IDS` / `CURATED_ARCHIVE_IDENTIFIERS`); promoting any of them
must be a deliberate, reviewed act with primary-source evidence — not a reflex
because "a PDF is right there."

| Title | Year | Why it is refused |
|---|---|---|
| ***Public Relations*** | 1945 | In copyright. The 1945 first edition's renewal is registered as **`RE0000069553`** (Catalog of Copyright Entries renewal), carrying the term to **© 2040** (1945 + 95). Not PD until 2041-01-01. |
| ***The Engineering of Consent*** | 1955 (essay 1947) | In copyright. A post-1945 work under the 95-year term; far from term expiry and renewal-era. No PD basis exists. |
| ***Biography of an Idea*** | 1965 | In copyright. A 1965 work is comfortably inside the 95-year term (PD no earlier than 2061-01-01). No PD basis exists. |

### The renewal-zone flag (1927–1930)

Any Bernays title first published **1927–1930** is in the renewal-sensitive zone:
a 1929–1930 work's US public-domain status depends on whether its copyright was
**renewed**, which requires a **primary Catalog-of-Copyright-Entries (CCE) or
Stanford Copyright Renewal Database lookup BEFORE any promotion to servable**.
The two titles above (1923, 1928) are NOT renewal-sensitive — 1923 is pre-1929
(term-expired regardless of renewal) and 1928 entered PD by the 95-year term on
2024-01-01. **The renewal research itself is a flagged follow-on, OUT of SPR-04**:
no 1927–1930 Bernays title may be ingested as PD until that primary-source check
is recorded here.

---

## The rejected shadow path

A copy of an in-copyright Bernays title **"floating around the open internet"**
(a stray PDF, a re-host, a scan on a random site) is **NOT a license** and is
explicitly refused. The presence of a file proves nothing about its rights; only
a **source's positive PD assertion** (Gutenberg `copyright=false`, an archive.org
PDM rights field) is a basis. Ingesting a third Bernays title because "the PDF is
there" is the exact §9.0 infringement (Hachette / Bartz discipline) this whole
spec exists to prevent.

---

## The gates that enforce this

- **`acquisition.licenses_core.classify()`** — the ONE rights-classification
  chokepoint. Both PD titles' `content_class` is its verdict off the source's PD
  signal; the audit BINDING (`assert_no_content_class_bypass()`) statically
  forbids any connector minting `content_class` by a string literal.
- **`substrate.books.serve.serve_full_text`** — the data-layer serve gate. A
  `public_domain` doc serves full text (`servable=True`, `reason="servable"`);
  anything not in `SERVABLE_CONTENT_CLASSES` serves at most a bounded snippet.
- **`substrate.corpus_audit.run_audit`** — the standing corpus audit:
  `servable_without_basis` requires every servable doc carry a non-empty
  `license_basis`; the `gated_body_leak` (b2) cross-check catches a servable
  class over a `GATED:`/circumvented basis.
- **Tests:** [`tests/test_bernays_public_domain.py`](../../tests/test_bernays_public_domain.py)
  proves serve + sha256 dedup no-op + `run_audit().ok == True` + the denylist
  (exactly the two PD titles at `public_domain`, zero denylisted titles), all
  offline with `FakeSourceClient` + temp DuckDB.
