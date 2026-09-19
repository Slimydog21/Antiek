"""Immutable, owner-qualified ordered collective manifests."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from .authority import owner_qualified_id
from .collective import _collective_id, merge_spawns_collective
from .store import AuthorizedEngagementStore

MANIFEST_VERSION = 1


class CollectiveManifestNotFound(KeyError):
    pass


class CollectiveManifestUnavailable(RuntimeError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _ordered_ids(spawn_ids: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(spawn_ids, (list, tuple)):
        raise ValueError("spawn_ids must be a list")
    if any(not isinstance(value, str) for value in spawn_ids):
        raise ValueError("spawn_ids must contain strings")
    ids = tuple(value.strip() for value in spawn_ids)
    if not 1 <= len(ids) <= 32 or any(
        not value
        or value != original
        or len(value.encode("utf-8")) > 512
        or any(unicodedata.category(character) == "Cc" for character in value)
        for value, original in zip(ids, spawn_ids, strict=True)
    ):
        raise ValueError("spawn_ids must contain 1-32 identifiers")
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate spawn_id is not allowed")
    return ids


@dataclass(frozen=True)
class CollectiveManifest:
    document_id: str
    manifest_id: str
    collective_id: str
    ordered_spawn_ids: tuple[str, ...]
    membership_sha256: str
    created_at: str

    def document(self) -> dict[str, Any]:
        return {
            "kind": "collective_manifest",
            "version": MANIFEST_VERSION,
            "document_id": self.document_id,
            "manifest_id": self.manifest_id,
            "collective_id": self.collective_id,
            "ordered_spawn_ids": list(self.ordered_spawn_ids),
            "membership_sha256": self.membership_sha256,
            "created_at": self.created_at,
        }

    def receipt(self, availability: Literal["ready", "unavailable"] = "ready") -> dict[str, Any]:
        return {
            "schema_version": 1,
            "manifest_id": self.manifest_id,
            "collective_id": self.collective_id,
            "ordered_spawn_ids": list(self.ordered_spawn_ids),
            "membership_sha256": self.membership_sha256,
            "availability": availability,
            "view_format": "html",
        }


def _identity(store: AuthorizedEngagementStore, ids: tuple[str, ...]) -> tuple[str, str, str]:
    collective_id = _collective_id(ids, authority=store.authority)
    membership_sha256 = _sha({"version": 1, "spawn_ids": sorted(ids)})
    manifest_id = owner_qualified_id(
        store.authority, "cmanifest", str(MANIFEST_VERSION), collective_id, *ids
    )
    return collective_id, membership_sha256, manifest_id


def preview_collective_manifest(
    spawn_ids: list[str] | tuple[str, ...], *, store: AuthorizedEngagementStore
) -> CollectiveManifest:
    """Validate members and derive immutable identity without claiming a document."""
    ids = _ordered_ids(spawn_ids)
    try:
        for spawn_id in ids:
            if store.get_spawn_strict(spawn_id) is None:
                raise KeyError(spawn_id)
        merge_spawns_collective(ids, store=store, include_twin_promote=False)
    except RuntimeError as exc:
        raise CollectiveManifestUnavailable("collective members unavailable") from exc
    collective_id, digest, manifest_id = _identity(store, ids)
    return CollectiveManifest(manifest_id, manifest_id, collective_id, ids, digest, "")


def _parse(
    row: dict[str, Any], manifest_id: str, store: AuthorizedEngagementStore
) -> CollectiveManifest:
    allowed = {
        "kind",
        "version",
        "document_id",
        "manifest_id",
        "collective_id",
        "ordered_spawn_ids",
        "membership_sha256",
        "created_at",
        "engagement_authority_version",
        "owner_account_digest",
        "engagement_key_id",
        "display_document_id",
    }
    if set(row) - allowed or row.get("kind") != "collective_manifest" or row.get("version") != 1:
        raise CollectiveManifestUnavailable("collective manifest is corrupt")
    try:
        ids = _ordered_ids(row["ordered_spawn_ids"])
        collective_id, digest, expected_id = _identity(store, ids)
        created_at = row["created_at"]
        if not isinstance(created_at, str) or not created_at.endswith("Z"):
            raise ValueError("created_at is invalid")
        datetime.fromisoformat(created_at.removesuffix("Z") + "+00:00")
    except (KeyError, TypeError, ValueError) as exc:
        raise CollectiveManifestUnavailable("collective manifest is corrupt") from exc
    if (
        manifest_id != expected_id
        or row.get("manifest_id") != expected_id
        or row.get("document_id") != expected_id
        or row.get("collective_id") != collective_id
        or row.get("membership_sha256") != digest
        or not created_at
    ):
        raise CollectiveManifestUnavailable("collective manifest integrity failed")
    return CollectiveManifest(expected_id, expected_id, collective_id, ids, digest, created_at)


def read_collective_manifest(
    manifest_id: str, *, store: AuthorizedEngagementStore, validate_members: bool = True
) -> CollectiveManifest:
    try:
        row = store.get_document_strict(manifest_id)
    except RuntimeError as exc:
        raise CollectiveManifestUnavailable("collective manifest storage unavailable") from exc
    if row is None:
        raise CollectiveManifestNotFound(manifest_id)
    manifest = _parse(row, manifest_id, store)
    if validate_members:
        try:
            for spawn_id in manifest.ordered_spawn_ids:
                if store.get_spawn_strict(spawn_id) is None:
                    raise CollectiveManifestNotFound(manifest_id)
            merge_spawns_collective(
                manifest.ordered_spawn_ids, store=store, include_twin_promote=False
            )
        except CollectiveManifestNotFound:
            raise
        except KeyError as exc:
            raise CollectiveManifestNotFound(manifest_id) from exc
        except (RuntimeError, ValueError) as exc:
            raise CollectiveManifestUnavailable("collective manifest members unavailable") from exc
    return manifest


def create_collective_manifest(
    spawn_ids: list[str] | tuple[str, ...], *, store: AuthorizedEngagementStore
) -> CollectiveManifest:
    preview = preview_collective_manifest(spawn_ids, store=store)
    ids = preview.ordered_spawn_ids
    collective_id = preview.collective_id
    digest = preview.membership_sha256
    manifest_id = preview.manifest_id
    manifest = CollectiveManifest(
        manifest_id,
        manifest_id,
        collective_id,
        ids,
        digest,
        datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    if store.claim_document(manifest_id, manifest.document()):
        return manifest
    existing = read_collective_manifest(manifest_id, store=store, validate_members=False)
    expected = manifest.document()
    actual = existing.document()
    expected.pop("created_at")
    actual.pop("created_at")
    if _canonical(expected) != _canonical(actual):
        raise CollectiveManifestUnavailable("collective manifest replay is corrupt")
    return existing


def project_collective_manifest(manifest_id: str, *, store: AuthorizedEngagementStore):
    manifest = read_collective_manifest(manifest_id, store=store)
    unit = merge_spawns_collective(
        manifest.ordered_spawn_ids, store=store, include_twin_promote=False
    )
    if unit.collective_id != manifest.collective_id or unit.spawn_ids != manifest.ordered_spawn_ids:
        raise CollectiveManifestUnavailable("collective projection contradicted manifest")
    return manifest, unit


__all__ = [
    "CollectiveManifestNotFound",
    "CollectiveManifestUnavailable",
    "create_collective_manifest",
    "preview_collective_manifest",
    "read_collective_manifest",
    "project_collective_manifest",
]
