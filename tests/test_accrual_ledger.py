"""SPR-06 M2/M3/M4 — the (arxiv_id, author_position) accrual ledger.

Mirrors tests/test_frame_attention_accrual.py: the con() fixture is a
connect_write to a tempfile DuckDB; the asserts cover the balance gate
(conservation to the cent), the T1-only gate, the multi-author split, the
unattributed pool, append-only idempotency, and the source/version citation.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.payouts.ledger import (
    LEDGER_VERSION,
    UNATTRIBUTED_AUTHOR_POSITION,
    accrue_paper_read,
    reconcile,
)
from substrate.payouts.split import SPLIT_POLICY_VERSION

# Minimal documents table — only the columns the ledger reads (document_id +
# metadata JSON). Mirrors the _IP_HOLDERS_DDL convention in
# test_frame_attention_accrual.py (a focused DDL in the test, not the full
# graph schema).
_DOCUMENTS_DDL = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    metadata    TEXT
);
"""

# A real CC-BY URI that resolves to T1 (ad-eligible), and a real CC-BY-NC URI
# that resolves to T2 (not ad-eligible).
_CC_BY = "https://creativecommons.org/licenses/by/4.0/"
_CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"
_CC_BY_NC = "https://creativecommons.org/licenses/by-nc/4.0/"


@pytest.fixture
def con():
    tmpdir = tempfile.mkdtemp(prefix="antiek-payouts-ledger-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    c = connect_write(db_path, purpose="payouts_ledger_test")
    c.execute(_DOCUMENTS_DDL)
    yield c
    c.close()


def _authors(*positions_orcids):
    """Build an OpenAlex-shaped author list: positions_orcids = (pos, orcid)."""
    return [
        {"author_position": pos, "orcid": orcid, "display_name": f"Author {pos}"}
        for pos, orcid in positions_orcids
    ]


def _seed(con, document_id, *, arxiv_id, license_uri, authors=None,
          enrichment=True, rights_tier="T1"):
    """Insert a documents row with the metadata the ledger reads. ``enrichment``
    False omits the openalex_enrichment key entirely (the no-enrichment case);
    ``authors`` is the enriched author list when enrichment is present.
    ``rights_tier`` is stored (deliberately, to prove it is NOT trusted)."""
    meta = {"arxiv_id": arxiv_id, "license_uri": license_uri,
            "rights_tier": rights_tier, "source": "arxiv_oai_pmh"}
    if enrichment:
        meta["openalex_enrichment"] = {"authors": authors or []}
    con.execute(
        "INSERT INTO documents (document_id, metadata) VALUES (?, ?)",
        [document_id, json.dumps(meta)],
    )


# ── M2 balance gate — conservation to the cent ───────────────────────


def test_balance_single_author(con):
    _seed(con, "doc1", arxiv_id="2401.00001",
          license_uri=_CC_BY, authors=_authors((0, "orcid-a")))
    r = accrue_paper_read(con, document_id="doc1", revenue_cents=500,
                          ad_event_id="evt1")
    assert r.accruable
    assert r.reconciles()
    assert r.author_cents + r.unattributed_cents == r.attributed_cents == 500
    assert r.author_cents == 500 and r.unattributed_cents == 0


def test_balance_multi_author_indivisible(con):
    """3 authors, 100 cents → 34/33/33; Σ + unattributed == 100 to the cent."""
    _seed(con, "doc2", arxiv_id="2401.00002", license_uri=_CC0,
          authors=_authors((0, None), (1, "orcid-b"), (2, None)))
    r = accrue_paper_read(con, document_id="doc2", revenue_cents=100,
                          ad_event_id="evt2")
    assert r.reconciles()
    author_amounts = sorted(
        l.amount_cents for l in r.lines if l.attribution_kind == "author"
    )
    assert author_amounts == [33, 33, 34]
    assert sum(author_amounts) == 100
    assert r.unattributed_cents == 0


def test_reconcile_query_matches_attributed(con):
    """The read-only reconcile() query: Σ author + Σ unattributed ==
    Σ attributed, both for one paper and across the ledger."""
    _seed(con, "docA", arxiv_id="2401.00010", license_uri=_CC_BY,
          authors=_authors((0, None), (1, None)))
    _seed(con, "docB", arxiv_id="2401.00011", license_uri=_CC_BY,
          enrichment=False)  # → unattributed
    accrue_paper_read(con, document_id="docA", revenue_cents=777, ad_event_id="eA")
    accrue_paper_read(con, document_id="docB", revenue_cents=300, ad_event_id="eB")

    rec_all = reconcile(con)
    assert rec_all["author_cents"] + rec_all["unattributed_cents"] == \
        rec_all["attributed_cents"] == 1077
    assert rec_all["total_cents"] == 1077

    rec_b = reconcile(con, arxiv_id="2401.00011")
    assert rec_b["unattributed_cents"] == 300
    assert rec_b["author_cents"] == 0
    assert rec_b["attributed_cents"] == 300


# ── T1-only gate ─────────────────────────────────────────────────────


def test_t2_emits_nothing(con):
    """A CC-BY-NC (T2) paper is NOT ad-eligible — the ledger emits nothing,
    even though revenue and authors are present."""
    _seed(con, "t2doc", arxiv_id="2401.02000", license_uri=_CC_BY_NC,
          authors=_authors((0, None)), rights_tier="T1")  # stored T1 — a lie
    r = accrue_paper_read(con, document_id="t2doc", revenue_cents=500,
                          ad_event_id="evtT2")
    assert not r.accruable
    assert "tier_not_ad_eligible" in r.reason
    assert reconcile(con)["total_cents"] == 0


def test_t3_emits_nothing(con):
    """An absent/unknown license (T3) is not ad-eligible — nothing emitted."""
    _seed(con, "t3doc", arxiv_id="2401.03000", license_uri="", authors=None)
    r = accrue_paper_read(con, document_id="t3doc", revenue_cents=500,
                          ad_event_id="evtT3")
    assert not r.accruable
    assert reconcile(con)["total_cents"] == 0


def test_rights_tier_is_re_derived_not_trusted(con):
    """The stored rights_tier='T1' on a CC-BY-NC paper is a (planted) lie; the
    ledger re-derives the tier from the immutable license_uri and refuses it.
    This is the SPR-02 anti-laundering rule, asserted directly."""
    _seed(con, "liar", arxiv_id="2401.04000", license_uri=_CC_BY_NC,
          authors=_authors((0, None)), rights_tier="T1")
    r = accrue_paper_read(con, document_id="liar", revenue_cents=900,
                          ad_event_id="evtLiar")
    assert not r.accruable  # re-derived T2, not the stored T1


def test_non_arxiv_emits_nothing(con):
    """A document with no arxiv_id in metadata is not a paper — nothing
    emitted into the payouts ledger (book/publisher revenue is book_escrow's)."""
    con.execute(
        "INSERT INTO documents (document_id, metadata) VALUES (?, ?)",
        ["bookdoc", json.dumps({"license_uri": _CC_BY})],  # no arxiv_id
    )
    r = accrue_paper_read(con, document_id="bookdoc", revenue_cents=500,
                          ad_event_id="evtBook")
    assert not r.accruable
    assert r.reason == "not_an_arxiv_paper"


def test_zero_revenue_emits_nothing(con):
    _seed(con, "zdoc", arxiv_id="2401.05000", license_uri=_CC_BY,
          authors=_authors((0, None)))
    r = accrue_paper_read(con, document_id="zdoc", revenue_cents=0,
                          ad_event_id="evtZero")
    assert not r.accruable
    assert r.reason == "zero_revenue"
    assert reconcile(con)["total_cents"] == 0


# ── M4 unattributed pool ─────────────────────────────────────────────


def test_unattributed_no_enrichment(con):
    """A T1 paper with NO openalex_enrichment key → the whole amount to the
    explicit unattributed entry, never silently dropped."""
    _seed(con, "noenrich", arxiv_id="2405.99999", license_uri=_CC_BY,
          enrichment=False)
    r = accrue_paper_read(con, document_id="noenrich", revenue_cents=640,
                          ad_event_id="evtNE")
    assert r.accruable and r.reconciles()
    assert r.unattributed_cents == 640
    assert r.author_cents == 0
    (line,) = r.lines
    assert line.author_position == UNATTRIBUTED_AUTHOR_POSITION
    assert line.attribution_kind == "unattributed"


def test_unattributed_empty_authors(con):
    """A T1 paper whose enrichment matched but authors == [] → unattributed."""
    _seed(con, "empty", arxiv_id="2405.88888", license_uri=_CC_BY, authors=[])
    r = accrue_paper_read(con, document_id="empty", revenue_cents=250,
                          ad_event_id="evtEmpty")
    assert r.accruable and r.reconciles()
    assert r.unattributed_cents == 250 and r.author_cents == 0


# ── Append-only idempotency + citation ───────────────────────────────


def test_idempotent_re_accrual_no_double_count(con):
    """Re-accruing the SAME ad-event id is a no-op: row count unchanged, the
    ledger total does not double."""
    _seed(con, "idem", arxiv_id="2401.06000", license_uri=_CC_BY,
          authors=_authors((0, None), (1, None)))
    r1 = accrue_paper_read(con, document_id="idem", revenue_cents=400,
                           ad_event_id="evtIdem")
    n1 = con.execute("SELECT COUNT(*) FROM paper_author_accruals").fetchone()[0]
    r2 = accrue_paper_read(con, document_id="idem", revenue_cents=400,
                           ad_event_id="evtIdem")
    n2 = con.execute("SELECT COUNT(*) FROM paper_author_accruals").fetchone()[0]
    assert n1 == n2  # no new rows
    assert r1.event_ref == r2.event_ref
    assert reconcile(con)["total_cents"] == 400  # not 800


def test_each_row_cites_ad_event_and_versions(con):
    """Defensibility: every accrual row records the SOURCE ad-event id, the
    split-policy version, and the ledger version — so 'why is author X owed $Y'
    is fully traceable."""
    _seed(con, "cite", arxiv_id="2401.07000", license_uri=_CC_BY,
          authors=_authors((0, "orcid-x"), (1, None)))
    accrue_paper_read(con, document_id="cite", revenue_cents=200,
                      ad_event_id="evtCite")
    rows = con.execute(
        "SELECT ad_event_id, split_policy_version, ledger_version, orcid, "
        "author_position FROM paper_author_accruals ORDER BY author_position"
    ).fetchall()
    assert all(r[0] == "evtCite" for r in rows)
    assert all(r[1] == SPLIT_POLICY_VERSION for r in rows)
    assert all(r[2] == LEDGER_VERSION for r in rows)
    # The ORCID is carried through for the claimable (position 0) author.
    by_pos = {r[4]: r for r in rows}
    assert by_pos[0][3] == "orcid-x"
    assert by_pos[1][3] is None  # absent ORCID stays None, never invented


def test_distinct_events_accumulate(con):
    """Two distinct ad-events on the same paper accumulate (append-only) and
    reconcile to their combined attributed total."""
    _seed(con, "two", arxiv_id="2401.08000", license_uri=_CC_BY,
          authors=_authors((0, None), (1, None)))
    accrue_paper_read(con, document_id="two", revenue_cents=100, ad_event_id="e1")
    accrue_paper_read(con, document_id="two", revenue_cents=51, ad_event_id="e2")
    rec = reconcile(con, arxiv_id="2401.08000")
    assert rec["author_cents"] == 151
    assert rec["attributed_cents"] == 151


# ── Conservation under the incremental-posting model (SPR-06 R2 send-back) ──
# The reader posts impressions INCREMENTALLY (one page-flush at a time) under a
# CONSTANT per-session ad_event_id. The discriminator that keeps disjoint batches
# distinct — and a true retry idempotent — is the batch's underlying impression
# -id SET. These three tests pin that: (a) distinct batches with EQUAL revenue
# under the SAME constant ad_event_id MUST both accrue; (b) a true retry (same
# impression set) MUST be a no-op. Each FAILS if event_ref reverts to the
# constant-key form (ad_event_id + inputs only, ignoring impression_ids).


def test_disjoint_batches_equal_revenue_accumulate(con):
    """(a) The conservation bite. Two page-flush batches under the SAME constant
    ad_event_id with EQUAL revenue but DIFFERENT impression-id sets accumulate —
    they are NOT mis-deduped as a retry. Under the old constant-key event_ref the
    second collapses onto the first and its revenue is DROPPED (total 100, not
    200) — exactly the latent under-count this fix closes."""
    _seed(con, "incr", arxiv_id="2401.09000", license_uri=_CC_BY,
          authors=_authors((0, None), (1, None)))
    # Batch 1 — page 0's slots. Batch 2 — page 1's slots. Same constant
    # ad_event_id (the per-session key), equal revenue, DISJOINT impression ids.
    accrue_paper_read(con, document_id="incr", revenue_cents=100,
                      ad_event_id="session:S1:incr",
                      impression_ids=["imp:S1:p0s0", "imp:S1:p0s1"])
    accrue_paper_read(con, document_id="incr", revenue_cents=100,
                      ad_event_id="session:S1:incr",
                      impression_ids=["imp:S1:p1s0", "imp:S1:p1s1"])
    rec = reconcile(con, arxiv_id="2401.09000")
    assert rec["attributed_cents"] == 200  # both batches accrued — conserves
    assert rec["author_cents"] + rec["unattributed_cents"] == 200
    assert rec["total_cents"] == 200  # would be 100 under the constant key


def test_true_retry_same_impression_set_is_noop(con):
    """(b) Retry idempotency preserved. Re-posting the SAME batch — same constant
    ad_event_id AND the same impression-id set (order-insensitive) — is a no-op:
    no new rows, total unchanged. The fix distinguishes a disjoint batch from a
    genuine retry by the impression SET, so a true retry still collapses."""
    _seed(con, "retry", arxiv_id="2401.09100", license_uri=_CC_BY,
          authors=_authors((0, None), (1, None)))
    r1 = accrue_paper_read(con, document_id="retry", revenue_cents=100,
                           ad_event_id="session:S2:retry",
                           impression_ids=["imp:S2:p0s0", "imp:S2:p0s1"])
    n1 = con.execute("SELECT COUNT(*) FROM paper_author_accruals").fetchone()[0]
    # Same set, REVERSED order → same sorted set → same event_ref → no-op.
    r2 = accrue_paper_read(con, document_id="retry", revenue_cents=100,
                           ad_event_id="session:S2:retry",
                           impression_ids=["imp:S2:p0s1", "imp:S2:p0s0"])
    n2 = con.execute("SELECT COUNT(*) FROM paper_author_accruals").fetchone()[0]
    assert n1 == n2  # no new rows
    assert r1.event_ref == r2.event_ref
    assert reconcile(con, arxiv_id="2401.09100")["total_cents"] == 100  # not 200
