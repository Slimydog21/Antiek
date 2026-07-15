"""SPR-AHT-05 — compose index."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight
from substrate.research_artifact.compose import _publish_immutable, compose_artifacts


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
        promote_insight(text=txt, investigation_id=iid, source_document_id="doc-1")
    res = compose_artifacts(
        ["inv-a", "inv-b"],
        db_path=compose_env["db"],
        events_dir=compose_env["events"],
    )
    assert res.path.is_file()
    index = res.path.read_text(encoding="utf-8")
    assert "inv-a" in index and "inv-b" in index
    assert len(res.members) == 2
    assert res.composition_id.startswith("cmp-")
    assert "file://" not in index
    metadata = json.loads(index.split('id="composition-metadata">', 1)[1].split("</script>", 1)[0])
    assert [m["investigation_id"] for m in metadata["members"]] == ["inv-a", "inv-b"]
    replay = compose_artifacts(
        ["inv-a", "inv-b"], db_path=compose_env["db"], events_dir=compose_env["events"]
    )
    assert replay.composition_id == res.composition_id
    assert replay.path.read_bytes() == res.path.read_bytes()


@pytest.mark.parametrize(
    "ids", [[], ["one"], ["one", "one"], ["../one", "two"], ["one/two", "three"]]
)
def test_compose_rejects_bad_member_sets(compose_env, ids):
    with pytest.raises(ValueError):
        compose_artifacts(ids, db_path=compose_env["db"], events_dir=compose_env["events"])


def test_compose_preserves_existing_index_on_publish_failure(compose_env, monkeypatch):
    for iid in ("inv-a", "inv-b"):
        promote_insight(text=iid, investigation_id=iid, source_document_id="doc")
    first = compose_artifacts(
        ["inv-a", "inv-b"], db_path=compose_env["db"], events_dir=compose_env["events"]
    )
    original = first.path.read_bytes()
    import substrate.research_artifact.compose as module

    promote_insight(text="changed", investigation_id="inv-a", source_document_id="doc")
    monkeypatch.setattr(
        module.os,
        "link",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("simulated publish failure")),
    )
    with pytest.raises(OSError):
        compose_artifacts(
            ["inv-a", "inv-b"], db_path=compose_env["db"], events_dir=compose_env["events"]
        )
    assert first.path.read_bytes() == original


def test_composition_identity_binds_member_content(compose_env):
    for iid in ("inv-a", "inv-b"):
        promote_insight(text=iid, investigation_id=iid, source_document_id="doc")
    first = compose_artifacts(
        ["inv-a", "inv-b"], db_path=compose_env["db"], events_dir=compose_env["events"]
    )
    promote_insight(text="new evidence", investigation_id="inv-a", source_document_id="doc")
    second = compose_artifacts(
        ["inv-a", "inv-b"], db_path=compose_env["db"], events_dir=compose_env["events"]
    )
    assert second.composition_id != first.composition_id
    assert first.path.read_bytes() != second.path.read_bytes()
    first_member = first.path.parent / first.composition_id / "inv-a.html"
    second_member = second.path.parent / second.composition_id / "inv-a.html"
    assert first_member.read_bytes() != second_member.read_bytes()


def test_immutable_publisher_rejects_symlinked_parent(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(store))
    os.symlink(outside, store / "compositions")

    with pytest.raises(OSError):
        _publish_immutable(Path(store / "compositions" / "artifact.html"), "trusted")
    assert not (outside / "artifact.html").exists()


def test_immutable_publisher_rejects_existing_symlink(tmp_path, monkeypatch):
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(store))
    destination = store / "artifact.html"
    outside = tmp_path / "outside.html"
    outside.write_text("trusted", encoding="utf-8")
    os.symlink(outside, destination)

    with pytest.raises(OSError):
        _publish_immutable(destination, "trusted")
