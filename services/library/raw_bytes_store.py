"""Content-addressed raw bytes store (2026-05-22 follow-up).

SPR-10 surfaced the gap: the share-bundle endpoint needs the original
PDF bytes alongside the sidecar, but the substrate only stores
``raw_text`` (the extracted text). Adding a column for in-DB blobs is
the wrong abstraction (DuckDB blob columns are usable but the format
isn't designed for hundreds of multi-MB PDFs per user). Storing in
arbitrary filesystem paths reinvents the GC + dedup wheel.

The abstraction that fits: content-addressed storage. Hash the bytes,
key them by hash, lay them out as
``~/.antiek/raw/<sha2[:2]>/<sha2>.<ext>``. This:

- **Dedups automatically.** Two users importing the same PDF only pay
  for one copy. Two ingests of the same URL get the same path.
- **Verifies cheaply.** ``sha256(file_contents) == filename`` is the
  integrity invariant. Corruption shows up as a hash mismatch on read.
- **Shards directories.** The first 2 hex chars (256 directories)
  keep any one directory under ~10k entries even for large corpora.
- **Mirrors the SPR-09 pattern.** ``~/.antiek/notebooks/<id>.antiek``
  is the AntiekPersistence layout. Operators already see this prefix
  in their home dir; adding ``~/.antiek/raw/`` is the same idiom.
- **Garbage-collectable.** A future GC pass can list filesystem hashes
  vs. ``documents.raw_bytes_path`` references and delete orphans.

The wire contract for ``documents.raw_bytes_path``:
- VALUE: absolute path under ``$ANTIEK_HOME/raw/...`` (or ``~/.antiek/raw/...``
  when ``ANTIEK_HOME`` isn't set)
- NULL means: not stored. Older rows (pre-2026-05-22), or imports
  where the bytes weren't retrievable (e.g., the user pasted a URL
  that's now 404).

The fetcher writes bytes through this store during ingest; the share-
bundle endpoint reads through it. No other writers — the store is
substrate-owned.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

_log = logging.getLogger(__name__)


def _resolve_root() -> Path:
    """Return ``$ANTIEK_HOME/raw`` if ``ANTIEK_HOME`` is set, else
    ``~/.antiek/raw``. Created lazily."""
    env = os.environ.get("ANTIEK_HOME")
    if env:
        return Path(env).expanduser() / "raw"
    return Path.home() / ".antiek" / "raw"


def _path_for_hash(sha256_hex: str, *, ext: str) -> Path:
    """``<root>/<first-two-hex>/<full-hex>.<ext>``. The 2-char shard
    cap is 256 dirs; collisions inside a shard remain extremely rare
    until the corpus crosses ~10k unique blobs."""
    if len(sha256_hex) != 64:
        raise ValueError(f"sha256_hex must be 64 chars; got {len(sha256_hex)}")
    ext = ext.lstrip(".") or "bin"
    return _resolve_root() / sha256_hex[:2] / f"{sha256_hex}.{ext}"


def store_bytes(
    raw_bytes: bytes,
    *,
    ext: str = "pdf",
) -> Tuple[str, str]:
    """Write ``raw_bytes`` to the content-addressed store. Returns
    ``(absolute_path, sha256_hex)``.

    Idempotent: writing the same bytes twice produces the same path
    and writes nothing the second time (the file already exists with
    the expected hash). Verifies the existing file's hash on the
    second write — if the disk got corrupted, the second write
    overwrites with the new bytes.
    """
    sha = hashlib.sha256(raw_bytes).hexdigest()
    path = _path_for_hash(sha, ext=ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = hashlib.sha256(path.read_bytes()).hexdigest()
        if existing == sha:
            # Dedup hit — already stored.
            return str(path), sha
        # Disk corruption — overwrite.
        _log.warning(
            "library.raw_bytes_store: %s exists but hash mismatch "
            "(have=%s, want=%s); overwriting.",
            path, existing, sha,
        )
    # Atomic write: stage under a temp name in the same directory, then
    # rename. Rename within a single filesystem is atomic on POSIX.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw_bytes)
    os.replace(tmp, path)
    return str(path), sha


def load_bytes(path: str) -> bytes:
    """Read raw bytes from the store. Validates that the filename hash
    matches the file contents — if not, raises ``IntegrityError``."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    bytes_on_disk = p.read_bytes()
    # The filename stem is the expected sha256.
    expected = p.stem
    actual = hashlib.sha256(bytes_on_disk).hexdigest()
    if expected != actual:
        raise IntegrityError(
            f"raw_bytes_store: {path} hash mismatch "
            f"(filename={expected}, contents={actual})"
        )
    return bytes_on_disk


def path_for_hash(sha256_hex: str, *, ext: str = "pdf") -> str:
    """Inverse of ``store_bytes``: given a sha, return the path where
    it would be stored. Useful for the GC pass."""
    return str(_path_for_hash(sha256_hex, ext=ext))


def iter_stored_hashes() -> list[str]:
    """List every sha256 currently in the store. Used by the GC pass
    that diffs against ``documents.raw_bytes_path`` references."""
    root = _resolve_root()
    if not root.exists():
        return []
    out: list[str] = []
    for shard in root.iterdir():
        if not shard.is_dir():
            continue
        for blob in shard.iterdir():
            sha = blob.stem
            if len(sha) == 64:
                out.append(sha)
    return out


class IntegrityError(Exception):
    """Raised by ``load_bytes`` when the file's sha256 doesn't match
    the filename. Indicates disk corruption — caller should treat the
    blob as lost and re-fetch if possible."""


__all__ = [
    "IntegrityError",
    "iter_stored_hashes",
    "load_bytes",
    "path_for_hash",
    "store_bytes",
]
