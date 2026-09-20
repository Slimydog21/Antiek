"""research_only — the derivable-only rights state (books/publishers SPR-1).

The operator's product (ii) is a discounted ingestion whose asset the buyer never
reads: an agent ingests it, and all the buyer interacts with is the notes and
analysis in the research outcome artifact. Two promises carry that product, and
this file is where they are pinned.

INVARIANT 1 — no serve path returns a research_only body. Every path below was
found by tracing the callers of ``serve_full_text`` and the readers of
``documents.raw_text``, not from a list. The owner paths are asserted alongside
the public ones, because the person who paid for the ingestion IS the owner and
is exactly who the terms withhold the work from. That is the single way this
state differs from ``personal_reading``, so it is the assertion that would catch
the two collapsing back together.

INVARIANT 2 — a derived claim citing a research_only chunk still renders its
provenance, and the provenance does not leak the body. A research artifact whose
claims cannot name their sources is unfalsifiable, so citability is part of the
product, not a concession to it. Each projection adapter is asserted to emit the
citation (title, ip_holder, locator) while the passage is absent from the
serialized doc-model entirely — absent, not merely hidden in the rendered HTML,
since an island carries whatever the model carries.

Every body-bearing assertion scans the WHOLE serialized result for a sentinel
rather than checking one field, so a leak through a field nobody thought to name
still fails the test. Against a temp DuckDB with a deterministic stub embedding —
no live network, no prod DB.
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.ad_inventory.attribution import PUBLIC_GRAPH_CONTENT_CLASSES
from substrate.books.servability import ServabilityStatus, is_servable_full_text, servability_of
from substrate.books.serve import serve_full_text
from substrate.books.serve_guard import (
    guard_candidate_full_text,
    guard_document_candidate_full_text,
    serve_full_text_guarded,
)
from substrate.collective_graph.eligibility import NON_ATTRIBUTABLE_CONTENT_CLASSES
from substrate.constants import (
    NON_TRAINABLE_CONTENT_CLASSES,
    PERSONAL_READABLE_CONTENT_CLASSES,
    RESEARCH_ONLY_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
    SERVE_SNIPPET_MAX_CHARS,
    TURBOPUFFER_INDEX_CONTENT_CLASSES,
)
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.retrieval_gate import (
    _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES,
    PERSONAL_ONLY_CONTENT_CLASSES,
    RESEARCH_ONLY_CONTENT_CLASSES,
    RESTRICTED_CONTENT_CLASSES,
    is_chunk_body_withheld,
)
from substrate.graph.schema import init_database
from substrate.graph.search import search
from substrate.rights.research_only import (
    BRIEF_QUOTATION,
    DEFAULT_QUOTATION_POLICY,
    DERIVED_ONLY,
    QUOTATION_CEILING_CHARS,
    QUOTATION_CHARS_METADATA_KEY,
    QUOTATION_TIER_METADATA_KEY,
    SNIPPET_PARITY,
    apply_quotation_policy,
    resolve_quotation_policy,
)

# The body no path may return. Distinctive enough that a substring scan over a
# whole serialized result is meaningful, and long enough to exceed every
# quotation cap so a "capped quote" can never accidentally equal the body.
SECRET_BODY = "PUBLISHER-CONFIDENTIAL-INTERIOR " + ("the licensed interior text. " * 80)
RESEARCH_DOC = "doc-research-only"


class StubEmbedding:
    """Deterministic length-4 embedding (no sentence-transformers)."""

    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [
            float(h % 7) / 7.0,
            float((h >> 3) % 11) / 11.0,
            float((h >> 5) % 13) / 13.0,
            float((h >> 7) % 17) / 17.0,
        ]


@pytest.fixture
def db_path(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-research-only-")
    path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    con = connect_write(path, purpose="research-only-setup")
    init_database(con)
    con.close()
    return path


def _seed(path: str, document_id: str, content_class: str | None, *, metadata=None) -> None:
    con = connect_write(path, purpose="seed")
    try:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title=f"Title {document_id}",
            author="A. Publisher",
            raw_text=SECRET_BODY,
            metadata=metadata,
            content_class=content_class,
        )
    finally:
        con.close()


def _seed_chunk(path: str, document_id: str, content_class: str | None, text: str) -> None:
    con = connect_write(path, purpose="seed-chunk")
    try:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title=f"Title {document_id}",
            raw_text=SECRET_BODY,
            content_class=content_class,
        )
        insert_chunk(
            con,
            document_id=document_id,
            chunk_index=0,
            text=text,
            token_count=10,
            embedding=StubEmbedding().encode(text),
        )
    finally:
        con.close()


def _assert_body_absent(obj: object, where: str) -> None:
    """The body must not appear ANYWHERE in a serialized result.

    Checking one named field only proves that field is clean. Serializing the
    whole object and scanning it catches a leak through a field this test does
    not know about — including one a future change adds.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        blob = json.dumps(dataclasses.asdict(obj), default=str)
    else:
        blob = json.dumps(obj, default=str)
    assert SECRET_BODY not in blob, f"research_only body leaked through {where}"
    # A cut of the body is still the body. Catch a partial that exceeds every
    # quotation ceiling the policy layer can ever grant.
    over_ceiling = SECRET_BODY[: QUOTATION_CEILING_CHARS + 1]
    assert over_ceiling not in blob, (
        f"{where} returned more of the research_only body than the quotation "
        f"ceiling ({QUOTATION_CEILING_CHARS} chars) permits"
    )


# ---------------------------------------------------------------------------
# Where this state sits among the ones that already exist
# ---------------------------------------------------------------------------


def test_research_only_is_servable_to_nobody():
    """Not publicly servable, and — unlike personal_reading — not owner-readable.

    The second half is the whole distinction between the two states. If a future
    edit folds research_only into the personal lane to save a branch, this is the
    assertion that says no.
    """
    assert RESEARCH_ONLY_CONTENT_CLASS not in SERVABLE_CONTENT_CLASSES
    assert RESEARCH_ONLY_CONTENT_CLASS not in PERSONAL_READABLE_CONTENT_CLASSES
    assert RESEARCH_ONLY_CONTENT_CLASS not in PERSONAL_ONLY_CONTENT_CLASSES, (
        "PERSONAL_ONLY_CONTENT_CLASSES is granted to a matching owner_user_id on "
        "the privileged retrieval branch; research_only must never take that grant"
    )


def test_research_only_is_distinct_from_the_gated_and_personal_states():
    assert RESEARCH_ONLY_CONTENT_CLASSES.isdisjoint(RESTRICTED_CONTENT_CLASSES)
    assert RESEARCH_ONLY_CONTENT_CLASSES.isdisjoint(PERSONAL_ONLY_CONTENT_CLASSES)
    assert RESEARCH_ONLY_CONTENT_CLASSES <= _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES


def test_withheld_classes_stay_disjoint_from_the_servable_allowlist():
    """The chunk gate is a denylist and book serve is an allowlist; a class in
    both would be withheld from search and served in full, the worst polarity
    error available. Extends tests/test_retrieval_gate_polarity to the new class."""
    assert frozenset() == _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES & SERVABLE_CONTENT_CLASSES


def test_research_only_never_trains_indexes_or_earns():
    assert RESEARCH_ONLY_CONTENT_CLASS in NON_TRAINABLE_CONTENT_CLASSES
    assert RESEARCH_ONLY_CONTENT_CLASS not in TURBOPUFFER_INDEX_CONTENT_CLASSES
    assert RESEARCH_ONLY_CONTENT_CLASS in NON_ATTRIBUTABLE_CONTENT_CLASSES
    assert RESEARCH_ONLY_CONTENT_CLASS not in PUBLIC_GRAPH_CONTENT_CLASSES


def test_servability_projects_to_its_own_non_servable_status():
    status = servability_of(RESEARCH_ONLY_CONTENT_CLASS)
    assert status is ServabilityStatus.RESEARCH_DERIVABLE_ONLY
    assert not is_servable_full_text(status)
    assert status is not ServabilityStatus.GATED_METADATA_ONLY, (
        "a gated book yields the default snippet and may still be opted in; a "
        "research_only work does neither — flattening them would hand this state "
        "the gated snippet it must negotiate for"
    )


def test_takedown_still_wins_over_research_only():
    assert (
        servability_of(RESEARCH_ONLY_CONTENT_CLASS, taken_down=True)
        is ServabilityStatus.TAKEN_DOWN
    )


# ---------------------------------------------------------------------------
# INVARIANT 1 — no serve path returns a research_only body
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("owner", [False, True])
def test_serve_full_text_withholds_body_on_both_paths(db_path, owner):
    """The binding gate. ``owner=True`` is the assertion that matters: it is the
    switch that releases a personal_reading body, and it must not release this one."""
    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)
    con = connect_write(db_path, purpose="serve")
    try:
        result = serve_full_text(con, RESEARCH_DOC, owner=owner)
    finally:
        con.close()
    assert result.found is True
    assert result.servable is False
    assert result.full_text is None
    assert result.reason.startswith("research_only_derivable")
    _assert_body_absent(result, f"serve_full_text(owner={owner})")


@pytest.mark.parametrize("owner", [False, True])
def test_serve_full_text_guarded_withholds_body_on_both_paths(db_path, owner):
    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)
    con = connect_write(db_path, purpose="serve-guarded")
    try:
        result = serve_full_text_guarded(con, RESEARCH_DOC, owner=owner)
    finally:
        con.close()
    assert result.full_text is None
    assert result.servable is False
    _assert_body_absent(result, f"serve_full_text_guarded(owner={owner})")


def test_owner_read_of_personal_reading_still_works(db_path):
    """A control, and the reason this file is not just asserting False everywhere.

    The owner full-read privilege is real and must survive: if this went green
    only because the owner path stopped serving anything, the tests above would
    be vacuous. personal_reading still opens in full for the owner.
    """
    _seed(db_path, "doc-personal", "personal_reading")
    con = connect_write(db_path, purpose="serve-control")
    try:
        owner_view = serve_full_text(con, "doc-personal", owner=True)
        public_view = serve_full_text(con, "doc-personal", owner=False)
    finally:
        con.close()
    assert owner_view.full_text == SECRET_BODY
    assert public_view.full_text is None


def test_pre_insert_guard_refuses_a_research_only_body():
    """``guard_candidate_full_text`` derives the twin envelope's body before the
    row exists. It is called with ``owner=True`` from ``insert_document``, so it
    is a genuine owner-path body decision made outside the serve gate."""
    body = guard_candidate_full_text(
        SECRET_BODY, RESEARCH_ONLY_CONTENT_CLASS, None, owner=True
    )
    assert body is None


def test_stored_row_guard_refuses_a_research_only_body(db_path):
    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)
    con = connect_write(db_path, purpose="guard-stored")
    try:
        body = guard_document_candidate_full_text(
            con, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS, owner=True
        )
    finally:
        con.close()
    assert body is None


def test_twin_source_envelope_carries_no_research_only_body(db_path):
    """``insert_document`` stamps a twin envelope derived from the body on the
    owner path. A body refused by the serve gate but copied into the envelope
    column would leak through the twin projection instead."""
    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)
    con = connect_write(db_path, purpose="read-envelope")
    try:
        row = con.execute(
            "SELECT twin_source_envelope FROM documents WHERE document_id = ?",
            [RESEARCH_DOC],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    _assert_body_absent(row[0], "documents.twin_source_envelope")


def test_reader_html_sidecar_withholds_a_research_only_body(db_path):
    """The sidecar is a SECOND body store. It delegates its rights decision to
    the serve guard, so a research_only document must get no HTML body from it
    even when a snapshot row exists."""
    from substrate.reader_html.store import serve_reader_html, store_reader_html

    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)
    con = connect_write(db_path, purpose="sidecar")
    try:
        store_reader_html(
            con,
            document_id=RESEARCH_DOC,
            main_html=f"<p>{SECRET_BODY}</p>",
            source_kind="publisher_epub",
        )
        public_view = serve_reader_html(con, RESEARCH_DOC)
        owner_view = serve_reader_html(con, RESEARCH_DOC, owner=True)
    finally:
        con.close()
    for label, view in (("public", public_view), ("owner", owner_view)):
        assert view.available is False, f"{label} reader-HTML released a research_only body"
        assert view.reason == "rights_denied"
        _assert_body_absent(view, f"serve_reader_html({label})")


def test_research_seed_from_a_passage_carries_no_body(db_path):
    """The reader can select a passage and send it to research. For a withheld
    work the caller's selection is DROPPED — otherwise the body would travel out
    through a field the caller supplied rather than one the gate returned."""
    from substrate.books.passage_research import build_research_seed

    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)
    con = connect_write(db_path, purpose="passage")
    try:
        seed = build_research_seed(
            con, document_id=RESEARCH_DOC, page_index=3, passage_text=SECRET_BODY
        )
    finally:
        con.close()
    assert seed.gated is True
    _assert_body_absent(seed, "build_research_seed(passage_text=<body>)")


def test_curated_reading_list_omits_research_only(db_path):
    """The library's curation query keys on the servable allowlist in SQL."""
    from substrate.books.curate import curate_reading_list

    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)
    _seed(db_path, "doc-pd", "public_domain")
    con = connect_write(db_path, purpose="curate")
    try:
        curated = curate_reading_list(con, "publisher", model=StubEmbedding(), limit=10)
    finally:
        con.close()
    assert RESEARCH_DOC not in {c.document_id for c in curated}


def test_chunk_http_path_withholds_a_research_only_body():
    """The HTTP chunk surface serves users, and no user receives this body — so
    unlike ``personal_readable`` this verdict has no owner branch that releases it."""
    assert is_chunk_body_withheld(RESEARCH_ONLY_CONTENT_CLASS) == (True, "research_only")
    assert is_chunk_body_withheld(RESEARCH_ONLY_CONTENT_CLASS, taken_down=True) == (
        True,
        "taken_down",
    )


def test_search_excludes_research_only_on_the_public_path(db_path):
    _seed_chunk(db_path, "doc-pd", "public_domain", "quantum optics public domain review")
    _seed_chunk(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS, "quantum optics licensed interior")
    con = connect_write(db_path, purpose="search-public")
    try:
        res = search(con, "quantum", model=StubEmbedding(), top_k=10)
    finally:
        con.close()
    doc_ids = {r["document_id"] for r in res["results"]}
    assert "doc-pd" in doc_ids
    assert RESEARCH_DOC not in doc_ids, "research_only leaked onto the public search gate"


def test_search_reaches_research_only_on_the_private_research_path(db_path):
    """The agent's path. "Ingested, chunked, embedded and cited by an agent" IS
    the privileged retrieval tag in this codebase, so this must succeed — a state
    nothing can retrieve derives nothing, and the product is gone."""
    _seed_chunk(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS, "quantum optics licensed interior")
    con = connect_write(db_path, purpose="search-private")
    try:
        res = search(
            con, "quantum", model=StubEmbedding(), top_k=10, policy_tag="private_research"
        )
    finally:
        con.close()
    assert RESEARCH_DOC in {r["document_id"] for r in res["results"]}


def test_rights_audit_reports_no_leak_for_research_only(db_path):
    """The standing §9.0 audit cross-checks the stored class against what the
    serve path actually returns. A research_only row must not read as a leak."""
    from substrate.rights_audit import audit_batch

    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)
    con = connect_write(db_path, purpose="audit")
    try:
        result = audit_batch(con, [RESEARCH_DOC])
    finally:
        con.close()
    assert result.violations == []
    assert result.passed is True


def test_no_serve_result_field_ever_carries_the_body(db_path):
    """A sweep over every ServeResult field, so a leak through a field added
    later fails here rather than in production."""
    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)
    con = connect_write(db_path, purpose="sweep")
    try:
        for owner in (False, True):
            result = serve_full_text_guarded(con, RESEARCH_DOC, owner=owner)
            for field in dataclasses.fields(result):
                value = getattr(result, field.name)
                if isinstance(value, str):
                    assert SECRET_BODY not in value, (
                        f"ServeResult.{field.name} carried the research_only body "
                        f"on the owner={owner} path"
                    )
    finally:
        con.close()


# ---------------------------------------------------------------------------
# INVARIANT 2 — a derived claim renders provenance without leaking the body
# ---------------------------------------------------------------------------


def test_a_research_only_chunk_stays_citable():
    """Deliberately citable, and asserted from the policy module that owns the
    decision. A derived claim that cannot name its source is not research."""
    from tools.codegen.chunk_provenance import (
        NON_CITABLE_CONTENT_CLASSES,
        is_chunk_citable,
        is_document_citable,
        provenance_policy_errors,
    )

    assert RESEARCH_ONLY_CONTENT_CLASS not in NON_CITABLE_CONTENT_CLASSES
    assert is_chunk_citable(RESEARCH_ONLY_CONTENT_CLASS)
    assert is_document_citable(RESEARCH_ONLY_CONTENT_CLASS)
    assert provenance_policy_errors() == []


def test_synthesis_export_cites_the_source_without_embedding_the_passage():
    """The synthesis adapter builds the doc-model, so the leak surface is the
    serialized model itself — an island carries whatever the model carries."""
    from services.html_projection.adapters.synthesis import (
        Claim,
        SourceRef,
        SynthesisExport,
        adapt_synthesis,
    )

    source = SourceRef(
        document_id="doc-research-only",
        document_title="The Licensed Monograph",
        content_class=RESEARCH_ONLY_CONTENT_CLASS,
        ip_holder_id="holder-42",
        locator="ch. 4",
        chunk_text=SECRET_BODY,
    )
    export = SynthesisExport(
        synthesis_id="syn-1",
        target_question="What does the monograph conclude?",
        claims=[Claim(statement="The monograph concludes X.", sources=[source])],
    )
    assert source.servable is False
    doc_model = adapt_synthesis(export)
    blob = json.dumps(doc_model, default=str)

    assert SECRET_BODY not in blob, "the research_only passage reached the doc-model"
    assert "The monograph concludes X." in blob, "the derived claim was dropped"
    assert "The Licensed Monograph" in blob, "the citation lost its source identity"
    assert "holder-42" in blob, "the citation lost its rights holder"
    assert "ch. 4" in blob, "the citation lost its locator"


def test_notebook_resolver_returns_cite_only_for_a_research_only_ref():
    """A notebook resolves chunk text live at render time, so the gate is the
    resolver: identity passes, the payload does not."""
    from services.html_projection.adapters.notebook import (
        ResolvedRefData,
        RightsAwareResolver,
    )

    ref = ResolvedRefData(
        kind="chunk",
        content_class=RESEARCH_ONLY_CONTENT_CLASS,
        ip_holder_id="holder-42",
        title="The Licensed Monograph",
        payload={"text": SECRET_BODY, "passage": SECRET_BODY},
    )
    assert ref.servable is False
    resolved = RightsAwareResolver({"ref-1": ref})("ref-1", "chunk")
    blob = json.dumps(dataclasses.asdict(resolved), default=str)

    assert SECRET_BODY not in blob, "the research_only passage reached the renderer"
    assert "The Licensed Monograph" in blob
    assert "holder-42" in blob


def test_deliverable_block_quoting_a_research_only_source_is_cite_only():
    from services.html_projection.adapters.deliverable import (
        DeliverableBlock,
        DeliverableExport,
        DeliverableSection,
        adapt_deliverable,
    )

    block = DeliverableBlock(
        block_kind="claim",
        text=SECRET_BODY,
        content_class=RESEARCH_ONLY_CONTENT_CLASS,
        ip_holder_id="holder-42",
        source_title="The Licensed Monograph",
        source_document_id="doc-research-only",
    )
    assert block.servable is False
    doc_model = adapt_deliverable(
        DeliverableExport(title="Findings", sections=[DeliverableSection("One", [block])])
    )
    blob = json.dumps(doc_model, default=str)

    assert SECRET_BODY not in blob
    assert "The Licensed Monograph" in blob
    # The knowledge-graph edge still records the citation, flagged non-servable.
    edges = doc_model["edges"]
    assert any(e["to_document_id"] == "doc-research-only" for e in edges)
    assert all(e["tone"] == "warning" for e in edges)


# ---------------------------------------------------------------------------
# The quotation policy — the per-tier knob, and the ceiling it cannot pass
# ---------------------------------------------------------------------------


def test_quotation_denies_by_default():
    """A source whose terms were never recorded quotes nothing."""
    assert resolve_quotation_policy(None) == DEFAULT_QUOTATION_POLICY
    assert DEFAULT_QUOTATION_POLICY.max_quote_chars == 0
    assert DEFAULT_QUOTATION_POLICY.quotation_permitted is False
    assert apply_quotation_policy(SECRET_BODY, DEFAULT_QUOTATION_POLICY) is None


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {QUOTATION_TIER_METADATA_KEY: "a_tier_no_build_knows"},
        {QUOTATION_TIER_METADATA_KEY: 7},
        "not json at all",
        b"\x00\x01",
        [1, 2, 3],
        {QUOTATION_CHARS_METADATA_KEY: "200"},
        {QUOTATION_CHARS_METADATA_KEY: -50},
        {QUOTATION_CHARS_METADATA_KEY: True},
    ],
)
def test_an_unrecorded_or_malformed_term_quotes_nothing(metadata):
    """Deny-by-default across every shape a metadata blob arrives in. The bool
    case is the subtle one: ``isinstance(True, int)`` holds in Python, so a
    stray ``true`` in JSON would otherwise buy a one-character quotation."""
    assert resolve_quotation_policy(metadata).max_quote_chars == 0


def test_a_named_tier_sets_the_cap():
    policy = resolve_quotation_policy({QUOTATION_TIER_METADATA_KEY: BRIEF_QUOTATION})
    assert policy.tier == BRIEF_QUOTATION
    assert policy.max_quote_chars == 200
    quote = apply_quotation_policy(SECRET_BODY, policy)
    assert quote is not None
    assert len(quote) <= 201  # the cap, plus the ellipsis marking the cut
    assert quote != SECRET_BODY


def test_a_bespoke_term_overrides_the_tier():
    policy = resolve_quotation_policy(
        {QUOTATION_TIER_METADATA_KEY: SNIPPET_PARITY, QUOTATION_CHARS_METADATA_KEY: 25}
    )
    assert policy.max_quote_chars == 25, (
        "a negotiated per-work term is the one that was actually agreed; it must "
        "win over the shape the deal started from"
    )


def test_no_policy_can_raise_the_quotation_ceiling():
    """The knob only ever tightens. This is what keeps invariant 1 true in the
    presence of a knob at all: whatever a metadata blob claims, the cut can never
    grow into the body."""
    assert QUOTATION_CEILING_CHARS == SERVE_SNIPPET_MAX_CHARS
    policy = resolve_quotation_policy({QUOTATION_CHARS_METADATA_KEY: 10_000_000})
    assert policy.max_quote_chars == QUOTATION_CEILING_CHARS
    quote = apply_quotation_policy(SECRET_BODY, policy)
    assert quote is not None
    assert len(quote) <= QUOTATION_CEILING_CHARS + 1
    assert quote != SECRET_BODY


def test_the_most_permissive_tier_is_only_snippet_parity():
    """The widest research_only deal is exactly as wide as the bounded excerpt
    the platform already serves for a gated book, never wider."""
    widest = max(resolve_quotation_policy({QUOTATION_TIER_METADATA_KEY: t}).max_quote_chars
                 for t in (DERIVED_ONLY, BRIEF_QUOTATION, SNIPPET_PARITY))
    assert widest == SERVE_SNIPPET_MAX_CHARS


def test_the_serve_gate_honours_the_negotiated_tier(db_path):
    """End to end: the tier recorded on the document decides what the serve path
    may return alongside the refusal, and the body is still withheld."""
    _seed(
        db_path,
        RESEARCH_DOC,
        RESEARCH_ONLY_CONTENT_CLASS,
        metadata={QUOTATION_TIER_METADATA_KEY: BRIEF_QUOTATION},
    )
    con = connect_write(db_path, purpose="serve-tiered")
    try:
        result = serve_full_text(con, RESEARCH_DOC, owner=True)
    finally:
        con.close()
    assert result.full_text is None
    assert result.reason == f"research_only_derivable:{BRIEF_QUOTATION}"
    assert result.snippet is not None
    assert len(result.snippet) <= 201
    _assert_body_absent(result, "serve_full_text with a brief_quotation tier")


def test_the_default_tier_returns_no_snippet_at_all(db_path):
    """A gated book yields a 500-character snippet by default. This state yields
    nothing by default — that difference is why it is not the gated class."""
    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)
    _seed(db_path, "doc-gated", "restricted_pending_opt_in")
    con = connect_write(db_path, purpose="serve-default")
    try:
        research = serve_full_text(con, RESEARCH_DOC)
        gated = serve_full_text(con, "doc-gated")
    finally:
        con.close()
    assert research.snippet is None
    assert gated.snippet is not None, (
        "control: the gated class still yields its bounded snippet, so the "
        "assertion above is about research_only and not a broken fixture"
    )


# ---------------------------------------------------------------------------
# The standing corpus check — enforcement that survives past CI
# ---------------------------------------------------------------------------


def _run_research_only_check(path: str):
    from runtime.db_lock import connect_read
    from substrate.corpus_audit import _check_research_only_withheld

    con = connect_read(path)
    try:
        return _check_research_only_withheld(con)
    finally:
        con.close()


def test_standing_audit_passes_on_a_correctly_withheld_row(db_path):
    from substrate.corpus_audit import ALL_CHECK_NAMES, CHECK_RESEARCH_ONLY_WITHHELD

    assert CHECK_RESEARCH_ONLY_WITHHELD in ALL_CHECK_NAMES
    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)
    result = _run_research_only_check(db_path)
    assert result.ok is True
    assert result.count == 0


def test_standing_audit_bites_on_a_planted_leak(db_path):
    """Falsifiability: the check must go red on a row that actually leaks, or it
    is decoration. The leak is planted the way a real regression would arrive —
    a research_only work relabelled servable, so the serve path hands back the
    body while the corpus still calls it derivable-only.
    """
    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)
    con = connect_write(db_path, purpose="plant-leak")
    try:
        # Straight to the column: we are simulating drift, not exercising the
        # registrar, which would refuse this transition through its own guard.
        con.execute(
            "UPDATE documents SET content_class = 'public_domain' WHERE document_id = ?",
            [RESEARCH_DOC],
        )
    finally:
        con.close()
    # The row no longer reads as research_only, so the check cannot see it —
    # which is the honest limit of a class-keyed scan and why it is stated here.
    assert _run_research_only_check(db_path).ok is True

    # The regression the check DOES catch: the class is intact and the serve path
    # released the body anyway.
    con = connect_write(db_path, purpose="restore-class")
    try:
        con.execute(
            "UPDATE documents SET content_class = ? WHERE document_id = ?",
            [RESEARCH_ONLY_CONTENT_CLASS, RESEARCH_DOC],
        )
    finally:
        con.close()

    import substrate.corpus_audit as corpus_audit

    real_serve = corpus_audit.serve_full_text

    def leaky_serve(con, document_id, *, owner=False):
        result = real_serve(con, document_id, owner=owner)
        return dataclasses.replace(result, full_text=SECRET_BODY) if owner else result

    corpus_audit.serve_full_text = leaky_serve
    try:
        leaked = _run_research_only_check(db_path)
    finally:
        corpus_audit.serve_full_text = real_serve

    assert leaked.ok is False, "the standing check did not bite on an owner-path leak"
    assert leaked.count == 1
    assert "owner" in leaked.offending[0]


def test_standing_audit_bites_when_a_quote_exceeds_its_cap(db_path):
    """The cross-check arm: the class is right and no full body is served, but the
    bytes alongside the refusal exceed what this row's tier permits."""
    import substrate.corpus_audit as corpus_audit

    _seed(db_path, RESEARCH_DOC, RESEARCH_ONLY_CONTENT_CLASS)  # derived_only => cap 0
    real_serve = corpus_audit.serve_full_text

    def over_quoting_serve(con, document_id, *, owner=False):
        result = real_serve(con, document_id, owner=owner)
        return dataclasses.replace(result, snippet=SECRET_BODY[:300])

    corpus_audit.serve_full_text = over_quoting_serve
    try:
        result = _run_research_only_check(db_path)
    finally:
        corpus_audit.serve_full_text = real_serve

    assert result.ok is False
    assert "quotation cap" in result.offending[0]
