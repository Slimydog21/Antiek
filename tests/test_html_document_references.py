from __future__ import annotations

import hashlib
import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.workspace_resume_routes import workspace_resume_router
from substrate.engagement_spine.authority import EngagementAuthority
from substrate.engagement_spine.progress import record_progress
from substrate.engagement_spine.store import (
    FileEngagementStore,
    InMemoryEngagementStore,
    authorized_store,
)
from substrate.marketplace_host.library import FileHostStore, InMemoryHostStore
from substrate.midnight_oil.deposit import deposit_job_results
from substrate.midnight_oil.job import InMemoryJobStore, MidnightOilJob
from substrate.multi_user.auth import UserClaims
from substrate.workspace_resume import account_workspace_authority, read_workspace_checkpoint


def _doc_model_row(document_id: str, title: str, text: str) -> dict[str, object]:
    doc_model = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }
    digest = hashlib.sha256(
        json.dumps(
            doc_model,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "document_id": document_id,
        "parent_asset_id": f"asset:{document_id}",
        "title": title,
        "body_text": text,
        "mode": "draft_combined",
        "source_spawn_ids": ["spawn-1"],
        "doc_model": doc_model,
        "draft_sha256": digest,
    }


@pytest.fixture
def reference_app(tmp_path, monkeypatch):
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    host = InMemoryHostStore()
    engagement = InMemoryEngagementStore()
    app = FastAPI()
    app.state.marketplace_host_store = host
    app.state.engagement_store = engagement

    @app.middleware("http")
    async def test_claims(request: Request, call_next):
        account_id = request.headers.get("x-test-account", "alice")
        claims = UserClaims(
            user_id=account_id,
            email=None,
            scopes=frozenset({"private_research"}),
            issued_at="2026-07-15T00:00:00Z",
        )
        request.state.user_claims = claims
        request.state.user_id = claims.user_id
        request.state.scopes = claims.scopes
        request.state.auth_method = "test_claims"
        response = await call_next(request)
        if request.url.path.startswith("/account/html-document-refs/") or request.url.path == "/account/workspace-resume":
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(workspace_resume_router)
    return app, host, engagement


def _put_hosted(
    store: InMemoryHostStore,
    document_id: str,
    *,
    owner: str,
    title: str,
    body: str,
    state: str = "ready",
    membership: bool = True,
) -> None:
    store.put_document(
        document_id,
        {
            "document_id": document_id,
            "owner_id": owner,
            "state": state,
            "view_format": "html",
            "title": title,
            "body_text": body,
            "license_class": "private_upload",
        },
    )
    if membership:
        store.put_membership(owner, document_id)


def test_same_display_id_resolves_by_explicit_store_and_current_account(reference_app):
    app, host, engagement = reference_app
    _put_hosted(host, "same", owner="alice", title="Alice hosted", body="host bytes")
    alice = authorized_store(engagement, EngagementAuthority("alice"))
    bob = authorized_store(engagement, EngagementAuthority("bob"))
    alice.put_document("same", _doc_model_row("same", "Alice engagement", "alice draft"))
    bob.put_document("same", _doc_model_row("same", "Bob engagement", "bob draft"))

    with TestClient(app) as client:
        hosted = client.get("/account/html-document-refs/hosted_document/same")
        alice_engagement = client.get("/account/html-document-refs/engagement_document/same")
        bob_hosted = client.get(
            "/account/html-document-refs/hosted_document/same",
            headers={"x-test-account": "bob"},
        )
        bob_engagement = client.get(
            "/account/html-document-refs/engagement_document/same",
            headers={"x-test-account": "bob"},
        )

    assert hosted.status_code == 200
    assert hosted.headers["cache-control"] == "no-store"
    assert set(hosted.json()) == {
        "schema_version", "resolver", "document_id", "title", "view_format", "html"
    }
    assert hosted.json()["resolver"] == "hosted_document"
    assert "host bytes" in hosted.json()["html"]
    assert alice_engagement.status_code == 200
    assert alice_engagement.json()["resolver"] == "engagement_document"
    assert "alice draft" in alice_engagement.json()["html"]
    assert bob_hosted.status_code == 404
    assert bob_hosted.headers["cache-control"] == "no-store"
    assert bob_engagement.status_code == 200
    assert "bob draft" in bob_engagement.json()["html"]


def test_resolver_refuses_foreign_revoked_non_viewable_and_arbitrary_rows(reference_app):
    app, host, engagement = reference_app
    _put_hosted(host, "foreign", owner="bob", title="Foreign", body="private")
    _put_hosted(
        host,
        "revoked",
        owner="alice",
        title="Revoked",
        body="private",
        membership=False,
    )
    _put_hosted(
        host,
        "not-ready",
        owner="alice",
        title="Not ready",
        body="private",
        state="non_viewable",
    )
    alice = authorized_store(engagement, EngagementAuthority("alice"))
    alice.put_document(
        "receipt",
        {"document_id": "receipt", "kind": "provider_receipt", "payload": "raw provider"},
    )
    corrupt = _doc_model_row("corrupt", "Corrupt", "must not render")
    corrupt["draft_sha256"] = "0" * 64
    alice.put_document("corrupt", corrupt)
    unsupported = _doc_model_row("unsupported", "Unsupported", "must not render")
    unsupported_model = {
        "type": "doc",
        "content": [{"type": "provider_receipt", "raw": "provider secret"}],
    }
    unsupported["doc_model"] = unsupported_model
    unsupported["draft_sha256"] = hashlib.sha256(
        json.dumps(
            unsupported_model,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    alice.put_document("unsupported", unsupported)

    with TestClient(app) as client:
        responses = [
            client.get(f"/account/html-document-refs/{resolver}/{document_id}")
            for resolver, document_id in (
                ("hosted_document", "foreign"),
                ("hosted_document", "revoked"),
                ("hosted_document", "not-ready"),
                ("engagement_document", "receipt"),
                ("engagement_document", "corrupt"),
                ("engagement_document", "unsupported"),
                ("guessed_from_id", "receipt"),
            )
        ]

    assert {response.status_code for response in responses} == {404}
    assert all(response.headers["cache-control"] == "no-store" for response in responses)
    assert all("raw provider" not in response.text for response in responses)
    assert all("provider secret" not in response.text for response in responses)
    assert len({response.text for response in responses}) == 1


def test_recognized_progress_uses_existing_projector(reference_app):
    app, _, engagement = reference_app
    alice = authorized_store(engagement, EngagementAuthority("alice"))
    alice.put_spawn({"spawn_id": "progress-spawn", "parent_asset_id": "asset"})
    record_progress("progress-spawn", "plan", "Plan privately", store=alice, ts=1.0)

    with TestClient(app) as client:
        response = client.get(
            "/account/html-document-refs/engagement_document/_progress%3Aprogress-spawn"
        )

    assert response.status_code == 200
    assert response.json()["document_id"] == "_progress:progress-spawn"
    assert "Plan privately" in response.json()["html"]


def test_checkpoint_admission_filtering_and_denial_are_reference_only(reference_app):
    app, host, engagement = reference_app
    _put_hosted(host, "same", owner="alice", title="Hosted", body="host body")
    alice = authorized_store(engagement, EngagementAuthority("alice"))
    alice.put_document("same", _doc_model_row("same", "Engagement", "engagement body"))
    entries = [
        {
            "kind": "hosted_html_document",
            "resolver": "hosted_document",
            "document_id": "same",
        },
        {
            "kind": "hosted_html_document",
            "resolver": "engagement_document",
            "document_id": "same",
        },
    ]

    with TestClient(app) as client:
        synced = client.put(
            "/account/workspace-resume",
            json={
                "schema_version": 1,
                "base_revision": 0,
                "entries": entries,
                "mutation_key": "two-resolvers",
            },
        )
        leaked = client.put(
            "/account/workspace-resume",
            json={
                "schema_version": 1,
                "base_revision": 1,
                "entries": [{**entries[0], "html": "<p>must-not-enter</p>"}],
                "mutation_key": "raw-html",
            },
        )
        denied = client.put(
            "/account/workspace-resume",
            json={
                "schema_version": 1,
                "base_revision": 0,
                "entries": [
                    {
                        "kind": "hosted_html_document",
                        "resolver": "hosted_document",
                        "document_id": "missing",
                    }
                ],
                "mutation_key": "denied",
            },
            headers={"x-test-account": "bob"},
        )
        host._lib["alice"] = []
        filtered = client.get("/account/workspace-resume")

    assert synced.status_code == 200
    assert leaked.status_code == 422
    assert denied.status_code == 404
    assert denied.headers["cache-control"] == "no-store"
    assert filtered.json() == {
        "schema_version": 1,
        "revision": 1,
        "entries": [entries[1]],
    }
    stored = read_workspace_checkpoint(account_workspace_authority("alice"))
    assert stored.revision == 1
    assert len(stored.entries) == 2
    assert read_workspace_checkpoint(account_workspace_authority("bob")).revision == 0
    encoded_entries = json.dumps([entry.model_dump() for entry in stored.entries])
    assert '"html":' not in encoded_entries
    assert "must-not-enter" not in encoded_entries


def test_unavailable_store_is_503_and_no_store(reference_app):
    app, _, _ = reference_app

    class UnavailableHostStore(InMemoryHostStore):
        def get_document(self, document_id: str):
            del document_id
            raise OSError("offline")

    app.state.marketplace_host_store = UnavailableHostStore()
    with TestClient(app) as client:
        response = client.get("/account/html-document-refs/hosted_document/anything")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"


def test_corrupt_engagement_file_is_503_and_no_store(reference_app, tmp_path):
    app, _, _ = reference_app
    store = FileEngagementStore(tmp_path / "engagement")
    alice = authorized_store(store, EngagementAuthority("alice"))
    alice.put_document("corrupt-file", _doc_model_row("corrupt-file", "Title", "body"))
    [stored_path] = (tmp_path / "engagement" / "docs").glob("*.json")
    stored_path.write_text("{not-json", encoding="utf-8")
    app.state.engagement_store = store

    with TestClient(app) as client:
        response = client.get(
            "/account/html-document-refs/engagement_document/corrupt-file"
        )

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert "not-json" not in response.text


def test_corrupt_host_file_is_503_and_no_store(reference_app, tmp_path):
    app, _, _ = reference_app
    store = FileHostStore(tmp_path / "host")
    _put_hosted(store, "corrupt-file", owner="alice", title="Title", body="body")
    [stored_path] = (tmp_path / "host" / "docs").glob("*.json")
    stored_path.write_text("{not-json", encoding="utf-8")
    app.state.marketplace_host_store = store

    with TestClient(app) as client:
        response = client.get(
            "/account/html-document-refs/hosted_document/corrupt-file"
        )

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert "not-json" not in response.text


def test_host_row_swap_during_projection_is_denied_without_leak(reference_app):
    app, _, _ = reference_app

    class SwappingHostStore(InMemoryHostStore):
        reads = 0

        def get_document(self, document_id: str):
            self.reads += 1
            if self.reads == 2:
                self.put_document(
                    document_id,
                    {
                        "document_id": document_id,
                        "owner_id": "bob",
                        "state": "ready",
                        "view_format": "html",
                        "title": "Swapped secret",
                        "body_text": "swapped private bytes",
                        "license_class": "private_upload",
                    },
                )
            return super().get_document(document_id)

    store = SwappingHostStore()
    _put_hosted(store, "race", owner="alice", title="Original", body="original bytes")
    app.state.marketplace_host_store = store

    with TestClient(app) as client:
        response = client.get("/account/html-document-refs/hosted_document/race")

    assert response.status_code == 404
    assert "swapped private bytes" not in response.text
    assert "original bytes" not in response.text


def test_midnight_oil_no_spawn_deposit_is_durable_and_reference_resolvable(reference_app):
    app, _, engagement = reference_app
    job_store = InMemoryJobStore()
    alice = authorized_store(engagement, EngagementAuthority("alice"))
    job = MidnightOilJob(
        job_id="moil-no-spawn",
        goals=(),
        duration_minutes=1,
        model_id=None,
        recommended_price_ceiling_usd=0.0,
        status="complete",
        asset_id="oil-empty",
    )

    deposited = deposit_job_results(
        job.job_id,
        job_store=job_store,
        engagement_store=alice,
        job_snapshot=job,
    )
    stored = alice.get_document(deposited.document_id)
    assert stored is not None
    assert stored["mode"] == "midnight_oil_deposit"
    assert stored["source_spawn_ids"] == []
    assert stored["doc_model"]["type"] == "doc"

    with TestClient(app) as client:
        response = client.get(
            f"/account/html-document-refs/engagement_document/{deposited.document_id}"
        )

    assert response.status_code == 200
    assert response.json()["document_id"] == deposited.document_id
    assert "Midnight Oil" in response.json()["html"]


def test_real_spawned_midnight_oil_merge_shape_is_reference_resolvable(reference_app):
    app, _, engagement = reference_app
    job_store = InMemoryJobStore()
    alice = authorized_store(engagement, EngagementAuthority("alice"))
    job = MidnightOilJob(
        job_id="moil-with-spawn",
        goals=("Investigate the real merge model",),
        duration_minutes=1,
        model_id=None,
        recommended_price_ceiling_usd=0.0,
        status="complete",
        asset_id="oil-with-spawn",
    )

    deposited = deposit_job_results(
        job.job_id,
        job_store=job_store,
        engagement_store=alice,
        job_snapshot=job,
    )
    stored = alice.get_document(deposited.document_id)
    assert stored is not None
    assert stored["mode"] == "draft_combined"
    assert set(stored["doc_model"]) == {"title", "content", "edges", "meta"}

    with TestClient(app) as client:
        response = client.get(
            f"/account/html-document-refs/engagement_document/{deposited.document_id}"
        )

    assert response.status_code == 200
    assert response.json()["document_id"] == deposited.document_id
    assert "real merge model" in response.json()["html"]
