"""SR-02 — GET /chunks/{id} withholds personal_reading on the public path.

The chunk endpoint is always attribution_eligible (no policy_tag knob): bodies
from personal_reading sources must not leave the API, matching search/VSS.
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


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-sr02-chunk-pr-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir}


def _client(temp_substrate):
    import importlib

    app_mod = importlib.import_module("interfaces.research.api.app")
    importlib.reload(app_mod)
    app = app_mod.create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    return TestClient(app)


def _seed_chunk(temp_substrate, *, document_id, content_class, text):
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(temp_substrate["db_path"])
    with connect_write(temp_substrate["db_path"], purpose="sr02-chunk-pr") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="web_page",
            title=f"Title of {document_id}",
            content_class=content_class,
            on_conflict="ignore",
        )
        return insert_chunk(
            con,
            document_id=document_id,
            chunk_index=0,
            text=text,
            section_path="p.1",
        )


def test_get_chunk_personal_reading_withheld(temp_substrate):
    """personal_reading body must not leave GET /chunks on the public path."""
    secret = "OWNER private third-party essay text must not leak SR02"
    chunk_id = _seed_chunk(
        temp_substrate,
        document_id="doc-pr",
        content_class="personal_reading",
        text=secret,
    )
    client = _client(temp_substrate)
    body = client.get(f"/chunks/{chunk_id}").json()
    assert body["servable"] is False
    assert body["servability"] == "personal_readable"
    assert body["text"] == ""
    assert secret not in body["text"]
    assert body["document_title"] == "Title of doc-pr"


def test_get_chunk_public_domain_still_servable(temp_substrate):
    """Control: public_domain chunks remain servable after the gate union."""
    chunk_id = _seed_chunk(
        temp_substrate,
        document_id="doc-pd",
        content_class="public_domain",
        text="Open chunk text SR02 control.",
    )
    client = _client(temp_substrate)
    body = client.get(f"/chunks/{chunk_id}").json()
    assert body["servable"] is True
    assert body["servability"] is None
    assert body["text"] == "Open chunk text SR02 control."