#!/usr/bin/env python3
"""Owner-namespace migration — re-own legacy ``__operator__`` settings rows
to the stable opaque owner derived from ONE verified operator e-mail.

Implements the data half of DECISION-REQUIRED-owner-namespace.md Option A:
``settings_models_admin.request_owner_user_id`` now resolves the derived
per-person owner, so every record written under the legacy ``__operator__``
sentinel must be explicitly re-owned or it becomes invisible. This tool is
that migration. It is ONE-WAY (there is no reverse flag), DRY-RUN BY DEFAULT
(``--apply`` is required to write), and AUDITABLE (every row moved is printed
with its store, table and key).

Stores re-owned (enumerated by tracing the 24 ``request_owner_user_id`` call
sites across settings_models_admin, byot_usage_routes, settings_lineup,
settings_budget, settings_compute_capacity / compute_capacity_gate,
oauth_routes, settings_tiers and settings_privacy):

  1. user-model registry JSON — ``owner_user_id`` on each record; the record
     id is re-namespaced (``user-<hash>-<slug>``) and its BYOK credential is
     re-sealed under the v3 owner binding for the new owner + handle.
  2. BYOK artifact — ``oauth:*`` and ``provider:<handle>`` credentials whose
     owner is the legacy sentinel are re-sealed to the derived owner.
  3. BYOT usage sqlite — ``byot_key_usage`` and ``byot_operation_journal``.
  4. lineup JSON sidecar — the ``owners`` map key.
  5. graph DuckDB — ``owner_compute_capacity``, ``owner_compute_acu_ledger``
     and ``chunk_tier_overrides.set_by``.
  6. telemetry preferences sqlite — ``user_telemetry_preferences.user_id``.
  7. connected BYO tools JSON (``settings_tool_connections``, read by
     ``research_tool_search``) — each row moves to the key hashed from the
     derived owner and its ``connector_<vendor>`` credential is re-sealed to
     that owner. The old credentials are queued as the registry's own
     pending deletions in the same write that moves the rows, so a run
     interrupted after that write is finished by the registry's recovery; an
     error before it deletes the re-sealed copies and writes nothing.

REFUSALS (fail-closed, no partial silent migration):

  * the stores contain rows for more than one legacy (non-derived) owner —
    re-owning everything to one e-mail would misassign a second person's
    data;
  * the target owner already holds conflicting rows (same record id, key id,
    operation id, capacity row, lineup entry, preference surface or tool
    vendor);
  * a legacy tool connection's stored credential is not bound to that row
    (owner, kind, handle, fingerprint), so re-sealing it could hand someone
    else's secret to the target owner;
  * ``--email`` does not derive (``derive_owner_from_verified_email``
    returns None).

Stop the API process before ``--apply``: the registry/artifact file locks are
per-process advisory locks, and the DuckDB single-writer rule applies.

Usage::

    # preview every move, write nothing
    python -m tools.migrate_owner_namespace --email operator@example.com

    # perform the one-way migration
    python -m tools.migrate_owner_namespace --email operator@example.com --apply
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import (  # noqa: E402
    settings_lineup,
    settings_privacy,
)
from interfaces.research.api import settings_models_admin as models_admin  # noqa: E402
from interfaces.research.api.account_memory_identity import (  # noqa: E402
    OPERATOR_STORAGE_SENTINEL,
    derive_owner_from_verified_email,
)
from runtime.byok.store import (  # noqa: E402
    CredentialIntegrityError,
    CredentialMetadata,
    delete_credential,
    list_credentials,
    load_credential,
    store_credential,
    store_credential_with_metadata,
)
from runtime.connectors import registry as connectors  # noqa: E402
from runtime.db_lock import (  # noqa: E402
    LockedConnection,
    ReadConnection,
    connect_read,
    connect_write,
)
from substrate.byot_usage.ledger import default_byot_usage_db_path  # noqa: E402
from substrate.graph import default_db_path  # noqa: E402

logger = logging.getLogger("tools.migrate_owner_namespace")

LEGACY_OWNER = OPERATOR_STORAGE_SENTINEL  # "__operator__"
_DERIVED_OWNER_RE = re.compile(r"acct_[0-9a-f]{32}")
_MODEL_PROVIDER_KIND = "model_provider"

_LOCK_TIMEOUT_S = 30.0


class MigrationRefused(RuntimeError):
    """The registry/store set is unsafe to migrate; nothing was written."""


@dataclass(frozen=True, slots=True)
class Move:
    """One audited row move: store, table, row key, old → new owner."""

    store: str
    table: str
    key: str
    note: str = ""


@dataclass
class MigrationReport:
    target_owner: str = ""
    moves: list[Move] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    applied: bool = False


# ---------------------------------------------------------------------------
# Legacy-owner plurality: re-owning is only meaningful when ONE person owns
# every legacy row. Any second non-derived owner (another sentinel, a genuine
# per-user id) means the data is already multi-person and this tool would
# misassign it.
# ---------------------------------------------------------------------------


def _check_legacy_owners(owners: set[str], source: str) -> None:
    legacy = {o for o in owners if o != LEGACY_OWNER and not _DERIVED_OWNER_RE.fullmatch(o)}
    if legacy:
        raise MigrationRefused(
            f"{source} contains rows for non-derived owner(s) {sorted(legacy)!r} "
            f"alongside {LEGACY_OWNER!r}: more than one legacy owner means the "
            "data is already multi-person; refusing to guess who owns what"
        )


def _check_no_target_conflict(conflicts: list[str], source: str) -> None:
    if conflicts:
        raise MigrationRefused(
            f"{source}: target owner already holds conflicting row(s) "
            f"{conflicts!r}; refusing to overwrite or merge another owner's data"
        )


# ---------------------------------------------------------------------------
# Per-store planners (read-only) and appliers
# ---------------------------------------------------------------------------


def _plan_user_models(report: MigrationReport) -> None:
    registry = models_admin._load_registry()
    if not registry:
        report.skipped.append("user-model registry: empty or absent")
        return
    _check_legacy_owners({r.owner_user_id for r in registry.values()}, "user-model registry")
    legacy_records = [r for r in registry.values() if r.owner_user_id == LEGACY_OWNER]
    conflicts = []
    for record in legacy_records:
        slug = record.id.removeprefix(models_admin._ID_PREFIX)
        new_id = models_admin._owner_id_prefix(report.target_owner) + slug
        if new_id in registry:
            conflicts.append(new_id)
        else:
            report.moves.append(
                Move("user_models.json", "registry", f"{record.id} -> {new_id}")
            )
    _check_no_target_conflict(conflicts, "user-model registry")


def _apply_user_models(report: MigrationReport) -> None:
    with models_admin._registry_guard(exclusive=True):
        registry = models_admin._load_registry_unlocked()
        for record in list(registry.values()):
            if record.owner_user_id != LEGACY_OWNER:
                continue
            slug = record.id.removeprefix(models_admin._ID_PREFIX)
            new_id = models_admin._owner_id_prefix(report.target_owner) + slug
            # Re-seal the credential under the v3 binding for the new owner +
            # handle. Decrypt-then-restore is the only way: the SecretBox key
            # is bound to (owner, handle). Plaintext never leaves this scope.
            plaintext: str | None = None
            try:
                plaintext = load_credential(record.cred_ref).reveal()
                new_ref = store_credential(
                    new_id,
                    plaintext,
                    pipeline_kind=_MODEL_PROVIDER_KIND,
                    owner_user_id=report.target_owner,
                )
                new_meta = {m.cred_id: m for m in list_credentials()}[new_ref]
                delete_credential(record.cred_ref)
                cred_update: dict[str, str | None] = {
                    "cred_ref": new_ref,
                    "cred_fingerprint": new_meta.artifact_fingerprint,
                }
            except (KeyError, CredentialIntegrityError):
                # The credential is already gone; the record is inert either
                # way. Re-own the row, keep the dangling ref, say so.
                logger.warning(
                    "user_models.json registry: %s has no stored credential; "
                    "re-owning the row without re-sealing", record.id,
                )
                cred_update = {}
            finally:
                plaintext = None
            del registry[record.id]
            registry[new_id] = record.model_copy(
                update={
                    "id": new_id,
                    "owner_user_id": report.target_owner,
                    **cred_update,
                }
            )
            logger.info(
                "user_models.json registry: %s -> %s (owner %s -> %s, cred re-sealed)",
                record.id, new_id, LEGACY_OWNER, report.target_owner,
            )
        models_admin._write_registry_unlocked(registry)


def _byok_reown_candidates() -> tuple[list[CredentialMetadata], list[str]]:
    """OAuth + dispatch-provider credentials still owned by the sentinel.

    Model-provider credentials are re-sealed with their registry record
    (their handle is the record id, which changes), so they are excluded
    here. v1/v2 credentials carry no owner and are out of scope: the v2
    model-provider case is re-sealed with its record, and ownerless oauth/
    provider credentials were already invisible to any owner-keyed lookup.
    """
    candidates = []
    skipped: list[str] = []
    for meta in list_credentials():
        kind = meta.pipeline_kind or ""
        if kind == _MODEL_PROVIDER_KIND:
            continue
        if not (kind.startswith("oauth") or kind.startswith("provider:")):
            continue
        if meta.owner_user_id == LEGACY_OWNER:
            candidates.append(meta)
        elif meta.owner_user_id is not None and not _DERIVED_OWNER_RE.fullmatch(
            meta.owner_user_id
        ):
            skipped.append(f"byok:{meta.cred_id} owner={meta.owner_user_id!r}")
    return candidates, skipped


def _plan_byok(report: MigrationReport) -> None:
    candidates, other_legacy = _byok_reown_candidates()
    if other_legacy:
        raise MigrationRefused(
            f"byok artifact holds oauth/provider credentials for non-derived "
            f"owner(s) {other_legacy!r}; refusing (more than one legacy owner)"
        )
    target_owned = {
        (m.pipeline_kind, m.account_handle)
        for m in list_credentials()
        if m.owner_user_id == report.target_owner
    }
    conflicts = [
        f"{m.pipeline_kind}/{m.account_handle}"
        for m in candidates
        if (m.pipeline_kind, m.account_handle) in target_owned
    ]
    _check_no_target_conflict(conflicts, "byok artifact")
    for meta in candidates:
        report.moves.append(
            Move("byok artifact", meta.pipeline_kind or "", meta.account_handle or meta.cred_id)
        )


def _apply_byok(report: MigrationReport) -> None:
    candidates, _ = _byok_reown_candidates()
    for meta in candidates:
        plaintext: str | None = None
        try:
            plaintext = load_credential(meta.cred_id).reveal()
            store_credential(
                meta.account_handle or meta.cred_id,
                plaintext,
                pipeline_kind=meta.pipeline_kind,
                owner_user_id=report.target_owner,
            )
        finally:
            plaintext = None
        delete_credential(meta.cred_id)
        logger.info(
            "byok artifact: %s/%s owner %s -> %s (re-sealed, old cred %s deleted)",
            meta.pipeline_kind, meta.account_handle, LEGACY_OWNER,
            report.target_owner, meta.cred_id,
        )


def _plan_byot_usage(report: MigrationReport) -> None:
    path = default_byot_usage_db_path()
    if not path.exists():
        report.skipped.append(f"byot usage ledger: {path} absent")
        return
    con = sqlite3.connect(str(path))
    try:
        owners = {
            row[0]
            for row in con.execute(
                "SELECT DISTINCT owner_user_id FROM byot_key_usage "
                "UNION SELECT DISTINCT owner_user_id FROM byot_operation_journal"
            )
        }
        _check_legacy_owners(owners, "byot usage ledger")
        usage_keys = [
            row[0]
            for row in con.execute(
                "SELECT api_key_id FROM byot_key_usage WHERE owner_user_id = ?", (LEGACY_OWNER,)
            )
        ]
        conflicts = [
            f"byot_key_usage/{key}"
            for key in usage_keys
            if con.execute(
                "SELECT 1 FROM byot_key_usage WHERE owner_user_id = ? AND api_key_id = ?",
                (report.target_owner, key),
            ).fetchone()
        ]
        ops = [
            row[0]
            for row in con.execute(
                "SELECT operation_id FROM byot_operation_journal WHERE owner_user_id = ?",
                (LEGACY_OWNER,),
            )
        ]
        conflicts += [
            f"byot_operation_journal/{op}"
            for op in ops
            if con.execute(
                "SELECT 1 FROM byot_operation_journal WHERE owner_user_id = ? AND operation_id = ?",
                (report.target_owner, op),
            ).fetchone()
        ]
        _check_no_target_conflict(conflicts, "byot usage ledger")
        for key in usage_keys:
            report.moves.append(Move(path.name, "byot_key_usage", key))
        for op in ops:
            report.moves.append(Move(path.name, "byot_operation_journal", op))
    finally:
        con.close()


def _apply_byot_usage(report: MigrationReport) -> None:
    path = default_byot_usage_db_path()
    if not path.exists():
        return
    con = sqlite3.connect(str(path))
    try:
        for table in ("byot_key_usage", "byot_operation_journal"):
            cur = con.execute(
                f"UPDATE {table} SET owner_user_id = ? WHERE owner_user_id = ?",
                (report.target_owner, LEGACY_OWNER),
            )
            if cur.rowcount:
                logger.info(
                    "%s %s: %d row(s) owner %s -> %s",
                    path.name, table, cur.rowcount, LEGACY_OWNER, report.target_owner,
                )
        con.commit()
    finally:
        con.close()


def _plan_lineup(report: MigrationReport) -> None:
    registry = settings_lineup._load_registry()
    owners = registry.get("owners", {})
    if not isinstance(owners, dict) or not owners:
        report.skipped.append("lineup registry: empty or absent")
        return
    _check_legacy_owners(set(owners), "lineup registry")
    if LEGACY_OWNER not in owners:
        return
    _check_no_target_conflict(
        [report.target_owner] if report.target_owner in owners else [],
        "lineup registry",
    )
    report.moves.append(Move("lineup.json", "owners", LEGACY_OWNER))


def _apply_lineup(report: MigrationReport) -> None:
    registry = settings_lineup._load_registry()
    owners = registry.get("owners", {})
    if LEGACY_OWNER not in owners:
        return
    owners[report.target_owner] = owners.pop(LEGACY_OWNER)
    registry["owners"] = owners
    settings_lineup._write_registry_unlocked(registry)
    logger.info("lineup.json owners: %s -> %s", LEGACY_OWNER, report.target_owner)


def _duckdb_tables(con: ReadConnection | LockedConnection) -> set[str]:
    return {
        row[0]
        for row in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
    }


def _plan_duckdb(report: MigrationReport) -> None:
    db = os.path.expanduser(default_db_path())
    if not os.path.exists(db):
        report.skipped.append(f"graph DuckDB: {db} absent")
        return
    con = connect_read(db)
    try:
        tables = _duckdb_tables(con)
        if "owner_compute_capacity" in tables:
            owners = {
                row[0]
                for row in con.execute(
                    "SELECT owner_user_id FROM owner_compute_capacity"
                ).fetchall()
            }
            _check_legacy_owners(owners, "owner_compute_capacity")
            if LEGACY_OWNER in owners:
                _check_no_target_conflict(
                    [report.target_owner] if report.target_owner in owners else [],
                    "owner_compute_capacity",
                )
                report.moves.append(Move(Path(db).name, "owner_compute_capacity", LEGACY_OWNER))
        if "owner_compute_acu_ledger" in tables:
            rows = con.execute(
                "SELECT investigation_id, owner_user_id FROM owner_compute_acu_ledger"
            ).fetchall()
            _check_legacy_owners({r[1] for r in rows}, "owner_compute_acu_ledger")
            for investigation_id, owner in rows:
                if owner == LEGACY_OWNER:
                    report.moves.append(
                        Move(Path(db).name, "owner_compute_acu_ledger", investigation_id)
                    )
        if "chunk_tier_overrides" in tables:
            rows = con.execute(
                "SELECT chunk_id, set_at, set_by FROM chunk_tier_overrides"
            ).fetchall()
            _check_legacy_owners({r[2] for r in rows}, "chunk_tier_overrides.set_by")
            for chunk_id, set_at, set_by in rows:
                if set_by == LEGACY_OWNER:
                    report.moves.append(
                        Move(
                            Path(db).name,
                            "chunk_tier_overrides.set_by",
                            f"{chunk_id}@{set_at}",
                        )
                    )
    finally:
        con.close()


def _apply_duckdb(report: MigrationReport) -> None:
    db = os.path.expanduser(default_db_path())
    if not os.path.exists(db):
        return
    with connect_write(db, purpose="tools/migrate-owner-namespace", timeout_s=_LOCK_TIMEOUT_S) as con:
        tables = _duckdb_tables(con)
        # (table, owner column) — duckdb's rowcount is unreliable for UPDATE,
        # so count the matching rows first for the audit line.
        for table, column in (
            ("owner_compute_capacity", "owner_user_id"),
            ("owner_compute_acu_ledger", "owner_user_id"),
            ("chunk_tier_overrides", "set_by"),
        ):
            if table not in tables:
                continue
            count = con.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", [LEGACY_OWNER]
            ).fetchone()[0]
            if not count:
                continue
            con.execute(
                f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                [report.target_owner, LEGACY_OWNER],
            )
            logger.info(
                "%s %s.%s: %d row(s) owner %s -> %s",
                Path(db).name, table, column, count, LEGACY_OWNER, report.target_owner,
            )


def _plan_telemetry(report: MigrationReport) -> None:
    path = settings_privacy.default_telemetry_preferences_db_path()
    if path is None or not path.exists():
        report.skipped.append("telemetry preferences: no sqlite store (absent or in-memory)")
        return
    con = sqlite3.connect(str(path))
    try:
        owners = {
            row[0]
            for row in con.execute("SELECT DISTINCT user_id FROM user_telemetry_preferences")
        }
        _check_legacy_owners(owners, "telemetry preferences")
        surfaces = [
            row[0]
            for row in con.execute(
                "SELECT surface_name FROM user_telemetry_preferences WHERE user_id = ?",
                (LEGACY_OWNER,),
            )
        ]
        conflicts = [
            surface
            for surface in surfaces
            if con.execute(
                "SELECT 1 FROM user_telemetry_preferences WHERE user_id = ? AND surface_name = ?",
                (report.target_owner, surface),
            ).fetchone()
        ]
        _check_no_target_conflict(conflicts, "telemetry preferences")
        for surface in surfaces:
            report.moves.append(Move(path.name, "user_telemetry_preferences", surface))
    finally:
        con.close()


def _apply_telemetry(report: MigrationReport) -> None:
    path = settings_privacy.default_telemetry_preferences_db_path()
    if path is None or not path.exists():
        return
    con = sqlite3.connect(str(path))
    try:
        cur = con.execute(
            "UPDATE user_telemetry_preferences SET user_id = ? WHERE user_id = ?",
            (report.target_owner, LEGACY_OWNER),
        )
        con.commit()
        if cur.rowcount:
            logger.info(
                "%s user_telemetry_preferences: %d row(s) owner %s -> %s",
                path.name, cur.rowcount, LEGACY_OWNER, report.target_owner,
            )
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Connected BYO tools. The registry hashes the owner into each row's key, so
# re-owning a row means moving it to a new key; the credential is bound to
# (owner, kind, handle), so it has to be re-sealed with the row or
# ``_metadata_matches`` reads the connection as tampered. ``account_handle``
# stays as it was: the registry compares it between row and credential, and
# keeping both sides on the old value keeps them equal.
# ---------------------------------------------------------------------------

_ToolMove = tuple[str, str, connectors.ToolConnectionRecord]


def _legacy_tool_connections(
    records: dict[str, connectors.ToolConnectionRecord], target_owner: str
) -> list[_ToolMove]:
    """``(old key, new key, row)`` for every sentinel-owned connection, checked."""
    _check_legacy_owners({r.owner_user_id for r in records.values()}, "tool connections")
    metadata = {m.cred_id: m for m in list_credentials()}
    moves: list[_ToolMove] = []
    conflicts: list[str] = []
    unbound: list[str] = []
    for key, record in records.items():
        if record.owner_user_id != LEGACY_OWNER:
            continue
        new_key = connectors._record_key(target_owner, record.vendor)
        if new_key in records:
            conflicts.append(f"{record.vendor}/{new_key}")
            continue
        meta = metadata.get(record.cred_id)
        if meta is not None and not connectors._metadata_matches(record, meta):
            unbound.append(f"{record.vendor}/{record.cred_id}")
        moves.append((key, new_key, record))
    _check_no_target_conflict(conflicts, "tool connections")
    if unbound:
        raise MigrationRefused(
            f"tool connections: stored credential(s) {unbound!r} are not bound to "
            f"their {LEGACY_OWNER!r} row; refusing to re-seal a secret whose owner "
            "cannot be proven"
        )
    return moves


def _plan_tool_connections(report: MigrationReport) -> None:
    path = connectors._path()
    if not path.exists():
        report.skipped.append(f"tool connections: {path} absent")
        return
    with connectors._guard(exclusive=False):
        records, _pending = connectors._load_unlocked()
    if not records:
        report.skipped.append("tool connections: empty")
        return
    for key, new_key, record in _legacy_tool_connections(records, report.target_owner):
        report.moves.append(
            Move("tool_connections.json", "registry", f"{record.vendor}: {key} -> {new_key}")
        )


def _apply_tool_connections(report: MigrationReport) -> None:
    if not connectors._path().exists():
        return
    with connectors._guard(exclusive=True):
        records, pending = connectors._load_unlocked()
        moves = _legacy_tool_connections(records, report.target_owner)
        if not moves:
            return
        stored = {m.cred_id for m in list_credentials()}
        resealed: list[str] = []
        retired: list[connectors.PendingDeletion] = []
        try:
            for key, new_key, record in moves:
                cred_id, fingerprint = record.cred_id, record.credential_fingerprint
                if record.cred_id in stored:
                    # Decrypt-then-restore is the only route: the SecretBox key
                    # is bound to (owner, handle). Plaintext never leaves here.
                    plaintext: str | None = None
                    try:
                        plaintext = load_credential(record.cred_id).reveal()
                        meta = store_credential_with_metadata(
                            record.account_handle,
                            plaintext,
                            pipeline_kind=f"connector_{record.vendor}",
                            owner_user_id=report.target_owner,
                        )
                    finally:
                        plaintext = None
                    resealed.append(meta.cred_id)
                    retired.append(connectors._pending_for(record))
                    cred_id, fingerprint = meta.cred_id, meta.artifact_fingerprint
                else:
                    logger.warning(
                        "tool_connections.json: %s has no stored credential; "
                        "re-owning the row without re-sealing (it stays degraded)", key,
                    )
                del records[key]
                records[new_key] = replace(
                    record,
                    owner_user_id=report.target_owner,
                    cred_id=cred_id,
                    credential_fingerprint=fingerprint,
                )
                logger.info(
                    "tool_connections.json: %s %s -> %s (owner %s -> %s%s)",
                    record.vendor, key, new_key, LEGACY_OWNER, report.target_owner,
                    ", cred re-sealed" if cred_id != record.cred_id else "",
                )
            connectors._write_unlocked(records, [*pending, *retired])
        except Exception:
            for new_cred_id in resealed:
                delete_credential(new_cred_id)
            raise
        # The rows now point at the re-sealed credentials and the old ones are
        # queued for deletion, so a crash from here is finished by the
        # registry's own recovery. Delete them now and clear the queue.
        for item in retired:
            delete_credential(item.cred_id)
        connectors._write_unlocked(records, pending)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

_PLANNERS = (
    _plan_user_models, _plan_byok, _plan_byot_usage, _plan_lineup, _plan_duckdb,
    _plan_telemetry, _plan_tool_connections,
)
_APPLIERS = (
    _apply_user_models, _apply_byok, _apply_byot_usage, _apply_lineup, _apply_duckdb,
    _apply_telemetry, _apply_tool_connections,
)


def run_migration(email: str, *, apply: bool = False) -> MigrationReport:
    """Plan (and, with ``apply=True``, perform) the one-way re-owning.

    The plan phase is fully read-only and never decrypts key material; the
    apply phase re-runs the planners first, so a store that changed between
    dry-run and apply is re-validated before anything is written.
    """
    target = derive_owner_from_verified_email(email)
    if target is None:
        raise MigrationRefused(
            f"--email {email!r} does not derive an owner; pass the exact "
            "verified operator address used at login"
        )
    report = MigrationReport(target_owner=target)
    for planner in _PLANNERS:
        planner(report)
    if not apply:
        return report
    # Re-validate immediately before writing, then apply store by store.
    fresh = MigrationReport(target_owner=target)
    for planner in _PLANNERS:
        planner(fresh)
    fresh.applied = True
    for applier in _APPLIERS:
        applier(fresh)
    return fresh


def _print_report(report: MigrationReport, email: str, *, apply: bool) -> None:
    prefix = "" if apply else "[DRY RUN] "
    print(f"\n{prefix}owner-namespace migration")
    print(f"  email:        {email}")
    print(f"  target owner: {report.target_owner}")
    print(f"  legacy owner: {LEGACY_OWNER!r}")
    if report.moves:
        print(f"\n{prefix}rows to re-own ({len(report.moves)}):")
        for move in report.moves:
            print(f"  {move.store} | {move.table} | {move.key}")
    else:
        print(f"\n{prefix}no {LEGACY_OWNER!r} rows found in any store — nothing to do")
    if report.skipped:
        print("\nskipped stores:")
        for note in report.skipped:
            print(f"  {note}")
    if not apply and report.moves:
        print(f"\n{'─' * 60}")
        print("Dry run only — nothing was written. Re-run with --apply to migrate.")
        print("Stop the API process first (DuckDB single-writer rule).")
        print("This migration is ONE-WAY; there is no reverse.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.migrate_owner_namespace",
        description=(
            "One-way migration: re-own every legacy '__operator__' settings "
            "record to the opaque owner derived from ONE verified operator "
            "e-mail. Dry-run by default; --apply writes."
        ),
    )
    p.add_argument(
        "--email",
        required=True,
        help="The operator's verified login address; its derived owner becomes "
        "the new owner of every legacy record",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform the migration (default: dry-run, print only)",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    try:
        report = run_migration(args.email, apply=args.apply)
    except MigrationRefused as exc:
        print(f"error: migration refused: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: migration failed: {exc}", file=sys.stderr)
        return 1
    _print_report(report, args.email, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
