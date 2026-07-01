"""Tests for substrate.deletion_worker — 30-day SLA cascade delete."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta

from runtime.db_lock import connect_write
import substrate.deletion_worker.db as deletion_db
import substrate.deletion_worker.__main__ as deletion_worker_cli_module
from substrate.deletion_worker.__main__ import main as deletion_worker_cli
from substrate.deletion_worker import (
    CANCELLATION_WINDOW_DAYS,
    CASCADE_TARGETS,
    SLA_DAYS,
    DeletionRequest,
    DeletionRequestStatus,
    DeletionResult,
    DeletionResultKind,
    process_request,
    run_db_cycle,
    run_db_cycle_at_path,
    run_one_cycle,
)
from substrate.graph import ensure_initialized, init_database
from substrate.telemetry_preferences import (
    InMemoryPreferenceStore,
    SqlitePreferenceStore,
    set_preference,
)


def _request_at(days_ago: float, *, status=DeletionRequestStatus.PENDING) -> DeletionRequest:
    requested = datetime.now(UTC) - timedelta(days=days_ago)
    return DeletionRequest(
        request_id=f"del-{days_ago}",
        user_id=f"u-{days_ago}",
        status=status,
        requested_at=requested,
        updated_at=requested,
        reason="test",
    )


def _record_cascade(captured: list[str]):
    """Cascade strategy that records the user_id called against it."""
    def strategy(user_id: str) -> dict[str, int]:
        captured.append(user_id)
        return {target: 1 for target in CASCADE_TARGETS}
    return strategy


# ── 7-day cancellation window ──────────────────────────────────


def test_pending_inside_cancellation_window_skipped():
    captured: list[str] = []
    req = _request_at(days_ago=3)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.SKIPPED_CANCELLATION_WINDOW
    assert captured == []
    assert result.sla_remaining_days == SLA_DAYS - 3


def test_pending_at_window_edge_processes():
    """Exactly 7 days old → fires cascade (> 7 days strictly)."""
    captured: list[str] = []
    # Just past the 7-day boundary.
    req = _request_at(days_ago=CANCELLATION_WINDOW_DAYS + 0.5)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.COMPLETED
    assert len(captured) == 1


def test_pending_past_window_processes_cascade():
    captured: list[str] = []
    req = _request_at(days_ago=15)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.COMPLETED
    assert captured == [req.user_id]
    # All cascade targets reported deleted rows.
    assert set(result.rows_deleted.keys()) == set(CASCADE_TARGETS)


def test_confirmed_inside_cancellation_window_still_skipped():
    captured: list[str] = []
    req = _request_at(days_ago=3, status=DeletionRequestStatus.CONFIRMED)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.SKIPPED_CANCELLATION_WINDOW
    assert captured == []


# ── Terminal states are skipped ────────────────────────────────


def test_cancelled_request_skipped():
    captured: list[str] = []
    req = _request_at(days_ago=10, status=DeletionRequestStatus.CANCELLED)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.SKIPPED_ALREADY_TERMINAL
    assert captured == []


def test_completed_request_skipped_idempotent_replay():
    captured: list[str] = []
    req = _request_at(days_ago=10, status=DeletionRequestStatus.COMPLETED)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.SKIPPED_ALREADY_TERMINAL
    assert captured == []


def test_failed_request_skipped():
    captured: list[str] = []
    req = _request_at(days_ago=10, status=DeletionRequestStatus.FAILED)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.SKIPPED_ALREADY_TERMINAL


# ── Cascade error handling ─────────────────────────────────────


def test_cascade_exception_yields_failed_result():
    def bad_cascade(user_id: str) -> dict[str, int]:
        raise RuntimeError("DB unreachable")

    req = _request_at(days_ago=15)
    result = process_request(req, cascade=bad_cascade)
    assert result.kind == DeletionResultKind.FAILED
    assert result.error == "DB unreachable"
    # SLA timing still reported.
    assert result.sla_remaining_days is not None


# ── SLA remaining days ─────────────────────────────────────────


def test_sla_remaining_zero_at_or_past_30_days():
    captured: list[str] = []
    req = _request_at(days_ago=35)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.kind == DeletionResultKind.COMPLETED
    assert result.sla_remaining_days == 0  # max(0, 30-35) = 0


def test_sla_remaining_positive_when_within_window():
    captured: list[str] = []
    req = _request_at(days_ago=10)
    result = process_request(req, cascade=_record_cascade(captured))
    assert result.sla_remaining_days == SLA_DAYS - 10


# ── run_one_cycle ───────────────────────────────────────────────


def test_run_one_cycle_processes_all_requests():
    captured: list[str] = []
    requests = [
        _request_at(days_ago=15),  # COMPLETED
        _request_at(days_ago=3),   # SKIPPED window
        _request_at(days_ago=8, status=DeletionRequestStatus.CANCELLED),  # SKIPPED terminal
    ]
    results = run_one_cycle(requests, cascade=_record_cascade(captured))
    assert len(results) == 3
    kinds = [r.kind for r in results]
    assert DeletionResultKind.COMPLETED in kinds
    assert DeletionResultKind.SKIPPED_CANCELLATION_WINDOW in kinds
    assert DeletionResultKind.SKIPPED_ALREADY_TERMINAL in kinds
    # Only one cascade actually fired.
    assert len(captured) == 1


# ── Cascade targets include all the spec-relevant tables ───────


def test_cascade_targets_cover_personal_graph_dependents():
    """Spec §13.2: deletion must unwind chunks, embeddings, derived
    skills, per-user attribution shares. Verify CASCADE_TARGETS
    enumerates these (or their equivalent tables)."""
    targets = set(CASCADE_TARGETS)
    # Spec-named categories.
    assert "documents" in targets  # the source for chunks
    assert "edges" in targets
    assert "chunk_tier_overrides" in targets
    assert "chunks" in targets
    assert "url_alias" in targets
    assert "book_assets" in targets
    assert "claims" in targets
    assert "claim_evidence" in targets
    assert "user_telemetry_preferences" in targets
    assert "personal_graph_metadata" in targets


# ── Custom clock for deterministic tests ───────────────────────


def test_clock_injection_controls_age():
    fixed_now = datetime(2026, 6, 1, tzinfo=UTC)
    req = DeletionRequest(
        request_id="del-clock",
        user_id="u-1",
        status=DeletionRequestStatus.PENDING,
        requested_at=datetime(2026, 5, 1, tzinfo=UTC),
        updated_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    captured: list[str] = []
    result = process_request(req, cascade=_record_cascade(captured), now=fixed_now)
    # 31 days old → completed; SLA exhausted.
    assert result.kind == DeletionResultKind.COMPLETED
    assert result.sla_remaining_days == 0


# ── DuckDB persistence adapter ───────────────────────────────────


def test_db_cycle_completes_old_pending_request_and_deletes_owned_rows(tmp_path):
    db_path = str(tmp_path / "antiek.duckdb")
    ensure_initialized(db_path)
    preference_store = InMemoryPreferenceStore()
    set_preference(
        preference_store,
        user_id="u-delete",
        surface_name="skill_invocation_frequency",
        enabled=False,
    )
    set_preference(
        preference_store,
        user_id="u-keep",
        surface_name="skill_invocation_frequency",
        enabled=False,
    )
    with connect_write(db_path, purpose="test:deletion_worker") as con:
        con.execute(
            """
            INSERT INTO documents
                (document_id, source_uri, title, source_tier, document_type,
                 owner_user_id, raw_text)
            VALUES
                ('doc-owned', 'mem://owned', 'Owned', 1, 'note', 'u-delete', 'owned'),
                ('doc-other', 'mem://other', 'Other', 1, 'note', 'u-keep', 'other')
            """
        )
        con.execute(
            """
            INSERT INTO chunks (chunk_id, document_id, chunk_index, text)
            VALUES
                ('chunk-owned', 'doc-owned', 0, 'owned'),
                ('chunk-other', 'doc-other', 0, 'other')
            """
        )
        con.execute(
            """
            INSERT INTO nodes
                (node_id, canonical_label, node_type, graph_scope)
            VALUES
                ('node-a', 'A', 'entity', 'depth'),
                ('node-b', 'B', 'entity', 'depth')
            """
        )
        con.execute(
            """
            INSERT INTO edges
                (edge_id, source_node_id, target_node_id, relation, chunk_id,
                 source_document_id, source_tier, extraction_confidence,
                 graph_scope)
            VALUES
                ('edge-owned', 'node-a', 'node-b', 'supports', 'chunk-owned',
                 'doc-owned', 1, 0.9, 'depth'),
                ('edge-other', 'node-a', 'node-b', 'supports', 'chunk-other',
                 'doc-other', 1, 0.9, 'depth')
            """
        )
        con.execute(
            """
            INSERT INTO chunk_tier_overrides
                (chunk_id, original_tier, override_tier, reason)
            VALUES
                ('chunk-owned', 1, 2, 'owned override'),
                ('chunk-other', 1, 2, 'other override')
            """
        )
        con.execute(
            """
            INSERT INTO url_alias (requested_url, document_id)
            VALUES
                ('https://owned.example', 'doc-owned'),
                ('https://other.example', 'doc-other')
            """
        )
        con.execute(
            """
            INSERT INTO book_assets (document_id)
            VALUES ('doc-owned'), ('doc-other')
            """
        )
        con.execute(
            """
            INSERT INTO deliverables
                (deliverable_id, title, deliverable_kind, owner_user_id)
            VALUES
                ('deliv-owned', 'Owned deliverable', 'general_essay', 'u-delete'),
                ('deliv-other', 'Other deliverable', 'general_essay', 'u-keep')
            """
        )
        con.execute(
            """
            INSERT INTO interview_projects
                (project_id, title, deliverable_id, owner_user_id)
            VALUES
                ('project-owned', 'Owned project', 'deliv-owned', 'u-delete'),
                ('project-other', 'Other project', 'deliv-other', 'u-keep')
            """
        )
        con.execute(
            """
            INSERT INTO interviews
                (interview_id, project_id, transcript_document_id, status)
            VALUES
                ('interview-owned', 'project-owned', 'doc-owned', 'completed'),
                ('interview-other', 'project-other', 'doc-other', 'completed')
            """
        )
        con.execute(
            """
            INSERT INTO deliverable_sections
                (section_id, deliverable_id, parent_section_id, section_index, title)
            VALUES
                ('sec-owned-parent', 'deliv-owned', NULL, 0, 'Parent')
            """
        )
        con.execute(
            """
            INSERT INTO deliverable_sections
                (section_id, deliverable_id, parent_section_id, section_index, title)
            VALUES
                ('sec-owned-child', 'deliv-owned', 'sec-owned-parent', 1, 'Child'),
                ('sec-other', 'deliv-other', NULL, 0, 'Other')
            """
        )
        con.execute(
            """
            INSERT INTO section_blocks
                (section_id, block_kind, block_id, block_index)
            VALUES
                ('sec-owned-child', 'operator_note', 'block-owned', 0),
                ('sec-other', 'operator_note', 'block-other', 0)
            """
        )
        con.execute(
            """
            INSERT INTO outline_blocks
                (outline_block_id, section_id, block_kind, provenance_kind,
                 content, block_index)
            VALUES
                ('outline-owned', 'sec-owned-child', 'user_authored',
                 'user_authored', 'owned', 0),
                ('outline-other', 'sec-other', 'user_authored',
                 'user_authored', 'other', 0)
            """
        )
        con.execute(
            """
            INSERT INTO deletion_requests
                (request_id, user_id, status, requested_at, updated_at, reason)
            VALUES (
                'del-owned', 'u-delete', 'pending',
                TIMESTAMP '2026-05-01 00:00:00',
                TIMESTAMP '2026-05-01 00:00:00',
                'test'
            )
            """
        )

        results = run_db_cycle(
            con,
            now=datetime(2026, 5, 20, tzinfo=UTC),
            preference_store=preference_store,
        )

        assert [r.kind for r in results] == [DeletionResultKind.COMPLETED], results[
            0
        ].error
        assert results[0].rows_deleted["edges"] == 1
        assert results[0].rows_deleted["chunk_tier_overrides"] == 1
        assert results[0].rows_deleted["url_alias"] == 1
        assert results[0].rows_deleted["book_assets"] == 1
        assert results[0].rows_deleted["section_blocks"] == 1
        assert results[0].rows_deleted["outline_blocks"] == 1
        assert results[0].rows_deleted["deliverable_sections"] == 2
        assert results[0].rows_deleted["deliverables"] == 1
        assert results[0].rows_deleted["chunks"] == 1
        assert results[0].rows_deleted["documents"] == 1
        assert results[0].rows_deleted["interviews"] == 1
        assert results[0].rows_deleted["interview_projects"] == 1
        assert results[0].rows_deleted["user_telemetry_preferences"] == 1
        assert con.execute(
            "SELECT status FROM deletion_requests WHERE request_id = 'del-owned'",
        ).fetchone()[0] == "completed"
        assert con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = 'doc-owned'",
        ).fetchone()[0] == 0
        assert con.execute(
            "SELECT COUNT(*) FROM chunks WHERE chunk_id = 'chunk-owned'",
        ).fetchone()[0] == 0
        assert con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = 'doc-other'",
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM chunks WHERE chunk_id = 'chunk-other'",
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM edges WHERE edge_id = 'edge-other'",
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM url_alias WHERE requested_url = 'https://other.example'",
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM deliverable_sections WHERE section_id = 'sec-other'",
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM outline_blocks WHERE outline_block_id = 'outline-other'",
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM interviews WHERE interview_id = 'interview-other'",
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT COUNT(*) FROM interview_projects WHERE project_id = 'project-other'",
        ).fetchone()[0] == 1
        assert preference_store.list_for_user("u-delete") == []
        assert len(preference_store.list_for_user("u-keep")) == 1


def test_db_cycle_at_path_deletes_adjacent_telemetry_preferences(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("ANTIEK_TELEMETRY_PREFERENCES_PATH", raising=False)
    db_path = tmp_path / "antiek.duckdb"
    ensure_initialized(str(db_path))
    preference_store = SqlitePreferenceStore(
        str(tmp_path / "telemetry_preferences.sqlite"),
    )
    set_preference(
        preference_store,
        user_id="u-delete",
        surface_name="skill_invocation_frequency",
        enabled=False,
    )
    set_preference(
        preference_store,
        user_id="u-keep",
        surface_name="skill_invocation_frequency",
        enabled=False,
    )
    with connect_write(str(db_path), purpose="test:deletion_worker_path_seed") as con:
        con.execute(
            """
            INSERT INTO deletion_requests
                (request_id, user_id, status, requested_at, updated_at, reason)
            VALUES (
                'del-prefs', 'u-delete', 'pending',
                TIMESTAMP '2026-05-01 00:00:00',
                TIMESTAMP '2026-05-01 00:00:00',
                'test'
            )
            """
        )

    results = run_db_cycle_at_path(
        db_path,
        now=datetime(2026, 5, 20, tzinfo=UTC),
    )

    assert [r.kind for r in results] == [DeletionResultKind.COMPLETED]
    assert results[0].rows_deleted["user_telemetry_preferences"] == 1
    reopened = SqlitePreferenceStore(str(tmp_path / "telemetry_preferences.sqlite"))
    assert reopened.list_for_user("u-delete") == []
    assert len(reopened.list_for_user("u-keep")) == 1


def test_db_cycle_at_path_honors_telemetry_preferences_env_override(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "antiek.duckdb"
    override_path = tmp_path / "override_prefs.sqlite"
    adjacent_path = tmp_path / "telemetry_preferences.sqlite"
    monkeypatch.setenv("ANTIEK_TELEMETRY_PREFERENCES_PATH", str(override_path))
    ensure_initialized(str(db_path))
    override_store = SqlitePreferenceStore(str(override_path))
    adjacent_store = SqlitePreferenceStore(str(adjacent_path))
    set_preference(
        override_store,
        user_id="u-delete",
        surface_name="skill_invocation_frequency",
        enabled=False,
    )
    set_preference(
        adjacent_store,
        user_id="u-delete",
        surface_name="skill_invocation_frequency",
        enabled=False,
    )
    with connect_write(str(db_path), purpose="test:deletion_worker_env_seed") as con:
        con.execute(
            """
            INSERT INTO deletion_requests
                (request_id, user_id, status, requested_at, updated_at, reason)
            VALUES (
                'del-prefs-env', 'u-delete', 'pending',
                TIMESTAMP '2026-05-01 00:00:00',
                TIMESTAMP '2026-05-01 00:00:00',
                'test'
            )
            """
        )

    results = run_db_cycle_at_path(
        db_path,
        now=datetime(2026, 5, 20, tzinfo=UTC),
    )

    assert [r.kind for r in results] == [DeletionResultKind.COMPLETED]
    assert results[0].rows_deleted["user_telemetry_preferences"] == 1
    assert SqlitePreferenceStore(str(override_path)).list_for_user("u-delete") == []
    assert len(SqlitePreferenceStore(str(adjacent_path)).list_for_user("u-delete")) == 1


def test_db_cycle_respects_cancellation_window(tmp_path):
    db_path = str(tmp_path / "antiek.duckdb")
    ensure_initialized(db_path)
    with connect_write(db_path, purpose="test:deletion_worker_window") as con:
        con.execute(
            """
            INSERT INTO documents
                (document_id, source_uri, title, source_tier, document_type,
                 owner_user_id, raw_text)
            VALUES ('doc-fresh', 'mem://fresh', 'Fresh', 1, 'note', 'u-fresh', 'fresh')
            """
        )
        con.execute(
            """
            INSERT INTO deletion_requests
                (request_id, user_id, status, requested_at, updated_at, reason)
            VALUES (
                'del-fresh', 'u-fresh', 'pending',
                TIMESTAMP '2026-05-18 00:00:00',
                TIMESTAMP '2026-05-18 00:00:00',
                'test'
            )
            """
        )

        results = run_db_cycle(
            con,
            now=datetime(2026, 5, 20, tzinfo=UTC),
        )

        assert [r.kind for r in results] == [
            DeletionResultKind.SKIPPED_CANCELLATION_WINDOW,
        ]
        assert con.execute(
            "SELECT status FROM deletion_requests WHERE request_id = 'del-fresh'",
        ).fetchone()[0] == "pending"
        assert con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = 'doc-fresh'",
        ).fetchone()[0] == 1


def test_db_cycle_confirmed_row_respects_cancellation_window(tmp_path):
    db_path = str(tmp_path / "antiek.duckdb")
    ensure_initialized(db_path)
    with connect_write(db_path, purpose="test:deletion_worker_confirmed") as con:
        con.execute(
            """
            INSERT INTO documents
                (document_id, source_uri, title, source_tier, document_type,
                 owner_user_id, raw_text)
            VALUES ('doc-confirmed', 'mem://confirmed', 'Confirmed', 1, 'note',
                    'u-confirmed', 'confirmed')
            """
        )
        con.execute(
            """
            INSERT INTO deletion_requests
                (request_id, user_id, status, requested_at, updated_at, reason)
            VALUES (
                'del-confirmed', 'u-confirmed', 'confirmed',
                TIMESTAMP '2026-05-18 00:00:00',
                TIMESTAMP '2026-05-18 00:00:00',
                'test'
            )
            """
        )

        results = run_db_cycle(
            con,
            now=datetime(2026, 5, 20, tzinfo=UTC),
        )

        assert [r.kind for r in results] == [
            DeletionResultKind.SKIPPED_CANCELLATION_WINDOW,
        ]
        assert con.execute(
            "SELECT status FROM deletion_requests WHERE request_id = 'del-confirmed'",
        ).fetchone()[0] == "confirmed"
        assert con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = 'doc-confirmed'",
        ).fetchone()[0] == 1


def test_db_cycle_requires_preference_store_before_cascade(tmp_path):
    db_path = str(tmp_path / "antiek.duckdb")
    ensure_initialized(db_path)
    with connect_write(db_path, purpose="test:deletion_worker_store_required") as con:
        con.execute(
            """
            INSERT INTO deletion_requests
                (request_id, user_id, status, requested_at, updated_at, reason)
            VALUES (
                'del-needs-store', 'u-needs-store', 'pending',
                TIMESTAMP '2026-05-01 00:00:00',
                TIMESTAMP '2026-05-01 00:00:00',
                'test'
            )
            """
        )

        results = run_db_cycle(
            con,
            now=datetime(2026, 5, 20, tzinfo=UTC),
        )

        assert [r.kind for r in results] == [DeletionResultKind.FAILED]
        assert "telemetry preference store" in (results[0].error or "")
        assert con.execute(
            "SELECT status FROM deletion_requests WHERE request_id = 'del-needs-store'",
        ).fetchone()[0] == "failed"


def test_db_cycle_persists_failed_status_on_cascade_error(tmp_path, monkeypatch):
    db_path = str(tmp_path / "antiek.duckdb")
    ensure_initialized(db_path)

    def fail_cascade(con, user_id: str, **kwargs) -> dict[str, int]:
        raise RuntimeError(f"cascade unavailable for {user_id}")

    monkeypatch.setattr(deletion_db, "cascade_delete_user", fail_cascade)
    with connect_write(db_path, purpose="test:deletion_worker_failed") as con:
        con.execute(
            """
            INSERT INTO deletion_requests
                (request_id, user_id, status, requested_at, updated_at, reason)
            VALUES (
                'del-fails', 'u-fails', 'pending',
                TIMESTAMP '2026-05-01 00:00:00',
                TIMESTAMP '2026-05-01 00:00:00',
                'test'
            )
            """
        )

        results = run_db_cycle(
            con,
            now=datetime(2026, 5, 20, tzinfo=UTC),
            preference_store=InMemoryPreferenceStore(),
        )

        assert [r.kind for r in results] == [DeletionResultKind.FAILED]
        assert "cascade unavailable" in (results[0].error or "")
        assert con.execute(
            "SELECT status FROM deletion_requests WHERE request_id = 'del-fails'",
        ).fetchone()[0] == "failed"


def test_schema_migrates_legacy_deletion_request_check_to_failed(tmp_path):
    db_path = str(tmp_path / "legacy.duckdb")
    with connect_write(db_path, purpose="test:legacy_deletion_schema") as con:
        con.execute(
            """
            CREATE TABLE deletion_requests (
                request_id      TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                    'pending', 'confirmed', 'cancelled', 'completed'
                )),
                requested_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reason          TEXT
            )
            """
        )
        con.execute(
            """
            INSERT INTO deletion_requests (request_id, user_id, status, reason)
            VALUES ('del-legacy', 'u-legacy', 'pending', 'test')
            """
        )

        init_database(con)
        con.execute(
            """
            INSERT INTO deletion_requests (request_id, user_id, status, reason)
            VALUES ('del-failed', 'u-legacy', 'failed', 'worker error')
            """
        )

        rows = con.execute(
            "SELECT request_id, status FROM deletion_requests ORDER BY request_id",
        ).fetchall()
        assert rows == [
            ("del-failed", "failed"),
            ("del-legacy", "pending"),
        ]


def test_deletion_worker_cli_runs_cycle_and_emits_jsonl(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTIEK_TELEMETRY_PREFERENCES_PATH", raising=False)
    db_path = tmp_path / "antiek.duckdb"
    ensure_initialized(str(db_path))
    preference_store = SqlitePreferenceStore(
        str(tmp_path / "telemetry_preferences.sqlite"),
    )
    set_preference(
        preference_store,
        user_id="u-cli",
        surface_name="skill_invocation_frequency",
        enabled=False,
    )
    with connect_write(str(db_path), purpose="test:deletion_worker_cli_seed") as con:
        con.execute(
            """
            INSERT INTO deletion_requests
                (request_id, user_id, status, requested_at, updated_at, reason)
            VALUES (
                'del-cli', 'u-cli', 'pending',
                TIMESTAMP '2026-05-01 00:00:00',
                TIMESTAMP '2026-05-01 00:00:00',
                'cli test'
            )
            """
        )

    out = io.StringIO()
    rc = deletion_worker_cli(
        ["--db", str(db_path), "--now", "2026-05-20T00:00:00+00:00"],
        out=out,
    )

    assert rc == 0
    payloads = [json.loads(line) for line in out.getvalue().splitlines()]
    assert payloads == [
        {
            "kind": "completed",
            "request_id": "del-cli",
            "rows_deleted": {
                "book_assets": 0,
                "chunks": 0,
                "claim_evidence": 0,
                "claims": 0,
                "deliverable_sections": 0,
                "deliverables": 0,
                "documents": 0,
                "edges": 0,
                "interview_projects": 0,
                "interviews": 0,
                "investigations": 0,
                "notebook_blocks": 0,
                "notebooks": 0,
                "outline_blocks": 0,
                "personal_graph_metadata": 0,
                "section_blocks": 0,
                "url_alias": 0,
                "chunk_tier_overrides": 0,
                "user_telemetry_preferences": 1,
            },
            "sla_remaining_days": 11,
            "user_id": "u-cli",
        },
    ]
    assert preference_store.list_for_user("u-cli") == []
    with connect_write(str(db_path), purpose="test:deletion_worker_cli_assert") as con:
        assert con.execute(
            "SELECT status FROM deletion_requests WHERE request_id = 'del-cli'",
        ).fetchone()[0] == "completed"


def test_deletion_worker_cli_exits_nonzero_when_cycle_fails(monkeypatch):
    failed = DeletionResult(
        request_id="del-cli-fails",
        user_id="u-cli-fails",
        kind=DeletionResultKind.FAILED,
        error="cascade unavailable",
        sla_remaining_days=11,
    )
    monkeypatch.setattr(
        deletion_worker_cli_module,
        "_resolve_db_path",
        lambda override: override or "antiek.duckdb",
    )
    monkeypatch.setattr(
        deletion_worker_cli_module,
        "run_db_cycle_at_path",
        lambda db_path, now=None, preference_store=None: [failed],
    )

    out = io.StringIO()
    rc = deletion_worker_cli(
        ["--db", "unused.duckdb", "--now", "2026-05-20T00:00:00+00:00"],
        out=out,
    )

    assert rc == 1
    payload = json.loads(out.getvalue())
    assert payload["kind"] == "failed"
    assert payload["request_id"] == "del-cli-fails"
    assert payload["error"] == "cascade unavailable"


def test_deletion_worker_cli_rejects_db_with_env_pref_override(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "antiek.duckdb"
    monkeypatch.setenv(
        "ANTIEK_TELEMETRY_PREFERENCES_PATH",
        str(tmp_path / "override.sqlite"),
    )

    out = io.StringIO()
    rc = deletion_worker_cli(["--db", str(db_path)], out=out)

    assert rc == 1
    payload = json.loads(out.getvalue())
    assert payload["kind"] == "failed"
    assert payload["scope"] == "cycle"
    assert "--telemetry-preferences" in payload["error"]


def test_deletion_worker_cli_accepts_explicit_preference_override(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "antiek.duckdb"
    pref_path = tmp_path / "explicit.sqlite"
    wrong_env_path = tmp_path / "wrong-env.sqlite"
    monkeypatch.setenv("ANTIEK_TELEMETRY_PREFERENCES_PATH", str(wrong_env_path))
    ensure_initialized(str(db_path))
    explicit_store = SqlitePreferenceStore(str(pref_path))
    wrong_store = SqlitePreferenceStore(str(wrong_env_path))
    set_preference(
        explicit_store,
        user_id="u-explicit",
        surface_name="skill_invocation_frequency",
        enabled=False,
    )
    set_preference(
        wrong_store,
        user_id="u-explicit",
        surface_name="skill_invocation_frequency",
        enabled=False,
    )
    with connect_write(str(db_path), purpose="test:deletion_worker_cli_pref_seed") as con:
        con.execute(
            """
            INSERT INTO deletion_requests
                (request_id, user_id, status, requested_at, updated_at, reason)
            VALUES (
                'del-cli-explicit', 'u-explicit', 'pending',
                TIMESTAMP '2026-05-01 00:00:00',
                TIMESTAMP '2026-05-01 00:00:00',
                'cli explicit pref test'
            )
            """
        )

    out = io.StringIO()
    rc = deletion_worker_cli(
        [
            "--db",
            str(db_path),
            "--telemetry-preferences",
            str(pref_path),
            "--now",
            "2026-05-20T00:00:00+00:00",
        ],
        out=out,
    )

    assert rc == 0
    payload = json.loads(out.getvalue())
    assert payload["kind"] == "completed"
    assert payload["rows_deleted"]["user_telemetry_preferences"] == 1
    assert SqlitePreferenceStore(str(pref_path)).list_for_user("u-explicit") == []
    assert len(SqlitePreferenceStore(str(wrong_env_path)).list_for_user("u-explicit")) == 1


def test_deletion_worker_cli_bad_now_returns_cycle_failure(tmp_path):
    out = io.StringIO()
    rc = deletion_worker_cli(
        ["--db", str(tmp_path / "antiek.duckdb"), "--now", "not-a-date"],
        out=out,
    )

    assert rc == 1
    payload = json.loads(out.getvalue())
    assert payload["kind"] == "failed"
    assert payload["scope"] == "cycle"
    assert "Invalid isoformat" in payload["error"]


def test_deletion_worker_cli_initializes_default_db_path(tmp_path, monkeypatch):
    db_path = tmp_path / "antiek.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.delenv("ANTIEK_TELEMETRY_PREFERENCES_PATH", raising=False)

    out = io.StringIO()
    rc = deletion_worker_cli(["--now", "2026-05-20T00:00:00+00:00"], out=out)

    assert rc == 0
    assert out.getvalue() == ""
    assert db_path.exists()
