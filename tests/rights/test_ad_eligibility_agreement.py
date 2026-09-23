"""Every persisted source kind obeys the ONE serve/payout ad-eligibility rule."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from runtime.db_lock import connect_write
from substrate.books.model import upsert_book_asset
from substrate.books.serve_guard import serve_full_text_guarded
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database
from substrate.payouts.ledger import accrue_paper_read, payout_ad_eligibility
from substrate.rights import RightsTier
from substrate.rights.ad_eligibility import ad_eligibility
from substrate.rights.register import SourceKind, register_source_document

_BODY = "A body long enough to serve. " * 20
_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_CC_BY_NC = "http://creativecommons.org/licenses/by-nc/4.0/"


@dataclass(frozen=True)
class Shape:
    name: str
    content_class: str | None
    metadata: dict[str, object] | None
    holder: str | None
    expected: bool


SHAPES: dict[SourceKind, list[Shape]] = {
    SourceKind.LICENSED_PUBLISHER: [
        Shape("opt_in_book", "opt_in_licensed", None, "Acme Press", True),
        Shape("gated_pre_onboarded_book", None, None, "Acme Press", False),
        Shape("public_domain_book", "public_domain", None, None, True),
        Shape(
            "arxiv_book_without_license_uri",
            "source_declared_open",
            {"arxiv_id": "2401.00001"},
            None,
            False,
        ),
        Shape(
            "arxiv_book_with_cc_by",
            "source_declared_open",
            {"arxiv_id": "2401.00002", "license_uri": _CC_BY},
            None,
            True,
        ),
    ],
    SourceKind.ACADEMIC_PREPRINT: [
        Shape(
            "arxiv_t1_servable",
            "source_declared_open",
            {"arxiv_id": "2401.00003", "license_uri": _CC_BY},
            None,
            True,
        ),
        Shape(
            "arxiv_t1_gated",
            None,
            {"arxiv_id": "2401.00004", "license_uri": _CC_BY},
            None,
            True,
        ),
        Shape(
            "arxiv_t2_gated",
            None,
            {"arxiv_id": "2401.00005", "license_uri": _CC_BY_NC},
            None,
            False,
        ),
        Shape(
            "arxiv_no_license_gated",
            None,
            {"arxiv_id": "2401.00006"},
            None,
            False,
        ),
    ],
    SourceKind.USER_CONTENT: [
        Shape("capture_default_gated", None, None, None, False),
        Shape("operator_authored", "user_owned", None, None, True),
        Shape("personal_reading", "personal_reading", None, None, False),
    ],
    SourceKind.WEB: [
        Shape("url_personal_reading", "personal_reading", None, None, False),
        Shape("web_default_gated", None, None, None, False),
        Shape("declared_open_page", "source_declared_open", None, None, True),
    ],
}


@pytest.fixture
def con(tmp_path, monkeypatch):
    path = str(tmp_path / "ad-eligibility.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    connection = connect_write(path, purpose="ad-eligibility-agreement-test")
    init_database(connection)
    yield connection
    connection.close()


def _doc_id(kind: SourceKind, shape: Shape) -> str:
    return f"{kind.value}-{shape.name}"


def _make(
    con, kind: SourceKind, shape: Shape, *, document_id: str | None = None
) -> str:
    doc_id = document_id or _doc_id(kind, shape)
    insert_document(
        con,
        document_id=doc_id,
        source_tier=3,
        document_type=(
            "academic_paper"
            if shape.metadata and "arxiv_id" in shape.metadata
            else "book"
        ),
        title="T",
        author="A",
        raw_text=_BODY,
        metadata=shape.metadata,
    )
    register_source_document(
        con,
        document_id=doc_id,
        source_kind=kind,
        content_class=shape.content_class,
        rights_holder_name=shape.holder,
    )
    return doc_id


def test_every_source_kind_has_a_shape():
    assert set(SHAPES) == set(SourceKind)


@pytest.mark.parametrize("kind", list(SourceKind), ids=lambda kind: kind.value)
def test_serve_time_ad_eligible_equals_payout_time_accruability(con, kind):
    """Serve-time eligibility equals the payout predicate for every shape.
    For an arXiv shape that is what the ledger accrues on (next tests); for
    the others the ledger never reaches the predicate, so this pins only what
    it would decide (test_the_ledger_turns_every_non_arxiv_document_away)."""
    for shape in SHAPES[kind]:
        doc_id = _make(con, kind, shape)
        serve = serve_full_text_guarded(con, doc_id).ad_eligible
        decision = payout_ad_eligibility(con, doc_id)
        assert decision is not None
        assert serve == decision.eligible, (
            f"{kind.value}/{shape.name}: serve={serve} "
            f"payout={decision.eligible} ({decision.reason})"
        )
        assert serve is shape.expected, f"{kind.value}/{shape.name}"


def test_a_taken_down_opt_in_book_is_eligible_nowhere(con):
    opt_in = SHAPES[SourceKind.LICENSED_PUBLISHER][0]
    doc_id = _make(
        con,
        SourceKind.LICENSED_PUBLISHER,
        opt_in,
        document_id="taken-down-book",
    )
    upsert_book_asset(con, document_id=doc_id)
    con.execute(
        "UPDATE book_assets SET taken_down = TRUE WHERE document_id = ?",
        [doc_id],
    )
    serve = serve_full_text_guarded(con, doc_id).ad_eligible
    decision = payout_ad_eligibility(con, doc_id)
    assert decision is not None
    assert serve is False
    assert decision.eligible is False


def test_the_ledger_accrues_exactly_when_payout_eligible(con):
    """The ledger's gate IS payout_ad_eligibility for every document it
    treats as an arXiv paper, including the ones register_book tagged
    LICENSED_PUBLISHER."""
    arxiv_shapes = [
        (kind, shape)
        for kind in (SourceKind.ACADEMIC_PREPRINT, SourceKind.LICENSED_PUBLISHER)
        for shape in SHAPES[kind]
        if shape.metadata and "arxiv_id" in shape.metadata
    ]
    assert len(arxiv_shapes) == 6
    for kind, shape in arxiv_shapes:
        doc_id = _make(con, kind, shape)
        result = accrue_paper_read(
            con,
            document_id=doc_id,
            revenue_cents=100,
            ad_event_id=f"evt-{doc_id}",
        )
        decision = payout_ad_eligibility(con, doc_id)
        assert decision is not None
        assert result.accruable is decision.eligible, f"{kind.value}/{shape.name}"
        assert result.accruable is shape.expected, f"{kind.value}/{shape.name}"


def test_the_ledger_turns_every_non_arxiv_document_away(con):
    """The agreement stops at arXiv: the ledger refuses a non-arXiv document
    before the predicate, ad-eligible or not. If this starts failing, the
    ledger has begun accruing non-arXiv revenue and the agreement claims in
    ad_eligibility.ad_eligibility need re-checking."""
    non_arxiv_shapes = [
        (kind, shape)
        for kind in SourceKind
        for shape in SHAPES[kind]
        if not (shape.metadata and "arxiv_id" in shape.metadata)
    ]
    assert any(shape.expected for _kind, shape in non_arxiv_shapes)
    for kind, shape in non_arxiv_shapes:
        doc_id = _make(con, kind, shape)
        result = accrue_paper_read(
            con,
            document_id=doc_id,
            revenue_cents=100,
            ad_event_id=f"evt-{doc_id}",
        )
        assert result.accruable is False, f"{kind.value}/{shape.name}"
        assert result.reason == "not_an_arxiv_paper", f"{kind.value}/{shape.name}"


def test_ad_eligibility_requires_servable_without_a_tier():
    with pytest.raises(ValueError):
        ad_eligibility(None, servable=None)
    assert ad_eligibility(RightsTier.T1_REDISTRIBUTABLE, servable=None).eligible
