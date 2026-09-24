"""Every persisted source kind obeys the ONE serve/payout ad-eligibility rule."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from interfaces.research.api.ad_routes import resolve_window_value_cents
from runtime.db_lock import connect_write
from substrate import ip_holders
from substrate.ad_inventory.advertiser_onboarding import (
    AdvertiserRegistry,
    activate_advertiser,
    approve_advertiser,
    save_record,
    submit_application,
)
from substrate.ad_inventory.fill_decisions import decide_fills
from substrate.ad_inventory.fill_settlement import settle_fill_decision
from substrate.ad_inventory.reader_impressions import record_raw_impression
from substrate.books.model import upsert_book_asset
from substrate.books.serve_guard import serve_full_text_guarded
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database
from substrate.marketplace_metrics.book_escrow import accrue_reading_session
from substrate.payouts.ledger import (
    accrue_paper_read,
    ensure_tables,
    payout_ad_eligibility,
)
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
            "Acme Press",
            False,
        ),
        Shape(
            "arxiv_book_with_cc_by",
            "source_declared_open",
            {"arxiv_id": "2401.00002", "license_uri": _CC_BY},
            "Acme Press",
            True,
        ),
    ],
    SourceKind.ACADEMIC_PREPRINT: [
        Shape(
            "arxiv_t1_servable",
            "source_declared_open",
            {"arxiv_id": "2401.00003", "license_uri": _CC_BY},
            "Preprint Holder",
            True,
        ),
        Shape(
            "arxiv_t1_gated",
            None,
            {"arxiv_id": "2401.00004", "license_uri": _CC_BY},
            "Preprint Holder",
            True,
        ),
        Shape(
            "arxiv_t2_gated",
            None,
            {"arxiv_id": "2401.00005", "license_uri": _CC_BY_NC},
            "Preprint Holder",
            False,
        ),
        Shape(
            "arxiv_no_license_gated",
            None,
            {"arxiv_id": "2401.00006"},
            "Preprint Holder",
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
        Shape("web_default_gated", None, None, "Example Web", False),
        Shape("declared_open_page", "source_declared_open", None, "Example Web", True),
    ],
}


@pytest.fixture
def con(tmp_path, monkeypatch):
    path = str(tmp_path / "ad-eligibility.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
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
def test_serve_time_ad_eligible_equals_the_payout_predicate(con, kind):
    """Serve-time eligibility equals the payout predicate for every shape.
    This pins the predicate only; what the money actually does is
    test_a_settled_fill_accrues_exactly_when_serve_time_says_ad_eligible."""
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


_SETTLED_CENTS = 1000


def _active_advertiser(con) -> str:
    """PENDING -> APPROVED -> ACTIVE, the paid-fill gate settle_fill_decision
    checks."""
    registry = AdvertiserRegistry()
    pending = submit_application(
        registry,
        display_name="Acme Ads",
        contact_email="ads@example.com",
        verticals=("research",),
        audience_intents=("academic",),
        advertiser_id="adv:agreement",
    )
    approve_advertiser(registry, advertiser_id=pending.advertiser_id)
    activate_advertiser(
        registry, advertiser_id=pending.advertiser_id, legal_gate_passed=True
    )
    for record in registry.records:
        save_record(con, record)
    return pending.advertiser_id


def _settled_fill_cents(con, doc_id: str, advertiser_id: str) -> int:
    """Persist a paid fill for ``doc_id``'s reader window, settle it through
    the Rank 0.1 gate, and mint its value the way the server does
    (resolve_window_value_cents reads the settled row, never the client)."""
    window_id = f"win:{doc_id}"
    decision = decide_fills(
        con,
        owner_user_id="__operator__",
        window_id=window_id,
        document_id=doc_id,
        page_index=0,
        lens="read",
        positions=("top",),
        select_fills=lambda: [
            {
                "position": "top",
                "kind": "ad",
                "revenue_usd_cents": 0,
                "ad": {
                    "inventory_id": "inv:agreement",
                    "advertiser_display_name": "Acme Ads",
                    "creative_url": "/mark-32.png",
                    "landing_url": "https://example.com/",
                },
                "house": None,
            }
        ],
    )
    settle_fill_decision(
        con,
        decision_id=decision.decision_id,
        revenue_usd_cents=_SETTLED_CENTS,
        legal_gate_passed=True,
        pricing_authority_ref="budget:agreement-test",
        advertiser_id=advertiser_id,
    )
    return resolve_window_value_cents(
        owner_user_id="__operator__", window_id=window_id, con=con
    )


def _holder_of(con, doc_id: str) -> str | None:
    row = con.execute(
        "SELECT ip_holder_id FROM documents WHERE document_id = ?", [doc_id]
    ).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def _escrow_cents(con, holder_id: str | None) -> int:
    if holder_id is None:
        return 0
    holder = ip_holders.get(con, holder_id)
    assert holder is not None
    return int(holder.escrow_balance_usd * 100)


def _author_ledger_cents(con, doc_id: str) -> int:
    ensure_tables(con)
    row = con.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM paper_author_accruals "
        "WHERE document_id = ?",
        [doc_id],
    ).fetchone()
    return int(row[0])


@pytest.mark.parametrize("kind", list(SourceKind), ids=lambda kind: kind.value)
def test_a_settled_fill_accrues_exactly_when_serve_time_says_ad_eligible(con, kind):
    """SPR-10 task 6, measured on the money rather than on the predicate: a
    paid fill on the document's reader window is settled through the Rank 0.1
    gate, its value is minted from the settled row, and the reader-session
    settlement (book_escrow.accrue_reading_session: the holder's escrow plus,
    for an arXiv paper, the per-author ledger) either takes it or refuses it.
    It must take it exactly when the serve guard mounted an ad border."""
    advertiser_id = _active_advertiser(con)
    observed = []
    for shape in SHAPES[kind]:
        doc_id = _make(con, kind, shape)
        serve = serve_full_text_guarded(con, doc_id).ad_eligible
        cents = _settled_fill_cents(con, doc_id, advertiser_id)
        assert cents == _SETTLED_CENTS, f"{kind.value}/{shape.name}"
        holder_id = _holder_of(con, doc_id)
        before = _escrow_cents(con, holder_id)
        result = accrue_reading_session(
            con,
            document_id=doc_id,
            session_id=f"sess-{doc_id}",
            impressions=[
                record_raw_impression(
                    session_id=f"sess-{doc_id}",
                    document_id=doc_id,
                    slot_id=f"slot:{doc_id}:p0:top",
                    page_index=0,
                    fill_kind="ad",
                    revenue_usd_cents=cents,
                    focused_dwell_ms=5000,
                )
            ],
        )
        escrow_moved = _escrow_cents(con, holder_id) - before
        observed.append(
            (shape, serve, holder_id, escrow_moved, _author_ledger_cents(con, doc_id), result)
        )

    # What the ledgers now hold, read back, before what the settlement says.
    for shape, serve, holder_id, escrow_moved, author_cents, _result in observed:
        label = f"{kind.value}/{shape.name}"
        if not serve:
            assert escrow_moved == 0 and author_cents == 0, (
                f"{label}: serve ad_eligible=False but the settled fill moved "
                f"{escrow_moved} cents into {holder_id}'s escrow and "
                f"{author_cents} into the author ledger"
            )
        elif holder_id is not None:
            assert escrow_moved > 0, (
                f"{label}: serve ad_eligible=True but the settled fill moved "
                f"nothing into {holder_id}'s escrow"
            )
    for shape, serve, _holder_id, _escrow_moved, _author_cents, result in observed:
        label = f"{kind.value}/{shape.name}"
        assert result.accruable is serve, (
            f"{label}: serve={serve} settlement={result.accruable} ({result.reason})"
        )
        assert serve is shape.expected, label


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


def test_the_author_ledger_answers_with_the_predicate_before_its_arxiv_scope(con):
    """The per-author ledger is arXiv-only, but it asks the shared predicate
    first: an ineligible non-arXiv document is refused for the predicate's
    reason, and only an ELIGIBLE one reaches the ledger's own scope check
    (``not_an_arxiv_paper``). Its revenue is the reader-session settlement's
    (test_a_settled_fill_accrues_exactly_when_serve_time_says_ad_eligible)."""
    non_arxiv_shapes = [
        (kind, shape)
        for kind in SourceKind
        for shape in SHAPES[kind]
        if not (shape.metadata and "arxiv_id" in shape.metadata)
    ]
    assert any(shape.expected for _kind, shape in non_arxiv_shapes)
    assert any(not shape.expected for _kind, shape in non_arxiv_shapes)
    for kind, shape in non_arxiv_shapes:
        doc_id = _make(con, kind, shape)
        decision = payout_ad_eligibility(con, doc_id)
        assert decision is not None
        result = accrue_paper_read(
            con,
            document_id=doc_id,
            revenue_cents=100,
            ad_event_id=f"evt-{doc_id}",
        )
        label = f"{kind.value}/{shape.name}"
        assert result.accruable is False, label
        expected = "not_an_arxiv_paper" if decision.eligible else decision.reason
        assert result.reason == expected, label


def test_ad_eligibility_requires_servable_without_a_tier():
    with pytest.raises(ValueError):
        ad_eligibility(None, servable=None)
    assert ad_eligibility(RightsTier.T1_REDISTRIBUTABLE, servable=None).eligible
