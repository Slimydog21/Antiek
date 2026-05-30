"""Resumable per-source ingest checkpoint store (SPR-09 M2).

The 2026-05-29 prod corpus run was hand-fed in tiny batches partly because a
restart re-discovered everything from scratch and could re-ingest. A standing
continuous engine the operator can leave running needs the opposite property:
kill it mid-batch, restart it, and it resumes from where each source left off
without re-ingesting and without losing committed-to-staging work.

This module is the SINGLE home for that resume state. It is a small JSON file
on the one box, written ATOMICALLY (tmp + ``os.replace``), holding per source::

    {source: {cursor, last_run_ts, ingested_ids_seen: [<dedup-basis>, ...]}}

Two §16 / rigor properties this file upholds, by construction:

  * **Off the live writer.** The checkpoint is a sidecar JSON file under
    ``~/.antiek/`` (the same convention ``source_throttle.json`` and the event
    log use). It NEVER acquires the DuckDB single-writer lock, so a checkpoint
    update can never block the live ``antiek.service`` (M2 criterion 4). The
    pattern is deliberately identical to ``substrate.source_throttle`` — a
    proven, daemon-free, last-writer-wins sidecar — not a second DB engine.

  * **Atomic per unit of work.** Every update writes a temp file in the same
    directory and ``os.replace``s it over the real file. ``os.replace`` is
    atomic on POSIX, so a crash mid-write can only leave EITHER the prior
    complete file OR the new complete file — never a truncated one that reads
    as "never ingested anything" and re-ingests the world (rigor card #3:
    crash safety is the property under test).

The "already seen" check is SPR-04's content-stable dedup *basis*
(``substrate.dedup.identity_basis`` — DOI / ISBN-13 / arXiv-id / source-id /
content-hash, never a mutable title+author string). This module stores and
checks that string; it does NOT re-derive identity. So on resume, a candidate
whose basis is already in ``ingested_ids_seen`` is skipped — the SAME identity
the cross-source dedup keyed on and that SPR-01's ``on_conflict=ignore`` merge
treats as a no-op. Cursor + dedup-key are belt-and-suspenders: the cursor
advances the source's pagination so we do not re-fetch, and the dedup-key set
catches anything double-fetched across a cursor boundary.

§16 box-bounded: this is a plain file + pure in-process logic. It introduces no
store engine, no service, no queue, no second runtime.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional

# The dedup-key set per source is bounded so the checkpoint file cannot grow
# without limit over a long-running continuous engine (a source with millions
# of ids would otherwise balloon the JSON). We keep the most-recent N seen
# bases — the cursor is the primary resume mechanism, the seen-set is the
# double-fetch guard for the window around the cursor, which is small. 50k
# bases is a few MB of JSON at most and covers far more than one round's worth
# of in-flight ids.
DEFAULT_MAX_SEEN_PER_SOURCE = 50_000


def default_checkpoint_path() -> str:
    """The cross-process checkpoint file. Honors
    ``ANTIEK_INGEST_CHECKPOINT_PATH`` for tests / alternate homes; otherwise
    lands under ``~/.antiek/`` alongside the other Antiek runtime state. It is
    NOT the DuckDB path — this state never goes through the single-writer lock.
    """
    env = os.environ.get("ANTIEK_INGEST_CHECKPOINT_PATH")
    if env:
        return env
    home = os.environ.get("ANTIEK_HOME", os.path.expanduser("~/.antiek"))
    return str(Path(home) / "ingest_checkpoint.json")


@dataclass
class SourceCheckpoint:
    """One source's resume state.

    ``cursor`` is the source-opaque pagination position the source reached
    (an offset, a page token, a date — the orchestrator chooses the shape per
    source; this store treats it as opaque). ``last_run_ts`` is when the source
    was last scheduled (epoch seconds), for observability + fair rotation
    tie-breaks. ``ingested_ids_seen`` is the bounded set of SPR-04 dedup BASES
    already enqueued-to-staging or merged for this source.
    """

    cursor: Optional[str] = None
    last_run_ts: float = 0.0
    ingested_ids_seen: set[str] = field(default_factory=set)

    @classmethod
    def from_dict(cls, d: Mapping[str, object]) -> "SourceCheckpoint":
        seen = d.get("ingested_ids_seen") or []
        return cls(
            cursor=(str(d["cursor"]) if d.get("cursor") is not None else None),
            last_run_ts=float(d.get("last_run_ts", 0.0) or 0.0),
            ingested_ids_seen=set(str(x) for x in seen if x is not None),
        )

    def to_dict(self) -> dict:
        # Sort the seen set so the serialized file is deterministic (stable
        # diff, reproducible test assertions) rather than set-iteration-order.
        return {
            "cursor": self.cursor,
            "last_run_ts": self.last_run_ts,
            "ingested_ids_seen": sorted(self.ingested_ids_seen),
        }


@dataclass
class _AllCheckpoints:
    """The whole file: a map of source-key -> per-source checkpoint."""

    sources: dict[str, SourceCheckpoint] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Mapping[str, object]) -> "_AllCheckpoints":
        raw = d.get("sources") if isinstance(d, Mapping) else None
        sources: dict[str, SourceCheckpoint] = {}
        if isinstance(raw, Mapping):
            for key, val in raw.items():
                if isinstance(val, Mapping):
                    sources[str(key)] = SourceCheckpoint.from_dict(val)
        return cls(sources=sources)

    def to_dict(self) -> dict:
        return {"sources": {k: v.to_dict() for k, v in self.sources.items()}}


class CheckpointStore:
    """Per-source resume state backed by ONE atomically-written JSON file.

    Cross-process: the file is re-read on every public call so a restarted
    process sees the prior process's committed cursors and seen-ids. The
    read-modify-write is unlocked (last-writer-wins) — identical to
    ``SourceThrottle``'s rationale: a single low-concurrency operator engine
    where the continuous loop is the only writer of this file, and even a lost
    write at most replays one unit of work (which the dedup-key catches as a
    no-op anyway).

    ``now`` is injectable so CI is deterministic and never depends on wall
    time.
    """

    def __init__(
        self,
        *,
        path: Optional[str] = None,
        max_seen_per_source: int = DEFAULT_MAX_SEEN_PER_SOURCE,
        now: Callable[[], float] = None,  # type: ignore[assignment]
    ) -> None:
        import time as _time

        self._path = Path(path or default_checkpoint_path())
        self._max_seen = int(max_seen_per_source)
        self._now = now or _time.time

    # -- file I/O (atomic write; unlocked, last-writer-wins) -----------------

    def _read_all(self) -> _AllCheckpoints:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _AllCheckpoints()
        except OSError:
            # An unreadable checkpoint must not silently make us re-ingest the
            # world; but we also cannot trust a corrupt file. Empty means "no
            # cursors yet" — the dedup-key set in the live DB / staging still
            # makes a re-ingest a no-op, so this degrades safely.
            return _AllCheckpoints()
        try:
            return _AllCheckpoints.from_dict(json.loads(raw))
        except (json.JSONDecodeError, ValueError, TypeError):
            return _AllCheckpoints()

    def _write_all(self, state: _AllCheckpoints) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic: write a temp file in the SAME directory (so os.replace is a
        # rename within one filesystem, which is atomic on POSIX) then replace.
        # A crash mid-write leaves the prior complete file or the new complete
        # file — never a truncated one.
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(state.to_dict(), indent=0), encoding="utf-8")
        os.replace(tmp, self._path)

    # -- public read API -----------------------------------------------------

    def get(self, source: str) -> SourceCheckpoint:
        """The current checkpoint for ``source`` (a fresh default when unseen).
        Reads the file each call so a restarted process sees committed state."""
        return self._read_all().sources.get(source, SourceCheckpoint())

    def cursor(self, source: str) -> Optional[str]:
        return self.get(source).cursor

    def all_sources(self) -> dict[str, SourceCheckpoint]:
        """Every checkpointed source's state (a snapshot copy)."""
        return dict(self._read_all().sources)

    def has_seen(self, source: str, basis: str) -> bool:
        """Whether this SPR-04 dedup basis was already ingested for ``source``.
        The orchestrator calls this on resume to skip a re-ingest — the SAME
        identity SPR-01's merge would treat as a no-op."""
        return basis in self.get(source).ingested_ids_seen

    # -- public write API (atomic per unit of work) --------------------------

    def record_unit(
        self,
        source: str,
        *,
        cursor: Optional[str] = None,
        new_bases: Optional[set[str]] = None,
    ) -> SourceCheckpoint:
        """Atomically advance ``source``'s checkpoint after one unit of work.

        ``cursor`` (when given) becomes the new resume position — the
        orchestrator only ever passes a cursor that ADVANCES the source's
        pagination, never one that rewinds it. ``new_bases`` are the SPR-04
        dedup bases ingested-to-staging this unit, unioned into the seen set
        (bounded to ``max_seen_per_source``, oldest-trimmed). ``last_run_ts`` is
        stamped to now.

        Returns the updated checkpoint. Atomicity: one read-modify-write +
        ``os.replace``; a kill between staging-write and this call simply means
        the unit replays on restart, and the dedup-key (in staging/live + this
        seen set once written) makes the replay a no-op (rigor card #3).
        """
        all_state = self._read_all()
        cp = all_state.sources.get(source) or SourceCheckpoint()
        if cursor is not None:
            cp.cursor = cursor
        if new_bases:
            cp.ingested_ids_seen |= set(new_bases)
            if len(cp.ingested_ids_seen) > self._max_seen:
                # Keep the most-recently-added bases. We have no per-id
                # timestamp, so "most recent" is approximated by sorted order;
                # the cursor is the real resume guarantee, so trimming the
                # double-fetch guard set never causes a re-ingest of work the
                # live DB already holds (SPR-01 merge is idempotent regardless).
                keep = sorted(cp.ingested_ids_seen)[-self._max_seen:]
                cp.ingested_ids_seen = set(keep)
        cp.last_run_ts = self._now()
        all_state.sources[source] = cp
        self._write_all(all_state)
        return cp

    def reset(self, source: Optional[str] = None) -> None:
        """Clear one source's checkpoint, or (source=None) the whole store.
        Operator/test affordance — never called on the hot path."""
        all_state = self._read_all()
        if source is None:
            all_state.sources.clear()
        else:
            all_state.sources.pop(source, None)
        self._write_all(all_state)
