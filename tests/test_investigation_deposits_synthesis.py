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

import asyncio
import hashlib
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import EventBroadcaster, create_app  # noqa: E402
from processing.embedding import _reset_default_provider  # noqa: E402
from substrate.dispatch import (  # noqa: E402
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.schemas import ActionType  # noqa: E402
from tests.research_quote_support import (  # noqa: E402
    async_signed_body,
    configure_research_quote_authority,
)
from tests.test_loop_one_orchestrator import (  # noqa: E402
    _CONNECTOR_RESPONSE,
    _DECOMPOSER_RESPONSE,
    _KNOWLEDGE_EXTRACTION_RESPONSE,
    _PARAMETER_EXTRACTOR_RESPONSE,
    _SYNTHESIZER_RESPONSE,
    _all_role_config,
    _evidence_response_for,
    _patch_dispatch,
    _RoleStubProvider,
)


class _PaidRoleStubProvider(_RoleStubProvider):
    def __init__(self, responses_by_tag):
        super().__init__(responses_by_tag)
        self._receipts = {}

    def call_idempotent(self, *, model, prompt, max_tokens, temperature, idempotency_key):
        if idempotency_key not in self._receipts:
            self._receipts[idempotency_key] = self.call(
                model=model,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        return self._receipts[idempotency_key]


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
    configure_research_quote_authority(monkeypatch, tmp_path)
    quantum_dir = tmp_path / "skills" / "quantum-computing-knowledge"
    quantum_dir.mkdir(parents=True)
    (quantum_dir / "SKILL.md").write_text(
        "# Quantum Computing Knowledge\n\n## Domain Fundamentals\n\n(Findings.)\n"
    )

    import duckdb

    from runtime.db_lock import connect_write
    from substrate.graph.ops import seal_existing_admitted_state
    from substrate.graph.schema import init_database_at_path
    from substrate.investigation_streams import initialize_composite_stream
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.legal_gate.admission import admit_staged_document
    from substrate.legal_gate.policy_store import account_policy_authority

    init_database_at_path(str(db_path))
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            "INSERT INTO documents "
            "(document_id, source_uri, title, author, source_tier, document_type, "
            "investigation_id, raw_text, metadata, content_class, owner_user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "doc-psi-quantum",
                "https://example.test/psiquantum-roadmap",
                "PsiQuantum photonic quantum roadmap",
                "Antiek fixture",
                1,
                "academic_paper",
                "inv-spr03-deposit",
                "PsiQuantum photonic quantum roadmap evidence. Quantum X holds.",
                "{}",
                "restricted_pending_opt_in",
                "__operator__",
            ],
        )
        con.execute(
            "INSERT INTO chunks "
            "(chunk_id, document_id, chunk_index, section_path, text, token_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                "chunk-1",
                "doc-psi-quantum",
                0,
                "Fixture",
                "PsiQuantum photonic quantum roadmap evidence: Quantum X holds.",
                32,
            ],
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata) "
            "VALUES (?, ?, 'claim', 'cross_domain', ?)",
            [
                "node-chunk-1",
                "PsiQuantum photonic substrate is established",
                '{"chunk_id":"chunk-1"}',
            ],
        )
    finally:
        con.close()

    authority = InvestigationAuthority(
        "__operator__", "inv-spr03-deposit", root=tmp_path / "events"
    )
    initialize_composite_stream(authority)
    content = "PsiQuantum photonic quantum roadmap evidence. Quantum X holds."
    with connect_write(
        str(db_path), purpose="test-deposit-legal-admission", log_on_close=False
    ) as locked_con:
        receipt = admit_staged_document(
            locked_con,
            account_policy_authority(authority),
            investigation_digest=authority.investigation_digest,
            document_id="doc-psi-quantum",
            provenance_class="internal_operator",
            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
            at=datetime.now(UTC),
        )
        seal_existing_admitted_state(
            locked_con,
            authority,
            admission_receipt_id=receipt.receipt_id,
            admitted_content_sha256=hashlib.sha256(content.encode()).hexdigest(),
            document_id="doc-psi-quantum",
        )
    _reset_default_provider()
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


@pytest.mark.asyncio
async def test_investigation_deposits_synthesis_with_manifest(
    monkeypatch,
    app_and_bus,
    async_client,
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
    register_provider(
        _PaidRoleStubProvider(
            {
                "decomposer": _DECOMPOSER_RESPONSE,
                "evidence_retriever": _evidence_response_for("(any sub-question)"),
                "parameter_extractor": _PARAMETER_EXTRACTOR_RESPONSE,
                "connector": _CONNECTOR_RESPONSE,
                "synthesizer": _SYNTHESIZER_RESPONSE,
                "knowledge_extractor": _KNOWLEDGE_EXTRACTION_RESPONSE,
            }
        )
    )
    config = _all_role_config()
    config.tiers["pro"] = replace(
        config.tiers["pro"],
        pricing=TierPricing(
            input_per_mtok=0.01,
            output_per_mtok=0.02,
            cached_input_per_mtok=0.001,
            currency="USD",
            billing_unit="per_million_tokens",
            source_url="https://provider.example/pricing",
            verified_at="2026-01-01T00:00:00Z",
            expires_at="2099-01-01T00:00:00Z",
        ),
    )
    _patch_dispatch(monkeypatch, config)

    payload = {
        "investigation_id": inv,
        "question": "Is PsiQuantum's photonic quantum roadmap defensible?",
        "topic_slug": "psi-quantum-demo",
        "max_sub_questions": 4,
        "approved_run_ceiling_usd": 1.0,
    }
    response = await async_client.post(
        "/investigations",
        json=await async_signed_body(async_client, "/investigations/quote", payload),
    )
    assert response.status_code == 202, response.text
    from substrate.event_log import trajectory_authorized
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.multi_user.auth import operator_claims

    authority = InvestigationAuthority(
        operator_claims().user_id,
        inv,
        root=Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]),
    )
    terminal = None
    deadline = asyncio.get_event_loop().time() + 20.0
    while asyncio.get_event_loop().time() < deadline:
        await bus.wait_for_handlers(timeout=2.0)
        terminal = next(
            (
                row
                for row in trajectory_authorized(authority)
                if row.get("action_type")
                in {
                    ActionType.INVESTIGATION_COMPLETED.value,
                    ActionType.INVESTIGATION_FAILED.value,
                }
            ),
            None,
        )
        if terminal is not None:
            break
        await asyncio.sleep(0.05)
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
    pinned_nodes = {e for k, e in manifest if k == "node"}
    assert "node-chunk-1" in pinned_nodes, pinned_nodes

    promoted = await async_client.post(
        "/write/deliverables/from-investigation",
        json={"investigation_id": inv, "deliverable_kind": "research_memo"},
    )
    assert promoted.status_code == 201, promoted.text
    assert promoted.json()["block_count"] == 1
