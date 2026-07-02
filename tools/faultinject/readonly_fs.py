"""Path-scoped read-only-filesystem fault injector."""

from __future__ import annotations

import builtins
import errno
import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_WRITE_MODES = frozenset({"w", "a", "x", "+"})


def _is_write_mode(mode: str) -> bool:
    return any(flag in mode for flag in _WRITE_MODES)


def _under(path: Any, target: Path) -> bool:
    try:
        candidate = Path(os.fspath(path)).expanduser().resolve(strict=False)
    except TypeError:
        return False
    try:
        candidate.relative_to(target)
        return True
    except ValueError:
        return candidate == target


@dataclass
class ReadonlyFSInjector:
    """Raise ``OSError(errno.EROFS)`` for writes under ``target_path`` only."""

    target_path: str | os.PathLike[str]
    fail_on_call: int = 1
    errno_code: int = errno.EROFS
    name: str = "readonly_fs"
    calls: int = 0
    _original_open: Any = field(default=None, init=False, repr=False)
    _original_io_open: Any = field(default=None, init=False, repr=False)
    _original_replace: Any = field(default=None, init=False, repr=False)
    _armed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.fail_on_call < 1:
            raise ValueError("fail_on_call must be >= 1")
        self._target = Path(self.target_path).expanduser().resolve(strict=False)

    def _maybe_raise(self, path: Any) -> None:
        if not _under(path, self._target):
            return
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise OSError(
                self.errno_code,
                os.strerror(self.errno_code),
                os.fspath(path),
            )

    def install(self) -> None:
        if self._armed:
            return
        self.calls = 0
        self._original_open = builtins.open
        self._original_io_open = io.open
        self._original_replace = os.replace
        original_open = self._original_open
        original_io_open = self._original_io_open
        original_replace = self._original_replace
        injector = self

        def guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if _is_write_mode(mode):
                injector._maybe_raise(file)
            return original_open(file, mode, *args, **kwargs)

        def guarded_io_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if _is_write_mode(mode):
                injector._maybe_raise(file)
            return original_io_open(file, mode, *args, **kwargs)

        def guarded_replace(src: Any, dst: Any, *args: Any, **kwargs: Any) -> Any:
            injector._maybe_raise(dst)
            return original_replace(src, dst, *args, **kwargs)

        builtins.open = guarded_open
        io.open = guarded_io_open
        os.replace = guarded_replace
        self._armed = True

    def uninstall(self) -> None:
        if not self._armed:
            return
        builtins.open = self._original_open
        io.open = self._original_io_open
        os.replace = self._original_replace
        self._original_open = None
        self._original_io_open = None
        self._original_replace = None
        self._armed = False


def readonly_fs(
    target_path: str | os.PathLike[str],
    *,
    fail_on_call: int = 1,
    errno_code: int = errno.EROFS,
) -> ReadonlyFSInjector:
    return ReadonlyFSInjector(
        target_path=target_path,
        fail_on_call=fail_on_call,
        errno_code=errno_code,
    )
