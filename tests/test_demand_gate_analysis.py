"""SPR-08 M5: analysis reproducibility — both verdict directions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.demand_gate.analysis import (
    AGENT_UNPROMPTED,
    CRITERIA_COMMIT,
    EXPORT_OFFERED,
    RETIRE,
    ROUNDTRIP,
    SUSTAIN,
    THIRD_PARTY_READER,
    compute_verdict,
)

OP = "operator-1"
TESTERS = frozenset(f"tester-{i}" for i in range(2, 7))
START = datetime(2026, 10, 1, tzinfo=UTC)
AT = (START + timedelta(days=2)).isoformat()
# Coverage: the dual offer reached a pinned tester in the window.
OFFERED = {"action_type": EXPORT_OFFERED, "user_id": "tester-2", "emitted_at": AT}


def _verdict(events):
    return compute_verdict(
        [OFFERED, *events],
        operator_user_id=OP,
        tester_ids=TESTERS,
        window_start=START,
        window_end=START + timedelta(days=14),
    )


def test_sustain_on_non_operator_roundtrip():
    events = [{"action_type": ROUNDTRIP, "user_id": "tester-2", "exported_by": ["tester-3"],
               "classification": "traveled_and_changed", "emitted_at": AT}]
    v = _verdict(events)
    assert v.verdict == SUSTAIN and v.counts["organic_roundtrip"] == 1


def test_operator_roundtrip_does_not_sustain_the_n1_confound():
    events = [
        {"action_type": ROUNDTRIP, "user_id": OP, "exported_by": ["tester-3"],
         "classification": "traveled_and_changed", "emitted_at": AT},
        {"action_type": "demand_gate.export_taken", "user_id": "tester-2", "format": "antiek", "emitted_at": AT},
        {"action_type": "demand_gate.export_taken", "user_id": "tester-3", "format": "antiek", "emitted_at": AT},
    ]
    assert _verdict(events).verdict == RETIRE


def test_sustain_on_third_party_reader():
    ev = {"action_type": THIRD_PARTY_READER, "tool": "someones-parser", "user_id": "someone",
          "evidence_ref": "https://example.org/parser", "emitted_at": AT}
    assert _verdict([ev]).verdict == SUSTAIN
    # A bare, unattributed observation is not admissible (pre-wave-4 it sustained).
    assert _verdict([{"action_type": THIRD_PARTY_READER, "tool": "someones-parser"}]).verdict == RETIRE


def test_sustain_on_agent_unprompted():
    ev = {"action_type": AGENT_UNPROMPTED, "agent": "x", "user_id": "someone",
          "evidence_ref": "transcript-42", "emitted_at": AT}
    assert _verdict([ev]).verdict == SUSTAIN
    assert _verdict([{"action_type": AGENT_UNPROMPTED, "agent": "x"}]).verdict == RETIRE


def test_retire_on_only_downloads_and_opens():
    events = [
        {"action_type": "demand_gate.export_taken", "user_id": "t", "format": "antiek", "emitted_at": AT},
        {"action_type": "demand_gate.share_link_taken", "user_id": "t", "emitted_at": AT},
    ] * 50
    assert _verdict(events).verdict == RETIRE


def test_reproducible_same_events_same_verdict():
    events = [{"action_type": ROUNDTRIP, "user_id": "tester-2", "exported_by": ["tester-2"], "emitted_at": AT}]
    assert _verdict(events) == _verdict(events)


def test_criteria_commit_is_pinned():
    v = _verdict([])
    assert v.criteria_commit == CRITERIA_COMMIT and len(CRITERIA_COMMIT) == 40
