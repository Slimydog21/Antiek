# arXiv on-demand PDF storage — T1 only; T2 deferred; T3 never

**Decision date:** 2026-05-30 (SPR-04, arxiv-ingest, M2 storage tiering)
**Status:** ✅ Implemented — `store_pdf_for_arxiv_row` in
`acquisition/arxiv/store.py` fetches-stores-promotes **T1 only**, returns a
`deferred` outcome for **T2** (no write), and `refused` for **T3** (no write).
**Owner:** SPR-04 on-demand PDF acquisition + storage tiering
**Gate:** the §9.0 / counsel legal gate (plus a genuine non-commercial serving
mode) is what would later promote T2 to fetch-to-store. Until both, T1 only.

## The decision

When SPR-04 fetches a paper's PDF on demand, it writes the extracted body to
`documents.raw_text` and promotes `content_class` to the license-derived servable
class **for T1 papers only** (CC0 → `public_domain`; CC-BY / CC-BY-SA →
`source_declared_open`). For every other tier it writes NOTHING:

- **T3** (arXiv-default non-exclusive license, all-rights-reserved, ND, any
  unrecognised URI, and the absent/empty case — the corpus majority) → **REFUSED**.
  The body is never written; the row stays at the gated floor
  (`restricted_pending_opt_in`) with `raw_text` NULL.
- **T2** (CC-BY-NC*) → **DEFERRED**. The body is never written; the row is left
  untouched, pending counsel.
- **T1** (CC0 / CC-BY / CC-BY-SA) → stored, promoted, indexed for search.

## Why this DIVERGES from the SPR-04 sprint-page wording (recorded honestly)

The SPR-04 sprint page describes a "(T2 read-only)" tier and says "T2 bodies may
be fetched for in-app reading". This implementation does **not** fetch-to-store or
promote T2 today. The divergence is deliberate and follows directly from already
shipped, binding code — it is honesty + defensibility, not a silent softening of
the spec:

1. **The canonical resolver already gates CC-BY-NC.**
   `acquisition/licenses_core.py` resolves CC-BY-NC to `redistributable=False` +
   `GATED_DEFAULT_CONTENT_CLASS`, with the binding rationale *"NC forbids
   commercial reuse; Antiek's ad-funded serving is commercial → gated."* So a T2
   paper's servable `content_class` is the gated floor — there is no servable
   class to promote it to.

2. **SPR-02's serve guard mechanically precludes a served T2 body.**
   `substrate/books/serve_guard.py::serve_full_text_guarded` re-derives the tier
   from the immutable `<license>` URI and raises `T3BodyServeError` on any served
   body whose tier is not in `_BODY_SERVABLE_TIERS = {T1}`. So if SPR-04 *did*
   promote a T2 row's `content_class` to servable and store its body,
   `serve_full_text` would emit it and the guard would RAISE. T2
   storage-for-serving is therefore **mechanically precluded today** — storing it
   would be a no-op at best and a latent rights leak at worst. SPR-04's store path
   runs that same guard as a post-store self-check, so a mis-promotion fails loudly
   at WRITE time, not silently at read time.

3. **Deny-by-default on an unresolved legal question.** Whether a
   primarily-commercial platform serving an NC body (even ad-free) is "directed
   toward commercial advantage" is fact-specific and has been litigated to
   inconsistent outcomes. A wrong promotion of a body out of storage is the
   *cardinal* redistribution violation; the conservative reading biases the
   ambiguous case to deny.

The "T2 in-app reading" world is the **same §9.0/counsel-gated future** as SPR-02's
`{T1}`→`{T1,T2}` body-servable flip — a non-commercial serving mode that does not
exist yet. See `docs/decisions/arxiv-t2-noncommercial-serving.md`, which owns the
binding posture and the one-line reversal. When that reversal lands (counsel sign-
off + a genuine non-commercial serving mode + the lockstep `licenses_core` flip),
SPR-04's gate widens to fetch-to-store T2 in lockstep — and not before.

## Why T3 is never stored — the cardinal sin

A wrong T3 → servable promotion rehosts and (via the ad border) monetizes a paper
Antiek holds no redistribution right to — the *Hachette v. Internet Archive* /
*Bartz v. Anthropic* liability the §9.0 gate exists to avoid. A wrong T1 → gated
demotion merely leaves money on the table. The two errors are not symmetric, so
every ambiguous input biases to "do not store". The test suite asserts the
negative directly: after a store attempt on a T3-seeded row, `raw_text` is still
NULL and `content_class` is still `restricted_pending_opt_in`.

## Operate on the existing row — no parallel ingest path

SPR-01's `oai_persist` already inserted one `documents` row per paper, keyed by
`arxiv_doc_id(arxiv_id)`, at the gated floor, with `license_uri` / `rights_tier` /
`license_content_class` in `documents.metadata`. SPR-04 **UPDATES that row**
(`raw_text` + promoted `content_class` + an additive `pdf_acquisition` provenance
block). It does NOT call `acquisition/books/adapter.py::ingest_servable_book`,
which would mint a `book_doc_id` row — that would duplicate the paper and orphan
its rights metadata. The license anchors (`license_uri` / `license_basis` /
`rights_tier`) are immutable here and are never touched.

## Defensibility — every stored body is auditable from the row

A T1 store records, in `documents.metadata.pdf_acquisition`: `source_url`,
`fetched_at`, `sha256`, `byte_size`, `page_count`. So an arXiv compliance query
("where did this body come from, are these the bytes we fetched, which papers do
we host full text for") is answerable from the row alone, without re-fetching.
