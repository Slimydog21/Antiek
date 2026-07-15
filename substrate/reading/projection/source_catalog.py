"""Read-only discovery of immutable PDF bytes for HTML projection."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class UnresolvedSourceReason(StrEnum):
    """Closed reasons for declining a PDF document as a projection source."""

    MISSING_ASSET_METADATA = "missing_asset_metadata"
    INVALID_ASSET_METADATA = "invalid_asset_metadata"
    UNSAFE_OBJECT_KEY = "unsafe_object_key"
    MISSING_SOURCE_BYTES = "missing_source_bytes"
    SOURCE_SIZE_MISMATCH = "source_size_mismatch"
    SOURCE_HASH_MISMATCH = "source_hash_mismatch"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"


@dataclass(frozen=True)
class ProjectionSourceCandidate:
    document_id: str
    source_asset_id: str
    object_key: str
    source_path: Path
    sha256: str
    byte_size: int
    media_type: str

    @property
    def object_path(self) -> Path:
        return self.source_path

    @property
    def source_sha256(self) -> str:
        return self.sha256


@dataclass(frozen=True)
class UnresolvedProjectionSource:
    document_id: str
    reason: UnresolvedSourceReason

    @property
    def reason_code(self) -> str:
        return self.reason.value

    @property
    def code(self) -> str:
        return self.reason.value


ProjectionSourceRecord = ProjectionSourceCandidate | UnresolvedProjectionSource


class ProjectionSourceCatalog:
    """A deterministic view over existing document rows and object bytes."""

    def __init__(self, connection: Any, object_root: str | Path) -> None:
        self._connection = connection
        self._object_root = Path(object_root)

    def list(self) -> tuple[ProjectionSourceRecord, ...]:
        rows = self._connection.execute(
            "SELECT document_id, document_type, metadata FROM documents ORDER BY document_id"
        ).fetchall()
        records: list[ProjectionSourceRecord] = []
        for document_id, document_type, raw_metadata in rows:
            metadata, metadata_valid = _metadata_dict(raw_metadata)
            if not _is_pdf_document(str(document_type), metadata):
                continue
            records.append(
                self._resolve(str(document_id), metadata, metadata_valid=metadata_valid)
            )
        return tuple(records)

    def enumerate(self) -> tuple[ProjectionSourceRecord, ...]:
        """Alias spelling useful to orchestration callers."""
        return self.list()

    def _resolve(
        self,
        document_id: str,
        metadata: dict[str, object] | None,
        *,
        metadata_valid: bool,
    ) -> ProjectionSourceRecord:
        if not metadata_valid:
            return UnresolvedProjectionSource(
                document_id, UnresolvedSourceReason.INVALID_ASSET_METADATA
            )
        if metadata is None or "html_projection_source" not in metadata:
            return UnresolvedProjectionSource(
                document_id, UnresolvedSourceReason.MISSING_ASSET_METADATA
            )
        asset = metadata["html_projection_source"]
        if not isinstance(asset, dict):
            return UnresolvedProjectionSource(
                document_id, UnresolvedSourceReason.INVALID_ASSET_METADATA
            )
        required = {"source_asset_id", "object_key", "sha256", "byte_size", "media_type"}
        if set(asset) != required or not _valid_asset_values(asset):
            return UnresolvedProjectionSource(
                document_id, UnresolvedSourceReason.INVALID_ASSET_METADATA
            )
        object_key = asset["object_key"]
        if not isinstance(object_key, str):  # defensive if validation is refactored
            return UnresolvedProjectionSource(
                document_id, UnresolvedSourceReason.INVALID_ASSET_METADATA
            )
        if not _safe_object_key(object_key):
            return UnresolvedProjectionSource(document_id, UnresolvedSourceReason.UNSAFE_OBJECT_KEY)
        if asset["media_type"] != "application/pdf":
            return UnresolvedProjectionSource(
                document_id, UnresolvedSourceReason.UNSUPPORTED_MEDIA_TYPE
            )

        root = self._object_root.resolve()
        path = root.joinpath(*PurePosixPath(object_key).parts)
        try:
            resolved = path.resolve(strict=True)
        except (FileNotFoundError, OSError):
            return UnresolvedProjectionSource(
                document_id, UnresolvedSourceReason.MISSING_SOURCE_BYTES
            )
        if not resolved.is_relative_to(root):
            return UnresolvedProjectionSource(document_id, UnresolvedSourceReason.UNSAFE_OBJECT_KEY)
        if not resolved.is_file():
            return UnresolvedProjectionSource(
                document_id, UnresolvedSourceReason.MISSING_SOURCE_BYTES
            )
        if resolved.stat().st_size != asset["byte_size"]:
            return UnresolvedProjectionSource(
                document_id, UnresolvedSourceReason.SOURCE_SIZE_MISMATCH
            )
        if _file_sha256(resolved) != asset["sha256"]:
            return UnresolvedProjectionSource(
                document_id, UnresolvedSourceReason.SOURCE_HASH_MISMATCH
            )
        return ProjectionSourceCandidate(
            document_id=document_id,
            source_asset_id=asset["source_asset_id"],
            object_key=object_key,
            source_path=resolved,
            sha256=asset["sha256"],
            byte_size=asset["byte_size"],
            media_type=asset["media_type"],
        )


def enumerate_projection_sources(
    connection: Any, object_root: str | Path
) -> tuple[ProjectionSourceRecord, ...]:
    return ProjectionSourceCatalog(connection, object_root).list()


def _metadata_dict(value: object) -> tuple[dict[str, object] | None, bool]:
    if value is None:
        return None, True
    if isinstance(value, dict):
        return value, True
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None, False
        return (decoded, True) if isinstance(decoded, dict) else (None, False)
    return None, False


def _is_pdf_document(
    document_type: str, metadata: dict[str, object] | None
) -> bool:
    if document_type.strip().lower() == "pdf":
        return True
    if metadata is None:
        return False
    # Historical arXiv/open-access rows use document_type="paper" while their
    # PDF provenance lives in metadata. Explicit source metadata also marks a
    # PDF candidate even before the legacy provenance key exists.
    return "html_projection_source" in metadata or "pdf_acquisition" in metadata


def _valid_asset_values(asset: dict[object, object]) -> bool:
    return (
        isinstance(asset["source_asset_id"], str)
        and bool(asset["source_asset_id"])
        and isinstance(asset["object_key"], str)
        and isinstance(asset["sha256"], str)
        and _SHA256.fullmatch(asset["sha256"]) is not None
        and isinstance(asset["byte_size"], int)
        and not isinstance(asset["byte_size"], bool)
        and asset["byte_size"] >= 0
        and isinstance(asset["media_type"], str)
    )


def _safe_object_key(value: str) -> bool:
    split = urlsplit(value)
    path = PurePosixPath(value)
    return bool(value) and not (
        split.scheme
        or split.netloc
        or split.query
        or split.fragment
        or value.startswith("/")
        or "\\" in value
        or "%" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in value.split("/"))
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Short compatibility names for consumers that treat this module as the boundary.
SourceCatalog = ProjectionSourceCatalog
SourceCandidate = ProjectionSourceCandidate
UnresolvedSource = UnresolvedProjectionSource
SourceCatalogReason = UnresolvedSourceReason

__all__ = [
    "ProjectionSourceCandidate",
    "ProjectionSourceCatalog",
    "ProjectionSourceRecord",
    "SourceCandidate",
    "SourceCatalog",
    "SourceCatalogReason",
    "UnresolvedProjectionSource",
    "UnresolvedSource",
    "UnresolvedSourceReason",
    "enumerate_projection_sources",
]
