"""EventLog -- append-only per-session JSONL writer."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Iterator

from substrate.conversation.event import Event


class ConversationLogCorrupted(RuntimeError):
    pass


class EventLog:
    def __init__(
        self, session_id: str, project_root: Path, *, fsync_on_append: bool = True,
    ) -> None:
        if "/" in session_id or ".." in session_id:
            raise ValueError(f"session_id must not contain '/' or '..': {session_id!r}")
        self.session_id = session_id
        self.project_root = project_root
        self.fsync_on_append = fsync_on_append
        self.dir = project_root / ".antiek" / "conversation" / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "events.jsonl"

    def position(self) -> int:
        if not self.path.exists():
            return 0
        last_line = None
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line
        if last_line is None:
            return 0
        try:
            data = json.loads(last_line)
            return int(data["position"])
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise ConversationLogCorrupted(
                f"final line of {self.path} is not a valid Event JSON: {exc!r}"
            ) from exc

    def iter_events(
        self, *, from_position: int = 1, to_position: int | None = None,
    ) -> Iterator[Event]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    event = Event(**data)
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    raise ConversationLogCorrupted(
                        f"{self.path}:{line_no} not parseable as Event: {exc!r}"
                    ) from exc
                if event.position < from_position:
                    continue
                if to_position is not None and event.position > to_position:
                    break
                yield event

    def append(self, event: Event) -> None:
        expected = self.position() + 1
        if event.position != expected:
            raise ConversationLogCorrupted(
                f"expected position {expected}, got {event.position} "
                f"(append must be strictly monotonic)"
            )
        with self.path.open("a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(event.canonical_json() + "\n")
                f.flush()
                if self.fsync_on_append:
                    os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
