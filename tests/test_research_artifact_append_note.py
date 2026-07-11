"""Persistence and trust-boundary tests for canonical artifact notes."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.graph import ensure_initialized
from substrate.research_artifact.append_note import MAX_NOTE_CHARS, StaleArtifactError, append_note
from substrate.research_artifact.import_notes import parse_body_from_path
from substrate.research_artifact.paths import artifact_path_for
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody


@pytest.fixture
def artifact_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    root, events = tmp_path / "artifacts", tmp_path / "events"
    root.mkdir()
    events.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(root))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    return root, events


def _write(investigation_id: str = "inv-note", *, source_text: str = "") -> ResearchArtifactBody:
    body = ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="Bounded question",
        source_event_ids=["event-one"],
    )
    path = artifact_path_for(investigation_id)
    path.write_text(render_html(body), encoding="utf-8")
    if source_text:
        assert source_text not in path.read_text(encoding="utf-8")
    return body


def test_append_persists_across_read_and_refresh_and_is_private(artifact_env: tuple[Path, Path]):
    _, events = artifact_env
    body = _write(source_text="PRIVATE SOURCE PASSAGE")
    result = append_note("inv-note", " durable note ", body.content_hash(), events_dir=str(events))

    assert (result.notes_persisted, result.notes_skipped_duplicate) == (1, 0)
    assert parse_body_from_path(artifact_path_for("inv-note")).agent_notes == ["durable note"]
    assert (
        parse_body_from_path(artifact_path_for("inv-note")).content_hash()
        == result.current_content_hash
    )
    assert stat_mode(artifact_path_for("inv-note")) == 0o600
    assert "PRIVATE SOURCE PASSAGE" not in artifact_path_for("inv-note").read_text(encoding="utf-8")


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_duplicate_is_append_only_and_does_not_emit_again(artifact_env: tuple[Path, Path]):
    _, events = artifact_env
    body = _write()
    first = append_note("inv-note", "same", body.content_hash(), events_dir=str(events))
    duplicate = append_note(
        "inv-note", " same ", first.current_content_hash, events_dir=str(events)
    )

    assert (duplicate.notes_persisted, duplicate.notes_skipped_duplicate) == (0, 1)
    assert duplicate.event_ids == []
    assert parse_body_from_path(artifact_path_for("inv-note")).agent_notes == ["same"]


def test_rejects_stale_hash_identity_and_bounds(artifact_env: tuple[Path, Path]):
    body = _write()
    with pytest.raises(ValueError, match="empty"):
        append_note("inv-note", "   ", body.content_hash())
    with pytest.raises(StaleArtifactError, match="stale"):
        append_note("inv-note", "note", "0" * 64)
    with pytest.raises(ValueError, match="characters"):
        append_note("inv-note", "x" * (MAX_NOTE_CHARS + 1), body.content_hash())

    wrong = _write("wrong")
    artifact_path_for("wrong").write_text(
        render_html(wrong.model_copy(update={"investigation_id": "other"})), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="identity"):
        append_note("wrong", "note", wrong.content_hash())


def test_atomic_replace_failure_preserves_file_and_emits_no_event(
    artifact_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    _, events = artifact_env
    body = _write()
    path = artifact_path_for("inv-note")
    before = path.read_bytes()

    def fail_replace(_source: str, _destination: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        append_note("inv-note", "not persisted", body.content_hash(), events_dir=str(events))
    assert path.read_bytes() == before
    assert list(events.iterdir()) == []


def test_event_store_failure_reports_pending_and_duplicate_reconciles(
    artifact_env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
):
    _, events = artifact_env
    body = _write()
    module = importlib.import_module("substrate.research_artifact.append_note")
    original = module.import_agent_notes

    def fail_event(*_args, **_kwargs):
        raise OSError("event store unavailable")

    monkeypatch.setattr(module, "import_agent_notes", fail_event)
    pending = append_note(
        "inv-note", "durable pending", body.content_hash(), events_dir=str(events)
    )
    assert pending.event_pending is True
    assert parse_body_from_path(artifact_path_for("inv-note")).agent_notes == ["durable pending"]

    monkeypatch.setattr(module, "import_agent_notes", original)
    reconciled = append_note(
        "inv-note",
        "durable pending",
        pending.current_content_hash,
        events_dir=str(events),
    )
    assert reconciled.notes_skipped_duplicate == 1
    assert reconciled.event_pending is False
    assert len(reconciled.event_ids) == 1


def test_notes_endpoint_has_stable_conflict_and_counts(
    artifact_env: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db = tmp_path / "graph.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(str(db))
    body = _write()
    client = TestClient(create_app(register_wrestling=False))

    stale = client.post(
        "/research/inv-note/artifact/notes", json={"note": "x", "expected_content_hash": "0" * 64}
    )
    assert stale.status_code == 409
    assert stale.json() == {"detail": "artifact content hash is stale"}

    saved = client.post(
        "/research/inv-note/artifact/notes",
        json={"note": "x", "expected_content_hash": body.content_hash()},
    )
    assert saved.status_code == 200
    assert saved.json()["notes_persisted"] == 1
    assert saved.json()["notes_skipped_duplicate"] == 0
