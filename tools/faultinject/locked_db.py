"""Real flock-contention injector for ``runtime.db_lock``."""

from __future__ import annotations

import contextlib
import fcntl
import os
from dataclasses import dataclass, field

from runtime import db_lock


@dataclass
class LockedDBInjector:
    """Hold the same sidecar flock ``connect_write`` must acquire."""

    db_path: str | os.PathLike[str]
    purpose: str = "faultinject"
    name: str = "locked_db"
    lock_path: str = field(default="", init=False)
    _fd: int | None = field(default=None, init=False, repr=False)

    def install(self) -> None:
        if self._fd is not None:
            return
        resolved = os.fspath(self.db_path)
        self.lock_path = db_lock._lock_path_for(resolved)
        parent = os.path.dirname(self.lock_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()} {self.purpose} faultinject\n".encode())
        self._fd = fd

    def uninstall(self) -> None:
        if self._fd is None:
            return
        fd = self._fd
        self._fd = None
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            os.close(fd)


def locked_db(
    db_path: str | os.PathLike[str],
    *,
    purpose: str = "faultinject",
) -> LockedDBInjector:
    return LockedDBInjector(db_path=db_path, purpose=purpose)
