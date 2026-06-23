"""Tests for tools/golden_traces/ (Sprint 4 day 4-5 scaffold).

Coverage:

1. ``stable_json_hash`` is deterministic and key-order-independent.
2. ``GoldenTrace`` + ``RoleCall`` round-trip through model_dump_json
   → model_validate_json.
3. ``GoldenTrace.signature`` depends on role_call ordering + hashes.
4. ``replay_trace_strict`` returns exact_signature_match=True when
   inputs are identical; reports per-call drift correctly when not.
5. The committed synthetic fixture parses cleanly + has a stable
   signature.
6. ``capture_from_researchmaxx_trajectory`` builds role_calls from
   matched ``role.call.start`` / ``role.call.end`` event pairs.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from tools.golden_traces import (  # noqa: E402
    GoldenTrace,
    MatchReport,
    RoleCall,
    load_trace,
    replay_trace_strict,
    stable_json_hash,
)
from tools.golden_traces.capture import (  # noqa: E402
    capture_from_researchmaxx_trajectory,
)

# ---------------------------------------------------------------------------
# 1. stable_json_hash
# ---------------------------------------------------------------------------


def test_stable_json_hash_is_deterministic():
    a = stable_json_hash({"x": 1, "y": [2, 3]})
    b = stable_json_hash({"x": 1, "y": [2, 3]})
    assert a == b


def test_stable_json_hash_is_key_order_independent():
    a = stable_json_hash({"x": 1, "y": 2})
    b = stable_json_hash({"y": 2, "x": 1})
    assert a == b


def test_stable_json_hash_distinguishes_different_inputs():
    a = stable_json_hash({"x": 1})
    b = stable_json_hash({"x": 2})
    assert a != b


def test_stable_json_hash_handles_datetime():
    h = stable_json_hash({"ts": datetime(2026, 5, 17)})
    # No raise; produces a hex string of expected length.
    assert len(h) == 64


# ---------------------------------------------------------------------------
# 2. GoldenTrace round-trip
# ---------------------------------------------------------------------------


def _make_trace(*, num_calls: int = 2) -> GoldenTrace:
    calls = [
        RoleCall(
            sequence_index=i,
            role=f"role-{i}",
            input_json={"i": i},
            output_json={"o": i * 2},
            input_hash=stable_json_hash({"i": i}),
            output_hash=stable_json_hash({"o": i * 2}),
        )
        for i in range(num_calls)
    ]
    return GoldenTrace(
        trace_id="gt-test",
        captured_at=datetime(2026, 5, 17, tzinfo=UTC),
        investigation_id="inv-test",
        target_question="Test question?",
        role_calls=calls,
    )


def test_golden_trace_round_trips_through_json():
    original = _make_trace(num_calls=3)
    raw = original.model_dump_json()
    rebuilt = GoldenTrace.model_validate_json(raw)
    assert rebuilt.trace_id == original.trace_id
    assert len(rebuilt.role_calls) == 3
    assert rebuilt.role_calls[1].input_hash == original.role_calls[1].input_hash


def test_golden_trace_signature_is_deterministic():
    t1 = _make_trace(num_calls=2)
    t2 = _make_trace(num_calls=2)
    assert t1.signature() == t2.signature()


def test_golden_trace_signature_depends_on_call_count():
    t_short = _make_trace(num_calls=1)
    t_long = _make_trace(num_calls=3)
    assert t_short.signature() != t_long.signature()


def test_golden_trace_signature_depends_on_per_call_hashes():
    """Changing one call's output_hash changes the trace signature.
    This is the property Sprint 5 extractions assert against."""
    t = _make_trace(num_calls=2)
    base_sig = t.signature()
    drifted = GoldenTrace(
        trace_id=t.trace_id,
        captured_at=t.captured_at,
        investigation_id=t.investigation_id,
        target_question=t.target_question,
        role_calls=[
            RoleCall(
                sequence_index=0, role="role-0",
                input_json={"i": 0}, output_json={"o": "drifted"},
                input_hash=t.role_calls[0].input_hash,
                output_hash=stable_json_hash({"o": "drifted"}),
            ),
            t.role_calls[1],
        ],
    )
    assert drifted.signature() != base_sig


# ---------------------------------------------------------------------------
# 3. replay_trace_strict
# ---------------------------------------------------------------------------


def test_replay_strict_exact_match():
    cap = _make_trace(num_calls=2)
    report = replay_trace_strict(cap, list(cap.role_calls))
    assert isinstance(report, MatchReport)
    assert report.exact_signature_match is True
    assert all(c.input_match and c.output_match for c in report.per_call)


def test_replay_strict_detects_output_drift():
    cap = _make_trace(num_calls=2)
    drifted = [
        cap.role_calls[0],
        RoleCall(
            sequence_index=1, role="role-1",
            input_json=cap.role_calls[1].input_json,
            output_json={"o": "different"},
            input_hash=cap.role_calls[1].input_hash,
            output_hash=stable_json_hash({"o": "different"}),
        ),
    ]
    report = replay_trace_strict(cap, drifted)
    assert report.exact_signature_match is False
    drifted_calls = [c for c in report.per_call if not c.output_match]
    assert len(drifted_calls) == 1
    assert drifted_calls[0].sequence_index == 1


def test_replay_strict_detects_missing_call():
    cap = _make_trace(num_calls=3)
    report = replay_trace_strict(cap, [cap.role_calls[0], cap.role_calls[1]])
    assert report.exact_signature_match is False
    missing = [c for c in report.per_call if "missing" in c.note]
    assert len(missing) == 1
    assert missing[0].sequence_index == 2


def test_replay_strict_detects_extra_call():
    cap = _make_trace(num_calls=1)
    extra_call = RoleCall(
        sequence_index=5, role="bonus",
        input_json={}, output_json={},
        input_hash="0" * 64, output_hash="0" * 64,
    )
    report = replay_trace_strict(cap, list(cap.role_calls) + [extra_call])
    assert report.exact_signature_match is False
    extras = [c for c in report.per_call if "extra" in c.note]
    assert len(extras) == 1


# ---------------------------------------------------------------------------
# 4. Synthetic fixture
# ---------------------------------------------------------------------------


def test_committed_synthetic_fixture_parses():
    path = Path(__file__).resolve().parent.parent / "tools" / "golden_traces" / "captured" / "synthetic-causal-xy.json"
    assert path.exists(), f"missing synthetic fixture at {path}"
    trace = load_trace(path)
    assert trace.trace_id == "gt-synthetic-001"
    assert len(trace.role_calls) >= 1
    assert trace.role_calls[0].role == "decomposer"


def test_synthetic_fixture_round_trip_signature_stable():
    """A captured trace must produce the same signature on re-parse —
    if not, the Sprint 5 extraction ratchet would false-alarm every
    time we re-serialize."""
    path = Path(__file__).resolve().parent.parent / "tools" / "golden_traces" / "captured" / "synthetic-causal-xy.json"
    trace = load_trace(path)
    sig1 = trace.signature()
    rebuilt = GoldenTrace.model_validate_json(trace.model_dump_json())
    assert rebuilt.signature() == sig1


# ---------------------------------------------------------------------------
# 5. capture_from_researchmaxx_trajectory
# ---------------------------------------------------------------------------


def test_capture_builds_role_calls_from_paired_events(tmp_path):
    """A trajectory JSONL with role.call.start + role.call.end pairs
    becomes a GoldenTrace with one RoleCall per pair."""
    jsonl = tmp_path / "events.jsonl"
    events = [
        {
            "event_id": "evt-start-1",
            "action_type": "role.call.start",
            "role": "decomposer",
            "payload": {"provider": "deepseek", "model": "v4-pro", "input": "Q1"},
            "parent_event_id": None,
        },
        {
            "event_id": "evt-end-1",
            "action_type": "role.call.end",
            "role": "decomposer",
            "payload": {"output": "sub-qs"},
            "parent_event_id": "evt-start-1",
        },
        {
            "event_id": "evt-start-2",
            "action_type": "role.call.start",
            "role": "synthesizer",
            "payload": {"provider": "anthropic", "model": "opus-4-7", "input": "synth"},
            "parent_event_id": None,
        },
        {
            "event_id": "evt-end-2",
            "action_type": "role.call.end",
            "role": "synthesizer",
            "payload": {"output": "thesis"},
            "parent_event_id": "evt-start-2",
        },
    ]
    with jsonl.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    trace = capture_from_researchmaxx_trajectory(
        trajectory_jsonl_path=jsonl,
        investigation_id="inv-cap-test",
        target_question="Test capture",
    )
    assert len(trace.role_calls) == 2
    assert {c.role for c in trace.role_calls} == {"decomposer", "synthesizer"}
    # input + output hashes computed from the captured payloads.
    for c in trace.role_calls:
        assert c.input_hash != "<missing>"
        assert c.output_hash != "<missing>"


def test_capture_marks_orphaned_starts_as_missing_output(tmp_path):
    """A role.call.start without a matching role.call.end gets
    output_hash='<missing>' so the replay can flag it."""
    jsonl = tmp_path / "events.jsonl"
    events = [
        {
            "event_id": "evt-start-only",
            "action_type": "role.call.start",
            "role": "decomposer",
            "payload": {"input": "x"},
        },
    ]
    with jsonl.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    trace = capture_from_researchmaxx_trajectory(
        trajectory_jsonl_path=jsonl,
        investigation_id="inv-orphan",
        target_question="x",
    )
    assert len(trace.role_calls) == 1
    assert trace.role_calls[0].output_hash == "<missing>"


def test_capture_ignores_malformed_jsonl_lines(tmp_path):
    """A real trajectory might have partial lines from crash recovery.
    The capture script must tolerate them rather than aborting."""
    jsonl = tmp_path / "events.jsonl"
    jsonl.write_text(
        '{"event_id": "evt-1", "action_type": "role.call.start", "role": "x"}\n'
        'not valid json at all\n'
        '\n'  # empty line
        '{"event_id": "evt-end", "action_type": "role.call.end", '
        '"parent_event_id": "evt-1", "payload": {}}\n',
        encoding="utf-8",
    )
    trace = capture_from_researchmaxx_trajectory(
        trajectory_jsonl_path=jsonl,
        investigation_id="inv-malformed",
        target_question="q",
    )
    assert len(trace.role_calls) == 1  # the one valid pair
