from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.midnight_oil_routes import register_midnight_oil_routes
from interfaces.research.api.midnight_oil_runtime import (
    build_midnight_oil_api_runtime,
    create_midnight_oil_production_app,
)
from runtime.db_lock import connect_read, connect_write
from substrate.dispatch import (
    DispatchConfig,
    NormalizedUsage,
    ProviderError,
    RawProviderResponse,
    get_provider,
    register_provider,
    reset_provider_registry,
)
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_chunk, insert_document
from substrate.midnight_oil.job import (
    MidnightOilStepEvidence,
    create_job,
    get_job,
    put_job_state,
)
from substrate.midnight_oil.job_store import OperationState, OwnerJob
from substrate.midnight_oil.runtime import (
    MidnightOilRuntimeConfig,
    MidnightOilRuntimeConfigError,
    ProviderIdempotencyAttestation,
    provider_endpoint_sha256,
)
from substrate.midnight_oil.worker_cli import build_worker_runtime, run_worker_once


class _Embedding:
    dimension = 2

    def encode(self, text: str) -> list[float]:
        del text
        return [1.0, 0.0]


@pytest.fixture(autouse=True)
def _providers() -> Iterator[None]:
    reset_provider_registry()
    yield
    reset_provider_registry()


def _runtime_files(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    dispatch = tmp_path / "dispatch.yaml"
    dispatch.write_text(
        """
tiers:
  synthesis:
    provider: verified-provider
    model: verified-model
    pricing:
      input_per_mtok: 1.0
      output_per_mtok: 2.0
      cached_input_per_mtok: 0.5
tier_defaults:
  synthesis:
    max_tokens: 1000
    context_budget_tokens: 32000
    temperature: 0.1
role_tiers:
  synthesizer: synthesis
""".strip(),
        encoding="utf-8",
    )
    endpoint_hash = provider_endpoint_sha256(
        provider_name="verified-provider",
        base_url="https://provider.example.test",
        chat_completions_path="/v1/chat/completions",
        api_key_env="VERIFIED_PROVIDER_KEY",
    )
    attestation = tmp_path / "provider-attestation.json"
    attestation.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider_name": "verified-provider",
                "base_url": "https://provider.example.test",
                "chat_completions_path": "/v1/chat/completions",
                "api_key_env": "VERIFIED_PROVIDER_KEY",
                "endpoint_sha256": endpoint_hash,
                "dispatch_config_sha256": hashlib.sha256(
                    dispatch.read_bytes()
                ).hexdigest(),
                "evidence_ref": "urn:test:verified-idempotency-contract",
                "verified_at": "2026-07-12T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    runtime = tmp_path / "runtime.json"
    runtime.write_text(
        json.dumps(
            {
                "state_dir": str(tmp_path / "state"),
                "graph_db_path": str(tmp_path / "graph.duckdb"),
                "engagement_dir": str(tmp_path / "engagement"),
                "dispatch_config_path": str(dispatch),
                "retrieval_kind": "brute_force",
                "embedding_model_name": "test-embedding",
                "consent_active_key_id": "primary",
                "consent_signing_key_env": "MO_PRIMARY_KEY",
                "consent_verification_key_envs": {
                    "primary": "MO_PRIMARY_KEY"
                },
                "provider_attestation_paths": [str(attestation)],
                "worker_lease_ms": 60_000,
                "worker_poll_ms": 1_000,
            }
        ),
        encoding="utf-8",
    )
    environment = {
        "MO_PRIMARY_KEY": base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("="),
        "VERIFIED_PROVIDER_KEY": "test-key-never-serialized",
    }
    return runtime, environment, attestation


def test_runtime_builds_same_durable_api_and_worker_composition(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    api = build_midnight_oil_api_runtime(path, environ=environment)
    worker = build_worker_runtime(path, environ=environment)

    assert type(api.dependencies.owner_jobs) is type(worker.stores.owner_jobs)
    assert api.config == worker.config
    assert api.dependencies.operation_queue is api.stores.operation_queue
    assert api.dependencies.live_plan_resolver is not None
    provider = get_provider("verified-provider")
    assert provider.idempotency_guaranteed is True  # type: ignore[attr-defined]


def test_production_app_does_not_overwrite_attested_provider(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    app = create_midnight_oil_production_app(path, environ=environment)
    assert app.state.midnight_oil_runtime.config.state_dir == tmp_path / "state"
    provider = get_provider("verified-provider")
    assert provider.idempotency_guaranteed is True  # type: ignore[attr-defined]
    assert (
        app.state.engagement_store
        is app.state.midnight_oil_runtime.stores.engagement_store
    )


def test_production_app_rejects_conflicting_engagement_root(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    environment["ANTIEK_ENGAGEMENT_DIR"] = str(tmp_path / "different-engagement")

    with pytest.raises(RuntimeError, match="conflicts with the Midnight Oil"):
        create_midnight_oil_production_app(path, environ=environment)


def test_production_apps_keep_engagement_authority_isolated(tmp_path: Path) -> None:
    roots = (tmp_path / "runtime-a", tmp_path / "runtime-b")
    for root in roots:
        root.mkdir()
    path_a, environment_a, _ = _runtime_files(roots[0])
    path_b, environment_b, _ = _runtime_files(roots[1])
    app_a = create_midnight_oil_production_app(path_a, environ=environment_a)
    app_b = create_midnight_oil_production_app(path_b, environ=environment_b)
    client_a = TestClient(app_a)
    client_b = TestClient(app_b)

    for client, text in ((client_a, "runtime A insight"), (client_b, "runtime B insight")):
        recorded = client.post(
            "/engagement/twins",
            json={"asset_id": "shared-asset", "kind": "insight", "text": text},
        )
        assert recorded.status_code == 200, recorded.text

    notes_a = client_a.get("/engagement/twins/shared-asset").json()["notes"]
    notes_b = client_b.get("/engagement/twins/shared-asset").json()["notes"]
    assert {note["text"] for note in notes_a} == {"runtime A insight"}
    assert {note["text"] for note in notes_b} == {"runtime B insight"}


def test_production_twin_promotion_rolls_back_entire_batch(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    app = create_midnight_oil_production_app(path, environ=environment)
    client = TestClient(app, raise_server_exceptions=False)
    for kind, text in (
        ("insight", "The first graph write must roll back."),
        ("question", "Will the second promotion fail?"),
    ):
        recorded = client.post(
            "/engagement/twins",
            json={"asset_id": "atomic-batch", "kind": kind, "text": text},
        )
        assert recorded.status_code == 200
    with connect_read(str(app.state.engagement_graph_db_path)) as con:
        before = con.execute("SELECT count(*) FROM nodes").fetchone()[0]

    def reject_question(**kwargs: Any) -> str:
        del kwargs
        raise RuntimeError("injected second-note promotion failure")

    app.state.engagement_promote_question = reject_question
    failed = client.post(
        "/engagement/twins/promote-context", json={"asset_id": "atomic-batch"}
    )
    assert failed.status_code == 500
    with connect_read(str(app.state.engagement_graph_db_path)) as con:
        assert con.execute("SELECT count(*) FROM nodes").fetchone()[0] == before


def test_canonical_merge_commit_is_exact_revisioned_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from substrate.engagement_spine import (
        HighlightSelection,
        complete_spawn,
        merge_product_payload,
        spawn_from_highlight,
    )

    path, environment, _ = _runtime_files(tmp_path)
    app = create_midnight_oil_production_app(path, environ=environment)
    client = TestClient(app)
    store = app.state.engagement_store
    store.put_document(
        "source-paper",
        {"title": "Source paper", "body_text": "Immutable source body."},
    )
    spawn = spawn_from_highlight(
        HighlightSelection(
            asset_id="source-paper",
            selection_text="A claim requiring research.",
            region_id="region-1",
        ),
        store=store,
    )
    complete_spawn(
        spawn.spawn_id,
        store=store,
        output_text="Reviewed research output.",
        insights=["Reviewed insight."],
        questions=["Reviewed question?"],
    )
    draft = merge_product_payload(
        "source-paper",
        [spawn.spawn_id],
        store=store,
        mode="draft_combined",
        include_html=True,
    )
    reviewed_document = json.loads(json.dumps(store.get_document(draft["document_id"])))
    changed_spawn = store.get_spawn(spawn.spawn_id)
    assert changed_spawn is not None
    changed_spawn["output_text"] = "Later mutable spawn output."
    store.put_spawn(changed_spawn)

    body = {
        "draft_document_id": draft["document_id"],
        "reviewed_draft_sha256": draft["draft_sha256"],
        "target_deliverable_id": "dlv-reviewed-draft",
        "expected_revision": "new",
        "create_combined": True,
    }
    first = client.post("/engagement/merge/commit", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["twin_note_count"] == 2
    committed_twins = client.get(
        "/engagement/twins", params={"asset_id": "dlv-reviewed-draft"}
    )
    assert committed_twins.status_code == 200
    assert committed_twins.json()["note_count"] == 2
    assert any(
        "Reviewed research output." in note["text"]
        for note in committed_twins.json()["notes"]
    )
    assert {
        note["source_revision_sha256"] for note in committed_twins.json()["notes"]
    } == {draft["draft_sha256"]}
    from substrate.engagement_spine.project import project_to_html

    assert first.json()["html"] == project_to_html(
        reviewed_document["doc_model"],
        document_id="dlv-reviewed-draft",
        creator="engagement_spine.canonical_merge_commit",
    )
    second = client.post("/engagement/merge/commit", json=body)
    assert second.status_code == 200
    assert second.json()["new_revision"] == first.json()["new_revision"]
    assert second.json()["section_id"] == first.json()["section_id"]
    copied_draft_id = f"{draft['document_id']}-copy"
    store.put_document(copied_draft_id, reviewed_document)
    cross_draft_replay = client.post(
        "/engagement/merge/commit",
        json={**body, "draft_document_id": copied_draft_id},
    )
    assert cross_draft_replay.status_code == 409
    canonical = client.get("/deliverables/dlv-reviewed-draft").json()
    assert canonical["title"] == "Source paper"
    prose = canonical["sections"][-1]["prose_text"]
    assert "Reviewed research output." in prose
    assert "Later mutable spawn output." not in prose
    assert store.get_document("source-paper") == {
        "title": "Source paper",
        "body_text": "Immutable source body.",
    }
    revision = client.get("/engagement/merge/revision/dlv-reviewed-draft")
    assert revision.status_code == 200
    assert revision.json()["revision"] == first.json()["new_revision"]
    reloaded = client.get(
        "/engagement/merge/canonical/html",
        params={"deliverable_id": "dlv-reviewed-draft"},
    )
    assert reloaded.status_code == 200
    assert reloaded.json()["twin_note_count"] == 2
    assert reloaded.json()["draft_sha256"] == draft["draft_sha256"]
    assert "Reviewed research output." in reloaded.json()["html"]
    restarted_client = TestClient(
        create_midnight_oil_production_app(path, environ=environment)
    )
    cold_reloaded = restarted_client.get(
        "/engagement/merge/canonical/html",
        params={"deliverable_id": "dlv-reviewed-draft"},
    )
    assert cold_reloaded.status_code == 200
    assert cold_reloaded.json()["html"] == reloaded.json()["html"]
    cold_twins = restarted_client.get(
        "/engagement/twins", params={"asset_id": "dlv-reviewed-draft"}
    )
    assert cold_twins.status_code == 200
    assert cold_twins.json()["notes"] == committed_twins.json()["notes"]
    slash_draft_id = f"{draft['document_id']}-slash-target"
    store.put_document(slash_draft_id, reviewed_document)
    slash_commit = client.post(
        "/engagement/merge/commit",
        json={
            **body,
            "draft_document_id": slash_draft_id,
            "target_deliverable_id": "project/dlv-reviewed-draft",
        },
    )
    assert slash_commit.status_code == 200, slash_commit.text
    slash_reloaded = restarted_client.get(
        "/engagement/merge/canonical/html",
        params={"deliverable_id": "project/dlv-reviewed-draft"},
    )
    assert slash_reloaded.status_code == 200
    assert slash_reloaded.json()["deliverable_id"] == "project/dlv-reviewed-draft"
    assert "Reviewed research output." in slash_reloaded.json()["html"]
    slash_twins = restarted_client.get(
        "/engagement/twins", params={"asset_id": "project/dlv-reviewed-draft"}
    )
    assert slash_twins.status_code == 200
    assert slash_twins.json()["note_count"] == 2
    scoped_search = restarted_client.post(
        "/engagement/context-search",
        json={
            "asset_id": "project/dlv-reviewed-draft",
            "query": "Reviewed research output",
            "include_html": True,
        },
    )
    assert scoped_search.status_code == 200
    assert scoped_search.json()["hit_count"] == 1
    assert {
        hit["asset_id"] for hit in scoped_search.json()["hits"]
    } == {"project/dlv-reviewed-draft"}
    promoted = restarted_client.post(
        "/engagement/twins/promote-context",
        json={"asset_id": "project/dlv-reviewed-draft"},
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["promoted_count"] == 2
    assert promoted.json()["content_addressed_alignment"] is True
    promoted_replay = restarted_client.post(
        "/engagement/twins/promote-context",
        json={"asset_id": "project/dlv-reviewed-draft"},
    )
    assert promoted_replay.status_code == 200
    assert promoted_replay.json()["graph_node_ids"] == promoted.json()[
        "graph_node_ids"
    ]
    repair_draft_id = f"{draft['document_id']}-twin-repair"
    store.put_document(repair_draft_id, reviewed_document)
    original_replace_twins = store.replace_twins_for_origin

    def fail_twin_write(
        asset_id: str, origin: str, notes: list[dict[str, Any]]
    ) -> None:
        del asset_id, origin, notes
        raise OSError("injected canonical twin persistence failure")

    monkeypatch.setattr(store, "replace_twins_for_origin", fail_twin_write)
    repair_body = {
        **body,
        "draft_document_id": repair_draft_id,
        "target_deliverable_id": "dlv-twin-repair",
    }
    with pytest.raises(OSError, match="twin persistence failure"):
        client.post("/engagement/merge/commit", json=repair_body)
    canonical_after_twin_failure = client.get("/deliverables/dlv-twin-repair")
    assert canonical_after_twin_failure.status_code == 200
    failed_revision = client.get(
        "/engagement/merge/revision/dlv-twin-repair"
    ).json()["revision"]
    monkeypatch.setattr(store, "replace_twins_for_origin", original_replace_twins)
    repaired_commit = client.post("/engagement/merge/commit", json=repair_body)
    assert repaired_commit.status_code == 200
    assert repaired_commit.json()["new_revision"] == failed_revision
    assert repaired_commit.json()["twin_note_count"] == 2
    assert (
        client.get(
            "/engagement/merge/canonical/html",
            params={"deliverable_id": "missing-deliverable"},
        ).status_code
        == 404
    )
    with connect_write(str(app.state.engagement_graph_db_path)) as con:
        original_metadata = con.execute(
            "SELECT metadata FROM deliverables WHERE deliverable_id = ?",
            ["dlv-reviewed-draft"],
        ).fetchone()[0]
        changed = json.loads(original_metadata)
        changed["last_draft_sha256"] = "0" * 64
        con.execute(
            "UPDATE deliverables SET metadata = ? WHERE deliverable_id = ?",
            [json.dumps(changed), "dlv-reviewed-draft"],
        )
    assert (
        client.get(
            "/engagement/merge/canonical/html",
            params={"deliverable_id": "dlv-reviewed-draft"},
        ).status_code
        == 409
    )
    with connect_write(str(app.state.engagement_graph_db_path)) as con:
        con.execute(
            "UPDATE deliverables SET metadata = ? WHERE deliverable_id = ?",
            [original_metadata, "dlv-reviewed-draft"],
        )
        con.execute(
            "INSERT INTO deliverables "
            "(deliverable_id, title, deliverable_kind, owner_user_id) "
            "VALUES ('dlv-ordinary', 'Ordinary draft', 'research_memo', '__operator__')"
        )
    assert (
        client.get(
            "/engagement/merge/canonical/html",
            params={"deliverable_id": "dlv-ordinary"},
        ).status_code
        == 409
    )
    with connect_read(str(app.state.engagement_graph_db_path)) as con:
        metadata = json.loads(
            con.execute(
                "SELECT metadata FROM deliverables WHERE deliverable_id = ?",
                ["dlv-reviewed-draft"],
            ).fetchone()[0]
        )
        assert metadata["reviewed_doc_model"] == reviewed_document["doc_model"]
        assert (
            con.execute(
                "SELECT count(*) FROM section_blocks WHERE section_id = ?",
                [first.json()["section_id"]],
            ).fetchone()[0]
            == first.json()["paragraph_count"]
        )
        assert (
            con.execute(
                "SELECT count(*) FROM outline_blocks WHERE section_id = ?",
                [first.json()["section_id"]],
            ).fetchone()[0]
            == first.json()["paragraph_count"]
        )
    search = client.get("/engagement/merge/blocks/search", params={"q": "Reviewed insight"})
    assert search.status_code == 200
    assert any("Reviewed insight." in hit["label"] for hit in search.json()["hits"])

    other_target = client.post(
        "/engagement/merge/commit",
        json={**body, "target_deliverable_id": "dlv-reviewed-draft-copy"},
    )
    assert other_target.status_code == 200, other_target.text
    assert other_target.json()["section_id"] != first.json()["section_id"]

    newer_draft = merge_product_payload(
        "source-paper",
        [spawn.spawn_id],
        store=store,
        mode="draft_combined",
        parent_body="A distinct reviewed revision.",
    )
    with connect_read(str(app.state.engagement_graph_db_path)) as con:
        before_stale = {
            table: con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "deliverables",
                "deliverable_sections",
                "section_blocks",
                "outline_blocks",
                "nodes",
                "edges",
            )
        }
    stale = client.post(
        "/engagement/merge/commit",
        json={
            "draft_document_id": newer_draft["document_id"],
            "reviewed_draft_sha256": newer_draft["draft_sha256"],
            "target_deliverable_id": "dlv-reviewed-draft",
            "expected_revision": "stale-revision",
            "create_combined": False,
        },
    )
    assert stale.status_code == 409
    with connect_read(str(app.state.engagement_graph_db_path)) as con:
        assert {
            table: con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in before_stale
        } == before_stale

    tampered = store.get_document(draft["document_id"])
    assert tampered is not None
    tampered["doc_model"]["content"].append(
        {
            "type": "paragraph",
            "attrs": {"provenance": {"kind": "forged"}},
            "content": [{"type": "text", "text": "Forged after review."}],
        }
    )
    store.put_document(draft["document_id"], tampered)
    rejected = client.post(
        "/engagement/merge/commit",
        json={**body, "target_deliverable_id": "dlv-tampered"},
    )
    assert rejected.status_code == 409
    assert client.get("/deliverables/dlv-tampered").status_code == 404

    # Rewriting both mutable draft content and its store-side hash cannot bypass
    # the operator-held hash of the exact reviewed bytes.
    tampered_hash = hashlib.sha256(
        json.dumps(
            tampered["doc_model"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    tampered["draft_sha256"] = tampered_hash
    store.put_document(draft["document_id"], tampered)
    review_token_rejected = client.post(
        "/engagement/merge/commit",
        json={**body, "target_deliverable_id": "dlv-review-token"},
    )
    assert review_token_rejected.status_code == 409
    assert client.get("/deliverables/dlv-review-token").status_code == 404

    invalid = json.loads(json.dumps(reviewed_document))
    first_paragraph = next(
        block for block in invalid["doc_model"]["content"] if block.get("type") == "paragraph"
    )
    first_paragraph["attrs"]["provenance"] = {}
    invalid_hash = hashlib.sha256(
        json.dumps(
            invalid["doc_model"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    invalid["draft_sha256"] = invalid_hash
    store.put_document(draft["document_id"], invalid)
    invalid_provenance = client.post(
        "/engagement/merge/commit",
        json={
            **body,
            "reviewed_draft_sha256": invalid_hash,
            "target_deliverable_id": "dlv-invalid-provenance",
        },
    )
    assert invalid_provenance.status_code == 409
    assert client.get("/deliverables/dlv-invalid-provenance").status_code == 404

    # An idempotency checkpoint is evidence, not authority: canonical drift
    # invalidates replay even when its metadata still names this draft.
    with connect_write(str(app.state.engagement_graph_db_path)) as con:
        con.execute(
            "DELETE FROM edges WHERE source_node_id = ?",
            [first.json()["node_ids"][0]],
        )
    store.put_document(draft["document_id"], reviewed_document)
    drift_rejected = client.post("/engagement/merge/commit", json=body)
    assert drift_rejected.status_code == 409


def test_canonical_merge_commit_rolls_back_after_mid_transaction_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from substrate.engagement_spine import (
        HighlightSelection,
        canonical_commit,
        complete_spawn,
        merge_product_payload,
        spawn_from_highlight,
    )

    path, environment, _ = _runtime_files(tmp_path)
    app = create_midnight_oil_production_app(path, environ=environment)
    client = TestClient(app)
    store = app.state.engagement_store
    spawn = spawn_from_highlight(
        HighlightSelection(asset_id="atomic-source", selection_text="Atomic claim"),
        store=store,
    )
    complete_spawn(spawn.spawn_id, store=store, output_text="Atomic output")
    draft = merge_product_payload(
        "atomic-source", [spawn.spawn_id], store=store, mode="draft_combined"
    )
    colliding_parent_id = canonical_commit.content_addressed_id(
        "node", "source-asset|atomic-source"
    )
    with connect_write(str(app.state.engagement_graph_db_path)) as con:
        con.execute(
            "INSERT INTO nodes "
            "(node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES (?, 'poisoned authority', 'entity', 'depth', '{}')",
            [colliding_parent_id],
        )
    collision = client.post(
        "/engagement/merge/commit",
        json={
            "draft_document_id": draft["document_id"],
            "reviewed_draft_sha256": draft["draft_sha256"],
            "target_deliverable_id": "dlv-node-collision",
            "expected_revision": "new",
            "create_combined": True,
        },
    )
    assert collision.status_code == 409
    assert client.get("/deliverables/dlv-node-collision").status_code == 404
    with connect_write(str(app.state.engagement_graph_db_path)) as con:
        con.execute("DELETE FROM nodes WHERE node_id = ?", [colliding_parent_id])
    original = canonical_commit.commit_reviewed_draft

    def fail_after_writes(**kwargs: Any) -> Any:
        original(**kwargs)
        raise RuntimeError("injected after canonical writes")

    monkeypatch.setattr(canonical_commit, "commit_reviewed_draft", fail_after_writes)
    with connect_read(str(app.state.engagement_graph_db_path)) as con:
        before = {
            table: con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "deliverables",
                "deliverable_sections",
                "section_blocks",
                "outline_blocks",
                "nodes",
                "edges",
            )
        }
    with pytest.raises(RuntimeError, match="injected after canonical writes"):
        client.post(
            "/engagement/merge/commit",
            json={
                "draft_document_id": draft["document_id"],
                "reviewed_draft_sha256": draft["draft_sha256"],
                "target_deliverable_id": "dlv-atomic-failure",
                "expected_revision": "new",
                "create_combined": True,
            },
        )
    with connect_read(str(app.state.engagement_graph_db_path)) as con:
        after = {
            table: con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in before
        }
    assert after == before


def test_worker_no_work_is_structured_and_non_spending(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    record = run_worker_once(
        runtime,
        worker_id="worker-1",
        embedding_model=_Embedding(),
        clock_ms=lambda: 1_000,
    )
    assert record.result == "no_work"
    assert record.phase == "queue_empty"
    assert "test-key-never-serialized" not in record.to_json()


def test_attestation_fingerprint_tamper_fails_before_provider_install(
    tmp_path: Path,
) -> None:
    path, environment, attestation = _runtime_files(tmp_path)
    raw = json.loads(attestation.read_text(encoding="utf-8"))
    raw["base_url"] = "https://different.example.test"
    attestation.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(MidnightOilRuntimeConfigError, match="fingerprint conflicts"):
        build_worker_runtime(path, environ=environment)
    with pytest.raises(KeyError):
        get_provider("verified-provider")


def test_dispatch_config_drift_fails_before_provider_install(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime_raw = json.loads(path.read_text(encoding="utf-8"))
    dispatch = Path(runtime_raw["dispatch_config_path"])
    dispatch.write_text(
        dispatch.read_text(encoding="utf-8").replace(
            "model: verified-model", "model: unreviewed-model"
        ),
        encoding="utf-8",
    )
    with pytest.raises(MidnightOilRuntimeConfigError, match="configuration conflicts"):
        build_worker_runtime(path, environ=environment)
    with pytest.raises(KeyError):
        get_provider("verified-provider")


def test_runtime_and_attestation_contracts_reject_unknown_fields(tmp_path: Path) -> None:
    path, _, attestation = _runtime_files(tmp_path)
    runtime_raw = json.loads(path.read_text(encoding="utf-8"))
    runtime_raw["enable_live"] = True
    path.write_text(json.dumps(runtime_raw), encoding="utf-8")
    with pytest.raises(MidnightOilRuntimeConfigError, match="unknown or missing"):
        MidnightOilRuntimeConfig.from_file(path)

    attestation_raw = json.loads(attestation.read_text(encoding="utf-8"))
    attestation_raw["trusted"] = True
    attestation.write_text(json.dumps(attestation_raw), encoding="utf-8")
    with pytest.raises(MidnightOilRuntimeConfigError, match="unknown or missing"):
        ProviderIdempotencyAttestation.from_file(attestation)


def test_missing_secret_reports_configuration_without_naming_secret(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    environment.pop("VERIFIED_PROVIDER_KEY")
    with pytest.raises(MidnightOilRuntimeConfigError) as failure:
        build_worker_runtime(path, environ=environment)
    assert "VERIFIED_PROVIDER_KEY" not in str(failure.value)


@pytest.mark.parametrize(
    "mode",
    [
        "normal",
        "invalid_ceiling",
        "stop_after_paid",
        "config_drift",
        "deposit_crash",
        "projection_crash",
        "provider_timeout",
        "stop_before_claim",
        "stop_before_provider",
        "budget_halt",
        "post_action_crash",
        "max_steps",
        "max_steps_takeover",
        "max_steps_detail_crash",
        "max_steps_stale_fence",
        "engagement_store_convergence",
    ],
)
def test_api_to_worker_executes_deposits_projects_and_archives_once(
    tmp_path: Path, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    api = build_midnight_oil_api_runtime(path, environ=environment)
    app = (
        create_midnight_oil_production_app(path, environ=environment)
        if mode == "engagement_store_convergence"
        else FastAPI()
    )

    @app.middleware("http")
    async def _auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = "operator-runtime"
        return await call_next(request)

    if mode != "engagement_store_convergence":
        register_midnight_oil_routes(app, dependencies=api.dependencies)
    client = TestClient(app)
    created = client.post(
        "/midnight-oil/create",
        json={
            "goals": (
                ["Synthesize the seeded evidence.", "Challenge the synthesis."]
                if mode
                in {
                    "max_steps",
                    "max_steps_takeover",
                    "max_steps_detail_crash",
                    "max_steps_stale_fence",
                }
                else ["Synthesize the seeded evidence."]
            ),
            "duration_minutes": 10,
            "model_id": "verified-model",
            "live": True,
        },
    )
    assert created.status_code == 200, created.text
    job_id = created.json()["job_id"]
    consent = client.post(
        f"/midnight-oil/jobs/{job_id}/spend-consent",
        json=(
            {"ceiling_cents": 1, "force_below": True}
            if mode == "budget_halt"
            else {"use_recommended": True}
        ),
    )
    assert consent.status_code == 200, consent.text
    queued = client.post(
        "/midnight-oil/run",
        headers={"X-Midnight-Oil-Spend-Consent": consent.json()["token"]},
        json={
            "job_id": job_id,
            **(
                {"max_steps": 1}
                if mode
                in {
                    "max_steps",
                    "max_steps_takeover",
                    "max_steps_detail_crash",
                    "max_steps_stale_fence",
                }
                else {}
            ),
        },
    )
    assert queued.status_code == 200, queued.text

    ensure_initialized(str(api.config.graph_db_path))
    with connect_write(
        str(api.config.graph_db_path), purpose="test/runtime-e2e-seed"
    ) as con:
        insert_document(
            con,
            document_id="runtime-source",
            source_tier=1,
            document_type="paper",
            title="Runtime source",
        )
        insert_chunk(
            con,
            document_id="runtime-source",
            chunk_index=0,
            text="Seeded evidence for the runtime worker.",
            embedding=[1.0, 0.0],
            chunk_id="runtime-chunk",
        )

    class _PaidProvider:
        name = "verified-provider"
        idempotency_guaranteed = True

        def __init__(self) -> None:
            self.keys: list[str] = []

        def call_idempotent(
            self,
            *,
            idempotency_key: str,
            model: str,
            prompt: str,
            max_tokens: int,
            temperature: float,
        ) -> RawProviderResponse:
            del model, prompt, max_tokens, temperature
            self.keys.append(idempotency_key)
            if mode == "provider_timeout":
                raise ProviderError(
                    "secret provider timeout detail",
                    provider=self.name,
                    model="verified-model",
                    latency_ms=1,
                    retryable=True,
                )
            return RawProviderResponse(
                text="Runtime synthesis with durable evidence.",
                raw_usage={"prompt_tokens": 10, "completion_tokens": 5},
                finish_reason="stop",
                latency_ms=1,
                request_id="runtime-request",
            )

        def call(
            self,
            *,
            model: str,
            prompt: str,
            max_tokens: int,
            temperature: float,
        ) -> RawProviderResponse:
            del model, prompt, max_tokens, temperature
            raise AssertionError("live worker must use the idempotent provider method")

        def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
            return NormalizedUsage(
                input_tokens=int(raw_usage["prompt_tokens"]),
                output_tokens=int(raw_usage["completion_tokens"]),
            )

    paid = _PaidProvider()
    reset_provider_registry()
    register_provider(paid)
    worker = build_worker_runtime(path, environ=environment)
    # build_worker_runtime reinstalls the attested HTTP adapter; replace only
    # after its admission checks so the test proves the same config contract.
    register_provider(paid)

    if mode == "config_drift":
        tier = worker.dispatch_config.tiers["synthesis"]
        worker = replace(
            worker,
            dispatch_config=DispatchConfig(
                role_tiers=worker.dispatch_config.role_tiers,
                tiers={"synthesis": replace(tier, temperature=0.9)},
            ),
        )
        blocked = run_worker_once(
            worker,
            worker_id="runtime-worker-drift",
            embedding_model=_Embedding(),
        )
        assert blocked.result == "blocked_provider"
        assert blocked.deposit_document_id
        assert paid.keys == []
        assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is None
        return
    if mode == "invalid_ceiling":
        raw = worker.stores.jobs.get_job(job_id)
        assert raw is not None
        raw["approved_ceiling_usd"] = "invalid"
        with sqlite3.connect(worker.stores.jobs.path) as connection:
            connection.execute(
                "UPDATE midnight_oil_job_details SET row_json = ? WHERE job_id = ?",
                (json.dumps(raw), job_id),
            )
        quarantined = run_worker_once(
            worker,
            worker_id="runtime-worker-invalid-ceiling",
            embedding_model=_Embedding(),
        )
        assert quarantined.result == "reconcile_required"
        assert quarantined.phase == "lease_validation_quarantined"
        assert paid.keys == []
        assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is None
        return
    if mode == "stop_before_claim":
        stopped = run_worker_once(
            worker,
            worker_id="runtime-worker-prestopped",
            embedding_model=_Embedding(),
            stop_requested=lambda: True,
        )
        assert stopped.result == "no_work"
        assert stopped.phase == "shutdown_before_claim"
        assert paid.keys == []
        assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is not None
        return
    if mode == "stop_before_provider":
        checks = 0

        def stop_between_claim_and_provider() -> bool:
            nonlocal checks
            checks += 1
            return checks >= 2

        stopped = run_worker_once(
            worker,
            worker_id="runtime-worker-stop-before-provider",
            embedding_model=_Embedding(),
            stop_requested=stop_between_claim_and_provider,
        )
        assert stopped.result == "lease_pending"
        assert stopped.phase == "shutdown_before_provider"
        assert paid.keys == []
        recovered = run_worker_once(
            worker,
            worker_id="runtime-worker-after-stop",
            embedding_model=_Embedding(),
            clock_ms=lambda: 10**18,
        )
        assert recovered.result == "complete"
        assert len(paid.keys) == 1
        return
    if mode == "provider_timeout":
        reconciled = run_worker_once(
            worker,
            worker_id="runtime-worker-timeout",
            embedding_model=_Embedding(),
        )
        assert reconciled.result == "reconcile_required"
        assert reconciled.deposit_document_id
        assert "secret provider timeout detail" not in reconciled.to_json()
        assert len(paid.keys) == 1
        assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is None
        return
    if mode == "post_action_crash":
        def crash_after_paid_checkpoint() -> None:
            raise RuntimeError("soft crash after paid action")

        worker.stores.operation_queue._after_fenced_action = (  # type: ignore[method-assign]
            crash_after_paid_checkpoint
        )
        recovered = run_worker_once(
            worker,
            worker_id="runtime-worker-post-action-crash",
            embedding_model=_Embedding(),
        )
        assert recovered.result == "recovered"
        assert recovered.graph_deliverable_id
        authority = worker.stores.owner_jobs.get_job(
            owner_user_id="operator-runtime", job_id=job_id
        )
        assert authority is not None
        assert authority.operation_state is OperationState.COMPLETE
        assert len(paid.keys) == 1
        assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is None
        return
    if mode == "budget_halt":
        halted = run_worker_once(
            worker,
            worker_id="runtime-worker-budget",
            embedding_model=_Embedding(),
        )
        assert halted.result == "budget_halted"
        assert halted.phase == "terminal_without_graph_archived"
        assert halted.deposit_document_id
        assert halted.graph_deliverable_id is None
        assert paid.keys == []
        assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is None
        return
    if mode in {
        "max_steps",
        "max_steps_takeover",
        "max_steps_detail_crash",
        "max_steps_stale_fence",
    }:
        first = run_worker_once(
            worker,
            worker_id="runtime-worker-step-one",
            embedding_model=_Embedding(),
            stop_requested=(
                (lambda: bool(paid.keys))
                if mode == "max_steps_takeover"
                else (lambda: False)
            ),
        )
        assert first.result == "deposit_pending"
        assert len(paid.keys) == 1
        restarted = build_worker_runtime(path, environ=environment)
        register_provider(paid)
        if mode == "max_steps_stale_fence":
            monkeypatch.setattr(
                restarted.stores.operation_queue,
                "run_fenced",
                lambda **kwargs: (_ for _ in ()).throw(
                    RuntimeError("worker lease is stale")
                ),
            )
            with pytest.raises(RuntimeError, match="worker lease is stale"):
                run_worker_once(
                    restarted,
                    worker_id="runtime-worker-stale-cap",
                    embedding_model=_Embedding(),
                    clock_ms=lambda: 10**18,
                )
            authority = restarted.stores.owner_jobs.get_job(
                owner_user_id="operator-runtime", job_id=job_id
            )
            assert authority is not None
            assert authority.operation_state is OperationState.RUNNING
            detail = get_job(job_id, store=restarted.stores.jobs)
            assert detail is not None
            assert detail.status == "running"
            assert "max_steps" not in detail.notes.split(" | ")
            assert len(paid.keys) == 1
            return
        if mode == "max_steps_detail_crash":
            import substrate.midnight_oil.worker_cli as worker_module

            original = worker_module._converge_step_cap_detail

            def crash_before_detail(*args: Any, **kwargs: Any) -> None:
                del args, kwargs
                raise RuntimeError("crash before step-cap detail convergence")

            monkeypatch.setattr(
                worker_module, "_converge_step_cap_detail", crash_before_detail
            )
            with pytest.raises(RuntimeError, match="before step-cap detail"):
                run_worker_once(
                    restarted,
                    worker_id="runtime-worker-cap-crash",
                    embedding_model=_Embedding(),
                    clock_ms=lambda: 10**18,
                )
            monkeypatch.setattr(worker_module, "_converge_step_cap_detail", original)
        capped = run_worker_once(
            restarted,
            worker_id="runtime-worker-step-cap",
            embedding_model=_Embedding(),
            clock_ms=lambda: 10**18 + 100_000,
        )
        assert capped.result == "failed"
        assert capped.phase == "step_cap_archived"
        assert capped.error_code == "max_steps_reached"
        assert capped.deposit_document_id
        assert capped.graph_deliverable_id
        assert len(paid.keys) == 1
        authority = restarted.stores.owner_jobs.get_job(
            owner_user_id="operator-runtime", job_id=job_id
        )
        assert authority is not None
        assert authority.operation_state is OperationState.STEP_CAPPED
        detail = get_job(job_id, store=restarted.stores.jobs)
        assert detail is not None
        assert detail.status == "failed"
        assert detail.notes.split(" | ").count("max_steps") == 1
        assert len(detail.step_evidence) == 1
        assert restarted.stores.operation_queue.next_claimable(now_ms=10**18) is None
        with sqlite3.connect(restarted.stores.operation_queue.path) as connection:
            terminal = connection.execute(
                "SELECT terminal_state FROM midnight_oil_operation_terminal "
                "WHERE operation_id = ?",
                (queued.json()["operation_id"],),
            ).fetchone()
        assert terminal == ("failed",)
        return

    def execute(worker_id: str):  # type: ignore[no-untyped-def]
        return run_worker_once(
            worker,
            worker_id=worker_id,
            embedding_model=_Embedding(),
        )

    if mode in {"deposit_crash", "projection_crash"}:
        import substrate.midnight_oil.worker_cli as worker_module

        attribute = (
            "resume_terminal_deposit"
            if mode == "deposit_crash"
            else "resume_terminal_projection"
        )
        original = getattr(worker_module, attribute)

        def crash(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            raise RuntimeError("injected persistence crash")

        monkeypatch.setattr(worker_module, attribute, crash)
        pending = execute("runtime-worker-crashing")
        assert pending.result == (
            "deposit_pending" if mode == "deposit_crash" else "projection_pending"
        )
        assert len(paid.keys) == 1
        monkeypatch.setattr(worker_module, attribute, original)
        result = run_worker_once(
            worker,
            worker_id="runtime-worker-recovery",
            embedding_model=_Embedding(),
            clock_ms=lambda: 10**18,
        )
        assert result.result == "recovered"
    elif mode == "stop_after_paid":
        stopped = run_worker_once(
            worker,
            worker_id="runtime-worker-stopping",
            embedding_model=_Embedding(),
            stop_requested=lambda: bool(paid.keys),
        )
        assert stopped.result == "deposit_pending"
        assert stopped.phase == "shutdown_after_provider"
        assert len(paid.keys) == 1
        result = run_worker_once(
            worker,
            worker_id="runtime-worker-recovery",
            embedding_model=_Embedding(),
            clock_ms=lambda: 10**18,
        )
        assert result.result == "recovered"
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            records = list(pool.map(execute, ("runtime-worker-a", "runtime-worker-b")))
        result = next(record for record in records if record.result == "complete")
        assert {record.result for record in records} <= {
            "complete",
            "contended",
            "no_work",
        }
        assert sum(record.result == "complete" for record in records) == 1
    assert result.result in {"complete", "recovered"}
    assert result.deposit_document_id
    assert result.graph_deliverable_id
    assert len(paid.keys) == 1
    assert worker.stores.operation_queue.next_claimable(now_ms=10**18) is None
    if mode == "engagement_store_convergence":
        detail = get_job(job_id, store=worker.stores.jobs)
        assert detail is not None
        assert detail.asset_id
        twins = client.get(f"/engagement/twins/{detail.asset_id}")
        assert twins.status_code == 200, twins.text
        twin_body = twins.json()
        assert twin_body["insight_count"] == 1
        assert twin_body["question_count"] == 1
        texts = {note["text"] for note in twin_body["notes"]}
        assert "Runtime synthesis with durable evidence." in texts
        assert "Which claims remain unsupported by operator-corpus evidence?" in texts
        searched = client.post(
            "/engagement/context-search",
            json={
                "query": "evidence",
                "asset_id": detail.asset_id,
                "include_html": True,
            },
        )
        assert searched.status_code == 200, searched.text
        assert searched.json()["hit_count"] >= 1
        promoted = client.post(
            "/engagement/twins/promote-context",
            json={"asset_id": detail.asset_id, "kinds": ["question"]},
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["promoted_count"] == 1
        promoted_node_id = promoted.json()["promoted"][0]["graph_node_id"]
        with connect_read(str(api.config.graph_db_path)) as con:
            assert con.execute(
                "SELECT count(*) FROM nodes WHERE node_id = ?", [promoted_node_id]
            ).fetchone() == (1,)
        question = next(
            note["text"] for note in twin_body["notes"] if note["kind"] == "question"
        )
        opened = client.post(
            "/engagement/sessions/open",
            json={
                "asset_id": detail.asset_id,
                "selection_text": question,
                "goal_hint": f"Twin chase on {detail.asset_id}",
                "view_mode": "floating",
                "research_tier": "deep",
            },
        )
        assert opened.status_code == 200, opened.text
        assert opened.json()["parent_asset_id"] == detail.asset_id
        session_id = opened.json()["session_id"]
        replayed = client.post(
            "/midnight-oil/deposit",
            json={"job_id": job_id, "record_progress": False},
        )
        assert replayed.status_code == 200, replayed.text
        assert replayed.json()["document_id"] == result.deposit_document_id
        assert replayed.json()["twin_count"] == twin_body["note_count"]
        replayed_twins = client.get(f"/engagement/twins/{detail.asset_id}")
        assert replayed_twins.json()["note_count"] == twin_body["note_count"]
        draft = client.post(
            "/engagement/merge",
            json={
                "parent_asset_id": detail.asset_id,
                "spawn_ids": list(detail.spawn_ids),
                "mode": "draft_combined",
                "include_html": True,
            },
        )
        assert draft.status_code == 200, draft.text
        committed = client.post(
            "/engagement/merge/commit",
            json={
                "draft_document_id": draft.json()["document_id"],
                "reviewed_draft_sha256": draft.json()["draft_sha256"],
                "target_deliverable_id": "dlv-runtime-combined",
                "expected_revision": "new",
                "create_combined": True,
            },
        )
        assert committed.status_code == 200, committed.text
        assert committed.json()["paragraph_count"] >= 3
        assert committed.json()["node_ids"]
        canonical = client.get("/deliverables/dlv-runtime-combined")
        assert canonical.status_code == 200, canonical.text
        canonical_sections = canonical.json()["sections"]
        assert canonical_sections
        assert canonical_sections[-1]["prose_provenance"]
        assert "Runtime synthesis with durable evidence." in canonical_sections[-1]["prose_text"]
        restarted_app = create_midnight_oil_production_app(path, environ=environment)
        restarted_client = TestClient(restarted_app)
        restarted_twins = restarted_client.get(f"/engagement/twins/{detail.asset_id}")
        assert restarted_twins.status_code == 200
        assert restarted_twins.json()["note_count"] == twin_body["note_count"]
        with connect_read(str(api.config.graph_db_path)) as con:
            graph_nodes_before_followup = con.execute(
                "SELECT count(*) FROM nodes"
            ).fetchone()[0]
        completed_session = restarted_client.post(
            "/engagement/sessions/complete-flywheel",
            json={
                "session_id": session_id,
                "output_text": "Follow-up complete.",
                "insights": ["Follow-up insight persisted."],
                "questions": ["Which recursive branch follows?"],
                "record_twins": True,
                "include_twin_promote": True,
            },
        )
        assert completed_session.status_code == 200, completed_session.text
        assert completed_session.json()["status"] == "complete"
        with connect_read(str(api.config.graph_db_path)) as con:
            assert (
                con.execute("SELECT count(*) FROM nodes").fetchone()[0]
                > graph_nodes_before_followup
            )
    second = run_worker_once(
        worker,
        worker_id="runtime-worker",
        embedding_model=_Embedding(),
    )
    assert second.result == "no_work"
    assert len(paid.keys) == 1
    with connect_read(str(api.config.graph_db_path)) as con:
        assert con.execute(
            "SELECT count(*) FROM deliverables WHERE deliverable_id = ?",
            [result.graph_deliverable_id],
        ).fetchone() == (1,)


def test_terminal_failure_without_paid_evidence_deposits_and_archives(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    job = create_job(
        ["A pre-network failure still deserves a visible terminal deposit."],
        10,
        store=runtime.stores.jobs,
        job_id="failed-job",
        asset_id="failed-asset",
    )
    put_job_state(
        replace(job, status="failed"),
        store=runtime.stores.jobs,
    )
    runtime.stores.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="operator-runtime",
            job_id=job.job_id,
            state_version=4,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="c" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=2,
            operation_id="failed-operation",
            operation_state=OperationState.FAILED,
            dispatch_started_at_ms=3,
            dispatched_at_ms=None,
            completed_at_ms=4,
            payload={},
        )
    )
    runtime.stores.operation_queue.enqueue_once(
        operation_id="failed-operation",
        owner_user_id="operator-runtime",
        job_id=job.job_id,
        enqueued_at_ms=1,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    runtime.stores.operation_queue.lease(
        operation_id="failed-operation",
        worker_id="dead-worker",
        leased_at_ms=2,
        lease_expires_at_ms=3,
    )
    result = run_worker_once(
        runtime,
        worker_id="recovery-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 4,
    )
    assert result.result == "failed"
    assert result.deposit_document_id
    assert result.graph_deliverable_id is None
    assert runtime.stores.operation_queue.next_claimable(now_ms=5) is None


def test_terminal_failure_at_cap_boundary_is_not_relabelled_as_step_cap(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    job = create_job(
        ["An unrelated failure must retain its provenance."],
        10,
        store=runtime.stores.jobs,
        job_id="unrelated-failed-job",
        asset_id="unrelated-failed-asset",
    )
    put_job_state(
        replace(job, status="failed", notes="provider_failure"),
        store=runtime.stores.jobs,
    )
    runtime.stores.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="operator-runtime",
            job_id=job.job_id,
            state_version=4,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="c" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=2,
            operation_id="unrelated-failed-operation",
            operation_state=OperationState.FAILED,
            dispatch_started_at_ms=3,
            dispatched_at_ms=None,
            completed_at_ms=4,
            payload={},
        )
    )
    runtime.stores.operation_queue.enqueue_once(
        operation_id="unrelated-failed-operation",
        owner_user_id="operator-runtime",
        job_id=job.job_id,
        enqueued_at_ms=1,
        options={
            "max_steps": 1,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    leased, won = runtime.stores.operation_queue.lease(
        operation_id="unrelated-failed-operation",
        worker_id="expired-worker",
        leased_at_ms=2,
        lease_expires_at_ms=3,
    )
    assert won
    runtime.stores.operation_queue.run_fenced(
        operation_id=leased.operation_id,
        worker_id="expired-worker",
        lease_generation=leased.lease_generation,
        now_ms=2,
        expected_step_index=0,
        action=lambda: (None, True),
    )

    recovered = run_worker_once(
        runtime,
        worker_id="recovery-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 4,
    )

    assert recovered.result == "failed"
    assert recovered.phase == "terminal_archived"
    assert recovered.error_code is None
    restored = get_job(job.job_id, store=runtime.stores.jobs)
    assert restored is not None
    assert restored.notes.startswith("provider_failure")
    assert "max_steps" not in restored.notes.split(" | ")


def test_validation_quarantine_race_recovers_concurrently_terminal_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import substrate.midnight_oil.worker_cli as worker_module

    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    job = create_job(
        ["Concurrent terminal recovery must retain its deposit."],
        10,
        store=runtime.stores.jobs,
        job_id="race-job",
        asset_id="race-asset",
    )
    put_job_state(replace(job, status="failed"), store=runtime.stores.jobs)
    runtime.stores.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="operator-runtime",
            job_id=job.job_id,
            state_version=3,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="c" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=2,
            operation_id="race-operation",
            operation_state=OperationState.QUEUED,
            dispatch_started_at_ms=None,
            dispatched_at_ms=None,
            completed_at_ms=None,
            payload={},
        )
    )
    runtime.stores.operation_queue.enqueue_once(
        operation_id="race-operation",
        owner_user_id="operator-runtime",
        job_id=job.job_id,
        enqueued_at_ms=2,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )

    def terminal_race(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        current = runtime.stores.owner_jobs.get_job(
            owner_user_id="operator-runtime", job_id=job.job_id
        )
        assert current is not None
        changed = runtime.stores.owner_jobs.compare_and_set(
            owner_user_id="operator-runtime",
            job_id=job.job_id,
            expected_version=current.state_version,
            expected_state=OperationState.QUEUED,
            operation_id="race-operation",
            next_state=OperationState.FAILED_RECONCILE,
            completed_at_ms=4,
        )
        assert changed.applied
        raise worker_module.LeaseValidationError("stale validation snapshot")

    monkeypatch.setattr(worker_module, "lease_authorized_operation", terminal_race)
    recovered = run_worker_once(
        runtime,
        worker_id="race-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 4,
    )
    assert recovered.result == "reconcile_required"
    assert recovered.phase == "terminal_archived"
    assert recovered.deposit_document_id
    assert runtime.stores.operation_queue.next_claimable(now_ms=5) is None


def test_running_validation_quarantine_recovers_paid_evidence_before_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import substrate.midnight_oil.worker_cli as worker_module

    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    ensure_initialized(str(runtime.config.graph_db_path))
    job = create_job(
        ["Paid evidence must survive quarantine."],
        10,
        store=runtime.stores.jobs,
        job_id="paid-poison-job",
        asset_id="paid-poison-asset",
    )
    put_job_state(
        replace(
            job,
            status="failed",
            step_evidence=(
                MidnightOilStepEvidence(
                    step_key="paid-step",
                    spawn_id="paid-spawn",
                    output_text="Durable paid evidence.",
                    insights=("Evidence survived.",),
                    questions=("What remains?",),
                ),
            ),
        ),
        store=runtime.stores.jobs,
    )
    runtime.stores.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="operator-runtime",
            job_id=job.job_id,
            state_version=4,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="c" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=2,
            operation_id="paid-poison-operation",
            operation_state=OperationState.RUNNING,
            dispatch_started_at_ms=3,
            dispatched_at_ms=None,
            completed_at_ms=None,
            payload={},
        )
    )
    runtime.stores.operation_queue.enqueue_once(
        operation_id="paid-poison-operation",
        owner_user_id="operator-runtime",
        job_id=job.job_id,
        enqueued_at_ms=2,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    runtime.stores.operation_queue.lease(
        operation_id="paid-poison-operation",
        worker_id="expired-worker",
        leased_at_ms=3,
        lease_expires_at_ms=4,
    )
    monkeypatch.setattr(
        worker_module,
        "lease_authorized_operation",
        lambda **kwargs: (_ for _ in ()).throw(
            worker_module.LeaseValidationError("corrupt running projection")
        ),
    )
    recovered = run_worker_once(
        runtime,
        worker_id="recovery-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 5,
    )
    assert recovered.result == "reconcile_required"
    assert recovered.phase == "terminal_archived"
    assert recovered.deposit_document_id
    assert recovered.graph_deliverable_id
    assert runtime.stores.operation_queue.next_claimable(now_ms=6) is None


def test_validation_quarantine_tolerates_concurrent_queue_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import substrate.midnight_oil.worker_cli as worker_module

    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    runtime.stores.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="removed-owner",
            job_id="removed-job",
            state_version=2,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="c" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=None,
            operation_id="removed-operation",
            operation_state=OperationState.CONSENT_ISSUED,
            dispatch_started_at_ms=None,
            dispatched_at_ms=None,
            completed_at_ms=None,
            payload={},
        )
    )
    runtime.stores.operation_queue.enqueue_once(
        operation_id="removed-operation",
        owner_user_id="removed-owner",
        job_id="removed-job",
        enqueued_at_ms=1,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )

    def remove_then_fail(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        leased, won = runtime.stores.operation_queue.lease(
            operation_id="removed-operation",
            worker_id="winning-worker",
            leased_at_ms=2,
            lease_expires_at_ms=20_000,
        )
        assert won
        assert runtime.stores.operation_queue.acknowledge_terminal(
            operation_id="removed-operation",
            worker_id="winning-worker",
            lease_generation=leased.lease_generation,
            terminal_state="failed_reconcile",
            completed_at_ms=2,
        )
        raise worker_module.LeaseValidationError("stale selected row")

    monkeypatch.setattr(worker_module, "lease_authorized_operation", remove_then_fail)
    record = run_worker_once(
        runtime,
        worker_id="losing-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 2,
    )
    assert record.result == "contended"
    assert record.phase == "lease_validation_queue_resolved"


def test_missing_authority_is_quarantined_without_starving_queue(tmp_path: Path) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    runtime.stores.operation_queue.enqueue_once(
        operation_id="orphan-operation",
        owner_user_id="missing-owner",
        job_id="missing-job",
        enqueued_at_ms=1,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    record = run_worker_once(
        runtime,
        worker_id="quarantine-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 2,
    )
    assert record.result == "reconcile_required"
    assert record.phase == "authority_quarantined"
    assert runtime.stores.operation_queue.next_claimable(now_ms=3) is None


def test_malformed_authority_is_quarantined_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    runtime.stores.operation_queue.enqueue_once(
        operation_id="malformed-operation",
        owner_user_id="malformed-owner",
        job_id="malformed-job",
        enqueued_at_ms=1,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    monkeypatch.setattr(
        runtime.stores.owner_jobs,
        "get_job",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("corrupt owner row")),
    )
    record = run_worker_once(
        runtime,
        worker_id="quarantine-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 2,
    )
    assert record.result == "reconcile_required"
    assert record.phase == "authority_quarantined"
    assert "corrupt owner row" not in record.to_json()
    assert runtime.stores.operation_queue.next_claimable(now_ms=3) is None


def test_malformed_dispatch_refresh_is_quarantined_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import substrate.midnight_oil.worker_cli as worker_module

    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    authority = OwnerJob(
        owner_user_id="refresh-owner",
        job_id="refresh-job",
        state_version=2,
        approved_ceiling_cents=100,
        consent_receipt_id="receipt",
        consent_config_hash="c" * 64,
        consent_issued_at_ms=1,
        consent_expires_at_ms=100,
        consent_claimed_at_ms=None,
        operation_id="refresh-operation",
        operation_state=OperationState.CONSENT_ISSUED,
        dispatch_started_at_ms=None,
        dispatched_at_ms=None,
        completed_at_ms=None,
        payload={},
    )
    runtime.stores.owner_jobs.put_job(authority)
    runtime.stores.operation_queue.enqueue_once(
        operation_id="refresh-operation",
        owner_user_id="refresh-owner",
        job_id="refresh-job",
        enqueued_at_ms=1,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    reads = 0

    def malformed_after_selection(**kwargs):  # type: ignore[no-untyped-def]
        nonlocal reads
        del kwargs
        reads += 1
        if reads == 1:
            return authority
        raise ValueError("corrupt refreshed owner row")

    monkeypatch.setattr(runtime.stores.owner_jobs, "get_job", malformed_after_selection)
    monkeypatch.setattr(
        worker_module,
        "lease_authorized_operation",
        lambda **kwargs: (_ for _ in ()).throw(
            worker_module.OperationNotDispatchableError("state changed")
        ),
    )
    record = run_worker_once(
        runtime,
        worker_id="refresh-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 2,
    )
    assert record.result == "reconcile_required"
    assert record.phase == "lease_validation_authority_malformed"
    assert "corrupt refreshed owner row" not in record.to_json()
    assert runtime.stores.operation_queue.next_claimable(now_ms=3) is None


@pytest.mark.parametrize(
    ("initial_state", "claimed_at_ms"),
    [
        (OperationState.CONSENT_ISSUED, None),
        (OperationState.QUEUED, 2),
    ],
)
def test_missing_details_poison_is_quarantined_instead_of_hot_looping(
    tmp_path: Path,
    initial_state: OperationState,
    claimed_at_ms: int | None,
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    runtime.stores.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="operator-runtime",
            job_id="poison-job",
            state_version=3,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="c" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=claimed_at_ms,
            operation_id="poison-operation",
            operation_state=initial_state,
            dispatch_started_at_ms=None,
            dispatched_at_ms=None,
            completed_at_ms=None,
            payload={},
        )
    )
    runtime.stores.operation_queue.enqueue_once(
        operation_id="poison-operation",
        owner_user_id="operator-runtime",
        job_id="poison-job",
        enqueued_at_ms=2,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    runtime.stores.operation_queue.enqueue_once(
        operation_id="valid-operation-behind-poison",
        owner_user_id="next-owner",
        job_id="next-job",
        enqueued_at_ms=2,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    quarantined = run_worker_once(
        runtime,
        worker_id="quarantine-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 3,
    )
    assert quarantined.result == "reconcile_required"
    assert quarantined.phase == "lease_validation_quarantined"
    assert quarantined.error_code == "lease_validation"
    authority = runtime.stores.owner_jobs.get_job(
        owner_user_id="operator-runtime", job_id="poison-job"
    )
    assert authority is not None
    assert authority.operation_state is OperationState.FAILED_RECONCILE
    assert authority.dispatch_started_at_ms is None
    next_claimable = runtime.stores.operation_queue.next_claimable(now_ms=4)
    assert next_claimable is not None
    assert next_claimable.operation_id == "valid-operation-behind-poison"


def test_malformed_queue_policy_is_quarantined_without_starving_later_work(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    runtime.stores.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="operator-runtime",
            job_id="policy-poison-job",
            state_version=3,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="c" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=2,
            operation_id="policy-poison-operation",
            operation_state=OperationState.QUEUED,
            dispatch_started_at_ms=None,
            dispatched_at_ms=None,
            completed_at_ms=None,
            payload={},
        )
    )
    legacy_options = {
        "max_steps": None,
        "auto_deposit": True,
        "draft_combined": True,
        "force_offline": False,
    }
    runtime.stores.operation_queue.enqueue_once(
        operation_id="policy-poison-operation",
        owner_user_id="operator-runtime",
        job_id="policy-poison-job",
        enqueued_at_ms=2,
        options=legacy_options,
    )
    with sqlite3.connect(runtime.stores.operation_queue.path) as connection:
        connection.execute(
            "UPDATE midnight_oil_operation_queue SET options_json = ? "
            "WHERE operation_id = ?",
            (
                json.dumps(
                    {**legacy_options, "acceptance_policy_version": 1},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "policy-poison-operation",
            ),
        )
    runtime.stores.operation_queue.enqueue_once(
        operation_id="valid-operation-behind-policy-poison",
        owner_user_id="next-owner",
        job_id="next-job",
        enqueued_at_ms=3,
        options=legacy_options,
    )

    quarantined = run_worker_once(
        runtime,
        worker_id="policy-quarantine-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 4,
    )

    assert quarantined.result == "reconcile_required"
    assert quarantined.phase == "lease_validation_quarantined"
    authority = runtime.stores.owner_jobs.get_job(
        owner_user_id="operator-runtime", job_id="policy-poison-job"
    )
    assert authority is not None
    assert authority.operation_state is OperationState.FAILED_RECONCILE
    next_claimable = runtime.stores.operation_queue.next_claimable(now_ms=5)
    assert next_claimable is not None
    assert next_claimable.operation_id == "valid-operation-behind-policy-poison"


def test_missing_terminal_details_are_quarantined_and_survive_restart(
    tmp_path: Path,
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    runtime.stores.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="terminal-owner",
            job_id="missing-terminal-job",
            state_version=5,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="c" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=2,
            operation_id="terminal-poison-operation",
            operation_state=OperationState.FAILED_RECONCILE,
            dispatch_started_at_ms=3,
            dispatched_at_ms=None,
            completed_at_ms=4,
            payload={},
        )
    )
    for operation_id, owner_user_id, job_id, enqueued_at_ms in (
        ("terminal-poison-operation", "terminal-owner", "missing-terminal-job", 1),
        ("valid-behind-terminal-poison", "next-owner", "next-job", 2),
    ):
        runtime.stores.operation_queue.enqueue_once(
            operation_id=operation_id,
            owner_user_id=owner_user_id,
            job_id=job_id,
            enqueued_at_ms=enqueued_at_ms,
            options={
                "max_steps": None,
                "auto_deposit": True,
                "draft_combined": True,
                "force_offline": False,
            },
        )

    quarantined = run_worker_once(
        runtime,
        worker_id="terminal-quarantine-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 5,
    )

    assert quarantined.result == "reconcile_required"
    assert quarantined.phase == "terminal_recovery_quarantined"
    assert quarantined.error_code == "terminal_recovery_invalid"
    assert quarantined.operation_id == "terminal-poison-operation"
    assert "live deposit job not found" not in quarantined.to_json()
    reopened = build_worker_runtime(path, environ=environment)
    next_claimable = reopened.stores.operation_queue.next_claimable(now_ms=6)
    assert next_claimable is not None
    assert next_claimable.operation_id == "valid-behind-terminal-poison"


def test_terminal_graph_conflict_is_quarantined_without_starving_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import substrate.midnight_oil.worker_cli as worker_module

    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    job = create_job(
        ["Preserve paid evidence even when graph state conflicts."],
        10,
        store=runtime.stores.jobs,
        job_id="graph-conflict-job",
        asset_id="graph-conflict-asset",
    )
    put_job_state(
        replace(
            job,
            status="failed",
            step_evidence=(
                MidnightOilStepEvidence(
                    step_key="paid-step",
                    spawn_id="paid-spawn",
                    output_text="Paid evidence remains deposited.",
                    insights=("Recovery must be fenced.",),
                    questions=("How should conflict be reconciled?",),
                ),
            ),
        ),
        store=runtime.stores.jobs,
    )
    runtime.stores.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="graph-owner",
            job_id=job.job_id,
            state_version=5,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="c" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=2,
            operation_id="graph-conflict-operation",
            operation_state=OperationState.FAILED_RECONCILE,
            dispatch_started_at_ms=3,
            dispatched_at_ms=None,
            completed_at_ms=4,
            payload={},
        )
    )
    for operation_id, owner_user_id, job_id, enqueued_at_ms in (
        ("graph-conflict-operation", "graph-owner", job.job_id, 1),
        ("valid-behind-graph-conflict", "next-owner", "next-job", 2),
    ):
        runtime.stores.operation_queue.enqueue_once(
            operation_id=operation_id,
            owner_user_id=owner_user_id,
            job_id=job_id,
            enqueued_at_ms=enqueued_at_ms,
            options={
                "max_steps": None,
                "auto_deposit": True,
                "draft_combined": True,
                "force_offline": False,
            },
        )

    monkeypatch.setattr(
        worker_module,
        "resume_terminal_projection",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            worker_module.GraphProjectionConflict("secret conflicting graph payload")
        ),
    )
    quarantined = run_worker_once(
        runtime,
        worker_id="graph-quarantine-worker",
        embedding_model=_Embedding(),
        clock_ms=lambda: 5,
    )

    assert quarantined.result == "reconcile_required"
    assert quarantined.phase == "terminal_recovery_quarantined"
    assert "secret conflicting graph payload" not in quarantined.to_json()
    deposited = get_job(job.job_id, store=runtime.stores.jobs)
    assert deposited is not None
    assert deposited.deposit_state == "complete"
    next_claimable = runtime.stores.operation_queue.next_claimable(now_ms=6)
    assert next_claimable is not None
    assert next_claimable.operation_id == "valid-behind-graph-conflict"


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_untyped_terminal_recovery_failure_remains_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    import substrate.midnight_oil.worker_cli as worker_module

    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    job = create_job(
        ["Transient recovery failure must not erase retry authority."],
        10,
        store=runtime.stores.jobs,
        job_id="transient-recovery-job",
        asset_id="transient-recovery-asset",
    )
    put_job_state(replace(job, status="failed"), store=runtime.stores.jobs)
    runtime.stores.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="transient-owner",
            job_id=job.job_id,
            state_version=5,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="c" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=2,
            operation_id="transient-recovery-operation",
            operation_state=OperationState.FAILED,
            dispatch_started_at_ms=3,
            dispatched_at_ms=None,
            completed_at_ms=4,
            payload={},
        )
    )
    runtime.stores.operation_queue.enqueue_once(
        operation_id="transient-recovery-operation",
        owner_user_id="transient-owner",
        job_id=job.job_id,
        enqueued_at_ms=1,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    monkeypatch.setattr(
        worker_module,
        "resume_terminal_deposit",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            error_type("temporary storage outage")
        ),
    )

    with pytest.raises(error_type, match="temporary storage outage"):
        run_worker_once(
            runtime,
            worker_id="transient-worker",
            embedding_model=_Embedding(),
            clock_ms=lambda: 5,
        )

    assert runtime.stores.operation_queue.next_claimable(now_ms=60_006) is not None


def test_terminal_recovery_quarantine_refuses_lost_queue_fence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, environment, _ = _runtime_files(tmp_path)
    runtime = build_worker_runtime(path, environ=environment)
    runtime.stores.owner_jobs.put_job(
        OwnerJob(
            owner_user_id="fence-owner",
            job_id="missing-fence-job",
            state_version=5,
            approved_ceiling_cents=100,
            consent_receipt_id="receipt",
            consent_config_hash="c" * 64,
            consent_issued_at_ms=1,
            consent_expires_at_ms=100,
            consent_claimed_at_ms=2,
            operation_id="fence-poison-operation",
            operation_state=OperationState.FAILED_RECONCILE,
            dispatch_started_at_ms=3,
            dispatched_at_ms=None,
            completed_at_ms=4,
            payload={},
        )
    )
    runtime.stores.operation_queue.enqueue_once(
        operation_id="fence-poison-operation",
        owner_user_id="fence-owner",
        job_id="missing-fence-job",
        enqueued_at_ms=1,
        options={
            "max_steps": None,
            "auto_deposit": True,
            "draft_combined": True,
            "force_offline": False,
        },
    )
    monkeypatch.setattr(
        runtime.stores.operation_queue,
        "acknowledge_terminal",
        lambda **kwargs: False,
    )

    with pytest.raises(
        RuntimeError, match="terminal recovery quarantine lost its queue fence"
    ):
        run_worker_once(
            runtime,
            worker_id="stale-fence-worker",
            embedding_model=_Embedding(),
            clock_ms=lambda: 5,
        )

    assert runtime.stores.operation_queue.next_claimable(now_ms=60_006) is not None
