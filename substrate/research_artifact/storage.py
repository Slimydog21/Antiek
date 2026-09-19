"""Private atomic filesystem storage for owner-bound ResearchArtifacts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .authority import KEY_CODEC_VERSION, ArtifactAuthority

SIDECAR_SCHEMA_VERSION = 1
MAX_HISTORY_HTML_BYTES = 20 * 1024 * 1024
MAX_HISTORY_RECORD_BYTES = MAX_HISTORY_HTML_BYTES * 6 + 4096


class UnsafeArtifactState(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactSidecar:
    schema_version: int
    key_codec_version: int
    account_id_digest: str
    investigation_id_digest: str
    content_hash: str
    created_at: str
    migrated_at: str | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _check_regular(path: Path) -> os.stat_result:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise UnsafeArtifactState("artifact storage entry is not a private regular file")
    return info


def _private_dir(root: Path, path: Path) -> None:
    """Create/check every directory component without accepting symlink ancestors."""
    root = root.absolute()
    path = path.absolute()
    if path != root and root not in path.parents:
        raise UnsafeArtifactState("artifact path escaped its storage root")
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise UnsafeArtifactState("artifact storage root cannot be created safely") from exc
    current = root
    for part in (".", *path.relative_to(root).parts):
        if part != ".":
            current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            current.mkdir(mode=0o700)
            info = current.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise UnsafeArtifactState("artifact directory chain is unsafe")
        os.chmod(current, 0o700)


def _read_regular(path: Path, *, max_bytes: int | None = None) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise UnsafeArtifactState("artifact storage entry cannot be opened safely") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise UnsafeArtifactState("artifact storage entry is not a private regular file")
        if max_bytes is not None and (max_bytes < 0 or info.st_size > max_bytes):
            raise UnsafeArtifactState("artifact storage entry exceeds the read bound")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(fd, 1024 * 1024):
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise UnsafeArtifactState("artifact storage entry exceeds the read bound")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _atomic_write(root: Path, path: Path, data: bytes) -> None:
    _private_dir(root, path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        tmp.unlink(missing_ok=True)


def _atomic_claim(root: Path, path: Path, data: bytes) -> bool:
    """Atomically publish immutable bytes without ever replacing an existing path."""
    _private_dir(root, path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp, path, follow_symlinks=False)
        except FileExistsError:
            if _read_regular(path, max_bytes=MAX_HISTORY_RECORD_BYTES) != data:
                raise UnsafeArtifactState(
                    "immutable artifact history collision"
                ) from None
            return False
        os.chmod(path, 0o600)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return True
    finally:
        tmp.unlink(missing_ok=True)


class FilesystemArtifactStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root
        self._held_locks: dict[Path, int] = {}
        self._held_locks_guard = threading.Lock()

    def write(
        self, authority: ArtifactAuthority, html: str, *, migrated_at: str | None = None
    ) -> Path:
        with self.mutation_lock(authority):
            return self._write_locked(authority, html, migrated_at=migrated_at)

    def _write_locked(
        self, authority: ArtifactAuthority, html: str, *, migrated_at: str | None = None
    ) -> Path:
        raw = html.encode("utf-8")
        root = Path(self.root or authority.account_dir().parents[1])
        path = authority.artifact_path(self.root)
        sidecar_path = authority.sidecar_path(self.root)
        marker_path = path.with_suffix(".write-in-progress")
        if path.exists() or path.is_symlink():
            _check_regular(path)
        sidecar = ArtifactSidecar(
            schema_version=SIDECAR_SCHEMA_VERSION,
            key_codec_version=KEY_CODEC_VERSION,
            account_id_digest=authority.account_digest,
            investigation_id_digest=authority.investigation_digest,
            content_hash=hashlib.sha256(raw).hexdigest(),
            created_at=_now(),
            migrated_at=migrated_at,
        )
        artifact_exists = path.exists() or path.is_symlink()
        sidecar_exists = sidecar_path.exists() or sidecar_path.is_symlink()
        if artifact_exists != sidecar_exists:
            raise UnsafeArtifactState("artifact storage pair is incomplete")
        if artifact_exists and sidecar_exists:
            # Preserve the last validated pair so a process/power loss between
            # the two publishes can recover without making old bytes unavailable.
            self.read(authority)
            _atomic_write(root, path.with_suffix(".previous.html"), _read_regular(path))
            _atomic_write(
                root,
                sidecar_path.with_suffix(".previous.json"),
                _read_regular(sidecar_path),
            )
        marker = {
            "version": 2,
            "sidecar": asdict(sidecar),
        }
        _atomic_write(
            root,
            marker_path,
            json.dumps(marker, sort_keys=True, separators=(",", ":")).encode(),
        )
        _atomic_write(root, path, raw)
        _atomic_write(
            root,
            sidecar_path,
            json.dumps(asdict(sidecar), sort_keys=True, separators=(",", ":")).encode(),
        )
        marker_path.unlink(missing_ok=True)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return path

    def _validated_pair(
        self,
        authority: ArtifactAuthority,
        path: Path,
        sidecar_path: Path,
        *,
        max_bytes: int | None = None,
    ) -> bytes:
        raw = _read_regular(path, max_bytes=max_bytes)
        sidecar = json.loads(_read_regular(sidecar_path).decode("utf-8"))
        expected = {
            "account_id_digest": authority.account_digest,
            "investigation_id_digest": authority.investigation_digest,
            "key_codec_version": KEY_CODEC_VERSION,
            "content_hash": hashlib.sha256(raw).hexdigest(),
        }
        if any(sidecar.get(key) != value for key, value in expected.items()):
            raise UnsafeArtifactState("artifact sidecar identity or content hash mismatch")
        return raw

    def read(self, authority: ArtifactAuthority) -> str:
        with self.mutation_lock(authority):
            return self._read_locked(authority)

    def read_bounded(self, authority: ArtifactAuthority, *, max_bytes: int) -> str:
        """Read one validated artifact snapshot without exceeding ``max_bytes``."""
        if max_bytes < 1:
            raise UnsafeArtifactState("artifact read bound is invalid")
        with self.mutation_lock(authority):
            return self._read_locked(authority, max_bytes=max_bytes)

    def read_bounded_if_present(
        self, authority: ArtifactAuthority, *, max_bytes: int
    ) -> str | None:
        """Return absent only when both pair members are absent under the lock."""
        if max_bytes < 1:
            raise UnsafeArtifactState("artifact read bound is invalid")
        with self.mutation_lock(authority):
            path = authority.artifact_path(self.root)
            sidecar = authority.sidecar_path(self.root)
            artifact_exists = path.exists() or path.is_symlink()
            sidecar_exists = sidecar.exists() or sidecar.is_symlink()
            if not artifact_exists and not sidecar_exists:
                return None
            return self._read_locked(authority, max_bytes=max_bytes)

    def _read_locked(
        self, authority: ArtifactAuthority, *, max_bytes: int | None = None
    ) -> str:
        root = Path(self.root or authority.account_dir().parents[1])
        path = authority.artifact_path(self.root)
        sidecar_path = authority.sidecar_path(self.root)
        _private_dir(root, path.parent)
        try:
            raw = self._validated_pair(
                authority, path, sidecar_path, max_bytes=max_bytes
            )
        except (OSError, ValueError, json.JSONDecodeError, UnsafeArtifactState) as original_exc:
            marker_path = path.with_suffix(".write-in-progress")
            try:
                marker = json.loads(_read_regular(marker_path).decode("utf-8"))
            # fmt: off -- project supports Python 3.11+; py314 syntax is invalid there.
            except (OSError, ValueError, json.JSONDecodeError, UnsafeArtifactState):
                # fmt: on
                raise original_exc from None
            if not isinstance(marker, dict) or marker.get("version") != 2:
                raise UnsafeArtifactState("artifact recovery marker is invalid") from original_exc
            previous_path = path.with_suffix(".previous.html")
            previous_sidecar = sidecar_path.with_suffix(".previous.json")
            try:
                raw = self._validated_pair(
                    authority, previous_path, previous_sidecar, max_bytes=max_bytes
                )
            # fmt: off -- project supports Python 3.11+; py314 syntax is invalid there.
            except (OSError, ValueError, json.JSONDecodeError, UnsafeArtifactState):
                # fmt: on
                raw = None
            if raw is not None:
                _atomic_write(root, path, raw)
                _atomic_write(root, sidecar_path, _read_regular(previous_sidecar))
                marker_path.unlink(missing_ok=True)
                return raw.decode("utf-8")
            proposed_sidecar = marker.get("sidecar")
            if isinstance(proposed_sidecar, dict):
                try:
                    current_raw = _read_regular(path, max_bytes=max_bytes)
                # fmt: off -- project supports Python 3.11+; py314 syntax is invalid there.
                except (OSError, UnsafeArtifactState):
                    # fmt: on
                    current_raw = None
                if (
                    current_raw is not None
                    and proposed_sidecar.get("account_id_digest") == authority.account_digest
                    and proposed_sidecar.get("investigation_id_digest")
                    == authority.investigation_digest
                    and proposed_sidecar.get("key_codec_version") == KEY_CODEC_VERSION
                    and proposed_sidecar.get("content_hash")
                    == hashlib.sha256(current_raw).hexdigest()
                ):
                    _atomic_write(
                        root,
                        sidecar_path,
                        json.dumps(
                            proposed_sidecar, sort_keys=True, separators=(",", ":")
                        ).encode(),
                    )
                    marker_path.unlink(missing_ok=True)
                    return current_raw.decode("utf-8")
            raise UnsafeArtifactState("artifact write could not be recovered") from original_exc
        return raw.decode("utf-8")

    def exists(self, authority: ArtifactAuthority) -> bool:
        path = authority.artifact_path(self.root)
        return path.exists() and authority.sidecar_path(self.root).exists()

    def _history_path(
        self, authority: ArtifactAuthority, body_content_hash: str
    ) -> Path:
        if (
            len(body_content_hash) != 64
            or any(char not in "0123456789abcdef" for char in body_content_hash)
        ):
            raise ValueError("artifact history content hash is invalid")
        return (
            authority.account_dir(self.root)
            / "artifact-history"
            / authority.investigation_key
            / f"{body_content_hash}.json"
        )

    def claim_history(
        self,
        authority: ArtifactAuthority,
        *,
        body_content_hash: str,
        html: str,
    ) -> Path:
        raw = html.encode("utf-8")
        if not raw or len(raw) > MAX_HISTORY_HTML_BYTES:
            raise UnsafeArtifactState("artifact history HTML exceeds its bound")
        from .import_notes import parse_body_from_html

        try:
            body = parse_body_from_html(html)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise UnsafeArtifactState("artifact history body is malformed") from exc
        if (
            body.investigation_id != authority.investigation_id
            or body.content_hash() != body_content_hash
        ):
            raise UnsafeArtifactState("artifact history body identity mismatch")
        payload = {
            "schema_version": 1,
            "account_id_digest": authority.account_digest,
            "investigation_id_digest": authority.investigation_digest,
            "body_content_hash": body_content_hash,
            "html_sha256": hashlib.sha256(raw).hexdigest(),
            "html": html,
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        root = Path(self.root or authority.account_dir().parents[1])
        path = self._history_path(authority, body_content_hash)
        with self.mutation_lock(authority):
            _atomic_claim(root, path, encoded)
        return path

    def read_history(
        self,
        authority: ArtifactAuthority,
        *,
        body_content_hash: str,
        max_bytes: int = MAX_HISTORY_HTML_BYTES,
    ) -> str:
        if max_bytes < 1 or max_bytes > MAX_HISTORY_HTML_BYTES:
            raise UnsafeArtifactState("artifact history read bound is invalid")
        path = self._history_path(authority, body_content_hash)
        with self.mutation_lock(authority):
            encoded = _read_regular(path, max_bytes=MAX_HISTORY_RECORD_BYTES)
        try:
            payload = json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UnsafeArtifactState("artifact history is corrupt") from exc
        if not isinstance(payload, dict):
            raise UnsafeArtifactState("artifact history is corrupt")
        html_value = payload.get("html")
        if not isinstance(html_value, str):
            raise UnsafeArtifactState("artifact history HTML is corrupt")
        raw = html_value.encode("utf-8")
        expected = {
            "schema_version": 1,
            "account_id_digest": authority.account_digest,
            "investigation_id_digest": authority.investigation_digest,
            "body_content_hash": body_content_hash,
            "html_sha256": hashlib.sha256(raw).hexdigest(),
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise UnsafeArtifactState("artifact history identity or digest mismatch")
        if len(raw) > max_bytes:
            raise UnsafeArtifactState("artifact history HTML exceeds the read bound")
        return html_value

    @contextmanager
    def mutation_lock(self, authority: ArtifactAuthority) -> Iterator[None]:
        """Serialize read-modify-write operations for one owner-bound artifact."""
        root = Path(self.root or authority.account_dir().parents[1])
        path = authority.artifact_path(self.root)
        _private_dir(root, path.parent)
        lock_path = path.with_suffix(".lock")
        thread_id = threading.get_ident()
        with self._held_locks_guard:
            reentrant = self._held_locks.get(lock_path) == thread_id
        if reentrant:
            yield
            return
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise UnsafeArtifactState("artifact mutation lock is unsafe") from exc
        with os.fdopen(fd, "a+b") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise UnsafeArtifactState("artifact mutation lock is unsafe")
            os.fchmod(handle.fileno(), 0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            with self._held_locks_guard:
                self._held_locks[lock_path] = thread_id
            try:
                yield
            finally:
                with self._held_locks_guard:
                    self._held_locks.pop(lock_path, None)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
