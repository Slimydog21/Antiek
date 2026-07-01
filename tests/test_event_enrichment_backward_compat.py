"""Backward-compat proof for the Majors-Observability SPR-01 event
enrichment (substrate/schemas/events.py, schema v28).

THE LOAD-BEARING GATE (rigor #3): SPR-01 widened three EXISTING
orchestration payloads with OPTIONAL high-cardinality fields —
``chunk_count`` / ``latency_ms`` on EvidenceRetrieveDeliveredPayload,
``latency_ms`` / ``provider`` / ``model`` on SynthesizeDeliveredPayload,
``latency_ms`` on PhaseExitPayload. The whole point of "additive, no
schema-breaking change" is that a schema-v<=27 trajectory row — written
BEFORE these fields existed, and therefore MISSING them entirely — still
validates and round-trips unchanged.

So the fixtures here are GENUINELY OLD-SHAPE rows (the new keys are
ABSENT, not present-and-nulled). If a future edit accidentally makes any
new field required, every ``_OLD_*`` fixture below fails to validate and
this file goes red — that is the alarm.

Enumerated edge cases (per the sprint's rigor bar):
  1. field ABSENT entirely (the real historical shape)          → validates, default applies
  2. field present-but-NULL (a defensive emitter that wrote None) → validates
  3. a numeric field passed as a STRING                          → DEFENDED (lax coercion, see below)
  4. a numeric field NEGATIVE / non-numeric                      → REJECTED (Field(ge=0) / type)

On case 3 (numeric-as-string): the payload base config is
``ConfigDict(extra="forbid", use_enum_values=True)`` — it does NOT set
``strict=True``, so Pydantic v2 runs in lax mode and coerces ``"3"`` →
``3`` exactly as DispatchCallPayload's own int fields do. We DEFEND this:
a legacy JSONL row that stringified a count still parses to the correct
int rather than throwing. A non-numeric string ("abc") is still rejected,
so the field stays genuinely typed — coercion widens the accepted input,
it does not weaken the type.
"""

from __future__ import annotations

import os
import sys

import pytest
from pydantic import TypeAdapter, ValidationError

# Make the project root importable without a separate conftest.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from substrate.schemas import (  # noqa: E402
    EVENT_SCHEMA_VERSION,
    WRESTLING_ACTION_TYPES,
    EvidenceRetrieveDeliveredPayload,
    Event,
    PhaseExitPayload,
    SynthesizeDeliveredPayload,
    TypedPayload,
)

_PAYLOAD_ADAPTER = TypeAdapter(TypedPayload)


# ---------------------------------------------------------------------------
# Genuinely OLD-SHAPE payload dicts — exactly the keys a schema-v27
# trajectory carried, with the SPR-01 fields ABSENT (not nulled).
# ---------------------------------------------------------------------------

_OLD_PHASE_EXIT: dict = {
    "action_type": "phase.exit",
    "exited_at": "2026-01-01T00:00:00.000000Z",
    "outputs_hash": None,
    # NOTE: no ``latency_ms`` key — this is the pre-SPR-01 shape.
}

_OLD_EVIDENCE_DELIVERED: dict = {
    "action_type": "evidence.retrieve.delivered",
    "sub_question": "What is the fab yield of the 2nm node?",
    "answer": "Reported early-run yields cluster around 60-70%.",
    "supporting_claims": [],
    "evidentiary_gaps": [],
    "insufficient_evidence": False,
    # NOTE: no ``chunk_count`` / ``latency_ms`` keys — pre-SPR-01 shape.
}

_OLD_SYNTHESIZE_DELIVERED: dict = {
    "action_type": "synthesize.delivered",
    "thesis_summary": "The node is investable under a staged-capex thesis.",
    "implicit_recommendation": "conditional",
    "thesis_components": [],
    "falsification_conditions": [],
    "execution_risks": [],
    "constraint_compliance": {
        "hard_constraints_satisfied": True,
        "soft_constraints_violated": [],
        "violations_justified": [],
    },
    "reasoning_paths_used": [],
    "conviction_level": None,
    "constraint_loop_status": "single_pass",
    "constraint_loop_iterations": 1,
    # NOTE: no ``latency_ms`` / ``provider`` / ``model`` keys — pre-SPR-01.
}


def _envelope(payload: dict, *, phase: int | None) -> dict:
    """Wrap an old-shape payload in the historical Event envelope shape a
    JSONL trajectory row carried at schema_version=27 (the new payload
    keys still ABSENT; the envelope itself is unchanged by SPR-01)."""
    action = payload["action_type"]
    assert action not in WRESTLING_ACTION_TYPES, (
        f"{action} is a wrestling action type — the envelope fixture would "
        "need document_id; none of the SPR-01 payloads are wrestling events."
    )
    return {
        "event_id": "evt-oldshape-0001",
        "investigation_id": "inv-oldshape-0001",
        "synthesis_id": None,
        "phase": phase,
        "role": "phase_log",
        "action_type": action,
        "payload": payload,
        "parent_event_id": None,
        "policy_id": "orchestrator-deterministic",
        "param_version": "0.1.0",
        "schema_version": 27,  # a genuinely pre-SPR-01 row
        "emitted_at": "2026-01-01T00:00:00Z",
        "document_id": None,
    }


# ---------------------------------------------------------------------------
# Sanity: the version bumped, and the fields are genuinely absent.
# ---------------------------------------------------------------------------


def test_schema_version_bumped_to_at_least_28():
    """SPR-01 widened the schema; the floor moved to 28. A floor (not ==)
    so a later additive bump doesn't force touching this file."""
    assert EVENT_SCHEMA_VERSION >= 28


def test_fixtures_are_genuinely_old_shape():
    """Guard the guard: these fixtures must be MISSING the new keys, not
    carrying them as null. If someone 'helpfully' adds the keys, the
    backward-compat proof degrades into an enriched-event happy path."""
    assert "latency_ms" not in _OLD_PHASE_EXIT
    assert "chunk_count" not in _OLD_EVIDENCE_DELIVERED
    assert "latency_ms" not in _OLD_EVIDENCE_DELIVERED
    for k in ("latency_ms", "provider", "model"):
        assert k not in _OLD_SYNTHESIZE_DELIVERED


# ---------------------------------------------------------------------------
# Case 1 — field ABSENT: old-shape payloads validate + defaults apply.
# ---------------------------------------------------------------------------


def test_old_phase_exit_validates_and_defaults_latency_none():
    p = PhaseExitPayload.model_validate(_OLD_PHASE_EXIT)
    assert p.exited_at == "2026-01-01T00:00:00.000000Z"
    assert p.latency_ms is None  # absent → default None, never fabricated
    # Discriminated-union routing still lands the right variant.
    routed = _PAYLOAD_ADAPTER.validate_python(_OLD_PHASE_EXIT)
    assert isinstance(routed, PhaseExitPayload)


def test_old_evidence_delivered_validates_and_defaults():
    p = EvidenceRetrieveDeliveredPayload.model_validate(_OLD_EVIDENCE_DELIVERED)
    assert p.sub_question.startswith("What is the fab yield")
    # Absent count → None (UNKNOWN), NOT 0 — an old row never carried a count,
    # so labeling it "searched-and-empty" would be a lie a bisector could trust.
    assert p.chunk_count is None
    assert p.latency_ms is None
    routed = _PAYLOAD_ADAPTER.validate_python(_OLD_EVIDENCE_DELIVERED)
    assert isinstance(routed, EvidenceRetrieveDeliveredPayload)


def test_old_synthesize_delivered_validates_and_defaults():
    p = SynthesizeDeliveredPayload.model_validate(_OLD_SYNTHESIZE_DELIVERED)
    assert p.implicit_recommendation == "conditional"
    assert p.latency_ms is None
    assert p.provider is None      # recovered via dispatch.call correlation (SPR-04), not faked
    assert p.model is None
    routed = _PAYLOAD_ADAPTER.validate_python(_OLD_SYNTHESIZE_DELIVERED)
    assert isinstance(routed, SynthesizeDeliveredPayload)


# ---------------------------------------------------------------------------
# Case 1 (continued) — the FULL Event envelope round-trips an old row.
# This is the shape the trajectory store actually persists and re-reads.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,phase",
    [
        (_OLD_PHASE_EXIT, 6),
        (_OLD_EVIDENCE_DELIVERED, 2),
        (_OLD_SYNTHESIZE_DELIVERED, 6),
    ],
    ids=["phase.exit", "evidence.retrieve.delivered", "synthesize.delivered"],
)
def test_old_envelope_row_round_trips(payload: dict, phase: int):
    """A schema-v27 JSONL row (new fields absent) validates through the
    Event envelope AND survives a dump→reload cycle unchanged — the exact
    path the audit/query tools use when they re-read historical logs."""
    row = _envelope(payload, phase=phase)
    ev = Event.model_validate(row)
    assert ev.schema_version == 27           # the stamp is preserved, not rewritten
    assert ev.phase == phase                 # phase stays on the ENVELOPE (not the payload)
    # Round-trip: serialize back to a row and re-validate to the same variant.
    reloaded = Event.model_validate(ev.model_dump(mode="json"))
    assert type(reloaded.payload) is type(ev.payload)
    assert reloaded.action_type == ev.action_type


# ---------------------------------------------------------------------------
# Case 2 — field present-but-NULL (a defensive emitter wrote None).
# ---------------------------------------------------------------------------


def test_present_but_null_fields_validate():
    ev = {**_OLD_EVIDENCE_DELIVERED, "chunk_count": 0, "latency_ms": None}
    p = EvidenceRetrieveDeliveredPayload.model_validate(ev)
    assert p.chunk_count == 0 and p.latency_ms is None

    syn = {
        **_OLD_SYNTHESIZE_DELIVERED,
        "latency_ms": None,
        "provider": None,
        "model": None,
    }
    ps = SynthesizeDeliveredPayload.model_validate(syn)
    assert ps.latency_ms is None and ps.provider is None and ps.model is None

    px = PhaseExitPayload.model_validate({**_OLD_PHASE_EXIT, "latency_ms": None})
    assert px.latency_ms is None


# ---------------------------------------------------------------------------
# Case 3 — numeric field passed as a STRING → DEFENDED via lax coercion.
# (Documented in the module docstring: mirrors DispatchCallPayload int
# fields; widens accepted input, does not weaken the type.)
# ---------------------------------------------------------------------------


def test_numeric_as_string_is_coerced_not_rejected():
    p = EvidenceRetrieveDeliveredPayload.model_validate(
        {**_OLD_EVIDENCE_DELIVERED, "chunk_count": "3", "latency_ms": "150"}
    )
    assert p.chunk_count == 3 and isinstance(p.chunk_count, int)
    assert p.latency_ms == 150 and isinstance(p.latency_ms, int)

    px = PhaseExitPayload.model_validate({**_OLD_PHASE_EXIT, "latency_ms": "42"})
    assert px.latency_ms == 42 and isinstance(px.latency_ms, int)


# ---------------------------------------------------------------------------
# Case 4 — the field stays genuinely typed: bad values are REJECTED.
# ---------------------------------------------------------------------------


def test_non_numeric_string_rejected():
    with pytest.raises(ValidationError):
        EvidenceRetrieveDeliveredPayload.model_validate(
            {**_OLD_EVIDENCE_DELIVERED, "chunk_count": "not-a-number"}
        )


def test_negative_counts_and_latencies_rejected():
    # Field(ge=0) mirrors DispatchCallPayload.latency_ms exactly.
    with pytest.raises(ValidationError):
        EvidenceRetrieveDeliveredPayload.model_validate(
            {**_OLD_EVIDENCE_DELIVERED, "chunk_count": -1}
        )
    with pytest.raises(ValidationError):
        EvidenceRetrieveDeliveredPayload.model_validate(
            {**_OLD_EVIDENCE_DELIVERED, "latency_ms": -1}
        )
    with pytest.raises(ValidationError):
        PhaseExitPayload.model_validate({**_OLD_PHASE_EXIT, "latency_ms": -1})
    with pytest.raises(ValidationError):
        SynthesizeDeliveredPayload.model_validate(
            {**_OLD_SYNTHESIZE_DELIVERED, "latency_ms": -1}
        )


def test_extra_forbid_still_rejects_typos():
    """The base config is ``extra='forbid'`` — a mistyped enrichment key
    must fail loudly rather than land as a silent extra column. This
    proves the additive widening did NOT relax the strictness that keeps
    codegen honest."""
    with pytest.raises(ValidationError):
        PhaseExitPayload.model_validate({**_OLD_PHASE_EXIT, "latencyMs": 5})


# ---------------------------------------------------------------------------
# Enriched (NEW-shape) events also validate + round-trip — the forward
# half of the additive contract.
# ---------------------------------------------------------------------------


def test_enriched_events_round_trip():
    px = PhaseExitPayload(exited_at="2026-07-01T00:00:00Z", latency_ms=1234)
    assert PhaseExitPayload.model_validate(px.model_dump()).latency_ms == 1234

    ev = EvidenceRetrieveDeliveredPayload(
        sub_question="q?", answer="a", chunk_count=5, latency_ms=800,
    )
    r = EvidenceRetrieveDeliveredPayload.model_validate(ev.model_dump())
    assert r.chunk_count == 5 and r.latency_ms == 800

    # chunk_count=0 is a distinct, valid state (searched-and-empty).
    z = EvidenceRetrieveDeliveredPayload(sub_question="q?", answer="a", chunk_count=0)
    assert EvidenceRetrieveDeliveredPayload.model_validate(z.model_dump()).chunk_count == 0

    syn = SynthesizeDeliveredPayload(
        thesis_summary="t",
        implicit_recommendation="proceed",
        constraint_compliance={
            "hard_constraints_satisfied": True,
            "soft_constraints_violated": [],
            "violations_justified": [],
        },
        latency_ms=9000,
        provider="deepseek",
        model="deepseek-v4-pro",
    )
    rs = SynthesizeDeliveredPayload.model_validate(syn.model_dump())
    assert rs.latency_ms == 9000
    assert rs.provider == "deepseek" and rs.model == "deepseek-v4-pro"


# ---------------------------------------------------------------------------
# chunk_count reconstruction at the evidence bridge — the three honest states
# + the body-collision case (round-2 sharpen FIX 2). Lazy import so the
# schema-only tests above stay decoupled from the bridge's deps.
# ---------------------------------------------------------------------------


def _render_two_chunk_block(*, body_has_header: bool = False) -> str:
    """Reproduce the orchestrator's render shape: ``### chunk_id: {cid}`` +
    body per chunk, joined by ``\\n---\\n``."""
    body_a = "Yield ramps take quarters." + (
        "\n### chunk_id: not-a-real-chunk see spec header in prose" if body_has_header else ""
    )
    seg_a = f"### chunk_id: c1\nSource tier: 2 | Document: A\n\n{body_a}\n"
    seg_b = "### chunk_id: c2\nSource tier: 3 | Document: B\n\nSecond chunk.\n"
    return "\n---\n".join([seg_a, seg_b])


def test_chunk_count_from_block_three_states_and_body_collision():
    from interfaces.research.api.evidence_retriever import _chunk_count_from_block

    # None (unknown): empty / absent / corpus-search UNAVAILABLE.
    assert _chunk_count_from_block(None) is None
    assert _chunk_count_from_block("") is None
    assert _chunk_count_from_block(
        "(corpus search unavailable: RuntimeError: boom)"
    ) is None
    # 0: searched, genuinely empty (distinct from unknown).
    assert _chunk_count_from_block(
        "(corpus search returned no matches above the similarity floor)"
    ) == 0
    # N: two real chunks → 2.
    assert _chunk_count_from_block(_render_two_chunk_block()) == 2
    # Body-collision: a chunk BODY line that itself starts with the header must
    # NOT inflate the count (the critic reproduced 2→3 with the old regex).
    assert _chunk_count_from_block(_render_two_chunk_block(body_has_header=True)) == 2
