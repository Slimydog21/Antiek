# Audit wave 3 — the calls that are the operator's, not the engineer's

**Date:** 2026-09-23
**Status:** PROPOSED — four decisions recorded with a recommendation each; none executed
**Owner:** Antiek — audit wave 3 (46-agent executing-refuter audit of 2026-09-22, 19 confirmed findings)
**Surfaces:**
`services/antiek_format/single_file.py:93-115` + `native_reader.py:274` + `sidecar_reader.py:328` (signature verification, #10);
`processing/embedding/embed.py` (`SentenceTransformerEmbedding`, #2) + `processing/chunking/chunker.py:31` (`DEFAULT_MAX_CHUNK_TOKENS = 2000`);
`acquisition/corpus_quality.py` (`check_metadata_completeness`, #15) + `tools/run_corpus_ingest.py:666,764,903,1086,1174,1283` (the templated reasons);
`substrate/books/servability.py` / the public chunk gate (NULL `content_class` grandfathering, the #13 residual);
`services/html_projection/resolvers/substrate_refs.py` + `adapters/deliverable.py` (source-less claims, the #5 residual).
**Builds on:** the 15 wave-3 repairs that WERE engineering calls and shipped on
`fix/audit-wave3` (Tier 1: #16 #11 #19 #1 #3; Tier 2: #4 #7 #8 #9; Tier 4: #17 #18 #5
#6 #13 #14 #15 #12; plus the #2 instrumentation). Each of those has a seeded-red
test and a killed mutant. What follows is what a test cannot settle.

---

## Why these are recorded and not built

Every item below changes a POLICY — who is trusted, what the corpus admits,
what a stored vector is allowed to mean, whether legacy rows keep a privilege —
or forces a corpus-wide re-computation. An engineer guessing the policy and
shipping it would produce code that is hard to vary in exactly the wrong way:
confident, tested, and possibly not what the operator wants. The audit's rule
was "record, recommend, do not guess", and this file is the record.

---

## 1. `.antiek` signatures have no trust anchor (#10)

**Finding.** `verify_single_file_html`, the container reader and the sidecar
reader all verify the signature against the public key **the artifact itself
carries** (`manifest.creator_pubkey` / the signature island's `pubkey`). There
is no anchor: any producer satisfies `signature_valid=True` by minting a
keypair. `ingest_antiek` then uses that verdict as the boundary that exempts a
"born-Antiek" artifact from foreign-HTML quarantine and admits it to the
round-trip demand signal.

**What the signature does prove today:** integrity — the bytes were not
altered since *someone* signed them. **What it does not prove:** that the
someone was this instance, this operator, or anyone we have ever met. The
ingest boundary reads it as the second thing.

**Options.**
1. **Operator-pinned signer set.** `~/.antiek/settings/trusted_signers.json`
   listing the public keys this instance trusts (the local `native_writer`
   keypair is trusted by construction; a partner's key is added by hand).
   `signature_valid` becomes `signature_valid AND pubkey in trusted_signers`.
   Unknown key → the artifact is treated as FOREIGN (quarantine path), not
   rejected. Lowest blast radius; matches the existing settings model.
2. **Trust-on-first-use per `creator_user_id`.** Remember the first key seen
   per creator and alarm on a change. Weaker (the first sight is trusted
   blind) and adds state to ingest.
3. **Rename the boundary.** Keep verification as-is but stop treating
   `signature_valid` as "born-Antiek": everything ingested goes through the
   foreign quarantine, and the round-trip detector admits only artifacts whose
   key is the local writer's. Equivalent to (1) with an empty partner list.

**Recommendation:** (1), with (3) as the interim default — i.e. until a signer
list exists, only the local writer's key exempts an artifact from quarantine.
The change is ~30 lines across `ingest_antiek.py` and a new
`settings/trusted_signers.py`; the test is "an artifact signed with a fresh
keypair is quarantined; one signed with the local writer's key is not".

**Why it is the operator's call:** it decides whether a partner's `.antiek`
file is trusted content or foreign content, which is a product relationship,
not a code property.

---

## 2. The embedding window is 256 word-pieces; the chunk default is 2000 words (#2)

**Finding.** `SentenceTransformerEmbedding.encode` hands the whole chunk to
`all-MiniLM-L6-v2`, whose `max_seq_length` is 256 word-pieces. The model
silently drops everything after that. `chunk_markdown` defaults to
`DEFAULT_MAX_CHUNK_TOKENS = 2000` whitespace words and every ingest path uses
the default, so any chunk longer than roughly 200 English words is embedded
by its opening words only — and the vector is stored, ranked and served as if
it stood for the whole `chunks.text`.

**What shipped in wave 3:** accounting, not a cure. Every `encode` is
counted, an over-window input is counted as truncated, the first truncation
in a process prints one stderr line with the numbers, and
`truncation_ratio` exposes the running rate. The degradation is now visible;
it is not gone.

**Options.**
1. **Chunk to the model window.** Set the default chunk size for the
   sentence-transformer path to ~180 words (≈256 word-pieces with headroom),
   re-chunk and re-embed the corpus with `tools/backfill_embeddings_meta.py`'s
   verified path. Retrieval granularity changes (more, smaller chunks);
   every downstream that assumes chunk size (citations, reader anchors)
   must be checked.
2. **Embed with a longer-window model.** `bge-m3` / `nomic-embed-text-v1.5`
   read 8k tokens. Changes the provider identity (every stored vector is
   re-pinned — the wave-3 pin makes this LOUD rather than silent), ~5x the
   model size, slower ingest.
3. **Chunk-level pooling.** Embed each ≤256-piece window of a chunk and store
   the mean (or all windows). Keeps chunk size; the vector then represents
   the whole text, at N× encode cost.

**Recommendation:** (1) for the corpus as it is (MiniLM is the pinned
provider and the platform's retrieval tests assume it), measured first: run
the accounting for one full ingest and read `truncation_ratio` — if it is
under ~5% the cure can wait; the audit's estimate from the chunker default is
that it is well above that. Record `truncated` per chunk in `embeddings_meta`
when the re-embed runs, so the flag never has to be inferred again.

**Why it is the operator's call:** every option re-embeds the corpus (hours
of ingest downtime — `antiek.service` is a single writer) and (1) changes
what a "chunk" is in the reader.

---

## 3. Should author-less records be admitted to the corpus at all? (#15)

**Finding.** `check_metadata_completeness` allows a null author when the
caller states an `allow_null_author_reason` — an "explicit auditable
decision". Every producer in `tools/run_corpus_ingest.py` states one, for
every author-less record, from a template ("open-access record exposes no
author at discovery"). The hatch is satisfied by construction: on the
corpus-ingest path the gate can never reject a candidate for a missing author.

**What shipped in wave 3:** the admission is recorded on the `CheckResult`
(`admitted_by_exception`), exposed on the verdict, counted and tallied per
reason on the run report and rendered. The count is now a number the
operator can read after every run.

**The decision.** The templated reasons are TRUE statements about the record
(the discovery API exposed no author). The question is whether that is an
acceptable reason to admit, and it is a corpus-policy question:
1. **Admit and count** (today, after wave 3). Author-less works enter with
   the reason on record; the report shows how many.
2. **Admit only from sources that cannot carry an author** (PD scans, some
   OA aggregators) and reject from sources that should (arXiv, Crossref,
   publisher catalogs) — a per-source allowlist in the producer, not a
   template.
3. **Reject** unless a human supplied the reason for that record.

**Recommendation:** (2). It keeps the hatch meaningful (a missing author on
arXiv is a data defect, on a 1910 scan it is the record) and needs no human
in the loop. Implement as a `NULL_AUTHOR_ACCEPTABLE_SOURCES` set in
`run_corpus_ingest.py` consulted before the template is attached.

---

## 4. NULL `content_class` is grandfathered as public (the #13 residual)

**Finding.** The public chunk gate treats a NULL `content_class` as servable
("legacy rows"). Wave 3 closed the producer that could create a NEW NULL row
(books are now born classified), but the grandfathering itself stands: any
NULL-classed row that already exists, and any future producer that forgets
the class, is public by default — the one place in the rights system that
fails OPEN.

**Options.**
1. **Backfill then flip.** Count NULL rows (`SELECT count(*) FROM documents
   WHERE content_class IS NULL`), classify them by source (most legacy rows
   have a known source tier), then change the gate to deny NULL. Deny-by-
   default everywhere, consistent with `GATED_DEFAULT_CONTENT_CLASS`.
2. **Flip without backfill.** Every NULL row becomes gated (metadata-only)
   immediately. Safe for rights, visible to users as content disappearing
   from full-text search until backfilled.
3. **Keep grandfathering, add a lint.** A guard test that fails when any
   producer can insert a document without a class. Cheap; does not fix the
   existing rows.

**Recommendation:** (1), with (3)'s guard test shipped first (it is the same
shape as `tests/test_insert_chunk_names_its_provider.py` and can land now).
The backfill is one operator command under the ingest-downtime window.

---

## 5. A claim with no source document resolves to `None` (the #5 residual)

**Finding.** After wave 3 the resolver returns the gated default for a node
that NAMES a source document whose rights cannot be read. A node that names
no source at all still resolves to `content_class=None`, which the deliverable
adapter reads as operator-authored (servable) and the notebook adapter reads
as not servable. For a `question` node that is right (the operator wrote the
question). For a `claim` with no `supported_by` edge it is an unsupported
claim being exported in full under the operator's name.

**Options.**
1. **Kind-aware default in the resolver:** `question`/`synthesized` → `None`
   (own content); `claim`/`insight`/`evidence` with no source → gated
   default. Small, and keeps the notebook/deliverable adapters unchanged.
2. **Refuse to project unsupported claims** — the projection omits them with
   an "unsupported" marker. Stronger; changes what a deliverable shows.

**Recommendation:** (1). The test is one line per node kind in
`services/html_projection/tests/test_substrate_refs.py`.

---

## Also noted, no decision needed

* The three free-text PD gates (`internet_archive.py`, `library_of_congress.py`,
  `public_domain.py`) carry three copies of the negation / copyright-claim
  regexes, and `public_domain.py`'s copyright-claim regex is the weakest of
  the three (it accepted "Public domain in Canada; may be under copyright
  elsewhere" before the jurisdiction rule gated it). One shared module, as
  `pd_jurisdiction.py` now is for the jurisdiction rule, is the next step and
  is engineering, not policy.
* Dependabot's "31 vulnerabilities" on the default branch are all in
  `apps/reading/package-lock.json`; the 14 critical/high are
  `scope=development` (axios, vite, minimatch, form-data). The only two
  runtime-scope alerts are medium react-router, fixed by the open Dependabot
  PR #3355.
