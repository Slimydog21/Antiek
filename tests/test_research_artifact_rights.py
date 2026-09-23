"""The research artifact is an export: it passes the same rights chokepoint as
the notebook / deliverable exporters (spr-05-export-eligibility-contract.md).

An insight grounded in a non-servable document (personal_reading,
restricted_pending_opt_in, or a source whose rights cannot be resolved) must
reach every research-artifact surface as a cite-only notice, never as its
canonical text: the body, the stored export file + its island, the twin notes,
the HTML-native view, the compose draft-merge and the outline shelf labels.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from services.html_projection.island import extract_island
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight, promote_question
from substrate.research_artifact import build_body, export_research_artifact
from substrate.research_artifact.blocks import list_outline_blocks

PERSONAL = "PERSONAL READING PASSAGE quoted verbatim from a paywalled essay"
RESTRICTED = "RESTRICTED PASSAGE from a publisher who has not opted in"
DANGLING = "PASSAGE whose source document row is gone"
UNSOURCED = "UNSOURCED insight with no source document at all"
PUBLIC = "Public-domain finding that is servable in full."
OWN_QUESTION = "What evidence would change the operator verdict here"
PERSONAL_QUESTION = "PERSONAL QUESTION quoting the paywalled essay"

WITHHELD = (PERSONAL, RESTRICTED, DANGLING, UNSOURCED, PERSONAL_QUESTION)


@pytest.fixture
def rights_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ra-rights-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", os.path.join(tmpdir, "arts"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    con = connect_write(db)
    try:
        for doc_id, cls, holder, title in (
            ("doc-pr", "personal_reading", "holder-x", "Paywalled essay"),
            ("doc-rs", "restricted_pending_opt_in", "holder-y", "Gated book"),
            ("doc-pd", "public_domain", None, "Old pamphlet"),
        ):
            con.execute(
                "INSERT INTO documents (document_id, source_tier, document_type, "
                "content_class, ip_holder_id, title) VALUES (?,?,?,?,?,?)",
                [doc_id, 1, "article", cls, holder, title],
            )
    finally:
        con.close()
    for inv in ("inv-r", "inv-r2"):
        for text, doc in (
            (PERSONAL, "doc-pr"),
            (RESTRICTED, "doc-rs"),
            (DANGLING, "doc-missing"),
            (UNSOURCED, None),
            (PUBLIC, "doc-pd"),
        ):
            promote_insight(
                text=f"{text} [{inv}]",
                investigation_id=inv,
                confidence="moderate",
                source_document_id=doc,
            )
        promote_question(text=f"{OWN_QUESTION} [{inv}]", investigation_id=inv)
        promote_question(
            text=f"{PERSONAL_QUESTION} [{inv}]",
            investigation_id=inv,
            source_document_id="doc-pr",
        )
    return {"db": db, "events": events}


def _assert_rights_filtered(text: str, label: str) -> None:
    for secret in WITHHELD:
        assert secret not in text, f"{label}: non-servable text leaked: {secret!r}"
    assert PUBLIC in text, f"{label}: servable finding went missing"
    assert OWN_QUESTION in text, f"{label}: operator's own question went missing"
    assert "cite-only" in text, f"{label}: no cite-only marker"


def test_build_body_reduces_non_servable_nodes_to_cite_only(rights_env):
    body = build_body("inv-r", db_path=rights_env["db"], events_dir=rights_env["events"])
    texts = [ins.text for ins in body.insights]
    assert len(texts) == 5, texts
    assert sum(PUBLIC in t for t in texts) == 1
    cite_only = [t for t in texts if t.startswith("[cite-only")]
    assert len(cite_only) == 4, texts
    # The notice names the source's identity (title · holder), never its text.
    assert any("Paywalled essay · holder-x" in t for t in cite_only)
    assert any("Gated book · holder-y" in t for t in cite_only)
    _assert_rights_filtered(body.model_dump_json(), "build_body")


def test_every_research_artifact_surface_withholds_non_servable_text(rights_env):
    res = export_research_artifact(
        "inv-r", db_path=rights_env["db"], events_dir=rights_env["events"], emit_event=False
    )
    exported = res.path.read_text(encoding="utf-8")
    _assert_rights_filtered(exported, "stored export file")
    _assert_rights_filtered(str(extract_island(exported)), "export island")
    _assert_rights_filtered(
        res.twin_notes_path.read_text(encoding="utf-8"), "twin notes file"
    )

    labels = " ".join(
        b.label
        for b in list_outline_blocks(
            "inv-r", db_path=rights_env["db"], events_dir=rights_env["events"]
        )
    )
    _assert_rights_filtered(labels, "outline shelf labels")

    client = TestClient(create_app(register_wrestling=False))
    for path in (
        "/research/inv-r/artifact.html",
        "/research/inv-r/artifact/twin-notes.html",
        "/research/artifacts/compose/draft-merge.html"
        "?investigation_ids=inv-r&investigation_ids=inv-r2",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, (path, resp.text[:300])
        _assert_rights_filtered(resp.text, path)

    resp = client.post("/research/inv-r/artifact/export")
    assert resp.status_code == 200, resp.text[:300]
    with open(resp.json()["path"], encoding="utf-8") as f:
        _assert_rights_filtered(f.read(), "POST /artifact/export file")
