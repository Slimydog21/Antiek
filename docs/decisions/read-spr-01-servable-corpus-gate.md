# Servable-corpus legal gate — Read SPR-01

**Date:** 2026-05-25
**Branch:** `read/wave-1-legal-spine`
**Source spec:** `specs/read/sprint-01-book-asset-and-corpus-gate.html`
**Status:** Built. 7 milestones landed; 31 corpus-gate tests + 2 reader-TOC
tests green; full suite shows no new failures; latency lock intact.

## What this doc records — and why it has to exist

This is the document a future maintainer (or counsel) reads to defend why
a given book was, or wasn't, served full text. The spec names this the
sprint "whose decisions most need to survive scrutiny," so the
definitions and their legal basis are written down here rather than left
implicit in code.

## The thesis: Spotify, not Internet Archive

The Read workflow serves book full text **only** for content whose
license permits it. The single highest-liability move in the product is
"aggregate arbitrary copyrighted books and serve them with ads" — the
exact fact pattern enjoined in **_Hachette v. Internet Archive_** (2d Cir.
2024), which killed the structural fair-use defence for aggregate-and-
serve. **_Bartz v. Anthropic_** (~$1.5B settlement) then priced the
downside: post-serve damages dwarf the cost of pre-serve gating. The gate
encodes both lessons — deny by default, and make takedown cheap and total.

## The load-bearing design decision: servability is derived, not stored

There is **no `servability_status` column.** Servability is a *projection*
over the existing `documents.content_class` column — the same column the
chunk-search G1 gate keys off in `substrate/graph/search.py`. A second,
parallel status column was considered and rejected: it would inevitably
drift from G1, and **a gate that can drift is a gate that fails open.**

The projection lives in exactly one function,
`substrate.books.servability.servability_of(content_class, taken_down)`,
and an import-time assertion guarantees the set of content classes it
calls servable equals `SERVABLE_CONTENT_CLASSES` (the SQL allowlist used
at the data layer). The UI-layer predicate and the data-layer SQL cannot
disagree about whether a book may be served.

### The servability vocabulary (`BOOK_SERVABILITY_STATUSES`)

| Status | Derived from `content_class` | Full text served? |
|---|---|---|
| `public_domain` | `public_domain` | **yes** |
| `platform_authored` | `user_owned` / `user_public_contribution` | **yes** |
| `publisher_opted_in` | `opt_in_licensed` | **yes** |
| `gated_metadata_only` | `restricted_pending_opt_in`, **NULL**, unrecognised | no — bounded snippet only |
| `taken_down` | (any) + `book_assets.taken_down` override | no — nothing, not even a snippet |

### Two deliberate asymmetries

1. **Deny-by-default allowlist, stricter than the chunk-search gate.**
   Full-text serving uses an *allowlist* (`SERVABLE_CONTENT_CLASSES`).
   This is intentionally stricter than the chunk-search G1 gate's
   *denylist*, where NULL `content_class` passes as legacy/grandfathered.
   Serving a whole book is a far higher-liability act than returning a
   ≤500-char research snippet, so unknown / NULL / restricted content
   resolves to `gated_metadata_only` here — over the **same column**, so
   nothing drifts. The default for "aggregated from online, unknown
   rights" is therefore gated, by construction.

2. **The snippet line is the _Authors Guild v. Google_ line.** A gated
   book returns at most `SERVE_SNIPPET_MAX_CHARS` (500) of body —
   **_Authors Guild v. Google_** (2d Cir. 2015) upheld bounded snippet
   view of in-copyright books as fair use. A servable book returns the
   whole body. A taken-down book returns nothing. Three legally-distinct
   regimes, three outcomes.

## Takedown reuses the existing gate (no new mechanism)

`substrate.books.takedown.take_down` does five things atomically under
the single write lock:

1. saves the current `content_class` to `book_assets.pre_takedown_content_class` (reversibility),
2. moves `documents.content_class` to `restricted_pending_opt_in`
   (`TAKEDOWN_CONTENT_CLASS`) — the **existing** restricted gate, so the
   book vanishes from BOTH the full-text serve allowlist AND the
   chunk-search G1 denylist with zero new gating code,
3. nulls `documents.raw_text` (purges the cached served full text),
4. flips `book_assets.taken_down = TRUE` (the override the projection
   reads as `TAKEN_DOWN`, distinct from merely gated),
5. emits `book.taken_down` + `book.servability_changed` audit events.

Takedown is an **override orthogonal to the license**: a taken-down
public-domain book stays public-domain underneath, and `reinstate`
restores the saved class. `raw_text` is *not* restored on reinstate
(re-ingestion required) — takedown is meant to be heavy to undo.

## The DuckDB constraint that shaped the implementation

DuckDB 1.5.2 cannot `UPDATE` a **secondary-indexed** column
(`content_class`, `ip_holder_id`) on a row that is the target of a
foreign key (`chunks` and `book_assets` both reference
`documents.document_id`): it rejects the implied delete-half of its
delete+reinsert update path. Unindexed columns (`raw_text`) update fine.
The workaround is confined to one documented primitive,
`substrate.graph.ops.update_document_gate_columns`, which drops the
affected index(es), runs the UPDATE, and recreates them — atomic under
the write lock, invisible to readers. Every post-ingest gate mutation
(publisher opt-in, takedown, reinstate) routes through it. This also
provides the correct primitive that the latent
`middleware/ip_holder_resolver.apply_resolved_ip_holder` bug needs (that
function's raw UPDATE would fail once a document has chunks).

## Steelman of the rejected alternative (rigor #2)

The Internet-Archive model — serve broadly, take down on complaint — is
genuinely more content, faster, and was a real library's good-faith
posture. It collapses on the law, not the engineering: *Hachette* removed
the fair-use cover for aggregate-and-serve, and *Bartz* showed
complaint-driven post-serve takedown is the expensive path. The steelman
only holds via **licensing** (which flips titles to servable through this
same gate), never via posture. We deny by default and let licensing open
the gate.

## Intellectual honesty — where detection is fallible (rigor #1)

"Public domain" is itself error-prone: a public-domain work can carry a
copyrighted modern **translation**, edition, or introduction. The gate
does not try to be clever about this. When provenance is uncertain, the
operator simply does not pass a servable `content_class`, and the book
lands `gated_metadata_only` by default. A hopeful classifier never marks
uncertain content servable. (Tested:
`test_public_domain_text_with_copyrighted_translation_is_gated_when_uncertain`.)

## What is explicitly NOT in this sprint

Publisher outreach / opt-in emails (gated on G2 lawyer review),
disbursement of accrued escrow (G2 + G3), buy/sell marketplace (§9.10),
multi-user ownership of the corpus (Sprint 22 / gate G7). Accrual of ad
revenue is SPR-09; serving is gated here, payout stays gated there.

## Open question escalated to the operator + G2 counsel

**What exactly is "servable" for content "aggregated from online"?** The
code's answer is unambiguous — unknown rights ⇒ `gated_metadata_only`,
snippet only. But the *line* on what may be aggregated and snippet-shown
at all (vs. not ingested) is a counsel question, not a code question. The
gate is built so that whatever counsel decides, flipping a title's
`content_class` is the only change needed.

## Files

- `substrate/books/servability.py` — the projection (M2)
- `substrate/books/model.py` — `book_assets` CRUD + `BookAsset` (M1, M7)
- `substrate/books/serve.py` — data-layer serve gate (M3)
- `substrate/books/takedown.py` — takedown + reinstate (M4)
- `substrate/books/ingest.py` — registration: provenance, ip_holder, deny-by-default (M5)
- `interfaces/research/api/books.py` — servable-corpus query API (M6)
- `substrate/graph/schema.py` — `book_assets` table (V7)
- `substrate/graph/ops.py` — `update_document_gate_columns` + `insert_document` gate columns
- `substrate/constants.py` — §I servable-corpus constants
- `substrate/schemas/events.py` — `book.servability_changed` + `book.taken_down` (v14)
- `acquisition/books/reader.py` — TOC/outline extraction
- `acquisition/books/adapter.py` — `ingest_servable_book` orchestrator
- `tests/test_book_corpus_gate.py` — 31 tests
