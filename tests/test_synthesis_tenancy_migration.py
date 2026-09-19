from __future__ import annotations

from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.synthesis_tenancy_migration import (
    SynthesisAuthorityAssignment,
    SynthesisMigrationConflict,
    SynthesisMigrationState,
    activate_synthesis_migration,
    migrate_synthesis_authority,
    rollback_synthesis_migration,
    verify_synthesis_migration,
)


class SimulatedCrash(BaseException):
    pass


def _environment(tmp_path: Path):
    database = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    events.mkdir()
    init_database_at_path(str(database))
    alice = InvestigationAuthority("alice", "shared-display", root=events)
    bob = InvestigationAuthority("bob", "shared-display", root=events)
    with connect_write(str(database), purpose="seed-synthesis-migration") as con:
        con.execute(
            "INSERT INTO syntheses (synthesis_id, investigation_id, "
            "target_question, synthesis_timestamp, status, "
            "implicit_recommendation) VALUES "
            "('legacy-alice', 'shared-display', 'Alice?', CURRENT_TIMESTAMP, "
            "'passed', 'proceed'), "
            "('legacy-bob', 'shared-display', 'Bob?', CURRENT_TIMESTAMP, "
            "'passed', 'proceed')"
        )
    assignments = (
        SynthesisAuthorityAssignment("legacy-alice", alice),
        SynthesisAuthorityAssignment("legacy-bob", bob),
    )
    return database, assignments


def test_explicit_same_display_migration_resumes_verifies_and_activates(tmp_path):
    database, assignments = _environment(tmp_path)
    crashed = False

    def checkpoint(phase: str, synthesis_id: str | None) -> None:
        nonlocal crashed
        if phase == "row_migrated" and not crashed:
            crashed = True
            raise SimulatedCrash(synthesis_id)

    with (
        pytest.raises(SimulatedCrash),
        connect_write(str(database), purpose="crash-synthesis-migration") as con,
    ):
        migrate_synthesis_authority(con, assignments, checkpoint=checkpoint)

    with connect_write(str(database), purpose="resume-synthesis-migration") as con:
        assert con.execute(
            "SELECT state FROM synthesis_tenancy_migration_manifest"
        ).fetchone() == ("copying",)
        receipt = migrate_synthesis_authority(con, reversed(assignments))
        assert receipt.state is SynthesisMigrationState.SHADOW
        assert receipt.assigned_rows == receipt.total_rows == 2
        verified = verify_synthesis_migration(con, assignments=assignments)
        assert verified.assigned_rows == 2
        rows = con.execute(
            "SELECT synthesis_id, account_digest, investigation_digest "
            "FROM syntheses ORDER BY synthesis_id"
        ).fetchall()
        assert rows == [
            (
                "legacy-alice",
                assignments[0].authority.account_digest,
                assignments[0].authority.investigation_digest,
            ),
            (
                "legacy-bob",
                assignments[1].authority.account_digest,
                assignments[1].authority.investigation_digest,
            ),
        ]
        activate_synthesis_migration(con, assignments=assignments)
        assert con.execute(
            "SELECT state FROM synthesis_tenancy_migration_manifest"
        ).fetchone() == ("scoped",)
        with pytest.raises(SynthesisMigrationConflict, match="cannot be rolled back"):
            rollback_synthesis_migration(con)


def test_shadow_migration_rolls_back_exact_original_pairs(tmp_path):
    database, assignments = _environment(tmp_path)
    with connect_write(str(database), purpose="rollback-synthesis-migration") as con:
        assert migrate_synthesis_authority(con, assignments).state is (
            SynthesisMigrationState.SHADOW
        )
        assert rollback_synthesis_migration(con) == 2
        assert con.execute(
            "SELECT synthesis_id, account_digest, investigation_digest "
            "FROM syntheses ORDER BY synthesis_id"
        ).fetchall() == [
            ("legacy-alice", None, None),
            ("legacy-bob", None, None),
        ]
        assert con.execute(
            "SELECT state FROM synthesis_tenancy_migration_manifest"
        ).fetchone() == ("rolled_back",)
        assert migrate_synthesis_authority(con, assignments).state is (
            SynthesisMigrationState.SHADOW
        )


def test_incomplete_assignment_quarantines_without_activation(tmp_path):
    database, assignments = _environment(tmp_path)
    with connect_write(str(database), purpose="incomplete-synthesis-migration") as con:
        with pytest.raises(SynthesisMigrationConflict, match="cover every row"):
            migrate_synthesis_authority(con, assignments[:1])
        assert con.execute(
            "SELECT state FROM synthesis_tenancy_migration_manifest"
        ).fetchone() == ("quarantined",)
        with pytest.raises(SynthesisMigrationConflict, match="not shadow-verified"):
            activate_synthesis_migration(con, assignments=assignments[:1])
        assert rollback_synthesis_migration(con) == 1


def test_source_drift_quarantines_rollback(tmp_path):
    database, assignments = _environment(tmp_path)
    with connect_write(str(database), purpose="drift-synthesis-migration") as con:
        migrate_synthesis_authority(con, assignments)
        con.execute(
            "UPDATE syntheses SET target_question = 'tampered' "
            "WHERE synthesis_id = 'legacy-alice'"
        )
        with pytest.raises(SynthesisMigrationConflict, match="rollback verification"):
            rollback_synthesis_migration(con)
        assert con.execute(
            "SELECT state FROM synthesis_tenancy_migration_manifest"
        ).fetchone() == ("quarantined",)
