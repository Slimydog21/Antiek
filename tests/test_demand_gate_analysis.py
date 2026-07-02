"""SPR-08 M5: analysis reproducibility — both verdict directions."""

from __future__ import annotations

from services.demand_gate.analysis import (
    AGENT_UNPROMPTED,
    CRITERIA_COMMIT,
    RETIRE,
    ROUNDTRIP,
    SUSTAIN,
    THIRD_PARTY_READER,
    compute_verdict,
)

OP = "operator-1"


def test_sustain_on_non_operator_roundtrip():
    events = [{"action_type": ROUNDTRIP, "user_id": "tester-2", "classification": "traveled_and_changed"}]
    v = compute_verdict(events, operator_user_id=OP)
    assert v.verdict == SUSTAIN and v.counts["organic_roundtrip"] == 1


def test_operator_roundtrip_does_not_sustain_the_n1_confound():
    events = [
        {"action_type": ROUNDTRIP, "user_id": OP, "classification": "traveled_and_changed"},
        {"action_type": "demand_gate.export_taken", "user_id": "tester-2", "format": "antiek"},
        {"action_type": "demand_gate.export_taken", "user_id": "tester-3", "format": "antiek"},
    ]
    assert compute_verdict(events, operator_user_id=OP).verdict == RETIRE


def test_sustain_on_third_party_reader():
    assert (
        compute_verdict(
            [{"action_type": THIRD_PARTY_READER, "tool": "someones-parser"}],
            operator_user_id=OP,
        ).verdict
        == SUSTAIN
    )


def test_sustain_on_agent_unprompted():
    assert (
        compute_verdict(
            [{"action_type": AGENT_UNPROMPTED, "agent": "x"}], operator_user_id=OP
        ).verdict
        == SUSTAIN
    )


def test_retire_on_only_downloads_and_opens():
    events = [
        {"action_type": "demand_gate.export_taken", "user_id": "t", "format": "antiek"},
        {"action_type": "demand_gate.share_link_taken", "user_id": "t"},
    ] * 50
    assert compute_verdict(events, operator_user_id=OP).verdict == RETIRE


def test_reproducible_same_events_same_verdict():
    events = [{"action_type": ROUNDTRIP, "user_id": "tester-2"}]
    assert compute_verdict(events, operator_user_id=OP) == compute_verdict(
        events, operator_user_id=OP
    )


def test_criteria_commit_is_pinned():
    v = compute_verdict([], operator_user_id=OP)
    assert v.criteria_commit == CRITERIA_COMMIT and len(CRITERIA_COMMIT) == 40
