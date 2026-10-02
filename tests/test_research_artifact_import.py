"""SPR-AHT-03 — import append-only agent notes from artifact HTML."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from substrate.event_log import trajectory
from substrate.graph import ensure_initialized
from substrate.research_artifact import export_research_artifact, import_agent_notes
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody
from substrate.schemas.events import ActionType


@pytest.fixture
def imp_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ra-import-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    arts = os.path.join(tmpdir, "artifacts")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", arts)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "events": events, "arts": arts}


def test_import_emits_events_for_new_notes(imp_env):
    body = ResearchArtifactBody(
        investigation_id="inv-imp",
        problem_question="Test Q",
        agent_notes=["Cross-window note A", "Note B"],
    )
    path = os.path.join(imp_env["arts"], "inv-imp.html")
    os.makedirs(imp_env["arts"], exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html(body))

    r1 = import_agent_notes(Path(path), events_dir=imp_env["events"])
    assert r1.notes_imported == 2
    r2 = import_agent_notes(Path(path), events_dir=imp_env["events"])
    assert r2.notes_imported == 0
    assert r2.notes_skipped_duplicate == 2

    rows = trajectory("inv-imp", events_dir=imp_env["events"])
    kinds = [x.get("action_type") for x in rows]
    assert kinds.count(ActionType.ARTIFACT_GENERATED.value) == 2


def test_export_carries_forward_agent_notes(imp_env):
    body = ResearchArtifactBody(
        investigation_id="inv-carry",
        problem_question="Carry",
        agent_notes=["Persist me"],
    )
    path = os.path.join(imp_env["arts"], "inv-carry.html")
    os.makedirs(imp_env["arts"], exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html(body))

    res = export_research_artifact(
        "inv-carry", db_path=imp_env["db"], events_dir=imp_env["events"]
    )
    text = res.path.read_text(encoding="utf-8")
    twin = res.twin_notes_path.read_text(encoding="utf-8")
    assert "Persist me" in text
    assert "Persist me" in twin
    assert '"agent_notes"' in text
    assert '"agent_notes"' in twin
