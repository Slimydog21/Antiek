"""SPR-AHT-06 — outline blocks."""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest

from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight, promote_question
from substrate.research_artifact.blocks import list_outline_blocks


@pytest.fixture
def blocks_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ra-blocks-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "events": events}


def test_blocks_match_distill_count(blocks_env):
    promote_insight(text="I1", investigation_id="inv-b", source_document_id="d")
    promote_question(text="Q1", investigation_id="inv-b", source_document_id="d")
    blocks = list_outline_blocks(
        "inv-b", db_path=blocks_env["db"], events_dir=blocks_env["events"]
    )
    assert len(blocks) == 2
    kinds = {b.kind for b in blocks}
    assert kinds == {"insight", "question"}