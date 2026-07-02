"""SPR-06: deliverable (Write surface) export route — all 3 formats + rights.

Resolver mocked (the route logic + emit + rights are tested; the DB read is
honestly degraded — see the route docstring).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import deliverable_artifact as mod
from services.html_projection.adapters.deliverable import (
    DeliverableBlock,
    DeliverableExport,
    DeliverableSection,
)


def _source():
    return mod.DeliverableExportSource(
        export=DeliverableExport(
            title="My memo",
            sections=[
                DeliverableSection(
                    heading="Findings",
                    blocks=[
                        DeliverableBlock(block_kind="synthesized", text="OPERATOR PROSE", content_class=None),
                        DeliverableBlock(
                            block_kind="claim",
                            text="SECRET DELIVERABLE TEXT",
                            content_class="personal_reading",
                            ip_holder_id="pg",
                            source_title="A PG essay",
                        ),
                    ],
                )
            ],
        ),
        owner_user_id="u",
        document_id="dlv-1",
    )


def _client() -> TestClient:
    app = FastAPI()
    mod.register_deliverable_artifact_routes(app)
    return TestClient(app)


def test_html_export_has_prose_and_cite_only(monkeypatch):
    monkeypatch.setattr(mod, "resolve_deliverable_export", lambda did, **kw: _source())
    r = _client().get("/api/deliverables/dlv-1/artifact?format=html")
    assert r.status_code == 200
    assert "OPERATOR PROSE" in r.text
    assert "SECRET DELIVERABLE TEXT" not in r.text  # non-servable block cite-only'd


def test_antiek_export_valid_and_no_leak(monkeypatch, tmp_path):
    from services.antiek_format import read_antiek

    monkeypatch.setattr(mod, "resolve_deliverable_export", lambda did, **kw: _source())
    monkeypatch.setattr(mod, "_resolve_db_path", lambda: str(tmp_path / "g.duckdb"))
    r = _client().get("/api/deliverables/dlv-1/artifact?format=antiek")
    assert r.status_code == 200
    assert "dlv-1.antiek" in r.headers["content-disposition"]
    assert read_antiek(r.content).signature_valid is True
    assert b"SECRET DELIVERABLE TEXT" not in r.content  # rights hold through container


def test_antiek_html_export_verifies(monkeypatch, tmp_path):
    from services.antiek_format.single_file import verify_single_file_html

    monkeypatch.setattr(mod, "resolve_deliverable_export", lambda did, **kw: _source())
    monkeypatch.setattr(mod, "_resolve_db_path", lambda: str(tmp_path / "g.duckdb"))
    r = _client().get("/api/deliverables/dlv-1/artifact?format=antiek_html")
    assert r.status_code == 200 and verify_single_file_html(r.text) is True


def test_unknown_format_400_and_missing_404(monkeypatch):
    monkeypatch.setattr(mod, "resolve_deliverable_export", lambda did, **kw: _source())
    assert _client().get("/api/deliverables/dlv-1/artifact?format=pdf").status_code == 400
    monkeypatch.setattr(mod, "resolve_deliverable_export", lambda did, **kw: None)
    assert _client().get("/api/deliverables/none/artifact").status_code == 404
