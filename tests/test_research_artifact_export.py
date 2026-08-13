"""SPR-AHT-02 — exporter + artifact path."""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from services.html_projection.island import extract_island
from substrate.event_log import trajectory
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight
from substrate.research_artifact import export_research_artifact, parse_body_from_html
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
    res = export_research_artifact("inv-ra", db_path=art_env["db"], events_dir=art_env["events"])
    assert res.path.is_file()
    assert res.artifact_id == "inv-ra"
    text = res.path.read_text(encoding="utf-8")
    assert "Finding one." in text
    assert res.size_bytes > 0
    rows = trajectory("inv-ra", events_dir=art_env["events"])
    kinds = [r.get("action_type") for r in rows]
    assert ActionType.ARTIFACT_GENERATED.value in kinds
    generated = next(r for r in rows if r.get("action_type") == ActionType.ARTIFACT_GENERATED.value)
    assert generated["payload"]["artifact_id"] == res.artifact_id
    island = extract_island(text)
    assert island["research_artifact"] == parse_body_from_html(text).model_dump(mode="json")
    assert island["research_artifact"]["investigation_id"] == "inv-ra"
    assert island["research_artifact"]["insights"][0]["text"] == "Finding one."



def test_export_is_deterministic_when_source_provenance_is_unchanged(art_env):
    first = export_research_artifact(
        "inv-repeat", db_path=art_env["db"], events_dir=art_env["events"], emit_event=False
    )
    first_text = first.path.read_text(encoding="utf-8")
    second = export_research_artifact(
        "inv-repeat", db_path=art_env["db"], events_dir=art_env["events"], emit_event=False
    )
    second_text = second.path.read_text(encoding="utf-8")
    assert second_text == first_text
    assert second.content_hash == first.content_hash
    assert extract_island(second_text) == extract_island(first_text)


def test_same_owner_concurrent_exports_emit_only_immutable_exact_paths(
    art_env, monkeypatch
):
    import substrate.research_artifact.export as export_module

    barrier = threading.Barrier(2)
    original_build = export_module.build_body

    def synchronized_build(*args, **kwargs):
        body = original_build(*args, **kwargs)
        barrier.wait(timeout=5)
        return body

    monkeypatch.setattr(export_module, "build_body", synchronized_build)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: export_research_artifact(
                    "inv-concurrent",
                    db_path=art_env["db"],
                    events_dir=art_env["events"],
                ),
                range(2),
            )
        )
    assert all(result.path.is_file() for result in results)
    rows = [
        row
        for row in trajectory("inv-concurrent", events_dir=art_env["events"])
        if row.get("action_type") == ActionType.ARTIFACT_GENERATED.value
    ]
    assert len(rows) == 2
    for row in rows:
        event_path = Path(row["payload"]["artifact_path"])
        assert event_path.is_file()
        assert event_path.stat().st_size == row["payload"]["size_bytes"]
