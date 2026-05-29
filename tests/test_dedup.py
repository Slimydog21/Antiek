"""Tests for SPR-04 cross-source identity (``substrate.dedup``).

The five values are exercised directly:

- **Rigor (#3):** every identifier normalizer has a fixture PAIR asserting two
  surface forms yield the SAME key — DOI prefix/casing, ISBN-10↔13,
  arXiv version/old-vs-new, content-hash whitespace/casing/line-endings.
- **Fairness (#2):** the central cross-source merge (same DOI ×3 → one work)
  AND the false-merge guard (two "History"/"Anonymous" works stay apart) are
  both asserted — a layer that only merges, or only splits, is not dedup.
- **Honesty (#1):** the run report surfaces the per-key-type distribution
  incl. the LOW-confidence fallback count, not a green checkmark.
- **Defensibility (#5):** collapse retains every contributing source and the
  reconciled license names its winning source; canonical selection is proven
  order-independent (same set, shuffled, → same canonical).
- **§9.0 deny-by-default (M5):** an unverified duplicate can NEVER raise a work
  to servable.
"""

from __future__ import annotations

import random

from acquisition.licenses_core import (
    CC_LICENSE_ROWS,
    PUBLIC_DOMAIN_CONTENT_CLASS,
    resolve_against_table,
)
from substrate.constants import (
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from substrate.dedup import (
    Confidence,
    IdentityRecord,
    KeyType,
    collapse,
    document_id_basis,
    identity_key,
    normalize_arxiv_id,
    normalize_content_hash,
    normalize_doi,
    normalize_isbn,
    reconcile_license,
    summarize,
)

# A body comfortably above MIN_CONTENT_HASH_CHARS so the content-hash key is
# available where a test wants it.
LONG_BODY = (
    "The quality of a corpus depends on careful selection of legitimate "
    "sources and rigorous evaluation of each candidate document before it "
    "enters the substrate for retrieval and synthesis. A work's identity must "
    "rest on stable identifiers, never on a mutable title or author string, "
    "because generic titles collide and cross-source titles drift."
)

# A SECOND distinct body, comfortably above the content-hash floor, for fixtures
# that need two different works (so they do not collide on a shared content
# hash — a content hash legitimately merges two records with the same body).
OTHER_BODY = (
    "Frankenstein opens with a series of letters from an arctic explorer to his "
    "sister, framing the narrative of a scientist whose ambition to animate dead "
    "matter produces a creature he cannot answer for, a story about creation, "
    "abandonment, and the responsibilities the maker owes to the made."
)


# --------------------------------------------------------------------------
# M2 — identifier normalization (rigor #3): fixture pairs → same key.
# --------------------------------------------------------------------------


def test_normalize_doi_prefix_and_casing_collapse() -> None:
    assert normalize_doi("10.1/AB") == normalize_doi("https://doi.org/10.1/ab")
    assert normalize_doi("doi:10.1/AB") == "10.1/ab"
    assert normalize_doi("http://dx.doi.org/10.5555/Xy") == "10.5555/xy"
    assert normalize_doi(None) is None
    assert normalize_doi("   ") is None


def test_normalize_isbn10_and_isbn13_collapse() -> None:
    # 0-306-40615-2 (ISBN-10) ⇔ 978-0-306-40615-7 (its ISBN-13 form).
    assert normalize_isbn("0-306-40615-2") == normalize_isbn("978-0-306-40615-7")
    assert normalize_isbn("0306406152") == "9780306406157"
    # An ISBN-10 ending in X (check digit 10).
    assert normalize_isbn("097522980X") is not None
    # A structurally invalid ISBN (bad check digit) is not a usable identity.
    assert normalize_isbn("0-306-40615-9") is None
    assert normalize_isbn("not-an-isbn") is None
    assert normalize_isbn(None) is None


def test_normalize_arxiv_version_and_form_collapse() -> None:
    assert normalize_arxiv_id("2401.00001v2") == normalize_arxiv_id("2401.00001")
    assert normalize_arxiv_id("arXiv:2401.00001v5") == "2401.00001"
    # Old-style ids keep their archive-class/number structure (lowered).
    assert normalize_arxiv_id("math.GT/0309136") == "math.gt/0309136"
    assert normalize_arxiv_id("hep-th/9901001v3") == "hep-th/9901001"
    assert normalize_arxiv_id(None) is None


def test_normalize_content_hash_stable_under_extraction_noise() -> None:
    a = LONG_BODY
    # Same body, re-extracted with casing drift, doubled whitespace, CRLF line
    # endings, and a smart quote — must hash identically.
    b = ("  " + LONG_BODY.upper().replace(" ", "  ").replace("\n", "\r\n")
         + "  ").replace("'", "’")
    assert normalize_content_hash(a) == normalize_content_hash(b)
    assert normalize_content_hash(a) is not None


def test_normalize_content_hash_none_for_thin_body() -> None:
    assert normalize_content_hash("short stub") is None
    assert normalize_content_hash(None) is None
    assert normalize_content_hash("") is None


# --------------------------------------------------------------------------
# M2 — identity_key precedence + confidence.
# --------------------------------------------------------------------------


def test_identity_key_precedence_doi_beats_everything() -> None:
    rec = IdentityRecord(
        ref_id="r", source="oa", doi="10.1/X", isbn="9780306406157",
        arxiv_id="2401.1", title="T", author="A", body=LONG_BODY,
    )
    ikey = identity_key(rec)
    assert ikey.key_type is KeyType.DOI
    assert ikey.key == "10.1/x"
    assert ikey.confidence is Confidence.HIGH


def test_identity_key_precedence_order_isbn_arxiv_content() -> None:
    isbn = identity_key(IdentityRecord(
        ref_id="r", source="b", isbn="978-0-306-40615-7", arxiv_id="2401.1",
        body=LONG_BODY,
    ))
    assert isbn.key_type is KeyType.ISBN
    arx = identity_key(IdentityRecord(
        ref_id="r", source="a", arxiv_id="2401.00001v2", body=LONG_BODY,
    ))
    assert arx.key_type is KeyType.ARXIV
    content = identity_key(IdentityRecord(
        ref_id="r", source="pd", title="A Title", author="An Author",
        body=LONG_BODY,
    ))
    assert content.key_type is KeyType.CONTENT
    assert content.confidence is Confidence.HIGH


def test_identity_key_falls_back_to_low_confidence_title_author() -> None:
    # No stable id AND no body → the title+author fallback, flagged LOW.
    rec = IdentityRecord(ref_id="r", source="pd", title="History", author="Anonymous")
    ikey = identity_key(rec)
    assert ikey.key_type is KeyType.TITLE_AUTHOR
    assert ikey.confidence is Confidence.LOW


def test_identity_key_last_resort_keys_on_ref_id_when_no_title() -> None:
    # Neither stable id, nor body, nor title — identity is its own ref_id,
    # flagged LOW so it can never collapse into another work.
    a = identity_key(IdentityRecord(ref_id="a", source="x"))
    b = identity_key(IdentityRecord(ref_id="b", source="x"))
    assert a.confidence is Confidence.LOW and b.confidence is Confidence.LOW
    assert a.key != b.key


# --------------------------------------------------------------------------
# M4 — document_id basis contract (for SPR-01).
# --------------------------------------------------------------------------


def test_document_id_basis_is_namespaced_and_stable() -> None:
    rec = IdentityRecord(ref_id="r", source="oa", doi="https://doi.org/10.1/AB")
    basis = document_id_basis(identity_key(rec))
    assert basis == "doi:10.1/ab"
    # Same work re-fetched (different surface form, different ref) → same basis.
    rec2 = IdentityRecord(ref_id="other", source="pmc", doi="10.1/ab")
    assert document_id_basis(identity_key(rec2)) == basis


def test_document_id_basis_namespacing_prevents_cross_type_collision() -> None:
    # A DOI and an arXiv-id that happen to share a literal string must not
    # collide as document_id bases.
    doi = document_id_basis(identity_key(
        IdentityRecord(ref_id="d", source="oa", doi="2401.00001")))
    arx = document_id_basis(identity_key(
        IdentityRecord(ref_id="a", source="arxiv", arxiv_id="2401.00001")))
    assert doi != arx
    assert doi.startswith("doi:") and arx.startswith("arxiv:")


# --------------------------------------------------------------------------
# M3 — collapse + canonical selection (gate -k: same_doi_three_sources,
# generic_title_no_collapse).
# --------------------------------------------------------------------------


def test_collapse_same_doi_three_sources_to_one() -> None:
    # The central cross-source case: arXiv + OpenAlex + PMC, one DOI, titles
    # drifting by casing/whitespace → ONE canonical work.
    arxiv = IdentityRecord(
        ref_id="arxiv:1", source="arxiv", doi="10.1/Z",
        title="Scaling Laws  for Corpora", arxiv_id="2401.1",
    )
    openalex = IdentityRecord(
        ref_id="oa:1", source="openalex", doi="https://doi.org/10.1/z",
        title="Scaling laws for corpora", author="Ada Lovelace", body=LONG_BODY,
    )
    pmc = IdentityRecord(
        ref_id="pmc:1", source="pmc", doi="doi:10.1/Z",
        title="SCALING LAWS FOR CORPORA",
    )
    works = collapse([arxiv, openalex, pmc])
    assert len(works) == 1
    work = works[0]
    assert work.identity.key_type is KeyType.DOI
    assert work.identity.key == "10.1/z"
    # OpenAlex is canonical: it has title+author+body (completeness 3).
    assert work.canonical.ref_id == "oa:1"
    # All three sources retained as provenance.
    assert set(work.contributing_sources) == {"arxiv", "openalex", "pmc"}


def test_collapse_generic_title_no_collapse() -> None:
    # Two genuinely DIFFERENT works that share the generic title "History" by
    # "Anonymous", each with only the LOW-confidence fallback (no stable id, no
    # body) → must stay TWO works.
    a = IdentityRecord(ref_id="g:1", source="pd", title="History", author="Anonymous")
    b = IdentityRecord(ref_id="ia:1", source="archive", title="History", author="Anonymous")
    works = collapse([a, b])
    assert len(works) == 2
    assert {w.canonical.ref_id for w in works} == {"g:1", "ia:1"}
    assert all(w.identity.confidence is Confidence.LOW for w in works)


def test_collapse_distinct_dois_sharing_title_stay_apart() -> None:
    # Distinct DOIs that share a title are different works (the HIGH key, DOI,
    # differs) — they must not merge on the coincidental title.
    a = IdentityRecord(ref_id="a", source="oa", doi="10.1/AAA", title="Methods")
    b = IdentityRecord(ref_id="b", source="oa", doi="10.1/BBB", title="Methods")
    works = collapse([a, b])
    assert len(works) == 2


def test_collapse_canonical_selection_is_order_independent() -> None:
    # Same set, many shuffles → the SAME canonical record every time.
    members = [
        IdentityRecord(ref_id="thin", source="arxiv", doi="10.1/q", title="T"),
        IdentityRecord(ref_id="rich", source="openalex", doi="10.1/q",
                       title="T", author="A", body=LONG_BODY),
        IdentityRecord(ref_id="mid", source="pmc", doi="10.1/q", title="T", author="A"),
    ]
    rng = random.Random(20260529)
    canonicals = set()
    for _ in range(12):
        shuffled = members[:]
        rng.shuffle(shuffled)
        works = collapse(shuffled)
        assert len(works) == 1
        canonicals.add(works[0].canonical.ref_id)
    assert canonicals == {"rich"}  # most-complete metadata + longest body wins


def test_collapse_content_hash_merges_cross_extraction_duplicate() -> None:
    # No stable id, but the SAME body extracted twice (with noise) → the
    # content-hash collapses them; HIGH confidence.
    a = IdentityRecord(ref_id="pd:1", source="gutenberg", title="A Book",
                       author="Author One", body=LONG_BODY)
    b = IdentityRecord(ref_id="ia:1", source="archive", title="A Book (scan)",
                       author="Author One", body="  " + LONG_BODY.upper())
    works = collapse([a, b])
    assert len(works) == 1
    assert works[0].identity.key_type is KeyType.CONTENT
    assert works[0].identity.confidence is Confidence.HIGH


# --------------------------------------------------------------------------
# M3/M4 — idempotency (gate -k: idempotent_rerun).
# --------------------------------------------------------------------------


def test_idempotent_rerun_same_keys_zero_new_works() -> None:
    records = [
        IdentityRecord(ref_id="arxiv:1", source="arxiv", doi="10.1/a", arxiv_id="2401.1"),
        IdentityRecord(ref_id="oa:1", source="openalex", doi="10.1/a", title="P", author="A"),
        IdentityRecord(ref_id="pd:1", source="gutenberg", title="A Book",
                       author="Author", body=LONG_BODY),
    ]
    first = collapse(records)
    # Re-run over the SAME candidate set: identical identity keys.
    first_bases = sorted(document_id_basis(w.identity) for w in first)
    second = collapse(records)
    second_bases = sorted(document_id_basis(w.identity) for w in second)
    assert first_bases == second_bases
    assert len(first) == len(second)
    # The "second pass adds zero new works" contract: the union of the two runs'
    # document_id bases is exactly the first run's set — nothing new appeared.
    assert set(second_bases) == set(first_bases)


def test_idempotent_rerun_reingest_of_seen_work_is_noop() -> None:
    # Re-ingesting an already-seen work (same DOI, new ref) yields the same
    # document_id basis, so SPR-01's on_conflict=ignore makes it a no-op.
    seen = IdentityRecord(ref_id="oa:1", source="openalex", doi="10.1/seen", title="P")
    reingest = IdentityRecord(ref_id="pmc:9", source="pmc", doi="https://doi.org/10.1/SEEN")
    assert (document_id_basis(identity_key(seen))
            == document_id_basis(identity_key(reingest)))


# --------------------------------------------------------------------------
# M5 — license reconciliation (gate -k: license_reconcile).
# --------------------------------------------------------------------------


def _resolve(uri):
    """Resolve a license URI through the ONE legal home (licenses_core),
    exactly as the connectors do — never re-encoding CC ordering here."""
    return resolve_against_table(uri, CC_LICENSE_ROWS)


def test_license_reconcile_ccby_beats_gated_unknown() -> None:
    # CC-BY (positively verified) on OpenAlex; gated/unknown on arXiv.
    # Reconciliation → CC-BY, both sources recorded in the basis.
    ccby = _resolve("https://creativecommons.org/licenses/by/4.0/")
    unknown = _resolve(None)  # no license declared → gated
    arxiv = IdentityRecord(ref_id="arxiv:1", source="arxiv", doi="10.1/r", license=unknown)
    openalex = IdentityRecord(ref_id="oa:1", source="openalex", doi="10.1/r",
                              title="P", author="A", license=ccby)
    works = collapse([arxiv, openalex])
    assert len(works) == 1
    work = works[0]
    assert work.reconciled_license is not None
    assert work.reconciled_license.redistributable is True
    assert work.reconciled_license.content_class in SERVABLE_CONTENT_CLASSES
    # The winning license names its source; both contributing sources recorded.
    assert "CC BY" in work.license_basis
    assert "openalex" in work.license_basis
    assert "arxiv" in work.license_basis


def test_license_reconcile_unverified_never_raises_to_servable() -> None:
    # §9.0 catastrophe guard: a gated work + an UNVERIFIED (unknown-license)
    # duplicate must STAY gated. An unverified record can never raise a work to
    # servable on the strength of a source merely lacking a restriction.
    gated_a = _resolve(None)
    gated_b = _resolve("https://example.com/all-rights-reserved")
    rec_a = IdentityRecord(ref_id="a", source="arxiv", doi="10.1/g", license=gated_a)
    rec_b = IdentityRecord(ref_id="b", source="pmc", doi="10.1/g", license=gated_b)
    works = collapse([rec_a, rec_b])
    assert len(works) == 1
    work = works[0]
    assert work.reconciled_license is not None
    assert work.reconciled_license.redistributable is False
    assert work.reconciled_license.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert "GATED" in work.license_basis


def test_license_reconcile_public_domain_beats_attribution_obligation() -> None:
    # Most-permissive ranks public_domain (CC0/PDM, no obligation) above
    # source_declared_open (CC-BY, attribution obligation).
    cc0 = _resolve("https://creativecommons.org/publicdomain/zero/1.0/")
    ccby = _resolve("https://creativecommons.org/licenses/by/4.0/")
    assert cc0.content_class == PUBLIC_DOMAIN_CONTENT_CLASS
    winner, basis = reconcile_license([
        IdentityRecord(ref_id="x", source="openalex", license=ccby),
        IdentityRecord(ref_id="y", source="doaj", license=cc0),
    ])
    assert winner is not None
    assert winner.content_class == PUBLIC_DOMAIN_CONTENT_CLASS
    assert "doaj" in basis


def test_license_reconcile_no_signal_yields_none() -> None:
    # No member carried any resolution → nothing to reconcile.
    winner, basis = reconcile_license([
        IdentityRecord(ref_id="a", source="arxiv"),
        IdentityRecord(ref_id="b", source="pmc"),
    ])
    assert winner is None and basis is None


def test_license_reconcile_ties_keep_earliest_source() -> None:
    # Two equally-permissive (same rank) licenses → the EARLIER source wins,
    # for determinism.
    ccby = _resolve("https://creativecommons.org/licenses/by/4.0/")
    ccbysa = _resolve("https://creativecommons.org/licenses/by-sa/4.0/")
    winner, basis = reconcile_license([
        IdentityRecord(ref_id="first", source="openalex", license=ccby),
        IdentityRecord(ref_id="second", source="doaj", license=ccbysa),
    ])
    assert winner is ccby  # first-seen of the rank-1 tie
    assert "openalex" in basis


# --------------------------------------------------------------------------
# M3 — low-confidence fallback never collapses (gate -k: low_confidence_no_collapse).
# --------------------------------------------------------------------------


def test_low_confidence_no_collapse_even_on_identical_title_author() -> None:
    # Two records that are byte-identical in title+author but carry no stable id
    # and no body resolve to the SAME low-confidence key — yet must NOT merge,
    # because a LOW key is never authoritative for a merge.
    a = IdentityRecord(ref_id="a", source="pd", title="Poems", author="Anonymous")
    b = IdentityRecord(ref_id="b", source="archive", title="Poems", author="Anonymous")
    assert identity_key(a).key == identity_key(b).key  # same fallback hash
    assert identity_key(a).confidence is Confidence.LOW
    works = collapse([a, b])
    assert len(works) == 2  # but NOT collapsed


def test_low_confidence_does_not_block_high_confidence_collapse() -> None:
    # A LOW record alongside a genuine HIGH-key duplicate pair: the HIGH pair
    # still collapses; the LOW one stays its own work.
    low = IdentityRecord(ref_id="low", source="pd", title="History", author="Anonymous")
    h1 = IdentityRecord(ref_id="h1", source="arxiv", doi="10.1/x", title="P")
    h2 = IdentityRecord(ref_id="h2", source="oa", doi="10.1/x", title="P", author="A")
    works = collapse([low, h1, h2])
    assert len(works) == 2  # the DOI pair collapsed, the LOW one stands alone


# --------------------------------------------------------------------------
# M4 — orchestrator integration: plan_corpus computes the identity over the
# SAME candidate set, reports the key-type distribution, and is an idempotent
# re-run (the seam wired into tools/run_corpus_ingest.py is exercised, not just
# the pure layer).
# --------------------------------------------------------------------------


def _planned(ref_id, *, source, doi=None, arxiv_id=None, source_id=None,
             isbn=None, title=None, author=None, text="", assess_body=False,
             sink=None):
    from acquisition.corpus_quality import CandidateRef
    from tools.run_corpus_ingest import PlannedCandidate

    def _ingest(db_path: str, doc_basis: str) -> str:
        if sink is not None:
            sink.append((ref_id, doc_basis))
        return f"wrote {ref_id}"

    return PlannedCandidate(
        ref=CandidateRef(ref_id=ref_id, doi=doi, arxiv_id=arxiv_id,
                         source_id=source_id, isbn=isbn, title=title,
                         author=author, body=text or None if assess_body else None),
        source=source, assessable_text=text, assess_body=assess_body,
        ingest=_ingest,
        allow_null_author_reason="test record" if author is None else None,
    )


def test_plan_corpus_reports_identity_and_document_id_basis() -> None:
    from tools.run_corpus_ingest import plan_corpus

    plan = plan_corpus([
        _planned("oa:1", source="open_access", doi="https://doi.org/10.1/AB",
                 title="A Paper"),
        _planned("arxiv:1", source="arxiv", arxiv_id="2401.00001v2",
                 title="Another", author="X", text=LONG_BODY, assess_body=True),
    ])
    # The document_id basis is the SPR-04 normalized key, surfaced per kept doc.
    bases = dict(plan.document_id_bases)
    assert bases["oa:1"] == "doi:10.1/ab"  # prefix stripped, lowered
    assert bases["arxiv:1"] == "arxiv:2401.00001"  # version dropped
    # The identity report carries the per-key-type distribution (rigor #1).
    assert plan.identity_report.key_type_counts.get("doi") == 1
    assert plan.identity_report.key_type_counts.get("arxiv") == 1
    assert "key types" in plan.render()


def test_plan_corpus_identity_idempotent_rerun_same_bases() -> None:
    from tools.run_corpus_ingest import plan_corpus

    cands = [
        _planned("oa:1", source="open_access", doi="10.1/seen", title="P"),
        _planned("oa:2", source="open_access", doi="10.1/other", title="Q"),
    ]
    first = dict(plan_corpus(cands).document_id_bases)
    second = dict(plan_corpus(cands).document_id_bases)
    assert first == second  # identity is stable across runs


def test_dedup_candidates_keys_through_substrate_identity() -> None:
    # The unification (defect-fix): the orchestrator's cross-source dedup driver
    # IS the substrate.dedup identity, not a second ladder. A re-fetch of the
    # same paper with a different DOI surface form (prefix/casing) collapses,
    # because dedup_candidates normalizes the DOI through substrate.dedup.
    from acquisition.corpus_quality import CandidateRef, dedup_candidates

    a = CandidateRef(ref_id="oa:1", doi="10.1/Z", title="A Paper")
    b = CandidateRef(ref_id="pmc:1", doi="https://doi.org/10.1/z", title="A paper")
    res = dedup_candidates([a, b])
    assert len(res.kept) == 1
    assert res.dropped[0].key_kind is KeyType.DOI
    # And the kept survivor's document_id basis is that SAME normalized key.
    assert document_id_basis(identity_key(
        IdentityRecord(ref_id="oa:1", source="oa", doi="10.1/Z"))) == "doi:10.1/z"


def test_orchestrator_dry_run_end_to_end_exercises_seam(monkeypatch, capsys) -> None:
    # Defect-fix for the "orchestrator dry-run" gate: drive the REAL main()
    # entrypoint end-to-end (discover_all -> plan_corpus -> execute_plan) with
    # discovery stubbed so there is no network and no DB. This exercises the
    # integration seam the verbatim --oa-query gate never reached (it errored at
    # the --oa-source guard before planning). The dry-run must write nothing,
    # collapse the cross-source duplicate, and PRINT the key-type distribution
    # over real connector-shaped candidates (rigor #1).
    from tools import run_corpus_ingest as orch

    sink: list = []

    def _fake_discover(args):
        # Three sources, with a genuine cross-source DOI duplicate (arxiv+oa+pmc
        # share 10.1/x), one Gutenberg book keyed on its source-id, and one
        # generic-title work that must stay LOW and never collapse.
        return [
            _planned("arxiv:2401.1", source="arxiv", arxiv_id="2401.1",
                     doi="10.1/X", title="Scaling Laws", text=LONG_BODY,
                     assess_body=True, sink=sink),
            _planned("oa:1", source="open_access", doi="https://doi.org/10.1/x",
                     title="scaling laws", author="A", sink=sink),
            _planned("pmc:1", source="open_access", doi="doi:10.1/X",
                     title="SCALING LAWS", sink=sink),
            _planned("gutenberg:84", source="public_domain",
                     source_id="project_gutenberg:84", title="Frankenstein",
                     author="Mary Shelley", text=OTHER_BODY, assess_body=True,
                     sink=sink),
        ]

    monkeypatch.setattr(orch, "discover_all", _fake_discover)
    rc = orch.main(["--source", "arxiv", "--arxiv-query", "x", "--dry-run"])
    out = capsys.readouterr().out

    assert rc == 0
    # Dry-run wrote nothing: NO ingest thunk ran.
    assert sink == []
    assert "DRY RUN" in out and "wrote nothing" in out
    # The cross-source DOI duplicate collapsed (3 papers -> 1); the book stands
    # apart on its own source-id. So 2 kept, 2 dropped.
    assert "2 kept, 2 dropped" in out
    # The identity report printed the per-key-type distribution (rigor #1).
    assert "key types:" in out
    assert "doi=1" in out  # the collapsed paper resolved on its DOI
    # The book resolved on its source-local id (not the LOW title fallback) —
    # the SOURCE_ID precedence level reachable only through the real pipeline.
    assert "source_id=1" in out
    assert "low-confidence fallback: 0" in out


def test_orchestrator_real_run_threads_basis_to_thunk(monkeypatch) -> None:
    # A non-dry real run hands each thunk its document_id basis — the identity
    # the plan computed reaches the write boundary (defect-fix: the basis is
    # consumed, not computed-and-discarded). Local db_path, so no prod guard.
    from tools import run_corpus_ingest as orch

    sink: list = []

    def _fake_discover(args):
        return [
            _planned("oa:1", source="open_access", doi="10.1/AB",
                     title="A Paper", sink=sink),
            _planned("gutenberg:84", source="public_domain",
                     source_id="project_gutenberg:84", title="Frankenstein",
                     author="Mary Shelley", text=LONG_BODY, assess_body=True,
                     sink=sink),
        ]

    monkeypatch.setattr(orch, "discover_all", _fake_discover)
    rc = orch.main([
        "--source", "open_access", "--oa-query", "x",
        "--db-path", "/tmp/spr04-local.duckdb",
    ])
    assert rc == 0
    # Each thunk received its document_id basis: the OA DOI key + the book's
    # namespaced source-id key — exactly what dedup keyed identity on.
    by_ref = dict(sink)
    assert by_ref["oa:1"] == "doi:10.1/ab"
    assert by_ref["gutenberg:84"] == "source_id:project_gutenberg:84"


# --------------------------------------------------------------------------
# Honesty (#1) — the run report surfaces the key-type distribution.
# --------------------------------------------------------------------------


def test_summarize_reports_key_type_distribution_incl_fallback() -> None:
    records = [
        IdentityRecord(ref_id="d1", source="oa", doi="10.1/a"),
        IdentityRecord(ref_id="d2", source="pmc", doi="10.1/a"),  # dup of d1
        IdentityRecord(ref_id="x1", source="arxiv", arxiv_id="2401.1"),
        IdentityRecord(ref_id="b1", source="pd", title="H", author="Anonymous"),
    ]
    works = collapse(records)
    report = summarize(works, total_records=len(records))
    assert report.kept == 3  # d1/d2 collapsed
    assert report.collapsed_away == 1
    assert report.key_type_counts.get("doi") == 1
    assert report.key_type_counts.get("arxiv") == 1
    assert report.low_confidence == 1
    rendered = report.render()
    assert "low-confidence fallback: 1" in rendered
    assert "1 duplicates collapsed" in rendered
