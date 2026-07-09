"""Bench result + proposal store (offline)."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


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
        return json.loads(path.read_text(encoding="utf-8"))

    def list_runs(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted((self.root / "runs").glob("*.json")):
            out.append(json.loads(path.read_text(encoding="utf-8")))
        return out

    def put_proposal(self, proposal_id: str, proposal: dict[str, Any]) -> None:
        path = self.root / "proposals" / f"{proposal_id.replace('/', '_')}.json"
        path.write_text(json.dumps(proposal, sort_keys=True, indent=2), encoding="utf-8")

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        path = self.root / "proposals" / f"{proposal_id.replace('/', '_')}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
