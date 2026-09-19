"""GET /documents/{document_id}/render — the ingest half of the HTML thesis.

Two HTML systems existed in this tree and did not touch. The projection
engine rendered a doc-model into script-free HTML with an island and a style
from the forkable wheel, but only ever saw research exports. An ingested
PDF, web page or .docx landed as a flat sanitized blob with no doc-model, no
island, no style and no version — so the wheel could not reach the documents
the operator actually ingests. This route is the join.

The acceptance is deliberately end-to-end, from a document row and a real
sidecar write to the rendered bytes, because every individual piece already
worked before the route existed. What did not exist was the path.

Refusals are tested as carefully as the success: the sidecar's serve gate is
fail-closed on rights AND on sanitizer version, and a route that fell back to
some other representation when the gate refused would render a markdown
approximation under a wheel style, looking exactly like the real document.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.snapshot.reader_html import markdown_to_safe_html  # noqa: E402
from interfaces.research.api import books as books_api  # noqa: E402
from interfaces.research.api.app import create_app  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from services.html_projection.gate import find_violations  # noqa: E402
from services.html_projection.island import extract_island  # noqa: E402
from substrate.reader_html.store import store_reader_html  # noqa: E402

_SOURCE_MARKDOWN = """\
# Field Notes

An opening paragraph with a [reference](https://example.com/ref).

## Samples

| id  | mass | state |
|-----|------|-------|
| A-1 | 11.4 | dry   |
| A-2 | 9.8  | wet   |

- first observation
- second observation
"""


@pytest.fixture
def api_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-doc-render-api-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", os.path.join(tmpdir, "artifacts"))
    from substrate.graph.schema import init_database

    writer = connect_write(db_path, purpose="test/doc-render-api/schema")
    try:
        init_database(writer)
    finally:
        writer.close()
    return {"db_path": db_path, "tmpdir": tmpdir}


@pytest.fixture
def client(api_env):
    return TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))


def _seed_document(db: str, document_id: str = "doc-ingested") -> None:
    writer = connect_write(db, purpose="test/doc-render-api/seed")
    try:
        writer.execute(
            """
            INSERT INTO documents (
                document_id, document_type, content_class, source_tier,
                raw_text, metadata, source_uri, title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                document_id,
                "web_article",
                "personal_reading",
                4,
                _SOURCE_MARKDOWN,
                "{}",
                "https://example.com/field-notes",
                "Field Notes",
            ],
        )
    finally:
        writer.close()


def _seed_sidecar(db: str, document_id: str = "doc-ingested") -> None:
    """Write the sidecar the way ingest does: the ingest renderer's output
    handed to the store, which sanitizes inside the call."""
    writer = connect_write(db, purpose="test/doc-render-api/sidecar")
    try:
        store_reader_html(
            writer,
            document_id=document_id,
            main_html=markdown_to_safe_html(_SOURCE_MARKDOWN),
            source_kind="url",
            source_url="https://example.com/field-notes",
        )
    finally:
        writer.close()


def _as_owner(monkeypatch) -> None:
    """Grant the privileged owner policy tag — the same hook the reader-html
    and owner-full-text endpoint tests use. URL ingests are personal_reading,
    so without it the rights ring refuses the body."""
    monkeypatch.setattr(
        books_api,
        "_owner_read_policy_tag",
        lambda _request: books_api._OWNER_READ_POLICY_TAG,
    )


def _visible(html: str) -> str:
    return html.split("</style>", 1)[1].split("<template", 1)[0]


# ── The thesis: a wheel style applied to an ingested document ──


def test_ingested_document_renders_with_a_wheel_style(api_env, client, monkeypatch):
    _seed_document(api_env["db_path"])
    _seed_sidecar(api_env["db_path"])
    _as_owner(monkeypatch)

    resp = client.get("/documents/doc-ingested/render?style=academic-paper")
    assert resp.status_code == 200, resp.text
    html = resp.text
    assert resp.headers["X-Artifact-Style"] == "academic-paper"
    assert resp.headers["X-Document-ID"] == "doc-ingested"
    assert resp.headers["X-Reader-Revision"] == "1"

    body = _visible(html)
    # Structure the old flat-blob path could not carry.
    assert '<h2 class="antiek-heading">Samples</h2>' in body
    assert "<td>11.4</td>" in body
    assert '<ul class="antiek-list">' in body
    assert '<a href="https://example.com/ref">reference</a>' in body
    # The chosen style is present and the artifact is still an Antiek one.
    assert "Charter" in html  # the academic theme's serif stack
    # The provenance footer trails the data island, so it is asserted on the
    # whole artifact rather than on the visible-body slice.
    footer = html.split("</template>", 1)[1]
    assert "antiek-footer" in footer
    assert "document: doc-ingested" in footer
    assert find_violations(html) == []


def test_switching_style_rerenders_the_same_document_with_no_model_call(
    api_env, client, monkeypatch
):
    """Two styles, two responses, one document: the bodies are byte-identical
    and only the inlined stylesheet differs, which is what makes a restyle a
    pure presentation transform rather than a regeneration."""
    _seed_document(api_env["db_path"])
    _seed_sidecar(api_env["db_path"])
    _as_owner(monkeypatch)

    first = client.get("/documents/doc-ingested/render?style=antiek")
    second = client.get("/documents/doc-ingested/render?style=slate")
    assert first.status_code == second.status_code == 200
    assert first.text != second.text
    assert first.text.split("</style>", 1)[1] == second.text.split("</style>", 1)[1]
    assert extract_island(first.text) == extract_island(second.text)


def test_repeat_render_is_byte_identical(api_env, client, monkeypatch):
    """The other half of the no-model-call claim. Byte-identity across two
    independent requests is what a generation step could not give you: the
    route is parse-plus-template over stored bytes, end to end, so the same
    document under the same style is the same artifact every time — which is
    also what makes the X-Content-SHA256 header worth anything."""
    _seed_document(api_env["db_path"])
    _seed_sidecar(api_env["db_path"])
    _as_owner(monkeypatch)

    first = client.get("/documents/doc-ingested/render?style=book")
    second = client.get("/documents/doc-ingested/render?style=book")
    assert first.status_code == second.status_code == 200
    assert first.text == second.text
    assert first.headers["X-Content-SHA256"] == second.headers["X-Content-SHA256"]


def test_island_carries_the_doc_model_back(api_env, client, monkeypatch):
    _seed_document(api_env["db_path"])
    _seed_sidecar(api_env["db_path"])
    _as_owner(monkeypatch)

    resp = client.get("/documents/doc-ingested/render")
    assert resp.status_code == 200
    island = extract_island(resp.text)
    assert island["title"] == "Field Notes"
    assert island["source"] == {
        "document_id": "doc-ingested",
        "source_kind": "url",
        "source_url": "https://example.com/field-notes",
    }
    assert any(node["type"] == "table" for node in island["content"])


def test_default_style_is_the_house_look(api_env, client, monkeypatch):
    _seed_document(api_env["db_path"])
    _seed_sidecar(api_env["db_path"])
    _as_owner(monkeypatch)

    resp = client.get("/documents/doc-ingested/render")
    assert resp.status_code == 200
    assert resp.headers["X-Artifact-Style"] == "antiek"


# ── Refusals: the gate is the point, so each reason is a distinct answer ──


def test_unknown_style_is_404(api_env, client, monkeypatch):
    _seed_document(api_env["db_path"])
    _seed_sidecar(api_env["db_path"])
    _as_owner(monkeypatch)

    resp = client.get("/documents/doc-ingested/render?style=no-such-style")
    assert resp.status_code == 404


def test_missing_document_is_404(api_env, client, monkeypatch):
    _as_owner(monkeypatch)
    resp = client.get("/documents/doc-nowhere/render")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "document_not_found"


def test_document_without_a_sidecar_is_refused_not_approximated(
    api_env, client, monkeypatch
):
    """No reader HTML means no document to project. Rendering the stored
    markdown instead would produce something that looks exactly like a real
    projection of the source — the confusion the version gate exists to
    prevent."""
    _seed_document(api_env["db_path"])
    _as_owner(monkeypatch)

    resp = client.get("/documents/doc-ingested/render")
    assert resp.status_code == 422
    assert resp.json()["detail"] == "no_reader_html"


def test_version_stale_sidecar_is_refused(api_env, client, monkeypatch):
    _seed_document(api_env["db_path"])
    _seed_sidecar(api_env["db_path"])
    _as_owner(monkeypatch)
    writer = connect_write(api_env["db_path"], purpose="test/doc-render-api/stale")
    try:
        writer.execute(
            "UPDATE document_reader_html SET sanitizer_version = ? WHERE document_id = ?",
            ["books-allowlist/0.9.0", "doc-ingested"],
        )
    finally:
        writer.close()

    resp = client.get("/documents/doc-ingested/render")
    assert resp.status_code == 422
    assert resp.json()["detail"] == "sanitizer_version_stale"


def test_public_caller_is_refused_the_personal_reading_body(api_env, client):
    """No owner hook: the rights ring must refuse. A projection route that
    released a body the reader-html route would not would be a rights
    bypass wearing a stylesheet."""
    _seed_document(api_env["db_path"])
    _seed_sidecar(api_env["db_path"])

    resp = client.get("/documents/doc-ingested/render")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "rights_denied"
