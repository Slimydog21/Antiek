from __future__ import annotations

import inspect
import json
import sqlite3

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph.ops import (
    insert_document,
    replace_document_body,
    update_document_gate_columns,
)
from substrate.graph.schema import init_database
from substrate.rights import T3BodyServeError
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
        content_class="personal_reading",
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


def test_restricted_body_cannot_become_model_bound_twin_source(graph):
    insert_document(
        graph,
        document_id="restricted",
        source_tier=3,
        document_type="paper",
        title="Restricted paper",
        raw_text="Licensed body that must remain behind the serving boundary.",
        content_class="restricted_pending_opt_in",
        owner_user_id="acct",
    )
    envelope = verify_twin_source_envelopes(graph)[0]
    assert envelope.status == "metadata_only"
    assert envelope.source_hash is None


def test_rights_failure_precedes_atomic_document_insert(graph):
    with pytest.raises(T3BodyServeError, match="RIGHTS DRIFT"):
        insert_document(
            graph,
            document_id="rights-drift",
            source_tier=3,
            document_type="paper",
            title="Misclassified paper",
            raw_text="Body whose immutable license forbids this classification.",
            metadata={
                "license_uri": "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
                "arxiv_id": "2401.00001",
            },
            content_class="source_declared_open",
            owner_user_id="acct",
        )
    assert graph.execute(
        "SELECT count(*) FROM documents WHERE document_id='rights-drift'",
    ).fetchone() == (0,)


def test_rights_promotion_refreshes_twin_declaration(graph):
    insert_document(
        graph,
        document_id="promoted",
        source_tier=2,
        document_type="paper",
        title="Promoted paper",
        raw_text="A sufficiently long body with newly established open rights.",
        content_class="restricted_pending_opt_in",
        owner_user_id="acct",
    )
    assert verify_twin_source_envelopes(graph)[0].status == "metadata_only"
    update_document_gate_columns(
        graph,
        "promoted",
        content_class="source_declared_open",
        set_content_class=True,
    )
    assert verify_twin_source_envelopes(graph)[0].status == "eligible"


def test_reclassification_of_taken_down_book_keeps_metadata_only_envelope(graph):
    _insert_body(graph, document_id="taken-down")
    graph.execute(
        "INSERT INTO book_assets (document_id,taken_down) VALUES ('taken-down',TRUE)"
    )
    update_document_gate_columns(
        graph,
        "taken-down",
        content_class="source_declared_open",
        set_content_class=True,
    )
    assert verify_twin_source_envelopes(graph)[0].status == "metadata_only"


def test_rejected_rights_promotion_changes_neither_gate_nor_declaration(graph):
    insert_document(
        graph,
        document_id="rejected-promotion",
        source_tier=3,
        document_type="paper",
        title="Restricted paper",
        raw_text="Body whose immutable license remains restrictive.",
        metadata={
            "license_uri": "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
            "arxiv_id": "2401.00002",
        },
        content_class="restricted_pending_opt_in",
        owner_user_id="acct",
    )
    before = graph.execute(
        "SELECT content_class,twin_source_envelope FROM documents "
        "WHERE document_id='rejected-promotion'"
    ).fetchone()
    with pytest.raises(T3BodyServeError, match="RIGHTS DRIFT"):
        update_document_gate_columns(
            graph,
            "rejected-promotion",
            content_class="source_declared_open",
            set_content_class=True,
        )
    after = graph.execute(
        "SELECT content_class,twin_source_envelope FROM documents "
        "WHERE document_id='rejected-promotion'"
    ).fetchone()
    assert after == before


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
        content_class="personal_reading",
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
        "INSERT INTO documents (document_id,source_tier,document_type,title,raw_text,owner_user_id,content_class) "
        "VALUES ('bypass',2,'paper','Paper','A body long enough to become a twin source.','acct','personal_reading')"
    )
    with pytest.raises(TwinSourceEnvelopeError, match="lacks"):
        verify_twin_source_envelopes(graph)
    assert backfill_twin_source_envelopes(graph) == 1
    assert backfill_twin_source_envelopes(graph) == 0
    assert verify_twin_source_envelopes(graph)[0].document_id == "bypass"


def test_v20_initialization_backfills_legacy_rows_before_schema_is_ready(graph):
    graph.execute(
        "INSERT INTO documents (document_id,source_tier,document_type,title,raw_text,owner_user_id,content_class) "
        "VALUES ('upgrade',2,'paper','Paper','A legacy body that needs migration.','acct','personal_reading')"
    )
    init_database(graph)
    assert verify_twin_source_envelopes(graph)[0].document_id == "upgrade"


def test_backfill_rolls_back_every_row_when_one_legacy_asset_is_invalid(graph):
    graph.execute(
        "INSERT INTO documents (document_id,source_tier,document_type,title,raw_text,owner_user_id,content_class) "
        "VALUES ('a-valid',2,'paper','Paper','A body long enough to become a twin source.','acct','personal_reading')"
    )
    invalid_id = "z" * 300
    graph.execute(
        "INSERT INTO documents (document_id,source_tier,document_type,title,raw_text,owner_user_id,content_class) "
        "VALUES (?,2,'paper','Paper','A body long enough to become a twin source.','acct','personal_reading')",
        [invalid_id],
    )
    with pytest.raises(ValueError, match="asset_id"):
        backfill_twin_source_envelopes(graph)
    assert graph.execute(
        "SELECT count(*) FROM documents WHERE twin_source_envelope IS NOT NULL"
    ).fetchone() == (0,)


def test_ignore_replay_repairs_legacy_null_from_stored_not_caller_bytes(graph):
    graph.execute(
        "INSERT INTO documents (document_id,source_tier,document_type,title,raw_text,owner_user_id,content_class) "
        "VALUES ('legacy',2,'paper','Stored','Stored body long enough for exact declaration.','acct','personal_reading')"
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


def test_ignore_replay_rejects_forged_non_null_declaration(graph):
    _insert_body(graph)
    graph.execute("UPDATE documents SET title='Tampered' WHERE document_id='doc-1'")
    with pytest.raises(TwinSourceEnvelopeError, match="conflicts"):
        insert_document(
            graph,
            document_id="doc-1",
            source_tier=2,
            document_type="research",
            on_conflict="ignore",
        )


def test_sanctioned_body_replacement_refreshes_declaration_before_replay(graph):
    _insert_body(graph)
    replacement = "A legitimate revised body with a different canonical hash."
    replace_document_body(graph, "doc-1", raw_text=replacement)
    insert_document(
        graph,
        document_id="doc-1",
        source_tier=2,
        document_type="research",
        on_conflict="ignore",
    )
    envelope = verify_twin_source_envelopes(graph)[0]
    assert envelope.status == "eligible"
    assert envelope.body_sha256 is not None


def test_standalone_gate_update_rolls_back_after_post_update_failure(
    graph, monkeypatch
):
    _insert_body(graph)
    before = graph.execute(
        "SELECT content_class,twin_source_envelope FROM documents WHERE document_id='doc-1'"
    ).fetchone()
    original_execute = graph.execute

    def fail_after_update(query, parameters=None):
        result = original_execute(query, parameters)
        if query.startswith("UPDATE documents SET content_class"):
            raise RuntimeError("synthetic post-update failure")
        return result

    monkeypatch.setattr(graph, "execute", fail_after_update, raising=False)
    with pytest.raises(RuntimeError, match="synthetic post-update"):
        update_document_gate_columns(
            graph,
            "doc-1",
            content_class="source_declared_open",
            set_content_class=True,
        )
    monkeypatch.setattr(graph, "execute", original_execute)
    after = graph.execute(
        "SELECT content_class,twin_source_envelope FROM documents WHERE document_id='doc-1'"
    ).fetchone()
    assert after == before
    assert graph.execute(
        "SELECT count(*) FROM duckdb_indexes() "
        "WHERE index_name='idx_documents_content_class'"
    ).fetchone() == (0,)


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


def test_takedown_class_and_body_change_assigns_envelope_once(graph):
    _insert_body(graph, body="Body removed by the combined takedown mutation.")
    update_document_gate_columns(
        graph,
        "doc-1",
        content_class="taken_down",
        set_content_class=True,
        null_raw_text=True,
    )
    raw_text, content_class = graph.execute(
        "SELECT raw_text,content_class FROM documents WHERE document_id='doc-1'"
    ).fetchone()
    assert raw_text is None and content_class == "taken_down"
    assert verify_twin_source_envelopes(graph)[0].status == "metadata_only"


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


def test_fast_backfill_matches_per_row_gate_across_diverse_rows(graph):
    """The preloaded fast path must produce byte-identical envelopes to the
    per-row serve-gate path (the drift guard for the deploy backfill).

    Covers: personal_reading (owner body), servable, gated, taken_down,
    arXiv T1 (body + canonical link), arXiv T2/T3 (body denied -> metadata_only),
    arXiv missing arxiv_id (link-back denied -> metadata_only), null metadata.
    """
    from substrate.twin_recursion.source_registration import (
        _envelope_from_served_fields,
        _row_envelope,
    )

    rows = [
        # (document_id, title, doc_type, owner, raw_text, content_class, metadata, taken_down)
        ("doc-personal", "T", "research", "acct", "Body text for a personal doc.", "personal_reading", None, False),
        ("doc-servable", "T", "research", "acct", "Body text for a servable doc.", "servable", None, False),
        ("doc-gated", "T", "research", "acct", "Body text for a gated doc.", "gated", None, False),
        ("doc-taken", "T", "research", "acct", "Body text taken down.", "personal_reading", None, True),
        ("doc-t1", "T", "paper", "acct", "arXiv T1 body.", "servable",
         json.dumps({"license_uri": "http://arxiv.org/licenses/nonexclusive-distrib/1.0/", "arxiv_id": "2402.03300"}), False),
        ("doc-t2", "T", "paper", "acct", "arXiv T2 body.", "servable",
         json.dumps({"license_uri": "http://creativecommons.org/licenses/by-nc-sa/4.0/", "arxiv_id": "2402.03301"}), False),
        ("doc-t3", "T", "paper", "acct", "arXiv T3 body.", "servable",
         json.dumps({"license_uri": "http://arxiv.org/licenses/nonexclusive-distrib/1.0/", "arxiv_id": ""}), False),
        ("doc-nometa", "T", "research", "acct", "No metadata at all.", "personal_reading", None, False),
    ]
    for (did, title, dtype, owner, body, cc, meta, taken) in rows:
        graph.execute(
            "INSERT INTO documents (document_id,source_tier,document_type,title,raw_text,owner_user_id,content_class,metadata) "
            "VALUES (?,2,?,?,?,?,?,?)",
            [did, dtype, title, body, owner, cc, meta],
        )
        if taken:
            graph.execute(
                "INSERT INTO book_assets (document_id,taken_down) VALUES (?,TRUE)",
                [did],
            )

    # Fast path (preloaded row shape) vs per-row gate, for every row.
    preloaded = graph.execute(
        """
        SELECT d.document_id, d.title, d.document_type, d.owner_user_id,
               d.raw_text, d.content_class, d.metadata,
               COALESCE(b.taken_down, FALSE) AS taken_down
        FROM documents d
        LEFT JOIN book_assets b ON d.document_id = b.document_id
        ORDER BY d.document_id
        """
    ).fetchall()
    assert len(preloaded) == len(rows)
    for row in preloaded:
        fast, _body = _envelope_from_served_fields(row)
        gate, _body2 = _row_envelope(graph, tuple(row[:4]))
        assert fast == gate, (
            f"fast path diverged from the serve gate for {row[0]!r}: "
            f"{fast.to_json()} != {gate.to_json()}"
        )


def test_fast_backfill_batches_and_is_resumable(graph, tmp_path):
    """A 3-batch corpus backfills in committed batches and resumes cleanly."""
    from substrate.twin_recursion.source_registration import _BACKFILL_BATCH_SIZE

    n = _BACKFILL_BATCH_SIZE * 2 + 17  # 3 batches
    for i in range(n):
        graph.execute(
            "INSERT INTO documents (document_id,source_tier,document_type,title,raw_text,owner_user_id,content_class) "
            "VALUES (?,2,'research','T','A sufficiently long canonical body for a twin source.','acct','personal_reading')",
            [f"doc-{i:05d}"],
        )
    assert backfill_twin_source_envelopes(graph) == n
    assert backfill_twin_source_envelopes(graph) == 0  # idempotent
    stamped = graph.execute(
        "SELECT COUNT(*) FROM documents WHERE twin_source_envelope IS NOT NULL"
    ).fetchone()[0]
    assert stamped == n
    assert len(verify_twin_source_envelopes(graph)) == n
