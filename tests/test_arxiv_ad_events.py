"""SPR-06 M1 — the T1 paper-read ad-view → revenue → author-ledger hook.

Proves the additive hook in book_escrow.accrue_reading_session:
  * a T1 arXiv paper read accrues to the (arxiv_id, author_position) payouts
    ledger ALONGSIDE the existing escrow accrual, conserved to the cent;
  * a T2/T3/non-arXiv read emits NOTHING into the payouts ledger;
  * the existing escrow behaviour is unchanged (the hook is additive);
  * re-posting a session is idempotent on the payouts ledger (no double-count).

Uses the real graph schema (init_database) so both the escrow path and the
payouts ledger have their tables, exercising the LIVE seam, not a stub.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.ad_inventory.reader_impressions import record_raw_impression
from substrate.graph.schema import init_database
from substrate.marketplace_metrics.book_escrow import accrue_reading_session
from substrate.payouts.ledger import reconcile

_CC_BY = "https://creativecommons.org/licenses/by/4.0/"
_CC_BY_NC = "https://creativecommons.org/licenses/by-nc/4.0/"


@pytest.fixture
def con():
    tmpdir = tempfile.mkdtemp(prefix="antiek-arxiv-ad-events-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    c = connect_write(db_path, purpose="arxiv_ad_events_test")
    init_database(c)
    yield c
    c.close()


def _seed_paper(con, document_id, *, arxiv_id, license_uri, authors,
                ip_holder_id=None):
    meta = {"arxiv_id": arxiv_id, "license_uri": license_uri,
            "rights_tier": "T1", "source": "arxiv_oai_pmh",
            "openalex_enrichment": {"authors": authors}}
    con.execute(
        "INSERT INTO documents (document_id, source_tier, document_type, "
        "metadata, content_class, ip_holder_id) VALUES (?, ?, ?, ?, ?, ?)",
        [document_id, 2, "paper", json.dumps(meta), "source_declared_open",
         ip_holder_id],
    )


def _authors(*positions):
    return [
        {"author_position": p, "orcid": None, "display_name": f"A{p}"}
        for p in positions
    ]


def _impressions(session_id, document_id, *, revenue_cents, slots=1):
    """N ad-fill impressions across distinct slots, summing to revenue_cents
    (split across slots so dedup/summation is exercised)."""
    per = revenue_cents // slots
    rem = revenue_cents - per * slots
    out = []
    for i in range(slots):
        cents = per + (rem if i == 0 else 0)
        out.append(record_raw_impression(
            session_id=session_id, document_id=document_id, slot_id=f"slot{i}",
            page_index=0, fill_kind="ad", revenue_usd_cents=cents,
            focused_dwell_ms=2000, tab_focused=True,
        ))
    return out


def test_t1_read_accrues_to_author_ledger(con):
    """A T1 arXiv read with 3 authors accrues 600 cents → 200/200/200 in the
    payouts ledger, reconciling to the cent — alongside the escrow path."""
    _seed_paper(con, "p1", arxiv_id="2401.10001", license_uri=_CC_BY,
                authors=_authors(0, 1, 2))
    accrue_reading_session(
        con, document_id="p1",
        impressions=_impressions("sess1", "p1", revenue_cents=600, slots=3),
        session_id="sess1",
    )
    rec = reconcile(con, arxiv_id="2401.10001")
    assert rec["attributed_cents"] == 600
    assert rec["author_cents"] + rec["unattributed_cents"] == 600
    amounts = sorted(
        r[0] for r in con.execute(
            "SELECT amount_cents FROM paper_author_accruals "
            "WHERE arxiv_id = ? AND attribution_kind = 'author'", ["2401.10001"]
        ).fetchall()
    )
    assert amounts == [200, 200, 200]


def test_t2_read_emits_nothing_into_payouts_ledger(con):
    """A CC-BY-NC (T2) read records escrow-side as usual but emits NOTHING into
    the payouts ledger (T1-only gate, re-derived from the license)."""
    _seed_paper(con, "p2", arxiv_id="2401.20002", license_uri=_CC_BY_NC,
                authors=_authors(0, 1))
    accrue_reading_session(
        con, document_id="p2",
        impressions=_impressions("sess2", "p2", revenue_cents=500),
        session_id="sess2",
    )
    assert reconcile(con, arxiv_id="2401.20002")["total_cents"] == 0
    assert con.execute(
        "SELECT COUNT(*) FROM paper_author_accruals"
    ).fetchone()[0] == 0


def test_non_arxiv_read_emits_nothing_into_payouts_ledger(con):
    """A non-arXiv book read (no arxiv_id) accrues escrow but NOT the payouts
    ledger — book/publisher revenue stays book_escrow's concern."""
    con.execute(
        "INSERT INTO documents (document_id, source_tier, document_type, "
        "metadata, content_class) VALUES (?, ?, ?, ?, ?)",
        ["book1", 2, "book", json.dumps({"license_uri": _CC_BY}),
         "public_domain"],
    )
    accrue_reading_session(
        con, document_id="book1",
        impressions=_impressions("sessB", "book1", revenue_cents=400),
        session_id="sessB",
    )
    assert con.execute(
        "SELECT COUNT(*) FROM paper_author_accruals"
    ).fetchone()[0] == 0


def test_escrow_behaviour_unchanged_by_hook(con):
    """The hook is additive: the escrow AccrualResult is identical to what the
    escrow path produces on its own (unattributed → held, $0 escrow), and the
    payouts ledger still captures the T1 attribution separately."""
    # Paper with NO ip_holder_id → escrow side holds it unattributed ($0
    # escrow), but the payouts ledger still attributes to authors.
    _seed_paper(con, "p3", arxiv_id="2401.30003", license_uri=_CC_BY,
                authors=_authors(0, 1), ip_holder_id=None)
    result = accrue_reading_session(
        con, document_id="p3",
        impressions=_impressions("sess3", "p3", revenue_cents=300),
        session_id="sess3",
    )
    # Escrow side: revenue seen, but unknown holder → held, nothing to escrow.
    assert result.revenue_cents == 300
    assert result.accrued_to_escrow_cents == 0
    assert result.unattributed is True
    # Payouts side: still fully attributed to the two authors, to the cent.
    rec = reconcile(con, arxiv_id="2401.30003")
    assert rec["author_cents"] == 300 and rec["unattributed_cents"] == 0


def test_session_re_post_is_idempotent_on_payouts_ledger(con):
    """Re-posting the same session's impressions does not double the payouts
    ledger (same ad_event_id = session:{session}:{document})."""
    _seed_paper(con, "p4", arxiv_id="2401.40004", license_uri=_CC_BY,
                authors=_authors(0, 1))
    imps = _impressions("sess4", "p4", revenue_cents=200, slots=2)
    accrue_reading_session(con, document_id="p4", impressions=imps,
                           session_id="sess4")
    n1 = con.execute("SELECT COUNT(*) FROM paper_author_accruals").fetchone()[0]
    accrue_reading_session(con, document_id="p4", impressions=imps,
                           session_id="sess4")
    n2 = con.execute("SELECT COUNT(*) FROM paper_author_accruals").fetchone()[0]
    assert n1 == n2
    assert reconcile(con, arxiv_id="2401.40004")["total_cents"] == 200  # not 400


def _batch(session_id, document_id, *, slot_ids, page_index, revenue_cents):
    """One page-flush batch: ad-fill impressions on the given DISJOINT slot ids
    (distinct slots/pages → distinct impression ids), summing to revenue_cents.
    Mirrors the SPR-05 reader, which flushes only the current page's slots per
    page change under a constant session_id."""
    per = revenue_cents // len(slot_ids)
    rem = revenue_cents - per * len(slot_ids)
    out = []
    for i, sid in enumerate(slot_ids):
        cents = per + (rem if i == 0 else 0)
        out.append(record_raw_impression(
            session_id=session_id, document_id=document_id, slot_id=sid,
            page_index=page_index, fill_kind="ad", revenue_usd_cents=cents,
            focused_dwell_ms=2000, tab_focused=True,
        ))
    return out


def test_incremental_page_flushes_conserve_end_to_end(con):
    """(c) END-TO-END conservation under the reader's incremental-posting model.

    Two DISJOINT page-flush batches for the SAME session + document (equal
    revenue, different slot_ids → different impression ids) accrue through
    accrue_reading_session — exactly as the SPR-05 reader posts one page at a
    time under a constant session_id. The payouts-ledger reconcile total MUST
    equal the escrow-attributed revenue total (cumulative across flushes); they
    MUST NOT diverge. Under the old constant-key event_ref the second batch is
    mis-deduped and DROPPED → the ledger holds 200 while escrow saw 400, the
    exact conservation break this fix closes."""
    _seed_paper(con, "p5", arxiv_id="2401.50005", license_uri=_CC_BY,
                authors=_authors(0, 1))

    # Flush 1 — page 0's two slots, 200c.
    r1 = accrue_reading_session(
        con, document_id="p5",
        impressions=_batch("sess5", "p5", slot_ids=["p0s0", "p0s1"],
                           page_index=0, revenue_cents=200),
        session_id="sess5",
    )
    # Flush 2 — page 1's two slots, 200c (DISJOINT impression ids, EQUAL revenue).
    r2 = accrue_reading_session(
        con, document_id="p5",
        impressions=_batch("sess5", "p5", slot_ids=["p1s0", "p1s1"],
                           page_index=1, revenue_cents=200),
        session_id="sess5",
    )

    # The escrow path saw 200 + 200 = 400 of attributed revenue across the two
    # flushes (each flush's deduped book_imps sum, independent of the ledger).
    escrow_attributed = r1.revenue_cents + r2.revenue_cents
    assert escrow_attributed == 400

    # The payouts ledger must hold the SAME 400 — no batch dropped as a retry.
    rec = reconcile(con, arxiv_id="2401.50005")
    assert rec["attributed_cents"] == escrow_attributed == 400
    assert rec["author_cents"] + rec["unattributed_cents"] == 400
    assert rec["total_cents"] == 400  # would be 200 under the constant key


def test_payouts_ledger_failure_is_logged_and_escrow_unaffected(con, monkeypatch, caplog):
    """The attribution-layer swallow must be AUDITABLE. Force accrue_paper_read
    to raise; assert (i) the escrow accrual still completes normally (the
    defensive isolation holds), and (ii) the failure is LOGGED (no silent drop).
    """
    import logging as _logging

    import substrate.payouts.ledger as ledger_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated attribution-layer failure")

    monkeypatch.setattr(ledger_mod, "accrue_paper_read", _boom)

    # A T1 arXiv paper WITH a resolvable ip_holder so escrow actually accrues.
    from substrate import ip_holders
    holder_id = ip_holders.create_pre_onboarded(con, display_name="Pub X")
    _seed_paper(con, "p6", arxiv_id="2401.60006", license_uri=_CC_BY,
                authors=_authors(0), ip_holder_id=holder_id)

    with caplog.at_level(_logging.ERROR, logger="substrate.marketplace_metrics.book_escrow"):
        result = accrue_reading_session(
            con, document_id="p6",
            impressions=_impressions("sess6", "p6", revenue_cents=300),
            session_id="sess6",
        )

    # (i) Escrow path unaffected: the publisher escrow still accrued normally.
    assert result.revenue_cents == 300
    assert result.accrued_to_escrow_cents > 0
    assert result.unattributed is False
    assert result.reason == "accrued_to_publisher_escrow"
    # The payouts ledger wrote nothing (the hook raised before any insert).
    assert con.execute(
        "SELECT COUNT(*) FROM paper_author_accruals"
    ).fetchone()[0] == 0

    # (ii) The failure was LOGGED — visible, not silently swallowed.
    failure_logs = [
        r for r in caplog.records
        if r.name == "substrate.marketplace_metrics.book_escrow"
        and r.levelno >= _logging.ERROR
    ]
    assert failure_logs, "expected an ERROR log for the swallowed accrual failure"
    msg = failure_logs[0].getMessage()
    assert "payouts-ledger accrual failed" in msg
    assert "p6" in msg and "sess6" in msg
    # logger.exception attaches the traceback so the cause is auditable.
    assert failure_logs[0].exc_info is not None
