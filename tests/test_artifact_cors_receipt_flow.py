"""Authenticated artifact receipts across source changes and app reconstruction."""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read
from services.html_projection.context import RenderContext
from services.html_projection.renderer import render
from substrate.graph import ensure_initialized
from substrate.research_artifact.paths import artifact_source_path_for
from substrate.research_artifact.store import ResearchArtifactStore

ORIGIN = "https://antiek.ai"
TOKEN = "invented-receipt-operator-token"
ARTIFACT_ID = "receipt-composition"
EXPOSED = {
    "x-artifact-id",
    "x-artifact-style",
    "x-artifact-version",
    "x-content-sha256",
    "x-source-sha256",
    "x-artifact-source-state",
    "x-artifact-current-source-sha256",
    "x-document-id",
    "x-reader-revision",
    "etag",
}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source(text: str) -> bytes:
    document = {
        "title": "Receipt composition",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }
    return render(document, RenderContext()).encode("utf-8")


def _client() -> TestClient:
    return TestClient(
        create_app(
            cors_origins=[ORIGIN],
            register_wrestling=False,
            register_providers=False,
        ),
        headers={"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN},
    )


def _assert_receipt(
    response, *, version: str, source_hash: str, current_hash: str, state: str
) -> None:
    assert response.status_code == 200, response.text
    assert response.headers["x-artifact-id"] == ARTIFACT_ID
    assert response.headers["x-artifact-style"] == "antiek"
    assert response.headers["x-artifact-version"] == version
    assert response.headers["x-content-sha256"] == _digest(response.content)
    assert response.headers["x-source-sha256"] == source_hash
    assert response.headers["x-artifact-current-source-sha256"] == current_hash
    assert response.headers["x-artifact-source-state"] == state
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "origin" in {part.strip().lower() for part in response.headers["vary"].split(",")}
    exposed = {
        part.strip().lower()
        for part in response.headers["access-control-expose-headers"].split(",")
        if part.strip()
    }
    assert exposed == EXPOSED
    assert "*" not in exposed


def _resolve_schema(document: dict, node: dict) -> dict:
    ref = node.get("$ref")
    return (
        document["components"]["schemas"][ref.removeprefix("#/components/schemas/")]
        if ref
        else node
    )


def _schema_property(document: dict, model: str, field: str) -> dict:
    schemas = document["components"]["schemas"]

    def find(node: dict) -> dict | None:
        node = _resolve_schema(document, node)
        if field in node.get("properties", {}):
            return node["properties"][field]
        for branch in node.get("allOf", []):
            found = find(branch)
            if found is not None:
                return found
        return None

    result = find(schemas[model])
    assert result is not None, f"{model}.{field} is absent"
    return _resolve_schema(document, result)


def test_authenticated_artifact_version_receipts_survive_source_change_and_reopen(
    monkeypatch,
    tmp_path,
) -> None:
    db = tmp_path / "graph.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ANTIEK_OPERATOR_TOKEN", TOKEN)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(str(db))

    store = ResearchArtifactStore(str(db))
    source_a = _source("Source A records an ordinary first result.")
    hash_a = _digest(source_a)
    path_a = artifact_source_path_for(ARTIFACT_ID, hash_a)
    store.save_source(ARTIFACT_ID, "receipt-investigation", "__operator__", path_a, source_a)
    assert path_a.read_bytes() == source_a

    client = _client()
    stats = client.get("/stats")
    assert stats.status_code == 200, stats.text
    counts = stats.json()["counts"]
    assert counts["skill_rules"] == 0
    assert {
        "investigations",
        "documents",
        "chunks",
        "outcomes",
        "notebooks",
        "notebook_blocks",
        "ip_holders",
        "payout_transfers",
        "deletion_requests",
    } <= counts.keys()
    assert not any("skill_rules" in warning for warning in stats.json()["warnings"])
    with connect_read(str(db)) as con:
        assert (
            con.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name='skill_rules'"
            ).fetchone()
            is None
        )

    schema_response = client.get("/openapi.json")
    assert schema_response.status_code == 200, schema_response.text
    schema = schema_response.json()
    canonical = [
        "public_domain",
        "platform_authored",
        "publisher_opted_in",
        "source_declared_open",
        "gated_metadata_only",
        "taken_down",
        "personal_readable",
    ]
    for model in (
        "BookSummary",
        "BookDetail",
        "BookImportResponse",
        "BookHtmlPublishJobOut",
        "SpinResearchResponse",
    ):
        assert _schema_property(schema, model, "servability")["enum"] == canonical
    full_text = _schema_property(schema, "FullTextResponse", "servability")
    branches = [_resolve_schema(schema, branch) for branch in full_text["anyOf"]]
    assert len(branches) == 2
    assert [branch["enum"] for branch in branches if "enum" in branch] == [canonical]
    assert [branch["type"] for branch in branches if branch.get("type") == "null"] == ["null"]

    preview = client.get(f"/artifacts/{ARTIFACT_ID}/render")
    _assert_receipt(
        preview, version="preview", source_hash=hash_a, current_hash=hash_a, state="current"
    )
    assert store.get_version(ARTIFACT_ID, "__operator__") is None

    first = client.post(f"/artifacts/{ARTIFACT_ID}/render")
    _assert_receipt(first, version="1", source_hash=hash_a, current_hash=hash_a, state="current")
    first_body = first.content
    first_hash = _digest(first_body)
    assert store.get_version(ARTIFACT_ID, "__operator__", 1).content_hash == first_hash

    source_b = _source("Source B records a distinct later result.")
    hash_b = _digest(source_b)
    assert hash_b != hash_a
    path_b = artifact_source_path_for(ARTIFACT_ID, hash_b)
    store.save_source(ARTIFACT_ID, "receipt-investigation", "__operator__", path_b, source_b)
    assert path_b.read_bytes() == source_b

    reopened = _client()  # New app/client, same private database and artifact store.
    for suffix in ("1", "latest"):
        old = reopened.get(f"/artifacts/{ARTIFACT_ID}/versions/{suffix}")
        _assert_receipt(
            old, version="1", source_hash=hash_a, current_hash=hash_b, state="superseded"
        )
        assert old.content == first_body
        assert _digest(old.content) == first_hash

    second = reopened.post(f"/artifacts/{ARTIFACT_ID}/render")
    _assert_receipt(second, version="2", source_hash=hash_b, current_hash=hash_b, state="current")
    second_body = second.content
    second_hash = _digest(second_body)
    assert second_hash != first_hash

    persisted = ResearchArtifactStore(str(db))
    assert persisted.get_version(ARTIFACT_ID, "__operator__", 1).source_hash == hash_a
    assert persisted.get_version(ARTIFACT_ID, "__operator__", 2).source_hash == hash_b
    restarted = _client()
    latest = restarted.get(f"/artifacts/{ARTIFACT_ID}/versions/latest")
    _assert_receipt(latest, version="2", source_hash=hash_b, current_hash=hash_b, state="current")
    assert latest.content == second_body
    assert _digest(latest.content) == second_hash
    old = restarted.get(f"/artifacts/{ARTIFACT_ID}/versions/1")
    _assert_receipt(old, version="1", source_hash=hash_a, current_hash=hash_b, state="superseded")
    assert old.content == first_body

    unauthorized = TestClient(restarted.app).get(
        f"/artifacts/{ARTIFACT_ID}/versions/1",
        headers={"Origin": ORIGIN},
    )
    assert unauthorized.status_code == 401
    assert unauthorized.json() == {
        "error": {
            "message": (
                "Authentication required. One of: Antiek session cookie "
                "(sign in via /login), Cloudflare Access browser session, "
                "Cloudflare Access service token, or Authorization: "
                "Bearer <operator-token>."
            ),
            "code": "operator_auth_required",
        }
    }
    assert unauthorized.headers["access-control-allow-origin"] == ORIGIN
    assert unauthorized.headers["access-control-allow-credentials"] == "true"
    assert "origin" in {part.strip().lower() for part in unauthorized.headers["vary"].split(",")}
