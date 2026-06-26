"""The measurement record — one normalized row per provider call (SPR-02).

This is the value shape a provider call's OBSERVED telemetry lands in.
One ``MeasurementRecord`` == one ``ResearchProvider.answer`` call. It
records what the call ACTUALLY cost / took / returned (post-call
observations), NOT the SPR-01 ``CostModel`` estimates the router used to
SELECT the call. The distinction is load-bearing (see ``cost_usd`` /
``latency_ms`` field docs): estimates let the router budget before the
call; the record lets it reconcile after. The router (SPR-07) reads
these records to learn which provider/tier/task-class combinations
deliver; this sprint owns the record + writer + reader, not the
learning.

INV-2 (trajectory purity): every provider call is recorded as a discrete
measurement event, so the provider trajectory — which sub-question went
to which provider/tier, what it cost, how long it took, what it
returned — is fully reconstructable from the log alone. Decomposition,
provider selection, and answer verification stay in-house; the
measurement event is the receipt that a provider call happened and what
it produced inside the runner's trajectory.

INV-4 (normalized contract): the record carries ONLY normalized fields
(``provider``, ``tier``, ``cost_usd``, ``latency_ms``, ``confidence``,
``outcome``) — the same normalized shape every ``ResearchProvider``
returns (SPR-01 ``ResearchResult``). It does NOT embed raw provider
payload shape: no Exa ``score``, no Parallel ``chunk_id``, no provider-
specific dict. The raw payload is auditable behind the SPR-01
``RawRef`` handle (resolvable by the adapter, not by this record); the
``correlation_id`` links this record to that handle so an audit can
join measurement <-> raw without the measurement carrying the raw.

Why a frozen dataclass (not a TypedDict, not a Pydantic model)
--------------------------------------------------------------
``ResearchResult`` (SPR-01) is a ``@dataclass(frozen=True)`` and this
record is built FROM it via ``from_research_result``. Matching that
idiom keeps the measurement layer dependency-light and structurally
consistent with the provider contract it measures: the record is a pure
value, constructed in tests and by adapters without pulling Pydantic
onto the construction path, and frozen so a caller cannot mutate a
record after the writer has serialized it (a mutated-in-place record
would diverge from what was logged). A TypedDict would offer no
immutability and no constructor validation surface; a Pydantic model
would pull a heavy dependency into a layer that only needs to serialize
a flat dict to JSONL (the writer does its OWN validation, in
``log.py``, so it can name the offending field in the error — Pydantic's
``ValidationError`` is verbose and field-name extraction is fiddly, and
the writer's job is precisely to produce a CLEAR field-named error on
reject). The frozen dataclass is the right vehicle: value semantics,
immutability, zero new dependencies, matches the codebase's chosen
vehicle for normalized value shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from research.providers.types import RawRef, ResearchResult

# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------
#
# The measurement record carries its OWN schema version (distinct from the
# typed-Event ``EVENT_SCHEMA_VERSION`` in substrate/schemas/events.py) because
# it is a distinct record shape written to a distinct JSONL. This version
# bumps when the record's FIELD SET changes (a field added/removed/retyped).
# It is initialized to 1 at SPR-02; the v28 EVENT_SCHEMA_VERSION bump in
# substrate/schemas/events.py is the action-vocabulary bump (the new
# ActionType member) and is tracked separately. The two are intentionally
# decoupled: the action vocabulary and the record shape version
# independently, because one acknowledges the event exists and the other
# pins the record's wire shape.
#
# ADDITIVE evolution rule (same discipline as EVENT_SCHEMA_VERSION): a bump
# may add a field or an enum value; it MUST NOT remove or retype an existing
# field. The reader (log.py) tolerates OLDER versions (fewer fields) and
# UNKNOWN fields (forward-compat) so a mixed-version log round-trips.
MEASUREMENT_RECORD_SCHEMA_VERSION: int = 1


# ---------------------------------------------------------------------------
# Outcome — the terminal status of the measured provider call
# ---------------------------------------------------------------------------


class Outcome(str, Enum):
    """The terminal status of one ``ResearchProvider.answer`` call.

    A ``str, Enum`` (matching the codebase's ``ActionType`` idiom) so the
    value serializes to JSON as its string and a reader can compare
    against the string without importing the enum (forward-compat: an
    unknown outcome string from a future version parses without
    crashing).

    Members
    -------
    success:
        The call returned a fully-populated ``ResearchResult`` — every
        field in the sub-question's output schema the provider could
        populate is populated and cited (per the SPR-01 conformance
        invariant). The provider did its job.
    partial:
        The call returned a ``ResearchResult`` but one or more output-
        schema fields are ``None`` / empty (the provider could not
        populate them). The result is still conformant (null/empty
        fields are exempt from the citation requirement), but the call
        did not fully answer. Distinct from ``success`` so the router
        can learn which provider/tier/task-class combos under-deliver.
    failed:
        The call raised or returned a result the caller rejected as
        unusable (e.g. the adapter's own validation rejected the raw
        payload, or the call raised an exception the resilience layer
        (SPR-05) chose not to retry). ``cost_usd`` / ``latency_ms`` may
        still be populated (a failed call still spent money and time).
    timeout:
        The call exceeded its deadline and was terminated before
        completing. Distinct from ``failed`` because a timeout is a
        scheduling/budget signal (the provider may have succeeded given
        more time), not a correctness signal — the router learns
        latency risk, not answer quality, from a timeout.
    budget_exceeded:
        The call was not made (or was aborted) because the per-call or
        per-investigation budget was exhausted. ``cost_usd`` is the
        spend that triggered the exhaustion (may be 0 if the gate fired
        pre-call from a prior call's spend); ``latency_ms`` is 0 if the
        call never ran. Distinct from ``failed``/``timeout`` because no
        provider was asked to do work it couldn't finish — the budget
        gate refused before/around the call.
    """

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"


# ---------------------------------------------------------------------------
# MeasurementRecord — the normalized per-call telemetry value
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasurementRecord:
    """One normalized measurement row per ``ResearchProvider.answer`` call.

    Fields
    ------
    schema_version:
        The measurement-record schema version at emit time
        (``MEASUREMENT_RECORD_SCHEMA_VERSION``). Pinned on the record so a
        reader can branch on shape (additive evolution: a reader tolerates
        older + unknown). Populated at emit-time by the writer; callers do
        not set it.
    investigation_id:
        The investigation this call belongs to. The storage partition key
        (one JSONL per investigation). Required; never null. Populated at
        emit-time from the call context.
    sub_question_id:
        Stable identifier of the sub-question this call answered. Links
        the measurement to the decomposition (which sub-question went to
        which provider). Required; never null. Populated at emit-time
        from the call context. (The sub-question TEXT is not carried —
        it lives in the decomposition event; the id is the join key.)
    task_class:
        The coarse task-class prior assigned to this sub-question (see
        ``task_class.TaskClass``). A ``str`` (the enum's value) so it
        serializes cleanly and a future unknown class parses without
        crashing. Required; never null. Populated at emit-time — either
        passed from the caller (the router's real classification in
        SPR-07) or derived via ``task_class.classify`` as a coarse prior.
    provider:
        Provider identity string (e.g. ``"exa"``, ``"parallel"``,
        ``"stub"``). A label, NOT a branch key — the normalized fields
        are identical for every provider (INV-4). Mirrors
        ``ResearchResult.provider``. Required; never null. Populated at
        emit-time from the measured ``ResearchResult``.
    tier:
        The provider tier used for this call (e.g. ``"deep"``,
        ``"basic"``). Mirrors ``ResearchResult.tier``. Required; never
        null. Populated at emit-time from the measured
        ``ResearchResult``.
    cost_usd:
        OBSERVED USD spent on this call, ``float >= 0.0``. This is the
        actual metered spend the adapter reports AFTER the call returned
        (``ResearchResult.cost``), NOT the SPR-01 ``CostModel``
        ``cost_usd_estimate`` the router used to select the call. The
        distinction is load-bearing: the estimate is a pre-call guess
        for budgeting; this is the post-call truth for reconciliation.
        For a ``budget_exceeded`` outcome where the call never ran, this
        is the spend that triggered the gate (may be 0.0). Required;
        never null. Populated at emit-time from the measured
        ``ResearchResult``.
    latency_ms:
        OBSERVED wall-clock for the provider call, in **milliseconds**,
        ``int >= 0``. Post-call measurement (``ResearchResult.latency``),
        NOT the ``CostModel.latency_ms_estimate``. Milliseconds (not
        seconds) to match ``ResearchResult.latency`` — sub-second
        latencies matter for routing and seconds lose precision. For a
        ``budget_exceeded`` outcome where the call never ran, this is 0.
        Required; never null. Populated at emit-time from the measured
        ``ResearchResult``.
    confidence:
        Normalized confidence in ``[0.0, 1.0]``. Mirrors
        ``ResearchResult.confidence`` — the normalized scale every
        provider maps onto (Exa categorical → numeric, Parallel numeric
        pass-through; see the SPR-01 confidence-normalization rule). The
        mapping is an UNVERIFIED ASSUMPTION carried verbatim: this field
        records what the provider reported on the normalized scale, not
        a re-calibration. Required; never null. Populated at emit-time
        from the measured ``ResearchResult``. For ``failed`` /
        ``timeout`` / ``budget_exceeded`` outcomes where no confidence
        was produced, the caller passes the provider's last-known or
        floor confidence (0.0 if truly unknown) — the outcome field is
        the authoritative signal there, not confidence.
    outcome:
        The terminal status of the call (``Outcome``). A ``str`` (the
        enum's value) so an unknown future outcome parses without
        crashing. Required; never null. Populated at emit-time from the
        call context (the caller observes whether the call succeeded /
        partial / failed / timed out / was budget-gated).
    correlation_id:
        The id linking this measurement event <-> the SPR-01
        ``ResearchResult`` it measured. Set to
        ``ResearchResult.raw_ref.handle`` — the opaque adapter-owned
        handle that resolves to the stored raw provider payload (e.g.
        ``"exa:raw:abc123"``). This is the join key: an audit reads the
        measurement record for the normalized telemetry and resolves
        ``correlation_id`` via the adapter to inspect the raw payload —
        the measurement itself never carries raw shape (INV-4). The
        handle is opaque by construction (no provider-specific keys a
        caller could branch on), so carrying it here does not leak
        provider structure. Required; never null. Populated at
        emit-time from the measured ``ResearchResult.raw_ref.handle``.
    emitted_at:
        ISO 8601 UTC timestamp (with ``Z`` suffix) marking when the
        measurement record was written. Distinct from the provider
        call's own latency (``latency_ms`` measures the call;
        ``emitted_at`` marks the log append). Used by the reader to
        ORDER records into a trajectory. Required; never null.
        Populated at emit-time by the writer.
    """

    schema_version: int
    investigation_id: str
    sub_question_id: str
    task_class: str
    provider: str
    tier: str
    cost_usd: float
    latency_ms: int
    confidence: float
    outcome: str
    correlation_id: str
    emitted_at: str

    # The fields above are the complete, documented wire shape. The dataclass
    # carries no defaults: every field is required at construction, and the
    # writer (log.py) validates presence + range BEFORE serializing — a
    # missing field is a construction error (caught by the writer's required-
    # field check), not a silent None on the wire.


# ---------------------------------------------------------------------------
# from_research_result — prove the record carries normalized fields only
# ---------------------------------------------------------------------------


def from_research_result(
    result: ResearchResult,
    *,
    investigation_id: str,
    sub_question_id: str,
    task_class: str,
    outcome: Outcome,
    emitted_at: datetime | None = None,
) -> MeasurementRecord:
    """Build a ``MeasurementRecord`` from a SPR-01 ``ResearchResult`` + the
    call context.

    This helper is the PROOF that the measurement record carries only
    NORMALIZED fields (INV-4): it reads exclusively from the normalized
    ``ResearchResult`` (``provider`` / ``tier`` / ``cost`` / ``latency`` /
    ``confidence`` / ``raw_ref.handle``) plus the call context
    (``investigation_id`` / ``sub_question_id`` / ``task_class`` /
    ``outcome``). It never touches ``result.fields``,
    ``result.field_citations``, or any provider-specific structure — those
    are the answer payload, not the measurement. The record is the
    receipt that a call happened and what it OBSERVED, not a copy of what
    it returned.

    The ``correlation_id`` is set to ``result.raw_ref.handle`` — the
    opaque adapter-owned handle. This is the join key to the raw payload:
    an audit resolves it via the adapter, never via this record.

    Args:
        result: the SPR-01 normalized ``ResearchResult`` the provider
            returned. Read-only dependency — this function does not
            modify it.
        investigation_id: the investigation the call belongs to.
        sub_question_id: the stable id of the sub-question answered.
        task_class: the coarse task-class prior (a ``TaskClass`` value
            string, or the router's real classification in SPR-07).
        outcome: the terminal status of the call (observed by the
            caller).
        emitted_at: optional explicit timestamp; defaults to ``now``
            (UTC). The writer stamps ``emitted_at`` itself if the caller
            doesn't, so this is mainly for tests needing deterministic
            ordering.

    Returns:
        A frozen ``MeasurementRecord`` carrying only normalized fields.

    Raises:
        TypeError: if ``result`` is not a ``ResearchResult`` (defensive —
            a non-normalized input would silently produce a malformed
            record, violating INV-4 at the source).
    """
    if not isinstance(result, ResearchResult):
        raise TypeError(
            f"from_research_result expects a ResearchResult, got "
            f"{type(result).__name__}. The measurement record is built "
            "from the NORMALIZED result (INV-4), not a raw payload."
        )
    if not isinstance(result.raw_ref, RawRef):
        # Defensive: a ResearchResult without a proper RawRef cannot be
        # correlated to its raw payload — the correlation_id would be
        # meaningless.
        raise TypeError(
            "from_research_result: result.raw_ref must be a RawRef "
            "(opaque handle to the raw payload). Got "
            f"{type(result.raw_ref).__name__}."
        )

    ts = emitted_at if emitted_at is not None else datetime.now(UTC)
    # ISO 8601 with Z suffix, matching the event_log writer's emitted_at
    # format (substrate/event_log/events.py:220) so the reader's ordering
    # sort is consistent across record kinds.
    emitted_at_str = ts.astimezone(UTC).isoformat().replace("+00:00", "Z")

    return MeasurementRecord(
        schema_version=MEASUREMENT_RECORD_SCHEMA_VERSION,
        investigation_id=investigation_id,
        sub_question_id=sub_question_id,
        task_class=task_class,
        provider=result.provider,
        tier=result.tier,
        cost_usd=float(result.cost),
        latency_ms=int(result.latency),
        confidence=float(result.confidence),
        outcome=outcome.value if isinstance(outcome, Outcome) else str(outcome),
        correlation_id=result.raw_ref.handle,
        emitted_at=emitted_at_str,
    )


__all__ = [
    "MEASUREMENT_RECORD_SCHEMA_VERSION",
    "MeasurementRecord",
    "Outcome",
    "from_research_result",
]
