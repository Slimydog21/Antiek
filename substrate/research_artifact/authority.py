"""Owner-bound identity and opaque paths for private ResearchArtifact HTML."""

from __future__ import annotations

import hashlib
import hmac
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from .paths import research_artifacts_dir

KEY_CODEC_VERSION = 1
OPERATOR_ACCOUNT_ID = "__operator__"
MAX_ID_BYTES = 512
_KEY_ENV = "ANTIEK_ARTIFACT_KEY_SECRET"


def _key_material() -> bytes:
    configured = os.environ.get(_KEY_ENV, "")
    configured_key = hashlib.sha256(configured.encode("utf-8")).digest() if configured else None
    key_path = research_artifacts_dir() / ".authority-key-v1"
    key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent_info = key_path.parent.lstat()
    if not stat.S_ISDIR(parent_info.st_mode) or stat.S_ISLNK(parent_info.st_mode):
        raise RuntimeError("ResearchArtifact authority key directory is unsafe")
    os.chmod(key_path.parent, 0o700)
    try:
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            read_fd = os.open(key_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise RuntimeError("ResearchArtifact authority key is unsafe") from exc
        try:
            info = os.fstat(read_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise RuntimeError("ResearchArtifact authority key is unsafe")
            raw = os.read(read_fd, 33)
        finally:
            os.close(read_fd)
    else:
        raw = configured_key or os.urandom(32)
        try:
            os.write(fd, raw)
            os.fsync(fd)
        finally:
            os.close(fd)
        parent_fd = os.open(key_path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    if len(raw) != 32:
        raise RuntimeError("ResearchArtifact authority key is invalid")
    if configured_key is not None and not hmac.compare_digest(raw, configured_key):
        raise RuntimeError(
            "ResearchArtifact authority key rotation requires an authenticated migration"
        )
    return raw


def _validated(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} is invalid")
    if (
        not value
        or value != value.strip()
        or len(value.encode("utf-8")) > MAX_ID_BYTES
        or "\x00" in value
    ):
        raise ValueError(f"{field} is invalid")
    return value


def identity_digest(kind: str, value: str) -> str:
    value = _validated(value, kind)
    message = f"antiek-research-artifact-v1\0{kind}\0{value}".encode()
    return hmac.new(_key_material(), message, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class ArtifactAuthority:
    account_id: str
    investigation_id: str
    local_operator_compatibility: bool = field(default=False, repr=False, compare=False)
    _account_digest: str = field(init=False, repr=False)
    _investigation_digest: str = field(init=False, repr=False)
    _event_stream_id: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.local_operator_compatibility, bool):
            raise ValueError("local operator compatibility is invalid")
        object.__setattr__(self, "account_id", _validated(self.account_id, "account_id"))
        object.__setattr__(
            self,
            "investigation_id",
            _validated(self.investigation_id, "investigation_id"),
        )
        object.__setattr__(self, "_account_digest", identity_digest("account", self.account_id))
        object.__setattr__(
            self,
            "_investigation_digest",
            identity_digest("investigation", self.investigation_id),
        )
        object.__setattr__(
            self,
            "_event_stream_id",
            identity_digest(
                "artifact-event-stream",
                f"{self._account_digest}:{self._investigation_digest}",
            ),
        )

    @property
    def account_digest(self) -> str:
        return self._account_digest

    @property
    def investigation_digest(self) -> str:
        return self._investigation_digest

    @property
    def account_key(self) -> str:
        return f"a{KEY_CODEC_VERSION}-{self.account_digest}"

    @property
    def investigation_key(self) -> str:
        return f"i{KEY_CODEC_VERSION}-{self.investigation_digest}"

    @property
    def event_stream_id(self) -> str:
        """Opaque owner-bound key for artifact-side events and deduplication."""
        return self._event_stream_id

    def account_dir(self, root: Path | None = None) -> Path:
        return (root or research_artifacts_dir()) / "accounts" / self.account_key

    def artifact_path(self, root: Path | None = None) -> Path:
        return self.account_dir(root) / "artifacts" / f"{self.investigation_key}.html"

    def sidecar_path(self, root: Path | None = None) -> Path:
        return self.artifact_path(root).with_suffix(".meta.json")


def operator_authority(investigation_id: str) -> ArtifactAuthority:
    """Named compatibility adapter for trusted local CLI/background callers."""
    return ArtifactAuthority(
        OPERATOR_ACCOUNT_ID,
        investigation_id,
        local_operator_compatibility=True,
    )
