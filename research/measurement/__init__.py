"""Research measurement — the per-provider-call trajectory record (SPR-02).

This package owns the **measurement event**: one normalized record per
``ResearchProvider`` call, recording the observed cost / latency /
confidence / outcome of that call so the provider trajectory is fully
reconstructable from the log (INV-2). It is the DATA the router
(SPR-07) will READ; this sprint does not route, and the adapters
(SPR-03/04) will EMIT these records via the writer here — the schema +
writer + reader they call are what this package ships.

Scope (SPR-02):

* ``schema`` — the ``MeasurementRecord`` value shape (frozen dataclass),
  the ``Outcome`` enum, and the ``from_research_result`` helper that
  proves the record carries only NORMALIZED fields (INV-4) — never raw
  provider payload shape.
* ``task_class`` — a coarse, operator-legible task-class taxonomy with a
  deterministic ``classify`` prior (real classification is the router's
  job in SPR-07).
* ``log`` — a validated writer (rejects out-of-range / missing /
  unknown-enum BEFORE append; writes nothing on reject; atomic per line)
  and a forward/backward-compatible reader (tolerates older schema
  versions and unknown fields, never crashes on a field it doesn't know).
* ``reconstruct`` — a read helper returning the ORDERED measurement
  events for one investigation, proving INV-2 (trajectory purity): the
  provider trajectory is fully rebuildable from the log.

What this package does NOT do:

* No routing (SPR-07). The measurement event is data the router reads;
  this sprint owns the schema+writer+reader, not the decision.
* No adapter wiring (SPR-03/04). Adapters will call
  ``log.append_measurement``; this sprint ships the callable surface with
  a stub caller in tests only.
* No retry / budget / resilience (SPR-05/06).
* No modification to SPR-01's ``research/providers/types.py`` /
  ``base.py`` — those are a read-only dependency the record is built
  FROM (via ``from_research_result``).

Storage model
-------------
Measurement records share the trajectory store's storage discipline
(append-only JSONL, one record per line, sealed later) but are a
DISTINCT record shape from the typed ``Event`` envelope in
``substrate/schemas/events.py``. The measurement record is normalized
provider-call telemetry; it rides its own JSONL per investigation at
``{ANTIEK_RESEARCH_EVENTS_DIR}/{investigation_id}.measurements.jsonl``
so it does not interleave with (or require a payload-variant slot in)
the typed Event discriminated union — an additive change that touches
no existing payload. The ``ActionType.RESEARCH_PROVIDER_MEASURED``
vocabulary member exists so the action vocabulary acknowledges the
event; the record itself is written by this package's writer, not by
``emit_typed``.
"""

from __future__ import annotations

from research.measurement.log import (
    MeasurementLogError,
    append_measurement,
    read_measurements,
)
from research.measurement.reconstruct import reconstruct_trajectory
from research.measurement.schema import (
    MEASUREMENT_RECORD_SCHEMA_VERSION,
    MeasurementRecord,
    Outcome,
    from_research_result,
)
from research.measurement.task_class import TaskClass, classify

__all__ = [
    "MEASUREMENT_RECORD_SCHEMA_VERSION",
    "MeasurementLogError",
    "MeasurementRecord",
    "Outcome",
    "TaskClass",
    "append_measurement",
    "classify",
    "from_research_result",
    "read_measurements",
    "reconstruct_trajectory",
]
