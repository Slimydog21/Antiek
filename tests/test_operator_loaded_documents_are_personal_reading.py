"""Documents the operator loads or pastes are personal_reading, never NULL
(audit wave 3, #13 residual).

insert_document's deny-by-default guard covers the four connector types
only, and NULL content_class is an ACTIVE contract elsewhere (the licence
tool's "unlicensed" queue is the NULL rows) — so the fix is at the
producers: the Wrestle document load (any media_type), the Wrestle region
placeholder, and the research-bridge paste now say what they are. A
Wrestle-loaded PDF of anyone's authorship was grandfathered PUBLIC by the
chunk-search gate; the grounder reads it back on the owner's private-
research path.
"""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import duckdb
import httpx
import pytest

from interfaces.research.api import EventBroadcaster, create_app
from processing.embedding.embed import _reset_default_provider
from substrate.constants import THIRD_PARTY_DOCUMENT_TYPES
from substrate.dispatch import reset_provider_registry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


@pytest.fixture
def app_and_bus():
    bus = EventBroadcaster()
    app = create_app(broadcaster=bus, cors_origins=[])
    return app, bus


@pytest.fixture
async def async_client(app_and_bus):
    app, _ = app_and_bus
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _class_of(document_id: str):
    con = duckdb.connect(os.environ["ANTIEK_DUCKDB_PATH"], read_only=True)
    try:
        row = con.execute("SELECT content_class FROM documents WHERE document_id = ?", [document_id]).fetchone()
    finally:
        con.close()
    return row[0] if row else "<no row>"


async def _post(ac, *, investigation_id, document_id, payload):
    r = await ac.post(
        "/events/typed",
        json={"investigation_id": investigation_id, "document_id": document_id,
              "payload": payload, "role": "user_agent"},
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_wrestle_document_load_lands_personal_reading(app_and_bus, async_client):
    _, bus = app_and_bus
    await _post(async_client, investigation_id="inv-w", document_id="doc-loaded", payload={
        "action_type": "document.loaded", "media_type": "pdf",
        "content_hash": "sha256:t", "size_bytes": 1000,
    })
    await bus.wait_for_handlers(timeout=5.0)
    assert _class_of("doc-loaded") == "personal_reading"


@pytest.mark.asyncio
async def test_wrestle_region_placeholder_lands_personal_reading(app_and_bus, async_client):
    _, bus = app_and_bus
    # A region posted for a document that was never loaded (replay) makes the
    # bridge synthesise a placeholder documents row — it must be classed too.
    await _post(async_client, investigation_id="inv-w", document_id="doc-never-loaded", payload={
        "action_type": "document.region_selected", "region_id": "r-1", "page": 1,
        "char_start": 0, "char_end": 11, "text_excerpt": "some words.",
    })
    await bus.wait_for_handlers(timeout=5.0)
    assert _class_of("doc-never-loaded") == "personal_reading"


def test_research_bridge_paste_lands_personal_reading(tmp_path):
    from runtime.db_lock import connect_write
    from substrate.graph import ensure_initialized
    from substrate.research_bridge.ingest import ingest_paste
    from substrate.research_bridge.schema import init_research_bridge

    db = os.environ["ANTIEK_DUCKDB_PATH"]
    ensure_initialized(db)
    text = "Findings\n\nAn outside deep-research tool wrote these paragraphs about a topic. " * 5
    with connect_write(db, purpose="t") as con:
        init_research_bridge(con)
        res = ingest_paste(con, raw_text=text, investigation_id="inv-p", do_chunk=False)
    assert _class_of(res.document_id) == "personal_reading"


# Files whose class-less insert_document call registers the class in the SAME
# write transaction via the rights chokepoint (register_source_document), so
# the row is never committed NULL. A class-less insert whose document_type is
# in THIRD_PARTY_DOCUMENT_TYPES is covered by insert_document's own
# deny-by-default guard. Anything else must pass content_class=.
_REGISTERS_IN_TRANSACTION = {
    "acquisition/arxiv/adapter.py",
    "acquisition/books/adapter.py",
    "acquisition/interview/adapter.py",
    "acquisition/podcasts/adapter.py",
    "acquisition/voice/adapter.py",
}


def test_no_other_production_insert_document_is_class_less():
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    offenders = []
    for f in files:
        if f.startswith("tests/") or "/tests/" in f or "/test_" in f:
            continue
        try:
            tree = ast.parse((ROOT / f).read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name == "insert_document" and "content_class" not in {k.arg for k in node.keywords}:
                dt = next((k.value for k in node.keywords if k.arg == "document_type"), None)
                guarded = isinstance(dt, ast.Constant) and dt.value in THIRD_PARTY_DOCUMENT_TYPES
                if f not in _REGISTERS_IN_TRANSACTION and not guarded:
                    offenders.append(f"{f}:{node.lineno}")
    assert offenders == [], f"class-less insert_document outside the in-transaction registrars: {offenders}"
