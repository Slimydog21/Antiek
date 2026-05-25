"""Speak SPR-09 — publishing + serving + physical books tests.

Rigor #3: a public publish with an unmet gate (blocked with the
specific reason), a private book (creator-paid), a physical order for a
private vs public book (creator vs split), and the honest boundary —
a physical order is QUOTED, never fulfilled (no live POD vendor).
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.speak import contributor, physical_book, project, publish, publish_gate, subject_consent
from substrate.speak.publish_gate import PublishBlocked
from substrate.speak.schema import ensure_speak_schema
from substrate.speak.third_party import record_claim


@pytest.fixture
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-publish-test-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def _con(db):
    return connect_write(db, purpose="publish_test")


def _public_ready_project(con):
    """A public project that passes every gate: deceased subject with a
    documented rationale, contributors mapped, one operator-attested
    third-party claim."""
    p = project.create_project(con, title="Dad's biography", subject_ref="the-dad",
                               subject_status="deceased", publish_intent="will_be_public")
    subject_consent.record_subject_consent(
        con, project_id=p.project_id, subject_ref="the-dad", subject_status="deceased",
        consent_granted=False, rationale="deceased 2019; documented rule.",
    )
    contributor.map_contributor(con, interview_id="iv-a", project_id=p.project_id, display_name="A")
    c = record_claim(con, project_id=p.project_id, interview_id="iv-a",
                     text="He ran the village bakery for thirty years.",
                     about_subject=True, subject_ref="the-dad")
    publish_gate.operator_attest_claim(con, c.claim_id, project_id=p.project_id)
    return p.project_id


# ── M1 publish per mode ─────────────────────────────────────────────────


def test_private_publish_not_served(db):
    with _con(db) as con:
        p = project.create_project(con, title="Private bio", publish_intent="private_never_published")
        result = publish.publish(con, project_id=p.project_id)
        assert result.visibility == "private"
        assert result.served is False
        assert result.servability == "gated_metadata_only"


def test_public_publish_lands_in_servable_corpus(db, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")
    with _con(db) as con:
        project_id = _public_ready_project(con)
        result = publish.publish(con, project_id=project_id)
        assert result.visibility == "public"
        assert result.served is True
        assert result.servability == "platform_authored"  # Read's servable corpus


# ── M2 route the split on public publish ────────────────────────────────


def test_public_publish_routes_split_private_does_not(db, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")
    with _con(db) as con:
        project_id = _public_ready_project(con)
        result = publish.publish(con, project_id=project_id, ad_revenue_usd=Decimal("100"))
        assert len(result.accrual_lines) >= 1  # contributor shares accrued
    with _con(db) as con:
        p = project.create_project(con, title="Private", publish_intent="private_never_published")
        result = publish.publish(con, project_id=p.project_id)
        assert result.accrual_lines == ()  # private accrues nothing


# ── M3 consent + verification gate at publish ───────────────────────────


def test_public_publish_blocked_when_legal_gate_open(db, monkeypatch):
    monkeypatch.delenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", raising=False)  # G2/G3 open
    with _con(db) as con:
        project_id = _public_ready_project(con)
        with pytest.raises(PublishBlocked) as exc:
            publish.publish(con, project_id=project_id)
        assert "legal gate" in str(exc.value) or "G2" in str(exc.value)


def test_public_publish_blocked_without_subject_consent(db, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")
    with _con(db) as con:
        # Living subject, no consent → blocked even with G2/G3 "closed".
        p = project.create_project(con, title="Living-subject bio", subject_ref="the-dad",
                                   subject_status="living", publish_intent="will_be_public")
        subject_consent.record_subject_consent(
            con, project_id=p.project_id, subject_ref="the-dad",
            subject_status="living", consent_granted=False,
        )
        with pytest.raises(PublishBlocked):
            publish.publish(con, project_id=p.project_id)


def test_public_publish_blocked_by_uncorroborated_claim(db, monkeypatch):
    monkeypatch.setenv("ANTIEK_SPEAK_PUBLIC_PUBLISHING", "1")
    with _con(db) as con:
        project_id = _public_ready_project(con)
        # Add an uncorroborated third-party claim → public gate blocks.
        record_claim(con, project_id=project_id, interview_id="iv-b",
                     text="He secretly funded a rival.", about_subject=True, subject_ref="the-dad")
        with pytest.raises(PublishBlocked):
            publish.publish(con, project_id=project_id)


# ── M4 physical-book ordering hook (quote only) ─────────────────────────


def test_physical_order_is_quoted_not_fulfilled(db):
    with _con(db) as con:
        p = project.create_project(con, title="Private bio", publish_intent="private_never_published")
        quote = physical_book.order_physical_book(
            con, project_id=p.project_id, book_format="paperback", page_count=200,
        )
        assert quote.cost_usd > 0
        assert quote.provider == "stub"
        assert quote.fulfilled is False  # quoted, never printed/shipped


def test_unknown_format_rejected(db):
    with _con(db) as con:
        p = project.create_project(con, title="Bio")
        with pytest.raises(ValueError):
            physical_book.order_physical_book(con, project_id=p.project_id,
                                              book_format="scroll", page_count=10)


# ── M5 physical cost allocation per matrix ──────────────────────────────


def test_private_book_creator_pays(db):
    with _con(db) as con:
        p = project.create_project(con, title="Private bio", publish_intent="private_never_published")
        quote = physical_book.order_physical_book(
            con, project_id=p.project_id, book_format="hardcover", page_count=150,
        )
        assert quote.payer == "creator"


def test_public_book_split_persists(db):
    with _con(db) as con:
        p = project.create_project(con, title="Public bio", publish_intent="will_be_public")
        quote = physical_book.order_physical_book(
            con, project_id=p.project_id, book_format="paperback", page_count=150,
        )
        assert quote.payer == "split"


# ── provider seam is vendor-agnostic (drop-in) but fulfillment stays off ─


def test_stub_provider_registered():
    assert "stub" in physical_book.available_providers()
    assert physical_book.get_provider("stub").name == "stub"


def test_order_routes_to_registered_provider_by_name(db):
    class _FakeVendor:
        name = "fakepod"

        def quote(self, *, book_format, page_count):
            from decimal import Decimal
            return Decimal("99.99")  # distinctive price proves routing

    physical_book.register_provider(_FakeVendor())
    try:
        with _con(db) as con:
            p = project.create_project(con, title="Bio", publish_intent="private_never_published")
            quote = physical_book.order_physical_book(
                con, project_id=p.project_id, book_format="paperback", page_count=10,
                provider_name="fakepod",
            )
            assert quote.provider == "fakepod"
            assert str(quote.cost_usd) == "99.99"  # the vendor's pricing, no rework
    finally:
        physical_book._PROVIDERS.pop("fakepod", None)


def test_unknown_provider_name_rejected(db):
    with _con(db) as con:
        p = project.create_project(con, title="Bio")
        with pytest.raises(ValueError):
            physical_book.order_physical_book(
                con, project_id=p.project_id, book_format="paperback", page_count=10,
                provider_name="no-such-vendor",
            )


def test_fulfill_refused_no_live_vendor(db):
    # The chokepoint that proves nothing prints/ships before a vendor is
    # chosen: the stub can't fulfill, so fulfill() refuses.
    with _con(db) as con:
        p = project.create_project(con, title="Bio", publish_intent="private_never_published")
        quote = physical_book.order_physical_book(
            con, project_id=p.project_id, book_format="paperback", page_count=10,
        )
        with pytest.raises(physical_book.PodVendorUnconfigured):
            physical_book.fulfill(con, order_id=quote.order_id)
