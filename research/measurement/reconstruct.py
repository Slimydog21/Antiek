"""Reconstruction query — rebuild a provider trajectory from the log (SPR-02 M5).

INV-2 (trajectory purity): every provider call is recorded as a discrete
measurement event, so an investigation's provider trajectory — which
sub-question went to which provider/tier, what it cost, how long it took,
what it returned, in what order — is fully reconstructable from the log
alone. This module is the read helper that proves it: given an
investigation_id + the events dir, it returns the ORDERED measurement
events for that investigation.

Why a separate module from ``log.read_measurements``
----------------------------------------------------
``read_measurements`` is the raw reader (tolerant, returns dicts in
append order). ``reconstruct_trajectory`` is the QUERY: it guarantees
ORDER (by emission time, with a stable tiebreak), SCOPES to one
investigation (no bleed across investigations — a fixture with multiple
investigations returns only the requested one's records), and returns
``MeasurementRecord`` instances (typed values, not raw dicts) so the
caller gets the normalized shape the router will consume. The split
mirrors the event_log's separation of ``trajectory`` (raw read) from
``validate_trajectory`` (query/analysis).
"""

from __future__ import annotations

from research.measurement.log import read_measurements
from research.measurement.schema import MeasurementRecord


def reconstruct_trajectory(
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> list[MeasurementRecord]:
    """Return the ORDERED measurement records for one investigation.

    Proves INV-2: an investigation's provider trajectory is fully
    rebuildable from the log. The records are returned in EMISSION ORDER
    (sorted by ``emitted_at`` ascending, with ``correlation_id`` as a
    stable tiebreak for records that share a timestamp — e.g. two calls
    emitted in the same millisecond).

    Scoping: reads ONLY ``{investigation_id}.measurements.jsonl`` — it
    cannot bleed across investigations because each investigation's
    records live in a per-investigation file. A fixture with multiple
    investigations returns only the requested one's records.

    Tolerance: inherits the reader's forward/backward-compat (older
    records with fewer fields, unknown fields from future versions).
    An older record missing a field the current ``MeasurementRecord``
    requires is SKIPPED with a stderr warning (reconstructing a typed
    record from an incomplete dict would require inventing a default,
    which masks a real absence — better to skip and surface). Unknown
    FIELDS are ignored (the record still constructs). Unknown ENUM
    VALUES (outcome/task_class) are passed through as strings — the
    ``MeasurementRecord`` stores them as ``str`` fields precisely so a
    forward-compat reconstruction doesn't crash on a value the current
    enum doesn't know.

    Args:
        investigation_id: the investigation to reconstruct.
        events_dir: override the events dir.

    Returns:
        A list of ``MeasurementRecord`` in emission order. Empty list if
        the investigation has no measurement file (no provider calls
        recorded yet).
    """
    raw = read_measurements(investigation_id, events_dir=events_dir)

    # Sort by emitted_at ascending; correlation_id is a stable tiebreak
    # for same-timestamp records (two calls emitted in the same ms).
    # Append order is already emission order, but an explicit sort makes
    # the ordering guarantee independent of the reader's implementation
    # and robust to a log that was concatenated from multiple sources.
    raw.sort(key=lambda r: (r.get("emitted_at") or "", r.get("correlation_id") or ""))

    records: list[MeasurementRecord] = []
    for i, rec in enumerate(raw):
        # Reconstruct a typed MeasurementRecord. The record's fields are
        # all required at construction; an older-schema record missing a
        # field is skipped (with a warning) rather than reconstructed
        # with an invented default — inventing a default would silently
        # fabricate telemetry, violating the honesty the measurement
        # record exists to provide.
        try:
            records.append(MeasurementRecord(
                schema_version=rec["schema_version"],
                investigation_id=rec["investigation_id"],
                sub_question_id=rec["sub_question_id"],
                task_class=rec["task_class"],
                provider=rec["provider"],
                tier=rec["tier"],
                cost_usd=rec["cost_usd"],
                latency_ms=rec["latency_ms"],
                confidence=rec["confidence"],
                outcome=rec["outcome"],
                correlation_id=rec["correlation_id"],
                emitted_at=rec["emitted_at"],
            ))
        except KeyError as e:
            import sys
            print(
                f"reconstruct_trajectory: skipping record {i} for "
                f"investigation {investigation_id!r}: missing field {e}. "
                "(Likely an older-schema record; the field was added in a "
                "later version. The record is excluded from the typed "
                "trajectory but remains in the raw log.)",
                file=sys.stderr,
            )
            continue
        except TypeError as e:
            import sys
            print(
                f"reconstruct_trajectory: skipping record {i} for "
                f"investigation {investigation_id!r}: type error {e}. "
                "(Likely a malformed value in an older record.)",
                file=sys.stderr,
            )
            continue

    return records


__all__ = ["reconstruct_trajectory"]
