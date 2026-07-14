"""Immutable evidence of zero external provider charge for registered local media."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .local_provider_exclusion import (
    LocalZeroEvidenceConflict,
    LocalZeroEvidenceUnavailable,
    exclude_provider_executions,
)
from .narration_run import narration_child_revision

if TYPE_CHECKING:
    from .local_audible_coordinator import AudibleAuthority
    from .local_production_coordinator import VideoAuthority


class _VideoAuthorityBackend(Protocol):
    def assert_independent_snapshot_key(self, snapshot_key: bytes) -> None: ...

    def registered_video_authority(
        self, owner_id: str, asset_id: str, revision_id: str
    ) -> VideoAuthority: ...


class _AudioAuthorityBackend(Protocol):
    def assert_independent_snapshot_key(self, snapshot_key: bytes) -> None: ...

    def registered_audible_authority(
        self, owner_id: str, asset_id: str, revision_id: str
    ) -> AudibleAuthority: ...

_VIDEO_LIMITATION = (
    "Zero external provider charge is limited to the exact parent revision and "
    "deterministic narration child revisions represented by this registered local video."
)
_AUDIO_LIMITATION = (
    "Zero external provider charge is limited to the exact parent revision; v1 defines "
    "no provider child-revision namespace for AudibleRun."
)


class _EvidenceModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class LocalZeroRunAuthorityV1(_EvidenceModel):
    role: Literal["local_narration", "local_video", "local_audible"]
    run_id: str
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    terminal_status: Literal["narration_succeeded", "registered"]
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    updated_at: str

    @model_validator(mode="after")
    def role_shape_is_exact(self) -> LocalZeroRunAuthorityV1:
        if self.role == "local_narration":
            valid = self.terminal_status == "narration_succeeded" and self.receipt_digest is None
        else:
            valid = self.terminal_status == "registered" and self.receipt_digest is not None
        if not valid:
            raise ValueError("local zero authority role shape conflicts")
        _timestamp(datetime.fromisoformat(self.updated_at.replace("Z", "+00:00")))
        return self


class LocalZeroExternalCostEvidenceV1(_EvidenceModel):
    schema_version: Literal["antiek.local-zero-external-cost-evidence.v1"] = (
        "antiek.local-zero-external-cost-evidence.v1"
    )
    evidence_id: str = Field(pattern=r"^mmlocalzero_[0-9a-f]{64}$")
    owner_identity_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset_id: str
    revision_id: str
    generated_at_cutoff: str
    run_kind: Literal["video", "audio"]
    basis: Literal["local_registered_zero_external_provider_charge"] = (
        "local_registered_zero_external_provider_charge"
    )
    authorities: tuple[LocalZeroRunAuthorityV1, ...]
    production_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_link_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    excluded_revision_ids: tuple[str, ...]
    provider_execution_count: Literal[0] = 0
    external_cost_cents: Literal[0] = 0
    limitation: str
    snapshot_mac: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_local_video_zero_cost_evidence(
    *,
    coordinator: _VideoAuthorityBackend,
    db_path: str,
    snapshot_key: bytes,
    owner_id: str,
    asset_id: str,
    revision_id: str,
    now: datetime,
) -> LocalZeroExternalCostEvidenceV1:
    """Build signed local-zero evidence from the current registered video chain."""
    key = _key(snapshot_key)
    coordinator.assert_independent_snapshot_key(key)
    try:
        authority = coordinator.registered_video_authority(owner_id, asset_id, revision_id)
    except RuntimeError as exc:
        raise _classified_authority_error(exc) from exc
    expected_owner = hashlib.sha256(_owner_identity(owner_id).encode()).hexdigest()
    if authority.owner_digest != expected_owner:
        raise LocalZeroEvidenceConflict("evidence_conflict")
    child_revisions = tuple(
        narration_child_revision(revision_id, source.chapter_id, sequence)
        for sequence, source in enumerate(authority.receipt.narration.manifest.sources)
    )
    scope = (revision_id, *child_revisions)
    rows = (
        LocalZeroRunAuthorityV1(
            role="local_narration",
            run_id=authority.narration_run_id,
            input_digest=authority.narration_input_digest,
            config_digest=authority.narration_config_digest,
            terminal_status="narration_succeeded",
            artifact_digest=authority.narration_artifact_digest,
            updated_at=authority.narration_updated_at,
        ),
        LocalZeroRunAuthorityV1(
            role="local_video",
            run_id=authority.video_run_id,
            input_digest=authority.video_input_digest,
            config_digest=authority.video_config_digest,
            terminal_status="registered",
            artifact_digest=authority.video_artifact_digest,
            receipt_digest=authority.receipt_digest,
            updated_at=authority.video_updated_at,
        ),
    )
    exclusion = exclude_provider_executions(
        db_path=db_path,
        owner_id=owner_id,
        asset_id=asset_id,
        revision_ids=scope,
    )
    return _sign(
        snapshot_key=key,
        owner_digest=authority.owner_digest,
        asset_id=asset_id,
        revision_id=revision_id,
        run_kind="video",
        authorities=rows,
        receipt_digest=authority.receipt_digest,
        link_digest=_digest_model(authority.production_link),
        excluded_revision_ids=exclusion.revision_ids,
        limitation=_VIDEO_LIMITATION,
        now=now,
    )


def build_local_audio_zero_cost_evidence(
    *,
    coordinator: _AudioAuthorityBackend,
    db_path: str,
    snapshot_key: bytes,
    owner_id: str,
    asset_id: str,
    revision_id: str,
    now: datetime,
) -> LocalZeroExternalCostEvidenceV1:
    """Build signed local-zero evidence from the current registered audio chain."""
    key = _key(snapshot_key)
    coordinator.assert_independent_snapshot_key(key)
    try:
        authority = coordinator.registered_audible_authority(
            owner_id, asset_id, revision_id
        )
    except RuntimeError as exc:
        raise _classified_authority_error(exc) from exc
    expected_owner = hashlib.sha256(_owner_identity(owner_id).encode()).hexdigest()
    if authority.owner_digest != expected_owner:
        raise LocalZeroEvidenceConflict("evidence_conflict")
    rows = (
        LocalZeroRunAuthorityV1(
            role="local_audible",
            run_id=authority.run_id,
            input_digest=authority.input_digest,
            config_digest=authority.config_digest,
            terminal_status="registered",
            artifact_digest=authority.artifact_digest,
            receipt_digest=authority.receipt_digest,
            updated_at=authority.updated_at,
        ),
    )
    exclusion = exclude_provider_executions(
        db_path=db_path,
        owner_id=owner_id,
        asset_id=asset_id,
        revision_ids=(revision_id,),
    )
    return _sign(
        snapshot_key=key,
        owner_digest=authority.owner_digest,
        asset_id=asset_id,
        revision_id=revision_id,
        run_kind="audio",
        authorities=rows,
        receipt_digest=authority.receipt_digest,
        link_digest=_digest_model(authority.audio_production_link),
        excluded_revision_ids=exclusion.revision_ids,
        limitation=_AUDIO_LIMITATION,
        now=now,
    )


def verify_local_zero_cost_evidence(
    evidence: LocalZeroExternalCostEvidenceV1,
    *,
    snapshot_key: bytes,
    owner_id: str,
    asset_id: str,
    revision_id: str,
) -> None:
    """Verify one immutable envelope and its caller identity bindings."""
    key = _key(snapshot_key)
    owner_digest = hashlib.sha256(_owner_identity(owner_id).encode()).hexdigest()
    asset = _identity("asset_id", asset_id)
    revision = _identity("revision_id", revision_id)
    payload = evidence.model_dump(mode="json", exclude={"snapshot_mac"})
    unsigned = dict(payload)
    unsigned.pop("evidence_id")
    expected_id = "mmlocalzero_" + hashlib.sha256(_canonical(unsigned)).hexdigest()
    expected_mac = hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()
    roles = tuple(row.role for row in evidence.authorities)
    expected_roles = (
        ("local_narration", "local_video")
        if evidence.run_kind == "video"
        else ("local_audible",)
    )
    scope_is_exact_shape = (
        evidence.excluded_revision_ids == (revision,)
        if evidence.run_kind == "audio"
        else revision in evidence.excluded_revision_ids
        and len(evidence.excluded_revision_ids) >= 2
        and all(
            value == revision
            or (value.startswith("tts-") and len(value) == 36)
            for value in evidence.excluded_revision_ids
        )
    )
    receipt_authority = evidence.authorities[-1].receipt_digest if roles == expected_roles else None
    if (
        type(evidence.provider_execution_count) is not int
        or type(evidence.external_cost_cents) is not int
        or evidence.provider_execution_count != 0
        or evidence.external_cost_cents != 0
        or evidence.owner_identity_digest != owner_digest
        or evidence.asset_id != asset
        or evidence.revision_id != revision
        or roles != expected_roles
        or evidence.excluded_revision_ids
        != tuple(sorted(evidence.excluded_revision_ids))
        or not evidence.excluded_revision_ids
        or len(evidence.excluded_revision_ids) != len(set(evidence.excluded_revision_ids))
        or not scope_is_exact_shape
        or receipt_authority != evidence.production_receipt_digest
        or evidence.limitation
        != (_VIDEO_LIMITATION if evidence.run_kind == "video" else _AUDIO_LIMITATION)
        or not _run_ids_are_deterministic(evidence)
        or not hmac.compare_digest(evidence.evidence_id, expected_id)
        or not hmac.compare_digest(evidence.snapshot_mac, expected_mac)
    ):
        raise LocalZeroEvidenceUnavailable("evidence_unavailable")
    try:
        cutoff = datetime.fromisoformat(
            evidence.generated_at_cutoff.replace("Z", "+00:00")
        )
        _timestamp(cutoff)
        updates = tuple(
            datetime.fromisoformat(row.updated_at.replace("Z", "+00:00"))
            for row in evidence.authorities
        )
    except ValueError as exc:
        raise LocalZeroEvidenceUnavailable("evidence_unavailable") from exc
    if any(update > cutoff for update in updates):
        raise LocalZeroEvidenceUnavailable("evidence_unavailable")


def _sign(
    *,
    snapshot_key: bytes,
    owner_digest: str,
    asset_id: str,
    revision_id: str,
    run_kind: Literal["video", "audio"],
    authorities: tuple[LocalZeroRunAuthorityV1, ...],
    receipt_digest: str,
    link_digest: str,
    excluded_revision_ids: tuple[str, ...],
    limitation: str,
    now: datetime,
) -> LocalZeroExternalCostEvidenceV1:
    cutoff = _timestamp(now)
    unsigned = {
        "schema_version": "antiek.local-zero-external-cost-evidence.v1",
        "owner_identity_digest": owner_digest,
        "asset_id": _identity("asset_id", asset_id),
        "revision_id": _identity("revision_id", revision_id),
        "generated_at_cutoff": cutoff,
        "run_kind": run_kind,
        "basis": "local_registered_zero_external_provider_charge",
        "authorities": tuple(row.model_dump(mode="json") for row in authorities),
        "production_receipt_digest": receipt_digest,
        "current_link_digest": link_digest,
        "excluded_revision_ids": excluded_revision_ids,
        "provider_execution_count": 0,
        "external_cost_cents": 0,
        "limitation": limitation,
    }
    evidence_id = "mmlocalzero_" + hashlib.sha256(_canonical(unsigned)).hexdigest()
    signed = {"evidence_id": evidence_id, **unsigned}
    mac = hmac.new(snapshot_key, _canonical(signed), hashlib.sha256).hexdigest()
    return LocalZeroExternalCostEvidenceV1(**signed, snapshot_mac=mac)


def _run_ids_are_deterministic(evidence: LocalZeroExternalCostEvidenceV1) -> bool:
    owner = evidence.owner_identity_digest
    rows = evidence.authorities
    if evidence.run_kind == "audio":
        row = rows[0]
        expected = "mmlocalaudible_" + hashlib.sha256(
            f"{owner}\0{row.input_digest}\0{row.config_digest}".encode("ascii")
        ).hexdigest()
        return hmac.compare_digest(row.run_id, expected)
    narration, video = rows
    narration_id = "mmlocalrun_" + hashlib.sha256(
        f"{owner}\0{narration.input_digest}\0{narration.config_digest}".encode()
    ).hexdigest()
    video_id = "mmlocalvideo_" + hashlib.sha256(
        f"{narration.run_id}\0{owner}\0{video.input_digest}\0{video.config_digest}".encode()
    ).hexdigest()
    return hmac.compare_digest(narration.run_id, narration_id) and hmac.compare_digest(
        video.run_id, video_id
    )


def _digest_model(value: BaseModel) -> str:
    return hashlib.sha256(_canonical(value.model_dump(mode="json"))).hexdigest()


def _classified_authority_error(error: RuntimeError) -> LocalZeroEvidenceUnavailable:
    message = str(error).lower()
    unavailable_markers = (
        "unavailable",
        "missing",
        "not terminal",
        "multiple registered",
        "unsupported",
    )
    if any(marker in message for marker in unavailable_markers):
        return LocalZeroEvidenceUnavailable("evidence_unavailable")
    return LocalZeroEvidenceConflict("evidence_conflict")


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError("local zero snapshot key is invalid")
    return value


def _owner_identity(value: str) -> str:
    return _identity("owner_id", value)


def _identity(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    normalized = value.strip()
    encoded = normalized.encode("utf-8")
    if not encoded or len(encoded) > 512 or any(byte < 32 or byte == 127 for byte in encoded):
        raise ValueError(f"{name} is invalid")
    return normalized


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("local zero evidence timestamp must be timezone-aware")
    normalized = value.astimezone(UTC)
    if normalized.microsecond:
        raise ValueError("local zero evidence timestamp must use second precision")
    return normalized.isoformat().replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


__all__ = [
    "LocalZeroEvidenceConflict",
    "LocalZeroEvidenceUnavailable",
    "LocalZeroExternalCostEvidenceV1",
    "LocalZeroRunAuthorityV1",
    "build_local_audio_zero_cost_evidence",
    "build_local_video_zero_cost_evidence",
    "verify_local_zero_cost_evidence",
]
