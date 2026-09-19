"""SPR-AHT-03 — import append-only agent notes from artifact HTML."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from substrate.event_log import trajectory
from substrate.graph import ensure_initialized
from substrate.research_artifact import (
    export_research_artifact,
    import_agent_notes,
    import_agent_notes_html,
    operator_authority,
)
from substrate.research_artifact.import_notes import load_persisted_agent_notes
from substrate.research_artifact.outbox import reconcile_pending_events
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody
from substrate.research_artifact.storage import FilesystemArtifactStore, UnsafeArtifactState
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
    authority = operator_authority("inv-imp")
    path = FilesystemArtifactStore().write(authority, render_html(body))
    r1 = import_agent_notes(path, authority=authority, events_dir=imp_env["events"])
    assert r1.notes_imported == 2
    r2 = import_agent_notes(Path(path), authority=authority, events_dir=imp_env["events"])
    assert r2.notes_imported == 0
    assert r2.notes_skipped_duplicate == 2

    rows = trajectory(authority.event_stream_id, events_dir=imp_env["events"])
    kinds = [x.get("action_type") for x in rows]
    assert kinds.count(ActionType.ARTIFACT_GENERATED.value) == 2


def test_export_carries_forward_agent_notes(imp_env):
    body = ResearchArtifactBody(
        investigation_id="inv-carry",
        problem_question="Carry",
        agent_notes=["Persist me"],
    )
    authority = operator_authority("inv-carry")
    FilesystemArtifactStore().write(authority, render_html(body))

    res = export_research_artifact(
        "inv-carry",
        authority=authority,
        db_path=imp_env["db"],
        events_dir=imp_env["events"],
    )
    text = res.path.read_text(encoding="utf-8")
    assert "Persist me" in text
    assert '"agent_notes"' in text


def test_multi_note_partial_failure_reconciles_each_undelivered_event_once(imp_env, monkeypatch):
    from substrate.research_artifact import import_notes as import_module

    authority = operator_authority("inv-partial")
    body = ResearchArtifactBody(
        investigation_id="inv-partial",
        problem_question="Partial",
        agent_notes=["First exact note", "Second exact note"],
    )
    html = render_html(body)
    original_append = import_module.append_event_once
    calls = 0

    def fail_second(event, *, events_dir=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected event persistence failure")
        return original_append(event, events_dir=events_dir)

    monkeypatch.setattr(import_module, "append_event_once", fail_second)
    with pytest.raises(RuntimeError, match="injected"):
        import_agent_notes_html(html, authority=authority, events_dir=imp_env["events"])
    pending = list((authority.account_dir() / "pending-events").glob("*.json"))
    assert len(pending) == 1

    result = reconcile_pending_events(authority, events_dir=imp_env["events"])
    assert (result.delivered, result.pending, result.quarantined) == (1, 0, 0)
    rows = trajectory(authority.event_stream_id, events_dir=imp_env["events"])
    note_events = [
        row
        for row in rows
        if str((row.get("payload") or {}).get("intent", "")).startswith(
            "research_artifact_agent_note_v1:"
        )
    ]
    assert len(note_events) == 2
    assert len({row["event_id"] for row in note_events}) == 2


def test_retried_pending_note_converges_on_one_event(imp_env):
    authority = operator_authority("inv-retry")
    html = render_html(
        ResearchArtifactBody(
            investigation_id="inv-retry",
            problem_question="Retry",
            agent_notes=["One logical note"],
        )
    )

    def fail_before_emit():
        raise RuntimeError("injected pre-emit crash")

    for _ in range(2):
        with pytest.raises(RuntimeError, match="pre-emit"):
            import_agent_notes_html(
                html,
                authority=authority,
                events_dir=imp_env["events"],
                before_emit=fail_before_emit,
            )
    assert len(list((authority.account_dir() / "pending-events").glob("*.json"))) == 1
    result = reconcile_pending_events(authority, events_dir=imp_env["events"])
    assert (result.delivered, result.pending, result.quarantined) == (1, 0, 0)
    rows = trajectory(authority.event_stream_id, events_dir=imp_env["events"])
    assert (
        sum(
            str((row.get("payload") or {}).get("intent", "")).startswith(
                "research_artifact_agent_note_v1:"
            )
            for row in rows
        )
        == 1
    )


def test_local_import_adapter_rejects_noncanonical_path(imp_env, tmp_path):
    authority = operator_authority("inv-canonical-only")
    FilesystemArtifactStore().write(
        authority,
        render_html(
            ResearchArtifactBody(
                investigation_id="inv-canonical-only", problem_question="Canonical"
            )
        ),
    )
    foreign = tmp_path / "foreign.html"
    foreign.write_text("not canonical", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match authority"):
        import_agent_notes(foreign, authority=authority, events_dir=imp_env["events"])


def test_existing_unsafe_artifact_state_is_not_silently_treated_as_absent(imp_env):
    authority = operator_authority("inv-incomplete")
    path = authority.artifact_path()
    path.parent.mkdir(parents=True)
    path.write_text("orphan bytes", encoding="utf-8")
    with pytest.raises(UnsafeArtifactState):
        load_persisted_agent_notes("inv-incomplete", authority=authority)
