"""Read-only-FS fault injector — reproduces the 2026-05-17 EROFS class safely.

The 2026-05-17 failure: a write to a read-only filesystem raised
``OSError(errno.EROFS)`` at an acquisition/retriever write site and the broad
fallback path swallowed it into a benign-looking "insufficient evidence"
outcome (the class SPR-02 makes fail-loud). To test that end-to-end we need to
reproduce the *exact* error at the *exact* place — without endangering the real
tree.

This injector does a **scoped monkeypatch of the low-level write primitives**
(``builtins.open`` / ``io.open`` in a write mode, ``os.replace``, ``os.rename``,
and ``os.open`` with a write flag) so that a write to ONE armed target path
raises ``OSError(errno.EROFS)`` — the same error the real read-only FS raised —
while every other path writes normally. It never ``chmod``-s a real directory,
so a crash mid-block cannot leave the tree read-only. All primitives are
restored in a ``finally`` on teardown.

``io.open`` is patched alongside ``builtins.open`` because ``pathlib.Path.open``
(hence ``Path.write_text`` / ``Path.write_bytes``) calls ``io.open`` directly —
patching only ``builtins.open`` would miss the ``Path``-based write seams.

Because the write primitives are process-global, this injector is a precision
instrument, not a stackable one: exactly ONE ``readonly_fs`` may be armed at a
time process-wide. A nested or concurrent second arm would corrupt the
save/restore of the shared primitives, so it is refused loudly (``RuntimeError``)
rather than silently leaking a stale patch. Arming ``readonly_fs`` alongside
``locked_db`` / ``provider_fault`` is fine — those touch different seams.

Known limitation (documented, not a silent gap): writes issued via the
``dir_fd`` / ``src_dir_fd`` / ``dst_dir_fd`` parameters with a *relative* name
resolve against that directory fd, not the cwd, so such a write to the armed
target is NOT matched. The real Antiek write seams (DuckDB, plain file writes)
use absolute / cwd-relative paths, so this does not affect them; a test that
needs ``openat`` semantics should arm on the absolute resolved path.
"""

from __future__ import annotations

import builtins
import errno
import io
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .inject import _CallGate

__all__ = ["readonly_fs"]

# The write primitives are process-global, so only one readonly_fs may be armed
# at a time. This guard makes overlapping arms fail loudly instead of corrupting
# the shared save/restore (see module docstring).
_ARM_LOCK = threading.Lock()
_armed = False

# Any of these characters in a mode string means the open intends to write
# ('w' truncate, 'a' append, 'x' exclusive-create, '+' read/update).
_WRITE_MODE_CHARS = frozenset("wax+")
# os.open flag bits that imply a write intent.
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC


def _is_write_mode(mode: str) -> bool:
    return any(c in _WRITE_MODE_CHARS for c in mode)


def _resolve(path: Any) -> Path | None:
    """Best-effort absolute resolution; ``None`` if ``path`` is not path-like
    (e.g. an integer file descriptor passed to ``open``)."""
    try:
        return Path(os.fspath(path)).resolve()
    except (TypeError, ValueError, OSError):
        return None


@contextmanager
def readonly_fs(
    target_path: str | os.PathLike[str],
    *,
    fail_on_call: int | None = None,
) -> Iterator[None]:
    """Arm a read-only-FS fault for writes to ``target_path`` only.

    While armed, a write-mode ``open`` / ``os.open`` targeting ``target_path``,
    or an ``os.replace`` / ``os.rename`` whose source or destination is
    ``target_path``, raises ``OSError(errno.EROFS)``. Reads and writes to every
    other path are untouched. See :class:`tools.faultinject.inject._CallGate`
    for ``fail_on_call`` semantics.
    """
    global _armed
    target = _resolve(target_path)
    if target is None:
        raise ValueError(f"target_path must be path-like, got {target_path!r}")
    with _ARM_LOCK:
        if _armed:
            raise RuntimeError(
                "readonly_fs is already armed elsewhere. It patches process-"
                "global write primitives, so arm exactly one read-only-FS fault "
                "at a time (nested/concurrent arming would corrupt the shared "
                "restore). Disarm the active one first."
            )
        _armed = True
    gate = _CallGate(fail_on_call)

    real_open = builtins.open
    real_io_open = io.open
    real_replace = os.replace
    real_rename = os.rename
    real_os_open = os.open

    def _erofs(path: Any) -> OSError:
        return OSError(errno.EROFS, os.strerror(errno.EROFS), str(path))

    def _fake_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any):
        if _is_write_mode(mode) and _resolve(file) == target and gate.should_fault():
            raise _erofs(file)
        return real_open(file, mode, *args, **kwargs)

    def _fake_replace(src: Any, dst: Any, *args: Any, **kwargs: Any):
        if (_resolve(dst) == target or _resolve(src) == target) and gate.should_fault():
            raise _erofs(dst)
        return real_replace(src, dst, *args, **kwargs)

    def _fake_rename(src: Any, dst: Any, *args: Any, **kwargs: Any):
        if (_resolve(dst) == target or _resolve(src) == target) and gate.should_fault():
            raise _erofs(dst)
        return real_rename(src, dst, *args, **kwargs)

    def _fake_os_open(path: Any, flags: int, *args: Any, **kwargs: Any):
        if (flags & _WRITE_FLAGS) and _resolve(path) == target and gate.should_fault():
            raise _erofs(path)
        return real_os_open(path, flags, *args, **kwargs)

    builtins.open = _fake_open  # type: ignore[assignment]
    io.open = _fake_open  # type: ignore[assignment]
    os.replace = _fake_replace  # type: ignore[assignment]
    os.rename = _fake_rename  # type: ignore[assignment]
    os.open = _fake_os_open  # type: ignore[assignment]
    try:
        yield
    finally:
        builtins.open = real_open  # type: ignore[assignment]
        io.open = real_io_open  # type: ignore[assignment]
        os.replace = real_replace  # type: ignore[assignment]
        os.rename = real_rename  # type: ignore[assignment]
        os.open = real_os_open  # type: ignore[assignment]
        with _ARM_LOCK:
            _armed = False
