"""Audio-only publication receipt for a trusted local AudibleRun experience."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .audible_run import AudibleRunArtifact
from .local_audible_production import LocalAudibleProductionArtifact

_MAX_RECEIPT_BYTES = 8 * 1024 * 1024


class AudibleExperienceReceiptError(RuntimeError):
    """Audio receipt authority or private persistence failed closed."""


class AudibleExperienceReceipt(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", revalidate_instances="always", allow_inf_nan=False
    )

    schema_version: Literal["antiek.audible-experience-receipt.v1"] = (
        "antiek.audible-experience-receipt.v1"
    )
    owner_digest: str = Field(pattern="^[0-9a-f]{64}$")
    asset_id: str
    revision_id: str
    production: LocalAudibleProductionArtifact
    audible_run: AudibleRunArtifact
    cost_usd: Literal[0] = 0
    issued_at: str
    receipt_mac: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def authorities_are_exactly_cross_bound(self) -> AudibleExperienceReceipt:
        production = self.production.manifest
        run = self.audible_run.manifest
        if (
            production.asset_id != self.asset_id
            or run.asset_id != self.asset_id
            or production.revision_id != self.revision_id
            or run.revision_id != self.revision_id
        ):
            raise ValueError("audio receipt asset identity drifted")
        if production.audible_run_sha256 != self.audible_run.manifest_sha256:
            raise ValueError("audio receipt AudibleRun identity drifted")
        if production.duration_seconds != run.total_duration_seconds:
            raise ValueError("audio receipt duration authority drifted")
        if tuple(row.paragraph_id for row in production.sources) != tuple(
            row.paragraph_id for row in run.transcript_spans
        ):
            raise ValueError("audio receipt transcript coverage drifted")
        if tuple(row.chapter_id for row in production.sources) != tuple(
            row.chapter_id for row in run.transcript_spans
        ):
            raise ValueError("audio receipt chapter coverage drifted")
        if tuple(row.duration_seconds for row in production.sources) != tuple(
            round(row.end_offset_seconds - row.start_offset_seconds, 3)
            for row in run.transcript_spans
        ):
            raise ValueError("audio receipt span timing drifted")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @classmethod
    def reopen(
        cls,
        payload: str | bytes,
        *,
        signing_key: bytes,
        production_integrity_key: bytes,
    ) -> AudibleExperienceReceipt:
        size = len(payload.encode()) if isinstance(payload, str) else len(payload)
        if size > _MAX_RECEIPT_BYTES:
            raise AudibleExperienceReceiptError("audio receipt exceeds its byte ceiling")
        try:
            receipt = cls.model_validate_json(payload)
        except Exception:
            raise AudibleExperienceReceiptError("audio receipt payload is invalid") from None
        if not hmac.compare_digest(receipt.receipt_mac, _receipt_mac(receipt, signing_key)):
            raise AudibleExperienceReceiptError("audio receipt MAC is invalid")
        LocalAudibleProductionArtifact.reopen(
            receipt.production.to_json(), production_integrity_key
        )
        AudibleRunArtifact.reopen(receipt.audible_run.to_json())
        return receipt

    @classmethod
    def reopen_from_file(
        cls, path: str | Path, *, signing_key: bytes, production_integrity_key: bytes
    ) -> AudibleExperienceReceipt:
        return cls.reopen(
            _read_private_receipt(Path(path)),
            signing_key=signing_key,
            production_integrity_key=production_integrity_key,
        )


def issue_audible_experience_receipt(
    *,
    owner_digest: str,
    production: LocalAudibleProductionArtifact,
    audible_run: AudibleRunArtifact,
    signing_key: bytes,
    production_integrity_key: bytes,
    now: datetime,
) -> AudibleExperienceReceipt:
    if not isinstance(owner_digest, str) or len(owner_digest) != 64:
        raise ValueError("audio receipt owner identity is invalid")
    try:
        int(owner_digest, 16)
    except ValueError:
        raise ValueError("audio receipt owner identity is invalid") from None
    if now.tzinfo is None:
        raise ValueError("audio receipt timestamp must be timezone-aware")
    path = audible_receipt_path(production)
    pending = path.with_name(".receipt.pending.json")
    if path.exists() or path.is_symlink():
        _remove_same_inode_pending(path, pending)
        existing = AudibleExperienceReceipt.reopen_from_file(
            path,
            signing_key=signing_key,
            production_integrity_key=production_integrity_key,
        )
        if not _same_authority(existing, owner_digest, production, audible_run):
            raise AudibleExperienceReceiptError("existing audio receipt conflicts") from None
        return existing
    if pending.exists() or pending.is_symlink():
        try:
            receipt = AudibleExperienceReceipt.reopen(
                _read_private_receipt(pending, expected_name=pending.name),
                signing_key=signing_key,
                production_integrity_key=production_integrity_key,
            )
        except AudibleExperienceReceiptError:
            _discard_pending(pending)
            receipt = None
        if receipt is not None and not _same_authority(
            receipt, owner_digest, production, audible_run
        ):
            raise AudibleExperienceReceiptError("pending audio receipt conflicts")
    else:
        receipt = None
    if receipt is None:
        unsigned = AudibleExperienceReceipt(
            owner_digest=owner_digest,
            asset_id=production.manifest.asset_id,
            revision_id=production.manifest.revision_id,
            production=production,
            audible_run=audible_run,
            issued_at=now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            receipt_mac="0" * 64,
        )
        receipt = unsigned.model_copy(
            update={"receipt_mac": _receipt_mac(unsigned, signing_key)}
        )
        receipt = AudibleExperienceReceipt.reopen(
            receipt.to_json(),
            signing_key=signing_key,
            production_integrity_key=production_integrity_key,
        )
        _write_pending(pending, receipt.to_json().encode("ascii"))
    _fsync_directory(path.parent)
    try:
        os.link(pending, path, follow_symlinks=False)
    except FileExistsError:
        _remove_same_inode_pending(path, pending)
        existing = AudibleExperienceReceipt.reopen_from_file(
            path,
            signing_key=signing_key,
            production_integrity_key=production_integrity_key,
        )
        if not _same_authority(existing, owner_digest, production, audible_run):
            raise AudibleExperienceReceiptError("existing audio receipt conflicts") from None
        return existing
    os.unlink(pending)
    _fsync_directory(path.parent)
    return AudibleExperienceReceipt.reopen_from_file(
        path,
        signing_key=signing_key,
        production_integrity_key=production_integrity_key,
    )


def audible_receipt_path(production: LocalAudibleProductionArtifact) -> Path:
    output = Path(production.manifest.output_path)
    if output.name != "audible.wav" or not output.is_absolute():
        raise AudibleExperienceReceiptError("audio production path is invalid")
    return output.with_name("receipt.json")


def _receipt_mac(receipt: AudibleExperienceReceipt, key: bytes) -> str:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("audio receipt signing key must contain at least 32 bytes")
    values = receipt.model_dump(mode="json")
    values["receipt_mac"] = ""
    payload = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _read_private_receipt(path: Path, *, expected_name: str = "receipt.json") -> bytes:
    if path.name != expected_name or not path.is_absolute() or path.is_symlink():
        raise AudibleExperienceReceiptError("audio receipt path is invalid")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
    except OSError:
        raise AudibleExperienceReceiptError("audio receipt is unavailable") from None
    try:
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or not 1 <= info.st_size <= _MAX_RECEIPT_BYTES
        ):
            raise AudibleExperienceReceiptError("audio receipt is not private and bounded")
        chunks: list[bytes] = []
        remaining = info.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise AudibleExperienceReceiptError("audio receipt was truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise AudibleExperienceReceiptError("audio receipt changed while reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _write_pending(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise AudibleExperienceReceiptError("pending audio receipt election conflicts") from None
    try:
        view = memoryview(payload)
        while view:
            view = view[os.write(descriptor, view) :]
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    os.close(descriptor)


def _remove_same_inode_pending(path: Path, pending: Path) -> None:
    if not pending.exists() and not pending.is_symlink():
        return
    try:
        final_info = path.lstat()
        pending_info = pending.lstat()
    except OSError:
        raise AudibleExperienceReceiptError("audio receipt publication changed") from None
    if (
        stat.S_ISLNK(final_info.st_mode)
        or stat.S_ISLNK(pending_info.st_mode)
        or (final_info.st_dev, final_info.st_ino)
        != (pending_info.st_dev, pending_info.st_ino)
    ):
        return
    os.unlink(pending)
    _fsync_directory(path.parent)


def _discard_pending(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError:
        raise AudibleExperienceReceiptError("pending audio receipt changed") from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
        or info.st_size > _MAX_RECEIPT_BYTES
    ):
        raise AudibleExperienceReceiptError("pending audio receipt is unsafe")
    os.unlink(path)
    _fsync_directory(path.parent)


def _same_authority(
    receipt: AudibleExperienceReceipt,
    owner_digest: str,
    production: LocalAudibleProductionArtifact,
    audible_run: AudibleRunArtifact,
) -> bool:
    return (
        receipt.owner_digest == owner_digest
        and receipt.production == production
        and receipt.audible_run == audible_run
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "AudibleExperienceReceipt",
    "AudibleExperienceReceiptError",
    "audible_receipt_path",
    "issue_audible_experience_receipt",
]
