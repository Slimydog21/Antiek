"""A cascade whose leaves gathered nothing must not spend on synthesis.

``_run_to_completion`` used to run the Loop 1 synthesis tail after every
join, whatever the leaves did. Stopping every leaf (the operator's only cancel
control) therefore still dispatched the paid synthesizer over an empty pack,
twice with the self-repair retry, under a placeholder sub-question, and then
wrote ``investigation.completed`` on the session parent. The session read as
done with ``deep_research_complete: True`` and zero chunks, although
docs/decisions/session-evidence-pack.md says an empty pack cannot satisfy
DeepResearchComplete.

These tests drive the production route: ``create_app`` wires the real tail
runner, ``POST /research/plans/{root}/launch`` uses the default stop-limit
mode, the operator steers ``stop`` on each leaf, and the real background
``_run_to_completion`` task runs. A stub provider counts synthesizer
dispatches; nothing leaves the process.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

import interfaces.research.api.cascade_routes as cr
from runtime.research_runner import make_contract_gather_stub, make_demo_loop
from substrate.dispatch import (
    DispatchConfig,
    NormalizedUsage,
    ProviderError,
    RawProviderResponse,
    TierConfig,
    TierPricing,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory

_SYNTH_PROMPTS: list[str] = []
# The durable audit action on the session trajectory (wire name, pinned here).
SYNTHESIS_TAIL_SKIPPED = "cascade.synthesis_tail.skipped"


def _synthesis(chunk_id: str) -> str:
    return json.dumps({
        "thesis_summary": "Supports proceeding.",
        "implicit_recommendation": "proceed",
        "thesis_components": [{
            "claim": "Supports proceeding.", "confidence": "moderate",
            "confidence_basis": "DRW gather", "supporting_chunk_ids": [chunk_id],
            "supporting_path_indices": [], "effective_source_tier": 3,
            "hedging_required": True,
        }],
        "falsification_conditions": [{
            "condition": "Photonic gate fidelity stalls below the roadmap target",
            "specific_observable": "Published two-qubit fidelity under 99 percent",
            "timeframe": "2 quarters",
        }],
        "execution_risks": [],
        "constraint_compliance": {
            "hard_constraints_satisfied": True,
            "soft_constraints_violated": [], "violations_justified": [],
        },
        "reasoning_paths_used": [], "conviction_level": 0.6,
    })


class _CountingProvider:
    name = "tail-skip-stub"

    def call(self, *, model, prompt, max_tokens, temperature):
        usage = {"input_tokens": 1, "output_tokens": 1}
        if "senior investment analyst" in prompt:
            _SYNTH_PROMPTS.append(prompt)
            m = re.search(r'"chunk_ids":\s*\[\s*"([^"]+)"', prompt)
            return RawProviderResponse(
                text=_synthesis(m.group(1) if m else "none"),
                raw_usage=usage, finish_reason="end_turn", latency_ms=1,
            )
        if "knowledge curator" in prompt:
            return RawProviderResponse(
                text=json.dumps({"Domain Fundamentals": [{
                    "text": "x", "confidence": "Measured",
                    "date_observed": "2026", "source": "s",
                }]}),
                raw_usage=usage, finish_reason="end_turn", latency_ms=1,
            )
        raise ProviderError("unexpected", provider=self.name, model=model, latency_ms=0)

    def normalize_usage(self, raw_usage):
        return NormalizedUsage(input_tokens=1, output_tokens=1)


class _Embedding:
    dimension = 8

    def encode(self, text):
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


@pytest.fixture
def client(monkeypatch):
    import substrate.dispatch.router as router
    from interfaces.research.api.app import create_app

    tmpdir = tempfile.mkdtemp(prefix="tail-skip-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", os.path.join(tmpdir, "research"))
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", os.path.join(tmpdir, "phase_logs"))
    monkeypatch.setenv("ANTIEK_KNOWLEDGE_SKILLS_DIR", os.path.join(tmpdir, "skills"))
    # Phase 8 patches a knowledge skill; give it one to patch.
    skill_dir = os.path.join(tmpdir, "skills", "quantum-computing-knowledge")
    os.makedirs(skill_dir)
    with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
        f.write("# Quantum\n\n" + "".join(
            f"## {h}\n\n(Findings will be added.)\n\n" for h in (
                "Domain Fundamentals", "Key Players", "Quantitative Benchmarks",
                "Competitive Dynamics", "Open Questions", "Monitoring Checklist",
            )
        ))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("ANTIEK_DRW_GATHER", raising=False)
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _Embedding())
    tier = TierConfig(
        name="pro", provider="tail-skip-stub", model="stub", max_tokens=4096,
        temperature=0.1, context_budget_tokens=128_000,
        pricing=TierPricing(input_per_mtok=0.0, output_per_mtok=0.0), fallback=None,
    )
    cfg = DispatchConfig(
        role_tiers={"synthesizer": "pro", "knowledge_extractor": "pro"},
        tiers={"pro": tier},
    )
    monkeypatch.setattr(router.DispatchConfig, "from_yaml", classmethod(lambda cls, p: cfg))
    reset_provider_registry()
    register_provider(_CountingProvider())
    _SYNTH_PROMPTS.clear()
    saved_tail = cr._SYNTHESIS_TAIL_RUNNER
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
    app = create_app(register_wrestling=True, register_providers=False, cors_origins=[])
    assert cr._SYNTHESIS_TAIL_RUNNER is not None, "create_app must wire the real tail"
    with TestClient(app) as c:
        yield c
    cr.set_synthesis_tail_runner(saved_tail)
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
    reset_provider_registry()


def _approved_plan(client) -> str:
    r = client.post(
        "/research/plans",
        json={"problem": "quantum roadmap", "sub_questions": ["sub a", "sub b"]},
    )
    assert r.status_code == 200, r.text
    root = r.json()["root_node_id"]
    client.post(f"/research/plans/{root}/approve", json={"approver": "operator"})
    return root


def _wait_for_completion_task(sid: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = cr._SESSION_TASKS.get(sid)
        if task is not None and task.done():
            assert not task.cancelled()
            assert task.exception() is None
            return
        time.sleep(0.05)
    raise AssertionError("session completion task did not finish")


def _session_lifecycle(sid: str) -> list[str]:
    return [
        r["action_type"] for r in trajectory(sid)
        if r["action_type"] in ("investigation.completed", "investigation.failed")
    ]


def _parent_terminal_payload(sid: str) -> dict:
    rows = [r for r in trajectory(sid)
            if r["action_type"] in ("investigation.completed", "investigation.failed")]
    assert len(rows) == 1, rows
    return rows[0]["payload"]


def _skips(sid: str) -> list[dict]:
    return [r["payload"] for r in trajectory(sid) if r["action_type"] == SYNTHESIS_TAIL_SKIPPED]


def test_stopping_every_leaf_does_not_dispatch_the_synthesizer(client, monkeypatch):
    monkeypatch.setattr(
        cr, "_research_loop_factory",
        lambda **kw: make_contract_gather_stub(steps=300, delay_s=0.02, cost_per_step=0.0),
    )
    root = _approved_plan(client)
    launched = client.post(f"/research/plans/{root}/launch", json={})
    assert launched.status_code == 200, launched.text
    body = launched.json()
    assert body["spend_mode"] == "stop_limit"
    sid = body["session_id"]
    for leaf in body["researches"]:
        s = client.post(
            f"/research/sessions/{sid}/researches/{leaf['investigation_id']}/steer",
            json={"kind": "stop"},
        )
        assert s.status_code == 200, s.text
    _wait_for_completion_task(sid)

    status = client.get(f"/research/sessions/{sid}").json()
    assert {r["state"] for r in status["researches"]} == {"stopped"}
    assert _SYNTH_PROMPTS == []
    # The parent ends like a stopped research, so every status reader agrees.
    assert _session_lifecycle(sid) == ["investigation.completed"]
    assert _parent_terminal_payload(sid) == {"outcome": "stopped"}
    assert status["deep_research_complete"] is False
    assert status["synthesis_tail_skipped"] == "no_leaf_done"
    assert [p["reason"] for p in _skips(sid)] == ["no_leaf_done"]
    listed = client.get("/investigations").json()["investigations"]
    session_row = next(s for s in listed if s["investigation_id"] == sid)
    assert session_row["status"] == "stopped"
    assert client.get(f"/investigations/{sid}").json()["status"] == "stopped"


def test_done_leaves_with_an_empty_pack_do_not_dispatch_the_synthesizer(client, monkeypatch):
    monkeypatch.setattr(
        cr, "_research_loop_factory",
        lambda **kw: make_demo_loop(steps=1, cost_per_step=0.0, emit_note=False),
    )
    root = _approved_plan(client)
    launched = client.post(f"/research/plans/{root}/launch", json={})
    assert launched.status_code == 200, launched.text
    sid = launched.json()["session_id"]
    _wait_for_completion_task(sid)

    status = client.get(f"/research/sessions/{sid}").json()
    assert {r["state"] for r in status["researches"]} == {"done"}
    assert _SYNTH_PROMPTS == []
    # A finished gather with nothing citable fails at phase 6, the verdict the
    # tail itself gives an empty pack; list and detail must say the same.
    assert _session_lifecycle(sid) == ["investigation.failed"]
    assert _parent_terminal_payload(sid)["phase"] == 6
    assert status["deep_research_complete"] is False
    assert status["synthesis_tail_skipped"] == "empty_evidence_pack"
    assert [p["reason"] for p in _skips(sid)] == ["empty_evidence_pack"]
    listed = client.get("/investigations").json()["investigations"]
    session_row = next(s for s in listed if s["investigation_id"] == sid)
    assert session_row["status"] == "failed"
    assert client.get(f"/investigations/{sid}").json()["status"] == "failed"


def _seed_source() -> str:
    """One real source document + chunk, so a gather can cite substrate text."""
    from runtime.db_lock import connect_write
    from substrate.graph.ops import insert_chunk, insert_document
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(os.environ["ANTIEK_DUCKDB_PATH"])
    text = (
        "Photonic qubits lose coherence mainly through waveguide scattering, "
        "and the loss budget sets the fault-tolerance threshold. "
    ) * 5
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/seed") as con:
        insert_document(
            con, document_id="doc-skip-src", source_tier=2, document_type="web",
            title="Photonics source", raw_text=text,
            content_class="public_domain", ip_holder_id=None,
        )
        insert_chunk(
            con, document_id="doc-skip-src", chunk_index=0,
            chunk_id="chunk-skip-src", text=text,
        )
    return "doc-skip-src"


def _grounded_gather_loop(document_id: str):
    # The contract stub's placeholder note cites nothing in the substrate, so
    # since the evidence pack stopped inventing chunk ids (audit wave 5 W03) it
    # yields an empty pack and the tail is rightly skipped. "Gathered evidence"
    # has to mean a note on a real ingested document, as the Exa loop makes.
    async def _loop(ctx):
        sub_q = await ctx.checkpoint()
        yield ctx.note(f"source for {sub_q}", document_id=document_id)

    return _loop


def test_leaves_that_gathered_evidence_still_run_the_tail(client, monkeypatch):
    doc_id = _seed_source()
    monkeypatch.setattr(
        cr, "_research_loop_factory",
        lambda **kw: _grounded_gather_loop(doc_id),
    )
    root = _approved_plan(client)
    launched = client.post(f"/research/plans/{root}/launch", json={})
    assert launched.status_code == 200, launched.text
    sid = launched.json()["session_id"]
    _wait_for_completion_task(sid)

    status = client.get(f"/research/sessions/{sid}").json()
    assert {r["state"] for r in status["researches"]} == {"done"}
    assert len(_SYNTH_PROMPTS) >= 1
    assert all("Evidence from" not in p for p in _SYNTH_PROMPTS)
    assert _session_lifecycle(sid) == ["investigation.completed"]
    assert status.get("synthesis_tail_skipped") is None
    assert _skips(sid) == []
