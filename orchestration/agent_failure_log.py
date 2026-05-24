"""
Append-only log of observed agent failures.

Hashimoto's harness-engineering lens: anytime AI does a bad thing,
the operator should reach for tooling that catches the next instance.
This module is the persistent backstop — every agent failure (a
production agent path that produces wrong/surprising output) gets one
JSONL line here. The companion regression library at
``tests/regression/agent_failures/`` reads from the same vocabulary
(failure_id, prompt_hash) so a maintainer can trace a fixture back to
the original incident.

Where the log lives:

- Default: ``~/.antiek/agent_failures.jsonl``. Outside the repo so
  history doesn't bloat git and so operator-personal context (paths,
  env hints) isn't co-located with code.
- Override via ``ANTIEK_AGENT_FAILURE_LOG`` env var (path).
- Daily rotation: when the first write of a day arrives and the
  active file is non-empty, the current file is renamed to
  ``agent_failures/<YYYY-MM-DD>.jsonl`` and a fresh active file is
  opened. Old files are immutable (the file system enforces this only
  weakly; the convention is "do not edit, just append new lines").

Write path:

- Use ``os.O_APPEND`` so concurrent writers (the §7 daemon + the
  on-demand kanban worker) don't tear each other's lines. ``fcntl``-
  level locking would be overkill — single-line writes inside the
  POSIX PIPE_BUF (512 bytes minimum, typically 4096) are atomic on
  every modern filesystem, and our schema fits easily inside that.

Read path:

- ``iter_records()`` yields one ``AgentFailure`` per line; tolerant
  of malformed lines (skips with a warning).
- ``recent_failures(since=...)`` filters by timestamp for a CLI to
  surface "what's broken this week."

Schema:

    {
        "failure_id": "loky-semaphore-parameter-extractor",
        "observed_at": "2026-05-14T18:32:10.123Z",
        "agent": "claude" | "codex" | "operator-manual" | "...",
        "prompt_hash": "<sha256 from prompts/<hash>.md> | null",
        "phase": "parameter_extraction" | "synthesis" | "verify" | "...",
        "failure_type": "subprocess_died" | "rate_limited" | "ssl_handshake" | "...",
        "context_summary": "<≤300 chars human-readable>",
        "regression_fixture_path": "tests/regression/agent_failures/<slug>.yaml | null"
    }

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e2-harness.html
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

DEFAULT_LOG_PATH = Path.home() / ".antiek" / "agent_failures.jsonl"


def _now_iso() -> str:
    """Wall-clock UTC ISO-8601 with millisecond precision."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class AgentFailure:
    """One observed failure record.

    Frozen because the row is the source of truth — mutating after
    write would silently lie about the historical record.
    """

    failure_id: str
    observed_at: str = field(default_factory=_now_iso)
    agent: str = "unknown"
    prompt_hash: str | None = None
    phase: str = "unknown"
    failure_type: str = "unknown"
    context_summary: str = ""
    regression_fixture_path: str | None = None

    def to_json_line(self) -> str:
        """Serialize to a single newline-terminated JSON line.

        ``json.dumps`` with default options is sufficient — no need to
        sort keys (the dataclass field order is canonical) and no
        need to indent (single-line is what makes the file
        readable as JSONL).
        """
        return json.dumps(asdict(self), ensure_ascii=False) + "\n"


def log_path() -> Path:
    """Active log file path. Reads ``ANTIEK_AGENT_FAILURE_LOG`` env.

    Returns the configured path even if it doesn't exist yet — the
    caller is responsible for ``mkdir(parents=True, exist_ok=True)``
    before writing.
    """
    override = os.environ.get("ANTIEK_AGENT_FAILURE_LOG")
    if override:
        return Path(override).expanduser()
    return DEFAULT_LOG_PATH


def _archive_dir_for(active: Path) -> Path:
    """``~/.antiek/agent_failures/`` — sibling directory for rotated files."""
    return active.parent / "agent_failures"


def _maybe_rotate(active: Path) -> None:
    """Rotate ``active`` if its first line is from a previous date.

    Idempotent: a no-op when the active file is empty or already
    today's. Cost: one ``open + readline + close`` on every write —
    negligible compared to the JSONL append itself.
    """
    if not active.exists() or active.stat().st_size == 0:
        return
    with active.open("r", encoding="utf-8") as f:
        first = f.readline().strip()
    if not first:
        return
    try:
        row = json.loads(first)
        first_date = row.get("observed_at", "")[:10]  # YYYY-MM-DD
    except json.JSONDecodeError:
        return
    today_str = date.today().isoformat()
    if first_date == today_str or not first_date:
        return
    archive_dir = _archive_dir_for(active)
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / f"{first_date}.jsonl"
    # If a target with that name already exists (clock skew, manual
    # restore), append rather than overwrite.
    if target.exists():
        with target.open("ab") as dst, active.open("rb") as src:
            dst.write(src.read())
        active.unlink()
    else:
        active.replace(target)


def record(failure: AgentFailure, *, path: Path | None = None) -> Path:
    """Append one ``AgentFailure`` to the JSONL log. Returns the active path.

    Concurrent writes from two processes on a POSIX filesystem are safe
    as long as the line is shorter than ``PIPE_BUF`` (≥512 bytes
    guaranteed; typically 4096). Our schema fits well under that. We
    open with ``os.O_APPEND`` so the kernel performs the write
    atomically relative to the file's current end-of-data.
    """
    active = path if path is not None else log_path()
    active.parent.mkdir(parents=True, exist_ok=True)
    _maybe_rotate(active)
    line = failure.to_json_line()
    fd = os.open(str(active), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    return active


def iter_records(path: Path | None = None) -> Iterator[AgentFailure]:
    """Yield ``AgentFailure`` rows from the log; skip malformed lines.

    Tolerant of partially-flushed lines at end-of-file (a writer might
    have been interrupted mid-line). Strict-mode reading would risk
    crashing a read tool on real data; lenient parsing is the right
    default. A malformed line counts as a finding — the caller can
    surface it via the ``warnings`` channel if it cares.
    """
    active = path if path is not None else log_path()
    if not active.exists():
        return
    with active.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            yield AgentFailure(
                failure_id=row.get("failure_id", ""),
                observed_at=row.get("observed_at", ""),
                agent=row.get("agent", "unknown"),
                prompt_hash=row.get("prompt_hash"),
                phase=row.get("phase", "unknown"),
                failure_type=row.get("failure_type", "unknown"),
                context_summary=row.get("context_summary", ""),
                regression_fixture_path=row.get("regression_fixture_path"),
            )


def recent_failures(*, since_days: int, path: Path | None = None) -> list[AgentFailure]:
    """Return failures from the last ``since_days`` (UTC)."""
    if since_days < 0:
        raise ValueError("since_days must be non-negative")
    cutoff = datetime.now(timezone.utc).timestamp() - since_days * 86400
    out: list[AgentFailure] = []
    for record_ in iter_records(path):
        try:
            ts = datetime.fromisoformat(record_.observed_at.replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if ts >= cutoff:
            out.append(record_)
    return out
