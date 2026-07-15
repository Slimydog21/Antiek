"""Tests for Sprint 11 substrate API additions.

Coverage:
- New ActionType INVESTIGATION_SPAWNED_FROM + payload validation
- POST /investigations accepts parent_investigation_id + spawn_context
- POST /investigations emits INVESTIGATION_SPAWNED_FROM event when parent set
- GET /chunks/{chunk_id} happy path + 404
- GET /investigations (list) happy path + status filter
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

from substrate.schemas import (  # noqa: E402
    TYPED_PAYLOAD_ACTION_TYPES,
    ActionType,
    InvestigationSpawnedFromPayload,
    InvestigationStartRequestedPayload,
)

# ── 1. Schema additions ─────────────────────────────────────────────


def test_new_action_type_in_typed_set():
    """The new ActionType must be in TYPED_PAYLOAD_ACTION_TYPES so
    the event log's typed-payload reconstruction recognizes it."""
    assert ActionType.INVESTIGATION_SPAWNED_FROM.value in TYPED_PAYLOAD_ACTION_TYPES


def test_spawned_from_payload_round_trip():
    p = InvestigationSpawnedFromPayload(
        parent_investigation_id="inv-parent-abc",
        spawn_context="highlighted text from parent",
        parent_event_id="evt-xyz-123",
    )
    assert p.action_type == ActionType.INVESTIGATION_SPAWNED_FROM
    assert p.parent_investigation_id == "inv-parent-abc"
    assert p.spawn_context == "highlighted text from parent"
    # Round-trip through model_dump
    raw = p.model_dump()
    assert raw["parent_investigation_id"] == "inv-parent-abc"


def test_start_payload_carries_optional_parent_fields():
    p = InvestigationStartRequestedPayload(
        question="What is X?",
        parent_investigation_id="inv-parent",
        spawn_context="from parent",
    )
    assert p.parent_investigation_id == "inv-parent"
    assert p.spawn_context == "from parent"


def test_start_payload_parent_fields_optional():
    """Default behavior unchanged — parent fields are optional."""
    p = InvestigationStartRequestedPayload(question="What is Y?")
    assert p.parent_investigation_id is None
    assert p.spawn_context is None


# ── 2. POST /investigations with parent ──────────────────────────────


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-sprint11-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmp}


def _client(temp_substrate):
    from interfaces.research.api.app import create_app
    app = create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    return TestClient(app)


def test_post_investigation_with_parent_emits_spawned_from(temp_substrate):
    client = _client(temp_substrate)
    resp = client.post("/investigations", json={
        "question": "Why does X happen?",
        "parent_investigation_id": "inv-parent-foo",
        "spawn_context": "the highlighted text",
    })
    assert resp.status_code == 202
    inv_id = resp.json()["investigation_id"]

    # Trajectory should contain both start_requested AND spawned_from
    traj = client.get(f"/trajectory/{inv_id}").json()
    types = [e.get("action_type") for e in traj["events"]]
    assert ActionType.INVESTIGATION_START_REQUESTED.value in types
    assert ActionType.INVESTIGATION_SPAWNED_FROM.value in types

    # spawned_from payload should carry the parent info
    spawned = next(
        e for e in traj["events"]
        if e["action_type"] == ActionType.INVESTIGATION_SPAWNED_FROM.value
    )
    assert spawned["payload"]["parent_investigation_id"] == "inv-parent-foo"
    assert spawned["payload"]["spawn_context"] == "the highlighted text"


def test_post_investigation_without_parent_does_not_emit_spawned_from(
    temp_substrate,
):
    client = _client(temp_substrate)
    resp = client.post("/investigations", json={
        "question": "Plain cold question.",
    })
    assert resp.status_code == 202
    inv_id = resp.json()["investigation_id"]
    traj = client.get(f"/trajectory/{inv_id}").json()
    types = [e.get("action_type") for e in traj["events"]]
    assert ActionType.INVESTIGATION_SPAWNED_FROM.value not in types


def _derived_source() -> dict[str, object]:
    return {
        "derived_asset_id": "ast_" + "a" * 32,
        "revision_id": "rev_" + "b" * 32,
        "content_sha256": "c" * 64,
        "generation": 7,
        "citation_id": "dchunk_" + "d" * 64,
        "chunk_ordinal": 3,
        "chunk_text_sha256": "e" * 64,
        "excerpt": "Exact admitted passage.",
    }


def test_post_persists_structured_derived_citation(temp_substrate, monkeypatch):
    monkeypatch.setattr(
        "substrate.research_artifact.derived_citation_source."
        "verify_derived_citation_source",
        lambda **kwargs: kwargs["source"],
    )
    client = _client(temp_substrate)
    response = client.post("/investigations", json={
        "question": "What follows from this evidence?",
        "context": "Exact admitted passage.",
        "investigation_id": "inv-derived-typed",
        "derived_source": _derived_source(),
    })
    assert response.status_code == 202
    started = next(
        event for event in client.get("/trajectory/inv-derived-typed").json()["events"]
        if event["action_type"] == ActionType.INVESTIGATION_START_REQUESTED.value
    )
    assert started["payload"]["derived_source"] == _derived_source()
    assert "source identity" not in started["payload"]["context"]


def test_invalid_derived_citation_emits_no_start_event(temp_substrate, monkeypatch):
    from substrate.research_artifact.derived_citation_source import DerivedCitationConflict

    def refuse(**_kwargs):
        raise DerivedCitationConflict("mutated")

    monkeypatch.setattr(
        "substrate.research_artifact.derived_citation_source."
        "verify_derived_citation_source",
        refuse,
    )
    client = _client(temp_substrate)
    response = client.post("/investigations", json={
        "question": "What follows from this evidence?",
        "investigation_id": "inv-derived-refused",
        "derived_source": _derived_source(),
    })
    assert response.status_code == 409
    assert client.get("/trajectory/inv-derived-refused").json()["events"] == []


def test_derived_citation_must_match_research_context(temp_substrate, monkeypatch):
    verifier_called = False

    def verify(**_kwargs):
        nonlocal verifier_called
        verifier_called = True

    monkeypatch.setattr(
        "substrate.research_artifact.derived_citation_source."
        "verify_derived_citation_source",
        verify,
    )
    client = _client(temp_substrate)
    response = client.post("/investigations", json={
        "question": "What follows from this evidence?",
        "context": "Unrelated text.",
        "spawn_context": "Exact admitted passage.",
        "investigation_id": "inv-derived-mismatch",
        "derived_source": _derived_source(),
    })
    assert response.status_code == 409
    assert verifier_called is False
    assert client.get("/trajectory/inv-derived-mismatch").json()["events"] == []


def test_post_persists_ordered_derived_citations(temp_substrate, monkeypatch):
    sources = [_derived_source(), {
        **_derived_source(),
        "citation_id": "dchunk_" + "f" * 64,
        "chunk_ordinal": 4,
        "chunk_text_sha256": "1" * 64,
        "excerpt": "Second exact passage.",
    }]
    context = (
        "[Evidence 1 of 2]\nExact admitted passage.\n\n"
        "[Evidence 2 of 2]\nSecond exact passage."
    )
    monkeypatch.setattr(
        "substrate.research_artifact.derived_citation_source."
        "verify_derived_citation_sources",
        lambda **kwargs: tuple(kwargs["sources"]),
    )
    client = _client(temp_substrate)
    response = client.post("/investigations", json={
        "question": "What follows from these passages?",
        "context": context,
        "investigation_id": "inv-derived-curated",
        "derived_sources": sources,
    })
    assert response.status_code == 202
    events = client.get("/trajectory/inv-derived-curated").json()["events"]
    started = next(event for event in events if event["action_type"]
                   == ActionType.INVESTIGATION_START_REQUESTED.value)
    assert started["payload"]["derived_source"] is None
    assert started["payload"]["derived_sources"] == sources


def test_invalid_derived_citation_set_emits_no_event(temp_substrate, monkeypatch):
    from substrate.research_artifact.derived_citation_source import DerivedCitationConflict

    sources = [_derived_source(), {
        **_derived_source(),
        "citation_id": "dchunk_" + "f" * 64,
        "chunk_ordinal": 4,
        "chunk_text_sha256": "1" * 64,
        "excerpt": "Second exact passage.",
    }]
    context = (
        "[Evidence 1 of 2]\nExact admitted passage.\n\n"
        "[Evidence 2 of 2]\nSecond exact passage."
    )
    monkeypatch.setattr(
        "substrate.research_artifact.derived_citation_source."
        "verify_derived_citation_sources",
        lambda **_kwargs: (_ for _ in ()).throw(DerivedCitationConflict("last failed")),
    )
    client = _client(temp_substrate)
    response = client.post("/investigations", json={
        "question": "What follows from these passages?", "context": context,
        "investigation_id": "inv-derived-curated-refused",
        "derived_sources": sources,
    })
    assert response.status_code == 409
    assert client.get("/trajectory/inv-derived-curated-refused").json()["events"] == []


# ── 3. GET /chunks/{id} ──────────────────────────────────────────────


def test_get_chunk_happy_path(temp_substrate):
    """Seed a chunk via the graph ops, then fetch it via the API."""
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(temp_substrate["db_path"])
    with connect_write(temp_substrate["db_path"], purpose="test") as con:
        insert_document(
            con, document_id="doc-test", source_tier=2,
            document_type="academic_paper", title="Test Document",
        )
        chunk_id = insert_chunk(
            con, document_id="doc-test", chunk_index=0,
            text="The substantive chunk text.", section_path="Page 1",
        )

    client = _client(temp_substrate)
    resp = client.get(f"/chunks/{chunk_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["chunk_id"] == chunk_id
    assert body["text"] == "The substantive chunk text."
    assert body["section_path"] == "Page 1"
    assert body["document_id"] == "doc-test"
    assert body["document_title"] == "Test Document"
    assert body["source_tier"] == 2


def test_get_chunk_404(temp_substrate):
    from substrate.graph.schema import init_database_at_path
    init_database_at_path(temp_substrate["db_path"])
    client = _client(temp_substrate)
    resp = client.get("/chunks/chunk-does-not-exist")
    assert resp.status_code == 404


# ── 3b. SPR-04: §9.0 servability gate on the chunk endpoint ──────────


def _seed_chunk(temp_substrate, *, document_id, content_class, text="body text"):
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(temp_substrate["db_path"])
    with connect_write(temp_substrate["db_path"], purpose="test") as con:
        insert_document(
            con, document_id=document_id, source_tier=2,
            document_type="book", title=f"Title of {document_id}",
            content_class=content_class, on_conflict="ignore",
        )
        return insert_chunk(
            con, document_id=document_id, chunk_index=0,
            text=text, section_path="p.12",
        )


def test_get_chunk_servable_source_returns_body(temp_substrate):
    """A public-domain source IS servable: the named source opens, body
    text is returned, servable=True."""
    chunk_id = _seed_chunk(
        temp_substrate, document_id="doc-public",
        content_class="public_domain", text="The open chunk text.",
    )
    client = _client(temp_substrate)
    body = client.get(f"/chunks/{chunk_id}").json()
    assert body["servable"] is True
    assert body["servability"] is None
    assert body["text"] == "The open chunk text."
    # The named-source label resolves either way.
    assert body["document_title"] == "Title of doc-public"


def test_get_chunk_personal_reading_withholds_body(temp_substrate):
    """RG-03: personal_reading is owner-only — the HTTP chunk path must
    withhold the body on the same non-privileged gate as search/VSS."""
    chunk_id = _seed_chunk(
        temp_substrate, document_id="doc-personal",
        content_class="personal_reading",
        text="SECRET owner-only essay body that must not be served.",
    )
    client = _client(temp_substrate)
    body = client.get(f"/chunks/{chunk_id}").json()
    assert body["servable"] is False
    # Canonical ASR SR-09 label (consolidation unified #53's "personal_only").
    assert body["servability"] == "personal_readable"
    assert body["text"] == ""
    assert "SECRET" not in body["text"]
    assert body["document_title"] == "Title of doc-personal"


def test_get_chunk_restricted_source_not_opened(temp_substrate):
    """SPR-04 gate (verification): a restricted source's body is WITHHELD
    at the endpoint. The title still resolves (honest "not available to
    open" state), but ``text`` never carries the restricted body — even
    on a direct API call that bypasses the UI. This is the SAME
    restricted set the G1 chunk-search gate withholds on a non-privileged
    path (``substrate/graph/search.py`` RESTRICTED_CONTENT_CLASSES)."""
    chunk_id = _seed_chunk(
        temp_substrate, document_id="doc-restricted",
        content_class="restricted_pending_opt_in",
        text="SECRET in-copyright passage that must not be served.",
    )
    client = _client(temp_substrate)
    body = client.get(f"/chunks/{chunk_id}").json()
    assert body["servable"] is False
    assert body["servability"] == "restricted"
    # The body must NOT leave the endpoint.
    assert body["text"] == ""
    assert "SECRET" not in body["text"]
    # The named source still resolves so the reader sees the citation.
    assert body["document_title"] == "Title of doc-restricted"


def test_get_chunk_servable_source_surfaces_ip_holder(temp_substrate):
    """SPR-10 M1 — "whose work grounds this": a servable source surfaces its
    IP holder's display name + lifecycle status so the reader sees published-by
    on the named source. A null owner stays null (honest unknown, never
    invented)."""
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(temp_substrate["db_path"])
    with connect_write(temp_substrate["db_path"], purpose="test") as con:
        con.execute(
            "INSERT INTO ip_holders (ip_holder_id, display_name, legal_contact_email, "
            "status, escrow_balance_usd, metadata) "
            "VALUES ('ip-mit', 'MIT Press', '', 'pre_onboarded', 0, '{}')",
        )
        insert_document(
            con, document_id="doc-owned", source_tier=1,
            document_type="academic_paper", title="An Owned Paper",
            content_class="public_domain", ip_holder_id="ip-mit",
            on_conflict="ignore",
        )
        chunk_id = insert_chunk(
            con, document_id="doc-owned", chunk_index=0,
            text="body", section_path="p.1",
        )
    client = _client(temp_substrate)
    body = client.get(f"/chunks/{chunk_id}").json()
    assert body["servable"] is True
    assert body["ip_holder_name"] == "MIT Press"
    assert body["ip_holder_status"] == "pre_onboarded"


def test_get_chunk_restricted_source_withholds_ip_holder(temp_substrate):
    """SPR-10 §9.0 — a restricted source's IP holder is protected attribution:
    it is withheld with the body, so a reader can't infer "whose work" from a
    source we may not serve."""
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(temp_substrate["db_path"])
    with connect_write(temp_substrate["db_path"], purpose="test") as con:
        con.execute(
            "INSERT INTO ip_holders (ip_holder_id, display_name, legal_contact_email, "
            "status, escrow_balance_usd, metadata) "
            "VALUES ('ip-bigfive', 'A Big Five Publisher', '', 'pre_onboarded', 0, '{}')",
        )
        insert_document(
            con, document_id="doc-restricted-owned", source_tier=2,
            document_type="book", title="A Restricted Owned Book",
            content_class="restricted_pending_opt_in", ip_holder_id="ip-bigfive",
            on_conflict="ignore",
        )
        chunk_id = insert_chunk(
            con, document_id="doc-restricted-owned", chunk_index=0,
            text="restricted body", section_path="p.1",
        )
    client = _client(temp_substrate)
    body = client.get(f"/chunks/{chunk_id}").json()
    assert body["servable"] is False
    assert body["text"] == ""
    # The owner is withheld too — not just the body.
    assert body["ip_holder_name"] is None
    assert body["ip_holder_status"] is None


def test_get_chunk_null_content_class_grandfathered(temp_substrate):
    """A NULL content_class research chunk (legacy / the operator's own
    tier-2 paper) passes — exactly as it does in chunk search. The
    reading-surface preview is the operator reading their own research,
    not the stricter public full-text serve allowlist."""
    chunk_id = _seed_chunk(
        temp_substrate, document_id="doc-legacy",
        content_class=None, text="Legacy research body.",
    )
    client = _client(temp_substrate)
    body = client.get(f"/chunks/{chunk_id}").json()
    assert body["servable"] is True
    assert body["text"] == "Legacy research body."


def test_get_chunk_taken_down_source_not_opened(temp_substrate):
    """A taken-down source's body is withheld regardless of its
    underlying license — takedown wins over content_class."""
    from runtime.db_lock import connect_write

    chunk_id = _seed_chunk(
        temp_substrate, document_id="doc-pd-takedown",
        content_class="public_domain", text="Body to be taken down.",
    )
    with connect_write(temp_substrate["db_path"], purpose="test") as con:
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES (?, TRUE)",
            ["doc-pd-takedown"],
        )
    client = _client(temp_substrate)
    body = client.get(f"/chunks/{chunk_id}").json()
    assert body["servable"] is False
    assert body["servability"] == "taken_down"
    assert body["text"] == ""


# ── 4. GET /investigations (list) ────────────────────────────────────


def test_list_investigations_empty(temp_substrate):
    """Empty events dir → empty list."""
    client = _client(temp_substrate)
    resp = client.get("/investigations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["investigations"] == []


def test_list_investigations_returns_summaries(temp_substrate):
    client = _client(temp_substrate)
    # Create 3 investigations
    for q in ("first question?", "second question?", "third question?"):
        r = client.post("/investigations", json={"question": q})
        assert r.status_code == 202

    resp = client.get("/investigations")
    body = resp.json()
    assert body["count"] == 3
    questions = {s["question"] for s in body["investigations"]}
    assert questions == {
        "first question?", "second question?", "third question?",
    }
    # All in_progress (no orchestrator running in test)
    for s in body["investigations"]:
        assert s["status"] == "in_progress"
        assert s["started_at"] is not None
        assert s["cost_usd_total"] == 0.0


def test_list_investigations_status_filter(temp_substrate):
    """Status filter narrows to matching investigations."""
    client = _client(temp_substrate)
    r = client.post("/investigations", json={"question": "active query?"})
    assert r.status_code == 202

    resp = client.get("/investigations?status=in_progress")
    assert resp.json()["count"] == 1

    resp = client.get("/investigations?status=completed")
    assert resp.json()["count"] == 0


def test_list_investigations_carries_parent_lineage(temp_substrate):
    client = _client(temp_substrate)
    parent = client.post("/investigations", json={"question": "parent q?"}).json()
    child = client.post("/investigations", json={
        "question": "child q?",
        "parent_investigation_id": parent["investigation_id"],
        "spawn_context": "from parent",
    }).json()

    resp = client.get("/investigations").json()
    by_id = {s["investigation_id"]: s for s in resp["investigations"]}
    assert by_id[child["investigation_id"]]["parent_investigation_id"] == parent["investigation_id"]
    assert by_id[parent["investigation_id"]]["parent_investigation_id"] is None


def test_list_investigations_limit(temp_substrate):
    client = _client(temp_substrate)
    for i in range(5):
        client.post("/investigations", json={"question": f"q{i}?"})
    resp = client.get("/investigations?limit=3")
    assert resp.json()["count"] == 3
