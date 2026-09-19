"""Redacted operator CLI for explicit synthesis authority migration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

import duckdb

from runtime.db_lock import connect_write
from substrate.investigation_tenancy import InvestigationAuthority, default_tenancy_root
from substrate.synthesis_tenancy_migration import (
    SynthesisAuthorityAssignment,
    activate_synthesis_migration,
    migrate_synthesis_authority,
    rollback_synthesis_migration,
    verify_synthesis_migration,
)

_MAX_ASSIGNMENT_BYTES = 16 * 1024 * 1024
_MAX_ASSIGNMENTS = 1_000_000
_CONFIRM_ACTIVATION = "activate-synthesis-tenancy-v1"


def _read_assignment_rows(path: Path) -> list[dict[str, str]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("assignment file is unavailable or unsafe") from exc
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_size > _MAX_ASSIGNMENT_BYTES
        ):
            raise ValueError("assignment file is unavailable or unsafe")
        raw = os.read(fd, _MAX_ASSIGNMENT_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) > _MAX_ASSIGNMENT_BYTES:
        raise ValueError("assignment file exceeds size limit")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("assignment file is invalid") from exc
    if not isinstance(payload, list) or not 1 <= len(payload) <= _MAX_ASSIGNMENTS:
        raise ValueError("assignment file has invalid row count")
    expected_keys = {"synthesis_id", "account_id", "investigation_id"}
    rows: list[dict[str, str]] = []
    for value in payload:
        if not isinstance(value, dict) or set(value) != expected_keys:
            raise ValueError("assignment row shape is invalid")
        row: dict[str, str] = {}
        for key in sorted(expected_keys):
            item = value[key]
            if (
                not isinstance(item, str)
                or not item
                or item != item.strip()
                or len(item) > 512
                or any(ord(character) < 32 for character in item)
            ):
                raise ValueError("assignment row value is invalid")
            row[key] = item
        rows.append(row)
    if len({row["synthesis_id"] for row in rows}) != len(rows):
        raise ValueError("assignment file contains duplicate synthesis ids")
    return sorted(rows, key=lambda row: row["synthesis_id"])


def _plan(db_path: Path, rows: list[dict[str, str]]) -> dict[str, Any]:
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    assignment_digest = hashlib.sha256(canonical).hexdigest()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        total = int(con.execute("SELECT count(*) FROM syntheses").fetchone()[0])
        matched = 0
        display_mismatches = 0
        for row in rows:
            stored = con.execute(
                "SELECT investigation_id, account_digest, investigation_digest "
                "FROM syntheses WHERE synthesis_id = ?",
                [row["synthesis_id"]],
            ).fetchone()
            if stored is not None:
                matched += 1
                if stored[0] != row["investigation_id"]:
                    display_mismatches += 1
        return {
            "state": "plan",
            "assignment_digest": assignment_digest,
            "assignment_rows": len(rows),
            "database_rows": total,
            "matched_rows": matched,
            "missing_rows": len(rows) - matched,
            "unassigned_rows": max(0, total - matched),
            "display_mismatches": display_mismatches,
            "ready": (
                len(rows) == total == matched and display_mismatches == 0
            ),
        }
    finally:
        con.close()


def _assignments(
    rows: list[dict[str, str]], root: Path
) -> tuple[SynthesisAuthorityAssignment, ...]:
    return tuple(
        SynthesisAuthorityAssignment(
            row["synthesis_id"],
            InvestigationAuthority(
                row["account_id"], row["investigation_id"], root=root
            ),
        )
        for row in rows
    )


def _status(db_path: Path) -> dict[str, Any]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        manifest = con.execute(
            "SELECT state, assignment_digest FROM "
            "synthesis_tenancy_migration_manifest "
            "WHERE singleton_key = 'synthesis-tenancy-v1'"
        ).fetchone()
        journaled = int(
            con.execute(
                "SELECT count(*) FROM synthesis_tenancy_migration_rows"
            ).fetchone()[0]
        )
        total = int(con.execute("SELECT count(*) FROM syntheses").fetchone()[0])
        scoped = int(
            con.execute(
                "SELECT count(*) FROM syntheses WHERE account_digest IS NOT NULL "
                "AND investigation_digest IS NOT NULL"
            ).fetchone()[0]
        )
        return {
            "state": manifest[0] if manifest else "not_started",
            "assignment_digest": manifest[1] if manifest else None,
            "journaled_rows": journaled,
            "database_rows": total,
            "scoped_rows": scoped,
        }
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan, migrate, verify, activate, or roll back synthesis tenancy"
    )
    parser.add_argument("action", choices=("plan", "status", "migrate", "verify", "activate", "rollback"))
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--assignments", type=Path)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--approve-migration", action="store_true")
    parser.add_argument("--approve-rollback", action="store_true")
    parser.add_argument("--confirm-activation")
    args = parser.parse_args(argv)
    db_path = args.db_path.expanduser().resolve()
    root = (args.root or default_tenancy_root()).expanduser().resolve()

    if args.action == "status":
        print(json.dumps(_status(db_path), sort_keys=True))
        return 0
    if args.action != "rollback" and args.assignments is None:
        parser.error(f"{args.action} requires --assignments")
    rows = (
        _read_assignment_rows(args.assignments.expanduser().absolute())
        if args.assignments is not None
        else []
    )
    if args.action == "plan":
        receipt = _plan(db_path, rows)
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt["ready"] else 1

    assignments = _assignments(rows, root) if rows else ()
    if args.action == "migrate" and not args.approve_migration:
        parser.error("migrate requires --approve-migration")
    if args.action == "rollback" and not args.approve_rollback:
        parser.error("rollback requires --approve-rollback")
    if args.action == "activate" and args.confirm_activation != _CONFIRM_ACTIVATION:
        parser.error(
            f"activate requires --confirm-activation {_CONFIRM_ACTIVATION}"
        )

    with connect_write(str(db_path), purpose=f"synthesis-tenancy:{args.action}") as con:
        if args.action == "migrate":
            result = migrate_synthesis_authority(con, assignments)
            receipt = {
                "state": result.state.value,
                "assignment_digest": result.assignment_digest,
                "assigned_rows": result.assigned_rows,
                "database_rows": result.total_rows,
            }
        elif args.action == "verify":
            result = verify_synthesis_migration(con, assignments=assignments)
            receipt = {
                "state": result.state.value,
                "assignment_digest": result.assignment_digest,
                "assigned_rows": result.assigned_rows,
                "database_rows": result.total_rows,
            }
        elif args.action == "activate":
            activate_synthesis_migration(con, assignments=assignments)
            receipt = {
                "state": "scoped",
                "assignment_digest": con.execute(
                    "SELECT assignment_digest FROM "
                    "synthesis_tenancy_migration_manifest "
                    "WHERE singleton_key = 'synthesis-tenancy-v1'"
                ).fetchone()[0],
                "database_rows": int(
                    con.execute("SELECT count(*) FROM syntheses").fetchone()[0]
                ),
            }
        else:
            receipt = {
                "state": "rolled_back",
                "rolled_back_rows": rollback_synthesis_migration(con),
            }
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
