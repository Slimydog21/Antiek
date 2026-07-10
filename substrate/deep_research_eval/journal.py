"""Append-only JSONL journal of EvalRun records.

Pattern follows ``substrate/antiek_bench/judged/journal.py`` (flock + fsync +
torn-tail tolerance) but owns its OWN path — it never shares antiek_bench's
store or evidence journal.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from .runner import EvalRun

DEFAULT_JOURNAL_PATH = Path.home() / ".antiek" / "deep_research_eval" / "eval_runs.jsonl"


class EvalJournalCorruptionError(RuntimeError):
    pass


class EvalRunJournal:
    def __init__(self, path: Path | str = DEFAULT_JOURNAL_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, run: EvalRun) -> None:
        line = json.dumps(run.to_dict(), sort_keys=True, separators=(",", ":"))
        payload = (line + "\n").encode()
        fd = os.open(str(self.path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    raise OSError("eval journal append made no progress")
                offset += written
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def read_all(self) -> tuple[EvalRun, ...]:
        """Replay the journal in append order. A torn final line (crash mid-append)
        is ignored; any other malformed row raises — fail closed, never skip."""
        if not self.path.exists():
            return ()
        raw = self.path.read_bytes()
        lines = raw.splitlines(keepends=True)
        runs: list[EvalRun] = []
        for index, line in enumerate(lines):
            if index == len(lines) - 1 and not line.endswith(b"\n"):
                break  # torn tail (crash mid-append) — tolerated by design
            if not line.strip():
                raise EvalJournalCorruptionError(f"blank eval run row {index + 1}")
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    raise ValueError("row must be object")
                runs.append(EvalRun.from_dict(data))
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise EvalJournalCorruptionError(f"invalid eval run row {index + 1}") from exc
        return tuple(runs)
