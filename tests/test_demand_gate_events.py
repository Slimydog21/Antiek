"""SPR-08 M3: demand-gate event contract + the privacy gate.

The privacy audit, mechanical: every builder produces a counts/choices-only
event, and `assert_no_content` rejects any content-bearing or non-allowlisted
field — a measurement sprint must not smuggle in an ungated content event.
"""

from __future__ import annotations

import pytest

from services.demand_gate.events import (
    DEMAND_GATE_EVENT_TYPES,
    EXPORT_TAKEN,
    RE_IMPORT_DETECTED,
    SHARE_LINK_TAKEN,
    assert_no_content,
    build_export_offered,
    build_export_taken,
    build_re_import_detected,
    build_share_link_taken,
)


def test_builders_produce_only_counts_and_choices():
    events = [
        build_export_offered("u1", "synthesis_share", ("html", "antiek")),
        build_export_taken("u1", "synthesis_share", "antiek"),
        build_share_link_taken("u1", "synthesis_share"),
        build_re_import_detected("doc-1", "traveled_and_changed", "abc123"),
    ]
    for e in events:
        assert e["action_type"] in DEMAND_GATE_EVENT_TYPES
        assert_no_content(e)  # all clean


def test_export_taken_carries_the_format_choice_only():
    e = build_export_taken("u1", "notebook_share", "antiek_html")
    assert e["action_type"] == EXPORT_TAKEN and e["format"] == "antiek_html"
    assert "content" not in e and "text" not in e


def test_privacy_gate_rejects_a_content_field():
    with pytest.raises(ValueError):
        assert_no_content(
            {"action_type": EXPORT_TAKEN, "user_id": "u", "surface": "s", "text": "leaked passage"}
        )


def test_privacy_gate_rejects_a_non_allowlisted_field():
    with pytest.raises(ValueError):
        assert_no_content(
            {"action_type": SHARE_LINK_TAKEN, "user_id": "u", "surface": "s", "mystery": "x"}
        )


def test_re_import_event_matches_the_detectors_type():
    # The detector and the telemetry agree on the round-trip event type, so the
    # analysis sees one event stream.
    from services.demand_gate.roundtrip_detector import ROUNDTRIP_EVENT_TYPE

    assert RE_IMPORT_DETECTED == ROUNDTRIP_EVENT_TYPE
    e = build_re_import_detected("doc-1", "returned_unmodified", "hash", user_id="tester-2")
    assert e["user_id"] == "tester-2"
    assert_no_content(e)
