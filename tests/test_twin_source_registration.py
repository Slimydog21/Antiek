from __future__ import annotations

import inspect
import json
import sqlite3

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_document, update_document_gate_columns
from substrate.graph.schema import init_database
from substrate.twin_note_taker import MAX_CONTENT_CHARS
from substrate.twin_recursion import (
    TwinRecursionLedger,
    TwinSourceEnvelope,
    TwinSourceEnvelopeError,
    backfill_twin_source_envelopes,
    project_twin_sources,
    verify_twin_source_envelopes,
)
from substrate.twin_recursion.segmentation_ledger import TwinSegmentationLedger


@pytest.fixture
def graph(tmp_path):
    path = str(tmp_path / "graph.duckdb")
    con = connect_write(path, purpose="test_twin_source_registration")
    init_database(con)
    try:
        yield con
    finally:
        con.close()


def _insert_body(
    graph,
    *,
    document_id: str = "doc-1",
    owner: str = "acct",
    body: str = "Substantive canonical information body for recursive notes.",
):
    insert_document(
        graph,
        document_id=document_id,
        source_tier=2,
        document_type="research",
        title="Canonical title",
        raw_text=body,
        owner_user_id=owner,
    )


def test_fresh_insert_stamps_exact_eligible_envelope_in_document_row(graph):
    _insert_body(graph)
    row = graph.execute(
        "SELECT twin_source_envelope FROM documents WHERE document_id='doc-1'"
    ).fetchone()
    envelope = TwinSourceEnvelope.from_json(row[0])
    assert envelope.status == "eligible"
    assert envelope.account_id == "acct"
    assert envelope.document_id == "doc-1" and envelope.source_hash
    assert envelope.source_event_id.startswith("evt-twin-source-")
    assert "Substantive canonical" not in row[0]
    assert verify_twin_source_envelopes(graph) == (envelope,)


def test_document_and_declaration_share_one_insert_and_rollback(graph):
    source = inspect.getsource(insert_document)
    assert "owner_user_id, twin_source_envelope)" in source
    graph.execute("BEGIN")
    _insert_body(graph, document_id="rolled-back")
    graph.execute("ROLLBACK")
    assert graph.execute(
        "SELECT count(*) FROM documents WHERE document_id='rolled-back'"
    ).fetchone() == (0,)


def test_metadata_only_is_explicit_and_not_fabricated_as_eligible(graph):
    insert_document(
        graph,
        document_id="metadata",
        source_tier=3,
        document_type="web_article",
        title="Metadata only",
        owner_user_id="acct",
    )
    envelope = verify_twin_source_envelopes(graph)[0]
    assert envelope.status == "metadata_only"
    assert envelope.reason == "no_substantive_body"
    assert envelope.source_hash is None


def test_short_nonempty_body_requires_enrichment_not_metadata_exclusion(graph):
    _insert_body(graph, body="short")
    envelope = verify_twin_source_envelopes(graph)[0]
    assert envelope.status == "requires_enrichment"
    assert envelope.reason == "body_below_materializer_floor"


def test_legacy_multimedia_twin_requires_real_binding_and_never_recurses(graph, tmp_path):
    insert_document(
        graph,
        document_id="legacy-twin",
        source_tier=1,
        document_type="multimedia_twin",
        title="Twin notes",
        raw_text="A legacy twin body that must not recursively request another twin.",
        owner_user_id="acct",
    )
    envelope = verify_twin_source_envelopes(graph)[0]
    assert envelope.status == "requires_binding" and envelope.source_hash is None
    report = project_twin_sources(
        graph,
        TwinRecursionLedger(tmp_path / "twins.sqlite"),
        TwinSegmentationLedger(tmp_path / "segments.sqlite"),
        account_id="acct",
    )
    assert report.requires_binding == 1 and report.registered == 0
    assert report.verdict == "partial"


def test_oversized_body_projects_durable_segments_without_false_completion(graph, tmp_path):
    body = "x" * (MAX_CONTENT_CHARS + 1)
    _insert_body(graph, body=body)
    envelope = verify_twin_source_envelopes(graph)[0]
    assert envelope.status == "requires_segmentation"
    assert envelope.reason == "body_exceeds_materializer_limit"
    assert envelope.source_hash is None
    segments = TwinSegmentationLedger(tmp_path / "segments.sqlite")
    report = project_twin_sources(
        graph, TwinRecursionLedger(tmp_path / "twins.sqlite"), segments, account_id="acct"
    )
    assert report.segmentation_registered == 1 and report.verdict == "partial"
    with sqlite3.connect(tmp_path / "segments.sqlite") as con:
        parent_hash = con.execute(
            "SELECT parent_source_hash FROM segmentation_manifests"
        ).fetchone()[0]
    snapshot = segments.get("acct", "doc-1", parent_hash)
    assert snapshot.pending_segments >= 2 and not snapshot.parent_ready


def test_direct_sql_bypass_is_detected_and_locked_backfill_is_idempotent(graph):
    graph.execute(
        "INSERT INTO documents (document_id,source_tier,document_type,title,raw_text,owner_user_id) "
        "VALUES ('bypass',2,'paper','Paper','A body long enough to become a twin source.','acct')"
    )
    with pytest.raises(TwinSourceEnvelopeError, match="lacks"):
        verify_twin_source_envelopes(graph)
    assert backfill_twin_source_envelopes(graph) == 1
    assert backfill_twin_source_envelopes(graph) == 0
    assert verify_twin_source_envelopes(graph)[0].document_id == "bypass"


def test_v20_initialization_backfills_legacy_rows_before_schema_is_ready(graph):
    graph.execute(
        "INSERT INTO documents (document_id,source_tier,document_type,title,raw_text,owner_user_id) "
        "VALUES ('upgrade',2,'paper','Paper','A legacy body that needs migration.','acct')"
    )
    init_database(graph)
    assert verify_twin_source_envelopes(graph)[0].document_id == "upgrade"


def test_backfill_rolls_back_every_row_when_one_legacy_asset_is_invalid(graph):
    graph.execute(
        "INSERT INTO documents (document_id,source_tier,document_type,title,raw_text,owner_user_id) "
        "VALUES ('a-valid',2,'paper','Paper','A body long enough to become a twin source.','acct')"
    )
    invalid_id = "z" * 300
    graph.execute(
        "INSERT INTO documents (document_id,source_tier,document_type,title,raw_text,owner_user_id) "
        "VALUES (?,2,'paper','Paper','A body long enough to become a twin source.','acct')",
        [invalid_id],
    )
    with pytest.raises(ValueError, match="asset_id"):
        backfill_twin_source_envelopes(graph)
    assert graph.execute(
        "SELECT count(*) FROM documents WHERE twin_source_envelope IS NOT NULL"
    ).fetchone() == (0,)


def test_ignore_replay_repairs_legacy_null_from_stored_not_caller_bytes(graph):
    graph.execute(
        "INSERT INTO documents (document_id,source_tier,document_type,title,raw_text,owner_user_id) "
        "VALUES ('legacy',2,'paper','Stored','Stored body long enough for exact declaration.','acct')"
    )
    insert_document(
        graph,
        document_id="legacy",
        source_tier=5,
        document_type="different-caller-value",
        title="Different caller title",
        raw_text="Different caller body that must not become authority.",
        owner_user_id="other",
        on_conflict="ignore",
    )
    envelope = verify_twin_source_envelopes(graph)[0]
    assert envelope.account_id == "acct"
    assert envelope.title == "Stored"


def test_takedown_purges_body_without_leaving_envelope_copy(graph):
    body = "Copyrighted body bytes that must disappear during a legal takedown."
    _insert_body(graph, body=body)
    update_document_gate_columns(graph, "doc-1", null_raw_text=True)
    raw_text, envelope_json = graph.execute(
        "SELECT raw_text,twin_source_envelope FROM documents WHERE document_id='doc-1'"
    ).fetchone()
    assert raw_text is None and body not in envelope_json
    envelope = verify_twin_source_envelopes(graph)[0]
    assert envelope.status == "metadata_only" and envelope.body_sha256 is None


def test_document_drift_and_canonical_looking_substitution_fail_closed(graph):
    _insert_body(graph)
    graph.execute(
        "UPDATE documents SET title='Changed after declaration' WHERE document_id='doc-1'"
    )
    with pytest.raises(TwinSourceEnvelopeError, match="conflicts"):
        verify_twin_source_envelopes(graph)
    graph.execute("UPDATE documents SET title='Canonical title' WHERE document_id='doc-1'")
    raw = json.loads(
        graph.execute(
            "SELECT twin_source_envelope FROM documents WHERE document_id='doc-1'"
        ).fetchone()[0]
    )
    raw["account_id"] = "other"
    graph.execute(
        "UPDATE documents SET twin_source_envelope=? WHERE document_id='doc-1'",
        [json.dumps(raw, sort_keys=True, separators=(",", ":"))],
    )
    with pytest.raises(TwinSourceEnvelopeError, match="conflicts"):
        verify_twin_source_envelopes(graph)


def test_projector_is_account_scoped_restart_safe_and_reports_real_completion(graph, tmp_path):
    _insert_body(graph, document_id="a", owner="acct")
    _insert_body(graph, document_id="b", owner="other")
    insert_document(
        graph,
        document_id="meta",
        source_tier=2,
        document_type="paper",
        title="Metadata",
        owner_user_id="acct",
    )
    ledger_path = tmp_path / "twins.sqlite"
    segment_path = tmp_path / "segments.sqlite"
    first = project_twin_sources(
        graph,
        TwinRecursionLedger(ledger_path),
        TwinSegmentationLedger(segment_path),
        account_id="acct",
    )
    second = project_twin_sources(
        graph,
        TwinRecursionLedger(ledger_path),
        TwinSegmentationLedger(segment_path),
        account_id="acct",
    )
    assert first == second
    assert first.documents == 2 and first.eligible == 1 and first.metadata_only == 1
    assert first.registered == 1 and first.verdict == "partial"
    ledger = TwinRecursionLedger(ledger_path)
    assert ledger.universality_report("acct").twinnable_revisions == 1
    assert ledger.universality_report("other").verdict == "unknown"


def test_foreign_tenant_corruption_does_not_block_scoped_projection(graph, tmp_path):
    _insert_body(graph, document_id="owned", owner="acct")
    _insert_body(graph, document_id="foreign", owner="other")
    graph.execute("UPDATE documents SET twin_source_envelope='{}' WHERE document_id='foreign'")
    report = project_twin_sources(
        graph,
        TwinRecursionLedger(tmp_path / "twins.sqlite"),
        TwinSegmentationLedger(tmp_path / "segments.sqlite"),
        account_id="acct",
    )
    assert report.eligible == 1 and report.registered == 1
    with pytest.raises(TwinSourceEnvelopeError):
        verify_twin_source_envelopes(graph)


def test_raw_duckdb_connection_is_not_registration_authority(tmp_path):
    raw = duckdb.connect(str(tmp_path / "raw.duckdb"))
    with pytest.raises(TypeError, match="LockedConnection"):
        verify_twin_source_envelopes(raw)  # type: ignore[arg-type]
    raw.close()
