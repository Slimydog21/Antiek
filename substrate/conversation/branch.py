"""Branch — atomic copy of a session's events up to a checkpoint."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from substrate.conversation.checkpoint import Checkpoint, verify_checkpoint
from substrate.conversation.event_log import EventLog


@dataclass(frozen=True)
class BranchLineage:
    child_session_id: str
    parent_session_id: str
    branch_position: int
    branch_hash: str
    created_at: str
    name: str


def _branches_file(project_root: Path) -> Path:
    return project_root / ".antiek" / "conversation" / "branches.jsonl"


def _conversation_dir(project_root: Path) -> Path:
    return project_root / ".antiek" / "conversation"


def create_branch(
    parent_session_id: str,
    checkpoint: Checkpoint,
    name: str,
    project_root: Path,
) -> str:
    verify_checkpoint(parent_session_id, project_root, checkpoint.position, checkpoint.hash)
    child_session_id = f"branch-{uuid.uuid4().hex[:12]}"
    conv = _conversation_dir(project_root)
    tmp_dir = conv / f".tmp-{child_session_id}"
    final_dir = conv / child_session_id
    if final_dir.exists():
        raise FileExistsError(f"child session dir already exists: {final_dir}")
    tmp_dir.mkdir(parents=True, exist_ok=False)
    try:
        parent_log = EventLog(parent_session_id, project_root)
        target = tmp_dir / "events.jsonl"
        with target.open("w", encoding="utf-8") as fp:
            for event in parent_log.iter_events(from_position=1, to_position=checkpoint.position):
                fp.write(event.canonical_json() + "\n")
        tmp_dir.rename(final_dir)
    except Exception:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    lineage = BranchLineage(
        child_session_id=child_session_id,
        parent_session_id=parent_session_id,
        branch_position=checkpoint.position,
        branch_hash=checkpoint.hash,
        created_at=datetime.now(timezone.utc).isoformat(),
        name=name,
    )
    bf = _branches_file(project_root)
    bf.parent.mkdir(parents=True, exist_ok=True)
    with bf.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(asdict(lineage), sort_keys=True, separators=(",", ":")) + "\n")
    return child_session_id


def list_branches(project_root: Path) -> list[BranchLineage]:
    bf = _branches_file(project_root)
    if not bf.exists():
        return []
    out: list[BranchLineage] = []
    with bf.open("r", encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                out.append(BranchLineage(**json.loads(line)))
    return out
