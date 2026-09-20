"""Provenance readers, MCP, provider inputs, and exports are separate owner sinks."""
from __future__ import annotations

import io
import zipfile
from unittest.mock import Mock

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph import insert_chunk, insert_document, insert_edge, insert_node
from tests import test_owner_read_path as owner_fixtures

db = owner_fixtures.db
owner_client = owner_fixtures.owner_client
_clean_registry = owner_fixtures._clean_registry
PROBE = "PUBLISHERCONFIDENTIALPROBE"


def seed(db, content_class="research_only", count=40):
    with connect_write(db, purpose="direct-reader-probe") as con:
        insert_document(con, document_id="doc-probe", title="Licensed title", source_tier=1,
                        document_type="book", content_class=content_class, raw_text=PROBE * 100)
        for index in range(count):
            insert_chunk(con, document_id="doc-probe", chunk_index=index, chunk_id=f"chunk-probe{index}",
                         text=f"{PROBE} quantum " + "x" * 600, section_path=f"page {index}",
                         embedding=owner_fixtures.StubEmbedding().encode("quantum"))
        insert_node(con, node_id="claim-probe", canonical_label="Derived claim", node_type="claim", graph_scope="depth", investigation_id="inv-probe")
        insert_node(con, node_id="entity-probe", canonical_label="Topic", node_type="entity", graph_scope="depth", investigation_id="inv-probe")
        insert_edge(con, source_node_id="claim-probe", target_node_id="entity-probe", relation="supports",
                    source_tier=1, extraction_confidence=1.0, graph_scope="depth", investigation_id="inv-probe",
                    chunk_id="chunk-probe0", source_document_id="doc-probe")
        con.execute("INSERT INTO syntheses (synthesis_id,investigation_id,target_question,synthesis_timestamp,status,implicit_recommendation) VALUES ('syn-probe','inv-probe','quantum',CURRENT_TIMESTAMP,'passed','proceed')")
        con.execute("INSERT INTO synthesis_substrate_manifest (synthesis_id,entity_kind,entity_id) VALUES ('syn-probe','document','doc-probe'),('syn-probe','chunk','chunk-probe0'),('syn-probe','node','claim-probe')")


@pytest.mark.parametrize("path", ["/docs/doc-probe/explain", "/claims/claim-probe/explain", "/syntheses/syn-probe/explain"])
@pytest.mark.parametrize("content_class", ["research_only", "public_domain"])
def test_explain_preserves_identity_without_licensed_body(db, owner_client, path, content_class):
    seed(db, content_class)
    response = owner_client.get(path, headers=owner_fixtures._OWNER_HEADERS)
    assert response.status_code == 200, response.text
    assert "chunk-probe0" in response.text
    assert "Licensed title" in response.text
    assert (PROBE in response.text) is (content_class == "public_domain")
    if path.startswith("/docs/"):
        assert len(response.json()["chunks"]) == 40
        if content_class == "research_only":
            assert all(c["text"] is None for c in response.json()["chunks"])


@pytest.mark.parametrize("surface", ["search_personal", "search_public", "resource"])
@pytest.mark.parametrize("content_class", ["research_only", "public_domain"])
def test_mcp_readers_respect_body_rights(db, surface, content_class):
    from tools.antiek_memory.__main__ import _make_handlers

    seed(db, content_class, count=1)
    handlers, resource = _make_handlers(db)
    result = resource("antiek://books/123/chunk-probe0") if surface == "resource" else handlers[surface]({"query": "quantum"})
    assert (PROBE in str(result)) is (content_class == "public_domain")


@pytest.mark.parametrize("surface", ["wrestling", "multimedia", "source_card", "diagram"])
@pytest.mark.parametrize("content_class", ["research_only", "public_domain"])
def test_owner_selected_chunk_inputs(db, surface, content_class):
    seed(db, content_class, count=1)
    if surface == "wrestling":
        from interfaces.research.api.wrestling import _resolve_region_text_from_db
        result = _resolve_region_text_from_db(db, "r-probe0")
        assert (PROBE in str(result)) is (content_class == "public_domain")
        return
    from substrate.multimedia.diagram_evidence_authority import (
        DiagramEvidenceAuthorityError,
        _chunk_snapshot_on,
    )
    from substrate.multimedia.graph_evidence import _load_snapshots
    from substrate.multimedia.local_source_card import LocalSourceCardError, _snapshot

    with connect_write(db, purpose="direct-reader-check") as con:
        if surface == "multimedia":
            def call():
                return _load_snapshots(con, ("chunk-probe0",), owner_id="__operator__")
        elif surface == "diagram":
            def call():
                return _chunk_snapshot_on(con, ("chunk-probe0",))
        else:
            # Source card opens its own read connection, after this writer closes.
            call = None
        if call is not None:
            if content_class == "research_only":
                with pytest.raises((ValueError, DiagramEvidenceAuthorityError)):
                    call()
            else:
                result = call()
                assert "chunk-probe0" in str(result)
                if surface == "multimedia":
                    assert PROBE in str(result)
    if surface == "source_card":
        if content_class == "research_only":
            with pytest.raises(LocalSourceCardError):
                _snapshot(db, ("chunk-probe0",), expected_owner_id="__operator__")
        else:
            assert PROBE in str(_snapshot(db, ("chunk-probe0",), expected_owner_id="__operator__"))


@pytest.mark.parametrize("sealed", [False, True])
def test_export_of_normal_research_projects_events_and_retains_notes(db, owner_client, tmp_path, sealed):
    from substrate.event_log import emit_typed, seal_investigation, trajectory
    from substrate.schemas import EvidenceRetrieveDeliveredPayload, EvidenceRetrieveRequestedPayload

    emit_typed("inv-export", EvidenceRetrieveRequestedPayload(sub_question="quantum", category="market_sizing",
               evidence_type_required="quantitative", chunks_block=PROBE, subgraph_block=PROBE))
    emit_typed("inv-export", EvidenceRetrieveDeliveredPayload(sub_question="quantum", answer="Derived analysis"))
    if sealed:
        seal_investigation("inv-export")
    response = owner_client.get("/export/my-graph", headers=owner_fixtures._OWNER_HEADERS)
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        name = "events/inv-export." + ("parquet" if sealed else "jsonl")
        data = bundle.read(name)
    if sealed:
        path = tmp_path / "export.parquet"
        path.write_bytes(data)
        with duckdb.connect(":memory:") as con:
            exported = str(con.execute("SELECT * FROM read_parquet(?)", [str(path)]).fetchall())
    else:
        exported = data.decode()
    assert PROBE not in exported
    assert "Derived analysis" in exported
    assert PROBE in str(trajectory("inv-export")), "export must not change the internal agent log"


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_model", [False, True])
async def test_buyer_provider_does_not_gain_agent_read_authority(db, monkeypatch, owner_model):
    from interfaces.research.api import research_owner_dispatch as authority
    from interfaces.research.api.settings_models_admin import UserModelChoice
    from orchestration.loop_one.orchestrator import _render_chunks_block_for_sub_question_async
    from processing.embedding import embed

    seed(db, count=1)
    monkeypatch.setattr(embed, "default_embedding_provider", lambda: owner_fixtures.StubEmbedding())
    token = None
    if owner_model:
        choice = UserModelChoice(authority="user_model", provider_id="buyer-provider", model_id="buyer-model")
        token = authority.install_manifest(authority.ResearchOwnerManifest(Mock(), "payer", "inv-probe", "launch-probe", {r: choice for r in authority.PAID_LOOP_ONE_ROLES}))
    try:
        block = await _render_chunks_block_for_sub_question_async("quantum", policy_tag="private_research")
        assert (PROBE in block) is not owner_model
    finally:
        if token is not None:
            authority.reset_manifest(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("content_class", ["research_only", "public_domain", "missing"])
async def test_historical_evidence_replay_cannot_send_body_to_buyer_provider(db, monkeypatch, content_class):
    from interfaces.research.api import research_owner_dispatch as authority
    from interfaces.research.api.broadcast import EventBroadcaster
    from interfaces.research.api.evidence_retriever import make_evidence_retriever_handler
    from interfaces.research.api.settings_models_admin import UserModelChoice
    from orchestration.loop_one.coordinator import broadcast_emit
    from substrate.schemas import ActionType, EvidenceRetrieveRequestedPayload

    if content_class != "missing":
        seed(db, content_class, count=1)
    captured = []

    def capture(**kwargs):
        captured.append(kwargs)
        raise RuntimeError("STOP before provider call")

    monkeypatch.setattr(authority, "dispatch_talk_to_book_byot", capture)
    choice = UserModelChoice(authority="user_model", provider_id="buyer-provider", model_id="buyer-model")
    token = authority.install_manifest(authority.ResearchOwnerManifest(Mock(), "payer", "inv-probe", "launch-probe", {r: choice for r in authority.PAID_LOOP_ONE_ROLES}))
    bus = EventBroadcaster()
    bus.register_handler(ActionType.EVIDENCE_RETRIEVE_REQUESTED.value, make_evidence_retriever_handler(bus))
    try:
        await broadcast_emit(bus, "inv-probe", EvidenceRetrieveRequestedPayload(sub_question="quantum", category="market_sizing", evidence_type_required="quantitative", chunks_block="### chunk_id: chunk-probe0\n" + PROBE, subgraph_block=""))
        await bus.wait_for_handlers()
    finally:
        authority.reset_manifest(token)
    assert bool(captured) is (content_class == "public_domain")
    if captured:
        assert PROBE in captured[0]["prompt"]


@pytest.mark.parametrize("content_class", ["research_only", "public_domain"])
def test_mcp_citation_metadata_stays_available(db, content_class):
    from tools.antiek_memory.__main__ import _make_handlers
    seed(db, content_class, count=1)
    handlers, _ = _make_handlers(db)
    result = handlers["cite_source"]({"id": "chunk-probe0"})
    assert "Licensed title" in str(result)
    assert PROBE not in str(result)


def test_export_omits_persisted_agent_prompts_after_source_removal(db, owner_client, tmp_path):
    with connect_write(db, purpose="seed-private-replay") as con:
        con.execute("""INSERT INTO note_taker_windows
            (window_id,consumer_version,investigation_id,threshold,ordinal,
             first_event_id,last_event_id,source_event_ids_json,source_digest,
             request_json,request_sha256,provider_idempotency_key,state)
            VALUES ('window',1,'inv-export',1,0,'first','last','[]',?,?,?,'key','prepared')
        """, ["0" * 64, '{"prompt":"' + PROBE + '"}', "0" * 64])
    response = owner_client.get("/export/my-graph", headers=owner_fixtures._OWNER_HEADERS)
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        data = bundle.read("graph/note_taker_windows.parquet")
    path = tmp_path / "windows.parquet"
    path.write_bytes(data)
    with duckdb.connect(":memory:") as con:
        assert con.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0] == 0
    with connect_write(db, purpose="verify-private-replay-unchanged") as con:
        assert PROBE in con.execute("SELECT request_json FROM note_taker_windows").fetchone()[0]


@pytest.mark.parametrize("content_class", ["research_only", "public_domain"])
def test_sidecar_voice_reference_cannot_read_licensed_document(db, content_class):
    from services.antiek_format.sidecar_writer import _gather_anchors_and_audio
    seed(db, content_class, count=1)
    with connect_write(db, purpose="seed-anchor") as con:
        con.execute("""CREATE TABLE voice_note_anchor (
            anchor_id TEXT, voice_note_id TEXT, document_id TEXT, page INTEGER,
            bbox TEXT, chunk_id TEXT, chunker_version TEXT, created_at TIMESTAMP)""")
        con.execute("INSERT INTO voice_note_anchor VALUES ('anchor','doc-probe','owner-doc',1,'{}',NULL,'v1',CURRENT_TIMESTAMP)")
    anchors, _ = _gather_anchors_and_audio(document_id="owner-doc", db_path=str(db))
    assert len(anchors) == 1
    assert (PROBE in str(anchors[0].transcript)) is (content_class == "public_domain")


@pytest.mark.parametrize("block", ["unstructured confidential context", "### chunk_id: chunk-probe0\nFORGED_BODY"])
def test_owner_provider_context_is_rebuilt_not_trusted(db, block):
    from interfaces.research.api.research_owner_dispatch import (
        OwnerLaunchConflict,
        _owner_evidence_prompt,
    )
    from substrate.schemas import EvidenceRetrieveRequestedPayload
    seed(db, "public_domain", count=1)
    req = EvidenceRetrieveRequestedPayload(sub_question="quantum\n[unrelated-id]", category="market_sizing",
        evidence_type_required="quantitative", chunks_block=block, subgraph_block="FORGED_GRAPH_CONTEXT")
    if block.startswith("unstructured"):
        with pytest.raises(OwnerLaunchConflict):
            _owner_evidence_prompt(req, owner_user_id="__operator__")
    else:
        prompt = _owner_evidence_prompt(req, owner_user_id="__operator__")
        assert PROBE in prompt
        assert "FORGED_BODY" not in prompt
        assert "FORGED_GRAPH_CONTEXT" not in prompt


@pytest.mark.parametrize("policy_tag", ["operator_only", "private_research", "unknown"])
def test_vector_sql_reader_keeps_principals_separate(db, policy_tag):
    from substrate.graph.retrieval_substrate import DuckDbVssSubstrate
    model = owner_fixtures.StubEmbedding()
    with connect_write(db, purpose="vss-seed") as con:
        insert_document(con, document_id="vector-doc", title="Licensed", source_tier=1,
                        document_type="book", content_class="research_only")
        insert_chunk(con, document_id="vector-doc", chunk_id="vector-chunk", chunk_index=0,
                     text=PROBE, embedding=model.encode("quantum"))
    with connect_write(db, purpose="vss-reader-probe") as con:
        con.execute(f"ALTER TABLE chunks ADD COLUMN embedding_vss FLOAT[{model.dimension}]")
        con.execute(f"UPDATE chunks SET embedding_vss = embedding::FLOAT[{model.dimension}]")
        substrate = DuckDbVssSubstrate(con, model=model, vss_active=True)
        result = substrate._vss_query("quantum", top_k=5, source_tier_max=None, document_ids=None, policy_tag=policy_tag)
    assert (PROBE in str(result)) is (policy_tag == "private_research")


@pytest.mark.parametrize("restriction", ["foreign_owner", "taken_down"])
def test_owner_provider_replay_retains_ownership_and_takedown_checks(db, restriction):
    from interfaces.research.api.research_owner_dispatch import (
        OwnerLaunchConflict,
        _owner_evidence_prompt,
    )
    from substrate.schemas import EvidenceRetrieveRequestedPayload
    seed(db, "personal_reading" if restriction == "foreign_owner" else "public_domain", count=1)
    if restriction == "taken_down":
        with connect_write(db, purpose="takedown-probe") as con:
            con.execute("INSERT INTO book_assets (document_id,taken_down) VALUES ('doc-probe',TRUE)")
    request = EvidenceRetrieveRequestedPayload(sub_question="quantum", category="market_sizing",
        evidence_type_required="quantitative", chunks_block="### chunk_id: chunk-probe0\n" + PROBE, subgraph_block="")
    with pytest.raises(OwnerLaunchConflict):
        _owner_evidence_prompt(request, owner_user_id="another-buyer")
