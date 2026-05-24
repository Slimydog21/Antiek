"""Checkpoint — content-hashed snapshot of the first N events of a session."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from substrate.conversation.event_log import EventLog


class CheckpointVerifyFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class Checkpoint:
    session_id: str
    position: int
    hash: str
    created_at: str
    label: str | None = None


def _compute_hash(session_id: str, project_root: Path, position: int) -> str:
    if position < 1:
        raise ValueError(f"position must be >= 1, got {position}")
    log = EventLog(session_id, project_root)
    actual_high = log.position()
    if position > actual_high:
        raise ValueError(
            f"cannot checkpoint position {position}: session has only {actual_high} events"
        )
    h = hashlib.sha256()
    for event in log.iter_events(from_position=1, to_position=position):
        h.update(event.canonical_json().encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def _checkpoints_file(session_id: str, project_root: Path) -> Path:
    return project_root / ".antiek" / "conversation" / session_id / "checkpoints.jsonl"


def create_checkpoint(
    session_id: str,
    project_root: Path,
    position: int,
    label: str | None = None,
) -> Checkpoint:
    digest = _compute_hash(session_id, project_root, position)
    cp = Checkpoint(
        session_id=session_id,
        position=position,
        hash=digest,
        created_at=datetime.now(timezone.utc).isoformat(),
        label=label,
    )
    f = _checkpoints_file(session_id, project_root)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(asdict(cp), sort_keys=True, separators=(",", ":")) + "\n")
    return cp


def list_checkpoints(session_id: str, project_root: Path) -> list[Checkpoint]:
    f = _checkpoints_file(session_id, project_root)
    if not f.exists():
        return []
    out: list[Checkpoint] = []
    with f.open("r", encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                out.append(Checkpoint(**json.loads(line)))
    return out


def verify_checkpoint(
    session_id: str,
    project_root: Path,
    position: int,
    expected_hash: str,
) -> None:
    actual = _compute_hash(session_id, project_root, position)
    if actual != expected_hash:
        raise CheckpointVerifyFailed(
            f"checkpoint hash mismatch for session={session_id} position={position}: "
            f"expected={expected_hash}, actual={actual}"
        )
