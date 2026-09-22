"""insert_document: a document with no explicit content_class is
personal_reading, whatever its document_type (audit wave 3, #13 residual).

The rule used to be a denylist of four connector types; the Wrestle upload
(any media_type), the Wrestle region PDF and the research-bridge paste
inserted NULL and were grandfathered PUBLIC by the chunk-search gate.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph import ensure_initialized, insert_document


@pytest.fixture
def env(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="deny-default-")
    db = os.path.join(tmp, "g.duckdb")
    events = os.path.join(tmp, "events")
    os.makedirs(events)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    ensure_initialized(db)
    yield {"db": db, "events": events}
    shutil.rmtree(tmp, ignore_errors=True)


def _class_of(db: str, doc_id: str):
    con = duckdb.connect(db, read_only=True)
    try:
        return con.execute("SELECT content_class FROM documents WHERE document_id = ?", [doc_id]).fetchone()[0]
    finally:
        con.close()


def _defaulting_events(events_dir: str) -> list[dict]:
    out = []
    for name in os.listdir(events_dir):
        with open(os.path.join(events_dir, name), encoding="utf-8") as fh:
            for line in fh:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("action_type") == "document.content_class_defaulted":
                    out.append(ev)
    return out


@pytest.mark.parametrize("document_type", ["pdf", "epub", "external_deep_research", "interview_transcript", "book"])
def test_no_class_means_personal_reading_for_every_type(env, document_type):
    con = connect_write(env["db"], purpose="t")
    try:
        insert_document(con, document_id=f"d-{document_type}", source_tier=3,
                        document_type=document_type, title="t", raw_text="body")
    finally:
        con.close()
    assert _class_of(env["db"], f"d-{document_type}") == "personal_reading"
    evs = [e for e in _defaulting_events(env["events"]) if (e.get("payload") or {}).get("document_type") == document_type]
    assert len(evs) == 1, "the defaulting is recorded exactly once"
    assert "body" not in json.dumps(evs[0])  # §9.0: never the text


def test_explicit_class_still_wins(env):
    con = connect_write(env["db"], purpose="t")
    try:
        insert_document(con, document_id="d-pd", source_tier=3, document_type="pdf",
                        title="t", content_class="public_domain")
    finally:
        con.close()
    assert _class_of(env["db"], "d-pd") == "public_domain"
    assert not _defaulting_events(env["events"])


def test_no_production_document_is_ever_born_null():
    """Every insert_document site either names a class or gets the default —
    there is no third path. Pinned as a property of the function, not a
    list of callers."""
    import inspect

    from substrate.graph import ops

    src = inspect.getsource(ops.insert_document)
    assert "defaulted_to_personal_reading = content_class is None" in src
    # the old denylist condition must not come back in the CODE (the
    # docstring may recount it as history)
    assert "document_type in THIRD_PARTY_DOCUMENT_TYPES" not in src
