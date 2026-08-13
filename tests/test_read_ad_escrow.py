"""Read SPR-09 — book reading-session → rights-holder escrow accrual.

The non-negotiable gates: accrual is not disbursement (no pre-claim
payout path), zero buyers shows $0 (no invented money), unknown rights
holder accrues to a flagged bucket (not a wrong holder), and accrued
totals reconcile against impressions (no double-count).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate import ip_holders
from substrate.ad_inventory.reader_impressions import ReaderImpression
from substrate.books import ingest as bingest
from substrate.constants import UNATTRIBUTED_RIGHTS_BUCKET
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database
from substrate.marketplace_metrics.book_escrow import (
    accrue_reading_session,
    is_disbursement_unlocked,
)


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-read-escrow-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    con = connect_write(db_path, purpose="escrow-test")
    init_database(con)
    con.close()
    return db_path


def _imp(document_id, slot, revenue_cents, *, session="s1", attention=True):
    return ReaderImpression(
        impression_id=f"imp:{session}:{slot}", session_id=session,
        document_id=document_id, slot_id=slot, page_index=0,
        fill_kind="ad" if revenue_cents else "house",
        revenue_usd_cents=revenue_cents,
        focused_dwell_ms=2000 if attention else 0,
        counted_attention=attention,
    )


def _book_with_publisher(db, document_id, publisher_name):
    con = connect_write(db, purpose="setup")
    try:
        insert_document(con, document_id=document_id, source_tier=2,
                        document_type="book", title="B", raw_text="x")
        asset = bingest.register_book(
            con, document_id=document_id, content_class="opt_in_licensed",
            rights_holder_name=publisher_name,
        )
        return asset.ip_holder_id
    finally:
        con.close()


def test_accrual_credits_publisher_escrow(db):
    holder = _book_with_publisher(db, "doc-pub", "MIT Press")
    con = connect_write(db, purpose="accrue")
    try:
        result = accrue_reading_session(
            con, document_id="doc-pub", session_id="s1",
            impressions=[_imp("doc-pub", "slot:doc-pub:p0:top", 1000)],
        )
        holder_after = ip_holders.get(con, holder)
    finally:
        con.close()
    assert result.ip_holder_id == holder
    assert result.revenue_cents == 1000
    assert result.accrued_to_escrow_cents > 0
    # Escrow actually moved (publisher share of the 1000c, after platform cut).
    assert holder_after.escrow_balance_usd > 0


def test_accrual_is_not_disbursement(db):
    """The danger gate: a pre_onboarded publisher accrues escrow but
    disbursement stays locked. There is no pre-claim payout path."""
    holder = _book_with_publisher(db, "doc-pub2", "Cambridge University Press")
    con = connect_write(db, purpose="accrue")
    try:
        accrue_reading_session(
            con, document_id="doc-pub2", session_id="s1",
            impressions=[_imp("doc-pub2", "slot:doc-pub2:p0:top", 500)],
        )
        # Pre_onboarded → disbursement locked even though escrow accrued.
        locked_before = is_disbursement_unlocked(con, holder)
        # Only a claim (gated on G2 + G3) unlocks it.
        ip_holders.mark_invited(con, holder)
        ip_holders.claim(con, holder, stripe_connect_account_id="acct_x")
        unlocked_after = is_disbursement_unlocked(con, holder)
    finally:
        con.close()
    assert locked_before is False, "disbursement unlocked before claim — gate broken"
    assert unlocked_after is True


def test_zero_buyer_accrues_no_dollars_but_tracks_attention(db):
    holder = _book_with_publisher(db, "doc-free", "Princeton University Press")
    con = connect_write(db, purpose="accrue")
    try:
        result = accrue_reading_session(
            con, document_id="doc-free", session_id="s1",
            impressions=[_imp("doc-free", "slot:doc-free:p0:top", 0)],
        )
        holder_after = ip_holders.get(con, holder)
    finally:
        con.close()
    assert result.revenue_cents == 0
    assert result.accrued_to_escrow_cents == 0
    assert result.attention_impressions == 1  # share tracked
    assert holder_after.escrow_balance_usd == 0  # no invented money


def test_unknown_rights_holder_goes_to_flagged_bucket(db):
    """A gated book with no rights holder accrues to the unattributed
    bucket, never to a wrong holder, and never disburses."""
    con = connect_write(db, purpose="setup")
    try:
        insert_document(con, document_id="doc-orphan", source_tier=2,
                        document_type="book", title="Orphan", raw_text="x")
        # register with no rights_holder_name → gated, ip_holder_id NULL
        bingest.register_book(con, document_id="doc-orphan", provenance="online")
    finally:
        con.close()
    con = connect_write(db, purpose="accrue")
    try:
        result = accrue_reading_session(
            con, document_id="doc-orphan", session_id="s1",
            impressions=[_imp("doc-orphan", "slot:doc-orphan:p0:top", 800)],
        )
    finally:
        con.close()
    assert result.unattributed is True
    assert result.ip_holder_id == UNATTRIBUTED_RIGHTS_BUCKET
    assert result.accrued_to_escrow_cents == 0  # held, not mis-accrued
    assert is_disbursement_unlocked(connect_read(db), UNATTRIBUTED_RIGHTS_BUCKET) is False


def test_client_priced_book_impression_endpoint_is_tombstoned(db):
    """The legacy browser-priced route cannot mutate rights-holder escrow."""
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    holder = _book_with_publisher(db, "doc-imp", "MIT Press")
    con = connect_read(db)
    try:
        before = ip_holders.get(con, holder).escrow_balance_usd
    finally:
        con.close()
    client = TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))
    resp = client.post(
        "/books/doc-imp/ad-impressions",
        json={
            "session_id": "sess-1",
            "impressions": [
                # Focused + long dwell → attention counts.
                {"slot_id": "slot:doc-imp:p0:top", "page_index": 0, "fill_kind": "house",
                 "revenue_usd_cents": 999999, "focused_dwell_ms": 5000, "tab_focused": True},
                # Backgrounded tab + long dwell → attention does NOT count
                # (client cannot inflate attention).
                {"slot_id": "slot:doc-imp:p0:bottom", "page_index": 0, "fill_kind": "house",
                 "revenue_usd_cents": 0, "focused_dwell_ms": 99999, "tab_focused": False},
            ],
        },
    )
    assert resp.status_code == 410
    assert resp.json() == {"detail": "client_priced_ad_impressions_disabled"}
    con = connect_read(db)
    try:
        assert ip_holders.get(con, holder).escrow_balance_usd == before
        # No raw impression/accrual ledger was materialized by the rejected write.
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        if "reader_ad_impressions" in tables:
            assert con.execute("SELECT count(*) FROM reader_ad_impressions").fetchone()[0] == 0
    finally:
        con.close()


def test_reconciliation_no_double_count_on_reemit(db):
    """Re-emitted impressions (same id) accrue once, not twice — the
    reconciliation invariant."""
    holder = _book_with_publisher(db, "doc-rec", "MIT Press")
    imps = [
        _imp("doc-rec", "slot:doc-rec:p0:top", 1000),
        _imp("doc-rec", "slot:doc-rec:p0:top", 1000),  # re-emit, same slot
    ]
    con = connect_write(db, purpose="accrue")
    try:
        result = accrue_reading_session(
            con, document_id="doc-rec", session_id="s1", impressions=imps,
        )
        holder_after = ip_holders.get(con, holder)
    finally:
        con.close()
    assert result.revenue_cents == 1000, "re-emitted impression double-counted"
    # Escrow reflects one impression's publisher share, not two.
    from decimal import Decimal
    assert holder_after.escrow_balance_usd <= Decimal("10.00")
