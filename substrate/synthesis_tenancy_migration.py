"""Resumable, explicit synthesis authority migration and rollback."""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.graph.tenancy import initialize_graph_authority
from substrate.investigation_tenancy import InvestigationAuthority

Checkpoint = Callable[[str, str | None], None]


class SynthesisMigrationConflict(RuntimeError):
    """The stored migration state cannot prove the requested assignment."""


class SynthesisMigrationState(StrEnum):
    COPYING = "copying"
    SHADOW = "shadow"
    SCOPED = "scoped"
    QUARANTINED = "quarantined"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class SynthesisAuthorityAssignment:
    synthesis_id: str
    authority: InvestigationAuthority

    def __post_init__(self) -> None:
        if (
            not isinstance(self.synthesis_id, str)
            or not self.synthesis_id
            or self.synthesis_id != self.synthesis_id.strip()
            or len(self.synthesis_id) > 512
        ):
            raise ValueError("synthesis migration id is invalid")
        if not isinstance(self.authority, InvestigationAuthority):
            raise TypeError("synthesis migration requires InvestigationAuthority")


@dataclass(frozen=True)
class SynthesisMigrationReceipt:
    state: SynthesisMigrationState
    assignment_digest: str
    assigned_rows: int
    total_rows: int


def _require_locked(con: object) -> LockedConnection:
    if not isinstance(con, LockedConnection):
        raise TypeError("synthesis migration requires a LockedConnection")
    return con


def _normalized_assignments(
    assignments: Iterable[SynthesisAuthorityAssignment],
) -> tuple[SynthesisAuthorityAssignment, ...]:
    rows = sorted(assignments, key=lambda assignment: assignment.synthesis_id)
    if not rows:
        raise ValueError("synthesis migration assignments are empty")
    if len({row.synthesis_id for row in rows}) != len(rows):
        raise ValueError("synthesis migration contains duplicate ids")
    key_ids = {row.authority.key_id for row in rows}
    if len(key_ids) != 1:
        raise SynthesisMigrationConflict("assignments use different tenancy keys")
    return tuple(rows)


def _assignment_digest(rows: tuple[SynthesisAuthorityAssignment, ...]) -> str:
    payload = [
        {
            "synthesis_id": row.synthesis_id,
            "account_digest": row.authority.account_digest,
            "investigation_digest": row.authority.investigation_digest,
        }
        for row in rows
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _source_row(con: LockedConnection, synthesis_id: str) -> tuple[dict[str, Any], str]:
    cursor = con.execute("SELECT * FROM syntheses WHERE synthesis_id = ?", [synthesis_id])
    row = cursor.fetchone()
    if row is None:
        raise SynthesisMigrationConflict("assigned synthesis does not exist")
    names = [column[0] for column in cursor.description]
    material = dict(zip(names, row, strict=True))
    material.pop("account_digest", None)
    material.pop("investigation_digest", None)
    fingerprint = hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()
    return dict(zip(names, row, strict=True)), fingerprint


def _manifest(con: LockedConnection) -> tuple[str, SynthesisMigrationState, str] | None:
    rows = con.execute(
        "SELECT key_id, state, assignment_digest "
        "FROM synthesis_tenancy_migration_manifest "
        "WHERE singleton_key = 'synthesis-tenancy-v1'"
    ).fetchall()
    if not rows:
        return None
    if len(rows) != 1:
        raise SynthesisMigrationConflict("synthesis migration manifest is invalid")
    try:
        return rows[0][0], SynthesisMigrationState(rows[0][1]), rows[0][2]
    except (TypeError, ValueError) as exc:
        raise SynthesisMigrationConflict(
            "synthesis migration manifest is invalid"
        ) from exc


def _set_state(con: LockedConnection, state: SynthesisMigrationState) -> None:
    con.execute(
        "UPDATE synthesis_tenancy_migration_manifest SET state = ?, "
        "updated_at = CURRENT_TIMESTAMP "
        "WHERE singleton_key = 'synthesis-tenancy-v1'",
        [state.value],
    )


def _quarantine(con: LockedConnection) -> None:
    with contextlib.suppress(Exception):
        _set_state(con, SynthesisMigrationState.QUARANTINED)


def migrate_synthesis_authority(
    con: LockedConnection,
    assignments: Iterable[SynthesisAuthorityAssignment],
    *,
    checkpoint: Checkpoint | None = None,
) -> SynthesisMigrationReceipt:
    """Copy explicit authority into every synthesis and stop in shadow."""
    con = _require_locked(con)
    rows = _normalized_assignments(assignments)
    digest = _assignment_digest(rows)
    key_id = rows[0].authority.key_id
    manifest = _manifest(con)
    if manifest is None:
        con.execute(
            "INSERT INTO synthesis_tenancy_migration_manifest "
            "(singleton_key, version, key_id, state, assignment_digest) "
            "VALUES ('synthesis-tenancy-v1', 1, ?, 'copying', ?)",
            [key_id, digest],
        )
    elif manifest == (key_id, SynthesisMigrationState.ROLLED_BACK, digest):
        _set_state(con, SynthesisMigrationState.COPYING)
    elif manifest != (key_id, SynthesisMigrationState.COPYING, digest):
        if manifest == (key_id, SynthesisMigrationState.SHADOW, digest):
            return verify_synthesis_migration(con, assignments=rows)
        raise SynthesisMigrationConflict("synthesis migration manifest conflicts")

    try:
        for assignment in rows:
            stored, fingerprint = _source_row(con, assignment.synthesis_id)
            if stored.get("investigation_id") != assignment.authority.investigation_id:
                raise SynthesisMigrationConflict(
                    "assignment display investigation does not match synthesis"
                )
            existing = con.execute(
                "SELECT original_account_digest, original_investigation_digest, "
                "target_account_digest, target_investigation_digest, "
                "source_fingerprint FROM synthesis_tenancy_migration_rows "
                "WHERE synthesis_id = ?",
                [assignment.synthesis_id],
            ).fetchone()
            expected_target = (
                assignment.authority.account_digest,
                assignment.authority.investigation_digest,
                fingerprint,
            )
            if existing is None:
                con.execute(
                    "INSERT INTO synthesis_tenancy_migration_rows "
                    "(synthesis_id, original_account_digest, "
                    "original_investigation_digest, target_account_digest, "
                    "target_investigation_digest, source_fingerprint) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        assignment.synthesis_id,
                        stored.get("account_digest"),
                        stored.get("investigation_digest"),
                        *expected_target,
                    ],
                )
            elif tuple(existing[2:]) != expected_target:
                raise SynthesisMigrationConflict("synthesis migration journal conflicts")
            initialize_graph_authority(con, assignment.authority)
            current_pair = (
                stored.get("account_digest"),
                stored.get("investigation_digest"),
            )
            target_pair = expected_target[:2]
            original_pair = tuple(existing[:2]) if existing is not None else current_pair
            if current_pair not in {original_pair, target_pair}:
                raise SynthesisMigrationConflict("synthesis authority changed during migration")
            con.execute(
                "UPDATE syntheses SET account_digest = ?, investigation_digest = ? "
                "WHERE synthesis_id = ?",
                [*target_pair, assignment.synthesis_id],
            )
            if checkpoint is not None:
                checkpoint("row_migrated", assignment.synthesis_id)

        total_rows = int(con.execute("SELECT count(*) FROM syntheses").fetchone()[0])
        assigned_rows = len(rows)
        unscoped = int(
            con.execute(
                "SELECT count(*) FROM syntheses WHERE account_digest IS NULL "
                "OR investigation_digest IS NULL"
            ).fetchone()[0]
        )
        if assigned_rows != total_rows or unscoped:
            raise SynthesisMigrationConflict(
                "synthesis migration assignments do not cover every row"
            )
        receipt = verify_synthesis_migration(con, assignments=rows)
        _set_state(con, SynthesisMigrationState.SHADOW)
        if checkpoint is not None:
            checkpoint("shadow", None)
        return SynthesisMigrationReceipt(
            state=SynthesisMigrationState.SHADOW,
            assignment_digest=receipt.assignment_digest,
            assigned_rows=receipt.assigned_rows,
            total_rows=receipt.total_rows,
        )
    except Exception:
        _quarantine(con)
        raise


def verify_synthesis_migration(
    con: LockedConnection,
    *,
    assignments: Iterable[SynthesisAuthorityAssignment],
) -> SynthesisMigrationReceipt:
    con = _require_locked(con)
    rows = _normalized_assignments(assignments)
    digest = _assignment_digest(rows)
    for assignment in rows:
        stored, fingerprint = _source_row(con, assignment.synthesis_id)
        journal = con.execute(
            "SELECT target_account_digest, target_investigation_digest, "
            "source_fingerprint FROM synthesis_tenancy_migration_rows "
            "WHERE synthesis_id = ?",
            [assignment.synthesis_id],
        ).fetchone()
        expected = (
            assignment.authority.account_digest,
            assignment.authority.investigation_digest,
            fingerprint,
        )
        if journal != expected or (
            stored.get("account_digest"), stored.get("investigation_digest")
        ) != expected[:2]:
            raise SynthesisMigrationConflict("synthesis migration verification failed")
    total = int(con.execute("SELECT count(*) FROM syntheses").fetchone()[0])
    return SynthesisMigrationReceipt(
        state=(_manifest(con) or ("", SynthesisMigrationState.COPYING, ""))[1],
        assignment_digest=digest,
        assigned_rows=len(rows),
        total_rows=total,
    )


def activate_synthesis_migration(
    con: LockedConnection,
    *,
    assignments: Iterable[SynthesisAuthorityAssignment],
) -> None:
    con = _require_locked(con)
    manifest = _manifest(con)
    if manifest is None or manifest[1] is not SynthesisMigrationState.SHADOW:
        raise SynthesisMigrationConflict("synthesis migration is not shadow-verified")
    receipt = verify_synthesis_migration(con, assignments=assignments)
    if receipt.assigned_rows != receipt.total_rows:
        raise SynthesisMigrationConflict("synthesis migration coverage changed")
    _set_state(con, SynthesisMigrationState.SCOPED)


def rollback_synthesis_migration(con: LockedConnection) -> int:
    """Restore every journaled digest pair before scoped activation."""
    con = _require_locked(con)
    manifest = _manifest(con)
    if manifest is None or manifest[1] not in {
        SynthesisMigrationState.COPYING,
        SynthesisMigrationState.SHADOW,
        SynthesisMigrationState.QUARANTINED,
    }:
        raise SynthesisMigrationConflict("synthesis migration cannot be rolled back")
    rows = con.execute(
        "SELECT synthesis_id, original_account_digest, "
        "original_investigation_digest, target_account_digest, "
        "target_investigation_digest, source_fingerprint "
        "FROM synthesis_tenancy_migration_rows ORDER BY synthesis_id"
    ).fetchall()
    try:
        for row in rows:
            stored, fingerprint = _source_row(con, row[0])
            if fingerprint != row[5] or (
                stored.get("account_digest"), stored.get("investigation_digest")
            ) != (row[3], row[4]):
                raise SynthesisMigrationConflict("rollback verification failed")
            con.execute(
                "UPDATE syntheses SET account_digest = ?, investigation_digest = ? "
                "WHERE synthesis_id = ?",
                [row[1], row[2], row[0]],
            )
        _set_state(con, SynthesisMigrationState.ROLLED_BACK)
        return len(rows)
    except Exception:
        _quarantine(con)
        raise
