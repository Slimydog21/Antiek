"""SPR-05 M3: synthesis-artifact route — allowed / restricted / mixed / poisoned.

The resolver is mocked so the route logic + the in-path zero-script gate are
exercised without a live graph. The rights filtering itself is proven in
``services/html_projection/tests/test_synthesis_adapter.py``; here we prove the
route wires it correctly and refuses a poisoned render.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import synthesis_artifact as mod
from services.html_projection.adapters.synthesis import (
    Claim,
    SourceRef,
    SynthesisExport,
)
from services.html_projection.gate import assert_script_free

SERVABLE = SourceRef(
    document_id="doc-pd",
    document_title="On Liberty",
    content_class="public_domain",
    ip_holder_id=None,
    locator="/read/doc-pd",
    chunk_text="PUBLIC DOMAIN TEXT",
)
PERSONAL = SourceRef(
    document_id="doc-pr",
    document_title="A Paul Graham essay",
    content_class="personal_reading",
    ip_holder_id="pg",
    locator="/read/doc-pr",
    chunk_text="SECRET THIRD PARTY TEXT",
)


def _client() -> TestClient:
    app = FastAPI()
    mod.register_synthesis_artifact_routes(app)
    return TestClient(app)


def test_allowed_synthesis_200_gate_clean(monkeypatch):
    exp = SynthesisExport(
        synthesis_id="s1", target_question="Q?", claims=[Claim("A", [SERVABLE])]
    )
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    r = _client().get("/api/syntheses/s1/artifact.html")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert "synthesis-s1.html" in r.headers["content-disposition"]
    assert_script_free(r.text)  # gate-clean served bytes
    assert "PUBLIC DOMAIN TEXT" in r.text  # servable embedded


def test_restricted_synthesis_403_with_reason(monkeypatch):
    exp = SynthesisExport(
        synthesis_id="s2",
        target_question="Q?",
        restricted=True,
        restriction_reason="owner withheld this synthesis",
    )
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    r = _client().get("/api/syntheses/s2/artifact.html")
    assert r.status_code == 403
    body = r.json()
    assert body["error"] == "export_refused"
    assert body["reason"] == "owner withheld this synthesis"


def test_mixed_rights_cite_only_marked(monkeypatch):
    exp = SynthesisExport(
        synthesis_id="s3",
        target_question="Q?",
        claims=[Claim("A", [SERVABLE, PERSONAL])],
    )
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    r = _client().get("/api/syntheses/s3/artifact.html")
    assert r.status_code == 200
    assert "PUBLIC DOMAIN TEXT" in r.text  # servable embedded
    assert "SECRET THIRD PARTY TEXT" not in r.text  # personal_reading withheld
    assert "cite-only" in r.text  # the withheld source is visibly marked


def test_not_found_404(monkeypatch):
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: None)
    r = _client().get("/api/syntheses/nope/artifact.html")
    assert r.status_code == 404


def test_poisoned_render_is_refused(monkeypatch):
    # Prove the gate is wired in the route, not decorative: a render that
    # emits a script must be refused (500), never served as a 200.
    exp = SynthesisExport(
        synthesis_id="s4", target_question="Q?", claims=[Claim("A", [SERVABLE])]
    )
    monkeypatch.setattr(mod, "resolve_synthesis_export", lambda sid, **kw: exp)
    monkeypatch.setattr(
        mod,
        "render",
        lambda dm, ctx: "<html><body><script>alert(1)</script></body></html>",
    )
    r = _client().get("/api/syntheses/s4/artifact.html")
    assert r.status_code == 500
    assert "gate" in r.text.lower()  # refused with the gate reason
