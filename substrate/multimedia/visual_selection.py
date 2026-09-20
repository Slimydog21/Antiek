"""Provenance and rights gate for documentary renderer still inputs."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from fcntl import LOCK_EX, LOCK_UN, flock
from pathlib import Path
from typing import Literal, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ken_burns_renderer import SceneStillInput
from .video import TimelineEntry, VisualLabel

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_SCENES = 64
_MAX_FILE_BYTES = 100 * 1024 * 1024
_MAX_PACKET_BYTES = 512 * 1024 * 1024
_MAX_MANIFEST_BYTES = 1024 * 1024
_COPY_CHUNK = 1024 * 1024
_MIN_KEY_BYTES = 32
RightsBasis = Literal["public_domain", "licensed", "operator_owned"]


class VisualSelectionError(RuntimeError):
    """A visual selection packet failed closed."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")


class ReviewedVisualSelection(_FrozenModel):
    scene_id: str
    path: str
    expected_sha256: str = Field(pattern=_DIGEST.pattern)
    visual_label: VisualLabel
    source_chunk_ids: tuple[str, ...] = ()
    execution_receipt_id: str | None = None
    artifact_receipt_id: str | None = None
    source_locator_digest: str | None = Field(default=None, pattern=_DIGEST.pattern)
    rights_basis: RightsBasis | None = None
    rights_review_id: str | None = None

    @model_validator(mode="after")
    def evidence_matches_label(self) -> ReviewedVisualSelection:
        _identifier(self.scene_id, "scene_id")
        _identifiers(self.source_chunk_ids, "source_chunk_ids")
        generated = self.execution_receipt_id is not None or self.artifact_receipt_id is not None
        sourced = any(
            value is not None
            for value in (self.source_locator_digest, self.rights_basis, self.rights_review_id)
        )
        if self.visual_label == "generated":
            if not self.execution_receipt_id or not self.artifact_receipt_id or sourced:
                raise ValueError("generated visuals require only execution and artifact receipts")
            _identifier(self.execution_receipt_id, "execution_receipt_id")
            _identifier(self.artifact_receipt_id, "artifact_receipt_id")
        elif self.visual_label in {"sourced", "archival"}:
            if generated or not all(
                (self.source_locator_digest, self.rights_basis, self.rights_review_id)
            ):
                raise ValueError("sourced visuals require locator, rights basis, and rights review")
            _identifier(cast(str, self.rights_review_id), "rights_review_id")
        elif self.visual_label == "diagram":
            if generated or sourced or not self.source_chunk_ids:
                raise ValueError("diagrams require source chunks and no external-media evidence")
        else:
            raise ValueError("omitted scenes cannot become renderer inputs")
        return self


class PacketVisual(_FrozenModel):
    scene_id: str
    path: str
    sha256: str = Field(pattern=_DIGEST.pattern)
    visual_label: VisualLabel
    source_chunk_ids: tuple[str, ...]
    evidence_digest: str = Field(pattern=_DIGEST.pattern)


class VerifiedVisualEvidence(_FrozenModel):
    """Verdict returned by a trusted receipt/rights authority adapter."""

    scene_id: str
    visual_label: VisualLabel
    content_sha256: str = Field(pattern=_DIGEST.pattern)
    evidence_digest: str = Field(pattern=_DIGEST.pattern)
    authority_mac: str = Field(pattern=_DIGEST.pattern)

    @classmethod
    def issue(
        cls,
        *,
        scene_id: str,
        visual_label: VisualLabel,
        content_sha256: str,
        evidence_digest: str,
        authority_key: bytes,
    ) -> VerifiedVisualEvidence:
        unsigned = cls(
            scene_id=scene_id,
            visual_label=visual_label,
            content_sha256=content_sha256,
            evidence_digest=evidence_digest,
            authority_mac="0" * 64,
        )
        return unsigned.model_copy(
            update={"authority_mac": _authority_mac(unsigned, authority_key)}
        )


EvidenceVerifier = Callable[[ReviewedVisualSelection, str], VerifiedVisualEvidence]
_T = TypeVar("_T")


class VisualSelectionPacket(_FrozenModel):
    schema_version: Literal["antiek.documentary-visual-packet.v1"] = (
        "antiek.documentary-visual-packet.v1"
    )
    asset_id: str
    revision_id: str
    timeline_sha256: str = Field(pattern=_DIGEST.pattern)
    visuals: tuple[PacketVisual, ...] = Field(min_length=1, max_length=_MAX_SCENES)
    packet_digest: str = Field(pattern=_DIGEST.pattern)

    def consume_renderer_inputs(
        self,
        integrity_key: bytes,
        consumer: Callable[[tuple[SceneStillInput, ...]], _T],
    ) -> _T:
        """Verify and immediately pass read-only paths to a same-UID consumer."""
        if not hmac.compare_digest(self.packet_digest, _packet_digest(self, integrity_key)):
            raise VisualSelectionError("visual packet digest mismatch")
        for row in self.visuals:
            _verify_regular_digest(row.path, row.sha256)
        return consumer(
            tuple(
                SceneStillInput(
                    scene_id=row.scene_id,
                    path=row.path,
                    visual_label=row.visual_label,
                    source_chunk_ids=row.source_chunk_ids,
                )
                for row in self.visuals
            )
        )

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @classmethod
    def reopen(cls, payload: str | bytes, integrity_key: bytes) -> VisualSelectionPacket:
        size = len(payload.encode()) if isinstance(payload, str) else len(payload)
        if size > _MAX_MANIFEST_BYTES:
            raise VisualSelectionError("visual packet manifest exceeds its byte ceiling")
        packet = cls.model_validate_json(payload)
        if not hmac.compare_digest(packet.packet_digest, _packet_digest(packet, integrity_key)):
            raise VisualSelectionError("visual packet digest mismatch")
        for row in packet.visuals:
            _verify_regular_digest(row.path, row.sha256)
        return packet


def compile_visual_selection_packet(
    *,
    asset_id: str,
    revision_id: str,
    timeline: tuple[TimelineEntry, ...],
    selections: tuple[ReviewedVisualSelection, ...],
    output_dir: str,
    integrity_key: bytes,
    evidence_authority_key: bytes,
    verify_evidence: EvidenceVerifier,
) -> VisualSelectionPacket:
    """Materialize reviewed stills into one private, sealed renderer packet."""
    asset_id = _identifier(asset_id, "asset_id")
    revision_id = _identifier(revision_id, "revision_id")
    key = _key(integrity_key)
    evidence_authority_key = _key(evidence_authority_key)
    if not timeline or len(timeline) > _MAX_SCENES or len(selections) != len(timeline):
        raise ValueError("visual selections must exactly cover the bounded timeline")
    expected_ids = tuple(row.scene_id for row in timeline)
    if tuple(row.scene_id for row in selections) != expected_ids or len(set(expected_ids)) != len(
        expected_ids
    ):
        raise ValueError("visual selections must match unique timeline scene order")
    selections = tuple(
        ReviewedVisualSelection.model_validate(selection.model_dump(mode="python"))
        for selection in selections
    )
    for timeline_row, selection in zip(timeline, selections, strict=True):
        if selection.visual_label != timeline_row.visual_label:
            raise ValueError("visual disclosure label drifted from timeline authority")
        if selection.source_chunk_ids != timeline_row.source_chunk_ids:
            raise ValueError("visual source chunks drifted from timeline authority")

    root = _private_root(output_dir)
    packet_dir = root / f"{asset_id}-{revision_id}-visuals"
    lock_path = root / ".visual-selection.lock"
    visuals: list[PacketVisual] = []
    total = 0
    staging = Path(tempfile.mkdtemp(prefix=".visual-selection-", dir=root))
    os.chmod(staging, 0o700)
    try:
        for index, selection in enumerate(selections):
            suffix = Path(selection.path).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".ppm"}:
                raise VisualSelectionError("visual input format is not allowed")
            destination = staging / f"still-{index:04d}{suffix}"
            digest, copied = _copy_regular(selection.path, destination)
            total += copied
            if total > _MAX_PACKET_BYTES:
                raise VisualSelectionError("visual packet exceeds its aggregate byte ceiling")
            if not hmac.compare_digest(digest, selection.expected_sha256):
                raise VisualSelectionError("visual input digest does not match reviewed selection")
            verdict = VerifiedVisualEvidence.model_validate(
                verify_evidence(selection, digest).model_dump(mode="python")
            )
            if (
                verdict.scene_id != selection.scene_id
                or verdict.visual_label != selection.visual_label
                or not hmac.compare_digest(verdict.content_sha256, digest)
                or not hmac.compare_digest(
                    verdict.authority_mac, _authority_mac(verdict, evidence_authority_key)
                )
            ):
                raise VisualSelectionError(
                    "evidence authority verdict is not bound to the selection"
                )
            visuals.append(
                PacketVisual(
                    scene_id=selection.scene_id,
                    path=str((packet_dir / destination.name).resolve()),
                    sha256=digest,
                    visual_label=selection.visual_label,
                    source_chunk_ids=selection.source_chunk_ids,
                    evidence_digest=verdict.evidence_digest,
                )
            )
            os.chmod(destination, 0o400)
        timeline_sha = _timeline_digest(timeline)
        unsigned = VisualSelectionPacket(
            asset_id=asset_id,
            revision_id=revision_id,
            timeline_sha256=timeline_sha,
            visuals=tuple(visuals),
            packet_digest="0" * 64,
        )
        packet = unsigned.model_copy(update={"packet_digest": _packet_digest(unsigned, key)})
        manifest = staging / "visual-packet.json"
        _write_exclusive(manifest, packet.to_json().encode())
        _fsync_dir(staging)
        with _publication_lock(lock_path):
            if packet_dir.exists() or packet_dir.is_symlink():
                existing = VisualSelectionPacket.reopen(
                    (packet_dir / "visual-packet.json").read_bytes(), key
                )
                if existing != packet:
                    raise FileExistsError(f"visual packet destination conflicts: {packet_dir.name}")
                return existing
            os.rename(staging, packet_dir)
            _fsync_dir(root)
        return packet
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _copy_regular(source: str, destination: Path) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        source_fd = os.open(source, flags)
    except OSError as exc:
        raise VisualSelectionError("visual input is unavailable") from exc
    destination_fd: int | None = None
    try:
        info = os.fstat(source_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > _MAX_FILE_BYTES:
            raise VisualSelectionError("visual input is not a bounded regular file")
        destination_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        digest = hashlib.sha256()
        copied = 0
        while chunk := os.read(source_fd, _COPY_CHUNK):
            copied += len(chunk)
            if copied > _MAX_FILE_BYTES:
                raise VisualSelectionError("visual input exceeds its byte ceiling")
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_fd, view)
                view = view[written:]
        os.fsync(destination_fd)
        return digest.hexdigest(), copied
    finally:
        os.close(source_fd)
        if destination_fd is not None:
            os.close(destination_fd)


def _verify_regular_digest(path: str, expected: str) -> None:
    actual, _ = _copy_for_digest(path)
    if not hmac.compare_digest(actual, expected):
        raise VisualSelectionError("visual packet file digest mismatch")


def _copy_for_digest(path: str) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise VisualSelectionError("visual packet file is unavailable") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_FILE_BYTES:
            raise VisualSelectionError("visual packet file is not a bounded regular file")
        digest = hashlib.sha256()
        read = 0
        while chunk := os.read(fd, _COPY_CHUNK):
            read += len(chunk)
            if read > _MAX_FILE_BYTES:
                raise VisualSelectionError("visual packet file exceeds its byte ceiling")
            digest.update(chunk)
        return digest.hexdigest(), read
    finally:
        os.close(fd)


def _packet_digest(packet: VisualSelectionPacket, integrity_key: bytes) -> str:
    data = packet.model_dump(mode="json", exclude={"packet_digest"})
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(_key(integrity_key), payload, hashlib.sha256).hexdigest()


def _authority_mac(verdict: VerifiedVisualEvidence, authority_key: bytes) -> str:
    data = verdict.model_dump(mode="json", exclude={"authority_mac"})
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(_key(authority_key), payload, hashlib.sha256).hexdigest()


def _timeline_digest(timeline: tuple[TimelineEntry, ...]) -> str:
    payload = json.dumps(
        [row.model_dump(mode="json") for row in timeline], sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _private_root(value: str) -> Path:
    root = Path(value)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_mode & 0o077:
        raise ValueError("visual packet output root must be an existing private directory")
    return root.resolve()


@contextmanager
def _publication_lock(path: Path) -> Iterator[None]:
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        flock(fd, LOCK_EX)
        yield
    finally:
        flock(fd, LOCK_UN)
        os.close(fd)


def _write_exclusive(path: Path, payload: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _identifier(value: str, field: str) -> str:
    if not _ID.fullmatch(value):
        raise ValueError(f"{field} is not a bounded identifier")
    return value


def _identifiers(values: tuple[str, ...], field: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field} must be unique")
    for value in values:
        _identifier(value, field)


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < _MIN_KEY_BYTES:
        raise ValueError("visual packet integrity key is too short")
    return value
