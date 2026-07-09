"""SPR-AHT-02 — exporter + artifact path."""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest

from substrate.event_log import trajectory
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight
from substrate.research_artifact import export_research_artifact
from substrate.schemas.events import ActionType


class _StubEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


@pytest.fixture
def art_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ra-export-")
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


def test_export_writes_html_and_insight(art_env):
    promote_insight(
        text="Finding one.",
        investigation_id="inv-ra",
        confidence="moderate",
        source_document_id="doc-1",
    )
    res = export_research_artifact(
        "inv-ra", db_path=art_env["db"], events_dir=art_env["events"]
    )
    assert res.path.is_file()
    assert res.twin_notes_path.is_file()
    text = res.path.read_text(encoding="utf-8")
    twin = res.twin_notes_path.read_text(encoding="utf-8")
    assert "Finding one." in text
    assert "Finding one." in twin
    assert "ResearchArtifact twin notes" in twin
    assert 'id="antiek-artifact-v1"' in twin
    assert res.size_bytes > 0
    rows = trajectory("inv-ra", events_dir=art_env["events"])
    kinds = [r.get("action_type") for r in rows]
    assert ActionType.ARTIFACT_GENERATED.value in kinds


def test_export_writes_sibling_twin_note_document(art_env):
    promote_insight(
        text="Twin note finding.",
        investigation_id="inv-twin",
        confidence="high",
        source_document_id="doc-2",
    )
    res = export_research_artifact(
        "inv-twin", db_path=art_env["db"], events_dir=art_env["events"]
    )

    assert res.twin_notes_path.name == "inv-twin.notes.html"
    twin = res.twin_notes_path.read_text(encoding="utf-8")
    assert "Open research artifact" in twin
    assert "Finding prompts" in twin
    assert "Open question prompts" in twin
    assert "Agent notes" in twin
