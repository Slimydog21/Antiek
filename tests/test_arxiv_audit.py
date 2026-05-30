"""SPR-09 M4 — append-only fetch→serve→accrue→takedown audit + takedown CLI.

Acceptance (red-then-green):
  (a) a full fetch→serve→accrue sequence for one paper is QUERYABLE via
      ``trace(con, arxiv_id)`` returning all three legs in lifecycle order;
  (b) NO audit row contains body text (assert raw_text/snippet never stored,
      and the writer REJECTS a body-shaped detail key — §9.0);
  (c) ``tools/arxiv_takedown.py`` removes the body (raw_text NULL + content_class
      restricted) AND logs an ``arxiv.takedown`` event;
  (d) append-only idempotency — re-recording the same event is a no-op.

Uses the ``con()`` connect_write tempfile fixture convention from
``tests/test_frame_attention_accrual.py``.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.audit.arxiv_audit import (
    ARXIV_ACCRUE,
    ARXIV_FETCH,
    ARXIV_SERVE,
    ARXIV_TAKEDOWN,
    record_event,
    trace,
)
from substrate.graph.schema import init_database


@pytest.fixture
def con():
    tmpdir = tempfile.mkdtemp(prefix="antiek-arxiv-audit-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    c = connect_write(db_path, purpose="arxiv_audit_test")
    init_database(c)
    yield c
    c.close()


@pytest.fixture
def db_path():
    tmpdir = tempfile.mkdtemp(prefix="antiek-arxiv-audit-cli-")
    path = os.path.join(tmpdir, "test.duckdb")
    c = connect_write(path, purpose="arxiv_audit_cli_setup")
    init_database(c)
    c.close()
    return path


_ARXIV_ID = "2401.00001"
_DOC_ID = "doc-arxiv-2401.00001"
_BODY = "THE FULL PAPER BODY THAT MUST NEVER LAND IN AN AUDIT ROW. " * 30


# ── (a) full fetch→serve→accrue trace is queryable in lifecycle order ───────


def test_fetch_serve_accrue_trace_is_queryable_in_order(con):
    """A paper's three lifecycle legs, recorded out of order, reconstruct via
    trace() in fetch→serve→accrue order — the single ToS-compliance query."""
    # Record in a deliberately SCRAMBLED order to prove trace() orders them.
    record_event(
        con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_ACCRUE,
        amount_cents=42, reason="t1_arxiv_accrued",
        detail={"ad_event_id": "session:s1:" + _DOC_ID},
    )
    record_event(
        con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_FETCH,
        detail={"source_url": "https://arxiv.org/pdf/2401.00001", "byte_size": 12345},
    )
    record_event(
        con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_SERVE,
        tier="T1", reason="served", detail={"servable": True, "served_body": True},
    )

    events = trace(con, _ARXIV_ID)
    kinds = [e.kind for e in events]
    assert kinds == [ARXIV_FETCH, ARXIV_SERVE, ARXIV_ACCRUE], kinds
    # The accrue leg carries the attributed cents; the serve leg carries tier.
    accrue = next(e for e in events if e.kind == ARXIV_ACCRUE)
    serve = next(e for e in events if e.kind == ARXIV_SERVE)
    assert accrue.amount_cents == 42
    assert serve.tier == "T1"
    # A different paper does not appear in this paper's trace.
    assert trace(con, "2402.99999") == []


# ── (b) §9.0 — NO body text in any audit row ────────────────────────────────


def test_no_audit_row_contains_body_text(con):
    """§9.0 invariant: not a single audit row carries body content. We record all
    four kinds, then scan EVERY column of EVERY row for the body sentinel."""
    record_event(con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_FETCH,
                 detail={"source_url": "https://arxiv.org/pdf/2401.00001"})
    record_event(con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_SERVE,
                 tier="T1", reason="served", detail={"servable": True})
    record_event(con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_ACCRUE,
                 amount_cents=42, detail={"ad_event_id": "x"})
    record_event(con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_TAKEDOWN,
                 reason="dmca", detail={"chunks_deleted": False})

    rows = con.execute("SELECT * FROM arxiv_audit").fetchall()
    assert len(rows) == 4
    for row in rows:
        for col in row:
            assert _BODY not in str(col), "a body must NEVER appear in an audit row"
            # No column is large enough to be a body (refs/counts only).
            assert len(str(col)) < 500


def test_writer_rejects_a_body_shaped_detail_key(con):
    """§9.0 defensive enforcement: a careless caller that tries to stuff a body
    into ``detail`` is REFUSED — the audit trail cannot become a body leak."""
    with pytest.raises(ValueError, match="body content"):
        record_event(
            con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_SERVE,
            detail={"raw_text": _BODY},
        )
    with pytest.raises(ValueError, match="body content"):
        record_event(
            con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_SERVE,
            detail={"snippet": "a leaked snippet"},
        )
    # And nothing was written.
    assert trace(con, _ARXIV_ID) == []


def test_writer_rejects_a_nested_body_shaped_detail_key(con):
    """§9.0 round-2 — a body buried in a NESTED dict or a list (not just a
    top-level key) is ALSO rejected. The prior top-level-only scan let
    ``detail={'meta': {'raw_text': ...}}`` bypass; the recursive scan closes it."""
    # Nested under a sub-dict.
    with pytest.raises(ValueError, match="body content"):
        record_event(
            con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_SERVE,
            detail={"meta": {"raw_text": _BODY}},
        )
    # Buried two levels deep.
    with pytest.raises(ValueError, match="body content"):
        record_event(
            con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_SERVE,
            detail={"outer": {"inner": {"snippet": "leak"}}},
        )
    # Inside a list of dicts.
    with pytest.raises(ValueError, match="body content"):
        record_event(
            con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_SERVE,
            detail={"items": [{"ref": "ok"}, {"body": _BODY}]},
        )
    # Nothing was written by any rejected call.
    assert trace(con, _ARXIV_ID) == []

    # A genuinely body-free NESTED detail is still accepted (no false positive).
    record_event(
        con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_SERVE,
        detail={"meta": {"tier": "T1", "refs": ["a", "b"]}, "count": 3},
    )
    assert len([e for e in trace(con, _ARXIV_ID) if e.kind == ARXIV_SERVE]) == 1


def test_unknown_kind_is_rejected(con):
    """Only the four namespaced kinds are accepted — a typo cannot silently land
    an off-vocabulary row (the CHECK constraint backs this too)."""
    with pytest.raises(ValueError, match="unknown arxiv_audit kind"):
        record_event(con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind="arxiv.bogus")


# ── (c) the takedown CLI removes the body AND logs arxiv.takedown ───────────


def _register_arxiv_book(db_path: str, *, body: str) -> None:
    """Insert a documents row for the arXiv id (servable body) + register its
    book_assets row so take_down has a target."""
    from substrate.books.model import upsert_book_asset
    from substrate.constants import SOURCE_DECLARED_OPEN_CONTENT_CLASS
    from substrate.graph.ops import insert_document

    con = connect_write(db_path, purpose="arxiv_audit_setup")
    try:
        insert_document(
            con, document_id=_DOC_ID, source_tier=3,
            document_type="academic_paper", title="A Paper", author="Auth",
            raw_text=body, content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS,
            metadata={
                "source": "arxiv_oai_pmh",
                "arxiv_id": _ARXIV_ID,
                "license_uri": "http://creativecommons.org/licenses/by/4.0/",
            },
        )
        upsert_book_asset(con, document_id=_DOC_ID)
    finally:
        con.close()


def test_takedown_cli_removes_body_and_logs_takedown(db_path):
    """RED-THEN-GREEN acceptance: before takedown the body is present; after the
    CLI runs the raw_text is NULL + content_class is restricted AND an
    arxiv.takedown event appears in the trace."""
    from substrate.constants import TAKEDOWN_CONTENT_CLASS
    from tools.arxiv_takedown import take_down_arxiv

    _register_arxiv_book(db_path, body=_BODY)

    # Precondition: the body is present and servable-classed.
    c = connect_write(db_path, purpose="precheck")
    try:
        cc, raw = c.execute(
            "SELECT content_class, raw_text FROM documents WHERE document_id = ?",
            [_DOC_ID],
        ).fetchone()
        assert raw == _BODY
        assert cc != TAKEDOWN_CONTENT_CLASS
        # No takedown leg yet.
        assert [e.kind for e in trace(c, _ARXIV_ID)] == []
    finally:
        c.close()

    performed, document_id = take_down_arxiv(db_path, _ARXIV_ID, reason="dmca")
    assert performed is True
    assert document_id == _DOC_ID

    # Postcondition: body purged, content restricted, takedown logged.
    c = connect_write(db_path, purpose="postcheck")
    try:
        cc, raw = c.execute(
            "SELECT content_class, raw_text FROM documents WHERE document_id = ?",
            [_DOC_ID],
        ).fetchone()
        assert raw is None, "take_down must NULL raw_text"
        assert cc == TAKEDOWN_CONTENT_CLASS, "content_class must move to the takedown gate"
        events = trace(c, _ARXIV_ID)
        td = [e for e in events if e.kind == ARXIV_TAKEDOWN]
        assert len(td) == 1, events
        assert td[0].reason == "dmca"
        # HONEST chunk-erasure record: chunks are gate-suppressed, not deleted.
        assert td[0].detail.get("chunks_deleted") is False
    finally:
        c.close()


def test_takedown_cli_is_idempotent(db_path):
    """A second takedown of an already-down paper performs no second purge and
    the audit re-record is a no-op (append-only idempotency at the CLI level)."""
    from tools.arxiv_takedown import take_down_arxiv

    _register_arxiv_book(db_path, body=_BODY)
    take_down_arxiv(db_path, _ARXIV_ID, reason="dmca")
    performed2, _ = take_down_arxiv(db_path, _ARXIV_ID, reason="dmca")
    assert performed2 is False  # already down — no second purge

    c = connect_write(db_path, purpose="idem-check")
    try:
        td = [e for e in trace(c, _ARXIV_ID) if e.kind == ARXIV_TAKEDOWN]
        # Same (arxiv_id, kind, document_id, reason, detail) → one row (idempotent).
        assert len(td) == 1, td
    finally:
        c.close()


def test_takedown_with_a_different_reason_is_a_distinct_audit_event(db_path):
    """§9.0 round-2 — a re-takedown under a DIFFERENT reason is a DISTINCT audit
    event (the new reason is NOT lost), while an identical re-run stays idempotent.

    RED-THEN-GREEN: before ``reason`` was hashed into the event_id, the second
    takedown (reason='court-order') collapsed onto the first ('dmca') row and the
    new reason vanished — so the trace had ONE takedown leg with only the original
    reason. With reason in the identity there are TWO distinct takedown legs (one
    per reason), and the new reason is recorded."""
    from tools.arxiv_takedown import take_down_arxiv

    _register_arxiv_book(db_path, body=_BODY)
    take_down_arxiv(db_path, _ARXIV_ID, reason="dmca")
    # A second compliance demand under a DIFFERENT reason on the same paper.
    take_down_arxiv(db_path, _ARXIV_ID, reason="court-order")
    # A THIRD run repeating the first reason must NOT mint a new row (idempotent).
    take_down_arxiv(db_path, _ARXIV_ID, reason="dmca")

    c = connect_write(db_path, purpose="distinct-reason-check")
    try:
        td = [e for e in trace(c, _ARXIV_ID) if e.kind == ARXIV_TAKEDOWN]
        reasons = sorted(e.reason for e in td)
        assert reasons == ["court-order", "dmca"], (
            f"expected two distinct takedown legs (one per reason); got {reasons}"
        )
    finally:
        c.close()


# ── (d) append-only idempotency at the record_event level ───────────────────


def test_record_event_is_append_only_idempotent(con):
    """Re-recording the SAME event (same arxiv_id, kind, document_id, detail) is a
    no-op returning the existing id — never a duplicate row, never a mutation."""
    id1 = record_event(
        con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_FETCH,
        detail={"sha256": "abc", "byte_size": 100},
    )
    id2 = record_event(
        con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_FETCH,
        detail={"sha256": "abc", "byte_size": 100},
    )
    assert id1 == id2
    assert len(trace(con, _ARXIV_ID)) == 1

    # A DIFFERENT detail (a re-fetch with new bytes) is a DISTINCT append-only row.
    record_event(
        con, arxiv_id=_ARXIV_ID, document_id=_DOC_ID, kind=ARXIV_FETCH,
        detail={"sha256": "def", "byte_size": 200},
    )
    fetches = [e for e in trace(con, _ARXIV_ID) if e.kind == ARXIV_FETCH]
    assert len(fetches) == 2


# ── (e) the FETCH leg fires in the REAL production fetch→store path ──────────


class _StubEmbedder:
    """Deterministic fake embedder — no sentence-transformers in CI."""

    dimension = 16

    def encode(self, text: str) -> list[float]:
        v = [0.0] * 16
        v[abs(hash(text)) % 16] = 1.0
        return v


def test_fetch_leg_fires_in_the_real_store_path_not_just_via_audit_con(db_path, monkeypatch):
    """BLOCKING M4 — prove the ``arxiv.fetch`` leg appears in
    ``trace(con, arxiv_id)`` after the REAL production fetch→store path runs, NOT
    only when ``fetch_pdf(audit_con=...)`` is called directly.

    The round-1 fetch-audit was reachable ONLY via ``fetch_pdf(audit_con=...)``,
    which no production caller passed — so a real on-demand T1 acquisition left NO
    fetch leg in the trace (the "full fetch→serve→accrue trace" criterion was
    unmet). The production boundary is ``store_pdf_for_arxiv_row``: it holds the
    verified ``FetchedPdf`` + the single-writer connection, so the fetch is
    audited there. This test drives that REAL store path (a SPR-01-seeded T1 row +
    a fetched PDF) and asserts the fetch leg landed.

    RED-THEN-GREEN AT PRODUCTION LEVEL (verified): remove the
    ``_record_fetch_audit(...)`` call from
    ``acquisition/arxiv/store.py::store_pdf_for_arxiv_row`` and this test goes RED
    (no ``arxiv.fetch`` leg in the trace after a genuine store); restoring it makes
    it GREEN. Note: this does NOT call ``fetch_pdf(audit_con=...)`` — it proves the
    PRODUCTION wiring, not the helper."""
    import hashlib

    from acquisition.arxiv.adapter import arxiv_doc_id
    from acquisition.arxiv.oai_persist import persist_oai_records
    from acquisition.arxiv.pdf_fetch import FetchedPdf
    from acquisition.arxiv.store import store_pdf_for_arxiv_row
    from acquisition.books.public_domain import text_to_pdf
    from substrate.rights import RightsTier
    from substrate.schemas.documents import ArxivOaiRecord

    arxiv_id = "2402.20001"
    cc_by = "http://creativecommons.org/licenses/by/4.0/"

    # Seed exactly as SPR-01's harvest does — a gated-floor T1 row.
    persist_oai_records(
        [ArxivOaiRecord(
            arxiv_id=arxiv_id, datestamp="2024-02-15", license_uri=cc_by,
            title="An Open Paper", categories=("cs.AI",),
        )],
        db_path=db_path,
    )

    # A real PDF body so the real read_pdf extractor clears the husk floor.
    pdf_text = "This is a synthetic open-access academic paper body. " * 60
    pdf_bytes = text_to_pdf(pdf_text, title="Open Paper")
    fetched = FetchedPdf(
        arxiv_id=arxiv_id,
        source_url=f"https://arxiv.org/pdf/{arxiv_id}",
        content=pdf_bytes,
        sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        byte_size=len(pdf_bytes),
    )

    # The REAL production store path (NOT fetch_pdf(audit_con=...)).
    outcome = store_pdf_for_arxiv_row(
        fetched, db_path=db_path, embedder=_StubEmbedder()
    )
    assert outcome.status == "stored"
    assert outcome.tier is RightsTier.T1_REDISTRIBUTABLE

    # The fetch leg must now be in the compliance trace.
    c = connect_write(db_path, purpose="trace-check")
    try:
        events = trace(c, arxiv_id)
        fetch_legs = [e for e in events if e.kind == ARXIV_FETCH]
        assert len(fetch_legs) == 1, (
            f"expected exactly one arxiv.fetch leg after the real store path; "
            f"got trace kinds {[e.kind for e in events]}"
        )
        leg = fetch_legs[0]
        assert leg.document_id == arxiv_doc_id(arxiv_id)
        # §9.0: provenance refs only, never a body.
        assert leg.detail["sha256"] == fetched.sha256
        assert leg.detail["byte_size"] == fetched.byte_size
        assert leg.detail["source_url"] == fetched.source_url
        assert "raw_text" not in leg.detail and "body" not in leg.detail
    finally:
        c.close()


def test_refused_t3_store_emits_no_fetch_leg(db_path):
    """A T3 (arXiv-default) row is REFUSED by the store path (no body written), so
    NO fetch leg is emitted — the fetch leg tracks a genuinely-stored T1 body, not
    an attempt. This guards against the audit over-firing on a non-store."""
    from acquisition.arxiv.oai_persist import persist_oai_records
    from acquisition.arxiv.pdf_fetch import FetchedPdf
    from acquisition.arxiv.store import store_pdf_for_arxiv_row
    from acquisition.books.public_domain import text_to_pdf
    from substrate.schemas.documents import ArxivOaiRecord

    import hashlib

    arxiv_id = "2402.30001"
    arxiv_default = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"
    persist_oai_records(
        [ArxivOaiRecord(
            arxiv_id=arxiv_id, datestamp="2024-02-15", license_uri=arxiv_default,
            title="A Gated Paper", categories=("cs.AI",),
        )],
        db_path=db_path,
    )
    pdf_bytes = text_to_pdf("body " * 200, title="Gated")
    fetched = FetchedPdf(
        arxiv_id=arxiv_id, source_url=f"https://arxiv.org/pdf/{arxiv_id}",
        content=pdf_bytes, sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        byte_size=len(pdf_bytes),
    )
    outcome = store_pdf_for_arxiv_row(fetched, db_path=db_path, embedder=_StubEmbedder())
    assert outcome.status == "refused"  # T3 — nothing stored

    c = connect_write(db_path, purpose="trace-check")
    try:
        assert [e for e in trace(c, arxiv_id) if e.kind == ARXIV_FETCH] == []
    finally:
        c.close()


# ── (f) the FETCH leg fires in the REAL PRODUCTION CLI path (M4 round-3) ─────


def _arxiv_feed(arxiv_id: str, license_uri: str) -> bytes:
    lic = f"<arxiv:license>{license_uri}</arxiv:license>" if license_uri else ""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom"\n'
        '      xmlns:arxiv="http://arxiv.org/schemas/atom">\n'
        "  <entry>\n"
        f"    <id>http://arxiv.org/abs/{arxiv_id}v1</id>\n"
        "    <updated>2024-02-15T12:00:00Z</updated>\n"
        "    <published>2024-02-05T09:15:33Z</published>\n"
        f"    <title>Paper {arxiv_id}</title>\n"
        f"    <summary>Abstract for {arxiv_id}.</summary>\n"
        "    <author><name>Jane Doe</name></author>\n"
        '    <arxiv:primary_category term="cs.AI"/>\n'
        f"    {lic}\n"
        "  </entry>\n"
        "</feed>\n"
    ).encode("utf-8")


def test_fetch_leg_fires_in_the_real_ingest_paper_with_rights_path(db_path):
    """BLOCKING M4 (round-3) — prove the ``arxiv.fetch`` leg appears in
    ``trace(con, arxiv_id)`` after the REAL PRODUCTION on-demand T1 path runs:
    ``ingest_paper_with_rights`` (the entry point BOTH operator CLIs call) →
    ``ingest_servable_book``. This is the path that actually fetches arXiv bytes +
    lands a servable T1 body in production.

    The round-2 fetch-audit lived in ``store_pdf_for_arxiv_row``, which has ZERO
    production callers (CLIs never run it) — so a real on-demand T1 acquisition
    produced an EMPTY fetch trace. This test drives the genuine production entry
    point (NOT ``store_pdf_for_arxiv_row``) and asserts the fetch leg landed.

    RED-THEN-GREEN AT THE PRODUCTION/CALLER LEVEL (verified): remove the
    ``_record_fetch_audit(...)`` call from
    ``acquisition/arxiv/adapter.py::ingest_paper_with_rights`` and this test goes
    RED (the real ingest produces an empty fetch trace); restoring it makes it
    GREEN."""
    import hashlib

    from acquisition.arxiv.adapter import ingest_paper_with_rights
    from acquisition.arxiv.client import _parse_response
    from acquisition.books.public_domain import text_to_pdf

    arxiv_id = "2402.40001"
    cc_by = "http://creativecommons.org/licenses/by/4.0/"
    paper = _parse_response(_arxiv_feed(arxiv_id, cc_by))[0]

    pdf_text = "This is a synthetic open-access academic paper body. " * 60
    pdf_bytes = text_to_pdf(pdf_text, title="Open Paper")

    # The REAL production entry point (NOT store_pdf_for_arxiv_row). pdf_bytes is
    # injected exactly as the CLI's fixture path / a real fetch would supply it.
    result = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        pdf_bytes=pdf_bytes,
        db_path=db_path,
        embedder=_StubEmbedder(),
    )
    assert result.servable_full_text is True  # CC-BY → servable T1

    c = connect_write(db_path, purpose="trace-check")
    try:
        events = trace(c, arxiv_id)
        fetch_legs = [e for e in events if e.kind == ARXIV_FETCH]
        assert len(fetch_legs) == 1, (
            f"expected exactly one arxiv.fetch leg after the real "
            f"ingest_paper_with_rights path; got trace kinds {[e.kind for e in events]}"
        )
        leg = fetch_legs[0]
        assert leg.arxiv_id == arxiv_id
        assert leg.document_id == result.document_id
        # §9.0: provenance refs only, never a body.
        assert leg.detail["sha256"] == hashlib.sha256(pdf_bytes).hexdigest()
        assert leg.detail["byte_size"] == len(pdf_bytes)
        assert leg.detail["source_url"] == paper.pdf_url
        assert "raw_text" not in leg.detail and "body" not in leg.detail
    finally:
        c.close()


def test_gated_ingest_paper_with_rights_emits_no_fetch_leg(db_path):
    """A gated (arXiv-default-terms) paper run through the REAL production path is
    NOT servable, so NO fetch leg is emitted — the production fetch leg tracks a
    genuinely-stored servable T1 body, never a gated attempt."""
    from acquisition.arxiv.adapter import ingest_paper_with_rights
    from acquisition.arxiv.client import _parse_response
    from acquisition.books.public_domain import text_to_pdf

    arxiv_id = "2402.40002"
    arxiv_default = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"
    paper = _parse_response(_arxiv_feed(arxiv_id, arxiv_default))[0]
    pdf_bytes = text_to_pdf("gated body text " * 80, title="Gated")

    result = ingest_paper_with_rights(
        paper,
        investigation_id="inv-test",
        pdf_bytes=pdf_bytes,
        db_path=db_path,
        embedder=_StubEmbedder(),
    )
    assert result.servable_full_text is False  # gated — not servable

    c = connect_write(db_path, purpose="trace-check")
    try:
        assert [e for e in trace(c, arxiv_id) if e.kind == ARXIV_FETCH] == []
    finally:
        c.close()


# ── (g) the FETCH leg fires when the OPEN-ACCESS channel lands an arXiv body ──


def test_oa_ingest_of_arxiv_mirrored_work_emits_the_fetch_leg(db_path):
    """BLOCKING M4 (round-4) — when the OA channel lands an arXiv-HOST servable
    body (``ingest_oa_item`` with ``pdf_url = arxiv.org/pdf/<id>``), the
    ``arxiv.fetch`` leg appears in ``trace(con, arxiv_id)`` — the same compliance
    leg the native adapter path records, reached via the OA resolver.

    An OA ingest of an arXiv-mirrored work fetches an arXiv host and stores a
    servable body; without this leg the trace is blind to OA-sourced arXiv
    fetches. The arxiv_id is derived from the arxiv.org/pdf URL.

    RED-THEN-GREEN AT THE CALLER (verified): remove the
    ``_record_oa_arxiv_fetch_audit(...)`` call from
    ``acquisition/openaccess/ingest.py::ingest_oa_item`` and this test goes RED
    (the OA ingest of an arXiv work leaves an empty fetch trace); restoring it
    makes it GREEN."""
    import hashlib

    from acquisition.books.public_domain import text_to_pdf
    from acquisition.openaccess.ingest import build_license_basis, ingest_oa_item
    from acquisition.openaccess.licenses import resolve_oa_license

    arxiv_id = "2403.30001"
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    cc_by = "http://creativecommons.org/licenses/by/4.0/"
    resolution = resolve_oa_license(cc_by)
    assert resolution.redistributable is True  # CC-BY → servable

    pdf_text = "This is a synthetic open-access arXiv-mirrored paper body. " * 60
    pdf_bytes = text_to_pdf(pdf_text, title="OA arXiv Paper")
    basis = build_license_basis(
        resolution, source="OpenAlex best-OA (arXiv-mirrored)", how="per best_oa_location.license"
    )

    result = ingest_oa_item(
        investigation_id="inv-test",
        doi="10.48550/arXiv." + arxiv_id,
        pdf_url=pdf_url,
        resolution=resolution,
        license_basis=basis,
        pdf_bytes=pdf_bytes,
        db_path=db_path,
        embedder=_StubEmbedder(),
    )
    assert result.servable_full_text is True  # CC-BY → servable T1

    c = connect_write(db_path, purpose="trace-check")
    try:
        events = trace(c, arxiv_id)
        fetch_legs = [e for e in events if e.kind == ARXIV_FETCH]
        assert len(fetch_legs) == 1, (
            f"expected exactly one arxiv.fetch leg after the OA ingest of an "
            f"arXiv-mirrored work; got trace kinds {[e.kind for e in events]}"
        )
        leg = fetch_legs[0]
        assert leg.arxiv_id == arxiv_id
        assert leg.document_id == result.document_id
        # §9.0: provenance refs only, never a body.
        assert leg.detail["sha256"] == hashlib.sha256(pdf_bytes).hexdigest()
        assert leg.detail["byte_size"] == len(pdf_bytes)
        assert leg.detail["source_url"] == pdf_url
        assert leg.detail["via"] == "openaccess"
        assert "raw_text" not in leg.detail and "body" not in leg.detail
    finally:
        c.close()


def test_non_arxiv_oa_ingest_emits_no_arxiv_fetch_leg(db_path):
    """A NON-arXiv OA ingest (a publisher-host PDF) derives no arxiv_id, so it
    emits NO arXiv fetch leg — the OA fetch leg is keyed strictly on landing an
    arXiv host, not on the OA channel firing. Proves no spurious arXiv legs from
    ordinary (publisher/PMC) OA ingests."""
    from acquisition.books.public_domain import text_to_pdf
    from acquisition.openaccess.ingest import build_license_basis, ingest_oa_item
    from acquisition.openaccess.licenses import resolve_oa_license

    pdf_url = "https://journals.plos.org/plosone/article/file?id=10.1371/x&type=printable"
    cc_by = "http://creativecommons.org/licenses/by/4.0/"
    resolution = resolve_oa_license(cc_by)
    pdf_bytes = text_to_pdf("A publisher-hosted open-access paper body. " * 60, title="PLOS")
    basis = build_license_basis(resolution, source="Unpaywall", how="per best_oa_location.license")

    result = ingest_oa_item(
        investigation_id="inv-test",
        doi="10.1371/journal.pone.0000001",
        pdf_url=pdf_url,
        resolution=resolution,
        license_basis=basis,
        pdf_bytes=pdf_bytes,
        db_path=db_path,
        embedder=_StubEmbedder(),
    )
    assert result.servable_full_text is True  # servable — but NOT an arXiv host

    # The OA doc id is what the publisher ingest produced; no arxiv_id was derived,
    # so NO arXiv audit row exists for any plausible arXiv id. Assert the trace for
    # the (non-existent) arXiv id derived from this publisher URL is empty.
    c = connect_write(db_path, purpose="trace-check")
    try:
        # A publisher URL yields no arxiv_id; there is nothing to key a trace on.
        # Assert the audit table holds no arxiv.fetch row referencing this doc.
        rows = c.execute(
            "SELECT COUNT(*) FROM arxiv_audit WHERE document_id = ? AND kind = ?",
            [result.document_id, ARXIV_FETCH],
        ).fetchone()
        assert rows[0] == 0, (
            "a non-arXiv OA ingest wrongly emitted an arxiv.fetch leg"
        )
    finally:
        c.close()
