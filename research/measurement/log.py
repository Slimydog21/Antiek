"""Validated writer + compatible reader for measurement records (SPR-02 M4).

Writer contract
---------------
``append_measurement`` validates a ``MeasurementRecord`` against the
schema BEFORE appending, and writes NOTHING on reject (a malformed line
never lands in the log). On reject it raises ``MeasurementLogError``
naming the offending field — a clear, field-named error, not a silent
swallow and not a verbose Pydantic ``ValidationError`` the caller has to
parse. The append is ATOMIC PER LINE: a crash mid-write cannot corrupt a
prior record (the line is built in memory, then written in a single
``write`` call with a trailing newline; the OS guarantees a single
write ≤ PIPE_BUF is atomic, matching the event_log writer's idiom in
``substrate/event_log/events.py``).

This intentionally does NOT use the event_log ``_safe`` wrapper:
``_safe`` swallows errors to stderr and returns None (telemetry must
never break a real synthesis). But a REJECTED measurement record is a
caller bug, not telemetry noise — the caller passed an out-of-range
confidence or a missing field, and that MUST surface as a raise so the
caller fixes it, not as a silently-dropped record that leaves a hole in
the trajectory (INV-2: every provider call is recorded; a silent drop
breaks reconstruction). The durability PATTERN from event_log we DO
reuse: single-line atomic append, makedirs on the parent, no
read-modify-write.

Reader contract
---------------
``read_measurements`` tolerates OLDER schema versions (v27 and below —
records with fewer fields than the current schema) AND unknown fields
(forward-compat — a record from a future version with extra fields
parses, the extras are ignored). It NEVER crashes on an unknown field
or an unknown enum value (an unknown ``outcome`` or ``task_class``
string parses as the raw string; the caller decides what to do). It
skips blank/malformed lines with a stderr warning rather than raising,
so a single corrupt line doesn't poison the whole read. This matches
the event_log ``trajectory`` reader's tolerance (it ``continue``s on
``JSONDecodeError``).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from typing import Any

from research.measurement.schema import (
    MEASUREMENT_RECORD_SCHEMA_VERSION,
    MeasurementRecord,
    Outcome,
)
from research.measurement.task_class import TaskClass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
#
# Measurement records live in a measurement-specific JSONL, DISTINCT from the
# typed-Event trajectory ({investigation_id}.jsonl). The suffix
# ``.measurements.jsonl`` keeps them in the same per-investigation partition
# (one file per investigation, append-only) without interleaving with the
# Event envelope's discriminated-union payloads — an additive storage choice
# that touches no existing event_log code path. The events dir is the SAME
# one the event_log uses (ANTIEK_RESEARCH_EVENTS_DIR / ~/.antiek/research_events/)
# so sealing/backup tooling that operates on the dir sees both.


def _events_dir(events_dir: str | None = None) -> str:
    """Resolve the events dir, honoring the same env toggles as event_log."""
    if events_dir is not None:
        return events_dir
    return os.environ.get(
        "ANTIEK_RESEARCH_EVENTS_DIR",
        os.path.join(
            os.environ.get("ANTIEK_HOME", os.path.expanduser("~/.antiek")),
            "research_events",
        ),
    )


def _measurements_path(investigation_id: str, *, events_dir: str | None = None) -> str:
    return os.path.join(_events_dir(events_dir), f"{investigation_id}.measurements.jsonl")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
#
# The writer validates BEFORE append. Each check raises MeasurementLogError
# naming the offending field so the caller knows exactly what to fix. The
# checks are explicit (not Pydantic) so the error messages are field-named
# and clear — a Pydantic ValidationError buries the field name in a verbose
# structure that's awkward to surface to a caller wiring an adapter.


# Required fields (must be present and non-None). Matches MeasurementRecord's
# no-defaults dataclass: every field is required at construction. The writer
# re-checks because a caller could build a dict directly (the writer accepts
# a MeasurementRecord OR a dict, for test ergonomics).
_REQUIRED_FIELDS = (
    "schema_version",
    "investigation_id",
    "sub_question_id",
    "task_class",
    "provider",
    "tier",
    "cost_usd",
    "latency_ms",
    "confidence",
    "outcome",
    "correlation_id",
    "emitted_at",
)

# Valid task_class values (the TaskClass enum's string values). A record
# carrying a class not in this set is rejected — unknown classes are a
# caller bug at write time (the reader tolerates them for forward-compat,
# but the writer enforces the known set so a typo doesn't land on disk).
_VALID_TASK_CLASSES = frozenset(tc.value for tc in TaskClass)

# Valid outcome values (the Outcome enum's string values). Same discipline.
_VALID_OUTCOMES = frozenset(o.value for o in Outcome)


class MeasurementLogError(ValueError):
    """Raised when a measurement record fails validation before append.

    A ``ValueError`` subclass so it's catchable as a plain ValueError by
    callers that don't want to import the measurement package, but
    distinct so a caller can distinguish a validation reject from a
    different ValueError. The message always names the offending field.
    """


def _validate_record(record: MeasurementRecord | dict[str, Any]) -> None:
    """Validate a record against the schema. Raises MeasurementLogError
    (naming the field) on any violation. Writes nothing on reject — the
    caller (``append_measurement``) only appends after this returns."""
    # Normalize to a dict for uniform checking. asdict on a frozen
    # dataclass is safe (returns a fresh dict; the record is immutable).
    if isinstance(record, MeasurementRecord):
        data = asdict(record)
    elif isinstance(record, dict):
        # Defensive copy so a later mutation by the caller can't race the
        # validation. (The caller almost certainly won't, but the cost is
        # trivial and the invariant — "what we validated is what we wrote"
        # — is load-bearing for INV-2 reconstruction.)
        data = dict(record)
    else:
        raise MeasurementLogError(
            f"record must be a MeasurementRecord or dict, got "
            f"{type(record).__name__}"
        )

    # (a) Missing required field — each proven to raise + write nothing.
    for f in _REQUIRED_FIELDS:
        if f not in data:
            raise MeasurementLogError(
                f"missing required field: {f!r}. Every measurement record "
                "must carry all of: " + ", ".join(_REQUIRED_FIELDS) + "."
            )
        if data[f] is None:
            raise MeasurementLogError(
                f"required field {f!r} is None. Measurement records do not "
                "allow null on required fields."
            )

    # (b) cost_usd: float >= 0.0 (negative cost is impossible — a call
    # cannot earn money). NaN/inf rejected (they serialize to invalid JSON
    # and are meaningless telemetry).
    cost = data["cost_usd"]
    if not isinstance(cost, (int, float)) or isinstance(cost, bool):
        raise MeasurementLogError(
            f"cost_usd must be a number (int/float), got {type(cost).__name__}."
        )
    # NaN / inf checks (math.isnan/isinf would also work; direct comparison
    # avoids an import and is unambiguous: NaN != NaN, inf > any finite).
    if cost != cost:  # NaN
        raise MeasurementLogError("cost_usd is NaN; observed spend must be a finite number.")
    if cost in (float("inf"), float("-inf")):
        raise MeasurementLogError("cost_usd is infinite; observed spend must be a finite number.")
    if cost < 0:
        raise MeasurementLogError(
            f"cost_usd must be >= 0.0 (a call cannot earn money), got {cost}."
        )

    # (c) latency_ms: int >= 0 (negative latency is impossible; a call
    # cannot finish before it starts). bool is rejected (bool is a subtype
    # of int in Python — a True would silently serialize as 1).
    latency = data["latency_ms"]
    if isinstance(latency, bool) or not isinstance(latency, int):
        raise MeasurementLogError(
            f"latency_ms must be an int (milliseconds), got {type(latency).__name__}."
        )
    if latency < 0:
        raise MeasurementLogError(
            f"latency_ms must be >= 0 (a call cannot finish before it starts), got {latency}."
        )

    # (d) confidence: float in [0.0, 1.0]. Out-of-range rejected. NaN/inf
    # rejected (a normalized confidence is a probability, always finite
    # in [0,1]).
    conf = data["confidence"]
    if not isinstance(conf, (int, float)) or isinstance(conf, bool):
        raise MeasurementLogError(
            f"confidence must be a number (int/float), got {type(conf).__name__}."
        )
    if conf != conf:
        raise MeasurementLogError("confidence is NaN; normalized confidence must be in [0.0, 1.0].")
    if conf in (float("inf"), float("-inf")):
        raise MeasurementLogError("confidence is infinite; normalized confidence must be in [0.0, 1.0].")
    if conf < 0.0 or conf > 1.0:
        raise MeasurementLogError(
            f"confidence must be in [0.0, 1.0] (normalized scale), got {conf}."
        )

    # (e) task_class: must be a known TaskClass value. An unknown class is
    # a caller bug at write time (the reader tolerates unknowns for
    # forward-compat, but the writer enforces the known set so a typo
    # doesn't land on disk and poison the trajectory).
    tc = data["task_class"]
    if not isinstance(tc, str):
        raise MeasurementLogError(
            f"task_class must be a string (a TaskClass value), got {type(tc).__name__}."
        )
    if tc not in _VALID_TASK_CLASSES:
        raise MeasurementLogError(
            f"unknown task_class: {tc!r}. Known classes: "
            + ", ".join(sorted(_VALID_TASK_CLASSES))
            + ". (If this is a new class, add it to TaskClass in "
            "research/measurement/task_class.py.)"
        )

    # (f) outcome: must be a known Outcome value. Same discipline as
    # task_class.
    out = data["outcome"]
    if not isinstance(out, str):
        raise MeasurementLogError(
            f"outcome must be a string (an Outcome value), got {type(out).__name__}."
        )
    if out not in _VALID_OUTCOMES:
        raise MeasurementLogError(
            f"unknown outcome: {out!r}. Known outcomes: "
            + ", ".join(sorted(_VALID_OUTCOMES))
            + ". (If this is a new outcome, add it to Outcome in "
            "research/measurement/schema.py.)"
        )

    # (g) schema_version: int >= 1 (the record schema started at 1). A
    # non-int or < 1 is a caller bug.
    sv = data["schema_version"]
    if isinstance(sv, bool) or not isinstance(sv, int):
        raise MeasurementLogError(
            f"schema_version must be an int, got {type(sv).__name__}."
        )
    if sv < 1:
        raise MeasurementLogError(
            f"schema_version must be >= 1, got {sv}."
        )

    # (h) string fields non-empty: investigation_id, sub_question_id,
    # provider, tier, correlation_id, emitted_at. An empty string is a
    # missing value in disguise (a record with investigation_id="" would
    # partition to a file named ".measurements.jsonl" — a silent bug).
    for f in ("investigation_id", "sub_question_id", "provider", "tier",
              "correlation_id", "emitted_at"):
        v = data[f]
        if not isinstance(v, str):
            raise MeasurementLogError(
                f"{f} must be a string, got {type(v).__name__}."
            )
        if not v:
            raise MeasurementLogError(
                f"{f} must be a non-empty string (an empty value would "
                "partition/serialize incorrectly)."
            )


# ---------------------------------------------------------------------------
# Atomic append (matches event_log's _append_jsonl idiom)
# ---------------------------------------------------------------------------


def _append_jsonl(path: str, row: dict[str, Any]) -> None:
    """Append a single JSON line atomically.

    Matches the event_log writer's idiom (``substrate/event_log/events.py``
    ``_append_jsonl``): makedirs the parent, serialize to a single line,
    replace any embedded newlines (a payload value with a literal newline
    would split one record across two lines and corrupt the log), open in
    ``'a'`` mode, write ``line + "\\n"`` in one call.

    Atomicity: a single ``write`` of a string ≤ PIPE_BUF (4096 on Linux,
    512 on macOS) is atomic at the OS level — a crash mid-write cannot
    leave a partial line. Measurement records are small (a dozen fields,
    no payloads), so the serialized line is well under PIPE_BUF. We
    additionally guard against multi-line payloads by replacing embedded
    newlines (defense in depth — a record should never contain one, but
    if it does, we don't let it split the line).
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(row, default=str, separators=(",", ":"))
    if "\n" in line:
        line = line.replace("\n", "\\n")
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# Writer — validate THEN append (writes nothing on reject)
# ---------------------------------------------------------------------------


def append_measurement(
    record: MeasurementRecord | dict[str, Any],
    *,
    events_dir: str | None = None,
) -> str:
    """Validate ``record`` against the schema and append it atomically.

    Validates FIRST (raises ``MeasurementLogError`` naming the field on any
    violation) and writes NOTHING on reject — a malformed line never lands
    in the log. On success, appends one JSON line to
    ``{events_dir}/{investigation_id}.measurements.jsonl`` atomically.

    Args:
        record: a ``MeasurementRecord`` or a dict with the same keys. Dict
            acceptance is for test ergonomics and for adapters that build
            the row incrementally; the writer validates either identically.
        events_dir: override the events dir (defaults to
            ``ANTIEK_RESEARCH_EVENTS_DIR`` / ``~/.antiek/research_events/``).

    Returns:
        The ``correlation_id`` of the appended record (the stable id
        linking measurement <-> raw ResearchResult). Convenient for the
        caller to log/return.

    Raises:
        MeasurementLogError: if validation fails. The error message names
            the offending field. NOTHING is written on reject.
    """
    # Validate BEFORE touching the filesystem. A reject here means the
    # file is never opened — no partial write, no empty-line artifact.
    _validate_record(record)

    # Normalize to a dict for serialization (asdict on the dataclass).
    if isinstance(record, MeasurementRecord):
        data = asdict(record)
    else:
        data = dict(record)

    path = _measurements_path(data["investigation_id"], events_dir=events_dir)
    _append_jsonl(path, data)
    return data["correlation_id"]


# ---------------------------------------------------------------------------
# Reader — forward + backward compatible (never crashes on unknown/older)
# ---------------------------------------------------------------------------


def read_measurements(
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Read all measurement records for an investigation, in append order.

    Forward-compat: tolerates UNKNOWN fields (a record from a future
    schema version with extra fields parses; the extras are preserved in
    the returned dict so a caller can inspect them, but they never cause
    a crash).

    Backward-compat: tolerates OLDER schema versions (v27 and below —
    records with FEWER fields than the current schema). Missing fields
    are absent from the returned dict (the caller uses ``.get(...)``);
    the reader does not invent defaults that could mask a real absence.

    Robustness: skips blank lines and malformed JSON lines (with a
    stderr warning), so a single corrupt line does not poison the read.
    Matches the event_log ``trajectory`` reader's tolerance. An unknown
    ``outcome`` or ``task_class`` string parses as the raw string (the
    caller decides) — the reader does NOT reject, because a forward-compat
    reader that rejected unknown enum values would defeat the purpose of
    additive evolution.

    Ordering: returns records in the order they appear in the file
    (append order == emission order, since the writer appends one line
    per record and never reorders). This is the trajectory order the
    reconstruction query (``reconstruct_trajectory``) relies on. We do
    NOT sort by ``emitted_at`` here because append order is the
    authoritative order and a clock skew could reorder records that
    were emitted in a known sequence; ``reconstruct_trajectory`` sorts
    by ``emitted_at`` as a tiebreak only when needed.

    Args:
        investigation_id: the investigation to read.
        events_dir: override the events dir.

    Returns:
        A list of dicts (one per record) in append order. Empty list if
        the file doesn't exist (no records yet — a fresh investigation).
    """
    path = _measurements_path(investigation_id, events_dir=events_dir)
    if not os.path.exists(path):
        return []

    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                # Skip the corrupt line but surface it — a silent skip
                # would hide a real corruption. Matches event_log's
                # trajectory() tolerance (it continues on JSONDecodeError).
                print(
                    f"read_measurements: skipping malformed line {lineno} in "
                    f"{path}: {e!r}",
                    file=sys.stderr,
                )
                continue
            if not isinstance(rec, dict):
                # A non-object JSON line (e.g. a bare number/string) is
                # not a measurement record; skip with a warning.
                print(
                    f"read_measurements: skipping non-object line {lineno} in "
                    f"{path}: {rec!r}",
                    file=sys.stderr,
                )
                continue
            # Coerce numeric fields back to their typed form where the
            # value is present and unambiguous. JSON round-trips ints as
            # ints and floats as floats, so cost_usd may come back as int
            # if it was a whole number on the wire — normalize to float
            # for downstream consumers that expect a float. Do NOT invent
            # missing keys (backward-compat: an older record without a
            # field stays without it).
            if "cost_usd" in rec and isinstance(rec["cost_usd"], int) and not isinstance(rec["cost_usd"], bool):
                rec["cost_usd"] = float(rec["cost_usd"])
            if "confidence" in rec and isinstance(rec["confidence"], int) and not isinstance(rec["confidence"], bool):
                rec["confidence"] = float(rec["confidence"])
            records.append(rec)

    return records


__all__ = [
    "MeasurementLogError",
    "append_measurement",
    "read_measurements",
]
