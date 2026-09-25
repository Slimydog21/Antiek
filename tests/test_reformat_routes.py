"""Reformat route proofs (reformat-provenance SPR-02).

FastAPI TestClient against a REAL DuckDB fixture: POST reformat runs the
pipeline (the generator injected at the documented seam) and returns the
generation + derived document; the provenance GET carries the record +
per-bite classes + server-resolved page hints + byte-verified flags; a
plain document 404s; the owner boundary holds; a gated source's refusal is
an honest 422.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database_at_path
from tests.test_reformat_pipeline import BODY, CHUNKS


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    db = tmp_path / "t.duckdb"
    events = tmp_path / "events"
    arts = tmp_path / "artifacts"
    events.mkdir()
    arts.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(arts))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    init_database_at_path(str(db))
    return {"db": str(db), "events": str(events), "arts": str(arts)}


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False))


def _seed(db: str, document_id: str = "doc-1", content_class: str = "public_domain") -> None:
    with connect_write(db, purpose="test/seed-reformat-route") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title="The Pricing Book",
            raw_text=BODY,
            content_class=content_class,
            on_conflict="ignore",
        )
        for i, (chunk_id, section, text) in enumerate(CHUNKS):
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
                "section_path, text, token_count) VALUES (?, ?, ?, ?, ?, ?)",
                [f"{chunk_id}-{document_id}", document_id, i, section, text, len(text.split())],
            )


def _fixture_generator(prompt, blocks, params):
    from substrate.reformat.pipeline import GeneratedBite

    return [
        GeneratedBite(
            text=blocks[0].text,
            contribution_class="author_verbatim",
            source_block_indices=(0,),
        ),
        GeneratedBite(
            text="pricing, compressed",
            contribution_class="llm_compressed",
            source_block_indices=(0,),
        ),
        GeneratedBite(
            text="the diligence note, woven in",
            contribution_class="research_supplemented",
            source_block_indices=(2,),
            investigation_id="inv-dil-1",
        ),
        GeneratedBite(
            text="The conclusion, expanded with the operator's margins in view.",
            contribution_class="llm_expanded",
            source_block_indices=(2,),
        ),
        # One honestly novel connective line — at the ceiling (1 of 5 = 20%,
        # NOT past it), the asset does NOT flip.
        GeneratedBite(
            text="a novel connective line, honestly sourceless",
            contribution_class="llm_expanded",
            source_block_indices=None,
        ),
    ]


@pytest.fixture
def generator_override(monkeypatch):
    import interfaces.research.api.reformat_routes as routes

    monkeypatch.setattr(routes, "_generate_fn_override", _fixture_generator)
    yield
    monkeypatch.setattr(routes, "_generate_fn_override", None)


def test_post_reformat_runs_the_pipeline(api_env, generator_override) -> None:
    _seed(api_env["db"])
    client = _client()
    resp = client.post(
        "/books/doc-1/reformats",
        json={"prompt": "the 20-minute version", "mode": "time_window"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["derived_document_id"].startswith("drv-")
    assert body["thread_id"] == f"reformat:{body['generation_id']}"
    assert body["contribution_classes"] == [
        "author_verbatim",
        "llm_compressed",
        "research_supplemented",
        "llm_expanded",
        "llm_expanded",  # the honestly novel connective line
    ]
    assert body["mostly_generated"] is False


def test_provenance_get_carries_the_record_and_bites(api_env, generator_override) -> None:
    _seed(api_env["db"])
    client = _client()
    created = client.post(
        "/books/doc-1/reformats", json={"prompt": "the 20-minute version"}
    ).json()
    resp = client.get(f"/documents/{created['derived_document_id']}/provenance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["generation"]["prompt"] == "the 20-minute version"
    assert body["generation"]["source_document_id"] == "doc-1"
    bites = body["bites"]
    assert [b["ordinal"] for b in bites] == [0, 1, 2, 3, 4]
    # Byte-verified flag recomputed server-side.
    assert bites[0]["byte_verified"] is True
    assert bites[1]["byte_verified"] is False
    # The trace jump's page hint resolves server-side (chunk c-1 → page 1 → 0).
    assert bites[0]["source_refs"][0]["node_id"] == "c-1-doc-1"
    assert bites[0]["source_page_hints"] == [0]
    # The supplemented bite cites its core span AND its investigation.
    assert bites[2]["investigation_id"] == "inv-dil-1"
    assert bites[2]["source_refs"][0]["node_id"] == "c-2-doc-1"
    # The null-source bite is honestly null.
    assert bites[4]["source_refs"] is None


def test_provenance_404s_for_a_plain_document(api_env) -> None:
    _seed(api_env["db"])
    client = _client()
    assert client.get("/documents/doc-1/provenance").status_code == 404


def test_owner_boundary_and_gated_refusal(api_env, generator_override) -> None:
    _seed(api_env["db"])
    _seed(api_env["db"], document_id="doc-gated", content_class="personal_reading")
    client = _client()

    # A taken-down source refuses honestly (nothing to reformat).
    with connect_write(api_env["db"], purpose="test/takedown") as con:
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) "
            "VALUES ('doc-gated', TRUE) ON CONFLICT DO NOTHING"
        )
    refused = client.post(
        "/books/doc-gated/reformats", json={"prompt": "compress it"}
    )
    assert refused.status_code == 422

    # The owner boundary: re-key the derived document, the GET 404s.
    created = client.post(
        "/books/doc-1/reformats", json={"prompt": "the 20-minute version"}
    ).json()
    with connect_write(api_env["db"], purpose="test/rekey") as con:
        con.execute(
            "UPDATE documents SET owner_user_id = 'someone-else' WHERE document_id = ?",
            [created["derived_document_id"]],
        )
    assert (
        client.get(f"/documents/{created['derived_document_id']}/provenance").status_code
        == 404
    )


# ── Review hardening (2026-09-25): the reformat writer is owner-scoped. A
# caller may only reformat a document they own — the same boundary every
# sibling route enforces. ──────────────────────────────────────────────────


def test_reformat_requires_the_source_owner(api_env, monkeypatch) -> None:
    from runtime.db_lock import connect_write

    with connect_write(api_env["db"], purpose="test/seed-other-owner") as con:
        insert_document(
            con,
            document_id="doc-other-owner",
            source_tier=2,
            document_type="book",
            title="Someone Else's Private Book",
            raw_text=BODY,
            content_class="personal_reading",
            owner_user_id="owner-b",
            on_conflict="ignore",
        )
        for i, (chunk_id, section, text) in enumerate(CHUNKS):
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
                "section_path, text, token_count) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    f"{chunk_id}-doc-other-owner",
                    "doc-other-owner",
                    i,
                    section,
                    text,
                    len(text.split()),
                ],
            )
    from interfaces.research.api import reformat_routes

    monkeypatch.setattr(reformat_routes, "_reader_owner_id", lambda request: "owner-a")
    client = TestClient(create_app(register_wrestling=False))
    denied = client.post(
        "/books/doc-other-owner/reformats",
        json={"prompt": "the 20-minute version", "mode": "time_window"},
    )
    assert denied.status_code == 404
    assert denied.json()["detail"] == "book_not_found"

    monkeypatch.setattr(reformat_routes, "_generate_fn_override", _fixture_generator)
    monkeypatch.setattr(reformat_routes, "_reader_owner_id", lambda request: "owner-b")
    allowed = client.post(
        "/books/doc-other-owner/reformats",
        json={"prompt": "the 20-minute version", "mode": "time_window"},
    )
    assert allowed.status_code == 201
    assert allowed.json()["bite_count"] > 0


@pytest.fixture(autouse=True)
def _scrub_operator_auth_env(monkeypatch):
    """Environment invariance (review F2): these suites must pass on the
    operator's own Mac, where the login shell exports the operator-auth
    env — otherwise the middleware answers 401 and CI-clean tests fail
    locally. Scrub the credential env for every test in this module."""
    for key in (
        "ANTIEK_AUTH_SECRET",
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_COOKIE_INSECURE",
    ):
        monkeypatch.delenv(key, raising=False)


# ── Review hardening F4 (2026-09-25): load-bearing invariants must survive
# `python -O`. A vanished generation record (FK-impossible, monkeypatched
# here) surfaces as an honest explicit error, never a silently-skipped
# check. ──────────────────────────────────────────────────────────────────


def test_vanished_generation_record_is_an_explicit_error(api_env, monkeypatch) -> None:
    from substrate.provenance.store import ProvenanceStore
    from substrate.reformat.pipeline import reformat_document

    _seed(api_env["db"])
    result = reformat_document(
        api_env["db"],
        owner_user_id="__operator__",
        source_document_id="doc-1",
        prompt="the 20-minute version",
        generate_fn=_fixture_generator,
        events_dir=api_env["events"],
    )
    client = _client()
    monkeypatch.setattr(
        ProvenanceStore, "get_generation", lambda self, con, gid: None
    )
    resp = client.get(f"/documents/{result.derived_document_id}/provenance")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "provenance_record_missing"
