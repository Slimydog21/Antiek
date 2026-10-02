"""SPR-AHT-05 — compose index."""

from __future__ import annotations

import os
import tempfile

import pytest

from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight
from substrate.research_artifact.compose import compose_artifacts


@pytest.fixture
def compose_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ra-compose-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    arts = os.path.join(tmpdir, "artifacts")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", arts)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "events": events}


def test_compose_two_investigations(compose_env):
    for iid, txt in [("inv-a", "Alpha"), ("inv-b", "Beta")]:
        promote_insight(
            text=txt, investigation_id=iid, source_document_id="doc-1"
        )
    res = compose_artifacts(
        ["inv-a", "inv-b"],
        db_path=compose_env["db"],
        events_dir=compose_env["events"],
    )
    assert res.path.is_file()
    index = res.path.read_text(encoding="utf-8")
    assert "inv-a" in index and "inv-b" in index
    assert "notes twin" in index
    assert len(res.members) == 2


def test_compose_writes_no_mutation_draft_merge(compose_env):
    for iid, txt in [("inv-c", "Gamma"), ("inv-d", "Delta")]:
        promote_insight(
            text=txt, investigation_id=iid, source_document_id="doc-1"
        )
    res = compose_artifacts(
        ["inv-c", "inv-d"],
        db_path=compose_env["db"],
        events_dir=compose_env["events"],
        write_draft_merge=True,
    )

    assert res.draft_merge_path is not None
    assert res.draft_merge_path.is_file()
    draft = res.draft_merge_path.read_text(encoding="utf-8")
    assert "Draft merge review" in draft
    assert "no graph mutation" in draft
    assert "Gamma" in draft and "Delta" in draft
    assert "notes twin" in draft
    assert all(member.twin_notes_path.is_file() for member in res.members)
