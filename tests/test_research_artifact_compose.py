"""SPR-AHT-05 — compose index."""

from __future__ import annotations

import os
import tempfile

import pytest

from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight
from substrate.research_artifact.compose import (
    StaleComposePreview,
    compose_artifacts,
    create_compose_draft,
    delete_compose_draft,
    preview_artifacts,
)


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
    assert len(res.members) == 2


def test_preview_then_create_is_immutable_idempotent_and_deletable(compose_env):
    for iid, txt in [("inv-a", "Alpha"), ("inv-b", "Beta")]:
        promote_insight(text=txt, investigation_id=iid, source_document_id="doc-1")
    preview = preview_artifacts(["inv-a", "inv-b"], db_path=compose_env["db"], events_dir=compose_env["events"])
    assert preview.selection_fingerprint
    assert not preview.path.exists()
    first = create_compose_draft(["inv-a", "inv-b"], expected_fingerprint=preview.selection_fingerprint, db_path=compose_env["db"], events_dir=compose_env["events"])
    second = create_compose_draft(["inv-a", "inv-b"], expected_fingerprint=preview.selection_fingerprint, db_path=compose_env["db"], events_dir=compose_env["events"])
    assert first.path.is_file()
    assert second.compose_id == first.compose_id
    assert second.reused is True
    page = first.path.read_text(encoding="utf-8")
    assert "file://" not in page
    assert str(first.path.parent) not in page
    delete_compose_draft(first.compose_id or "")
    assert not first.path.exists()


def test_create_rejects_stale_preview(compose_env):
    for iid, txt in [("inv-a", "Alpha"), ("inv-b", "Beta")]:
        promote_insight(text=txt, investigation_id=iid, source_document_id="doc-1")
    preview = preview_artifacts(["inv-a", "inv-b"], db_path=compose_env["db"], events_dir=compose_env["events"])
    promote_insight(text="Changed", investigation_id="inv-a", source_document_id="doc-2")
    with pytest.raises(StaleComposePreview):
        create_compose_draft(["inv-a", "inv-b"], expected_fingerprint=preview.selection_fingerprint or "", db_path=compose_env["db"], events_dir=compose_env["events"])


@pytest.mark.parametrize("ids", [[], ["inv-a"], ["inv-a", "inv-a"]])
def test_preview_rejects_invalid_selection(compose_env, ids):
    with pytest.raises(ValueError):
        preview_artifacts(ids, db_path=compose_env["db"], events_dir=compose_env["events"])
