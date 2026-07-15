"""Durable receipt binding narration, visual, and render authorities into one MAC."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .educational_video_production import EducationalVideoProductionArtifact
from .ken_burns_renderer import KenBurnsRenderArtifact
from .narration_production import NarrationProductionArtifact
from .visual_selection import VisualSelectionPacket

_MAX_RECEIPT_BYTES = 2 * 1024 * 1024
_MAX_FILE_BYTES = 512 * 1024 * 1024
_MIN_KEY_BYTES = 32
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class EducationalVideoReceiptError(RuntimeError):
    """The receipt failed a binding, integrity, or publication check."""


class _ReceiptModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", revalidate_instances="always", allow_inf_nan=False
    )


class EducationalVideoReceipt(_ReceiptModel):
    schema_version: Literal["antiek.educational-video-receipt.v1"] = (
        "antiek.educational-video-receipt.v1"
    )
    asset_id: str
    revision_id: str
    narration: NarrationProductionArtifact
    visual: VisualSelectionPacket
    render: KenBurnsRenderArtifact
    receipt_mac: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def identity_is_bounded(self) -> EducationalVideoReceipt:
        _identifier(self.asset_id, "asset_id")
        _identifier(self.revision_id, "revision_id")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @classmethod
    def reopen(
        cls,
        payload: str | bytes,
        receipt_key: bytes,
        narration_key: bytes,
        visual_key: bytes,
        render_key: bytes,
    ) -> EducationalVideoReceipt:
        """Reopen from a payload, verifying receipt MAC and all nested authorities."""
        size = len(payload.encode()) if isinstance(payload, str) else len(payload)
        if size > _MAX_RECEIPT_BYTES:
            raise EducationalVideoReceiptError("receipt exceeds its byte ceiling")
        try:
            receipt = cls.model_validate_json(payload)
        except ValidationError:
            raise EducationalVideoReceiptError("receipt payload is invalid") from None
        expected_mac = _receipt_mac(receipt, _key(receipt_key))
        if not hmac.compare_digest(receipt.receipt_mac, expected_mac):
            raise EducationalVideoReceiptError("receipt MAC is invalid")
        NarrationProductionArtifact.reopen(receipt.narration.to_json(), _key(narration_key))
        VisualSelectionPacket.reopen(receipt.visual.to_json(), _key(visual_key))
        KenBurnsRenderArtifact.reopen(receipt.render.to_json(), _key(render_key))
        _verify_cross_bindings(receipt)
        return receipt

    @classmethod
    def reopen_from_file(
        cls,
        path: str,
        receipt_key: bytes,
        narration_key: bytes,
        visual_key: bytes,
        render_key: bytes,
    ) -> EducationalVideoReceipt:
        """Reopen from a private file, verifying file properties and receipt."""
        absolute, payload, file_identity, bundle_identity = _read_private_file(path)
        receipt = cls.reopen(payload, receipt_key, narration_key, visual_key, render_key)
        file_path = Path(absolute)
        if file_path.name != "receipt.json":
            raise EducationalVideoReceiptError("receipt file must be named receipt.json")
        parent = file_path.parent
        expected_bundle = _bundle_name(receipt.asset_id, receipt.revision_id)
        if parent.name != expected_bundle:
            raise EducationalVideoReceiptError("receipt file is not in the expected bundle directory")
        _verify_private_bundle(parent, bundle_identity)
        _verify_private_path(file_path, file_identity)
        return receipt


def issue(
    *,
    artifact: EducationalVideoProductionArtifact,
    receipt_key: bytes,
    narration_key: bytes,
    visual_key: bytes,
    render_key: bytes,
    output_dir: str,
) -> EducationalVideoReceipt:
    """Issue a durable receipt from a verified production artifact."""
    receipt_key = _key(receipt_key)
    narration_key = _key(narration_key)
    visual_key = _key(visual_key)
    render_key = _key(render_key)
    root = _private_directory(output_dir)
    narration = NarrationProductionArtifact.reopen(artifact.narration.to_json(), narration_key)
    visual = VisualSelectionPacket.reopen(
        artifact.documentary.visual_packet.to_json(), visual_key
    )
    render = KenBurnsRenderArtifact.reopen(
        artifact.documentary.render_artifact.to_json(), render_key
    )
    asset_id = narration.manifest.asset_id
    revision_id = narration.manifest.revision_id
    _identifier(asset_id, "asset_id")
    _identifier(revision_id, "revision_id")
    unsigned = EducationalVideoReceipt(
        asset_id=asset_id,
        revision_id=revision_id,
        narration=narration,
        visual=visual,
        render=render,
        receipt_mac="0" * 64,
    )
    receipt = unsigned.model_copy(update={"receipt_mac": _receipt_mac(unsigned, receipt_key)})
    bundle = root / _bundle_name(asset_id, revision_id)
    destination = bundle / "receipt.json"
    staging = Path(tempfile.mkdtemp(prefix=".receipt-", dir=root))
    published = False
    try:
        os.chmod(staging, 0o700)
        staged_file = staging / "receipt.json"
        staged_file.write_text(receipt.to_json())
        os.chmod(staged_file, 0o600)
        _fsync_file(staged_file)
        _fsync_dir(staging)
        _, staged_payload, _, _ = _read_private_file(str(staged_file))
        staged_receipt = EducationalVideoReceipt.reopen(
            staged_payload, receipt_key, narration_key, visual_key, render_key
        )
        if staged_receipt != receipt:
            raise EducationalVideoReceiptError("staged receipt conflicts with issuance")
        if bundle.exists() or bundle.is_symlink():
            existing = EducationalVideoReceipt.reopen_from_file(
                str(destination), receipt_key, narration_key, visual_key, render_key
            )
            if existing != receipt:
                shutil.rmtree(staging, ignore_errors=True)
                raise FileExistsError(f"receipt destination conflicts: {bundle.name}")
            shutil.rmtree(staging, ignore_errors=True)
            return existing
        try:
            os.rename(staging, bundle)
        except OSError:
            if not bundle.exists() or bundle.is_symlink():
                raise
            existing = EducationalVideoReceipt.reopen_from_file(
                str(destination), receipt_key, narration_key, visual_key, render_key
            )
            if existing != receipt:
                raise FileExistsError(f"receipt destination conflicts: {bundle.name}") from None
            shutil.rmtree(staging, ignore_errors=True)
            return existing
        _fsync_dir(root)
        published = True
        return receipt
    except BaseException:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)
        raise


def _verify_cross_bindings(receipt: EducationalVideoReceipt) -> None:
    """Verify all cross-authority bindings are consistent."""
    asset_id = receipt.asset_id
    revision_id = receipt.revision_id
    narration_manifest = receipt.narration.manifest
    render_manifest = receipt.render.manifest
    if narration_manifest.asset_id != asset_id or narration_manifest.revision_id != revision_id:
        raise EducationalVideoReceiptError("narration identity drifted from receipt")
    if receipt.visual.asset_id != asset_id or receipt.visual.revision_id != revision_id:
        raise EducationalVideoReceiptError("visual identity drifted from receipt")
    if render_manifest.asset_id != asset_id or render_manifest.revision_id != revision_id:
        raise EducationalVideoReceiptError("render identity drifted from receipt")
    if not hmac.compare_digest(receipt.visual.timeline_sha256, render_manifest.timeline_sha256):
        raise EducationalVideoReceiptError("visual timeline digest does not match render")
    if render_manifest.narration_path != narration_manifest.output_path:
        raise EducationalVideoReceiptError("render narration path does not match narration output")
    if not hmac.compare_digest(render_manifest.narration_sha256, narration_manifest.output_sha256):
        raise EducationalVideoReceiptError("render narration sha256 does not match narration output")
    visual_rows = tuple(
        (row.scene_id, row.path, row.sha256, row.visual_label, row.source_chunk_ids)
        for row in receipt.visual.visuals
    )
    render_rows = tuple(
        (row.scene_id, row.path, row.sha256, row.visual_label, row.source_chunk_ids)
        for row in render_manifest.inputs
    )
    if visual_rows != render_rows:
        raise EducationalVideoReceiptError("visual packet rows do not match render inputs")
    narration_sources = narration_manifest.sources
    render_captions = render_manifest.captions
    narration_chapter_ids = tuple(row.chapter_id for row in narration_sources)
    render_chapter_ids = tuple(row.chapter_id for row in render_captions)
    if narration_chapter_ids != render_chapter_ids:
        raise EducationalVideoReceiptError("narration chapter IDs do not match render captions")
    narration_boundaries: list[float] = []
    cumulative = 0.0
    for source in narration_sources:
        cumulative = round(cumulative + source.duration_seconds, 3)
        narration_boundaries.append(cumulative)
    render_boundaries: list[float] = []
    for caption in render_captions:
        render_boundaries.append(caption.end_seconds)
    if len(narration_boundaries) != len(render_boundaries):
        raise EducationalVideoReceiptError("narration and render boundary counts differ")
    for i, (n, r) in enumerate(zip(narration_boundaries, render_boundaries, strict=True)):
        if abs(n - r) > 0.001:
            raise EducationalVideoReceiptError(f"narration boundary {i} does not match render caption")
    if abs(narration_manifest.duration_seconds - render_manifest.duration_seconds) > 0.001:
        raise EducationalVideoReceiptError("total duration does not match between narration and render")


def _receipt_mac(receipt: EducationalVideoReceipt, key: bytes) -> str:
    data = receipt.model_dump(mode="json", exclude={"receipt_mac"})
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _read_private_file(
    path: str,
) -> tuple[str, bytes, tuple[int, int], tuple[int, int]]:
    """Read a private receipt through the same descriptor that was verified."""
    absolute = os.path.abspath(path)
    if absolute != os.path.realpath(path):
        raise EducationalVideoReceiptError("receipt file cannot traverse symlinks")
    file_path = Path(absolute)
    bundle_identity = _verify_private_bundle(file_path.parent)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError:
        raise EducationalVideoReceiptError("receipt file is unavailable") from None
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or not 0 < info.st_size <= _MAX_RECEIPT_BYTES
        ):
            raise EducationalVideoReceiptError("receipt file is not private and bounded")
        chunks: list[bytes] = []
        remaining = info.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise EducationalVideoReceiptError("receipt file was truncated while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise EducationalVideoReceiptError("receipt file changed while reading")
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size) != (
            info.st_dev,
            info.st_ino,
            info.st_size,
        ):
            raise EducationalVideoReceiptError("receipt file changed while reading")
        file_identity = (info.st_dev, info.st_ino)
    finally:
        os.close(descriptor)
    _verify_private_bundle(file_path.parent, bundle_identity)
    _verify_private_path(file_path, file_identity)
    return absolute, payload, file_identity, bundle_identity


def _verify_private_bundle(
    path: Path, expected_identity: tuple[int, int] | None = None
) -> tuple[int, int]:
    try:
        info = path.lstat()
    except OSError:
        raise EducationalVideoReceiptError("receipt bundle is unavailable") from None
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_nlink < 2
    ):
        raise EducationalVideoReceiptError("receipt bundle is not private")
    identity = (info.st_dev, info.st_ino)
    if expected_identity is not None and identity != expected_identity:
        raise EducationalVideoReceiptError("receipt bundle changed while reading")
    return identity


def _verify_private_path(path: Path, expected_identity: tuple[int, int]) -> None:
    try:
        info = path.lstat()
    except OSError:
        raise EducationalVideoReceiptError("receipt file changed while reading") from None
    if stat.S_ISLNK(info.st_mode) or (info.st_dev, info.st_ino) != expected_identity:
        raise EducationalVideoReceiptError("receipt file changed while reading")


def _private_directory(value: str) -> Path:
    if os.path.abspath(value) != os.path.realpath(value):
        raise ValueError("receipt output directory cannot traverse symlinks")
    root = Path(value)
    try:
        info = root.lstat()
    except OSError:
        raise ValueError("receipt output directory must already exist") from None
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("receipt output directory must be private")
    return root.resolve()


def _bundle_name(asset_id: str, revision_id: str) -> str:
    identity = json.dumps([asset_id, revision_id], separators=(",", ":")).encode("ascii")
    return "mmvideo_" + hashlib.sha256(identity).hexdigest()


def receipt_file_path(output_dir: str, asset_id: str, revision_id: str) -> str:
    """Return the canonical receipt path without asserting that it exists."""
    _identifier(asset_id, "asset_id")
    _identifier(revision_id, "revision_id")
    root = _private_directory(output_dir)
    return str(root / _bundle_name(asset_id, revision_id) / "receipt.json")


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field} is not a bounded identifier")
    return value


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < _MIN_KEY_BYTES:
        raise ValueError("integrity key must contain at least 32 bytes")
    return value


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "EducationalVideoReceipt",
    "EducationalVideoReceiptError",
    "issue",
]
