"""Validation of feedback anchors against immutable artifact bytes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.db_lock import LockedConnection
from services.html_projection.island import IslandError, extract_island
from substrate.books.servability import is_servable_full_text, servability_of
from substrate.feedback.domain import (
    ArtifactVersionRef,
    NodeTextAnchor,
    ValidatedNodeTextAnchor,
    validate_node_text_anchor,
)
from substrate.research_artifact.paths import (
    read_bounded_nofollow,
    research_artifacts_dir,
)

_MAX_ARTIFACT_BYTES = 10 * 1024 * 1024


class ArtifactAnchorMismatch(ValueError):
    """The supplied owner, immutable tuple, bytes, or node anchor disagrees."""


@dataclass(frozen=True, slots=True)
class ValidatedArtifactAnchor:
    artifact: ArtifactVersionRef
    anchor: ValidatedNodeTextAnchor
    investigation_id: str
    source_document_id: str | None


def _managed_bytes(path_value: str) -> bytes:
    path = Path(path_value)
    try:
        path.resolve(strict=False).relative_to(research_artifacts_dir().resolve())
    except (OSError, ValueError) as exc:
        raise ArtifactAnchorMismatch("artifact path is outside managed storage") from exc
    try:
        return read_bounded_nofollow(path, _MAX_ARTIFACT_BYTES)
    except (OSError, ValueError, OverflowError) as exc:
        raise ArtifactAnchorMismatch("artifact bytes cannot be read safely") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _find_node(model: dict[str, Any], node_id: str) -> dict[str, Any]:
    body = model.get("research_artifact")
    if not isinstance(body, dict):
        raise ArtifactAnchorMismatch("artifact has no research model")
    candidates: list[dict[str, Any]] = []
    for key in ("insights", "open_questions"):
        values = body.get(key, [])
        if not isinstance(values, list):
            raise ArtifactAnchorMismatch("artifact research model is malformed")
        candidates.extend(
            value
            for value in values
            if isinstance(value, dict) and value.get("node_id") == node_id
        )
    if len(candidates) != 1:
        raise ArtifactAnchorMismatch("artifact node identity is missing or ambiguous")
    return candidates[0]


def validate_artifact_anchor(
    con: LockedConnection,
    *,
    owner_user_id: str,
    artifact: ArtifactVersionRef,
    anchor: NodeTextAnchor,
) -> ValidatedArtifactAnchor:
    """Validate an exact historical version and node-local text selection."""
    row = con.execute(
        "SELECT a.investigation_id, a.source_path, a.source_hash, v.html_path, "
        "v.content_hash FROM research_artifacts a "
        "JOIN research_artifact_versions v ON v.artifact_id=a.artifact_id "
        "AND v.owner_user_id=a.owner_user_id "
        "WHERE a.artifact_id=? AND a.owner_user_id=? AND a.state='ready' "
        "AND v.version=?",
        [artifact.artifact_id, owner_user_id, artifact.version],
    ).fetchone()
    if row is None:
        raise ArtifactAnchorMismatch("artifact version not found")
    stored_source_hash = "" if row[2] is None else str(row[2])
    stored_content_hash = str(row[4])
    if (
        stored_source_hash != artifact.source_sha256
        or stored_content_hash != artifact.content_sha256
    ):
        raise ArtifactAnchorMismatch("artifact version hash mismatch")

    source_bytes = _managed_bytes(str(row[1]))
    version_bytes = _managed_bytes(str(row[3]))
    if _sha256(source_bytes) != artifact.source_sha256:
        raise ArtifactAnchorMismatch("artifact source integrity mismatch")
    if _sha256(version_bytes) != artifact.content_sha256:
        raise ArtifactAnchorMismatch("artifact version integrity mismatch")
    try:
        model = extract_island(version_bytes.decode("utf-8"))
    except (UnicodeDecodeError, IslandError) as exc:
        raise ArtifactAnchorMismatch("artifact version has no valid data island") from exc
    node = _find_node(model, anchor.node_id)
    text = node.get("text")
    if not isinstance(text, str):
        raise ArtifactAnchorMismatch("artifact node has no canonical text")
    try:
        validated_node = validate_node_text_anchor(text, anchor)
    except ValueError as exc:
        raise ArtifactAnchorMismatch(str(exc)) from exc
    source_document_id = node.get("source_document_id")
    if source_document_id is not None and not isinstance(source_document_id, str):
        raise ArtifactAnchorMismatch("artifact node source identity is malformed")
    if source_document_id is not None:
        source = con.execute(
            "SELECT content_class, owner_user_id FROM documents WHERE document_id=?",
            [source_document_id],
        ).fetchone()
        if source is None:
            raise ArtifactAnchorMismatch("artifact node source is not servable")
        content_class = None if source[0] is None else str(source[0])
        source_owner = str(source[1])
        owner_allowed = content_class != "user_owned" or source_owner == owner_user_id
        if not owner_allowed or not is_servable_full_text(servability_of(content_class)):
            raise ArtifactAnchorMismatch("artifact node source is not servable")
    return ValidatedArtifactAnchor(
        artifact=artifact,
        anchor=validated_node,
        investigation_id=str(row[0]),
        source_document_id=source_document_id,
    )
