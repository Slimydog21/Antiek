from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import engagement_routes as routes
from interfaces.research.api.engagement_routes import register_engagement_routes
from interfaces.research.api.substack_authorization_dependencies import (
    SubstackAuthorizationApiDependencies,
    build_substack_authorization_dependencies,
)
from substrate.engagement_spine.store import FileEngagementStore

_KEY = b"s" * 32


def _app(*, owner: str = "alice", configured: bool = True) -> TestClient:
    routes.reset_engagement_stores()
    app = FastAPI()

    @app.middleware("http")
    async def auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = owner
        return await call_next(request)

    dependencies = None
    if configured:
        dependencies = SubstackAuthorizationApiDependencies(
            engagement_store=routes._eng(),
            active_key_id="substack-review-2026-07",
            signing_key=_KEY,
            verification_keys={"substack-review-2026-07": _KEY},
            clock_ms=lambda: 1_000,
            token_hex=lambda size: "1" * (size * 2),
            test_mode=True,
        )
    register_engagement_routes(app, substack_authorization_dependencies=dependencies)
    return TestClient(app)


def _confirmed_collective(client: TestClient) -> tuple[str, str, str]:
    opened = client.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "private-reading",
            "selection_text": "Investigate this post",
            "references": ["https://antiek.substack.com/p/research-workstations"],
        },
    )
    assert opened.status_code == 200, opened.text
    request = {
        "session_ids": [opened.json()["session_id"]],
        "include_twin_preview": False,
        "include_prompt_block": True,
        "include_html": True,
    }
    preview = client.post("/engagement/sessions/collective", json=request)
    assert preview.status_code == 200, preview.text
    preview_sha = preview.json()["collective_preview_sha256"]
    confirmed = client.post(
        "/engagement/sessions/collective/confirm",
        json={
            **request,
            "expected_preview_sha256": preview_sha,
            "idempotency_key": "collective-review-source-001",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    ref = confirmed.json()["material"]["unit"]["source_references"][0]
    return confirmed.json()["collective_unit_id"], preview_sha, ref["ref_id"]


def _review_body(preview_sha: str, ref_id: str) -> dict[str, object]:
    return {
        "expected_collective_preview_sha256": preview_sha,
        "ref_id": ref_id,
        "selection_text": 'A & B — "owner private".',
        "source_representation_sha256": "c" * 64,
        "source_representation_bytes": 10_000,
        "source_byte_start": 100,
        "authorization_lifetime_minutes": 30,
        "owner_affirms_lawful_access": True,
        "owner_affirms_provider_processing": True,
        "partial_excerpt_affirmed": True,
        "redistribution_authorized": False,
        "training_authorized": False,
        "publication_authorized": False,
        "idempotency_key": "substack-review-request-001",
    }


def test_review_and_confirm_are_owner_private_escaped_and_execution_disabled() -> None:
    client = _app()
    unit_id, preview_sha, ref_id = _confirmed_collective(client)
    review = client.post(
        f"/engagement/sessions/collective/{unit_id}/substack-excerpts/review",
        json=_review_body(preview_sha, ref_id),
    )
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["publication_execution_enabled"] is False
    assert "html" not in body
    assert body["selection_text"] == 'A & B — "owner private".'
    assert "signature_sha256" not in review.text
    assert "key_id" not in review.text
    confirm = client.post(
        f"/engagement/sessions/collective/{unit_id}/substack-excerpts/confirm",
        json={
            "review_id": body["review_id"],
            "expected_review_preview_sha256": body["review_preview_sha256"],
            "idempotency_key": "substack-review-confirm-001",
        },
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["execution_ready"] is False
    assert confirm.json()["requires_manifest_v2"] is True
    assert "signature_sha256" not in confirm.text
    detail = client.get(f"/engagement/sessions/collective/{unit_id}")
    assert detail.status_code == 200
    assert len(detail.json()["substack_excerpt_reviews"]) == 1
    saved_review = detail.json()["substack_excerpt_reviews"][0]
    assert "selection_text" not in saved_review
    assert saved_review["authorization_state"] == "active"
    assert saved_review["execution_ready"] is False
    original = routes._eng().get_owned_document(unit_id, "alice")
    assert original is not None and original["preview_sha256"] == preview_sha


def test_review_fails_closed_without_signer_or_for_stale_and_foreign_authority() -> None:
    client = _app(configured=False)
    unit_id, preview_sha, ref_id = _confirmed_collective(client)
    unavailable = client.post(
        f"/engagement/sessions/collective/{unit_id}/substack-excerpts/review",
        json=_review_body(preview_sha, ref_id),
    )
    assert unavailable.status_code == 503

    client = _app()
    unit_id, preview_sha, ref_id = _confirmed_collective(client)
    stale = client.post(
        f"/engagement/sessions/collective/{unit_id}/substack-excerpts/review",
        json=_review_body("0" * 64, ref_id),
    )
    assert stale.status_code == 409
    absent = client.post(
        f"/engagement/sessions/collective/{unit_id}/substack-excerpts/review",
        json=_review_body(preview_sha, "sref_" + "0" * 16),
    )
    assert absent.status_code == 404
    foreign_id = "cunit_" + hashlib.sha256(b"foreign").hexdigest()[:24]
    foreign = client.post(
        f"/engagement/sessions/collective/{foreign_id}/substack-excerpts/review",
        json=_review_body(preview_sha, ref_id),
    )
    assert foreign.status_code == 404


def test_review_raw_json_rejects_duplicates_and_independent_false_affirmations() -> None:
    client = _app()
    unit_id, preview_sha, ref_id = _confirmed_collective(client)
    body = _review_body(preview_sha, ref_id)
    encoded = json.dumps(body)
    duplicate = encoded.replace(
        '"owner_affirms_lawful_access": true',
        '"owner_affirms_lawful_access": false, "owner_affirms_lawful_access": true',
    )
    response = client.post(
        f"/engagement/sessions/collective/{unit_id}/substack-excerpts/review",
        content=duplicate,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    for field in ("owner_affirms_lawful_access", "owner_affirms_provider_processing"):
        changed = {**body, field: False, "idempotency_key": f"different-{field}"}
        response = client.post(
            f"/engagement/sessions/collective/{unit_id}/substack-excerpts/review",
            json=changed,
        )
        assert response.status_code == 422

    oversized = client.post(
        f"/engagement/sessions/collective/{unit_id}/substack-excerpts/review",
        content=b"{" + b" " * 65_536,
        headers={"content-type": "application/json"},
    )
    assert oversized.status_code == 413
    invalid_utf8 = client.post(
        f"/engagement/sessions/collective/{unit_id}/substack-excerpts/review",
        content=b"\xff",
        headers={"content-type": "application/json"},
    )
    assert invalid_utf8.status_code == 400


def test_review_is_unavailable_to_a_different_authenticated_owner() -> None:
    alice = _app()
    unit_id, preview_sha, ref_id = _confirmed_collective(alice)
    dependencies = alice.app.state.substack_authorization_dependencies
    bob_app = FastAPI()

    @bob_app.middleware("http")
    async def bob_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = "bob"
        return await call_next(request)

    register_engagement_routes(
        bob_app,
        substack_authorization_dependencies=dependencies,
    )
    bob = TestClient(bob_app)
    response = bob.post(
        f"/engagement/sessions/collective/{unit_id}/substack-excerpts/review",
        json=_review_body(preview_sha, ref_id),
    )
    assert response.status_code == 404


def test_collective_reload_repairs_an_abandoned_capacity_reservation() -> None:
    client = _app()
    unit_id, preview_sha, ref_id = _confirmed_collective(client)
    reviewed = client.post(
        f"/engagement/sessions/collective/{unit_id}/substack-excerpts/review",
        json=_review_body(preview_sha, ref_id),
    )
    assert reviewed.status_code == 200
    store = routes._eng()
    original_mutate = store.mutate_owned_document
    armed = True

    def crash_after_reservation(logical_id: str, owner_id: str, mutation: Any) -> dict[str, Any]:
        nonlocal armed
        result = original_mutate(logical_id, owner_id, mutation)
        if armed and logical_id.startswith("csubidx_") and result.get("reservation_ids"):
            armed = False
            raise RuntimeError("simulated process loss after reservation")
        return result

    store.mutate_owned_document = crash_after_reservation  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="process loss"):
        client.post(
            f"/engagement/sessions/collective/{unit_id}/substack-excerpts/confirm",
            json={
                "review_id": reviewed.json()["review_id"],
                "expected_review_preview_sha256": reviewed.json()["review_preview_sha256"],
                "idempotency_key": "reload-lost-confirm-key-001",
            },
        )
    store.mutate_owned_document = original_mutate  # type: ignore[method-assign]

    fresh_app = FastAPI()

    @fresh_app.middleware("http")
    async def fresh_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = "alice"
        return await call_next(request)

    register_engagement_routes(
        fresh_app,
        substack_authorization_dependencies=client.app.state.substack_authorization_dependencies,
    )
    reloaded = TestClient(fresh_app).get(f"/engagement/sessions/collective/{unit_id}")
    assert reloaded.status_code == 200, reloaded.text
    assert reloaded.json()["pending_substack_excerpt_review_count"] == 0
    assert len(reloaded.json()["substack_excerpt_reviews"]) == 1


def test_production_dependency_loader_is_all_or_none_and_forbids_consent_key_reuse(
    tmp_path: Path,
) -> None:
    store = FileEngagementStore(tmp_path / "engagement")
    key = base64.urlsafe_b64encode(b"p" * 32).decode().rstrip("=")
    environment = {
        "ANTIEK_SUBSTACK_AUTH_ACTIVE_KEY_ID": "substack-2026-07",
        "ANTIEK_SUBSTACK_AUTH_SIGNING_KEY_ENV": "SUBSTACK_PRIVATE_KEY",
        "ANTIEK_SUBSTACK_AUTH_VERIFICATION_KEY_ENVS_JSON": json.dumps(
            {"substack-2026-07": "SUBSTACK_PRIVATE_KEY"}
        ),
        "SUBSTACK_PRIVATE_KEY": key,
    }
    dependencies = build_substack_authorization_dependencies(
        engagement_store=store,
        environ=environment,
    )
    assert dependencies is not None
    assert dependencies.engagement_store is store
    assert dependencies.signing_key == b"p" * 32
    assert build_substack_authorization_dependencies(engagement_store=store, environ={}) is None
    with pytest.raises(ValueError, match="incomplete"):
        build_substack_authorization_dependencies(
            engagement_store=store,
            environ={"ANTIEK_SUBSTACK_AUTH_ACTIVE_KEY_ID": "substack-2026-07"},
        )
    with pytest.raises(ValueError, match="must not reuse consent"):
        build_substack_authorization_dependencies(
            engagement_store=store,
            environ=environment,
            forbidden_key_envs=frozenset({"SUBSTACK_PRIVATE_KEY"}),
        )
    aliased = {**environment, "SUBSTACK_PRIVATE_KEY": key}
    with pytest.raises(ValueError, match="key material"):
        build_substack_authorization_dependencies(
            engagement_store=store,
            environ=aliased,
            forbidden_keys=(b"p" * 32,),
        )
    with pytest.raises(ValueError, match="duplicate keys"):
        build_substack_authorization_dependencies(
            engagement_store=store,
            environ={
                **environment,
                "ANTIEK_SUBSTACK_AUTH_VERIFICATION_KEY_ENVS_JSON": (
                    '{"substack-2026-07":"SUBSTACK_PRIVATE_KEY",'
                    '"substack-2026-07":"SUBSTACK_PRIVATE_KEY"}'
                ),
            },
        )
