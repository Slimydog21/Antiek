from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from interfaces.research.api import create_app
from substrate.event_log.events import IdempotencyConflict, seal_investigation_authorized
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas.events import WorkspaceResumeEntry
from substrate.workspace_resume import (
    WorkspaceRevisionConflict,
    append_workspace_checkpoint,
    read_workspace_checkpoint,
)


@pytest.fixture
def events_root(tmp_path, monkeypatch):
    root = tmp_path / "events"
    root.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(root))
    return root


def authority(root, account="alice"):
    return InvestigationAuthority(account, "antiek:account-workspace-resume:v1", root)


def put(auth, revision, entries, key):
    return append_workspace_checkpoint(
        auth, base_revision=revision, entries=tuple(entries), mutation_key=key
    )


def test_unbound_read_is_zero_and_does_not_allocate(events_root):
    auth = authority(events_root)
    before = set(events_root.rglob("*"))
    assert read_workspace_checkpoint(auth).revision == 0
    assert set(events_root.rglob("*")) == before


def test_replay_conflict_stale_and_append_order(events_root):
    auth = authority(events_root)
    first = put(auth, 0, [WorkspaceResumeEntry(kind="stats")], "same")
    replay = put(auth, 0, [WorkspaceResumeEntry(kind="stats")], "same")
    assert replay == first
    with pytest.raises(IdempotencyConflict):
        put(auth, 1, [WorkspaceResumeEntry(kind="library")], "same")
    with pytest.raises(WorkspaceRevisionConflict):
        put(auth, 0, [WorkspaceResumeEntry(kind="library")], "next")
    second = put(auth, 1, [WorkspaceResumeEntry(kind="library")], "next")
    assert read_workspace_checkpoint(auth) == second


def test_one_lock_allows_only_one_concurrent_successor(events_root):
    auth = authority(events_root)
    put(auth, 0, [], "seed")

    def successor(key):
        try:
            return put(auth, 1, [WorkspaceResumeEntry(kind="stats")], key).revision
        except WorkspaceRevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(successor, ["a", "b"]))
    assert sorted(results, key=str) == [2, "conflict"]
    assert read_workspace_checkpoint(auth).revision == 2


def test_account_streams_are_isolated_for_same_semantic_ids(events_root):
    alice = authority(events_root, "alice")
    bob = authority(events_root, "bob")
    entry = WorkspaceResumeEntry(kind="research_artifact", investigation_id="same")
    put(alice, 0, [entry], "alice-key")
    assert read_workspace_checkpoint(bob).revision == 0
    put(bob, 0, [WorkspaceResumeEntry(kind="library")], "bob-key")
    assert read_workspace_checkpoint(alice).entries == (entry,)


def test_resolver_qualified_entry_is_serialized_as_the_exact_closed_shape(events_root):
    auth = authority(events_root)
    entry = WorkspaceResumeEntry(
        kind="hosted_html_document",
        resolver="engagement_document",
        document_id="same",
    )
    put(auth, 0, [entry], "closed-ref")
    [event_path] = events_root.rglob("*.jsonl")
    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert event["payload"]["entries"] == [
        {
            "kind": "hosted_html_document",
            "resolver": "engagement_document",
            "document_id": "same",
        }
    ]


def test_sealed_prefix_then_live_tail_uses_physical_order(events_root):
    auth = authority(events_root)
    put(auth, 0, [WorkspaceResumeEntry(kind="stats")], "one")
    pytest.importorskip("pyarrow")
    seal_investigation_authorized(auth)
    second = put(auth, 1, [WorkspaceResumeEntry(kind="library")], "two")
    assert read_workspace_checkpoint(auth) == second


def test_deep_research_entry_is_serialized_as_the_exact_closed_shape(events_root):
    auth = authority(events_root)
    put(
        auth,
        0,
        [WorkspaceResumeEntry(kind="deep_research_session", session_id="session")],
        "closed-session-ref",
    )
    [event_path] = events_root.rglob("*.jsonl")
    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert event["payload"]["entries"] == [
        {"kind": "deep_research_session", "session_id": "session"}
    ]


def test_ancestry_interrogation_entry_serializes_only_three_references(events_root):
    auth = authority(events_root)
    entry = WorkspaceResumeEntry(
        kind="ancestry_interrogation",
        investigation_id="investigation",
        manifest_id="manifest",
        receipt_id="receipt",
    )
    put(auth, 0, [entry], "closed-interrogation-ref")
    [event_path] = events_root.rglob("*.jsonl")
    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert event["payload"]["entries"] == [{
        "kind": "ancestry_interrogation",
        "investigation_id": "investigation",
        "manifest_id": "manifest",
        "receipt_id": "receipt",
    }]
    assert not {
        "question", "claim", "closure_ordinals", "spawn_ids", "session_ids", "prompt"
    } & set(event["payload"]["entries"][0])


def test_api_admits_and_rehydrates_only_resolved_ancestry_interrogation_refs(
    events_root, monkeypatch
):
    from interfaces.research.api import workspace_resume_routes as routes

    calls: list[tuple[str, str, str, str]] = []

    def resolve(_request, account_id, entry):
        calls.append(
            (account_id, entry.investigation_id, entry.manifest_id, entry.receipt_id)
        )
        if entry.receipt_id == "missing":
            raise routes.CollectiveManifestNotFound(entry.receipt_id)
        return object()

    monkeypatch.setattr(routes, "_resolve_ancestry_interrogation", resolve)
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    entry = {
        "kind": "ancestry_interrogation",
        "investigation_id": "investigation",
        "manifest_id": "manifest",
        "receipt_id": "receipt",
    }
    accepted = client.put(
        "/account/workspace-resume",
        json={
            "schema_version": 1,
            "base_revision": 0,
            "entries": [entry],
            "mutation_key": "interrogation-entry",
        },
    )
    assert accepted.status_code == 200, accepted.text
    resumed = client.get("/account/workspace-resume")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["entries"] == [entry]
    assert calls == [
        ("__operator__", "investigation", "manifest", "receipt"),
        ("__operator__", "investigation", "manifest", "receipt"),
    ]
    missing = client.put(
        "/account/workspace-resume",
        json={
            "schema_version": 1,
            "base_revision": 1,
            "entries": [{**entry, "receipt_id": "missing"}],
            "mutation_key": "missing-interrogation",
        },
    )
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == "no-store"


def test_api_no_store_strict_validation_and_filtered_revocation(events_root, monkeypatch):
    from interfaces.research.api import workspace_resume_routes as routes

    monkeypatch.setattr(routes, "_artifact_allowed", lambda _a, iid, _r: iid == "kept")
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    empty = client.get("/account/workspace-resume")
    assert empty.status_code == 200
    assert empty.headers["cache-control"] == "no-store"
    assert empty.json() == {"schema_version": 1, "revision": 0, "entries": []}

    malformed = client.put("/account/workspace-resume", json={"schema_version": 1, "base_revision": 0, "entries": [{"kind": "stats", "title": "leak"}], "mutation_key": "m"})
    assert malformed.status_code == 422
    assert malformed.headers["cache-control"] == "no-store"

    denied = client.put("/account/workspace-resume", json={"schema_version": 1, "base_revision": 0, "entries": [{"kind": "research_artifact", "investigation_id": "revoked"}], "mutation_key": "m"})
    assert denied.status_code == 404
    assert denied.headers["cache-control"] == "no-store"

    synced = client.put("/account/workspace-resume", json={"schema_version": 1, "base_revision": 0, "entries": [{"kind": "research_artifact", "investigation_id": "kept"}], "mutation_key": "m2"})
    assert synced.status_code == 200
    monkeypatch.setattr(routes, "_artifact_allowed", lambda *_: False)
    filtered = client.get("/account/workspace-resume")
    assert filtered.json() == {"schema_version": 1, "revision": 1, "entries": []}

    oversized = client.put(
        "/account/workspace-resume",
        content=b"x" * 16_385,
        headers={"content-type": "application/json"},
    )
    assert oversized.status_code == 413
    assert oversized.headers["cache-control"] == "no-store"

    chunked = client.put(
        "/account/workspace-resume",
        content=(part for part in [b"x" * 8_193, b"x" * 8_192]),
        headers={"content-type": "application/json"},
    )
    assert chunked.status_code == 413
    assert chunked.headers["cache-control"] == "no-store"

    missing_reference = client.get(
        "/account/html-document-refs/unsupported/document"
    )
    assert missing_reference.status_code == 404
    assert missing_reference.headers["cache-control"] == "no-store"
    malformed_reference_path = client.get("/account/html-document-refs")
    assert malformed_reference_path.status_code == 404
    assert malformed_reference_path.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "entry",
    [
        {"kind": "unknown"},
        {"kind": "subaction", "workflow": "admin"},
        {"kind": "research_artifact", "investigation_id": "x" * 513},
        {
            "kind": "hosted_html_document",
            "resolver": "hosted_document",
            "document_id": "bad\u0000id",
        },
        {"kind": "deep_research_session", "session_id": "bad\u0000id"},
        {"kind": "deep_research_session", "session_id": "x" * 513},
        {
            "kind": "ancestry_interrogation",
            "investigation_id": "investigation",
            "manifest_id": "manifest",
            "receipt_id": "receipt",
            "question": "private",
        },
        {
            "kind": "hosted_html_document",
            "resolver": "hosted_document",
            "document_id": "x" * 513,
        },
        {"kind": "library", "html": "<secret>"},
    ],
)
def test_api_rejects_open_or_source_content_shapes(events_root, entry):
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    response = client.put("/account/workspace-resume", json={"schema_version": 1, "base_revision": 0, "entries": [entry], "mutation_key": "m"})
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


def test_deep_research_resolver_endpoint_is_exact_no_store(events_root, monkeypatch):
    from interfaces.research.api import workspace_resume_routes as routes
    from substrate.floating_session.resume_projection import DeepResearchSessionProjection

    calls: list[tuple[str, str]] = []
    def resolve(_request, account_id: str, session_id: str):
        calls.append((account_id, session_id))
        return DeepResearchSessionProjection(session_id, "spawn", "inv", "asset", "running", "deep")
    monkeypatch.setattr(routes, "_resolve_session", resolve)
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    response = client.get("/account/deep-research-session-refs/session")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"schema_version": 1, "session_id": "session", "spawn_id": "spawn", "investigation_id": "inv", "parent_asset_id": "asset", "status": "running", "research_tier": "deep", "view_format": "html"}
    assert calls == [("__operator__", "session")]

@pytest.mark.parametrize(
    "extra",
    ["spawn_id", "parent_asset_id", "investigation_id", "selection_text", "goal", "model_id", "citation_provenance", "html", "status", "research_tier", "view_format"],
)
def test_deep_research_checkpoint_entry_is_reference_only(extra: str) -> None:
    with pytest.raises(ValidationError):
        WorkspaceResumeEntry.model_validate({"kind": "deep_research_session", "session_id": "session", extra: "forged"})


@pytest.mark.parametrize("session_id", ["", " session", "session ", "bad\nvalue", "x" * 513])
def test_deep_research_checkpoint_identifier_is_canonical(session_id: str) -> None:
    with pytest.raises(ValidationError):
        WorkspaceResumeEntry(kind="deep_research_session", session_id=session_id)
