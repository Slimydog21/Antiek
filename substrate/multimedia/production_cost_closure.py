"""Read-only production-byte cost closure for registered educational video."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from runtime.db_lock import connect_read

from .educational_video_receipt import EducationalVideoReceipt
from .narration_production import NarrationProductionArtifact, NarrationProductionError
from .narration_run import (
    NarrationRunError,
    NarrationRunReceipt,
    list_narration_runs,
    narration_child_revision,
)
from .provider_execution import (
    ProviderExecutionIntegrityError,
    ProviderExecutionRecord,
    provider_execution_record_from_row,
)
from .read_model import MultimediaAssetStore, MultimediaProductionLink
from .reviewed_visual_registry import ReviewedVisualRegistry, ReviewedVisualRegistryError
from .ship_cost_snapshot import (
    MultimediaShipCostEvidenceConflict,
    MultimediaShipCostEvidenceUnavailable,
    validate_settled_execution,
)
from .verified_playback import VerifiedPlaybackError, VerifiedPlaybackRuntime

_IDENTIFIER_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-")
_MAX_CENTS = (1 << 63) - 1


class _ClosureModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ProductionByteConstituentV1(_ClosureModel):
    role: Literal["visual", "narration"]
    scene_id: str | None = None
    chapter_id: str | None = None
    execution_revision: str
    execution_id: str
    authorization_id: str
    provider: str
    model: str
    capability: str
    charged_cents: int = Field(ge=0, le=_MAX_CENTS)
    settled_at: str

    @model_validator(mode="after")
    def role_has_one_source_identity(self) -> ProductionByteConstituentV1:
        if self.role == "visual":
            valid = self.scene_id is not None and self.chapter_id is None
        else:
            valid = self.chapter_id is not None and self.scene_id is None
        if not valid:
            raise ValueError("production constituent role identity conflicts")
        for name, value in (
            ("source_id", self.scene_id or self.chapter_id or ""),
            ("execution_revision", self.execution_revision),
            ("execution_id", self.execution_id),
            ("authorization_id", self.authorization_id),
            ("provider", self.provider),
            ("model", self.model),
            ("capability", self.capability),
        ):
            _identity(name, value)
        try:
            _timestamp(datetime.fromisoformat(self.settled_at.replace("Z", "+00:00")))
        except ValueError as exc:
            raise ValueError("production constituent settlement time is invalid") from exc
        return self


class ProductionByteProjectionV1(_ClosureModel):
    schema_version: Literal["antiek.production-byte-projection.v1"] = (
        "antiek.production-byte-projection.v1"
    )
    evidence_id: str = Field(pattern=r"^mmprodbyte_[0-9a-f]{64}$")
    owner_identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset_id: str
    revision_id: str
    generated_at_cutoff: str
    basis: Literal["production_byte_contributing_settled_provider_executions"] = (
        "production_byte_contributing_settled_provider_executions"
    )
    production_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_set_id: str
    narration_run_id: str
    constituents: tuple[ProductionByteConstituentV1, ...]
    charged_cents: int = Field(ge=0, le=_MAX_CENTS)
    projection_mac: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProductionCostClosure:
    production_byte_projection: ProductionByteProjectionV1
    visual_execution_ids: tuple[str, ...]
    narration_execution_ids: tuple[str, ...]


@dataclass(frozen=True)
class _BoundExecution:
    role: Literal["visual", "narration"]
    source_id: str
    revision_id: str
    execution_id: str


def build_production_byte_cost_closure(
    *,
    asset_id: str,
    owner_id: str,
    db_path: str,
    store: MultimediaAssetStore,
    playback: VerifiedPlaybackRuntime,
    registry: ReviewedVisualRegistry,
    signing_key: bytes,
    snapshot_key: bytes,
    narration_key: bytes,
    now: datetime,
) -> ProductionCostClosure:
    """Derive and sign the exact settled execution set that produced current bytes."""
    asset = _identity("asset_id", asset_id)
    owner = _owner_identity(owner_id)
    cutoff = _timestamp(now)
    _key(signing_key, "signing_key")
    _key(snapshot_key, "snapshot_key")
    _key(narration_key, "narration_key")
    if snapshot_key in {signing_key, narration_key}:
        raise ValueError("production projection signing key must be independent")

    link, receipt, receipt_digest = _current_receipt(
        asset_id=asset, owner_id=owner, store=store, playback=playback
    )
    reviewed_set_id, visual = _visual_constituents(
        receipt=receipt,
        owner_digest=link.owner_identity_digest,
        asset_id=asset,
        revision_id=link.revision_id,
        registry=registry,
    )
    narration_run_id, narration = _narration_constituents(
        receipt=receipt,
        owner_id=owner,
        asset_id=asset,
        revision_id=link.revision_id,
        db_path=db_path,
        signing_key=signing_key,
        narration_key=narration_key,
    )
    bound = (*visual, *narration)
    ids = tuple(row.execution_id for row in bound)
    if not ids or len(ids) != len(set(ids)):
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    projection = _project_costs(
        bound=bound,
        owner_id=owner,
        asset_id=asset,
        revision_id=link.revision_id,
        receipt_digest=receipt_digest,
        reviewed_set_id=reviewed_set_id,
        narration_run_id=narration_run_id,
        db_path=db_path,
        signing_key=signing_key,
        snapshot_key=snapshot_key,
        cutoff=cutoff,
    )
    # Refuse a receipt or media change during accounting projection.
    _, _, final_digest = _current_receipt(
        asset_id=asset, owner_id=owner, store=store, playback=playback
    )
    if not hmac.compare_digest(receipt_digest, final_digest):
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    return ProductionCostClosure(
        production_byte_projection=projection,
        visual_execution_ids=tuple(row.execution_id for row in visual),
        narration_execution_ids=tuple(row.execution_id for row in narration),
    )


def verify_production_byte_projection(
    projection: ProductionByteProjectionV1,
    *,
    snapshot_key: bytes,
    owner_id: str,
    asset_id: str,
    revision_id: str,
) -> None:
    """Verify one immutable projection and its requested identity bindings."""
    _key(snapshot_key, "snapshot_key")
    owner = _owner_identity(owner_id)
    asset = _identity("asset_id", asset_id)
    revision = _identity("revision_id", revision_id)
    payload = projection.model_dump(mode="json", exclude={"projection_mac"})
    unsigned = dict(payload)
    unsigned.pop("evidence_id")
    expected_id = "mmprodbyte_" + hashlib.sha256(_canonical(unsigned)).hexdigest()
    expected_mac = hmac.new(snapshot_key, _canonical(payload), hashlib.sha256).hexdigest()
    ids = tuple(row.execution_id for row in projection.constituents)
    total = sum(row.charged_cents for row in projection.constituents)
    if (
        not ids
        or ids != tuple(sorted(ids))
        or len(ids) != len(set(ids))
        or total > _MAX_CENTS
        or projection.charged_cents != total
        or projection.owner_identity_digest != hashlib.sha256(owner.encode()).hexdigest()
        or projection.asset_id != asset
        or projection.revision_id != revision
        or any(
            (row.role == "narration" and row.capability != "text-to-speech")
            or (row.role == "visual" and row.capability == "text-to-speech")
            for row in projection.constituents
        )
        or not hmac.compare_digest(projection.evidence_id, expected_id)
        or not hmac.compare_digest(projection.projection_mac, expected_mac)
    ):
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
    _timestamp(datetime.fromisoformat(projection.generated_at_cutoff.replace("Z", "+00:00")))


def _current_receipt(
    *,
    asset_id: str,
    owner_id: str,
    store: MultimediaAssetStore,
    playback: VerifiedPlaybackRuntime,
) -> tuple[MultimediaProductionLink, EducationalVideoReceipt, str]:
    try:
        record = store.get(asset_id, owner_id=owner_id)
    except KeyError:
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable") from None
    except ValueError as exc:
        raise MultimediaShipCostEvidenceConflict("evidence_conflict") from exc
    link = record.production_link
    if link is None or record.mode == "audio" or str(record.asset.kind) == "audio_experience":
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
    expected_owner = hashlib.sha256(owner_id.encode()).hexdigest()
    if (
        link.owner_identity_digest != expected_owner
        or link.asset_id != asset_id
        or link.revision_id != record.asset.revision_id
    ):
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    try:
        receipt = playback.receipt(asset_id=asset_id, revision_id=link.revision_id)
        metadata = playback.metadata(asset_id=asset_id, revision_id=link.revision_id)
    except VerifiedPlaybackError as exc:
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable") from exc
    digest = hashlib.sha256(receipt.to_json().encode()).hexdigest()
    if (
        link.receipt_sha256 != digest
        or metadata.receipt_sha256 != digest
        or link.video_sha256 != metadata.video_sha256
        or link.audio_sha256 != metadata.audio_sha256
        or link.duration_seconds != metadata.duration_seconds
        or link.width_px != metadata.width_px
        or link.height_px != metadata.height_px
        or link.chapter_ids != metadata.chapter_ids
    ):
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    return link, receipt, digest


def _visual_constituents(
    *,
    receipt: EducationalVideoReceipt,
    owner_digest: str,
    asset_id: str,
    revision_id: str,
    registry: ReviewedVisualRegistry,
) -> tuple[str, tuple[_BoundExecution, ...]]:
    try:
        reviewed = registry.get_existing(
            owner_identity_digest=owner_digest,
            asset_id=asset_id,
            revision_id=revision_id,
        )
    except ReviewedVisualRegistryError as exc:
        message = str(exc).lower()
        error = (
            MultimediaShipCostEvidenceConflict
            if any(token in message for token in ("mac", "changed", "malformed", "conflict"))
            else MultimediaShipCostEvidenceUnavailable
        )
        raise error(error.code) from exc
    if len(reviewed.selections) != len(receipt.visual.visuals):
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    bound: list[_BoundExecution] = []
    for selection, packet in zip(reviewed.selections, receipt.visual.visuals, strict=True):
        if (
            selection.scene_id != packet.scene_id
            or selection.expected_sha256 != packet.sha256
            or selection.visual_label != packet.visual_label
            or selection.source_chunk_ids != packet.source_chunk_ids
        ):
            raise MultimediaShipCostEvidenceConflict("evidence_conflict")
        if selection.visual_label == "generated":
            if not selection.execution_receipt_id:
                raise MultimediaShipCostEvidenceConflict("evidence_conflict")
            bound.append(
                _BoundExecution(
                    role="visual",
                    source_id=selection.scene_id,
                    revision_id=revision_id,
                    execution_id=selection.execution_receipt_id,
                )
            )
        elif selection.execution_receipt_id is not None:
            raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    ids = tuple(row.execution_id for row in bound)
    if len(ids) != len(set(ids)):
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    return reviewed.receipt.set_id, tuple(bound)


def _narration_constituents(
    *,
    receipt: EducationalVideoReceipt,
    owner_id: str,
    asset_id: str,
    revision_id: str,
    db_path: str,
    signing_key: bytes,
    narration_key: bytes,
) -> tuple[str, tuple[_BoundExecution, ...]]:
    try:
        runs = list_narration_runs(
            db_path=db_path,
            asset_id=asset_id,
            revision_id=revision_id,
            signing_key=signing_key,
        )
    except NarrationRunError as exc:
        message = str(exc).lower()
        error = (
            MultimediaShipCostEvidenceConflict
            if "mac" in message or "shape" in message or "status" in message
            else MultimediaShipCostEvidenceUnavailable
        )
        raise error(error.code) from exc
    artifact_json = receipt.narration.to_json()
    matching: list[NarrationRunReceipt] = []
    for run in runs:
        if run.status != "sealed":
            continue
        if run.artifact_json is None:
            raise MultimediaShipCostEvidenceConflict("evidence_conflict")
        expected_run_id = "mmnrun_" + hashlib.sha256(
            json.dumps(
                [asset_id, revision_id, run.authorization_set_digest],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if run.run_id != expected_run_id:
            raise MultimediaShipCostEvidenceConflict("evidence_conflict")
        try:
            reopened = NarrationProductionArtifact.reopen(run.artifact_json, narration_key)
        except NarrationProductionError as exc:
            raise MultimediaShipCostEvidenceConflict("evidence_conflict") from exc
        if run.artifact_json != artifact_json:
            continue
        if reopened != receipt.narration:
            raise MultimediaShipCostEvidenceConflict("evidence_conflict")
        matching.append(run)
    if len(matching) != 1:
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
    run = matching[0]
    chapter_ids = tuple(row.chapter_id for row in receipt.narration.manifest.sources)
    expected_bindings = tuple(
        (
            row.chapter_id,
            row.script_line_ids,
            row.source_chunk_ids,
            row.paragraph_ids,
        )
        for row in receipt.narration.manifest.chapter_bindings
    )
    try:
        raw_bindings = json.loads(run.chapter_bindings_json)
        persisted_bindings = tuple(
            (str(row[0]), tuple(row[1]), tuple(row[2]), tuple(row[3])) for row in raw_bindings
        )
    except (IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MultimediaShipCostEvidenceConflict("evidence_conflict") from exc
    if (
        not expected_bindings
        or tuple(row[0] for row in persisted_bindings) != chapter_ids
        or persisted_bindings != expected_bindings
    ):
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")

    records: list[ProviderExecutionRecord] = []
    try:
        with connect_read(db_path) as connection:
            connection.execute("BEGIN TRANSACTION")
            for sequence, chapter_id in enumerate(chapter_ids):
                child_revision = narration_child_revision(revision_id, chapter_id, sequence)
                rows = connection.execute(
                    "SELECT * FROM multimedia_provider_executions "
                    "WHERE asset_id=? AND revision_id=? ORDER BY execution_id",
                    [asset_id, child_revision],
                ).fetchall()
                if len(rows) != 1:
                    raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
                try:
                    record = provider_execution_record_from_row(
                        tuple(rows[0]), signing_key=signing_key
                    )
                except ProviderExecutionIntegrityError as exc:
                    raise MultimediaShipCostEvidenceConflict("evidence_conflict") from exc
                if record.operator_id != owner_id or record.endpoint_capability != "text-to-speech":
                    raise MultimediaShipCostEvidenceConflict("evidence_conflict")
                records.append(record)
            connection.execute("COMMIT")
    except (
        MultimediaShipCostEvidenceUnavailable,
        MultimediaShipCostEvidenceConflict,
    ):
        raise
    except Exception as exc:
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable") from exc
    set_rows = [
        [
            sequence,
            chapter_id,
            record.revision_id,
            record.request_body_digest,
            record.authorization_id,
            record.approved_ceiling_microdollars,
        ]
        for sequence, (chapter_id, record) in enumerate(zip(chapter_ids, records, strict=True))
    ]
    digest = hashlib.sha256(
        json.dumps(set_rows, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    if not hmac.compare_digest(digest, run.authorization_set_digest):
        raise MultimediaShipCostEvidenceConflict("evidence_conflict")
    return run.run_id, tuple(
        _BoundExecution(
            role="narration",
            source_id=chapter_id,
            revision_id=record.revision_id,
            execution_id=record.execution_id,
        )
        for chapter_id, record in zip(chapter_ids, records, strict=True)
    )


def _project_costs(
    *,
    bound: tuple[_BoundExecution, ...],
    owner_id: str,
    asset_id: str,
    revision_id: str,
    receipt_digest: str,
    reviewed_set_id: str,
    narration_run_id: str,
    db_path: str,
    signing_key: bytes,
    snapshot_key: bytes,
    cutoff: str,
) -> ProductionByteProjectionV1:
    ordered = tuple(sorted(bound, key=lambda row: row.execution_id))
    try:
        with connect_read(db_path) as connection:
            connection.execute("BEGIN TRANSACTION")
            constituents: list[ProductionByteConstituentV1] = []
            for row in ordered:
                evidence = validate_settled_execution(
                    connection,
                    execution_id=row.execution_id,
                    signing_key=signing_key,
                    owner_id=owner_id,
                    asset_id=asset_id,
                    revision_id=row.revision_id,
                    cutoff=cutoff,
                )
                if (row.role == "narration" and evidence.capability != "text-to-speech") or (
                    row.role == "visual" and evidence.capability == "text-to-speech"
                ):
                    raise MultimediaShipCostEvidenceConflict("evidence_conflict")
                constituents.append(
                    ProductionByteConstituentV1(
                        role=row.role,
                        scene_id=row.source_id if row.role == "visual" else None,
                        chapter_id=row.source_id if row.role == "narration" else None,
                        execution_revision=row.revision_id,
                        execution_id=evidence.execution_id,
                        authorization_id=evidence.authorization_id,
                        provider=evidence.provider,
                        model=evidence.model,
                        capability=evidence.capability,
                        charged_cents=evidence.charged_cents,
                        settled_at=evidence.settled_at,
                    )
                )
            connection.execute("COMMIT")
    except (
        MultimediaShipCostEvidenceUnavailable,
        MultimediaShipCostEvidenceConflict,
    ):
        raise
    except Exception as exc:
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable") from exc
    total = sum(row.charged_cents for row in constituents)
    if not constituents or total > _MAX_CENTS:
        raise MultimediaShipCostEvidenceUnavailable("evidence_unavailable")
    unsigned = {
        "schema_version": "antiek.production-byte-projection.v1",
        "owner_identity_digest": hashlib.sha256(owner_id.encode()).hexdigest(),
        "asset_id": asset_id,
        "revision_id": revision_id,
        "generated_at_cutoff": cutoff,
        "basis": "production_byte_contributing_settled_provider_executions",
        "production_receipt_digest": receipt_digest,
        "reviewed_set_id": reviewed_set_id,
        "narration_run_id": narration_run_id,
        "constituents": tuple(row.model_dump(mode="json") for row in constituents),
        "charged_cents": total,
    }
    evidence_id = "mmprodbyte_" + hashlib.sha256(_canonical(unsigned)).hexdigest()
    signed = {"evidence_id": evidence_id, **unsigned}
    return ProductionByteProjectionV1(
        evidence_id=evidence_id,
        owner_identity_digest=hashlib.sha256(owner_id.encode()).hexdigest(),
        asset_id=asset_id,
        revision_id=revision_id,
        generated_at_cutoff=cutoff,
        production_receipt_digest=receipt_digest,
        reviewed_set_id=reviewed_set_id,
        narration_run_id=narration_run_id,
        constituents=tuple(constituents),
        charged_cents=total,
        projection_mac=hmac.new(snapshot_key, _canonical(signed), hashlib.sha256).hexdigest(),
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")


def _key(value: bytes, name: str) -> None:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError(f"{name} must contain at least 32 bytes")


def _identity(name: str, value: str, *, max_bytes: int = 128) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValueError(f"{name} is invalid")
    encoded = value.encode()
    if len(encoded) > max_bytes or any(char not in _IDENTIFIER_CHARS for char in value):
        raise ValueError(f"{name} is invalid")
    return value


def _owner_identity(value: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValueError("owner_id is invalid")
    encoded = value.encode()
    if len(encoded) > 512 or any(byte < 32 or byte == 127 for byte in encoded):
        raise ValueError("owner_id is invalid")
    return value


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("snapshot time must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


__all__ = [
    "ProductionByteConstituentV1",
    "ProductionByteProjectionV1",
    "ProductionCostClosure",
    "build_production_byte_cost_closure",
    "verify_production_byte_projection",
]
