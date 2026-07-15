from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.merge_asset_routes import (
    get_merge_draft_repository,
    merge_asset_router,
    register_merge_asset_routes,
)
from runtime.db_lock import connect_write
from substrate.contracts.html_projection import HtmlProjectionContract, derive_projection_id
from substrate.graph.schema import init_database_at_path
from substrate.research_artifact.merge_draft import MergeDraftRepository


@pytest.fixture  # type: ignore[untyped-decorator]
def fixture(tmp_path: Path) -> Iterator[tuple[TestClient, MergeDraftRepository, str, Path, str]]:
    db_path = str(tmp_path / "graph.duckdb")
    root = tmp_path / "objects"
    root.mkdir()
    init_database_at_path(db_path)
    body = b'<article><h1 id="top">Ready</h1><a href="#top">up</a></article>'
    object_path = root / "ready.html"
    object_path.write_bytes(body)
    identity = {
        "source_asset_id": "source-a",
        "source_document_id": "document-a",
        "source_sha256": "a" * 64,
        "converter_id": "converter",
        "converter_version": "1",
        "sanitizer_policy": "projection-policy",
        "sanitizer_version": "7",
    }
    projection_id = derive_projection_id(**identity)
    projection = HtmlProjectionContract.model_validate(
        {
            **identity,
            "projection_id": projection_id,
            "status": "ready",
            "hosted_html_locator": "ready.html",
            "hosted_html_sha256": hashlib.sha256(body).hexdigest(),
        }
    )
    with connect_write(db_path, purpose="merge-route-fixture") as con:
        con.execute(
            "INSERT INTO documents "
            "(document_id, source_tier, document_type, owner_user_id) VALUES (?, 1, ?, ?)",
            ["document-a", "html", "owner-a"],
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS html_projections "
            "(projection_id TEXT PRIMARY KEY, identity_json JSON NOT NULL UNIQUE, "
            "projection_json JSON NOT NULL)"
        )
        con.execute(
            "INSERT INTO html_projections VALUES (?, ?, ?)",
            [projection_id, json.dumps(identity), projection.model_dump_json()],
        )
    repository = MergeDraftRepository(db_path=db_path, projection_root=root)
    app = FastAPI()

    @app.middleware("http")
    async def auth(request: Request, call_next: object) -> object:
        request.state.user_id = request.headers.get("x-owner", "owner-a")
        request.state.auth_method = "bearer_token"
        return await call_next(request)  # type: ignore[operator]

    app.include_router(merge_asset_router)
    app.dependency_overrides[get_merge_draft_repository] = lambda: repository
    with TestClient(app) as client:
        yield client, repository, db_path, object_path, projection_id


def payload(projection_id: str) -> dict[str, object]:
    return {
        "projection_ids": [projection_id],
        "intent": "create",
        "title": "Draft",
        "asset_kind": "analysis",
    }


def test_id_only_draft_review_and_inert_preview(
    fixture: tuple[TestClient, MergeDraftRepository, str, Path, str],
) -> None:
    client, _repository, db_path, object_path, projection_id = fixture
    created = client.post("/research/derived-assets/merge/drafts", json=payload(projection_id))
    assert created.status_code == 201
    draft = created.json()
    assert draft["draft_id"].startswith("drf_") and len(draft["draft_id"]) == 36
    assert set(draft) == {
        "draft_id",
        "canonical_sha256",
        "manifest_sha256",
        "sanitizer_policy",
        "sanitizer_version",
    }
    reviewed = client.post(f"/research/derived-assets/merge/drafts/{draft['draft_id']}/reviews")
    assert reviewed.status_code == 201
    review = reviewed.json()
    assert review["review_id"].startswith("rvw_") and len(review["review_id"]) == 36
    object_path.write_text("<p>post-review drift</p>")
    assert (
        client.post(f"/research/derived-assets/merge/drafts/{draft['draft_id']}/reviews").json()
        == review
    )
    preview = client.get(f"/research/derived-assets/merge/previews/{review['review_id']}")
    assert preview.status_code == 200
    assert preview.headers["content-security-policy"] == (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; sandbox"
    )
    assert preview.headers["x-content-type-options"] == "nosniff"
    assert preview.headers["x-frame-options"] == "DENY"
    assert "ready.html" not in preview.text and str(Path(db_path).parent) not in preview.text
    with duckdb.connect(db_path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM derived_assets").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM derived_asset_revisions").fetchone() == (0,)


def test_unknown_fields_reject_browser_authority_before_storage(
    fixture: tuple[TestClient, MergeDraftRepository, str, Path, str],
) -> None:
    client, _repository, _db_path, _object_path, projection_id = fixture
    for forbidden in ("path", "locator", "owner", "commit", "receipt", "authority"):
        response = client.post(
            "/research/derived-assets/merge/drafts",
            json={**payload(projection_id), forbidden: "/tmp/evil"},
        )
        assert response.status_code == 422


def test_owner_scope_is_indistinguishable_404(
    fixture: tuple[TestClient, MergeDraftRepository, str, Path, str],
) -> None:
    client, _repository, _db_path, _object_path, projection_id = fixture
    draft_id = client.post(
        "/research/derived-assets/merge/drafts", json=payload(projection_id)
    ).json()["draft_id"]
    assert (
        client.get(
            f"/research/derived-assets/merge/previews/{draft_id}", headers={"x-owner": "owner-b"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/research/derived-assets/merge/drafts",
            json=payload(projection_id),
            headers={"x-owner": "owner-b"},
        ).status_code
        == 409
    )
    assert (
        client.get(
            "/research/derived-assets/merge/previews/drf_00000000000000000000000000000000"
        ).status_code
        == 404
    )


def test_projection_file_drift_and_symlink_refuse_review_without_partial_row(
    fixture: tuple[TestClient, MergeDraftRepository, str, Path, str], tmp_path: Path
) -> None:
    client, _repository, db_path, object_path, projection_id = fixture
    draft_id = client.post(
        "/research/derived-assets/merge/drafts", json=payload(projection_id)
    ).json()["draft_id"]
    object_path.write_text("<p>drift</p>")
    response = client.post(f"/research/derived-assets/merge/drafts/{draft_id}/reviews")
    assert response.status_code == 409
    with duckdb.connect(db_path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM derived_asset_merge_reviews").fetchone() == (0,)
    object_path.unlink()
    target = tmp_path / "outside.html"
    target.write_text("<p>outside</p>")
    object_path.symlink_to(target)
    assert (
        client.post(
            "/research/derived-assets/merge/drafts", json=payload(projection_id)
        ).status_code
        == 409
    )


def test_revise_intent_requires_owned_exact_current_parent(
    fixture: tuple[TestClient, MergeDraftRepository, str, Path, str],
) -> None:
    client, _repository, db_path, _object_path, projection_id = fixture
    revise = {
        **payload(projection_id),
        "intent": "revise",
        "target_asset_id": "asset-a",
        "expected_parent_revision_id": "rev-a",
        "expected_parent_sha256": "b" * 64,
    }
    assert client.post("/research/derived-assets/merge/drafts", json=revise).status_code == 409
    body = "<article>parent</article>"
    body_hash = hashlib.sha256(body.encode()).hexdigest()
    manifest = "[]"
    manifest_hash = hashlib.sha256(manifest.encode()).hexdigest()
    with connect_write(db_path, purpose="merge-target-fixture") as con:
        con.execute(
            "INSERT INTO derived_assets "
            "(derived_asset_id, title, asset_kind, owner_user_id) VALUES (?, ?, ?, ?)",
            ["asset-a", "Owned", "analysis", "owner-a"],
        )
        con.execute(
            "INSERT INTO derived_asset_revisions "
            "(derived_asset_id, revision_id, operation_kind, canonical_html, "
            "canonical_byte_count, content_sha256, manifest_json, manifest_sha256, "
            "sanitizer_policy, sanitizer_version, review_id, acknowledgement_version) "
            "VALUES (?, ?, 'create', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "asset-a",
                "rev-a",
                body,
                len(body.encode()),
                body_hash,
                manifest,
                manifest_hash,
                "policy",
                "1",
                "prior-review",
                "ack-1",
            ],
        )
        con.execute(
            "INSERT INTO derived_asset_current_revisions "
            "(derived_asset_id, current_revision_id, current_content_sha256, generation) "
            "VALUES (?, ?, ?, 1)",
            ["asset-a", "rev-a", body_hash],
        )
    assert client.post("/research/derived-assets/merge/drafts", json=revise).status_code == 409
    revise["expected_parent_sha256"] = body_hash
    drafted = client.post("/research/derived-assets/merge/drafts", json=revise)
    assert drafted.status_code == 201
    assert (
        client.post(
            "/research/derived-assets/merge/drafts",
            json=revise,
            headers={"x-owner": "owner-b"},
        ).status_code
        == 409
    )
    next_body = "<article>next parent</article>"
    next_hash = hashlib.sha256(next_body.encode()).hexdigest()
    with connect_write(db_path, purpose="merge-parent-drift-fixture") as con:
        con.execute(
            "INSERT INTO derived_asset_revisions "
            "(derived_asset_id, revision_id, operation_kind, canonical_html, "
            "canonical_byte_count, content_sha256, manifest_json, manifest_sha256, "
            "sanitizer_policy, sanitizer_version, review_id, acknowledgement_version, "
            "parent_revision_id) VALUES (?, ?, 'revise', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "asset-a",
                "rev-b",
                next_body,
                len(next_body.encode()),
                next_hash,
                manifest,
                manifest_hash,
                "policy",
                "1",
                "next-review",
                "ack-1",
                "rev-a",
            ],
        )
        con.execute(
            "UPDATE derived_asset_current_revisions SET current_revision_id=?, "
            "current_content_sha256=?, generation=2 WHERE derived_asset_id=?",
            ["rev-b", next_hash, "asset-a"],
        )
    assert (
        client.post(
            f"/research/derived-assets/merge/drafts/{drafted.json()['draft_id']}/reviews"
        ).status_code
        == 409
    )


def test_schema_has_v17_tables_without_route_time_ddl(
    fixture: tuple[TestClient, MergeDraftRepository, str, Path, str],
) -> None:
    _client, _repository, db_path, _object_path, _projection_id = fixture
    with duckdb.connect(db_path, read_only=True) as con:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    assert {
        "html_projections",
        "derived_asset_merge_drafts",
        "derived_asset_merge_reviews",
    } <= tables
    route_source = Path("interfaces/research/api/merge_asset_routes.py").read_text()
    assert "CREATE TABLE" not in route_source.upper()


def test_projection_open_race_returns_controlled_conflict(
    fixture: tuple[TestClient, MergeDraftRepository, str, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _repository, _db_path, _object_path, projection_id = fixture

    def fail_open(*_args: object, **_kwargs: object) -> int:
        raise FileNotFoundError("raced")

    monkeypatch.setattr("substrate.research_artifact.merge_draft.os.open", fail_open)
    response = client.post("/research/derived-assets/merge/drafts", json=payload(projection_id))
    assert response.status_code == 409
    assert response.json() == {"detail": "projection object is unavailable"}


def test_registered_app_applies_v17_at_startup_not_request_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "startup.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    app = FastAPI()
    register_merge_asset_routes(app)
    assert not db_path.exists()
    with TestClient(app):
        assert db_path.exists()
    with duckdb.connect(str(db_path), read_only=True) as con:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    assert {"derived_asset_merge_drafts", "derived_asset_merge_reviews"} <= tables
