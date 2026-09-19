"""Regression tests for init_database_at_path schema fast-path guard."""

from __future__ import annotations

import os
import sys
import tempfile

import duckdb

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)  # noqa: E402

from substrate.graph import schema as schema_mod  # noqa: E402
from substrate.graph.schema import (  # noqa: E402
    _schema_is_present,
    init_database_at_path,
)


def test_schema_is_present_false_before_init():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "absent.duckdb")
        assert _schema_is_present(p) is False


def test_schema_is_present_true_after_init():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        init_database_at_path(p)
        assert _schema_is_present(p) is True


def test_warm_init_skips_write_lock(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        init_database_at_path(p)

        def _forbidden(*_a, **_kw):
            raise AssertionError("connect_write must NOT be called on the warm path")

        monkeypatch.setattr(schema_mod, "connect_write", _forbidden)
        assert init_database_at_path(p) is None


def test_cold_init_calls_connect_write(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        real = schema_mod.connect_write
        called: list[bool] = []

        def tracking(*a, **kw):
            called.append(True)
            return real(*a, **kw)

        monkeypatch.setattr(schema_mod, "connect_write", tracking)
        init_database_at_path(p)
        assert called


def test_init_is_idempotent_after_fast_path():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        init_database_at_path(p)
        init_database_at_path(p)
        con = duckdb.connect(p, read_only=True)
        try:
            row = con.execute("SELECT count(*) FROM nodes").fetchone()
        finally:
            con.close()

        assert row is not None and row[0] == 0

def test_warm_probe_is_memoized_no_connection(monkeypatch):
    # After the schema is confirmed present once, _schema_is_present must
    # short-circuit via the per-process memo WITHOUT opening a connection —
    # turning the per-request warm path O(1) (the ~4s read-only open is paid
    # once, then never again for that path).
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        init_database_at_path(p)  # cold: probes + memoizes the path

        def _must_not_open(*_a, **_kw):
            raise AssertionError("warm probe must NOT open a connection (memo)")

        monkeypatch.setattr(schema_mod.duckdb, "connect", _must_not_open)
        assert _schema_is_present(p) is True  # served from the memo, no connect


def test_cold_probe_after_cache_clear_still_works(monkeypatch):
    # Clearing the memo must restore the read-only probe (a guard that the
    # memo never masks a genuinely-cold path).
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        init_database_at_path(p)
        schema_mod._INITIALIZED_PATHS.clear()
        # Re-probe: memo miss -> real read-only probe -> True.
        assert _schema_is_present(p) is True


def test_existing_database_missing_write_edit_authority_is_upgraded():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre-write-edit.duckdb")
        init_database_at_path(p)
        schema_mod._INITIALIZED_PATHS.discard(p)
        con = duckdb.connect(p)
        try:
            con.execute("DROP TABLE interview_write_edit_revisions_authority")
            con.execute("DROP TABLE interview_write_edit_events_authority")
            con.execute(
                "CREATE TABLE interview_write_edit_events_authority ("
                "account_digest TEXT NOT NULL, event_id TEXT NOT NULL, "
                "write_document_id TEXT NOT NULL, project_id TEXT NOT NULL, "
                "owner_user_id TEXT NOT NULL, mutation_key TEXT NOT NULL, "
                "request_sha256 TEXT NOT NULL, base_revision BIGINT NOT NULL, "
                "revision BIGINT NOT NULL, prior_body_sha256 TEXT NOT NULL, "
                "body_sha256 TEXT NOT NULL, root_acceptance_event_id TEXT NOT NULL, "
                "proposal_id TEXT NOT NULL, source_manifest_sha256 TEXT NOT NULL, "
                "source_body_sha256 TEXT NOT NULL, result_html_sha256 TEXT NOT NULL, "
                "summary TEXT, event_sha256 TEXT NOT NULL, "
                "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "PRIMARY KEY (account_digest, event_id), "
                "UNIQUE (account_digest, mutation_key), "
                "UNIQUE (account_digest, write_document_id, revision))"
            )
            con.execute(
                "UPDATE interview_authority_migration_manifest SET schema_version = 15 "
                "WHERE singleton_key = 1"
            )
        finally:
            con.close()

        assert _schema_is_present(p) is False
        init_database_at_path(p)
        assert _schema_is_present(p) is True
        con = duckdb.connect(p, read_only=True)
        try:
            columns = {
                str(row[1]) for row in con.execute(
                    "PRAGMA table_info('interview_write_edit_events_authority')"
                ).fetchall()
            }
            assert {"operation", "target_revision", "target_body_sha256"} <= columns
            assert con.execute(
                "SELECT schema_version FROM interview_authority_migration_manifest "
                "WHERE singleton_key = 1"
            ).fetchone() == (22,)
        finally:
            con.close()


def test_existing_database_missing_owner_native_write_authority_is_upgraded():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre-owner-native-write.duckdb")
        init_database_at_path(p)
        schema_mod._INITIALIZED_PATHS.discard(p)
        con = duckdb.connect(p)
        try:
            con.execute("DROP TABLE interview_write_native_revisions_authority")
            con.execute("DROP TABLE interview_write_native_events_authority")
            con.execute("ALTER TABLE interview_write_documents_authority DROP COLUMN origin_kind")
            con.execute(
                "UPDATE interview_authority_migration_manifest SET schema_version = 16 "
                "WHERE singleton_key = 1"
            )
        finally:
            con.close()

        assert _schema_is_present(p) is False
        init_database_at_path(p)
        assert _schema_is_present(p) is True
        con = duckdb.connect(p, read_only=True)
        try:
            assert "origin_kind" in {
                str(row[1]) for row in con.execute(
                    "PRAGMA table_info('interview_write_documents_authority')"
                ).fetchall()
            }
            assert con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name IN "
                "('interview_write_native_events_authority', "
                "'interview_write_native_revisions_authority')"
            ).fetchone() == (2,)
            assert con.execute(
                "SELECT schema_version FROM interview_authority_migration_manifest "
                "WHERE singleton_key = 1"
            ).fetchone() == (22,)
        finally:
            con.close()


def test_existing_database_missing_write_evidence_insertion_authority_is_upgraded():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre-evidence-insertion.duckdb")
        init_database_at_path(p)
        schema_mod._INITIALIZED_PATHS.discard(p)
        con = duckdb.connect(p)
        try:
            con.execute("DROP TABLE interview_write_evidence_insertions_authority")
            con.execute(
                "UPDATE interview_authority_migration_manifest SET schema_version = 17 "
                "WHERE singleton_key = 1"
            )
        finally:
            con.close()
        assert _schema_is_present(p) is False
        init_database_at_path(p)
        assert _schema_is_present(p) is True
        con = duckdb.connect(p, read_only=True)
        try:
            assert con.execute(
                "SELECT schema_version FROM interview_authority_migration_manifest"
            ).fetchone() == (22,)
            assert con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE "
                "table_name = 'interview_write_evidence_insertions_authority'"
            ).fetchone() == (1,)
        finally:
            con.close()


def test_existing_database_missing_write_evidence_bundle_authority_is_upgraded():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre-evidence-bundle.duckdb")
        init_database_at_path(p)
        schema_mod._INITIALIZED_PATHS.discard(p)
        con = duckdb.connect(p)
        try:
            con.execute("DROP TABLE interview_write_evidence_bundle_units_authority")
            con.execute("DROP TABLE interview_write_evidence_bundles_authority")
            con.execute(
                "UPDATE interview_authority_migration_manifest SET schema_version = 18 "
                "WHERE singleton_key = 1"
            )
        finally:
            con.close()
        assert _schema_is_present(p) is False
        init_database_at_path(p)
        assert _schema_is_present(p) is True
        con = duckdb.connect(p, read_only=True)
        try:
            assert con.execute(
                "SELECT schema_version FROM interview_authority_migration_manifest"
            ).fetchone() == (22,)
            assert con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name IN "
                "('interview_write_evidence_bundles_authority', "
                "'interview_write_evidence_bundle_units_authority')"
            ).fetchone() == (2,)
        finally:
            con.close()


def test_existing_database_missing_evidence_synthesis_authority_is_upgraded():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre-evidence-synthesis.duckdb")
        init_database_at_path(p)
        schema_mod._INITIALIZED_PATHS.discard(p)
        con = duckdb.connect(p)
        try:
            con.execute("DROP TABLE interview_evidence_bundle_synthesis_inputs_authority")
            con.execute("DROP TABLE interview_evidence_bundle_synthesis_proposals_authority")
            con.execute(
                "UPDATE interview_authority_migration_manifest SET schema_version = 19 "
                "WHERE singleton_key = 1"
            )
        finally:
            con.close()
        assert _schema_is_present(p) is False
        init_database_at_path(p)
        assert _schema_is_present(p) is True
        con = duckdb.connect(p, read_only=True)
        try:
            assert con.execute(
                "SELECT schema_version FROM interview_authority_migration_manifest"
            ).fetchone() == (22,)
            assert con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name IN "
                "('interview_evidence_bundle_synthesis_proposals_authority', "
                "'interview_evidence_bundle_synthesis_inputs_authority')"
            ).fetchone() == (2,)
        finally:
            con.close()


def test_existing_database_missing_synthesis_acceptance_authority_is_upgraded():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre-synthesis-acceptance.duckdb")
        init_database_at_path(p)
        schema_mod._INITIALIZED_PATHS.discard(p)
        con = duckdb.connect(p)
        try:
            con.execute("DROP TABLE interview_write_synthesis_acceptances_authority")
            con.execute(
                "UPDATE interview_authority_migration_manifest SET schema_version = 20 "
                "WHERE singleton_key = 1"
            )
        finally:
            con.close()
        assert _schema_is_present(p) is False
        init_database_at_path(p)
        assert _schema_is_present(p) is True
        con = duckdb.connect(p, read_only=True)
        try:
            assert con.execute(
                "SELECT schema_version FROM interview_authority_migration_manifest"
            ).fetchone() == (22,)
            assert con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = "
                "'interview_write_synthesis_acceptances_authority'"
            ).fetchone() == (1,)
        finally:
            con.close()


def test_existing_v21_database_missing_synthesis_knowledge_authority_is_upgraded():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre-synthesis-knowledge.duckdb")
        init_database_at_path(p)
        schema_mod._INITIALIZED_PATHS.discard(p)
        con = duckdb.connect(p)
        try:
            con.execute("DROP TABLE interview_synthesis_knowledge_admission_items_authority")
            con.execute("DROP TABLE interview_synthesis_knowledge_admissions_authority")
            con.execute(
                "UPDATE interview_authority_migration_manifest SET schema_version = 21 "
                "WHERE singleton_key = 1"
            )
        finally:
            con.close()
        assert _schema_is_present(p) is False
        init_database_at_path(p)
        assert _schema_is_present(p) is True
        con = duckdb.connect(p, read_only=True)
        try:
            assert con.execute(
                "SELECT schema_version FROM interview_authority_migration_manifest"
            ).fetchone() == (22,)
            assert con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name IN "
                "('interview_synthesis_knowledge_admissions_authority', "
                "'interview_synthesis_knowledge_admission_items_authority')"
            ).fetchone() == (2,)
        finally:
            con.close()


def test_existing_database_missing_latest_tenancy_schema_is_upgraded():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre-v16.duckdb")
        init_database_at_path(p)
        schema_mod._INITIALIZED_PATHS.discard(p)
        con = duckdb.connect(p)
        try:
            con.execute("DROP TABLE investigation_node_memberships")
            con.execute("DROP TABLE graph_investigation_allocations")
            con.execute("DROP TABLE graph_tenancy_manifest")
        finally:
            con.close()

        assert _schema_is_present(p) is False
        init_database_at_path(p)
        assert _schema_is_present(p) is True


def test_existing_database_missing_legal_seals_and_rollback_columns_is_upgraded():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre-legal-seals.duckdb")
        init_database_at_path(p)
        schema_mod._INITIALIZED_PATHS.discard(p)
        con = duckdb.connect(p)
        try:
            con.execute("DROP TABLE legal_document_custody_seals")
            con.execute("DROP TABLE legal_chunk_manifest_seals")
            con.execute(
                "ALTER TABLE legal_history_migration_rows DROP COLUMN evaluated_receipt_id"
            )
            con.execute(
                "ALTER TABLE legal_history_migration_rows DROP COLUMN receipt_created"
            )
        finally:
            con.close()

        assert _schema_is_present(p) is False
        init_database_at_path(p)
        assert _schema_is_present(p) is True


def test_existing_database_missing_lease_recovery_schema_is_upgraded():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "pre-lease-recovery.duckdb")
        init_database_at_path(p)
        schema_mod._INITIALIZED_PATHS.discard(p)
        con = duckdb.connect(p)
        try:
            con.execute("DROP TABLE legal_policy_lease_recoveries")
            con.execute(
                "ALTER TABLE legal_policy_dispatch_leases DROP COLUMN holder_investigation_id"
            )
        finally:
            con.close()

        assert _schema_is_present(p) is False
        init_database_at_path(p)
        assert _schema_is_present(p) is True
