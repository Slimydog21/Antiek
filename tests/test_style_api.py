"""Style-wheel HTTP API tests (spec §5.5 S2) — acceptance via TestClient.

Covers the bounded scope:
  - GET /styles lists builtins + the caller's forks (wheel order);
  - POST /styles creates a validated fork that then appears in the listing
    (and re-posting replaces a fork in place);
  - GET /artifacts/{id}/render?style=X re-projects the stored HTML: the
    <style> block changes while the data island (and every other byte)
    stays untouched — the deterministic no-model-call contract;
  - DELETE /styles/{name} removes a fork; builtins are 409 and unknown
    names are 404;
  - builtin override/removal → 409; unsafe CSS (@import / javascript: /
    <script>) → 422; bad slug → 422;
  - per-user isolation: a fork created by one identity is invisible to
    another (the persistence is keyed by user_id, layered over the shared
    builtin wheel).
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from services.html_projection.context import RenderContext
from services.html_projection.island import extract_island
from services.html_projection.renderer import render
from services.html_projection.styles import (
    BUILTIN_STYLES,
    ProjectionStyle,
    default_registry,
)
from substrate.graph import ensure_initialized
from substrate.multi_user.auth import UserClaims
from substrate.research_artifact.paths import artifact_path_for, atomic_write_nofollow
from substrate.research_artifact.store import ResearchArtifactStore

_BUILTIN_NAMES = [s.name for s in BUILTIN_STYLES]


@pytest.fixture
def api_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="style-api-")
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


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False))


def _sample_doc() -> dict:
    return {
        "title": "Styled doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Hello styled world."}],
            }
        ],
    }


def _seed_artifact(artifact_id: str, html: str) -> None:
    path = artifact_path_for(artifact_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def _style_block(html: str) -> str:
    match = re.search(r"<style>\n(.*?)</style>", html, re.DOTALL)
    assert match is not None, "rendered HTML carries no <style> block"
    return match.group(1)


def _without_style(html: str) -> str:
    """The document with the <style> block removed — what restyle must
    leave byte-identical (body, island, footer)."""
    return html.replace(_style_block(html), "", 1)


def _as_user(user_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch the identity the auth middleware attaches on the next
    requests, by patching the claims factory it calls per request.

    The factory is looked up through the module at call time (exactly as
    the middleware does with its in-handler import) so the patch takes
    effect for every request after this point.
    """
    import substrate.multi_user.auth as _auth

    original_claims = _auth.operator_claims
    monkeypatch.setattr(
        "substrate.multi_user.auth.operator_claims",
        lambda: replace(original_claims(), user_id=user_id),
    )


# ── GET /styles ──────────────────────────────────────────────────────────


def test_get_styles_lists_builtins_in_wheel_order(api_env):
    client = _client()
    resp = client.get("/styles")
    assert resp.status_code == 200
    styles = resp.json()["styles"]
    assert [s["name"] for s in styles] == _BUILTIN_NAMES
    assert all(s["builtin"] is True for s in styles)
    assert styles[0]["name"] == "antiek"


def test_get_styles_empty_wheel_for_fresh_user(api_env):
    """A user with no forks sees exactly the builtins — the wheel always
    starts from the shared house defaults."""
    client = _client()
    resp = client.get("/styles")
    assert resp.status_code == 200
    assert [s["name"] for s in resp.json()["styles"]] == _BUILTIN_NAMES


# ── POST /styles ─────────────────────────────────────────────────────────


def test_create_fork_appears_in_listing(api_env):
    client = _client()
    fork = {
        "name": "warm-serif",
        "label": "Warm serif",
        "description": "A cozy reading surface.",
        "theme_css": ".antiek-doc { font-family: Georgia, serif; color: #222; }",
    }
    resp = client.post("/styles", json=fork)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "warm-serif"
    assert body["builtin"] is False
    assert body["theme_css"] == fork["theme_css"]

    listing = client.get("/styles").json()["styles"]
    assert [s["name"] for s in listing] == _BUILTIN_NAMES + ["warm-serif"]
    forked = listing[-1]
    assert forked["builtin"] is False
    assert forked["label"] == "Warm serif"


def test_repost_fork_replaces_in_place(api_env):
    client = _client()
    base = {
        "name": "warm-serif",
        "label": "Warm serif",
        "description": "",
        "theme_css": ".antiek-doc { color: #222; }",
    }
    assert client.post("/styles", json=base).status_code == 201
    updated = dict(base, label="Warm serif v2", theme_css=".antiek-doc { color: #111; }")
    resp = client.post("/styles", json=updated)
    assert resp.status_code == 201
    listing = client.get("/styles").json()["styles"]
    assert [s["name"] for s in listing] == _BUILTIN_NAMES + ["warm-serif"]
    assert listing[-1]["label"] == "Warm serif v2"
    assert listing[-1]["theme_css"] == ".antiek-doc { color: #111; }"


def test_post_override_builtin_is_409(api_env):
    client = _client()
    resp = client.post(
        "/styles",
        json={
            "name": "antiek",
            "label": "Evil override",
            "theme_css": ".antiek-doc { color: red; }",
        },
    )
    assert resp.status_code == 409
    assert "fork it under a new name" in resp.json()["detail"]


@pytest.mark.parametrize(
    "unsafe_css",
    [
        "@import url('https://evil.example/x.css');",
        "a { color: red; } javascript:alert(1);",
        "<script>alert(1)</script>",
        ".antiek-doc { background: url(https://evil.example/p.png); }",
    ],
    ids=["at-import", "javascript", "script-tag", "url-external"],
)
def test_post_unsafe_css_is_422(api_env, unsafe_css):
    client = _client()
    resp = client.post(
        "/styles",
        json={"name": "evil-style", "label": "Evil", "theme_css": unsafe_css},
    )
    assert resp.status_code == 422, resp.text
    listing = client.get("/styles").json()["styles"]
    assert "evil-style" not in [s["name"] for s in listing]


@pytest.mark.parametrize(
    "bad_name",
    ["NotSlug", "with space", "UPPER", "trailing-", "-leading", ""],
    ids=["camel", "space", "upper", "trailing-hyphen", "leading-hyphen", "empty"],
)
def test_post_bad_slug_is_422(api_env, bad_name):
    client = _client()
    resp = client.post("/styles", json={"name": bad_name, "label": "Bad", "theme_css": ""})
    assert resp.status_code == 422, resp.text


def test_post_empty_label_is_422(api_env):
    client = _client()
    resp = client.post("/styles", json={"name": "ok-name", "label": "  "})
    assert resp.status_code == 422, resp.text


# ── DELETE /styles/{name} ────────────────────────────────────────────────


def test_delete_fork_removes_it(api_env):
    client = _client()
    fork = {"name": "temporary", "label": "Temp", "theme_css": ""}
    assert client.post("/styles", json=fork).status_code == 201

    resp = client.delete("/styles/temporary")
    assert resp.status_code == 204, resp.text
    listing = client.get("/styles").json()["styles"]
    assert "temporary" not in [s["name"] for s in listing]

    # A second delete of the same fork is a 404 — it is gone.
    resp = client.delete("/styles/temporary")
    assert resp.status_code == 404


def test_delete_builtin_is_409(api_env):
    client = _client()
    resp = client.delete("/styles/antiek")
    assert resp.status_code == 409, resp.text
    resp = client.delete("/styles/blog")
    assert resp.status_code == 409


def test_delete_unknown_style_is_404(api_env):
    client = _client()
    resp = client.delete("/styles/never-existed")
    assert resp.status_code == 404


# ── GET /artifacts/{id}/render ───────────────────────────────────────────


def test_render_artifact_in_style_changes_stylesheet_keeps_island(api_env):
    """The wheel's core contract: restyle is PURE presentation — the
    <style> block swaps, every other byte (including the data island)
    stays identical. No model call is involved."""
    client = _client()
    doc = _sample_doc()
    stored_html = render(doc, RenderContext())
    _seed_artifact("inv-styled", stored_html)

    resp = client.get("/artifacts/inv-styled/render", params={"style": "blog"})
    assert resp.status_code == 200, resp.text

    stored_block = _style_block(stored_html)
    restyled_block = _style_block(resp.text)
    assert restyled_block != stored_block
    # The restyled stylesheet is exactly the composed blog stylesheet.
    assert restyled_block == default_registry().get("blog").stylesheet()
    # Data island round-trips the SAME doc-model in both.
    assert extract_island(resp.text) == extract_island(stored_html) == doc
    # And nothing else moved: body, island, footer are byte-identical.
    assert _without_style(resp.text) == _without_style(stored_html)


def test_render_artifact_default_style_is_identity(api_env):
    """No style param → the Antiek default; the <style> block is
    byte-identical to the stored one's and the rest matches too."""
    client = _client()
    stored_html = render(_sample_doc(), RenderContext())
    _seed_artifact("inv-default", stored_html)

    resp = client.get("/artifacts/inv-default/render")
    assert resp.status_code == 200, resp.text
    assert _style_block(resp.text) == _style_block(stored_html)
    assert extract_island(resp.text) == extract_island(stored_html)
    assert _without_style(resp.text) == _without_style(stored_html)


def test_render_artifact_in_user_fork_style(api_env):
    """A fork created via the API is immediately usable on the render
    endpoint — the wheel's "regenerate in my style" path."""
    client = _client()
    assert (
        client.post(
            "/styles",
            json={
                "name": "night-owl",
                "label": "Night owl",
                "theme_css": ".antiek-doc { background: #101418; color: #e8e4da; }",
            },
        ).status_code
        == 201
    )
    stored_html = render(_sample_doc(), RenderContext())
    _seed_artifact("inv-fork", stored_html)

    resp = client.get("/artifacts/inv-fork/render", params={"style": "night-owl"})
    assert resp.status_code == 200, resp.text
    fork = ProjectionStyle(
        name="night-owl",
        label="Night owl",
        description="",
        theme_css=".antiek-doc { background: #101418; color: #e8e4da; }",
        builtin=False,
    )
    assert _style_block(resp.text) == fork.stylesheet()
    assert extract_island(resp.text) == extract_island(stored_html)


def test_render_missing_artifact_is_404(api_env):
    client = _client()
    resp = client.get("/artifacts/inv-missing/render", params={"style": "blog"})
    assert resp.status_code == 404


def test_render_unknown_style_is_404(api_env):
    client = _client()
    _seed_artifact("inv-x", render(_sample_doc(), RenderContext()))
    resp = client.get("/artifacts/inv-x/render", params={"style": "no-such-style"})
    assert resp.status_code == 404
    assert "no-such-style" in resp.json()["detail"]


def test_render_artifact_without_island_is_422(api_env):
    """A stored HTML file that was never a projection-engine artifact (no
    data island) cannot be restyled — a typed, honest 422, not a crash."""
    client = _client()
    _seed_artifact("inv-plain", "<!DOCTYPE html><html><body>plain</body></html>")
    resp = client.get("/artifacts/inv-plain/render", params={"style": "blog"})
    assert resp.status_code == 422, resp.text
    assert "data island" in resp.json()["detail"]


# ── per-user isolation ───────────────────────────────────────────────────


def test_fork_is_scoped_to_its_user(api_env, monkeypatch):
    client = _client()
    assert (
        client.post(
            "/styles",
            json={"name": "private-style", "label": "Mine", "theme_css": ""},
        ).status_code
        == 201
    )

    # Another identity's wheel shows only the builtins — the fork does not
    # leak across users.
    _as_user("user-b", monkeypatch)
    listing = client.get("/styles").json()["styles"]
    assert [s["name"] for s in listing] == _BUILTIN_NAMES

    # And user-b cannot delete or restyle with a style they cannot see.
    resp = client.delete("/styles/private-style")
    assert resp.status_code == 404
    _seed_artifact("inv-b", render(_sample_doc(), RenderContext()))
    resp = client.get("/artifacts/inv-b/render", params={"style": "private-style"})
    assert resp.status_code == 404


def test_users_share_builtins_but_not_forks(api_env, monkeypatch):
    client = _client()
    assert (
        client.post(
            "/styles",
            json={
                "name": "my-dark",
                "label": "My dark",
                "theme_css": ".antiek-doc { background: #000; }",
            },
        ).status_code
        == 201
    )
    _as_user("user-b", monkeypatch)
    assert (
        client.post(
            "/styles",
            json={"name": "my-dark", "label": "B's dark", "theme_css": ".x{}"},
        ).status_code
        == 201
    )

    # Same fork name, two owners, two wheels — both keep the builtins.
    _as_user("__operator__", monkeypatch)
    a_wheel = [s["label"] for s in client.get("/styles").json()["styles"]]
    assert a_wheel[-1] == "My dark"
    _as_user("user-b", monkeypatch)
    b_wheel = [s["label"] for s in client.get("/styles").json()["styles"]]
    assert b_wheel[-1] == "B's dark"
    assert a_wheel[: len(_BUILTIN_NAMES)] == [s.label for s in BUILTIN_STYLES]
    assert b_wheel[: len(_BUILTIN_NAMES)] == [s.label for s in BUILTIN_STYLES]


def test_user_claims_factory_shape(monkeypatch):
    """Guard the identity-switch seam the per-user tests rely on: the
    middleware's per-request claims factory must return UserClaims with a
    user_id the routes key forks by."""
    import substrate.multi_user.auth as _auth

    _as_user("user-b", monkeypatch)
    claims: UserClaims = _auth.operator_claims()
    assert claims.user_id == "user-b"


def test_export_then_render_exact_id_persists_owner_scoped_version(api_env, monkeypatch):
    """Real export -> style render uses one id and durably records the choice."""
    client = _client()
    exported = client.post("/research/inv-contract/artifact/export")
    assert exported.status_code == 200, exported.text
    assert exported.json()["artifact_id"] == "inv-contract"

    preview = client.get("/artifacts/inv-contract/render", params={"style": "blog"})
    assert preview.status_code == 200
    assert preview.headers["X-Artifact-Version"] == "preview"
    assert ResearchArtifactStore(api_env["db"]).get("inv-contract").latest_version == 0
    rendered = client.post("/artifacts/inv-contract/render", params={"style": "blog"})
    assert rendered.status_code == 200, rendered.text
    assert extract_island(rendered.text)["research_artifact"]["investigation_id"] == "inv-contract"
    record = ResearchArtifactStore(api_env["db"]).get("inv-contract")
    assert record is not None
    assert record.owner_user_id == "__operator__"
    assert record.source_hash is not None
    assert record.selected_style == "blog"
    assert record.latest_version == 1
    version_path = (
        artifact_path_for("inv-contract").parent / "versions" / "inv-contract" / "v1.html"
    )
    assert version_path.read_text(encoding="utf-8") == rendered.text
    latest = client.get("/artifacts/inv-contract/versions/latest")
    exact = client.get("/artifacts/inv-contract/versions/1")
    assert latest.text == exact.text == rendered.text
    assert latest.headers["X-Artifact-ID"] == "inv-contract"
    assert latest.headers["X-Artifact-Style"] == "blog"
    assert latest.headers["X-Artifact-Version"] == "1"
    assert latest.headers["X-Content-SHA256"] == hashlib.sha256(rendered.content).hexdigest()
    assert latest.headers["X-Source-SHA256"] == record.source_hash

    # Omitted style reuses the durable selection and identical apply is idempotent.
    again = client.post("/artifacts/inv-contract/render")
    assert again.headers["X-Artifact-Version"] == "1"
    assert ResearchArtifactStore(api_env["db"]).get("inv-contract").latest_version == 1

    _as_user("other-owner", monkeypatch)
    assert client.get("/artifacts/inv-contract/render").status_code == 404
    source_path = Path(exported.json()["path"])
    source_before = source_path.read_bytes()
    assert client.post("/research/inv-contract/artifact/export").status_code == 500
    assert source_path.read_bytes() == source_before


def test_render_refuses_oversize_and_corrupt_utf8(api_env):
    client = _client()
    oversized = artifact_path_for("too-large")
    oversized.parent.mkdir(parents=True, exist_ok=True)
    with oversized.open("wb") as handle:
        handle.truncate(10 * 1024 * 1024 + 1)
    assert client.get("/artifacts/too-large/render").status_code == 413

    corrupt = artifact_path_for("corrupt")
    corrupt.write_bytes(b"\xff\xfe")
    response = client.get("/artifacts/corrupt/render")
    assert response.status_code == 422
    assert "UTF-8" in response.json()["detail"]


def test_style_input_text_is_bounded(api_env):
    response = _client().post(
        "/styles",
        json={"name": "bounded", "label": "x" * 129, "theme_css": ""},
    )
    assert response.status_code == 422


def test_version_publish_failure_leaves_metadata_unchanged(api_env, monkeypatch):
    client = _client()
    assert client.post("/research/inv-fault/artifact/export").status_code == 200
    import substrate.research_artifact.store as store_module

    monkeypatch.setattr(
        store_module,
        "atomic_write_nofollow",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk fault")),
    )
    with pytest.raises(OSError, match="disk fault"):
        ResearchArtifactStore(api_env["db"]).add_version(
            "inv-fault", "__operator__", "blog", "<html></html>", "0" * 64
        )
    record = ResearchArtifactStore(api_env["db"]).get("inv-fault")
    assert record is not None and record.latest_version == 0


def test_orphan_next_version_is_recovered(api_env):
    client = _client()
    assert client.post("/research/inv-orphan/artifact/export").status_code == 200
    orphan = artifact_path_for("inv-orphan").parent / "versions" / "inv-orphan" / "v1.html"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("orphan", encoding="utf-8")
    applied = client.post("/artifacts/inv-orphan/render", params={"style": "blog"})
    assert applied.status_code == 200
    assert orphan.read_text(encoding="utf-8") == applied.text


def test_metadata_failure_removes_published_version(api_env, monkeypatch):
    client = _client()
    assert client.post("/research/inv-db-fault/artifact/export").status_code == 200
    from runtime.db_lock import LockedConnection

    original_execute = LockedConnection.execute

    def fail_version_insert(self, sql, parameters=None):
        if sql.startswith("INSERT INTO research_artifact_versions"):
            raise RuntimeError("metadata fault")
        return original_execute(self, sql, parameters)

    monkeypatch.setattr(LockedConnection, "execute", fail_version_insert)
    with pytest.raises(RuntimeError, match="metadata fault"):
        ResearchArtifactStore(api_env["db"]).add_version(
            "inv-db-fault", "__operator__", "blog", "<html></html>", "1" * 64
        )
    version = artifact_path_for("inv-db-fault").parent / "versions" / "inv-db-fault" / "v1.html"
    assert not version.exists()


def test_atomic_publish_failure_cleans_unique_temp(api_env, monkeypatch):
    target = artifact_path_for("atomic-fault")

    def fail_replace(*args, **kwargs):
        raise OSError("publish fault")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="publish fault"):
        atomic_write_nofollow(target, b"payload")
    assert not target.exists()
    assert list(target.parent.glob(".atomic-fault.html.*.tmp")) == []


def test_legacy_symlink_is_never_adopted(api_env, tmp_path):
    target = tmp_path / "outside.html"
    target.write_text(render(_sample_doc(), RenderContext()), encoding="utf-8")
    link = artifact_path_for("legacy-link")
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    assert _client().get("/artifacts/legacy-link/render").status_code == 404
    assert ResearchArtifactStore(api_env["db"]).get("legacy-link") is None


def test_source_publish_crash_leaves_owner_pending_and_retry_recovers(api_env, monkeypatch):
    import substrate.research_artifact.store as store_module

    with monkeypatch.context() as fault:
        fault.setattr(
            store_module,
            "atomic_write_nofollow",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("publish crash")),
        )
        response = _client().post("/research/inv-source-fault/artifact/export")
        assert response.status_code == 500
    # Pending claims are deliberately invisible to readers.
    assert ResearchArtifactStore(api_env["db"]).get("inv-source-fault") is None

    retry = _client().post("/research/inv-source-fault/artifact/export")
    assert retry.status_code == 200
    path = Path(retry.json()["path"])
    assert path.is_file()
    assert ResearchArtifactStore(api_env["db"]).get("inv-source-fault") is not None


def test_pending_claim_blocks_cross_owner_but_same_owner_can_retry(api_env, monkeypatch):
    import substrate.research_artifact.store as store_module

    with monkeypatch.context() as fault:
        fault.setattr(
            store_module,
            "atomic_write_nofollow",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("crash")),
        )
        assert _client().post("/research/inv-pending/artifact/export").status_code == 500
    _as_user("other-owner", monkeypatch)
    assert _client().post("/research/inv-pending/artifact/export").status_code == 500
    _as_user("__operator__", monkeypatch)
    assert _client().post("/research/inv-pending/artifact/export").status_code == 200


def test_anchored_unlink_removes_symlink_not_victim(api_env, tmp_path):
    from substrate.research_artifact.paths import unlink_anchored

    victim = tmp_path / "victim.txt"
    victim.write_text("survives", encoding="utf-8")
    link = artifact_path_for("unlink-link")
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(victim)
    unlink_anchored(link)
    assert not link.exists()
    assert victim.read_text(encoding="utf-8") == "survives"


def test_legacy_swap_after_fd_read_copies_validated_bytes(api_env, monkeypatch):
    import interfaces.research.api.style_routes as routes

    legacy = artifact_path_for("legacy-swap")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    original = render(
        {"title": "Original", "content": _sample_doc()["content"]}, RenderContext()
    )
    swapped = render(
        {"title": "Swapped", "content": _sample_doc()["content"]}, RenderContext()
    )
    legacy.write_text(original, encoding="utf-8")
    real_read = routes.read_bounded_nofollow
    swapped_once = False

    def read_then_swap(path, limit):
        nonlocal swapped_once
        data = real_read(path, limit)
        if not swapped_once and path == legacy:
            swapped_once = True
            legacy.write_text(swapped, encoding="utf-8")
        return data

    monkeypatch.setattr(routes, "read_bounded_nofollow", read_then_swap)
    response = _client().get("/artifacts/legacy-swap/render")
    assert response.status_code == 200
    assert extract_island(response.text)["title"] == "Original"
    record = ResearchArtifactStore(api_env["db"]).get("legacy-swap")
    assert record is not None
    assert record.source_path != legacy


def test_direct_legacy_ledger_table_migrates_before_get(api_env):
    source = artifact_path_for("legacy-ledger")
    source.parent.mkdir(parents=True, exist_ok=True)
    html = render(_sample_doc(), RenderContext())
    source.write_text(html, encoding="utf-8")
    con = duckdb.connect(api_env["db"])
    try:
        con.execute(
            "CREATE TABLE research_artifacts ("
            "artifact_id VARCHAR PRIMARY KEY, investigation_id VARCHAR NOT NULL, "
            "owner_user_id VARCHAR NOT NULL, source_path VARCHAR NOT NULL, "
            "selected_style VARCHAR, latest_version INTEGER NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        con.execute(
            "INSERT INTO research_artifacts VALUES "
            "('legacy-ledger', 'legacy-ledger', '__operator__', ?, NULL, 0, now(), now())",
            [str(source)],
        )
    finally:
        con.close()
    response = _client().get("/artifacts/legacy-ledger/render")
    assert response.status_code == 200
    record = ResearchArtifactStore(api_env["db"]).get("legacy-ledger")
    assert record is not None
    assert record.source_hash == hashlib.sha256(html.encode()).hexdigest()


def test_source_replacement_fails_stably_without_rebinding_hash(api_env):
    exported = _client().post("/research/inv-corrupt-source/artifact/export")
    assert exported.status_code == 200
    store = ResearchArtifactStore(api_env["db"])
    before = store.get("inv-corrupt-source")
    assert before is not None and before.source_hash is not None
    replacement = render(
        {"title": "Replacement", "content": _sample_doc()["content"]}, RenderContext()
    )
    before.source_path.write_text(replacement, encoding="utf-8")
    first = _client().get("/artifacts/inv-corrupt-source/render")
    second = _client().get("/artifacts/inv-corrupt-source/render")
    assert first.status_code == second.status_code == 422
    assert first.json()["detail"] == second.json()["detail"] == "artifact source hash mismatch"
    assert store.get("inv-corrupt-source").source_hash == before.source_hash



# ── style provenance: parent field ───────────────────────────────────────
# A fork records the slug it was derived from (a builtin or one of the
# caller's own forks), so the wheel can render "forked from X" durably
# across sessions instead of the frontend's fragile session-local tracking.


def test_fork_of_builtin_records_parent(api_env):
    """POST /styles with a builtin parent records and returns it; the GET
    listing carries the same parent so the frontend can render provenance."""
    client = _client()
    fork = {
        "name": "warm-serif",
        "label": "Warm serif",
        "theme_css": ".antiek-doc { font-family: Georgia, serif; }",
        "parent": "academic-paper",
    }
    resp = client.post("/styles", json=fork)
    assert resp.status_code == 201, resp.text
    assert resp.json()["parent"] == "academic-paper"

    listing = client.get("/styles").json()["styles"]
    forked = next(s for s in listing if s["name"] == "warm-serif")
    assert forked["parent"] == "academic-paper"


def test_fork_without_parent_is_null(api_env):
    """An omitted parent is a legitimate 'declares no provenance' fork — the
    response and listing carry parent: null."""
    client = _client()
    resp = client.post(
        "/styles",
        json={"name": "from-scratch", "label": "Scratch", "theme_css": ""},
    )
    assert resp.status_code == 201
    assert resp.json()["parent"] is None
    forked = next(
        s for s in client.get("/styles").json()["styles"] if s["name"] == "from-scratch"
    )
    assert forked["parent"] is None


def test_builtins_carry_null_parent(api_env):
    """Builtins have no parent (origin = the house); the GET listing reflects
    that so a frontend can distinguish 'forked from X' from the anchors."""
    client = _client()
    for s in client.get("/styles").json()["styles"]:
        assert s["builtin"] is True
        assert s["parent"] is None


def test_unknown_parent_is_422(api_env):
    """A parent that is neither a builtin nor one of the caller's forks is
    rejected with 422 (no invented provenance, no dangling reference)."""
    client = _client()
    resp = client.post(
        "/styles",
        json={
            "name": "bad-parent",
            "label": "Bad",
            "theme_css": "",
            "parent": "no-such-style",
        },
    )
    assert resp.status_code == 422, resp.text
    assert "unknown parent" in resp.json()["detail"]
    assert "bad-parent" not in [s["name"] for s in client.get("/styles").json()["styles"]]


def test_self_parent_is_422(api_env):
    """A fork cannot name itself as its parent (trivial provenance cycle)."""
    client = _client()
    resp = client.post(
        "/styles",
        json={"name": "ouroboros", "label": "Self", "theme_css": "", "parent": "ouroboros"},
    )
    assert resp.status_code == 422, resp.text
    assert "itself" in resp.json()["detail"]


def test_fork_of_own_fork_records_chain(api_env):
    """A fork whose parent is the caller's OWN existing fork is accepted —
    provenance can chain (builtin -> fork A -> fork B)."""
    client = _client()
    assert (
        client.post(
            "/styles",
            json={
                "name": "line-a",
                "label": "Line A",
                "theme_css": ".antiek-doc { color: #222; }",
                "parent": "book",
            },
        ).status_code
        == 201
    )
    resp = client.post(
        "/styles",
        json={
            "name": "line-b",
            "label": "Line B",
            "theme_css": ".antiek-doc { color: #111; }",
            "parent": "line-a",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["parent"] == "line-a"
    forked = next(
        s for s in client.get("/styles").json()["styles"] if s["name"] == "line-b"
    )
    assert forked["parent"] == "line-a"


def test_parent_pointing_at_another_users_fork_is_422(api_env, monkeypatch):
    """Provenance is user-scoped: a fork owned by ANOTHER identity is not a
    valid parent (it is not in the caller's wheel)."""
    client = _client()
    assert (
        client.post(
            "/styles",
            json={"name": "alice-style", "label": "Alice", "theme_css": "", "parent": "blog"},
        ).status_code
        == 201
    )
    _as_user("user-b", monkeypatch)
    resp = client.post(
        "/styles",
        json={
            "name": "bob-style",
            "label": "Bob",
            "theme_css": "",
            "parent": "alice-style",  # exists, but not on bob's wheel
        },
    )
    assert resp.status_code == 422, resp.text
    assert "unknown parent" in resp.json()["detail"]


def test_repost_fork_updates_parent(api_env):
    """Replacing a fork updates its provenance in place (the parent is real
    stored data, not frozen at first creation)."""
    client = _client()
    base = {
        "name": "editable",
        "label": "Editable",
        "theme_css": ".antiek-doc { color: #222; }",
        "parent": "blog",
    }
    assert client.post("/styles", json=base).status_code == 201
    updated = dict(base, parent="book", label="Editable v2")
    resp = client.post("/styles", json=updated)
    assert resp.status_code == 201
    assert resp.json()["parent"] == "book"
    forked = next(
        s for s in client.get("/styles").json()["styles"] if s["name"] == "editable"
    )
    assert forked["parent"] == "book"
    assert forked["label"] == "Editable v2"


def test_parent_survives_reload_across_sessions(api_env, monkeypatch):
    """The core fix: provenance is durable. A fork created with a parent,
    reloaded in a fresh client/registry, still carries 'forked from X' — no
    more session-local-only parent tracking."""
    client = _client()
    assert (
        client.post(
            "/styles",
            json={
                "name": "durable-fork",
                "label": "Durable",
                "theme_css": ".antiek-doc { color: #333; }",
                "parent": "slate",
            },
        ).status_code
        == 201
    )
    # A brand-new client (no in-memory wheel) reloads from the store.
    fresh = _client()
    forked = next(
        s for s in fresh.get("/styles").json()["styles"] if s["name"] == "durable-fork"
    )
    assert forked["parent"] == "slate"
