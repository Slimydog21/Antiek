"""Tamper-evident, dual-output run recorder.

Bridges a :class:`ScoreVerdict` (from the scorer) to the two frozen consumers
that close the recursive benchmark loop:

- a **view record** ``{task, model_id, score, n_runs, notes}`` for
  ``present_weekly_bench`` (the weekly Settings panel), and
- a **usage event** ``{task, success}`` for ``propose_next_week_weights`` (the
  failure-driven Laplace weight proposal).

One scored run produces BOTH. The mapping is deterministic: ``task`` comes from
the verdict, ``model_id`` from the candidate, ``score`` is the verdict's finite
float (``None`` if pending — the view marks the week ``incomplete``), and
``success`` is the verdict's real bool (``None`` if pending — the usage-learn
lane ignores non-bools as ``unknown_flags``).

Hard-to-vary invariants (each is a test):

1. **Tamper-evident hash chain.** Each record carries ``prev_hash`` (the prior
   record's hash, or ``GENESIS`` for the first) and ``record_hash`` (sha256 over
   ``prev_hash + canonical payload``). A break → :class:`LedgerCorruption`,
   never silent recovery. Absent/corrupt ledger → ``incomplete=True``.
2. **Secrets never persisted.** The canonical payload is audited before hashing;
   any of ``api_key``/``apikey``/``authorization``/``bearer``/``sk-``/
   ``raw_prompt``/``full_prompt`` raises before a record is written.
3. **Pending runs are incomplete, not invented.** A pending verdict (human score
   awaiting confirmation) writes a record with ``score=None``, ``success=None``;
   the view marks the week ``incomplete``; the usage event carries no real bool
   and is ignored by usage-learn's ``unknown_flags`` path — exactly the honest
   behavior.
4. **No network, no routing authority.** Pure file/JSON persistence. The
   authorized runner (a separate module) sets ``live_dispatch_authorized`` after
   the budget gate; the recorder never dispatches.

The frozen §2 contract shapes (from the execution-harness brief) are reproduced
verbatim in :class:`ViewRecord` and :class:`UsageEvent` so a future round-trip
test against the real consumers is zero-loss by construction.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

from .scorer import ScoreVerdict

GENESIS_HASH = "GENESIS"
RECORDER_VERSION = "antiek-bench-recorder-v1"

# Forbidden tokens in any persisted record payload (cross-bound redaction,
# mirroring scorecards._assert_no_sensitive_payload).
_FORBIDDEN_TOKENS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "authorization",
    "bearer ",
    "sk-",
    "raw_prompt",
    "full_prompt",
)


class LedgerCorruption(ValueError):
    """The hash chain broke (or the ledger file is unreadable). Never recovered silently."""


class ViewRecord(BaseModel):
    """Frozen §2 view record for ``present_weekly_bench``."""

    model_config = {"frozen": True}

    task: str
    model_id: str
    score: float | None = None
    n_runs: int = Field(default=1, ge=0)
    notes: str = ""


class UsageEvent(BaseModel):
    """Frozen §2 usage event for ``propose_next_week_weights``."""

    model_config = {"frozen": True}

    task: str
    success: bool | None = None  # None = pending/unknown; ignored by usage-learn


class RunRecord(BaseModel):
    """One tamper-evident run record: the verdict + its dual outputs + chain fields."""

    model_config = {"frozen": True}

    record_hash: str
    prev_hash: str
    version: str = RECORDER_VERSION
    week_id: str
    task_id: str
    candidate_model_id: str
    method: str
    score: float | None
    success: bool | None
    pending: bool
    disputed: bool
    rationale: str | None = None
    judge_model_id: str | None = None
    view_record: ViewRecord
    usage_event: UsageEvent


def _canonical_hash(payload: dict[str, object], prev_hash: str) -> str:
    blob = json.dumps(
        {"prev_hash": prev_hash, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _assert_no_secrets(payload: dict[str, object]) -> None:
    text = json.dumps(payload, sort_keys=True).lower()
    found = [tok for tok in _FORBIDDEN_TOKENS if tok in text]
    if found:
        raise ValueError(
            f"bench record contains forbidden sensitive token(s): {found}"
        )


def record_verdict(
    verdict: ScoreVerdict,
    *,
    week_id: str,
) -> RunRecord:
    """Turn one scored verdict into a tamper-evident dual-output record.

    Pure: builds the record object (with ``prev_hash=GENESIS`` and a fresh
    ``record_hash``) but does NOT persist it. Call :func:`append_to_ledger` to
    chain it onto a ledger file, or keep it in-memory for testing.
    """

    view = ViewRecord(
        task=verdict.task_id,
        model_id=verdict.candidate_model_id,
        score=verdict.score,
        n_runs=1,
        notes=verdict.rationale or "",
    )
    event = UsageEvent(task=verdict.task_id, success=verdict.success)
    payload: dict[str, object] = {
        "version": RECORDER_VERSION,
        "week_id": week_id,
        "task_id": verdict.task_id,
        "candidate_model_id": verdict.candidate_model_id,
        "method": verdict.method,
        "score": verdict.score,
        "success": verdict.success,
        "pending": verdict.pending,
        "disputed": verdict.disputed,
        "rationale": verdict.rationale,
        "judge_model_id": verdict.judge_model_id,
        "view_record": view.model_dump(mode="json"),
        "usage_event": event.model_dump(mode="json"),
    }
    _assert_no_secrets(payload)
    record_hash = _canonical_hash(payload, prev_hash=GENESIS_HASH)
    return RunRecord(
        record_hash=record_hash,
        prev_hash=GENESIS_HASH,
        week_id=week_id,
        task_id=verdict.task_id,
        candidate_model_id=verdict.candidate_model_id,
        method=verdict.method,
        score=verdict.score,
        success=verdict.success,
        pending=verdict.pending,
        disputed=verdict.disputed,
        rationale=verdict.rationale,
        judge_model_id=verdict.judge_model_id,
        view_record=view,
        usage_event=event,
    )


def append_to_ledger(record: RunRecord, *, ledger_path: Path) -> RunRecord:
    """Append a record to a hash-chained ledger file.

    Reads the current tail's ``record_hash`` to set this record's ``prev_hash``,
    re-hashes, and appends. Raises :class:`LedgerCorruption` if the chain is
    broken or the file is unreadable — never silently re-derives.
    """

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_ledger(ledger_path)
    prev_hash = existing[-1].record_hash if existing else GENESIS_HASH
    if existing and existing[-1].record_hash != record.prev_hash and existing:
        # Re-chain the record onto the real tail.
        pass
    payload = _record_payload(record)
    new_hash = _canonical_hash(payload, prev_hash=prev_hash)
    chained = record.model_copy(
        update={"record_hash": new_hash, "prev_hash": prev_hash}
    )
    _assert_no_secrets(_record_payload(chained))
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(chained.model_dump_json() + "\n")
    return chained


def read_ledger(ledger_path: Path) -> list[RunRecord]:
    """Read + verify a ledger's hash chain. Raises on corruption."""
    return _read_ledger(ledger_path)


def week_view_records(ledger_path: Path, *, week_id: str) -> list[ViewRecord]:
    """All view records for a week, from a verified ledger."""
    records = _read_ledger(ledger_path)
    return [r.view_record for r in records if r.week_id == week_id]


def week_usage_events(ledger_path: Path, *, week_id: str) -> list[UsageEvent]:
    """All usage events for a week, from a verified ledger."""
    records = _read_ledger(ledger_path)
    return [r.usage_event for r in records if r.week_id == week_id]


def week_incomplete(ledger_path: Path, *, week_id: str) -> bool:
    """True if any record in the week is pending or has a null score."""
    records = _read_ledger(ledger_path)
    week = [r for r in records if r.week_id == week_id]
    if not week:
        return True
    return any(r.pending or r.score is None for r in week)


def _read_ledger(ledger_path: Path) -> list[RunRecord]:
    if not ledger_path.is_file():
        return []
    try:
        raw = ledger_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LedgerCorruption(f"ledger unreadable: {exc}") from exc
    records: list[RunRecord] = []
    expected_prev = GENESIS_HASH
    for lineno, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = RunRecord.model_validate_json(line)
        except Exception as exc:
            raise LedgerCorruption(
                f"ledger line {lineno}: unparseable record ({exc})"
            ) from exc
        if record.prev_hash != expected_prev:
            raise LedgerCorruption(
                f"ledger line {lineno}: hash chain broken "
                f"(expected prev_hash={expected_prev!r}, got {record.prev_hash!r})"
            )
        recomputed = _canonical_hash(_record_payload(record), prev_hash=expected_prev)
        if recomputed != record.record_hash:
            raise LedgerCorruption(
                f"ledger line {lineno}: record_hash mismatch (tampered payload)"
            )
        records.append(record)
        expected_prev = record.record_hash
    return records


def _record_payload(record: RunRecord) -> dict[str, object]:
    """The hash payload (excludes chain fields; they wrap it)."""
    return {
        "version": record.version,
        "week_id": record.week_id,
        "task_id": record.task_id,
        "candidate_model_id": record.candidate_model_id,
        "method": record.method,
        "score": record.score,
        "success": record.success,
        "pending": record.pending,
        "disputed": record.disputed,
        "rationale": record.rationale,
        "judge_model_id": record.judge_model_id,
        "view_record": record.view_record.model_dump(mode="json"),
        "usage_event": record.usage_event.model_dump(mode="json"),
    }
