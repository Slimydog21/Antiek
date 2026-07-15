"""Private receipt authority for paid, authorized audio production."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .narration_production import NarrationProductionArtifact
from .planner import MultimediaPlan

_MAX_RECEIPT_BYTES = 8 * 1024 * 1024


class PaidAudioReceiptError(RuntimeError):
    """Paid audio receipt persistence or authority failed closed."""


class _Model(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", revalidate_instances="always", allow_inf_nan=False
    )


class PaidAudioChapter(_Model):
    chapter_id: str
    duration_seconds: float = Field(gt=0)


class PaidAudioRetentionMarker(_Model):
    line_id: str
    chapter_id: str
    kind: Literal["remember", "recap"]
    source_chunk_ids: tuple[str, ...] = Field(min_length=1)


class PaidAudioLearnedClaim(_Model):
    line_id: str
    chapter_id: str
    claim_text: str = Field(min_length=1)
    source_chunk_ids: tuple[str, ...] = Field(min_length=1)
    follow_up_prompt: str = Field(min_length=1)


class PaidAudioReceipt(_Model):
    schema_version: Literal["antiek.paid-audio-receipt.v1"] = "antiek.paid-audio-receipt.v1"
    owner_digest: str = Field(pattern="^[0-9a-f]{64}$")
    asset_id: str
    revision_id: str
    transformed_plan_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    transformed_plan: MultimediaPlan
    narration: NarrationProductionArtifact
    chapters: tuple[PaidAudioChapter, ...] = Field(min_length=1)
    retention_markers: tuple[PaidAudioRetentionMarker, ...] = Field(min_length=1)
    learned_claims: tuple[PaidAudioLearnedClaim, ...] = Field(min_length=1)
    source_chunk_ids: tuple[str, ...] = Field(min_length=1)
    issued_at: str
    receipt_mac: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def cross_bind_narration(self) -> PaidAudioReceipt:
        plan_payload = json.dumps(
            self.transformed_plan.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if hashlib.sha256(plan_payload).hexdigest() != self.transformed_plan_sha256:
            raise ValueError("paid audio transformed plan digest drifted")
        if self.transformed_plan.grounding_contract != "audible_transform_v1":
            raise ValueError("paid audio receipt does not contain an Audible plan")
        manifest = self.narration.manifest
        if manifest.asset_id != self.asset_id or manifest.revision_id != self.revision_id:
            raise ValueError("paid audio receipt identity drifted")
        if tuple(row.chapter_id for row in self.chapters) != tuple(
            row.chapter_id for row in manifest.sources
        ):
            raise ValueError("paid audio receipt chapter order drifted")
        if tuple(row.duration_seconds for row in self.chapters) != tuple(
            row.duration_seconds for row in manifest.sources
        ):
            raise ValueError("paid audio receipt chapter duration drifted")
        if (
            round(sum(row.duration_seconds for row in self.chapters), 3)
            != manifest.duration_seconds
        ):
            raise ValueError("paid audio receipt total duration drifted")
        if len(set(self.source_chunk_ids)) != len(self.source_chunk_ids):
            raise ValueError("paid audio receipt source authority is duplicated")
        source_set = set(self.source_chunk_ids)
        if any(
            not set(row.source_chunk_ids).issubset(source_set) for row in self.retention_markers
        ):
            raise ValueError("paid audio marker source authority drifted")
        if any(not set(row.source_chunk_ids).issubset(source_set) for row in self.learned_claims):
            raise ValueError("paid audio learned claim source authority drifted")
        expected_markers = tuple(
            PaidAudioRetentionMarker(
                line_id=line.line_id,
                chapter_id=line.line_id.split("-line-", 1)[0],
                kind="remember" if line.line_id.endswith("-run-remember") else "recap",
                source_chunk_ids=tuple(citation.chunk_id for citation in line.citations),
            )
            for line in self.transformed_plan.script_lines
            if line.line_id.endswith(("-run-remember", "-run-recap"))
        )
        expected_claims = tuple(
            PaidAudioLearnedClaim(
                line_id=line.line_id,
                chapter_id=line.line_id.split("-line-", 1)[0],
                claim_text=line.text,
                source_chunk_ids=tuple(citation.chunk_id for citation in line.citations),
                follow_up_prompt=(
                    "What additional context do source chunks "
                    + ", ".join(citation.chunk_id for citation in line.citations)
                    + " provide for this claim?"
                ),
            )
            for line in self.transformed_plan.script_lines
            if line.kind == "factual"
            and line.citations
            and not line.line_id.endswith(("-run-remember", "-run-recap"))
        )
        expected_sources = tuple(
            dict.fromkeys(
                citation.chunk_id
                for line in self.transformed_plan.script_lines
                for citation in line.citations
            )
        )
        if self.retention_markers != expected_markers:
            raise ValueError("paid audio retention marker index is incomplete")
        if self.learned_claims != expected_claims:
            raise ValueError("paid audio learned claim index is incomplete")
        if self.source_chunk_ids != expected_sources:
            raise ValueError("paid audio source authority is incomplete")
        if tuple(row.chapter_id for row in self.chapters) != tuple(
            row.chapter_id for row in self.transformed_plan.chapters
        ):
            raise ValueError("paid audio plan chapter order drifted")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @classmethod
    def reopen(
        cls, payload: str | bytes, *, receipt_key: bytes, narration_key: bytes
    ) -> PaidAudioReceipt:
        size = len(payload.encode()) if isinstance(payload, str) else len(payload)
        if size > _MAX_RECEIPT_BYTES:
            raise PaidAudioReceiptError("paid audio receipt exceeds its byte ceiling")
        try:
            receipt = cls.model_validate_json(payload)
        except Exception:
            raise PaidAudioReceiptError("paid audio receipt payload is invalid") from None
        if not hmac.compare_digest(receipt.receipt_mac, _mac(receipt, receipt_key)):
            raise PaidAudioReceiptError("paid audio receipt MAC is invalid")
        NarrationProductionArtifact.reopen(receipt.narration.to_json(), narration_key)
        return receipt

    @classmethod
    def reopen_from_file(
        cls, path: str | Path, *, receipt_key: bytes, narration_key: bytes
    ) -> PaidAudioReceipt:
        return cls.reopen(
            _read_private(Path(path)), receipt_key=receipt_key, narration_key=narration_key
        )


def paid_audio_receipt_path(output_dir: str | Path, asset_id: str, revision_id: str) -> Path:
    identity = hashlib.sha256(f"{asset_id}\0{revision_id}".encode()).hexdigest()
    return Path(output_dir) / f"paid-audio-{identity}" / "receipt.json"


def issue_paid_audio_receipt(
    *,
    owner_digest: str,
    asset_id: str,
    revision_id: str,
    transformed_plan_sha256: str,
    transformed_plan: MultimediaPlan,
    narration: NarrationProductionArtifact,
    chapters: tuple[PaidAudioChapter, ...],
    retention_markers: tuple[PaidAudioRetentionMarker, ...],
    learned_claims: tuple[PaidAudioLearnedClaim, ...],
    source_chunk_ids: tuple[str, ...],
    receipt_key: bytes,
    narration_key: bytes,
    output_dir: str,
    now: datetime,
) -> PaidAudioReceipt:
    if now.tzinfo is None:
        raise ValueError("paid audio receipt timestamp must be timezone-aware")
    path = paid_audio_receipt_path(output_dir, asset_id, revision_id)
    _prepare_private_directory(path.parent)
    if path.exists() or path.is_symlink():
        existing = PaidAudioReceipt.reopen_from_file(
            path, receipt_key=receipt_key, narration_key=narration_key
        )
        if not _same_authority(
            existing,
            owner_digest=owner_digest,
            transformed_plan_sha256=transformed_plan_sha256,
            transformed_plan=transformed_plan,
            narration=narration,
            chapters=chapters,
            retention_markers=retention_markers,
            learned_claims=learned_claims,
            source_chunk_ids=source_chunk_ids,
        ):
            raise PaidAudioReceiptError("existing paid audio receipt conflicts")
        return existing
    unsigned = PaidAudioReceipt(
        owner_digest=owner_digest,
        asset_id=asset_id,
        revision_id=revision_id,
        transformed_plan_sha256=transformed_plan_sha256,
        transformed_plan=transformed_plan,
        narration=narration,
        chapters=chapters,
        retention_markers=retention_markers,
        learned_claims=learned_claims,
        source_chunk_ids=source_chunk_ids,
        issued_at=now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        receipt_mac="0" * 64,
    )
    receipt = unsigned.model_copy(update={"receipt_mac": _mac(unsigned, receipt_key)})
    receipt = PaidAudioReceipt.reopen(
        receipt.to_json(), receipt_key=receipt_key, narration_key=narration_key
    )
    descriptor, staged_name = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
    staged = Path(staged_name)
    try:
        os.fchmod(descriptor, 0o600)
        payload = receipt.to_json().encode("ascii")
        os.write(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        PaidAudioReceipt.reopen_from_file(
            staged, receipt_key=receipt_key, narration_key=narration_key
        )
        try:
            os.link(staged, path, follow_symlinks=False)
        except FileExistsError:
            existing = PaidAudioReceipt.reopen_from_file(
                path, receipt_key=receipt_key, narration_key=narration_key
            )
            if not _same_authority(
                existing,
                owner_digest=owner_digest,
                transformed_plan_sha256=transformed_plan_sha256,
                transformed_plan=transformed_plan,
                narration=narration,
                chapters=chapters,
                retention_markers=retention_markers,
                learned_claims=learned_claims,
                source_chunk_ids=source_chunk_ids,
            ):
                raise PaidAudioReceiptError("concurrent paid audio receipt conflicts") from None
            return existing
        staged.unlink()
        _fsync(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if staged.exists():
            staged.unlink()
    return PaidAudioReceipt.reopen_from_file(
        path, receipt_key=receipt_key, narration_key=narration_key
    )


def _same_authority(
    receipt: PaidAudioReceipt,
    *,
    owner_digest: str,
    transformed_plan_sha256: str,
    transformed_plan: MultimediaPlan,
    narration: NarrationProductionArtifact,
    chapters: tuple[PaidAudioChapter, ...],
    retention_markers: tuple[PaidAudioRetentionMarker, ...],
    learned_claims: tuple[PaidAudioLearnedClaim, ...],
    source_chunk_ids: tuple[str, ...],
) -> bool:
    return (
        receipt.owner_digest == owner_digest
        and receipt.transformed_plan_sha256 == transformed_plan_sha256
        and receipt.transformed_plan == transformed_plan
        and receipt.narration == narration
        and receipt.chapters == chapters
        and receipt.retention_markers == retention_markers
        and receipt.learned_claims == learned_claims
        and receipt.source_chunk_ids == source_chunk_ids
    )


def _prepare_private_directory(path: Path) -> None:
    root = path.parent
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise PaidAudioReceiptError("paid audio receipt root is invalid")
    root_info = root.stat()
    if (
        root_info.st_uid != os.getuid()
        or not stat.S_ISDIR(root_info.st_mode)
        or stat.S_IMODE(root_info.st_mode) & 0o022
    ):
        raise PaidAudioReceiptError("paid audio receipt root is not private")
    with suppress(FileExistsError):
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        info = path.lstat()
    except OSError:
        raise PaidAudioReceiptError("paid audio receipt directory is unavailable") from None
    if (
        path.is_symlink()
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise PaidAudioReceiptError("paid audio receipt directory is not private")


def _mac(receipt: PaidAudioReceipt, key: bytes) -> str:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("paid audio receipt key is invalid")
    values = receipt.model_dump(mode="json")
    values["receipt_mac"] = ""
    payload = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _read_private(path: Path) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise PaidAudioReceiptError("paid audio receipt path is invalid")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
    except OSError:
        raise PaidAudioReceiptError("paid audio receipt is unavailable") from None
    try:
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or not 1 <= info.st_size <= _MAX_RECEIPT_BYTES
        ):
            raise PaidAudioReceiptError("paid audio receipt is not private and bounded")
        payload = os.read(descriptor, info.st_size + 1)
        if len(payload) != info.st_size:
            raise PaidAudioReceiptError("paid audio receipt changed while reading")
        return payload
    finally:
        os.close(descriptor)


def _fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "PaidAudioChapter",
    "PaidAudioLearnedClaim",
    "PaidAudioReceipt",
    "PaidAudioReceiptError",
    "PaidAudioRetentionMarker",
    "issue_paid_audio_receipt",
    "paid_audio_receipt_path",
]
