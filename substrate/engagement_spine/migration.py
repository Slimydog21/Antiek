"""Explicit owner assignment for legacy engagement-spine JSON stores.

Legacy rows remain quarantined from authenticated routes. This module copies
only structurally valid ownerless rows into one explicitly named account's
composite namespace and records enough provenance to remove those copies.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from substrate.floating_session.store import FileSessionStore, authorized_session_store

from .authority import ENGAGEMENT_AUTHORITY_VERSION, EngagementAuthority
from .store import FileEngagementStore, authorized_store

MigrationMode = Literal["dry-run", "apply", "rollback"]
_MIGRATION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


@dataclass(frozen=True)
class QuarantinedRow:
    path: str
    reason: str


@dataclass(frozen=True)
class LegacyInventory:
    spawns: int
    twins: int
    documents: int
    sessions: int
    quarantined: tuple[QuarantinedRow, ...]

    @property
    def total(self) -> int:
        return self.spawns + self.twins + self.documents + self.sessions

    def to_dict(self) -> dict[str, Any]:
        return {
            "spawns": self.spawns,
            "twins": self.twins,
            "documents": self.documents,
            "sessions": self.sessions,
            "total": self.total,
            "quarantined": [asdict(row) for row in self.quarantined],
        }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_json(path: Path, root: Path) -> Any:
    if path.is_symlink():
        raise ValueError("symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError("outside configured root")
    return json.loads(path.read_text(encoding="utf-8"))


def _legacy_rows(
    engagement_root: Path, session_root: Path
) -> tuple[dict[str, list[tuple[Path, dict[str, Any]]]], list[QuarantinedRow]]:
    groups: dict[str, list[tuple[Path, dict[str, Any]]]] = {
        "spawns": [],
        "twins": [],
        "documents": [],
        "sessions": [],
    }
    quarantined: list[QuarantinedRow] = []
    specs = (
        ("spawns", engagement_root / "spawns", "dict"),
        ("twins", engagement_root / "twins", "list"),
        ("documents", engagement_root / "docs", "dict"),
        ("sessions", session_root / "sessions", "dict"),
    )
    for kind, directory, shape in specs:
        if not directory.exists():
            continue
        root = engagement_root if kind != "sessions" else session_root
        for path in sorted(directory.glob("*.json")):
            try:
                decoded = _read_json(path, root)
                values = decoded if shape == "list" else [decoded]
                if not isinstance(values, list):
                    raise ValueError(f"expected {shape}")
                for value in values:
                    if not isinstance(value, dict):
                        raise ValueError("row is not an object")
                    if value.get("engagement_authority_version") is not None:
                        continue
                    groups[kind].append((path, dict(value)))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                quarantined.append(
                    QuarantinedRow(path=str(path), reason=f"{type(exc).__name__}: {exc}")
                )
    return groups, quarantined


def inventory_legacy_engagement(
    engagement_root: Path, session_root: Path | None = None
) -> LegacyInventory:
    engagement_root = Path(engagement_root)
    session_root = Path(session_root) if session_root is not None else engagement_root
    groups, quarantined = _legacy_rows(engagement_root, session_root)
    return LegacyInventory(
        spawns=len(groups["spawns"]),
        twins=len(groups["twins"]),
        documents=len(groups["documents"]),
        sessions=len(groups["sessions"]),
        quarantined=tuple(quarantined),
    )


def _tree_files(*roots: Path) -> set[str]:
    files: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                files.add(str(path.resolve()))
    return files


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, sort_keys=True, indent=2)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _manifest_path(engagement_root: Path, migration_id: str) -> Path:
    if not _MIGRATION_ID_RE.fullmatch(migration_id):
        raise ValueError("migration_id is invalid")
    return engagement_root / "migrations" / f"{migration_id}.json"


def migrate_legacy_engagement(
    *,
    engagement_root: Path,
    account_id: str,
    session_root: Path | None = None,
    mode: MigrationMode = "dry-run",
    migration_id: str | None = None,
) -> dict[str, Any]:
    """Inventory, copy, or roll back one explicit legacy owner assignment."""

    engagement_root = Path(engagement_root)
    session_root = Path(session_root) if session_root is not None else engagement_root
    authority = EngagementAuthority(account_id)
    if authority.account_id == "__operator__":
        raise ValueError("legacy migration requires a named authenticated account")
    digest = hashlib.sha256(
        f"{engagement_root.resolve()}:{session_root.resolve()}:{authority.account_digest}".encode()
    ).hexdigest()[:20]
    migration_id = migration_id or f"engagement-{digest}"
    manifest_path = _manifest_path(engagement_root, migration_id)

    if mode == "rollback":
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise FileNotFoundError(f"migration manifest not found: {migration_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("account_digest") != authority.account_digest:
            raise PermissionError("migration account does not match manifest")
        removed: list[str] = []
        for raw in manifest.get("created_files", []):
            path = Path(raw)
            allowed = any(
                path.resolve(strict=False).is_relative_to(root.resolve(strict=False))
                for root in (engagement_root, session_root)
            )
            if not allowed or path.is_symlink():
                raise RuntimeError("manifest contains unsafe created path")
            expected_hash = (manifest.get("created_file_sha256") or {}).get(str(path))
            if path.is_file() and expected_hash:
                actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    raise RuntimeError("migrated file changed after apply; rollback refused")
            if path.is_file():
                path.unlink()
                removed.append(str(path))
        manifest["state"] = "rolled_back"
        manifest["rolled_back_at"] = _utc_now()
        manifest["removed_files"] = removed
        _atomic_json(manifest_path, manifest)
        return manifest

    groups, quarantined = _legacy_rows(engagement_root, session_root)
    inventory = LegacyInventory(
        spawns=len(groups["spawns"]),
        twins=len(groups["twins"]),
        documents=len(groups["documents"]),
        sessions=len(groups["sessions"]),
        quarantined=tuple(quarantined),
    )
    report: dict[str, Any] = {
        "migration_id": migration_id,
        "mode": mode,
        "account_digest": authority.account_digest,
        "authority_version": ENGAGEMENT_AUTHORITY_VERSION,
        "inventory": inventory.to_dict(),
    }
    if mode == "dry-run":
        return report
    if mode != "apply":
        raise ValueError(f"unsupported migration mode: {mode}")
    if manifest_path.exists():
        raise FileExistsError(f"migration manifest already exists: {migration_id}")

    before = _tree_files(engagement_root, session_root)
    engagement = authorized_store(FileEngagementStore(engagement_root), authority)
    sessions = authorized_session_store(FileSessionStore(session_root), authority)
    applied = {"spawns": 0, "twins": 0, "documents": 0, "sessions": 0}
    apply_quarantine = list(quarantined)
    report.update(
        {
            "mode": "apply",
            "state": "applying",
            "applied_at": _utc_now(),
            "applied": applied,
            "quarantined": [],
            "created_files": [],
            "created_file_sha256": {},
        }
    )
    _atomic_json(manifest_path, report)

    def record_created(path: Path) -> None:
        resolved = str(path.resolve())
        if resolved not in before and resolved not in report["created_files"]:
            report["created_files"].append(resolved)
        if path.is_file() and not path.is_symlink():
            report["created_file_sha256"][resolved] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        report["applied"] = dict(applied)
        report["quarantined"] = [asdict(row) for row in apply_quarantine]
        _atomic_json(manifest_path, report)

    def record_intent(path: Path) -> None:
        resolved = str(path.resolve(strict=False))
        if resolved not in before and resolved not in report["created_files"]:
            report["created_files"].append(resolved)
            _atomic_json(manifest_path, report)

    def reject(path: Path, reason: str) -> None:
        apply_quarantine.append(QuarantinedRow(path=str(path), reason=reason))

    for path, row in groups["spawns"]:
        if not row.get("spawn_id") or not row.get("parent_asset_id"):
            reject(path, "spawn missing spawn_id or parent_asset_id")
            continue
        target_id = authority.storage_id("spawn", str(row["spawn_id"]))
        if engagement.base.get_spawn(target_id) is not None:
            reject(path, "spawn composite target already exists")
            continue
        record_intent(engagement.base._spawn_path(target_id))
        engagement.put_spawn(row)
        applied["spawns"] += 1
        record_created(engagement.base._spawn_path(target_id))
    for path, row in groups["twins"]:
        if not row.get("note_id") or not row.get("asset_id"):
            reject(path, "twin missing note_id or asset_id")
            continue
        target_asset = authority.storage_id("asset", str(row["asset_id"]))
        if any(
            existing.get("note_id") == row["note_id"]
            for existing in engagement.base.list_twins(target_asset)
        ):
            reject(path, "twin composite target already exists")
            continue
        record_intent(engagement.base._twin_path(target_asset))
        engagement.put_twin(row)
        applied["twins"] += 1
        record_created(engagement.base._twin_path(target_asset))
    for path, row in groups["documents"]:
        document_id = row.get("document_id")
        if not isinstance(document_id, str) or not document_id:
            reject(path, "document missing document_id")
            continue
        target_id = authority.storage_id("document", document_id)
        if engagement.base.get_document(target_id) is not None:
            reject(path, "document composite target already exists")
            continue
        record_intent(engagement.base._doc_path(target_id))
        engagement.put_document(document_id, row)
        applied["documents"] += 1
        record_created(engagement.base._doc_path(target_id))
    for path, row in groups["sessions"]:
        if not row.get("session_id") or not row.get("parent_asset_id"):
            reject(path, "session missing session_id or parent_asset_id")
            continue
        target_id = authority.storage_id("session", str(row["session_id"]))
        if sessions.base.get_session(target_id) is not None:
            reject(path, "session composite target already exists")
            continue
        record_intent(sessions.base._session_path(target_id))
        sessions.put_session(row)
        applied["sessions"] += 1
        record_created(sessions.base._session_path(target_id))

    created = sorted(
        path
        for path in (_tree_files(engagement_root, session_root) - before)
        if path != str(manifest_path.resolve())
    )
    report.update(
        {
            "state": "applied",
            "applied": applied,
            "quarantined": [asdict(row) for row in apply_quarantine],
            "created_files": created,
            "created_file_sha256": {
                path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                for path in created
                if Path(path).is_file() and not Path(path).is_symlink()
            },
        }
    )
    _atomic_json(manifest_path, report)
    return report


__all__ = [
    "LegacyInventory",
    "MigrationMode",
    "QuarantinedRow",
    "inventory_legacy_engagement",
    "migrate_legacy_engagement",
]
