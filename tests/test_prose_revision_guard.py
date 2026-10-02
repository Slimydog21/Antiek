"""CR-F1's surviving half: a prose write must refuse a STALE edit.

Contract: specs/SPEC-PROSE-REVISION-GUARD.md. ``based_on_prose_text`` is additive
and optional. Absent = today's blind behaviour, unchanged. Present and stale =
409 ``prose_revision_conflict``, nothing written, no event emitted.

Production shape this protects: two tabs editing one section. The blind UPDATE at
``substrate/graph/ops.py:741`` let the later writer win silently and destroyed the
earlier draft, while the client had already merged both the 409->conflict mapping
(``shared/failure.ts:92``) and the sentence for it (``:57``).
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
    tmp = tempfile.mkdtemp(prefix="antiek-prose-guard-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmp}


def _client(temp_substrate):
    from interfaces.research.api.app import create_app

    return TestClient(
        create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    )


def _section(client):
    d = client.post(
        "/deliverables", json={"title": "Memo", "deliverable_kind": "research_memo"}
    ).json()
    s = client.post(
        "/sections",
        json={"deliverable_id": d["deliverable_id"], "section_index": 0, "title": "Intro"},
    ).json()
    return s["section_id"]


def _prose(db_path, section_id):
    from runtime.db_lock import connect_read

    con = connect_read(db_path)
    try:
        row = con.execute(
            "SELECT prose_text FROM deliverable_sections WHERE section_id = ?",
            [section_id],
        ).fetchone()
    finally:
        con.close()
    return None if row is None else row[0]


def _outbox_rows(db_path):
    from runtime.db_lock import connect_read

    con = connect_read(db_path)
    try:
        return con.execute("SELECT COUNT(*) FROM write_event_outbox").fetchone()[0]
    finally:
        con.close()


def _patch(client, section_id, prose_text, **extra):
    body = {"prose_text": prose_text, **extra}
    return client.patch(f"/sections/{section_id}/prose", json=body)


def test_stale_write_is_refused_and_the_newer_draft_survives(temp_substrate):
    """Acceptance 1 and 7: the second writer of the same baseline loses."""
    db = temp_substrate["db_path"]
    client = _client(temp_substrate)
    sid = _section(client)

    first = _patch(client, sid, "first draft", based_on_prose_text="")
    assert first.status_code == 202, first.text
    assert _prose(db, sid) == "first draft"

    # A second tab that still holds the original baseline.
    stale = _patch(client, sid, "second draft", based_on_prose_text="")
    assert stale.status_code == 409, (
        f"a stale write must be refused, got {stale.status_code} {stale.text[:200]}"
    )
    assert stale.json()["detail"] == "prose_revision_conflict"
    assert _prose(db, sid) == "first draft", "the stale write must not land"


def test_a_write_based_on_the_current_prose_is_accepted(temp_substrate):
    """Acceptance 2: the happy path is unchanged for a client that keeps up."""
    db = temp_substrate["db_path"]
    client = _client(temp_substrate)
    sid = _section(client)

    assert _patch(client, sid, "one", based_on_prose_text="").status_code == 202
    second = _patch(client, sid, "two", based_on_prose_text="one")
    assert second.status_code == 202, second.text
    assert _prose(db, sid) == "two"


def test_a_caller_without_the_baseline_keeps_todays_blind_behaviour(temp_substrate):
    """Acceptance 3: the field is additive; legacy callers are untouched."""
    db = temp_substrate["db_path"]
    client = _client(temp_substrate)
    sid = _section(client)

    assert _patch(client, sid, "legacy one").status_code == 202
    assert _patch(client, sid, "legacy two").status_code == 202
    assert _prose(db, sid) == "legacy two"


def test_the_conflict_path_writes_no_event(temp_substrate):
    """Acceptance 4: a refused write emits nothing."""
    db = temp_substrate["db_path"]
    client = _client(temp_substrate)
    sid = _section(client)

    assert _patch(client, sid, "kept", based_on_prose_text="").status_code == 202
    before = _outbox_rows(db)
    assert (
        _patch(client, sid, "refused", based_on_prose_text="", promote_to_graph=True).status_code
        == 409
    )
    assert _outbox_rows(db) == before, "the conflict path must write no outbox row"
    assert _prose(db, sid) == "kept"
