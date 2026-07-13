from __future__ import annotations

import pytest

from substrate.event_log import log_event, seal_investigation, trajectory


def test_trajectory_merges_events_appended_after_seal(tmp_path):
    pytest.importorskip("pyarrow")
    events_dir = str(tmp_path)
    investigation_id = "long-lived-reader-stream"

    first_id = log_event(
        investigation_id,
        "before.seal",
        events_dir=events_dir,
    )
    assert seal_investigation(investigation_id, events_dir=events_dir) is not None
    second_id = log_event(
        investigation_id,
        "after.seal",
        events_dir=events_dir,
    )

    rows = trajectory(investigation_id, events_dir=events_dir)
    assert [row["event_id"] for row in rows] == [first_id, second_id]

    assert seal_investigation(investigation_id, events_dir=events_dir) is not None
    resealed = trajectory(investigation_id, events_dir=events_dir)
    assert [row["event_id"] for row in resealed] == [first_id, second_id]
