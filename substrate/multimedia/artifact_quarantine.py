"""Policy-pinned artifact download into private quarantine."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import stat
import struct
import time
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from runtime.db_lock import FlockWriteCoordinator, connect_read


class ArtifactQuarantineError(RuntimeError):
    """A safe artifact rejection without remote bytes or URL disclosure."""


class Resolver(Protocol):
    def resolve(self, hostname: str) -> Sequence[str]: ...


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    headers: Mapping[str, str]
    peer_ip: str
    body: Iterable[bytes]


class Transport(Protocol):
    def get(
        self, *, url: str, pinned_ips: frozenset[str], tls_hostname: str, timeout_seconds: float
    ) -> TransportResponse: ...


@dataclass(frozen=True)
class ArtifactQuarantineReceipt:
    receipt_id: str
    execution_id: str
    candidate_id: str
    media_type: str
    byte_count: int
    sha256: str
    quarantine_path: str
    receipt_mac: str


_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_artifact_quarantine_receipts (
 receipt_id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, candidate_id TEXT NOT NULL UNIQUE,
 media_type TEXT NOT NULL, byte_count BIGINT NOT NULL, sha256 TEXT NOT NULL,
 quarantine_path TEXT NOT NULL, created_at TEXT NOT NULL, receipt_mac TEXT NOT NULL)
"""


def quarantine_artifact(
    *,
    db_path: str,
    execution_id: str,
    candidate_id: str,
    url: str,
    allowlisted_hosts: frozenset[str],
    resolver: Resolver,
    transport: Transport,
    quarantine_dir: str,
    signing_key: bytes,
    expires_at: datetime | None = None,
    now: datetime | None = None,
    max_bytes: int = 25 * 1024 * 1024,
    timeout_seconds: float = 20.0,
    after_replace: Callable[[], None] | None = None,
) -> ArtifactQuarantineReceipt:
    """Resolve once, pin the peer, validate bytes, and persist without publish."""
    current = now or datetime.now(UTC)
    _verify_candidate(
        db_path=db_path,
        execution_id=execution_id,
        candidate_id=candidate_id,
        url=url,
        signing_key=signing_key,
    )
    existing = _existing_receipt(
        db_path=db_path,
        candidate_id=candidate_id,
        signing_key=signing_key,
    )
    if existing is not None:
        return existing
    if expires_at is not None and current >= expires_at:
        raise ArtifactQuarantineError("artifact URL expired")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.hostname not in allowlisted_hosts:
        raise ArtifactQuarantineError("artifact origin is not allowed")
    if parts.username or parts.password or parts.port not in (None, 443) or parts.fragment:
        raise ArtifactQuarantineError("artifact URL shape is not allowed")
    addresses = tuple(resolver.resolve(parts.hostname))
    pinned = _approved_addresses(addresses)
    started = time.monotonic()
    response = transport.get(
        url=url, pinned_ips=pinned, tls_hostname=parts.hostname, timeout_seconds=timeout_seconds
    )
    if 300 <= response.status_code < 400:
        raise ArtifactQuarantineError("artifact redirect refused")
    if response.status_code != 200:
        raise ArtifactQuarantineError("artifact response rejected")
    if response.peer_ip not in pinned:
        raise ArtifactQuarantineError("artifact peer address was not pinned")
    declared = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if declared not in {"image/png", "image/jpeg", "video/mp4"}:
        raise ArtifactQuarantineError("artifact media type rejected")
    length = response.headers.get("Content-Length")
    if length is not None:
        try:
            declared_length = int(length)
        except ValueError:
            raise ArtifactQuarantineError("artifact length invalid") from None
        if declared_length < 1 or declared_length > max_bytes:
            raise ArtifactQuarantineError("artifact exceeds byte limit")
    payload = bytearray()
    iterator = iter(response.body)
    try:
        for chunk in iterator:
            if time.monotonic() - started > timeout_seconds:
                raise ArtifactQuarantineError("artifact download timed out")
            if not isinstance(chunk, bytes):
                raise ArtifactQuarantineError("artifact transport yielded invalid bytes")
            payload.extend(chunk)
            if len(payload) > max_bytes:
                raise ArtifactQuarantineError("artifact exceeds byte limit")
    finally:
        close = getattr(iterator, "close", None)
        if callable(close):
            close()
    data = bytes(payload)
    _validate_structure(data, declared)
    digest = hashlib.sha256(data).hexdigest()
    root = Path(quarantine_dir)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        root_metadata = root.lstat()
    except OSError:
        raise ArtifactQuarantineError("quarantine directory is invalid") from None
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or root.is_symlink()
        or root_metadata.st_uid != os.getuid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise ArtifactQuarantineError("quarantine directory is invalid")
    final = root / digest
    temporary_name = f".{digest}.{os.getpid()}.tmp"
    root_flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        root_flags |= os.O_NOFOLLOW
    try:
        directory_fd = os.open(root, root_flags)
    except OSError:
        raise ArtifactQuarantineError("quarantine directory is invalid") from None
    try:
        opened = os.fstat(directory_fd)
        if (opened.st_dev, opened.st_ino) != (root_metadata.st_dev, root_metadata.st_ino):
            raise ArtifactQuarantineError("quarantine directory changed")
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        file_fd = os.open(temporary_name, file_flags, 0o600, dir_fd=directory_fd)
        try:
            view = memoryview(data)
            while view:
                written = os.write(file_fd, view)
                if written < 1:
                    raise ArtifactQuarantineError("artifact quarantine write failed")
                view = view[written:]
            os.fsync(file_fd)
        finally:
            os.close(file_fd)
        os.rename(
            temporary_name,
            digest,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
        if after_replace is not None:
            after_replace()
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary_name, dir_fd=directory_fd)
        os.close(directory_fd)
    created_at = current.astimezone(UTC).isoformat().replace("+00:00", "Z")
    receipt_id = (
        "mmartifact_"
        + hashlib.sha256(f"{execution_id}:{candidate_id}:{digest}".encode()).hexdigest()
    )
    values: list[object] = [
        receipt_id,
        execution_id,
        candidate_id,
        declared,
        len(data),
        digest,
        str(final),
        created_at,
    ]
    mac = _mac(signing_key, values)
    coordinator = FlockWriteCoordinator(db_path)
    with coordinator.acquire_write_context("multimedia.artifact.quarantine") as ctx:
        ctx.execute(_DDL)
        existing = ctx.execute(
            "SELECT * FROM multimedia_artifact_quarantine_receipts WHERE candidate_id=?",
            [candidate_id],
        ).fetchone()
        if existing is None:
            ctx.execute(
                "INSERT INTO multimedia_artifact_quarantine_receipts VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [*values, mac],
            )
        else:
            stored_values = list(existing[:-1])
            if (
                tuple(existing[:7]) != tuple(values[:7])
                or not isinstance(existing[-1], str)
                or not hmac.compare_digest(existing[-1], _mac(signing_key, stored_values))
            ):
                raise ArtifactQuarantineError("artifact receipt conflicts")
            return ArtifactQuarantineReceipt(
                str(existing[0]),
                str(existing[1]),
                str(existing[2]),
                str(existing[3]),
                int(existing[4]),
                str(existing[5]),
                str(existing[6]),
                str(existing[8]),
            )
    return ArtifactQuarantineReceipt(
        receipt_id, execution_id, candidate_id, declared, len(data), digest, str(final), mac
    )


def _verify_candidate(
    *, db_path: str, execution_id: str, candidate_id: str, url: str, signing_key: bytes
) -> None:
    try:
        with connect_read(db_path) as connection:
            row = connection.execute(
                "SELECT candidate_id, execution_id, ordinal, source_locator_digest, "
                "declared_media_type, candidate_mac "
                "FROM multimedia_provider_artifact_candidates WHERE candidate_id = ?",
                [candidate_id],
            ).fetchone()
    except Exception:
        raise ArtifactQuarantineError("artifact candidate is unavailable") from None
    if row is None or len(row) != 6 or not isinstance(row[5], str):
        raise ArtifactQuarantineError("artifact candidate is unavailable")
    values = list(row[:5])
    if (
        row[1] != execution_id
        or row[3] != hashlib.sha256(url.encode()).hexdigest()
        or not hmac.compare_digest(row[5], _mac(signing_key, values))
    ):
        raise ArtifactQuarantineError("artifact candidate binding is invalid")


def _existing_receipt(
    *, db_path: str, candidate_id: str, signing_key: bytes
) -> ArtifactQuarantineReceipt | None:
    try:
        with connect_read(db_path) as connection:
            row = connection.execute(
                "SELECT * FROM multimedia_artifact_quarantine_receipts WHERE candidate_id = ?",
                [candidate_id],
            ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    if len(row) != 9 or not isinstance(row[8], str):
        raise ArtifactQuarantineError("artifact receipt is invalid")
    values = list(row[:8])
    if not hmac.compare_digest(row[8], _mac(signing_key, values)):
        raise ArtifactQuarantineError("artifact receipt is invalid")
    path = Path(str(row[6]))
    try:
        metadata = path.lstat()
        if (
            path.is_symlink() or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise ArtifactQuarantineError("artifact receipt file is invalid")
        data = path.read_bytes()
    except OSError:
        raise ArtifactQuarantineError("artifact receipt file is invalid") from None
    if len(data) != row[4] or hashlib.sha256(data).hexdigest() != row[5]:
        raise ArtifactQuarantineError("artifact receipt file is invalid")
    _validate_structure(data, str(row[3]))
    return ArtifactQuarantineReceipt(
        str(row[0]),
        str(row[1]),
        str(row[2]),
        str(row[3]),
        int(row[4]),
        str(row[5]),
        str(row[6]),
        row[8],
    )


def reopen_quarantined_artifact(
    *, db_path: str, candidate_id: str, signing_key: bytes
) -> ArtifactQuarantineReceipt:
    """Reopen one MAC- and byte-verified receipt without network access."""
    receipt = _existing_receipt(
        db_path=db_path, candidate_id=candidate_id, signing_key=signing_key
    )
    if receipt is None:
        raise ArtifactQuarantineError("artifact receipt is unavailable")
    return receipt


def _approved_addresses(values: Sequence[str]) -> frozenset[str]:
    if not values or len(values) > 8:
        raise ArtifactQuarantineError("artifact DNS answer rejected")
    parsed = []
    for text in values:
        try:
            address = ipaddress.ip_address(text)
        except ValueError:
            raise ArtifactQuarantineError("artifact DNS answer rejected") from None
        if (
            not address.is_global
            or address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ArtifactQuarantineError("artifact DNS answer rejected")
        parsed.append(address)
    if len({address.version for address in parsed}) != 1:
        raise ArtifactQuarantineError("mixed artifact DNS answer rejected")
    return frozenset(str(address) for address in parsed)


def _validate_structure(data: bytes, media_type: str) -> None:
    if media_type == "image/png":
        _validate_png(data)
    elif media_type == "image/jpeg":
        _validate_jpeg(data)
    elif media_type == "video/mp4":
        _validate_mp4(data)
    else:
        raise ArtifactQuarantineError("artifact structure rejected")


_MAX_PIXELS = 100_000_000
_MAX_DURATION_SECONDS = 6 * 60 * 60


def _validate_png(data: bytes) -> None:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ArtifactQuarantineError("artifact structure rejected")
    offset, seen_ihdr, seen_idat, seen_iend = 8, False, False, False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ArtifactQuarantineError("artifact structure rejected")
        length = int.from_bytes(data[offset : offset + 4], "big")
        end = offset + 12 + length
        if end > len(data):
            raise ArtifactQuarantineError("artifact structure rejected")
        kind, payload = data[offset + 4 : offset + 8], data[offset + 8 : end - 4]
        crc = int.from_bytes(data[end - 4 : end], "big")
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise ArtifactQuarantineError("artifact structure rejected")
        if not seen_ihdr:
            if kind != b"IHDR" or length != 13:
                raise ArtifactQuarantineError("artifact structure rejected")
            width, height = struct.unpack(">II", payload[:8])
            if width < 1 or height < 1 or width * height > _MAX_PIXELS:
                raise ArtifactQuarantineError("artifact dimensions rejected")
            seen_ihdr = True
        elif kind == b"IHDR" or seen_iend:
            raise ArtifactQuarantineError("artifact structure rejected")
        if kind == b"IDAT":
            seen_idat = True
        if kind == b"IEND":
            if length != 0:
                raise ArtifactQuarantineError("artifact structure rejected")
            seen_iend = True
        offset = end
    if not (seen_ihdr and seen_idat and seen_iend) or offset != len(data):
        raise ArtifactQuarantineError("artifact structure rejected")


def _validate_jpeg(data: bytes) -> None:
    if not data.startswith(b"\xff\xd8"):
        raise ArtifactQuarantineError("artifact structure rejected")
    offset, saw_sof, saw_sos, saw_eoi = 2, False, False, False
    while offset < len(data):
        if data[offset] != 0xFF:
            if not saw_sos:
                raise ArtifactQuarantineError("artifact structure rejected")
            offset += 1
            continue
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker == 0x00 and saw_sos:
            continue
        if marker == 0xD9:
            saw_eoi = True
            break
        if marker in range(0xD0, 0xD8) or marker == 0x01:
            continue
        if offset + 2 > len(data):
            raise ArtifactQuarantineError("artifact structure rejected")
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            raise ArtifactQuarantineError("artifact structure rejected")
        payload = data[offset + 2 : offset + length]
        if marker in {0xC0, 0xC1, 0xC2}:
            if len(payload) < 6:
                raise ArtifactQuarantineError("artifact structure rejected")
            height, width = struct.unpack(">HH", payload[1:5])
            if width < 1 or height < 1 or width * height > _MAX_PIXELS:
                raise ArtifactQuarantineError("artifact dimensions rejected")
            saw_sof = True
        if marker == 0xDA:
            saw_sos = True
        offset += length
    if not (saw_sof and saw_sos and saw_eoi) or offset != len(data):
        raise ArtifactQuarantineError("artifact structure rejected")


def _validate_mp4(data: bytes) -> None:
    offset, kinds, duration_ok = 0, set(), False
    while offset < len(data):
        if offset + 8 > len(data):
            raise ArtifactQuarantineError("artifact structure rejected")
        size = int.from_bytes(data[offset : offset + 4], "big")
        kind = data[offset + 4 : offset + 8]
        header = 8
        if size == 1:
            if offset + 16 > len(data):
                raise ArtifactQuarantineError("artifact structure rejected")
            size, header = int.from_bytes(data[offset + 8 : offset + 16], "big"), 16
        if size < header or offset + size > len(data):
            raise ArtifactQuarantineError("artifact structure rejected")
        kinds.add(kind)
        if kind == b"moov":
            duration_ok = _validate_moov(data[offset + header : offset + size])
        offset += size
    if offset != len(data) or not {b"ftyp", b"moov", b"mdat"} <= kinds or not duration_ok:
        raise ArtifactQuarantineError("artifact structure rejected")


def _validate_moov(data: bytes) -> bool:
    offset = 0
    while offset < len(data):
        if offset + 8 > len(data):
            raise ArtifactQuarantineError("artifact structure rejected")
        size, kind = int.from_bytes(data[offset : offset + 4], "big"), data[offset + 4 : offset + 8]
        if size < 8 or offset + size > len(data):
            raise ArtifactQuarantineError("artifact structure rejected")
        if kind == b"mvhd":
            payload = data[offset + 8 : offset + size]
            version = payload[0] if payload else 255
            start = 20 if version == 1 else 12 if version == 0 else -1
            width = 8 if version == 1 else 4
            if start < 0 or len(payload) < start + 4 + width:
                raise ArtifactQuarantineError("artifact structure rejected")
            timescale = int.from_bytes(payload[start : start + 4], "big")
            duration = int.from_bytes(payload[start + 4 : start + 4 + width], "big")
            if timescale < 1 or duration / timescale > _MAX_DURATION_SECONDS:
                raise ArtifactQuarantineError("artifact duration rejected")
            return True
        offset += size
    return False


def _mac(key: bytes, values: list[object]) -> str:
    if len(key) < 32:
        raise ValueError("signing_key must contain at least 32 bytes")
    payload = json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


__all__ = [
    "ArtifactQuarantineError",
    "ArtifactQuarantineReceipt",
    "Resolver",
    "Transport",
    "TransportResponse",
    "quarantine_artifact",
    "reopen_quarantined_artifact",
]
