"""Audit wave 4, rights-settings cluster — red-first regression tests.

C03  POST /sources/upload re-attestation: the same bytes re-uploaded under a
     different ``acquisition_attestation`` were answered 201 while the first
     ``documents.content_class`` silently survived (``on_conflict="ignore"``),
     and ``book_assets.license_basis`` was overwritten so the book record and
     the serve gate disagreed. Only the restrictive correction
     (user_owned -> personal_reading) may apply; anything else is a 409 that
     names the stored attestation and writes nothing.
C04  /settings/lineup registry: a corrupt file was laundered into 200 + empty
     assignments and a PUT then overwrote every other owner's row; the
     read-modify-write ran unlocked through one shared tmp name, so
     concurrent owner PUTs lost rows or 500'd.
C18  /books/import/publish-job accepted any ``bookserve-`` string (a
     ``blocked`` review, or a fabricated id) and mapped ``personal_license``
     to the publicly servable ``user_owned`` class.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write
from substrate.dispatch.router import reset_provider_registry
from substrate.graph import default_db_path

# ---------------------------------------------------------------------------
# C03 — upload re-attestation
# ---------------------------------------------------------------------------


@pytest.fixture
def upload_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    tmpdir = tempfile.mkdtemp(prefix="antiek-wave4-reattest-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    from substrate.graph.schema import init_database

    writer = connect_write(db_path, purpose="test/wave4-reattest/schema")
    try:
        init_database(writer)
    finally:
        writer.close()
    yield TestClient(
        create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    )


_THIRD_PARTY = b"# Third-party chapter\n\nCopyrighted text the operator only holds a copy of.\n"


def _upload(client: TestClient, body: bytes, attestation: str) -> Any:
    return client.post(
        "/sources/upload",
        files={"file": ("chapter.md", body, "text/markdown")},
        data={"acquisition_attestation": attestation},
    )


def _upload_rights_state(document_id: str) -> tuple[str, str, str]:
    con = connect_read(default_db_path())
    try:
        row = con.execute(
            "SELECT d.content_class, d.metadata, b.license_basis FROM documents d "
            "JOIN book_assets b USING (document_id) WHERE d.document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    metadata = row[1] if isinstance(row[1], dict) else json.loads(row[1])
    return str(row[0]), str(metadata["acquisition_attestation"]), str(row[2])


def test_c03_reupload_as_personal_reading_downgrades_the_served_class(
    upload_client: TestClient,
) -> None:
    first = _upload(upload_client, _THIRD_PARTY, "user_owned")
    assert first.status_code == 201, first.text
    document_id = first.json()["document_id"]
    assert upload_client.get(f"/books/{document_id}/full-text").json()["servable"] is True

    second = _upload(upload_client, _THIRD_PARTY, "personal_reading")

    assert second.status_code == 201, second.text
    assert second.json()["document_id"] == document_id
    assert _upload_rights_state(document_id) == (
        "personal_reading",
        "personal_reading",
        "personal_reading",
    )
    assert second.json()["content_class"] == "personal_reading"
    served = upload_client.get(f"/books/{document_id}/full-text").json()
    assert served["servable"] is False
    assert served["ad_eligible"] is False
    assert not served.get("full_text")


def test_c03_reupload_cannot_upgrade_personal_reading_to_user_owned(
    upload_client: TestClient,
) -> None:
    first = _upload(upload_client, _THIRD_PARTY, "personal_reading")
    assert first.status_code == 201, first.text
    document_id = first.json()["document_id"]

    second = _upload(upload_client, _THIRD_PARTY, "user_owned")

    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert detail["code"] == "upload_attestation_conflict"
    assert detail["stored_attestation"] == "personal_reading"
    assert detail["document_id"] == document_id
    # Nothing was written: the book record still agrees with the gate.
    assert _upload_rights_state(document_id) == (
        "personal_reading",
        "personal_reading",
        "personal_reading",
    )


def test_c03_same_attestation_reupload_stays_idempotent_and_reports_class(
    upload_client: TestClient,
) -> None:
    first = _upload(upload_client, _THIRD_PARTY, "user_owned")
    second = _upload(upload_client, _THIRD_PARTY, "user_owned")
    assert first.status_code == second.status_code == 201
    assert first.json()["content_class"] == second.json()["content_class"] == "user_owned"
    assert _upload_rights_state(first.json()["document_id"]) == (
        "user_owned",
        "user_owned",
        "user_owned",
    )


# ---------------------------------------------------------------------------
# C04 — lineup registry integrity + serialized read-modify-write
# ---------------------------------------------------------------------------


@pytest.fixture
def lineup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv(
        "ANTIEK_USER_MODELS_PATH", str(tmp_path / "settings" / "user_models.json")
    )
    monkeypatch.setenv("ANTIEK_BYOK_ARTIFACT", str(tmp_path / "byok" / "credentials.enc"))
    monkeypatch.setenv("ANTIEK_BYOK_KEY_FILE", str(tmp_path / "byok" / "master.key"))
    path = tmp_path / "settings" / "lineup.json"
    monkeypatch.setenv("ANTIEK_LINEUP_PATH", str(path))
    reset_provider_registry()
    yield path
    reset_provider_registry()


def _lineup_app() -> FastAPI:
    from interfaces.research.api.settings_budget import register_settings_budget_routes
    from interfaces.research.api.settings_lineup import register_settings_lineup_routes

    app = FastAPI()
    register_settings_budget_routes(app)
    register_settings_lineup_routes(app)

    @app.middleware("http")
    async def _identity(request: Request, call_next: Any) -> Any:
        # A header names another owner. Without one the request is the verified
        # operator session, whose owner #3382 derives from its e-mail; the bare
        # "__operator__" sentinel names nobody and is refused (401).
        other = request.headers.get("x-test-owner")
        request.state.user_id = other or "__operator__"
        request.state.user_email = None if other else _OPERATOR_EMAIL
        request.state.auth_method = "antiek_session_cookie"
        return await call_next(request)

    return app


_OPERATOR_EMAIL = "operator@localhost"


def _operator_owner() -> str:
    from interfaces.research.api.account_memory_identity import (
        derive_owner_from_verified_email,
    )

    owner = derive_owner_from_verified_email(_OPERATOR_EMAIL)
    assert owner is not None
    return owner


def _role_id() -> str:
    from interfaces.research.api.settings_lineup import ROLE_BY_ID

    return next(iter(ROLE_BY_ID))


def _seed(path: Path) -> dict[str, Any]:
    role = _role_id()
    seed = {
        "owners": {
            _operator_owner(): {
                "general": {role: {"provider_id": "p", "model_id": "m"}},
                "advanced": {},
                "updated_at": "x",
            },
            "owner-b": {
                "general": {role: {"provider_id": "pb", "model_id": "mb"}},
                "advanced": {},
                "updated_at": "y",
            },
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seed), encoding="utf-8")
    return seed


@pytest.mark.parametrize(
    "corrupt",
    ["TRUNCATE", "[]", '{"owners": []}', '{"owners": {"owner-b": "nope"}}'],
)
def test_c04_unreadable_lineup_registry_is_a_typed_503_not_empty_200(
    lineup_env: Path, corrupt: str
) -> None:
    seed = _seed(lineup_env)
    bad = json.dumps(seed)[:-3] if corrupt == "TRUNCATE" else corrupt
    lineup_env.write_text(bad, encoding="utf-8")
    client = TestClient(_lineup_app())

    got = client.get("/settings/lineup", headers={"x-test-owner": "owner-b"})
    assert got.status_code == 503, got.text
    assert got.json()["detail"] == "lineup_registry_unreadable"

    put = client.put("/settings/lineup", json={"general": {_role_id(): None}, "advanced": {}})
    assert put.status_code == 503, put.text
    assert put.json()["detail"] == "lineup_registry_unreadable"
    # The corrupt bytes are preserved for operator recovery, never overwritten.
    assert lineup_env.read_text(encoding="utf-8") == bad


def test_c04_concurrent_owner_puts_all_persist(lineup_env: Path) -> None:
    lineup_env.parent.mkdir(parents=True, exist_ok=True)
    lineup_env.write_text(json.dumps({"owners": {}}), encoding="utf-8")
    client = TestClient(_lineup_app())
    owners = [f"owner-{i:02d}" for i in range(24)]
    start = threading.Barrier(len(owners))
    statuses: dict[str, int] = {}

    def put(owner: str) -> None:
        start.wait(timeout=10)
        resp = client.put(
            "/settings/lineup",
            json={"general": {_role_id(): None}, "advanced": {}},
            headers={"x-test-owner": owner},
        )
        statuses[owner] = resp.status_code

    threads = [threading.Thread(target=put, args=(o,)) for o in owners]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert statuses == {o: 200 for o in owners}
    persisted = json.loads(lineup_env.read_text(encoding="utf-8"))["owners"]
    assert sorted(persisted) == owners
    assert not [p for p in lineup_env.parent.iterdir() if p.name.endswith(".tmp")]


def test_c04_valid_registry_still_round_trips_other_owners(lineup_env: Path) -> None:
    _seed(lineup_env)
    client = TestClient(_lineup_app())
    got = client.get("/settings/lineup", headers={"x-test-owner": "owner-b"})
    assert got.status_code == 200
    assert got.json()["assignments"]["general"][_role_id()] == {
        "provider_id": "pb",
        "model_id": "mb",
    }
    put = client.put("/settings/lineup", json={"general": {_role_id(): None}, "advanced": {}})
    assert put.status_code == 200, put.text
    persisted = json.loads(lineup_env.read_text(encoding="utf-8"))["owners"]
    assert sorted(persisted) == sorted([_operator_owner(), "owner-b"])


# ---------------------------------------------------------------------------
# C18 — publish-job must consult the recorded serve-gate review
# ---------------------------------------------------------------------------


def _books_client() -> TestClient:
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def _review(
    client: TestClient,
    *,
    rights_basis: str,
    decision: str,
    conversion_result_id: str = "bookout-wave4",
) -> Any:
    return client.post(
        "/books/import/serve-gate-review",
        json={
            "conversion_result_id": conversion_result_id,
            "title": "A Held Book",
            "rights_basis": rights_basis,
            "servability_decision": decision,
            "acknowledge_rights_reviewed": True,
            "acknowledge_no_publication": True,
        },
    )


def _publication(
    client: TestClient,
    review_id: str,
    conversion_result_id: str = "bookout-wave4",
) -> Any:
    return client.post(
        "/books/import/publication-request",
        json={
            "serve_gate_review_id": review_id,
            "conversion_result_id": conversion_result_id,
            "shelf_visibility": "private_library",
            "acknowledge_publication_intent": True,
            "acknowledge_no_ingest_or_serve": True,
        },
    )


def _publish(
    client: TestClient,
    *,
    publication_request_id: str,
    review_id: str,
    document_id: str,
    rights_basis: str,
) -> Any:
    return client.post(
        "/books/import/publish-job",
        json={
            "publication_request_id": publication_request_id,
            "serve_gate_review_id": review_id,
            "document_id": document_id,
            "title": "A Held Book",
            "html_body": "<article><h1>Held</h1><p>Third-party prose.</p></article>",
            "rights_basis": rights_basis,
            "license_basis": "Operator-held copy.",
            "acknowledge_write_to_library": True,
            "acknowledge_full_text_servable": True,
        },
    )


def _document_exists(document_id: str) -> bool:
    con = connect_read(default_db_path())
    try:
        return (
            con.execute(
                "SELECT 1 FROM documents WHERE document_id = ?", [document_id]
            ).fetchone()
            is not None
        )
    finally:
        con.close()


def test_c18_blocked_review_cannot_publish() -> None:
    client = _books_client()
    review = _review(client, rights_basis="personal_license", decision="blocked")
    assert review.status_code == 202 and review.json()["status"] == "blocked"
    review_id = review.json()["serve_gate_review_id"]

    # The publication request itself refuses a blocked review ...
    pub = _publication(client, review_id)
    assert pub.status_code == 409, pub.text
    assert pub.json()["detail"] == "serve_gate_review_blocked"

    # ... and publish-job refuses it even with a well-formed request id.
    resp = _publish(
        client,
        publication_request_id="bookpub-forged",
        review_id=review_id,
        document_id="doc-wave4-blocked",
        rights_basis="personal_license",
    )
    assert resp.status_code == 409, resp.text
    assert not _document_exists("doc-wave4-blocked")


def test_c18_fabricated_review_and_request_ids_cannot_publish() -> None:
    client = _books_client()
    pub = _publication(client, "bookserve-FABRICATED")
    assert pub.status_code == 409, pub.text
    assert pub.json()["detail"] == "serve_gate_review_not_found"

    resp = _publish(
        client,
        publication_request_id="bookpub-FABRICATED",
        review_id="bookserve-FABRICATED",
        document_id="doc-wave4-fabricated",
        rights_basis="public_domain",
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "publication_request_not_found"
    assert not _document_exists("doc-wave4-fabricated")


def test_c18_publish_rights_basis_must_match_the_review() -> None:
    client = _books_client()
    review_id = _review(
        client, rights_basis="personal_license", decision="servable_full_text"
    ).json()["serve_gate_review_id"]
    pub_id = _publication(client, review_id).json()["publication_request_id"]

    resp = _publish(
        client,
        publication_request_id=pub_id,
        review_id=review_id,
        document_id="doc-wave4-upgrade",
        rights_basis="public_domain",
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "rights_basis_differs_from_review"
    assert not _document_exists("doc-wave4-upgrade")


def test_c18_publication_request_must_belong_to_the_review() -> None:
    client = _books_client()
    review_a = _review(
        client, rights_basis="personal_license", decision="servable_full_text"
    ).json()["serve_gate_review_id"]
    review_b = _review(
        client,
        rights_basis="personal_license",
        decision="servable_full_text",
        conversion_result_id="bookout-other",
    ).json()["serve_gate_review_id"]
    pub_a = _publication(client, review_a).json()["publication_request_id"]

    resp = _publish(
        client,
        publication_request_id=pub_a,
        review_id=review_b,
        document_id="doc-wave4-crossed",
        rights_basis="personal_license",
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "publication_request_review_mismatch"


def test_c18_personal_license_publishes_owner_only_not_publicly_servable() -> None:
    client = _books_client()
    review_id = _review(
        client, rights_basis="personal_license", decision="servable_full_text"
    ).json()["serve_gate_review_id"]
    pub = _publication(client, review_id)
    assert pub.status_code == 202, pub.text

    resp = _publish(
        client,
        publication_request_id=pub.json()["publication_request_id"],
        review_id=review_id,
        document_id="doc-wave4-personal",
        rights_basis="personal_license",
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["content_class"] == "personal_reading"
    assert resp.json()["servable_full_text"] is False

    served = client.get("/books/doc-wave4-personal/full-text").json()
    assert served["servable"] is False
    assert served["ad_eligible"] is False
    assert not served.get("full_text")


def test_c18_unknown_rights_review_publishes_only_as_personal_license() -> None:
    """The Library UI maps a reviewed ``unknown`` basis to ``personal_license``
    at publish time; that (owner-only) narrowing is the one admitted mismatch."""
    client = _books_client()
    review_id = _review(
        client, rights_basis="unknown", decision="servable_full_text"
    ).json()["serve_gate_review_id"]
    pub_id = _publication(client, review_id).json()["publication_request_id"]

    upgraded = _publish(
        client,
        publication_request_id=pub_id,
        review_id=review_id,
        document_id="doc-wave4-unknown-up",
        rights_basis="platform_authored",
    )
    assert upgraded.status_code == 409, upgraded.text

    narrowed = _publish(
        client,
        publication_request_id=pub_id,
        review_id=review_id,
        document_id="doc-wave4-unknown",
        rights_basis="personal_license",
    )
    assert narrowed.status_code == 201, narrowed.text
    assert narrowed.json()["content_class"] == "personal_reading"
