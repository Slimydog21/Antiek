"""SPR-06: notebook export route — all 3 formats, rights hold through .antiek.

The DB resolver is mocked (the route logic + emit + rights are what's tested;
the resolver's substrate read is honestly degraded — see the route docstring).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import notebook_artifact as mod
from services.html_projection.adapters.notebook import ResolvedRefData

CLAIM = {"type": "antiek_claim_card", "attrs": {"claim_id": "c1"}}
NOTE_PR = {"type": "antiek_note", "attrs": {"note_id": "n1"}}
PROSE = {"type": "paragraph", "content": [{"type": "text", "text": "Notebook prose."}]}

REFS = {
    "c1": ResolvedRefData(
        kind="claim", content_class="public_domain", ip_holder_id=None,
        title="On Liberty", payload={"statement": "REAL CLAIM TEXT"},
    ),
    "n1": ResolvedRefData(
        kind="note", content_class="personal_reading", ip_holder_id="pg",
        title="A PG essay", payload={"body": "SECRET PASSAGE TEXT"},
    ),
}


def _source():
    return mod.NotebookExportSource(
        content_tiptap={"type": "doc", "content": [CLAIM, NOTE_PR, PROSE]},
        title="My notebook",
        document_id="doc-nb",
        owner_user_id="u",
        content_class="notebook",
        resolved_refs=REFS,
    )


def _client() -> TestClient:
    app = FastAPI()
    mod.register_notebook_artifact_routes(app)
    return TestClient(app)


def test_html_export_gate_clean_with_resolved_content(monkeypatch):
    monkeypatch.setattr(mod, "resolve_notebook_export", lambda nid, **kw: _source())
    r = _client().get("/api/notebooks/nb1/artifact?format=html")
    assert r.status_code == 200
    assert "REAL CLAIM TEXT" in r.text  # servable claim inlined
    assert "Notebook prose." in r.text
    assert "SECRET PASSAGE TEXT" not in r.text  # personal_reading cite-only


def test_antiek_export_is_valid_and_does_not_leak(monkeypatch, tmp_path):
    from services.antiek_format import read_antiek

    monkeypatch.setattr(mod, "resolve_notebook_export", lambda nid, **kw: _source())
    monkeypatch.setattr(mod, "_resolve_db_path", lambda: str(tmp_path / "g.duckdb"))
    r = _client().get("/api/notebooks/nb1/artifact?format=antiek")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    assert "nb1.antiek" in r.headers["content-disposition"]
    assert read_antiek(r.content).signature_valid is True
    assert b"SECRET PASSAGE TEXT" not in r.content  # rights hold through container


def test_antiek_html_export_verifies(monkeypatch, tmp_path):
    from services.antiek_format.single_file import verify_single_file_html

    monkeypatch.setattr(mod, "resolve_notebook_export", lambda nid, **kw: _source())
    monkeypatch.setattr(mod, "_resolve_db_path", lambda: str(tmp_path / "g.duckdb"))
    r = _client().get("/api/notebooks/nb1/artifact?format=antiek_html")
    assert r.status_code == 200 and verify_single_file_html(r.text) is True


def test_unknown_format_400_and_missing_404(monkeypatch):
    monkeypatch.setattr(mod, "resolve_notebook_export", lambda nid, **kw: _source())
    assert _client().get("/api/notebooks/nb1/artifact?format=pdf").status_code == 400
    monkeypatch.setattr(mod, "resolve_notebook_export", lambda nid, **kw: None)
    assert _client().get("/api/notebooks/none/artifact").status_code == 404
