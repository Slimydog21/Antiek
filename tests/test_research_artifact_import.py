"""Durable note acceptance, replay, and failure recovery through real exports."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from substrate.event_log import emit_typed, events, trajectory
from substrate.graph import ensure_initialized
from substrate.research_artifact import export_research_artifact, import_agent_notes, note_store
from substrate.research_artifact.import_notes import (
    load_persisted_agent_notes,
    parse_body_from_path,
)
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody
from substrate.schemas.events import ArtifactGeneratedPayload


@pytest.fixture
def imp_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str]:
    settings = {"db": str(tmp_path / "t.duckdb"), "events": str(tmp_path / "events"),
                "arts": str(tmp_path / "artifacts")}
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", settings["db"])
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", settings["events"])
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", settings["arts"])
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)
    ensure_initialized(settings["db"])
    return settings


def _html(tmp_path: Path, texts: list[str], iid: str = "inv-note") -> Path:
    path = tmp_path / "caller.html"
    path.write_text(render_html(ResearchArtifactBody(
        investigation_id=iid, problem_question="Note persistence", agent_notes=texts,
    )), encoding="utf-8")
    return path


def test_hashed_export_note_import_survives_caller_removal(imp_env: dict[str, str], tmp_path: Path) -> None:
    first = export_research_artifact("inv-roundtrip", db_path=imp_env["db"], events_dir=imp_env["events"])
    assert first.path.parent.name == "inv-roundtrip"
    assert first.path.parent.parent.name == "sources"
    body = parse_body_from_path(first.path)
    body.agent_notes.append("Keep this imported note")
    edited = tmp_path / "caller-copy.html"
    edited.write_text(render_html(body), encoding="utf-8")
    database_before = Path(imp_env["db"]).read_bytes()
    result = import_agent_notes(edited, events_dir=imp_env["events"])
    assert Path(imp_env["db"]).read_bytes() == database_before
    assert result.notes_imported == 1 and len(result.event_ids) == 1
    edited.unlink()
    second = export_research_artifact("inv-roundtrip", db_path=imp_env["db"], events_dir=imp_env["events"])
    rebuilt = parse_body_from_path(second.path)
    assert rebuilt.agent_notes == ["Keep this imported note"]
    assert rebuilt.insights == body.insights
    assert rebuilt.problem_question == body.problem_question


def test_normalized_append_only_replay_and_sealed_events(imp_env: dict[str, str], tmp_path: Path) -> None:
    path = _html(tmp_path, [" A ", "A", "", "B"])
    first = import_agent_notes(path)
    assert (first.notes_imported, first.notes_skipped_duplicate) == (2, 1)
    assert events.seal_investigation("inv-note", outbox_db_path=None) is not None
    second = import_agent_notes(_html(tmp_path, ["B", "C"]))
    assert (second.notes_imported, second.notes_skipped_duplicate) == (1, 1)
    assert load_persisted_agent_notes("inv-note") == ["A", "B", "C"]
    assert len(trajectory("inv-note")) == 3
    assert len(set(first.event_ids + second.event_ids)) == 3


def test_legacy_html_and_v1_events_require_explicit_reimport(imp_env: dict[str, str], tmp_path: Path) -> None:
    path = _html(tmp_path, ["Persist me"])
    legacy = Path(imp_env["arts"]) / "inv-note.html"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(path.read_bytes())
    before = export_research_artifact("inv-note", db_path=imp_env["db"])
    assert parse_body_from_path(before.path).agent_notes == []
    digest = hashlib.sha256(b"Persist me").hexdigest()
    emit_typed("inv-note", ArtifactGeneratedPayload(
        artifact_id="legacy", artifact_kind="other", intent=f"research_artifact_agent_note_v1:inv-note:{digest[:16]}",
        generating_role="note_taker", artifact_path=str(legacy), content_hash=digest,
        size_bytes=10, source_event_ids=["inv-note"],
    ), strict_write=True)
    with pytest.raises(note_store.NotePersistenceError, match="explicit reimport"):
        export_research_artifact("inv-note", db_path=imp_env["db"])
    assert import_agent_notes(legacy).notes_imported == 1
    legacy.unlink()
    after = export_research_artifact("inv-note", db_path=imp_env["db"])
    assert parse_body_from_path(after.path).agent_notes == ["Persist me"]


def test_explicit_events_directory_is_export_authority(imp_env: dict[str, str], tmp_path: Path) -> None:
    alternate = str(tmp_path / "alternate-events")
    import_agent_notes(_html(tmp_path, ["Alternate stream"]), events_dir=alternate)
    assert load_persisted_agent_notes("inv-note") == []
    exported = export_research_artifact("inv-note", db_path=imp_env["db"], events_dir=alternate)
    assert parse_body_from_path(exported.path).agent_notes == ["Alternate stream"]


def test_disabled_events_leave_invisible_orphan_then_retry(imp_env: dict[str, str], tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    path = _html(tmp_path, ["Retry me"])
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "true")
    with pytest.raises(note_store.NotePersistenceError, match="enabled durable events"):
        import_agent_notes(path)
    assert list(Path(imp_env["arts"]).glob("notes/*/*.txt"))
    assert load_persisted_agent_notes("inv-note") == []
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED")
    assert import_agent_notes(path).notes_imported == 1
    assert load_persisted_agent_notes("inv-note") == ["Retry me"]


def test_strict_append_failure_preserves_prior_commits_and_retry(imp_env: dict[str, str], tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    original = events._append_jsonl
    calls = 0

    def fail_second(path: str, row: dict[str, Any]) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected append failure")
        original(path, row)

    monkeypatch.setattr(events, "_append_jsonl", fail_second)
    path = _html(tmp_path, ["First committed", "Second pending"])
    with pytest.raises(note_store.NotePersistenceError):
        import_agent_notes(path)
    assert load_persisted_agent_notes("inv-note") == ["First committed"]
    monkeypatch.setattr(events, "_append_jsonl", original)
    result = import_agent_notes(path)
    assert (result.notes_imported, result.notes_skipped_duplicate) == (1, 1)
    assert load_persisted_agent_notes("inv-note") == ["First committed", "Second pending"]


@pytest.mark.parametrize("damage", ["missing", "changed", "mode"])
def test_accepted_object_damage_fails_export(imp_env: dict[str, str], tmp_path: Path, damage: str) -> None:
    import_agent_notes(_html(tmp_path, ["Accepted"]))
    stored = next(Path(imp_env["arts"]).glob("notes/*/*.txt"))
    if damage == "missing":
        stored.unlink()
    elif damage == "changed":
        stored.write_text("Modified", encoding="utf-8")
    else:
        stored.chmod(0o644)
    with pytest.raises(note_store.NotePersistenceError, match="missing or corrupt"):
        export_research_artifact("inv-note", db_path=imp_env["db"])


def test_event_path_is_never_read_authority(imp_env: dict[str, str]) -> None:
    with note_store.note_import_lock("inv-note"):
        digest, _, size = note_store.publish_note("inv-note", "Derived path only")
    emit_typed("inv-note", ArtifactGeneratedPayload(
        artifact_id=note_store.note_artifact_id("inv-note", digest), artifact_kind="other",
        intent=note_store.note_intent("inv-note", digest), generating_role="note_taker",
        artifact_path="/never-open-this/../../private.html", content_hash=digest, size_bytes=size,
        source_event_ids=["inv-note"],
    ), strict_write=True, event_id=note_store.note_event_id("inv-note", digest))
    assert load_persisted_agent_notes("inv-note") == ["Derived path only"]


def test_concurrent_threads_and_processes_accept_one_event(imp_env: dict[str, str], tmp_path: Path) -> None:
    path = _html(tmp_path, ["Concurrent"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(import_agent_notes, [path] * 4))
    assert sum(result.notes_imported for result in results) == 1
    assert len(trajectory("inv-note")) == 1
    process_path = _html(tmp_path, ["Multiprocess"], "inv-process")
    code = (
        "import json,sys; from pathlib import Path; "
        "from substrate.research_artifact import import_agent_notes; "
        "r=import_agent_notes(Path(sys.argv[1])); print(json.dumps([r.notes_imported,r.notes_skipped_duplicate]))"
    )
    processes = [subprocess.Popen([sys.executable, "-c", code, str(process_path)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(3)]
    outputs = [process.communicate(timeout=30) for process in processes]
    assert all(process.returncode == 0 for process in processes), outputs
    counts = [json.loads(stdout) for stdout, _ in outputs]
    assert sum(count[0] for count in counts) == 1
    assert sum(count[1] for count in counts) == 2
    assert len(trajectory("inv-process")) == 1


@pytest.mark.parametrize("bound,value,texts", [
    ("MAX_BATCH_NOTES", 1, ["A", "B"]), ("MAX_NOTE_BYTES", 2, ["long"]),
    ("MAX_BATCH_BYTES", 3, ["AB", "CD"]), ("MAX_PERSISTED_NOTES", 1, ["A", "B"]),
    ("MAX_PERSISTED_BYTES", 3, ["AB", "CD"]),
])
def test_import_bounds_reject_before_acceptance(imp_env: dict[str, str], tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch,
                                               bound: str, value: int, texts: list[str]) -> None:
    monkeypatch.setattr(note_store, bound, value)
    with pytest.raises(ValueError):
        import_agent_notes(_html(tmp_path, texts))
    assert trajectory("inv-note") == []


def test_mismatch_and_unsafe_investigation_reject_before_writes(imp_env: dict[str, str], tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mismatch"):
        import_agent_notes(_html(tmp_path, ["note"]), investigation_id="another")
    with pytest.raises(ValueError, match="invalid note investigation"):
        import_agent_notes(_html(tmp_path, ["note"], "../escape"))
    assert not Path(imp_env["arts"]).exists()


@pytest.mark.parametrize("field,value", [("content_hash", "bad"), ("size_bytes", 999),
                                          ("artifact_id", "wrong"), ("event_id", "wrong")])
def test_recognized_note_event_corruption_is_explicit(imp_env: dict[str, str], tmp_path: Path,
                                                     field: str, value: str | int) -> None:
    import_agent_notes(_html(tmp_path, ["Accepted"]))
    path = next(Path(imp_env["events"]).glob("*.jsonl"))
    row = json.loads(path.read_text())
    if field == "event_id":
        row[field] = value
    else:
        row["payload"][field] = value
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(note_store.NotePersistenceError, match="missing or corrupt"):
        load_persisted_agent_notes("inv-note")


def test_html_and_future_schema_bounds(imp_env: dict[str, str], tmp_path: Path,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    from substrate.research_artifact import import_notes

    path = _html(tmp_path, ["note"])
    # Match the body schema's current JSON formatting without relying on it.
    body = parse_body_from_path(_html(tmp_path, ["note"]))
    data = body.model_dump(mode="json")
    data["schema_version"] = 999
    path.write_text('<script type="application/json" id="antiek-artifact-v1">'
                    + json.dumps(data) + '</script>', encoding="utf-8")
    with pytest.raises(ValueError):
        import_agent_notes(path)
    monkeypatch.setattr(import_notes, "_MAX_HTML_BYTES", 8)
    with pytest.raises(ValueError, match="bounded regular file"):
        import_agent_notes(path)
    assert trajectory("inv-note") == []


def test_accumulated_export_replays_and_accepts_one_new_note(imp_env: dict[str, str], tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(note_store, "MAX_BATCH_NOTES", 2)
    monkeypatch.setattr(note_store, "MAX_BATCH_BYTES", 2)
    import_agent_notes(_html(tmp_path, ["A", "B"]))
    import_agent_notes(_html(tmp_path, ["C", "D"]))
    exported = export_research_artifact("inv-note", db_path=imp_env["db"])
    replay = import_agent_notes(exported.path)
    assert (replay.notes_imported, replay.notes_skipped_duplicate) == (0, 4)
    body = parse_body_from_path(exported.path)
    body.agent_notes.append("E")
    edited = tmp_path / "edited-export.html"
    edited.write_text(render_html(body), encoding="utf-8")
    result = import_agent_notes(edited)
    assert (result.notes_imported, result.notes_skipped_duplicate) == (1, 4)
    assert load_persisted_agent_notes("inv-note") == ["A", "B", "C", "D", "E"]


def test_escaped_notes_roundtrip_at_persisted_capacity(imp_env: dict[str, str], tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(note_store, "MAX_PERSISTED_BYTES", 8)
    import_agent_notes(_html(tmp_path, ['<<<<', '""""']))
    exported = export_research_artifact("inv-note", db_path=imp_env["db"])
    assert b"\\u003c" in exported.path.read_bytes()
    replay = import_agent_notes(exported.path)
    assert (replay.notes_imported, replay.notes_skipped_duplicate) == (0, 2)
    with pytest.raises(ValueError, match="persisted aggregate"):
        import_agent_notes(_html(tmp_path, ["one more"]))
    assert load_persisted_agent_notes("inv-note") == ['<<<<', '""""']


@pytest.mark.parametrize("character", ["<", "&", '"', "\x01"])
def test_full_capacity_escaped_export_fits_existing_style_reader(imp_env: dict[str, str], tmp_path: Path,
                                                                character: str) -> None:
    from interfaces.research.api.style_routes import _MAX_ARTIFACT_BYTES

    texts = [character * (note_store.MAX_NOTE_BYTES - 1) + suffix for suffix in "ABCD"]
    assert sum(len(text.encode()) for text in texts) == note_store.MAX_PERSISTED_BYTES
    assert import_agent_notes(_html(tmp_path, texts)).notes_imported == 4
    exported = export_research_artifact("inv-note", db_path=imp_env["db"])
    # The existing style route reads at most 10 MiB. Exercise actual JSON
    # escaping and projection copies instead of estimating from raw note size.
    size = exported.path.stat().st_size
    assert note_store.MAX_PERSISTED_BYTES < size < _MAX_ARTIFACT_BYTES
    print(f"CHARACTER={character!r}; FULL_CAP_ESCAPED_EXPORT_BYTES={size}; "
          f"RETAINED_NOTE_BYTES={note_store.MAX_PERSISTED_BYTES}")
    result = import_agent_notes(exported.path)
    assert (result.notes_imported, result.notes_skipped_duplicate) == (0, 4)


def test_cli_import_then_export_after_caller_removed(imp_env: dict[str, str], tmp_path: Path) -> None:
    path = _html(tmp_path, ["CLI accepted"])
    imported = subprocess.run([sys.executable, "-m", "substrate.research_artifact", "--import-notes", str(path)],
                              capture_output=True, text=True, timeout=30, check=True)
    assert "imported=1 skipped_dup=0 investigation=inv-note" in imported.stdout
    path.unlink()
    exported = subprocess.run([sys.executable, "-m", "substrate.research_artifact", "inv-note"],
                              capture_output=True, text=True, timeout=30, check=True)
    assert parse_body_from_path(Path(exported.stdout.strip())).agent_notes == ["CLI accepted"]


def test_legacy_migration_requires_every_accepted_hash(imp_env: dict[str, str], tmp_path: Path) -> None:
    for text in ["First", "Second"]:
        digest = hashlib.sha256(text.encode()).hexdigest()
        emit_typed("inv-note", ArtifactGeneratedPayload(
            artifact_id="legacy-" + text, artifact_kind="other",
            intent=f"research_artifact_agent_note_v1:inv-note:{digest[:16]}",
            generating_role="note_taker", artifact_path="/not-readable", content_hash=digest,
            size_bytes=len(text), source_event_ids=["inv-note"],
        ), strict_write=True)
    assert import_agent_notes(_html(tmp_path, ["First"])).notes_imported == 1
    with pytest.raises(note_store.NotePersistenceError, match="explicit reimport"):
        load_persisted_agent_notes("inv-note")
    assert import_agent_notes(_html(tmp_path, ["Second"])).notes_imported == 1
    assert load_persisted_agent_notes("inv-note") == ["First", "Second"]
