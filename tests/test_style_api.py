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

import os
import re
import tempfile
from dataclasses import replace

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
from substrate.research_artifact.paths import artifact_path_for

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
    resp = client.post(
        "/styles", json={"name": bad_name, "label": "Bad", "theme_css": ""}
    )
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
    assert client.post(
        "/styles",
        json={
            "name": "night-owl",
            "label": "Night owl",
            "theme_css": ".antiek-doc { background: #101418; color: #e8e4da; }",
        },
    ).status_code == 201
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
    assert client.post(
        "/styles",
        json={"name": "private-style", "label": "Mine", "theme_css": ""},
    ).status_code == 201

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
    assert client.post(
        "/styles",
        json={
            "name": "my-dark",
            "label": "My dark",
            "theme_css": ".antiek-doc { background: #000; }",
        },
    ).status_code == 201
    _as_user("user-b", monkeypatch)
    assert client.post(
        "/styles",
        json={"name": "my-dark", "label": "B's dark", "theme_css": ".x{}"},
    ).status_code == 201

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
