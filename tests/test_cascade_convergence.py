"""SPR-DRL-06 — Path A convergence: DRW gather → Loop 1 synthesis tail."""

from __future__ import annotations

import hashlib
import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.api import EventBroadcaster  # noqa: E402
from orchestration.cascade_session import CascadeSession, Leaf  # noqa: E402
from orchestration.invariants.deep_research_complete import (  # noqa: E402
    check_deep_research_complete,
)
from orchestration.loop_one import register_handlers, run_synthesis_tail_from_pack  # noqa: E402
from processing.embedding import (  # noqa: E402
    _reset_default_provider,
    set_default_embedding_provider,
)
from roles.cascade_planner import SubQuestion, approve_plan, build_plan, persist_tree  # noqa: E402
from roles.cascade_planner.persist import load_tree  # noqa: E402
from runtime.research_runner import (  # noqa: E402
    HostLocalRunner,
    PromotionFunnel,
    make_contract_gather_stub,
)
from substrate.dispatch import (  # noqa: E402
    DispatchConfig,
    NormalizedUsage,
    ProviderError,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.graph.schema import init_database_at_path  # noqa: E402
from substrate.schemas import ActionType  # noqa: E402


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


class _Dec:
    def __init__(self, subs: list[str]) -> None:
        self._subs = subs

    def decompose(self, q: str, *, context: str = ""):
        return [SubQuestion(question=s) for s in self._subs]


class _SynthStubProvider:
    name = "cascade-tail-stub"

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        if "knowledge curator" in prompt:
            return RawProviderResponse(
                text=json.dumps({
                    "Domain Fundamentals": [{
                        "text": "Quantum gather evidence compounds.",
                        "confidence": "Measured",
                        "date_observed": "2026",
                        "source": "DRW gather",
                    }],
                }),
                raw_usage={"input_tokens": 40, "output_tokens": 60},
                finish_reason="end_turn",
                latency_ms=3,
            )
        if "senior investment analyst" in prompt:
            return RawProviderResponse(
                text=json.dumps({
                    "thesis_summary": (
                        "Gathered cascade quantum evidence supports the thesis."
                    ),
                    "implicit_recommendation": "proceed",
                    "thesis_components": [{
                        "claim": "Provisional gather notes compound into a thesis.",
                        "confidence": "moderate",
                        "confidence_basis": "DRW gather stub",
                        "supporting_chunk_ids": ["chunk-any"],
                        "supporting_path_indices": [],
                        "effective_source_tier": 3,
                        "hedging_required": True,
                    }],
                    "falsification_conditions": [{
                        "condition": "Gather evidence contradicts thesis",
                        "specific_observable": "Primary source revision",
                        "timeframe": "within 2 quarters",
                    }],
                    "execution_risks": [],
                    "constraint_compliance": {
                        "hard_constraints_satisfied": True,
                        "soft_constraints_violated": [],
                        "violations_justified": [],
                    },
                    "reasoning_paths_used": [],
                    "conviction_level": 0.55,
                    "constraint_loop_status": "single_pass",
                    "constraint_loop_iterations": 1,
                }),
                raw_usage={"input_tokens": 50, "output_tokens": 80},
                finish_reason="end_turn",
                latency_ms=3,
            )
        raise ProviderError("unexpected role", provider=self.name, model=model, latency_ms=0)

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "phase_logs"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(tmp_path / "research"))
    monkeypatch.setenv("ANTIEK_KNOWLEDGE_SKILLS_DIR", str(tmp_path / "skills"))
    skills = tmp_path / "skills" / "quantum-computing-knowledge"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "# Quantum Computing Knowledge\n\n## Domain Fundamentals\n\n(placeholder)\n"
        "## Key Players\n\n(placeholder)\n## Quantitative Benchmarks\n\n(placeholder)\n"
        "## Competitive Dynamics\n\n(placeholder)\n## Open Questions\n\n(placeholder)\n"
        "## Monitoring Checklist\n\n(placeholder)\n"
    )
    set_default_embedding_provider(_FakeEmbedding())
    reset_provider_registry()
    yield
    _reset_default_provider()
    reset_provider_registry()


def _patch_dispatch(monkeypatch):
    import substrate.dispatch.router as router

    pricing = TierPricing(input_per_mtok=0.0, output_per_mtok=0.0)
    tier = TierConfig(
        name="pro", provider="cascade-tail-stub", model="stub",
        max_tokens=4096, temperature=0.1, context_budget_tokens=128_000,
        pricing=pricing, fallback=None,
    )
    config = DispatchConfig(
        role_tiers={"synthesizer": "pro", "knowledge_extractor": "pro"},
        tiers={"pro": tier},
    )
    monkeypatch.setattr(
        router.DispatchConfig, "from_yaml",
        classmethod(lambda cls, path: config),
    )
    register_provider(_SynthStubProvider())


@pytest.mark.asyncio
async def test_pack_only_synthesis_tail_completes(tmp_path, monkeypatch):
    """M1: Loop 1 phases 6–9 accept SessionEvidencePack without phases 1–5."""
    _patch_dispatch(monkeypatch)
    bus = EventBroadcaster()
    from interfaces.research.api.synthesizer import register_handlers as _register_synth
    _register_synth(bus)
    coordinator = register_handlers(bus)

    from orchestration.session_evidence_pack import PackChunk, PackDocument, SessionEvidencePack

    pack = SessionEvidencePack(
        session_id="session-pack-only",
        problem_question="Does quantum Path A converge?",
        chunks=[
            PackChunk(
                chunk_id="chunk-1",
                document_id="doc-1",
                ip_holder_id=None,
                text="Provisional gather note.",
                source_investigation_id="leaf-0",
                sub_question="sub one",
            ),
        ],
        documents=[PackDocument(document_id="doc-1", title="Gather", ip_holder_id=None)],
        leaf_investigation_ids=["leaf-0"],
    )

    ctx = await run_synthesis_tail_from_pack(
        pack, broadcaster=bus, coordinator=coordinator,
    )
    assert ctx.failed_phase is None
    assert ctx.synthesis is not None
    ok, _ = check_deep_research_complete("session-pack-only", require_terminal_event=True)
    assert ok is True


@pytest.mark.asyncio
async def test_pack_synthesis_tail_mechanical_phase8_when_skill_templates_missing(
    tmp_path, monkeypatch,
):
    """Prod smoke regression: extract_and_patch without SKILL.md → mechanical fallback."""
    empty_skills = tmp_path / "no_templates"
    empty_skills.mkdir()
    monkeypatch.setenv("ANTIEK_KNOWLEDGE_SKILLS_DIR", str(empty_skills))
    _patch_dispatch(monkeypatch)
    bus = EventBroadcaster()
    from interfaces.research.api.synthesizer import register_handlers as _register_synth
    _register_synth(bus)
    coordinator = register_handlers(bus)

    from orchestration.session_evidence_pack import SessionEvidencePack, PackChunk, PackDocument

    pack = SessionEvidencePack(
        session_id="session-hbm-fallback",
        problem_question=(
            "Will high-bandwidth memory supply constraints limit GPU datacenter "
            "deployments through 2027?"
        ),
        chunks=[
            PackChunk(
                chunk_id="chunk-hbm",
                document_id="doc-url-hbm1",
                ip_holder_id=None,
                text="HBM capacity trails AI accelerator demand.",
                source_investigation_id="leaf-0",
                sub_question="HBM supply vs demand",
            ),
        ],
        documents=[PackDocument(document_id="doc-url-hbm1", title="HBM", ip_holder_id=None)],
        leaf_investigation_ids=["leaf-0"],
    )

    ctx = await run_synthesis_tail_from_pack(
        pack, broadcaster=bus, coordinator=coordinator,
    )
    assert ctx.failed_phase is None, ctx.fail_reason
    assert ctx.patched_domains
    assert (empty_skills / "semiconductor-knowledge" / "SKILL.md").exists()
    ok, _ = check_deep_research_complete(
        "session-hbm-fallback", require_terminal_event=True,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_cascade_gather_then_synthesis_tail_on_parent(tmp_path, monkeypatch):
    """M2: leaves gather-only; session parent reaches DeepResearchComplete."""
    _patch_dispatch(monkeypatch)
    db = os.environ["ANTIEK_DUCKDB_PATH"]
    ev = os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]
    init_database_at_path(db)

    tree = build_plan("quantum cascade convergence", decomposer=_Dec(["sub a"])).tree
    root_id = persist_tree(
        tree, investigation_id="session-conv",
        embedding_provider=_FakeEmbedding(), db_path=db,
    )
    approve_plan(root_id, approver="op", investigation_id="session-conv", db_path=db)
    loaded = load_tree(root_id, db_path=db)
    leaves = [
        Leaf(
            investigation_id="leaf-0",
            sub_question=c.question,
            question_node_id=c.graph_node_id,
        )
        for c in loaded.root.children
    ]

    funnel = PromotionFunnel(db_path=db, embedding_provider=_FakeEmbedding())
    runner = HostLocalRunner(
        make_contract_gather_stub(steps=1),
        events_dir=ev,
        seal_on_complete=False,
        on_emit=funnel.submit,
    )
    session = CascadeSession("session-conv", runner=runner, funnel=funnel,
                             events_dir=ev, db_path=db)
    bus = EventBroadcaster()
    from interfaces.research.api.synthesizer import register_handlers as _register_synth
    _register_synth(bus)
    coordinator = register_handlers(bus)

    await session.launch(root_id, leaves)
    _ = [ev_item async for ev_item in session.stream()]
    await session.join_and_merge()

    assert session.is_complete()
    assert not session.is_deep_research_complete()

    pack = session.build_evidence_pack(plan_root_node_id=root_id)
    await session.run_synthesis_tail(pack, broadcaster=bus, coordinator=coordinator)

    assert session.is_deep_research_complete()
    rows = trajectory("session-conv")
    assert any(
        r.get("action_type") == ActionType.INVESTIGATION_COMPLETED.value
        for r in rows
    )
    ok, _ = check_deep_research_complete("leaf-0")
    assert ok is False