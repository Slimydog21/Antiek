"""DOGFOOD SPR-03 M4 — the loop-closes reproducibility test.

Proves the research→synthesis deposit is not a one-off: against a tmp
ANTIEK_HOME + a fixture corpus + mocked dispatch, launching an
investigation deposits a ``syntheses`` row whose
``synthesis_substrate_manifest`` is non-empty and joins to a real fixture
document.

Before SPR-03 the completion path emitted ``INVESTIGATION_COMPLETED`` but
NEVER deposited the synthesis (``archive_synthesis_via_db`` was unwired),
so ``syntheses`` was 0 by construction. This test pins the wiring that
closed that gap. The role-stub harness + canned responses are reused from
``tests.test_loop_one_orchestrator`` (the proven Sprint-8 happy-path suite).
"""
from __future__ import annotations

import os
import sys

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import EventBroadcaster, create_app  # noqa: E402
from processing.embedding import _reset_default_provider  # noqa: E402
from substrate.dispatch import (  # noqa: E402
    register_provider,
    reset_provider_registry,
)
from substrate.schemas import ActionType  # noqa: E402
from tests.test_loop_one_orchestrator import (  # noqa: E402
    _CONNECTOR_RESPONSE,
    _DECOMPOSER_RESPONSE,
    _KNOWLEDGE_EXTRACTION_RESPONSE,
    _PARAMETER_EXTRACTOR_RESPONSE,
    _SYNTHESIZER_RESPONSE,
    _all_role_config,
    _await_terminal,
    _evidence_response_for,
    _patch_dispatch,
    _post_start,
    _RoleStubProvider,
)


@pytest.fixture
def app_and_bus():
    bus = EventBroadcaster()
    app = create_app(broadcaster=bus, cors_origins=[])
    return app, bus


@pytest.fixture
async def async_client(app_and_bus):
    app, _ = app_and_bus
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _isolate_db_and_corpus(tmp_path, monkeypatch):
    """Tmp ANTIEK_HOME + a fixture corpus (doc + chunk-1) so the deposit
    writes to an isolated DB, never prod."""
    db_path = tmp_path / "graph.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(tmp_path / "research"))
    monkeypatch.setenv("ANTIEK_KNOWLEDGE_SKILLS_DIR", str(tmp_path / "skills"))
    quantum_dir = tmp_path / "skills" / "quantum-computing-knowledge"
    quantum_dir.mkdir(parents=True)
    (quantum_dir / "SKILL.md").write_text(
        "# Quantum Computing Knowledge\n\n## Domain Fundamentals\n\n(Findings.)\n"
    )

    import duckdb

    from substrate.graph.schema import init_database_at_path

    init_database_at_path(str(db_path))
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            "INSERT INTO documents "
            "(document_id, source_uri, title, author, source_tier, document_type, "
            "raw_text, metadata, content_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "doc-psi-quantum", "https://example.test/psiquantum-roadmap",
                "PsiQuantum photonic quantum roadmap", "Antiek fixture",
                1, "academic_paper",
                "PsiQuantum photonic quantum roadmap evidence. Quantum X holds.",
                "{}", "restricted_pending_opt_in",
            ],
        )
        con.execute(
            "INSERT INTO chunks "
            "(chunk_id, document_id, chunk_index, section_path, text, token_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                "chunk-1", "doc-psi-quantum", 0, "Fixture",
                "PsiQuantum photonic quantum roadmap evidence: Quantum X holds.", 32,
            ],
        )
    finally:
        con.close()
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


@pytest.mark.asyncio
async def test_investigation_deposits_synthesis_with_manifest(
    monkeypatch, app_and_bus, async_client,
):
    """A completed investigation deposits a syntheses row + a non-empty
    substrate manifest that joins to a real fixture document."""
    _, bus = app_and_bus
    inv = "inv-spr03-deposit"
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._render_chunks_block_for_sub_question",
        lambda _q, top_k=5, policy_tag="attribution_eligible": (
            "[chunk-1] Source tier: 1 | Document: PsiQuantum photonic quantum "
            "roadmap | Section: Fixture | Similarity: 1.000\n\n"
            "PsiQuantum photonic quantum roadmap evidence: Quantum X holds.\n"
        ),
    )
    register_provider(_RoleStubProvider({
        "decomposer": _DECOMPOSER_RESPONSE,
        "evidence_retriever": _evidence_response_for("(any sub-question)"),
        "parameter_extractor": _PARAMETER_EXTRACTOR_RESPONSE,
        "connector": _CONNECTOR_RESPONSE,
        "synthesizer": _SYNTHESIZER_RESPONSE,
        "knowledge_extractor": _KNOWLEDGE_EXTRACTION_RESPONSE,
    }))
    _patch_dispatch(monkeypatch, _all_role_config())

    await _post_start(
        async_client, investigation_id=inv,
        question="Is PsiQuantum's photonic quantum roadmap defensible?",
    )
    terminal = await _await_terminal(bus, inv, timeout=30.0)
    assert terminal is not None, "no terminal event landed"
    assert terminal["action_type"] == ActionType.INVESTIGATION_COMPLETED.value

    # ── The SPR-03 witness assertions: the loop CLOSED + DEPOSITED ──────
    import duckdb

    from substrate.graph import default_db_path

    con = duckdb.connect(default_db_path(), read_only=True)
    try:
        n_synth = con.execute(
            "SELECT count(*) FROM syntheses WHERE investigation_id = ?", [inv]
        ).fetchone()[0]
        manifest = con.execute(
            "SELECT m.entity_kind, m.entity_id "
            "FROM synthesis_substrate_manifest m "
            "JOIN syntheses s ON m.synthesis_id = s.synthesis_id "
            "WHERE s.investigation_id = ?",
            [inv],
        ).fetchall()
        joined_docs = con.execute(
            "SELECT count(*) "
            "FROM synthesis_substrate_manifest m "
            "JOIN syntheses s ON m.synthesis_id = s.synthesis_id "
            "JOIN chunks c ON m.entity_id = c.chunk_id "
            "WHERE s.investigation_id = ? AND m.entity_kind = 'chunk'",
            [inv],
        ).fetchone()[0]
        row = con.execute(
            "SELECT target_question, status, implicit_recommendation, thesis_text "
            "FROM syntheses WHERE investigation_id = ? LIMIT 1",
            [inv],
        ).fetchone()
    finally:
        con.close()

    assert n_synth >= 1, f"expected syntheses>=1 for {inv}, got {n_synth}"
    assert manifest, "synthesis_substrate_manifest is empty — no pins deposited"
    assert joined_docs >= 1, "manifest chunk does not join to a real document"
    assert row is not None
    target_question, status, recommendation, thesis_text = row
    assert "PsiQuantum" in target_question, target_question
    assert thesis_text and "PsiQuantum" in thesis_text, thesis_text
    assert status in ("passed", "draft"), status
    assert recommendation == "proceed", recommendation
    pinned_chunks = {e for k, e in manifest if k == "chunk"}
    assert "chunk-1" in pinned_chunks, pinned_chunks
