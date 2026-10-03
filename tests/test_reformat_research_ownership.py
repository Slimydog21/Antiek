"""Ownership boundary: real graph products, gated bodies, persisted provenance."""

from __future__ import annotations

import json

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.event_log import trajectory
from substrate.graph.insight_question import promote_insight, promote_question
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database_at_path
from substrate.provenance.store import ProvenanceStore
from substrate.reformat.pipeline import GeneratedBite, reformat_document

BODY = "The factory makes 100 parts daily."


@pytest.fixture
def boundary_env(tmp_path, monkeypatch):
    db = str(tmp_path / "boundary.duckdb")
    events = str(tmp_path / "events")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    init_database_at_path(db)
    return db, events


def seed_document(db, document_id, owner, content_class="public_domain", *, metadata=None):
    with connect_write(db, purpose="test/boundary-source") as con:
        insert_document(
            con, document_id=document_id, source_tier=2, document_type="web",
            title=document_id, raw_text=BODY, content_class=content_class,
            owner_user_id=owner, metadata=metadata,
        )
        con.execute(
            "INSERT INTO chunks(chunk_id, document_id, chunk_index, text, token_count) "
            "VALUES (?, ?, 0, ?, 7)", [document_id + "-chunk", document_id, BODY],
        )


def seed_product(inv, node_owner, source, *, question=False):
    promote = promote_question if question else promote_insight
    return promote(
        text="The production evidence for " + inv + str(node_owner) + str(source),
        investigation_id=inv, source_document_id=source, owner_user_id=node_owner,
    )


def generate_for(inv):
    def generate(prompt, blocks, params):
        return [GeneratedBite(
            text="The research confirms a 100-part daily rate.",
            contribution_class="research_supplemented",
            source_block_indices=(0,), investigation_id=inv,
        )]
    return generate


def run_reformat(db, events, inv, caller="alice"):
    return reformat_document(
        db, owner_user_id=caller, source_document_id="base-" + caller,
        prompt="Summarize the production research.", generate_fn=generate_for(inv),
        events_dir=events,
    )


@pytest.mark.parametrize(
    "case,node_owner,source_owner,content_class,accepted",
    [
        ("same-owner", "alice", "alice", "personal_reading", True),
        ("nonexistent", "alice", "alice", "public_domain", False),
        ("foreign-private", "bob", "bob", "personal_reading", False),
        ("mixed-owner", "bob", "bob", "personal_reading", False),
        ("owned-node-foreign-private-source", "alice", "bob", "personal_reading", False),
        ("foreign-node-public-source", "bob", "alice", "public_domain", False),
        ("shared-public-source", None, "bob", "public_domain", True),
        ("legacy-owned-private-source", None, "alice", "personal_reading", True),
        ("legacy-foreign-private-source", None, "bob", "personal_reading", False),
        ("legacy-unknown-source", None, "alice", "public_domain", False),
        ("owned-unknown-source", "alice", "alice", "public_domain", False),
        ("missing-grounding", "alice", "alice", "public_domain", False),
        ("restricted-source", "alice", "alice", "restricted_pending_opt_in", False),
        ("taken-down", "alice", "alice", "public_domain", False),
        ("license-drift", "alice", "alice", "public_domain", False),
        ("blank-owner", "", "alice", "public_domain", False),
        ("mixed-unknown", "alice", "alice", "public_domain", False),
    ],
)
def test_provenance_requires_the_complete_readable_product(
    boundary_env, case, node_owner, source_owner, content_class, accepted,
):
    db, events = boundary_env
    seed_document(db, "base-alice", "alice")
    seed_document(db, "support", source_owner, content_class)
    source = None if case == "missing-grounding" else "support"
    if "unknown" in case:
        source = "unknown-source"
    if case != "nonexistent":
        seed_product(case, node_owner, source)
    if case in {"mixed-owner", "mixed-unknown"}:
        seed_product(case, "alice", "base-alice", question=True)
    if case == "taken-down":
        with connect_write(db, purpose="test/boundary-takedown") as con:
            con.execute("INSERT INTO book_assets(document_id,taken_down) VALUES ('support',TRUE)")
    if case == "license-drift":
        with connect_write(db, purpose="test/boundary-drift") as con:
            con.execute("UPDATE documents SET metadata=? WHERE document_id='support'", [
                json.dumps({"license_uri": "http://arxiv.org/licenses/nonexclusive-distrib/1.0/", "arxiv_id": "2401.00001"}),
            ])
    result = run_reformat(db, events, case)
    with connect_read(db) as con:
        bite = ProvenanceStore().bites_for_generation(con, result.generation_id)[0]
    audits = [
        row["payload"] for row in trajectory("read-base-alice", events_dir=events)
        if row["action_type"] == "reformat.research_reclassified"
    ]
    print("BOUNDARY", json.dumps({
        "case": case, "caller": "alice", "class": bite.contribution_class,
        "investigation_id": bite.investigation_id,
        "reclassed_research": result.reclassed_research, "audits": audits,
    }, sort_keys=True))
    assert result.contribution_classes == ["research_supplemented" if accepted else "llm_expanded"]
    assert bite.investigation_id == (case if accepted else None)
    assert result.reclassed_research == int(not accepted)
    assert bool(audits) is not accepted
    if not accepted:
        assert audits[0]["reclassed"] == 1
        assert audits[0]["investigation_ids"] == [case]
    # Access does not change the independently validated core source span.
    assert bite.source_refs == ("corespan:base-alice:base-alice-chunk:0:34",)


def test_the_other_owner_can_keep_the_same_private_product(boundary_env):
    db, events = boundary_env
    seed_document(db, "base-alice", "alice")
    seed_document(db, "base-bob", "bob")
    seed_document(db, "private-source", "bob", "personal_reading")
    seed_product("private-research", "bob", "private-source")
    alice = run_reformat(db, events, "private-research", "alice")
    bob = run_reformat(db, events, "private-research", "bob")
    print("BOTH_OWNERS", json.dumps({
        "alice": alice.contribution_classes, "bob": bob.contribution_classes,
        "alice_downgrades": alice.reclassed_research, "bob_downgrades": bob.reclassed_research,
    }))
    assert alice.contribution_classes == ["llm_expanded"]
    assert bob.contribution_classes == ["research_supplemented"]
    assert (alice.reclassed_research, bob.reclassed_research) == (1, 0)


@pytest.mark.parametrize(
    "case,products,expected_counts,expected_classes",
    [
        ("same-owner", [("alice", "alice", "personal_reading")], (1, 0), ("research_supplemented", "llm_expanded")),
        ("nonexistent", [], (0, 0), ("llm_expanded", "llm_expanded")),
        ("foreign-private", [("bob", "bob", "personal_reading")], (0, 1), ("llm_expanded", "research_supplemented")),
        ("mixed-owner", [("alice", "alice", "personal_reading"), ("bob", "bob", "personal_reading")], (1, 1), ("llm_expanded", "llm_expanded")),
        ("shared-public", [(None, "bob", "public_domain")], (1, 1), ("research_supplemented", "research_supplemented")),
        ("legacy-private", [(None, "bob", "personal_reading")], (0, 1), ("llm_expanded", "research_supplemented")),
        ("legacy-unknown", [(None, "bob", None)], (0, 0), ("llm_expanded", "llm_expanded")),
        ("owned-node-foreign-source", [("alice", "bob", "personal_reading")], (0, 0), ("llm_expanded", "llm_expanded")),
    ],
)
def test_distill_and_provenance_as_both_authenticated_owners(
    boundary_env, monkeypatch, case, products, expected_counts, expected_classes,
):
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app
    from substrate.auth import mint_session_cookie

    db, events = boundary_env
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "d6-hermetic-signing-secret-not-a-credential")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "alice@example.test,bob@example.test")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    for caller in ("alice", "bob"):
        seed_document(db, "base-" + caller, caller)
    node_ids = []
    for index, (node_owner, source_owner, content_class) in enumerate(products):
        source = f"support-{index}"
        if content_class:
            seed_document(db, source, source_owner, content_class)
        node_ids.append(seed_product(case, node_owner, source, question=index == 1))
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    anonymous = TestClient(app)
    assert anonymous.get(f"/research/{case}/distill").status_code == 401
    observed = []
    for caller in ("alice", "bob"):
        client = TestClient(app)
        client.cookies.set("ANTIEK_SESSION", mint_session_cookie(
            user_id=caller, email=caller + "@example.test",
        ))
        identity = client.get("/auth/me")
        assert identity.status_code == 200
        assert identity.json()["user_id"] == caller
        response = client.get(f"/research/{case}/distill")
        assert response.status_code == 200
        result = run_reformat(db, events, case, caller)
        provenance = client.get(f"/documents/{result.derived_document_id}/provenance")
        assert provenance.status_code == 200
        sources = []
        for source_index, (_, source_owner, content_class) in enumerate(products):
            source = f"support-{source_index}"
            metadata = client.get(f"/books/{source}")
            full_text = client.get(f"/books/{source}/full-text")
            passage = client.get(
                f"/books/{source}/passage?chunk_id={source}-chunk&start_scalar=0&end_scalar=34"
            )
            sources.append({
                "source": source, "metadata_status": metadata.status_code,
                "public_body": full_text.json().get("full_text"),
                "passage_status": passage.status_code, "passage_body": passage.json().get("text"),
            })
            if content_class and source_owner == caller:
                assert passage.status_code == 200
                assert passage.json()["text"] == BODY
            else:
                assert passage.status_code == 404
            if content_class == "public_domain":
                assert full_text.json()["full_text"] == BODY
            else:
                assert full_text.json().get("full_text") is None
        observed.append({
            "case": case, "caller": caller, "identity": identity.json(),
            "distill_status": response.status_code, "distill": response.json(),
            "provenance": provenance.json()["bites"], "sources": sources,
        })
        print("API_BOUNDARY", json.dumps(observed[-1], sort_keys=True))
    # Check after both requests so a regression still records the authorized run.
    for index, record in enumerate(observed):
        nodes = record["distill"]["insights"] + record["distill"]["questions"]
        assert len(nodes) == expected_counts[index]
        assert record["provenance"][0]["contribution_class"] == expected_classes[index]
        expected_id = case if expected_classes[index] == "research_supplemented" else None
        assert record["provenance"][0]["investigation_id"] == expected_id
        for node in nodes:
            assert node["node_id"] in node_ids
            assert node["text"].startswith("The production evidence for " + case)
        for node_index, (node_owner, _, _) in enumerate(products):
            if node_owner not in (None, record["caller"]):
                assert node_ids[node_index] not in json.dumps(record["distill"])
