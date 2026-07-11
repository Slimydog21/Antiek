"""Filesystem-safe, migration-preserving keys for durable identifier stores."""

import hashlib
import re
from pathlib import Path

_DIRECT_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")


def durable_file_key(value: str) -> str:
    """Return a single safe path component for an opaque logical identifier.

    Existing conventional identifiers retain their historical filenames. Values
    containing separators, traversal components, control characters, or excessive
    length are mapped deterministically instead of being interpolated into a path.
    """

    if not isinstance(value, str) or not value:
        raise ValueError("durable identifier must be a non-empty string")
    if _DIRECT_KEY.fullmatch(value) and value not in {".", ".."}:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"id_sha256_{digest}"


def contained_legacy_json_path(
    directory: Path, value: str, *, flatten_forward_slashes: bool = False
) -> Path | None:
    """Reproduce an old filename rule only when it remains in ``directory``."""

    if not isinstance(value, str) or not value:
        return None
    legacy = value.replace("/", "_") if flatten_forward_slashes else value
    candidate = directory / f"{legacy}.json"
    if candidate.resolve(strict=False).parent != directory.resolve(strict=False):
        return None
    return candidate
