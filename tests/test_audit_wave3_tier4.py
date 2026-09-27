"""Audit wave 3, Tier 4 — seven silent-degradation / producer-satisfied gates.

Each test names the finding it closes and pins BOTH directions: the seeded
red (what used to pass silently now surfaces) and a control (the legitimate
shape still passes). Every repair was mutation-tested by restoring the
pre-fix file and watching the seeded-red case fail.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from decimal import Decimal

import duckdb
import pytest

# ── #17 acu_meter: a dropped wall-time charge is logged, never silent ──


def test_17_dropped_wall_topup_is_logged_not_silent(monkeypatch, caplog):
    from runtime import db_lock
    from substrate.compute_capacity import acu_meter

    def _timeout(*_a, **_k):
        raise db_lock.WriteLockTimeout("busy")

    monkeypatch.setattr(db_lock, "connect_write", _timeout)
    with caplog.at_level(logging.WARNING, logger="antiek.compute_capacity.acu_meter"):
        charged = acu_meter.maybe_commit_investigation_wall_topup(
            "inv-dropped", db_path="/nonexistent/never-opened.duckdb", wall_seconds=900.0
        )
    assert charged == 0  # the contract (never raises) is kept …
    dropped = [r for r in caplog.records if "wall-topup DROPPED" in r.getMessage()]
    assert dropped, caplog.text  # … but the drop is no longer invisible
    assert "inv-dropped" in dropped[0].getMessage()
    assert "UNDER-counted" in dropped[0].getMessage()


def test_17_any_other_failure_is_logged_with_its_type(monkeypatch, caplog):
    from runtime import db_lock
    from substrate.compute_capacity import acu_meter

    def _boom(*_a, **_k):
        raise OSError("disk gone")

    monkeypatch.setattr(db_lock, "connect_write", _boom)
    with caplog.at_level(logging.WARNING, logger="antiek.compute_capacity.acu_meter"):
        assert acu_meter.maybe_commit_investigation_wall_topup("inv-x", db_path="/x") == 0
    assert any("OSError" in r.getMessage() and "inv-x" in r.getMessage() for r in caplog.records)


# ── #18 lineup_override: a corrupt operator lineup is logged, once per file version ──


@pytest.fixture
def lineup_path(monkeypatch):
    d = tempfile.mkdtemp(prefix="lineup-")
    p = os.path.join(d, "lineup.json")
    monkeypatch.setenv("ANTIEK_LINEUP_PATH", p)
    from substrate.dispatch import lineup_override

    lineup_override._registry_cache.clear()
    yield p
    shutil.rmtree(d, ignore_errors=True)


def test_18_corrupt_lineup_json_is_logged_and_ignored(lineup_path, caplog):
    from substrate.dispatch import lineup_override

    with open(lineup_path, "w", encoding="utf-8") as fh:
        fh.write("{ this is not json")
    with caplog.at_level(logging.WARNING, logger="antiek.dispatch.lineup_override"):
        assert lineup_override._load_registry() == {}
    msgs = [r.getMessage() for r in caplog.records]
    assert any("unreadable" in m and "IGNORED" in m for m in msgs), msgs
    # Once per file version: a second read of the same bytes hits the cache.
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="antiek.dispatch.lineup_override"):
        assert lineup_override._load_registry() == {}
    assert not caplog.records


def test_18_non_object_lineup_is_logged(lineup_path, caplog):
    from substrate.dispatch import lineup_override

    with open(lineup_path, "w", encoding="utf-8") as fh:
        json.dump([1, 2, 3], fh)
    with caplog.at_level(logging.WARNING, logger="antiek.dispatch.lineup_override"):
        assert lineup_override._load_registry() == {}
    assert any("not a JSON object" in r.getMessage() for r in caplog.records)


def test_18_control_valid_lineup_logs_nothing(lineup_path, caplog):
    from substrate.dispatch import lineup_override

    with open(lineup_path, "w", encoding="utf-8") as fh:
        json.dump({"general": {}, "advanced": {}}, fh)
    with caplog.at_level(logging.WARNING, logger="antiek.dispatch.lineup_override"):
        assert lineup_override._load_registry() == {"general": {}, "advanced": {}}
    assert not caplog.records


def test_18_control_missing_file_is_no_assignment_and_silent(monkeypatch, caplog):
    from substrate.dispatch import lineup_override

    monkeypatch.setenv("ANTIEK_LINEUP_PATH", "/nonexistent/dir/lineup.json")
    lineup_override._registry_cache.clear()
    with caplog.at_level(logging.WARNING, logger="antiek.dispatch.lineup_override"):
        assert lineup_override._load_registry() == {}
    assert not caplog.records


# ── #5 deliverable rights: a cited source whose rights cannot be read is withheld ──


@pytest.fixture
def refs_db():
    from runtime.db_lock import connect_write
    from substrate.graph.schema import init_database_at_path

    tmp = tempfile.mkdtemp(prefix="tier4-refs-")
    db_path = os.path.join(tmp, "graph.duckdb")
    init_database_at_path(db_path)
    con = connect_write(db_path, purpose="tier4-seed")
    try:
        con.execute(
            "INSERT INTO documents (document_id, source_tier, document_type, title, content_class) "
            "VALUES ('doc-null-class', 2, 'paper', 'Unclassed Source', NULL)"
        )
        con.execute(
            "INSERT INTO documents (document_id, source_tier, document_type, title, content_class) "
            "VALUES ('doc-pd', 2, 'paper', 'On Liberty', 'public_domain')"
        )
        for node_id, doc_id in (
            ("claim-missing-doc", "doc-that-does-not-exist"),
            ("claim-null-class", "doc-null-class"),
            ("claim-pd", "doc-pd"),
        ):
            con.execute(
                "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
                "VALUES (?, 'a claim', 'claim', 'depth', ?)",
                [node_id, json.dumps({"source_document_id": doc_id})],
            )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES ('question-orphan', 'What is liberty?', 'question', 'depth', NULL)"
        )
    finally:
        con.close()
    yield db_path
    shutil.rmtree(tmp, ignore_errors=True)


def test_5_missing_source_row_resolves_to_the_gated_default(refs_db):
    from services.html_projection.resolvers.substrate_refs import resolve_refs
    from substrate.constants import GATED_DEFAULT_CONTENT_CLASS

    out = resolve_refs(["claim-missing-doc", "claim-null-class", "claim-pd", "question-orphan"], db_path=refs_db)
    assert out["claim-missing-doc"].content_class == GATED_DEFAULT_CONTENT_CLASS
    assert out["claim-missing-doc"].servable is False
    assert out["claim-null-class"].content_class == GATED_DEFAULT_CONTENT_CLASS
    assert out["claim-null-class"].servable is False
    # Controls: a classed source resolves as before; a source-less question
    # keeps the documented None (it names no source, so nothing degraded).
    assert out["claim-pd"].content_class == "public_domain"
    assert out["question-orphan"].content_class is None


def test_5_deliverable_block_with_a_source_but_no_class_is_not_servable():
    from services.html_projection.adapters.deliverable import DeliverableBlock

    degraded = DeliverableBlock(
        block_kind="claim", text="quoted", content_class=None, source_document_id="doc-x"
    )
    assert degraded.servable is False
    own = DeliverableBlock(block_kind="synthesized", text="operator prose", content_class=None)
    assert own.servable is True
    assert DeliverableBlock(block_kind="claim", text="q", content_class="public_domain",
                            source_document_id="doc-x").servable is True


# ── #6 demand gate: a round-trip with no actor is not organic demand ──


def test_6_roundtrip_event_carries_the_importer():
    from services.demand_gate.events import assert_no_content
    from services.demand_gate.roundtrip_detector import ExportRegistry, classify_roundtrip

    reg = ExportRegistry()
    doc = {"type": "doc", "content": [{"type": "paragraph"}]}
    reg.record_export("doc-1", doc, exporter_id="tester-1")
    rt = classify_roundtrip("doc-1", doc, reg, user_id="reader-7")
    assert rt.is_roundtrip and rt.event is not None
    assert rt.event["user_id"] == "reader-7"
    assert_no_content(rt.event)  # still within the privacy allowlist


def test_6_verdict_excludes_operator_and_unknown_actor():
    from datetime import UTC, datetime, timedelta

    from services.demand_gate.analysis import EXPORT_OFFERED, compute_verdict
    from services.demand_gate.roundtrip_detector import ROUNDTRIP_EVENT_TYPE

    start = datetime(2026, 10, 1, tzinfo=UTC)
    at = (start + timedelta(days=1)).isoformat()

    def ev(uid):
        e = {"action_type": ROUNDTRIP_EVENT_TYPE, "document_id": "d", "classification": "traveled_and_changed",
             "exported_by": ["reader-3"], "emitted_at": at}
        if uid is not ...:
            e["user_id"] = uid
        return e

    op = "operator-1"
    testers = frozenset({"reader-2", "reader-3", "reader-4", "reader-5", "reader-6"})
    offered = {"action_type": EXPORT_OFFERED, "user_id": "reader-2", "emitted_at": at}

    def organic(e):
        return compute_verdict(
            [offered, e], operator_user_id=op, tester_ids=testers,
            window_start=start, window_end=start + timedelta(days=14),
        ).counts["organic_roundtrip"]

    assert organic(ev("reader-2")) == 1
    assert organic(ev(op)) == 0
    # The detector's own pre-fix event: no user_id key at all. Not admissible.
    assert organic(ev(...)) == 0
    assert organic(ev(None)) == 0


# ── #13 / #14 books: born classified; a skipped ingest is a skip ──


class _StubEmbedder:
    dimension = 16

    def encode(self, text: str) -> list[float]:
        v = [0.0] * 16
        v[abs(hash(text)) % 16] = 1.0
        return v


@pytest.fixture
def temp_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="tier4-books-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    from substrate.graph import ensure_initialized

    ensure_initialized(db_path)
    yield db_path
    shutil.rmtree(tmpdir, ignore_errors=True)


def _manifest(body: str) -> dict:
    return {
        "schema_version": "opt_in/1",
        "publisher": {
            "publisher_id": "mit-press",
            "display_name": "MIT Press",
            "legal_contact_email": "legal@mitpress.edu",
        },
        "works": [
            {
                "title": "A Generic Title",
                "author": "A. Author",
                "isbn": "978-0-262-04630-5",
                "doi": "10.7551/mitpress/00009.001.0001",
                "body_text": body,
                "grant": {
                    "rights_holder": "MIT Press",
                    "scope": "per_work",
                    "granted_at": "2026-05-30",
                    "statement": "MIT Press grants Antiek the right to serve this work.",
                },
            }
        ],
    }


_LONG_BODY = "This is a synthetic opt-in catalog work body used as an ingest fixture. " * 30
_TINY_BODY = "Too short to ingest."


def _documents_row(db_path: str, document_id: str):
    con = duckdb.connect(db_path, read_only=True)
    try:
        return con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?", [document_id]
        ).fetchone()
    finally:
        con.close()


def test_13_document_is_born_classified_even_if_registration_never_runs(temp_db, monkeypatch):
    """The exact defect: chunks + document committed in one transaction with
    content_class NULL, the class stamped in a SECOND transaction that can
    time out. If the second never runs, the row must still be classed."""
    import substrate.books.ingest as books_ingest
    from acquisition.opt_in import intake_manifest, parse_manifest
    from runtime.db_lock import WriteLockTimeout

    def _never(*_a, **_k):
        raise WriteLockTimeout("simulated lock timeout on the registration write")

    monkeypatch.setattr(books_ingest, "register_book", _never)
    # The registration failure surfaces (loudly) to the caller …
    with pytest.raises(WriteLockTimeout):
        intake_manifest(parse_manifest(_manifest(_LONG_BODY)), db_path=temp_db,
                        embedder=_StubEmbedder(), accrual_usd=Decimal("1"))
    # … but the row the FIRST transaction left behind is CLASSED, never
    # NULL-and-public.
    con = duckdb.connect(temp_db, read_only=True)
    try:
        rows = con.execute("SELECT document_id, content_class FROM documents").fetchall()
    finally:
        con.close()
    assert rows, "the first transaction did commit a documents row"
    assert all(cc is not None for _, cc in rows), rows
    assert all(cc == "opt_in_licensed" for _, cc in rows), rows


def test_13_resolve_content_class_is_the_chokepoint_rule():
    from substrate.constants import GATED_DEFAULT_CONTENT_CLASS
    from substrate.rights.register import resolve_content_class

    assert resolve_content_class(None) == GATED_DEFAULT_CONTENT_CLASS
    assert resolve_content_class("public_domain") == "public_domain"
    with pytest.raises(ValueError, match="unrecognised content_class"):
        resolve_content_class("pubilc_domain")


def test_14_skipped_ingest_is_a_skip_not_a_servable_phantom(temp_db):
    from acquisition.opt_in import intake_manifest, parse_manifest

    result = intake_manifest(parse_manifest(_manifest(_TINY_BODY)), db_path=temp_db,
                             embedder=_StubEmbedder(), accrual_usd=Decimal("1"))
    (outcome,) = result.outcomes
    assert outcome.skipped_reason is not None and "low_word_count" in outcome.skipped_reason
    assert outcome.servable is False
    assert outcome.accrued is False
    assert outcome.document_id is None  # no row exists to point at
    assert result.summary.skipped_count == 1
    assert result.summary.servable_count == 0
    con = duckdb.connect(temp_db, read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        escrow = con.execute("SELECT count(*) FROM ip_holders WHERE escrow_balance_usd > 0").fetchone()[0]
    finally:
        con.close()
    assert escrow == 0


def test_14_ingest_servable_book_skip_result_is_not_servable(temp_db, monkeypatch):
    from acquisition.books import adapter

    calls = {}

    class _Skipped:
        skipped_reason = "low_word_count"
        document_id = "doc-phantom"

    def _skip(*_a, **kw):
        calls.update(kw)
        return _Skipped()

    monkeypatch.setattr(adapter, "ingest_pdf", _skip)
    res = adapter.ingest_servable_book(b"%PDF-1.4 tiny", investigation_id="inv",
                                       content_class="public_domain", db_path=temp_db)
    assert res.servable_full_text is False
    assert res.ingest.skipped_reason == "low_word_count"
    # and the class reached ingest_pdf already resolved (born classified)
    assert calls["content_class"] == "public_domain"


def test_14_control_long_body_still_servable_and_accrues(temp_db):
    from acquisition.opt_in import intake_manifest, parse_manifest

    result = intake_manifest(parse_manifest(_manifest(_LONG_BODY)), db_path=temp_db,
                             embedder=_StubEmbedder(), accrual_usd=Decimal("1"))
    (outcome,) = result.outcomes
    assert outcome.skipped_reason is None
    assert outcome.servable is True and outcome.accrued is True
    assert _documents_row(temp_db, outcome.document_id) == ("opt_in_licensed",)


# ── #15 corpus quality: null-author admissions are counted, not silent ──


def test_15_null_author_admission_is_recorded_on_the_check():
    from acquisition.corpus_quality import check_metadata_completeness

    r = check_metadata_completeness(title="T", author=None, source_id="s",
                                    allow_null_author_reason="open-access record exposes no author at discovery")
    assert r.kind.value == "pass"
    assert r.admitted_by_exception == "author null: open-access record exposes no author at discovery"
    assert check_metadata_completeness(title="T", author="A", source_id="s").admitted_by_exception is None
    assert check_metadata_completeness(title="T", author=None, source_id="s").kind.value == "fail"


def test_15_run_report_counts_escape_hatch_admissions():
    from acquisition.corpus_quality import aggregate_verdicts, assess_corpus_quality

    reason = "open-access record exposes no author at discovery"
    verdicts = [
        assess_corpus_quality("", title="A", author=None, source_id="1",
                              allow_null_author_reason=reason, assess_body=False),
        assess_corpus_quality("", title="B", author=None, source_id="2",
                              allow_null_author_reason=reason, assess_body=False),
        assess_corpus_quality("", title="C", author="Someone", source_id="3", assess_body=False),
        assess_corpus_quality("", title=None, author="X", source_id="4", assess_body=False),
    ]
    report = aggregate_verdicts(verdicts)
    assert (report.total, report.passed, report.rejected) == (4, 3, 1)
    assert report.admitted_by_exception == 2
    assert report.exception_reasons == ((f"author null: {reason}", 2),)
    text = report.render()
    assert "2 of the 3 passed only through an escape hatch" in text
    assert f"2 x author null: {reason}" in text
