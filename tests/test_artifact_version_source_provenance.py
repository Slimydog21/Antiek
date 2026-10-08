from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from services.html_projection.context import RenderContext
from services.html_projection.renderer import render
from substrate.graph import ensure_initialized
from substrate.research_artifact.paths import (
    artifact_path_for,
    artifact_source_path_for,
    artifact_version_path_for,
)
from substrate.research_artifact.store import ArtifactSourceChanged, ResearchArtifactStore


@pytest.fixture
def api_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="artifact-version-source-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    artifacts = os.path.join(tmpdir, "artifacts")
    os.makedirs(events, exist_ok=True)
    for key in (
        "ANTIEK_AUTH_SECRET",
        "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
        "ANTIEK_COOKIE_INSECURE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", artifacts)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "artifacts": artifacts}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rendered_source(text: str) -> bytes:
    document = {
        "title": "Source-bound research",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }
    return render(document, RenderContext()).encode("utf-8")


def _save(store: ResearchArtifactStore, text: str, artifact_id: str = "source-test") -> str:
    source = _rendered_source(text)
    digest = _sha(source)
    store.save_source(
        artifact_id, "investigation-source-binding", "__operator__",
        artifact_source_path_for(artifact_id, digest), source,
    )
    return digest


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False, register_providers=False,
                                 cors_origins=[]))


def test_reopened_version_keeps_its_original_source_after_reexport(api_env) -> None:
    store = ResearchArtifactStore(api_env["db"])
    source_a = _rendered_source("Source A says the first result holds.")
    source_a_hash = _sha(source_a)
    store.save_source(
        "artifact-source-binding",
        "investigation-source-binding",
        "__operator__",
        artifact_source_path_for("artifact-source-binding", source_a_hash),
        source_a,
    )

    client = _client()
    applied = client.post("/artifacts/artifact-source-binding/render")
    assert applied.status_code == 200, applied.text
    assert applied.headers["X-Artifact-Version"] == "1"
    v1_body = applied.content
    v1_content_hash = applied.headers["X-Content-SHA256"]

    source_b = _rendered_source("Source B supersedes the first result.")
    source_b_hash = _sha(source_b)
    assert source_b_hash != source_a_hash
    store.save_source(
        "artifact-source-binding",
        "investigation-source-binding",
        "__operator__",
        artifact_source_path_for("artifact-source-binding", source_b_hash),
        source_b,
    )

    latest = client.get("/artifacts/artifact-source-binding/versions/latest")
    exact = client.get("/artifacts/artifact-source-binding/versions/1")
    assert latest.status_code == 200, latest.text
    assert exact.status_code == 200, exact.text
    assert latest.content == v1_body
    assert exact.content == v1_body
    assert latest.headers["X-Content-SHA256"] == v1_content_hash
    assert exact.headers["X-Content-SHA256"] == v1_content_hash
    assert latest.headers["X-Source-SHA256"] == source_a_hash
    assert exact.headers["X-Source-SHA256"] == source_a_hash
    assert latest.headers["X-Artifact-Current-Source-SHA256"] == source_b_hash
    assert exact.headers["X-Artifact-Source-State"] == "superseded"

    second = client.post("/artifacts/artifact-source-binding/render")
    assert second.status_code == 200, second.text
    assert second.headers["X-Artifact-Version"] == "2"
    assert second.headers["X-Source-SHA256"] == source_b_hash
    assert second.headers["X-Artifact-Source-State"] == "current"
    assert client.get("/artifacts/artifact-source-binding/versions/latest").content == second.content
    still_first = client.get("/artifacts/artifact-source-binding/versions/1")
    assert still_first.content == v1_body
    assert still_first.headers["X-Source-SHA256"] == source_a_hash


def test_same_bytes_new_source_does_not_reuse_version(api_env) -> None:
    store = ResearchArtifactStore(api_env["db"])
    source_a = _save(store, "A")
    html = "<html><body>same rendered bytes</body></html>"
    digest = _sha(html.encode())
    first, first_path = store.add_version(
        "source-test", "__operator__", "antiek", html, digest, source_hash=source_a,
    )
    assert first == 1
    again, again_path = store.add_version(
        "source-test", "__operator__", "antiek", html, digest, source_hash=source_a,
    )
    assert (again, again_path) == (1, first_path)
    source_b = _save(store, "B")
    assert source_b != source_a
    second, second_path = store.add_version(
        "source-test", "__operator__", "antiek", html, digest, source_hash=source_b,
    )
    assert second == 2 and second_path != first_path
    assert store.get_version("source-test", "__operator__", 1).source_hash == source_a
    assert store.get_version("source-test", "__operator__", 2).source_hash == source_b


def test_source_change_between_preview_and_apply_refuses_before_file_mutation(
    api_env, monkeypatch,
) -> None:
    store = ResearchArtifactStore(api_env["db"])
    source_a = _save(store, "A")
    version_path = artifact_version_path_for("source-test", 1)
    version_path.parent.mkdir(parents=True, exist_ok=True)
    version_path.write_bytes(b"orphan before stale preview")
    original_add = ResearchArtifactStore.add_version
    captured = []

    def change_source_before_add(self, *args, **kwargs):
        captured.append(kwargs["source_hash"])
        _save(store, "B")
        return original_add(self, *args, **kwargs)

    monkeypatch.setattr(ResearchArtifactStore, "add_version", change_source_before_add)
    response = _client().post("/artifacts/source-test/render")
    assert captured == [source_a]  # Preview rendered A before B was exported.
    assert response.status_code == 409
    assert response.json() == {"detail": "artifact_source_changed"}
    assert version_path.read_bytes() == b"orphan before stale preview"
    record = store.get("source-test")
    assert record.latest_version == 0 and record.selected_style is None
    assert store.get_version("source-test", "__operator__") is None


def test_legacy_restart_keeps_unknown_identity_and_creates_new_bound_version(api_env) -> None:
    store = ResearchArtifactStore(api_env["db"])
    source_hash = _save(store, "legacy source")
    first = _client().post("/artifacts/source-test/render")
    assert first.status_code == 200
    first_body = first.content
    with connect_write(api_env["db"], purpose="test/legacy-ledger") as con:
        con.execute("ALTER TABLE research_artifact_versions DROP COLUMN source_hash")
    restarted = ResearchArtifactStore(api_env["db"])
    legacy = restarted.get_version("source-test", "__operator__", 1)
    assert legacy.source_hash is None
    receipt = _client().get("/artifacts/source-test/versions/1")
    assert receipt.status_code == 200 and receipt.content == first_body
    assert receipt.headers["X-Artifact-Source-State"] == "unverified"
    assert "X-Source-SHA256" not in receipt.headers
    assert receipt.headers["X-Artifact-Current-Source-SHA256"] == source_hash
    second = _client().post("/artifacts/source-test/render")
    assert second.status_code == 200 and second.headers["X-Artifact-Version"] == "2"
    assert restarted.get_version("source-test", "__operator__", 1).source_hash is None
    assert restarted.get_version("source-test", "__operator__", 2).source_hash == source_hash


def test_unknown_current_source_does_not_relabel_known_version(api_env) -> None:
    store = ResearchArtifactStore(api_env["db"])
    source_hash = _save(store, "known source")
    assert _client().post("/artifacts/source-test/render").status_code == 200
    with connect_write(api_env["db"], purpose="test/unknown-current-source") as con:
        con.execute("UPDATE research_artifacts SET source_hash=NULL WHERE artifact_id='source-test'")
    receipt = _client().get("/artifacts/source-test/versions/1")
    assert receipt.status_code == 200
    assert receipt.headers["X-Source-SHA256"] == source_hash
    assert receipt.headers["X-Artifact-Source-State"] == "unverified"
    assert "X-Artifact-Current-Source-SHA256" not in receipt.headers


def test_owner_pending_and_invalid_source_refuse_without_writes(api_env) -> None:
    store = ResearchArtifactStore(api_env["db"])
    source_hash = _save(store, "source")
    html = "<html>version</html>"
    digest = _sha(html.encode())
    path = artifact_version_path_for("source-test", 1)
    with pytest.raises(KeyError):
        store.add_version("source-test", "another-owner", "antiek", html, digest,
                          source_hash=source_hash)
    with pytest.raises(ValueError, match="lowercase sha256"):
        store.add_version("source-test", "__operator__", "antiek", html, digest,
                          source_hash=source_hash.upper())
    with connect_write(api_env["db"], purpose="test/pending-source") as con:
        con.execute("UPDATE research_artifacts SET state='pending' WHERE artifact_id='source-test'")
    pending_response = _client().post("/artifacts/source-test/render")
    assert pending_response.status_code == 409
    assert pending_response.json() == {"detail": "artifact_source_changed"}
    assert _client().get("/artifacts/source-test/render").status_code == 404
    with pytest.raises(ArtifactSourceChanged):
        store.add_version("source-test", "__operator__", "antiek", html, digest,
                          source_hash=source_hash)
    assert not path.exists()
    with connect_write(api_env["db"], purpose="test/check-no-version") as con:
        assert con.execute("SELECT COUNT(*) FROM research_artifact_versions").fetchone()[0] == 0
        assert con.execute("SELECT latest_version, selected_style FROM research_artifacts").fetchone() == (0, None)


def test_pending_export_cannot_adopt_surviving_legacy_file(api_env, monkeypatch) -> None:
    import substrate.research_artifact.store as store_module

    store = ResearchArtifactStore(api_env["db"])
    source_a = _rendered_source("Old source in surviving legacy file")
    legacy = artifact_path_for("source-test")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(source_a)
    _save(store, "Old source in surviving legacy file")

    source_b = _rendered_source("New source still publishing")
    source_b_hash = _sha(source_b)
    with monkeypatch.context() as fault:
        fault.setattr(
            store_module, "atomic_write_nofollow",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("publish paused")),
        )
        with pytest.raises(OSError, match="publish paused"):
            store.save_source(
                "source-test", "investigation-source-binding", "__operator__",
                artifact_source_path_for("source-test", source_b_hash), source_b,
            )

    client = _client()
    applied = client.post("/artifacts/source-test/render")
    assert applied.status_code == 409
    assert applied.json() == {"detail": "artifact_source_changed"}
    assert client.get("/artifacts/source-test/render").status_code == 404
    with pytest.raises(FileExistsError):
        store.save_source(
            "source-test", "investigation-source-binding", "__operator__",
            artifact_source_path_for("source-test", _sha(source_a)), source_a,
            only_if_absent=True,
        )
    import substrate.multi_user.auth as auth

    original_claims = auth.operator_claims
    monkeypatch.setattr(
        auth, "operator_claims", lambda: replace(original_claims(), user_id="another-owner"),
    )
    assert client.post("/artifacts/source-test/render").status_code == 404
    assert client.get("/artifacts/source-test/render").status_code == 404
    assert legacy.read_bytes() == source_a
    with connect_write(api_env["db"], purpose="test/pending-legacy-unchanged") as con:
        assert con.execute(
            "SELECT state, source_hash, latest_version, selected_style "
            "FROM research_artifacts WHERE artifact_id='source-test'"
        ).fetchone() == ("pending", source_b_hash, 0, None)
        assert con.execute("SELECT COUNT(*) FROM research_artifact_versions").fetchone()[0] == 0
    assert not artifact_version_path_for("source-test", 1).exists()


def test_legacy_adoption_loses_to_source_published_after_absence_check(
    api_env, monkeypatch,
) -> None:
    store = ResearchArtifactStore(api_env["db"])
    source_a = _rendered_source("Surviving pre-ledger legacy source")
    legacy = artifact_path_for("source-test")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(source_a)
    source_b = _rendered_source("New source published after absent observation")
    source_b_hash = _sha(source_b)
    source_b_path = artifact_source_path_for("source-test", source_b_hash)
    client = _client()

    original_check = ResearchArtifactStore.has_ledger_record
    observed: list[bool] = []

    def publish_after_absence_check(self, artifact_id):
        absent = not original_check(self, artifact_id)
        observed.append(absent)
        if absent:
            store.save_source(
                artifact_id, "investigation-source-binding", "__operator__",
                source_b_path, source_b,
            )
        return not absent

    monkeypatch.setattr(
        ResearchArtifactStore, "has_ledger_record", publish_after_absence_check,
    )
    response = client.post("/artifacts/source-test/render")

    assert observed == [True]
    assert response.status_code == 404
    assert response.json() == {"detail": "artifact not found"}
    record = store.get("source-test")
    assert record is not None
    assert record.source_hash == source_b_hash
    assert record.source_path == source_b_path
    assert source_b_path.read_bytes() == source_b
    assert legacy.read_bytes() == source_a
    assert record.latest_version == 0 and record.selected_style is None
    with connect_write(api_env["db"], purpose="test/legacy-race-ready") as con:
        assert con.execute(
            "SELECT state FROM research_artifacts WHERE artifact_id='source-test'"
        ).fetchone() == ("ready",)
    assert store.get_version("source-test", "__operator__") is None
    assert not artifact_version_path_for("source-test", 1).exists()


def test_corrupt_saved_body_is_refused_without_rebinding(api_env) -> None:
    store = ResearchArtifactStore(api_env["db"])
    source_hash = _save(store, "source")
    applied = _client().post("/artifacts/source-test/render")
    assert applied.status_code == 200
    saved = store.get_version("source-test", "__operator__", 1)
    Path(saved.html_path).write_bytes(b"corrupt")
    receipt = _client().get("/artifacts/source-test/versions/1")
    assert receipt.status_code == 422
    assert receipt.json()["detail"] == "stored version hash mismatch"
    assert store.get_version("source-test", "__operator__", 1).source_hash == source_hash
