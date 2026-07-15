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
    derived_asset_router,
    get_merge_draft_repository,
    merge_asset_router,
    register_merge_asset_routes,
)
from runtime.db_lock import connect_write
from runtime.research_runner.derived_companion_receipt import (
    COMPANION_OPERATION,
    COMPANION_SEAM_ID,
    SettledCompanionReceiptVerifier,
    companion_operation_digest,
    companion_settlement_evidence,
)
from substrate.contracts.html_projection import HtmlProjectionContract, derive_projection_id
from substrate.graph.schema import init_database_at_path
from substrate.research_artifact.derived_citation_source import (
    DerivedCitationConflict,
    verify_derived_citation_source,
)
from substrate.research_artifact.derived_companion import (
    build_derived_revision_evidence_pack,
    canonical_evidence_json,
)
from substrate.research_artifact.derived_companion_repository import (
    CompanionAnswerConflict,
    CompanionAnswerUnavailable,
    DerivedCompanionRepository,
)
from substrate.research_artifact.grounded_companion_answer import (
    AnswerClaimInput,
    GroundedAnswerCandidate,
    candidate_digest,
)
from substrate.research_artifact.merge_draft import MergeDraftRepository
from substrate.research_spend import PaidHoldIntent, ResearchSpendLedger, RunBinding
from substrate.schemas import DerivedCitationSource


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

    app.include_router(derived_asset_router)
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
        "projection_ids",
    }
    assert draft["projection_ids"] == [projection_id]
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
    framed = client.get(
        f"/research/derived-assets/merge/frame-previews/{review['review_id']}"
    )
    assert framed.content == preview.content
    assert framed.headers["cache-control"] == "private, no-store"
    assert framed.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'self'" in framed.headers["content-security-policy"]
    assert "sandbox" in framed.headers["content-security-policy"]
    assert "x-frame-options" not in framed.headers
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


def test_review_apply_route_is_id_only_private_and_owner_scoped(
    fixture: tuple[TestClient, MergeDraftRepository, str, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _repository, db_path, _object_path, projection_id = fixture
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    draft = client.post("/research/derived-assets/merge/drafts", json=payload(projection_id)).json()
    review = client.post(
        f"/research/derived-assets/merge/drafts/{draft['draft_id']}/reviews"
    ).json()
    operation_id = "op_" + "1" * 32

    applied = client.post(
        f"/research/derived-assets/merge/reviews/{review['review_id']}/apply",
        json={"operation_id": operation_id},
    )
    assert applied.status_code == 200
    assert applied.headers["cache-control"] == "no-store"
    assert applied.json()["operation_id"] == operation_id
    assert applied.json()["generation"] == 1

    replay = client.post(
        f"/research/derived-assets/merge/reviews/{review['review_id']}/apply",
        json={"operation_id": operation_id},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True

    asset_id = applied.json()["derived_asset_id"]
    revision_id = applied.json()["revision_id"]
    content_sha256 = applied.json()["content_sha256"]
    restore_body = {
        "operation_id": "op_" + "4" * 32,
        "selected_revision_id": revision_id,
        "expected_revision_id": revision_id,
        "expected_content_sha256": content_sha256,
        "expected_generation": 1,
    }
    refused_no_op = client.post(
        f"/research/derived-assets/merge/assets/{asset_id}/restore", json=restore_body
    )
    assert refused_no_op.status_code == 409
    assert refused_no_op.headers["cache-control"] == "no-store"

    stale = client.post(
        f"/research/derived-assets/merge/assets/{asset_id}/restore",
        json={**restore_body, "operation_id": "op_" + "5" * 32},
    )
    assert stale.status_code == 409
    assert stale.headers["cache-control"] == "no-store"
    assert stale.json() == {"detail": "merge command refused"}
    foreign_restore = client.post(
        f"/research/derived-assets/merge/assets/{asset_id}/restore",
        json={**restore_body, "operation_id": "op_" + "6" * 32},
        headers={"x-owner": "owner-b"},
    )
    assert foreign_restore.status_code == 404
    assert foreign_restore.headers["cache-control"] == "no-store"
    assert foreign_restore.json() == {"detail": "merge authority not found"}
    forbidden_restore = client.post(
        f"/research/derived-assets/merge/assets/{asset_id}/restore",
        json={**restore_body, "operation_id": "op_" + "7" * 32, "canonical_html": "x"},
    )
    assert forbidden_restore.status_code == 422

    forbidden = client.post(
        f"/research/derived-assets/merge/reviews/{review['review_id']}/apply",
        json={"operation_id": "op_" + "2" * 32, "canonical_html": "<p>authority</p>"},
    )
    assert forbidden.status_code == 422
    foreign = client.post(
        f"/research/derived-assets/merge/reviews/{review['review_id']}/apply",
        json={"operation_id": "op_" + "3" * 32},
        headers={"x-owner": "owner-b"},
    )
    assert foreign.status_code == 404
    assert foreign.headers["cache-control"] == "no-store"
    assert foreign.json() == {"detail": "merge authority not found"}


def test_derived_asset_library_history_exact_previews_and_owner_scope(
    fixture: tuple[TestClient, MergeDraftRepository, str, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _repository, db_path, _object_path, projection_id = fixture
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    spend_db = Path(db_path).with_name("companion-spend.sqlite3")
    monkeypatch.setenv("ANTIEK_RESEARCH_SPEND_DB", str(spend_db))
    draft = client.post("/research/derived-assets/merge/drafts", json=payload(projection_id)).json()
    review = client.post(
        f"/research/derived-assets/merge/drafts/{draft['draft_id']}/reviews"
    ).json()
    created = client.post(
        f"/research/derived-assets/merge/reviews/{review['review_id']}/apply",
        json={"operation_id": "op_" + "8" * 32},
    ).json()
    asset_id, first_revision = created["derived_asset_id"], created["revision_id"]
    revise_draft = client.post(
        "/research/derived-assets/merge/drafts",
        json={
            **payload(projection_id),
            "intent": "revise",
            "target_asset_id": asset_id,
            "expected_parent_revision_id": first_revision,
            "expected_parent_sha256": created["content_sha256"],
        },
    ).json()
    revise_review = client.post(
        f"/research/derived-assets/merge/drafts/{revise_draft['draft_id']}/reviews"
    ).json()
    revised = client.post(
        f"/research/derived-assets/merge/reviews/{revise_review['review_id']}/apply",
        json={"operation_id": "op_" + "7" * 32, "expected_generation": 1},
    ).json()
    restored = client.post(
        f"/research/derived-assets/merge/assets/{asset_id}/restore",
        json={
            "operation_id": "op_" + "9" * 32,
            "selected_revision_id": first_revision,
            "expected_revision_id": revised["revision_id"],
            "expected_content_sha256": revised["content_sha256"],
            "expected_generation": 2,
        },
    ).json()

    discovered = client.get("/research/derived-assets")
    assert discovered.status_code == 200
    assert discovered.headers["cache-control"] == "private, no-store"
    assert client.get("/research/derived-assets?owner=owner-b").status_code == 422
    asset = discovered.json()["assets"][0]
    assert set(asset) == {"derived_asset_id", "title", "asset_kind", "current", "revision_count"}
    assert asset["derived_asset_id"] == asset_id and asset["revision_count"] == 3
    assert asset["current"] == {
        "revision_id": restored["revision_id"],
        "content_sha256": restored["content_sha256"],
        "generation": 3,
        "member_count": 1,
        "preview_url": f"/research/derived-assets/assets/{asset_id}/current/frame-preview",
    }

    history = client.get(f"/research/derived-assets/assets/{asset_id}/revisions")
    assert history.status_code == 200
    body = history.json()
    assert [item["revision_id"] for item in body["revisions"]] == [
        restored["revision_id"], revised["revision_id"], first_revision
    ]
    assert body["revisions"][0]["operation_kind"] == "restore"
    assert body["revisions"][0]["restored_from_revision_id"] == first_revision
    assert body["revisions"][1]["operation_kind"] == "revise"
    assert body["revisions"][2]["operation_kind"] == "create"
    assert all("created_at" not in repr(item) and "manifest" not in repr(item)
               for item in body["revisions"])

    current_preview = client.get(asset["current"]["preview_url"])
    exact_preview = client.get(body["revisions"][2]["preview_url"])
    assert current_preview.content == exact_preview.content
    for preview in (current_preview, exact_preview):
        assert preview.status_code == 200
        assert preview.headers["cache-control"] == "private, no-store"
        assert "frame-ancestors 'self'" in preview.headers["content-security-policy"]
        assert "sandbox" in preview.headers["content-security-policy"]
        assert preview.headers["x-content-type-options"] == "nosniff"
        assert preview.headers["referrer-policy"] == "no-referrer"

    current_reading_path = f"/research/derived-assets/assets/{asset_id}/reading"
    exact_reading_path = (
        f"/research/derived-assets/assets/{asset_id}/revisions/{first_revision}/reading"
    )
    current_reading = client.get(current_reading_path)
    exact_reading = client.get(exact_reading_path)
    assert current_reading.status_code == exact_reading.status_code == 200
    assert current_reading.headers["cache-control"] == "private, no-store"
    assert current_reading.json() == {
        "derived_asset_id": asset_id,
        "title": "Draft",
        "asset_kind": "analysis",
        "revision_id": restored["revision_id"],
        "content_sha256": restored["content_sha256"],
        "generation": 3,
        "member_count": 1,
        "is_current": True,
        "canonical_html": current_preview.text,
        "stable_reader_path": f"/read/derived/{asset_id}",
        "exact_reader_path": f"/read/derived/{asset_id}/revisions/{restored['revision_id']}",
    }
    assert exact_reading.json()["revision_id"] == first_revision
    assert exact_reading.json()["is_current"] is False
    assert exact_reading.json()["generation"] == 1
    assert exact_reading.json()["canonical_html"] == exact_preview.text
    current_search_path = f"/research/derived-assets/assets/{asset_id}/search"
    exact_search_path = (
        f"/research/derived-assets/assets/{asset_id}/revisions/{first_revision}/search"
    )
    current_search = client.post(current_search_path, json={"query": "Ready", "top_k": 3})
    exact_search = client.post(exact_search_path, json={"query": "Ready"})
    assert current_search.status_code == exact_search.status_code == 200
    assert current_search.headers["cache-control"] == "private, no-store"
    assert current_search.json()["revision_id"] == restored["revision_id"]
    assert current_search.json()["is_current"] is True
    assert exact_search.json()["revision_id"] == first_revision
    assert exact_search.json()["is_current"] is False
    assert current_search.json()["retrieval_mode"] == "deterministic_lexical_v1"
    assert current_search.json()["generation"] == 3
    assert len(current_search.json()["index_sha256"]) == 64
    assert current_search.json()["results"][0]["citation_id"].startswith("dchunk_")
    assert current_search.json()["results"][0]["text"] == "Ready\n\nup"
    assert len(current_search.json()["results"][0]["text_sha256"]) == 64
    pack = build_derived_revision_evidence_pack(
        db_path=db_path,
        owner_user_id="owner-a",
        asset_id=asset_id,
        revision_id=restored["revision_id"],
        question="Ready",
        top_k=3,
    )
    replay = build_derived_revision_evidence_pack(
        db_path=db_path,
        owner_user_id="owner-a",
        asset_id=asset_id,
        revision_id=restored["revision_id"],
        question="Ready",
        top_k=3,
    )
    assert replay == pack
    assert json.loads(canonical_evidence_json(pack)) == pack
    assert pack["pack_sha256"] == hashlib.sha256(
        canonical_evidence_json({key: value for key, value in pack.items()
                                 if key != "pack_sha256"}).encode()
    ).hexdigest()
    assert pack["citations"][0]["citation_id"] == current_search.json()["results"][0][
        "citation_id"
    ]
    citation = pack["citations"][0]
    source = DerivedCitationSource(
        derived_asset_id=asset_id,
        revision_id=restored["revision_id"],
        content_sha256=restored["content_sha256"],
        generation=3,
        citation_id=citation["citation_id"],
        chunk_ordinal=citation["chunk_ordinal"],
        chunk_text_sha256=citation["text_sha256"],
        excerpt=citation["text"],
    )
    assert verify_derived_citation_source(
        db_path=db_path, owner_user_id="owner-a", source=source
    ) == source
    with pytest.raises(DerivedCitationConflict):
        verify_derived_citation_source(
            db_path=db_path,
            owner_user_id="owner-a",
            source=source.model_copy(update={"chunk_text_sha256": "f" * 64}),
        )
    assert build_derived_revision_evidence_pack(
        db_path=db_path,
        owner_user_id="owner-a",
        asset_id=asset_id,
        question="absent",
    )["citations"] == []
    companion_path = f"/research/derived-assets/assets/{asset_id}/companion/evidence"
    companion_command = {
        "client_turn_id": "reader-turn-0001",
        "question": "Ready",
        "expected_revision_id": restored["revision_id"],
        "expected_content_sha256": restored["content_sha256"],
    }
    prepared = client.post(companion_path, json=companion_command)
    assert prepared.status_code == 200
    assert prepared.headers["cache-control"] == "private, no-store"
    assert prepared.json()["state"] == "evidence_ready"
    assert prepared.json()["replayed"] is False
    execution = prepared.json()["execution"]
    assert execution["schema_version"] == "antiek.derived-companion-execution.v1"
    assert execution["scope"] == {
        "derived_asset_id": asset_id,
        "revision_id": restored["revision_id"],
        "content_sha256": restored["content_sha256"],
        "generation": 3,
    }
    assert execution["available"] is False
    assert execution["reservable"] is False
    assert execution["dispatch_authorized"] is False
    assert execution["reason"] == "no_provider_route_qualified"
    assert execution["pricing_status"] == "unavailable"
    assert execution["recommended_ceiling_cents"] is None
    assert [route["provider"] for route in execution["routes"]] == [
        "exa", "openai", "perplexity", "tavily"
    ]
    replayed = client.post(companion_path, json=companion_command)
    assert replayed.status_code == 200 and replayed.json()["replayed"] is True
    answer_candidate = GroundedAnswerCandidate(claims=(
        AnswerClaimInput(
            text="The revision is ready.",
            citation_ids=(prepared.json()["evidence_pack"]["citations"][0]["citation_id"],),
        ),
        AnswerClaimInput(text="This remains an explicit unsupported observation."),
    ))
    admission_key = "answer-admission-0001"
    with pytest.raises(CompanionAnswerUnavailable):
        DerivedCompanionRepository(db_path=db_path).admit_answer(
            owner_user_id="owner-a", client_turn_id="reader-turn-0001",
            admission_key=admission_key, candidate=answer_candidate,
        )
    assert spend_db.exists() is False
    spend = ResearchSpendLedger(spend_db)
    spend.ensure_schema()
    binding = RunBinding(
        "companion-run-0001", "owner-a", "companion-session-0001",
        prepared.json()["evidence_pack"]["pack_sha256"], 1,
    )
    spend.create_or_reopen_run("create-companion-run-0001", binding, 20)
    turn_id = "dturn_" + hashlib.sha256(
        b"owner-a\0reader-turn-0001"
    ).hexdigest()[:32]
    hold = spend.reserve_paid(
        "reserve-companion-answer-0001", binding,
        PaidHoldIntent(
            reservation_key="companion-answer-reservation-0001",
            seam_id=COMPANION_SEAM_ID,
            provider="verified-provider",
            model="grounded-model",
            operation=COMPANION_OPERATION,
            operation_digest=companion_operation_digest(
                turn_id, prepared.json()["evidence_pack"]["pack_sha256"]
            ),
            projection_digest="8" * 64,
            rate_snapshot="verified-provider:2026-07-15",
            provider_idempotency_key="9" * 64,
        ),
        10,
    )
    spend.mark_dispatch_possible("dispatch-companion-answer-0001", hold.hold_id)
    spend.settle(
        "settle-companion-answer-0001", hold.hold_id, 7,
        companion_settlement_evidence(
            turn_id=turn_id,
            evidence_pack_sha256=prepared.json()["evidence_pack"]["pack_sha256"],
            output_digest=candidate_digest(answer_candidate),
            provider_response_digest="a" * 64,
        ),
    )
    verifier = SettledCompanionReceiptVerifier(spend, "owner-a", hold.hold_id)

    admitted = DerivedCompanionRepository(
        db_path=db_path, receipt_verifier=verifier,
    ).admit_answer(
        owner_user_id="owner-a", client_turn_id="reader-turn-0001",
        admission_key=admission_key, candidate=answer_candidate,
    )
    assert admitted["replayed"] is False
    assert admitted["unsupported_claim_count"] == 1
    assert "execution_receipt_id" not in admitted
    assert "execution_receipt_digest" not in admitted
    replayed_answer = DerivedCompanionRepository(db_path=db_path).admit_answer(
        owner_user_id="owner-a", client_turn_id="reader-turn-0001",
        admission_key=admission_key, candidate=answer_candidate,
    )
    assert replayed_answer == {**admitted, "replayed": True}
    with pytest.raises(CompanionAnswerConflict):
        DerivedCompanionRepository(db_path=db_path).admit_answer(
            owner_user_id="owner-a", client_turn_id="reader-turn-0001",
            admission_key=admission_key,
            candidate=GroundedAnswerCandidate(claims=(AnswerClaimInput(text="changed"),)),
        )
    with pytest.raises(CompanionAnswerUnavailable):
        DerivedCompanionRepository(db_path=db_path).admit_answer(
            owner_user_id="owner-b", client_turn_id="reader-turn-0001",
            admission_key=admission_key, candidate=answer_candidate,
        )
    refreshed = client.post(companion_path, json=companion_command).json()
    assert refreshed["answer"] == {key: value for key, value in replayed_answer.items()
                                    if key != "replayed"}
    assert client.post(companion_path.removesuffix("/evidence") + "/answer", json={}).status_code in (
        404, 405,
    )
    conflict = client.post(companion_path, json={**companion_command, "question": "up"})
    assert conflict.status_code == 409
    abstained = client.post(companion_path, json={
        **companion_command,
        "client_turn_id": "reader-turn-0002",
        "question": "absent",
    })
    assert abstained.status_code == 200
    assert abstained.json()["state"] == "insufficient_evidence"
    assert abstained.json()["evidence_pack"]["citations"] == []
    stale = client.post(companion_path, json={
        **companion_command,
        "client_turn_id": "reader-turn-0003",
        "expected_revision_id": first_revision,
        "expected_content_sha256": created["content_sha256"],
    })
    assert stale.status_code == 409
    assert stale.json()["current"]["revision_id"] == restored["revision_id"]
    exact_companion_path = (
        f"/research/derived-assets/assets/{asset_id}/revisions/{first_revision}"
        "/companion/evidence"
    )
    historical = client.post(exact_companion_path, json={
        "client_turn_id": "reader-turn-0004", "question": "Ready"
    })
    assert historical.status_code == 200
    assert historical.json()["scope"]["revision_id"] == first_revision
    assert historical.json()["scope"]["is_current"] is False
    conversation = client.get(
        f"/research/derived-assets/assets/{asset_id}/companion"
    )
    assert conversation.status_code == 200
    assert conversation.headers["cache-control"] == "private, no-store"
    assert conversation.json()["execution"] == execution
    assert conversation.json()["turns"][0]["answer"] == refreshed["answer"]
    assert [turn["question"] for turn in conversation.json()["turns"]] == [
        "Ready", "absent"
    ]
    exact_conversation = client.get(
        f"/research/derived-assets/assets/{asset_id}/revisions/{first_revision}/companion"
    )
    assert [turn["question"] for turn in exact_conversation.json()["turns"]] == ["Ready"]
    assert ResearchSpendLedger(spend_db).integrity_check() == "ok"
    with duckdb.connect(db_path, read_only=True) as con:
        turns = con.execute(
            "SELECT state,count(*) FROM derived_asset_companion_turns GROUP BY state ORDER BY state"
        ).fetchall()
        assert turns == [("evidence_ready", 2), ("insufficient_evidence", 1)]
        assert con.execute(
            "SELECT count(*) FROM derived_asset_companion_turn_citations"
        ).fetchone() == (2,)
        assert con.execute(
            "SELECT count(*) FROM derived_asset_companion_turn_citations "
            "WHERE used_in_answer=TRUE"
        ).fetchone() == (1,)
        assert con.execute(
            "SELECT count(*) FROM derived_asset_companion_answers"
        ).fetchone() == (1,)
        assert "<article" not in "".join(str(row[0]) for row in con.execute(
            "SELECT evidence_pack_json FROM derived_asset_companion_turns"
        ).fetchall())
    with connect_write(db_path, purpose="companion-composite-constraint-proof") as con:
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "UPDATE derived_asset_companion_threads SET derived_asset_id=?",
                ["ast_" + "f" * 32],
            )
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "UPDATE derived_asset_companion_turn_citations "
                "SET revision_id=? WHERE turn_id=?",
                [first_revision, "dturn_" + hashlib.sha256(
                    b"owner-a\0reader-turn-0001"
                ).hexdigest()[:32]],
            )
    assert client.post(current_search_path, json={"query": "absent"}).json()["results"] == []
    assert client.post(current_search_path, json={"query": "x", "unknown": True}).status_code == 422
    assert client.post(current_search_path, json={"query": "😀" * 3000}).status_code == 422
    assert client.get(current_reading_path + "?revision=forged").status_code == 422
    assert client.request("GET", current_reading_path, content=b"forged").status_code == 422
    with duckdb.connect(db_path, read_only=True) as con:
        projection = con.execute(
            "SELECT document_type,raw_text,owner_user_id,metadata FROM documents "
            "WHERE document_id=?", [asset_id]
        ).fetchone()
    assert projection is not None
    assert projection[:3] == ("derived_html", None, "owner-a")
    assert json.loads(projection[3]) == {
        "body_authority": "derived_asset_revisions", "derived_asset_id": asset_id
    }

    assert client.get(
        "/research/derived-assets", headers={"x-owner": "owner-b"}
    ).json()["assets"] == []
    for path in (
        f"/research/derived-assets/assets/{asset_id}/revisions",
        asset["current"]["preview_url"],
        body["revisions"][2]["preview_url"],
        current_reading_path,
        exact_reading_path,
    ):
        assert client.get(path, headers={"x-owner": "owner-b"}).status_code == 404
    for path in (current_search_path, exact_search_path):
        assert client.post(
            path, headers={"x-owner": "owner-b"}, json={"query": "Ready"}
        ).status_code == 404
    with connect_write(db_path, purpose="derived-index-tamper-proof") as con:
        con.execute(
            "UPDATE derived_asset_revision_indexes SET index_sha256=? "
            "WHERE derived_asset_id=? AND revision_id=?",
            ["f" * 64, asset_id, restored["revision_id"]],
        )
    assert client.post(current_search_path, json={"query": "Ready"}).status_code == 409


def test_derived_asset_library_refuses_member_drift(
    fixture: tuple[TestClient, MergeDraftRepository, str, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _repository, db_path, _object_path, projection_id = fixture
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    draft = client.post("/research/derived-assets/merge/drafts", json=payload(projection_id)).json()
    review = client.post(
        f"/research/derived-assets/merge/drafts/{draft['draft_id']}/reviews"
    ).json()
    applied = client.post(
        f"/research/derived-assets/merge/reviews/{review['review_id']}/apply",
        json={"operation_id": "op_" + "a" * 32},
    ).json()
    with connect_write(db_path, purpose="derived-library-member-drift") as con:
        con.execute(
            "UPDATE derived_asset_revision_members SET source_document_id='drifted' "
            "WHERE derived_asset_id=?",
            [applied["derived_asset_id"]],
        )
    assert client.get("/research/derived-assets").status_code == 409
    assert client.get(
        f"/research/derived-assets/assets/{applied['derived_asset_id']}/revisions"
    ).status_code == 409


def test_derived_asset_library_refuses_owned_missing_head_and_generation_drift(
    fixture: tuple[TestClient, MergeDraftRepository, str, Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _repository, db_path, _object_path, projection_id = fixture
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    with connect_write(db_path, purpose="derived-library-missing-head") as con:
        con.execute(
            "INSERT INTO derived_assets (derived_asset_id,title,asset_kind,owner_user_id) "
            "VALUES (?,?,?,?)",
            ["ast_" + "f" * 32, "Foreign incomplete", "analysis", "owner-b"],
        )
    assert client.get("/research/derived-assets").json()["assets"] == []
    assert client.get(
        "/research/derived-assets", headers={"x-owner": "owner-b"}
    ).status_code == 409

    draft = client.post("/research/derived-assets/merge/drafts", json=payload(projection_id)).json()
    review = client.post(
        f"/research/derived-assets/merge/drafts/{draft['draft_id']}/reviews"
    ).json()
    applied = client.post(
        f"/research/derived-assets/merge/reviews/{review['review_id']}/apply",
        json={"operation_id": "op_" + "b" * 32},
    ).json()
    with connect_write(db_path, purpose="derived-library-generation-drift") as con:
        con.execute(
            "UPDATE derived_asset_current_revisions SET generation=9 WHERE derived_asset_id=?",
            [applied["derived_asset_id"]],
        )
    assert client.get("/research/derived-assets").status_code == 409


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
