"""Goal harness — shipped entrypoints and fixture paths (no mocks)."""

from __future__ import annotations

from scripts.goal_harness_deliverables import (
    HARNESS_ROOT,
    VERIFICATION_SCRIPT,
    assert_goal_deliverables_on_disk,
)
from substrate.research_artifact.reading_surface import consume_kb_artifact


def test_goal_harness_deliverables_present():
    assert_goal_deliverables_on_disk()
    assert (HARNESS_ROOT / "antiek_check.py").is_file()
    assert VERIFICATION_SCRIPT.is_file()


def test_shared_fixture_via_reading_entrypoint():
    from interfaces.reading.kb_artifact import kb_artifact_minimal_fixture_path

    path = kb_artifact_minimal_fixture_path()
    view = consume_kb_artifact(path)
    assert view.investigation_id == "inv-ui"
    assert view.findings[0][0] == "n-1"