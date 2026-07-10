"""Bench result + proposal store (offline).

Usage events for Antiek-bench rewrite live as a special run id
``_usage_events`` (see usage_bridge). Durable resolution:

* ``ANTIEK_BENCH_USAGE_DIR`` set → ``FileBenchStore`` under that root
* unset → process-local ``InMemoryBenchStore`` (default for tests/CI)
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# Env for durable usage event persistence (operator opt-in).
ANTIEK_BENCH_USAGE_DIR_ENV = "ANTIEK_BENCH_USAGE_DIR"

@runtime_checkable
class BenchStore(Protocol):
    def put_run(self, run_id: str, run: dict[str, Any]) -> None: ...
    def get_run(self, run_id: str) -> dict[str, Any] | None: ...
    def list_runs(self) -> list[dict[str, Any]]: ...
    def put_proposal(self, proposal_id: str, proposal: dict[str, Any]) -> None: ...
    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None: ...


@dataclass
class InMemoryBenchStore:
    _runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _proposals: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def put_run(self, run_id: str, run: dict[str, Any]) -> None:
        with self._lock:
            self._runs[run_id] = dict(run)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._runs.get(run_id)
            return dict(row) if row is not None else None

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._runs.values()]

    def put_proposal(self, proposal_id: str, proposal: dict[str, Any]) -> None:
        with self._lock:
            self._proposals[proposal_id] = dict(proposal)

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._proposals.get(proposal_id)
            return dict(row) if row is not None else None


@dataclass
class FileBenchStore:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        (self.root / "runs").mkdir(parents=True, exist_ok=True)
        (self.root / "proposals").mkdir(parents=True, exist_ok=True)

    def put_run(self, run_id: str, run: dict[str, Any]) -> None:
        path = self.root / "runs" / f"{run_id.replace('/', '_')}.json"
        path.write_text(json.dumps(run, sort_keys=True, indent=2), encoding="utf-8")

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        path = self.root / "runs" / f"{run_id.replace('/', '_')}.json"
        if not path.is_file():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def list_runs(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted((self.root / "runs").glob("*.json")):
            out.append(json.loads(path.read_text(encoding="utf-8")))
        return out

    def put_proposal(self, proposal_id: str, proposal: dict[str, Any]) -> None:
        path = self.root / "proposals" / f"{proposal_id.replace('/', '_')}.json"
        payload = json.dumps(proposal, sort_keys=True, indent=2).encode()
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        path = self.root / "proposals" / f"{proposal_id.replace('/', '_')}.json"
        if not path.is_file():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data


def usage_store_data_dir() -> Path | None:
    """Resolve durable usage-store root when ANTIEK_BENCH_USAGE_DIR is set."""
    raw = (os.environ.get(ANTIEK_BENCH_USAGE_DIR_ENV) or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def resolve_usage_store(
    *,
    root: Path | str | None = None,
    create_if_missing: bool = True,
) -> BenchStore | None:
    """Construct the bench store used for usage event write/read.

    * Explicit ``root`` or ``ANTIEK_BENCH_USAGE_DIR`` → FileBenchStore (durable)
    * Otherwise → InMemoryBenchStore when create_if_missing else None

    Does not open a second usage writer — callers still use record_usage_event.
    """
    base: Path | None = (
        Path(root).expanduser() if root is not None else usage_store_data_dir()
    )

    if base is not None:
        base.mkdir(parents=True, exist_ok=True)
        return FileBenchStore(base)

    if not create_if_missing:
        return None
    return InMemoryBenchStore()
