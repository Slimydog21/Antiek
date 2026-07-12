"""Cross-store serialization for consent and operation-bound stage plans."""

from __future__ import annotations

import fcntl
import hashlib
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class ConsentStagePlanCoordinator:
    """Serialize one job across owner authority and detail-plan stores."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    @contextmanager
    def acquire(self, job_id: str) -> Iterator[None]:
        if not isinstance(job_id, str) or not job_id.strip() or len(job_id) > 256:
            raise ValueError("job_id must be a bounded non-empty string")
        digest = hashlib.sha256(job_id.strip().encode("utf-8")).hexdigest()
        with self._guard:
            local = self._locks.setdefault(digest, threading.Lock())
        with local:
            path = self.directory / f"{digest}.lock"
            with path.open("a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = ["ConsentStagePlanCoordinator"]
