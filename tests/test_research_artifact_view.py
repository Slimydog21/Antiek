"""Focused fail-closed tests for the canonical ResearchArtifact HTML view."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.graph import ensure_initialized


@pytest.fixture
def view_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = tmp_path / "graph.duckdb"
    artifacts = tmp_path / "artifacts"
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(artifacts))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(str(db))
    return artifacts


@pytest.fixture
def client(view_env: Path) -> TestClient:
    return TestClient(create_app(register_wrestling=False))


def _canonical(root: Path, investigation_id: str = "inv-view") -> Path:
    path = root / f"{investigation_id}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_view_serves_canonical_utf8_html_with_isolation_headers(client: TestClient, view_env: Path):
    html = "<!doctype html><style>body{color:#123}</style><script>window.x='✓'</script>"
    path = _canonical(view_env)
    path.write_text(html, encoding="utf-8")
    before = (path.read_bytes(), path.stat().st_mtime_ns)

    response = client.get("/research/inv-view/artifact/view")

    assert response.status_code == 200
    assert response.text == html
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    csp = response.headers["content-security-policy"]
    assert "sandbox allow-scripts" in csp
    assert "allow-same-origin" not in csp
    assert "default-src 'none'" in csp
    assert "style-src 'unsafe-inline'" in csp
    assert "script-src 'unsafe-inline'" in csp
    assert "form-action 'none'" in csp
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_view_ignores_caller_path_and_reads_only_canonical(
    client: TestClient, view_env: Path, tmp_path: Path
):
    _canonical(view_env).write_text("<p>canonical</p>", encoding="utf-8")
    decoy = tmp_path / "decoy.html"
    decoy.write_text("<p>decoy</p>", encoding="utf-8")

    response = client.get("/research/inv-view/artifact/view", params={"path": str(decoy)})

    assert response.status_code == 200
    assert response.text == "<p>canonical</p>"
    assert "decoy" not in response.text


@pytest.mark.parametrize("unsafe_kind", ["missing", "symlink", "directory", "multilink"])
def test_view_rejects_missing_and_unsafe_files(
    client: TestClient, view_env: Path, tmp_path: Path, unsafe_kind: str
):
    path = _canonical(view_env)
    if unsafe_kind == "symlink":
        target = tmp_path / "target.html"
        target.write_text("<p>secret</p>", encoding="utf-8")
        path.symlink_to(target)
    elif unsafe_kind == "directory":
        path.mkdir()
    elif unsafe_kind == "multilink":
        path.write_text("<p>linked</p>", encoding="utf-8")
        os.link(path, tmp_path / "second-link.html")

    response = client.get("/research/inv-view/artifact/view")

    assert response.status_code == 404
    assert response.json() == {"detail": "artifact unavailable"}


def test_view_rejects_oversize_and_non_utf8_files(client: TestClient, view_env: Path):
    path = _canonical(view_env)
    path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    assert client.get("/research/inv-view/artifact/view").status_code == 404

    path.write_bytes(b"<p>\xff</p>")
    assert client.get("/research/inv-view/artifact/view").status_code == 404


def test_export_includes_encoded_canonical_view_url(client: TestClient):
    response = client.post("/research/inv%20encoded/artifact/export")
    assert response.status_code == 200
    assert response.json()["view_url"] == "/research/inv%20encoded/artifact/view"


def test_rendered_add_note_posts_only_bounded_versioned_identity_and_hash():
    from substrate.research_artifact.render import render_html
    from substrate.research_artifact.schema import ResearchArtifactBody

    rendered = render_html(ResearchArtifactBody(investigation_id="inv", problem_question="q"))
    assert 'type: "antiek.research-artifact.append-note"' in rendered
    assert "version: 1" in rendered
    assert "investigation_id: p.investigation_id" in rendered
    assert "expected_content_hash:" in rendered
    assert "t.slice(0, 20000)" in rendered
    assert "p.agent_notes.push(t)" not in rendered
    assert "view_url" not in rendered
