"""Tests for interfaces/research/rlm_dag.py (Sprint 9 day 4-5).

Coverage:

A. DagNode / Dag dataclass round-trip:
   1. DagNode.to_dict / from_dict.
   2. Dag.from_plan_json builds nodes + meta.

B. Dag.validate:
   3. Valid DAG returns [].
   4. Unknown dep flagged.
   5. Cycles surfaced.
   6. No roots flagged.
   7. Empty DAG flagged.

C. Dag.topological_layers:
   8. Single-node DAG → one layer.
   9. Linear chain → N layers.
   10. Two parallel chains share layers.
   11. Unresolvable nodes land in final layer.
   12. layer_count matches.

D. _parse_json:
   13. Strict JSON parses.
   14. Bracket-slice fallback parses noisy LLM output.
   15. Unparseable input raises ValueError.

E. plan_dag:
   16. Returns Dag with nodes + planning meta.
   17. decomposition_examples baked into the prompt.

F. execute_dag:
   18. Single-node layer dispatches, answer stored.
   19. Multi-layer chain dispatches in topological order.
   20. verify_fn rejection triggers retry up to max_retries.
   21. Final failure surfaces "[HEDGED — verification failed]" + tracks node.
   22. Parent context threaded into child prompt.
   23. Total LLM call count matches node count when no retries.

G. classify_complexity heuristic:
   24. Tiny single-layer 1-node DAG → O(1).
   25. Linear 4-node 2-layer DAG → O(N).
   26. Wide multi-parent DAG → O(N²) via multi-parent threshold.
   27. Cross-domain category lifts to O(N²).
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.rlm_dag import (  # noqa: E402
    Dag,
    DagNode,
    _parse_json,
    classify_complexity,
    execute_dag,
    plan_dag,
)
from orchestration.rlm.prime_agent_backend import (  # noqa: E402
    PrimeAgentEvidence,
    PrimeAgentOutcome,
    PrimeAgentReceipt,
    PrimeAgentTerminalState,
)
from skills.verification.types import VerificationResult  # noqa: E402


class _PrimeBackendStub:
    def __init__(self, state, text=None):
        self.state = state
        self.text = text
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return PrimeAgentOutcome(
            request=request,
            evidence=PrimeAgentEvidence(self.text) if self.text else None,
            receipt=PrimeAgentReceipt(self.state, (), None, 1, 0, "stub"),
        )

# ---------------------------------------------------------------------------
# A. DagNode / Dag round-trip
# ---------------------------------------------------------------------------


def test_dagnode_round_trip():
    n = DagNode(
        id="a", question="Q?", deps=["b", "c"],
        category="synthesis", evidence_type_required="qualitative",
    )
    d = n.to_dict()
    assert d == {
        "id": "a", "question": "Q?", "deps": ["b", "c"],
        "category": "synthesis", "evidence_type_required": "qualitative",
    }
    n2 = DagNode.from_dict(d)
    assert n2.id == "a"
    assert n2.deps == ["b", "c"]
    assert n2.evidence_type_required == "qualitative"


def test_dag_from_plan_json_with_meta():
    plan = {
        "nodes": [
            {"id": "n1", "question": "Q1", "deps": []},
            {"id": "n2", "question": "Q2", "deps": ["n1"]},
        ],
        "final": "Combine n1 and n2.",
    }
    dag = Dag.from_plan_json(
        plan, planning_model="stub://model", planning_latency_s=0.42,
    )
    assert len(dag.nodes) == 2
    assert dag.final_assembly == "Combine n1 and n2."
    assert dag.planning_model == "stub://model"
    assert dag.planning_latency_s == 0.42


# ---------------------------------------------------------------------------
# B. Dag.validate
# ---------------------------------------------------------------------------


def test_validate_valid_dag_returns_empty():
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1"),
        DagNode(id="b", question="Q2", deps=["a"]),
    ])
    assert dag.validate() == []


def test_validate_unknown_dep_flagged():
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1"),
        DagNode(id="b", question="Q2", deps=["missing"]),
    ])
    issues = dag.validate()
    assert any("missing" in s for s in issues)


def test_validate_cycles_surfaced():
    dag = Dag(
        nodes=[
            DagNode(id="a", question="Q1", deps=["b"]),
            DagNode(id="b", question="Q2", deps=["a"]),
        ],
        cycles=[["a", "b", "a"]],
    )
    issues = dag.validate()
    assert any("Cycle" in s for s in issues)


def test_validate_no_roots_flagged():
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1", deps=["b"]),
        DagNode(id="b", question="Q2", deps=["a"]),
    ])
    issues = dag.validate()
    assert any("root" in s.lower() for s in issues)


def test_validate_empty_dag_flagged():
    issues = Dag(nodes=[]).validate()
    assert any("no nodes" in s.lower() for s in issues)


# ---------------------------------------------------------------------------
# C. topological_layers
# ---------------------------------------------------------------------------


def test_layers_single_node():
    dag = Dag(nodes=[DagNode(id="a", question="Q")])
    layers = dag.topological_layers()
    assert len(layers) == 1
    assert layers[0][0].id == "a"


def test_layers_linear_chain():
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1"),
        DagNode(id="b", question="Q2", deps=["a"]),
        DagNode(id="c", question="Q3", deps=["b"]),
    ])
    layers = dag.topological_layers()
    assert len(layers) == 3
    assert [n.id for n in layers[0]] == ["a"]
    assert [n.id for n in layers[1]] == ["b"]
    assert [n.id for n in layers[2]] == ["c"]


def test_layers_two_parallel_chains():
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1"),
        DagNode(id="b", question="Q2"),
        DagNode(id="c", question="Q3", deps=["a"]),
        DagNode(id="d", question="Q4", deps=["b"]),
    ])
    layers = dag.topological_layers()
    assert len(layers) == 2
    layer0_ids = {n.id for n in layers[0]}
    layer1_ids = {n.id for n in layers[1]}
    assert layer0_ids == {"a", "b"}
    assert layer1_ids == {"c", "d"}


def test_layers_unresolvable_lands_in_last_layer():
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1", deps=["nonexistent"]),
        DagNode(id="b", question="Q2", deps=["a"]),
    ])
    layers = dag.topological_layers()
    final_layer_ids = {n.id for n in layers[-1]}
    assert "a" in final_layer_ids


def test_layers_count_matches_layer_count_method():
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1"),
        DagNode(id="b", question="Q2", deps=["a"]),
    ])
    assert dag.layer_count() == len(dag.topological_layers())


# ---------------------------------------------------------------------------
# D. _parse_json
# ---------------------------------------------------------------------------


def test_parse_json_strict():
    assert _parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_bracket_slice_fallback():
    noisy = 'Here is the JSON you asked for: {"nodes": [], "final": "x"} done.'
    parsed = _parse_json(noisy)
    assert parsed == {"nodes": [], "final": "x"}


def test_parse_json_unparseable_raises():
    with pytest.raises(ValueError):
        _parse_json("no json here at all")


# ---------------------------------------------------------------------------
# E. plan_dag
# ---------------------------------------------------------------------------


def test_plan_dag_returns_dag_with_meta():
    plan = {
        "nodes": [
            {"id": "n1", "question": "What is X?", "deps": []},
            {"id": "n2", "question": "How does X compare to Y?",
             "deps": ["n1"]},
        ],
        "final": "Combine n1 and n2.",
    }

    def stub_llm(prompt: str) -> str:
        return json.dumps(plan)

    dag = plan_dag(
        "Compare X and Y", stub_llm, model="stub://plan",
    )
    assert len(dag.nodes) == 2
    assert dag.final_assembly == "Combine n1 and n2."
    assert dag.planning_model == "stub://plan"
    assert dag.planning_latency_s >= 0.0


def test_plan_dag_prime_disabled_preserves_prompt_and_call_count():
    prompts = []
    receipts = []
    backend = _PrimeBackendStub(PrimeAgentTerminalState.DISABLED)

    plan_dag(
        "Q?",
        lambda prompt: prompts.append(prompt) or json.dumps({
            "nodes": [{"id": "a", "question": "Q", "deps": []}],
        }),
        prime_backend=backend,
        evidence_sink=receipts.append,
    )

    assert len(prompts) == len(receipts) == 1
    assert "Supplemental Prime Agent evidence" not in prompts[0]


def test_plan_dag_prime_success_is_labeled_and_receipted():
    prompts = []
    receipts = []
    backend = _PrimeBackendStub(PrimeAgentTerminalState.SUCCESS, "plan evidence")

    plan_dag(
        "Q?",
        lambda prompt: prompts.append(prompt) or json.dumps({
            "nodes": [{"id": "a", "question": "Q", "deps": []}],
        }),
        prime_backend=backend,
        evidence_sink=receipts.append,
    )

    assert len(prompts) == len(receipts) == 1
    assert "Supplemental Prime Agent evidence (non-canonical)" in prompts[0]
    assert "plan evidence" in prompts[0]


def test_plan_dag_includes_decomposition_examples_in_prompt():
    captured_prompts: list[str] = []
    plan = {"nodes": [{"id": "a", "question": "Q", "deps": []}], "final": ""}

    def stub_llm(prompt: str) -> str:
        captured_prompts.append(prompt)
        return json.dumps(plan)

    examples = [
        {"nodes": [{"id": "ex1", "question": "EX1", "deps": []}],
         "final": "EX"},
    ]
    plan_dag(
        "Q?", stub_llm,
        decomposition_examples=examples,
    )
    assert len(captured_prompts) == 1
    assert "Canonical decomposition examples" in captured_prompts[0]
    assert "EX1" in captured_prompts[0]


# ---------------------------------------------------------------------------
# F. execute_dag
# ---------------------------------------------------------------------------


def _accept_verify_fn():
    """Verifier that always accepts and echoes the answer."""
    def _v(claim, context, llm_batch_fn, claim_id):
        # Extract "the answer is: X" from the claim.
        marker = "the answer is: "
        idx = claim.find(marker)
        answer = claim[idx + len(marker):] if idx != -1 else claim
        return VerificationResult(
            claim_id=claim_id,
            accepted=True,
            agreement_count=2,
            dispatch_count=2,
            agreed_answer=answer,
        )
    return _v


def test_execute_dag_prime_failure_preserves_canonical_answer_and_calls():
    backend = _PrimeBackendStub(PrimeAgentTerminalState.FAILED)
    prompts = []
    receipts = []
    dag = Dag(nodes=[DagNode(id="a", question="What is X?")])

    result = execute_dag(
        dag,
        lambda prompt: "unused",
        lambda batch: prompts.extend(batch) or ["canonical"],
        _accept_verify_fn(),
        prime_backend=backend,
        evidence_sink=receipts.append,
    )

    assert result.answers == {"a": "canonical"}
    assert result.total_sub_llm_calls == 1
    assert len(prompts) == len(receipts) == 1
    assert "Supplemental Prime Agent evidence" not in prompts[0]
    assert receipts[0].receipt.state is PrimeAgentTerminalState.FAILED


def test_execute_dag_single_node():
    dag = Dag(nodes=[DagNode(id="a", question="What is X?")])

    def llm_query(p: str) -> str: return "unused"
    def llm_batch(ps): return ["forty-two"] * len(ps)

    result = execute_dag(
        dag, llm_query, llm_batch, verify_fn=_accept_verify_fn(),
    )
    assert result.answers == {"a": "forty-two"}
    assert result.total_nodes == 1
    assert result.layers == 1
    assert result.total_sub_llm_calls == 1
    assert result.nodes_failed_verification == []


def test_execute_dag_multi_layer_dispatch_order():
    dispatch_order: list[list[str]] = []
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1"),
        DagNode(id="b", question="Q2"),
        DagNode(id="c", question="Q3", deps=["a", "b"]),
    ])

    def llm_query(p): return "unused"

    def llm_batch(prompts):
        dispatch_order.append([
            p.split("Question: ")[-1][:2] for p in prompts
        ])
        return ["x"] * len(prompts)

    result = execute_dag(
        dag, llm_query, llm_batch, verify_fn=_accept_verify_fn(),
    )
    assert result.layers == 2
    # First dispatch batch has a + b together; second has c alone.
    assert sorted(dispatch_order[0]) == ["Q1", "Q2"]
    assert dispatch_order[1] == ["Q3"]


def test_execute_dag_retries_on_verify_failure():
    calls = {"verify": 0}

    def verify_fn(claim, context, llm_batch_fn, claim_id):
        calls["verify"] += 1
        if calls["verify"] < 2:
            return VerificationResult(
                claim_id=claim_id, accepted=False,
                agreement_count=0, dispatch_count=3,
                disagreement_reason="initial mismatch",
            )
        return VerificationResult(
            claim_id=claim_id, accepted=True,
            agreement_count=2, dispatch_count=3,
            agreed_answer="recovered",
        )

    dag = Dag(nodes=[DagNode(id="a", question="Q?")])
    result = execute_dag(
        dag,
        lambda p: "unused",
        lambda ps: ["bad"] * len(ps),
        verify_fn=verify_fn,
        max_retries_per_node=2,
    )
    assert result.answers["a"] == "recovered"
    assert calls["verify"] == 2
    assert result.nodes_failed_verification == []


def test_execute_dag_final_failure_hedges_answer():
    def verify_fn(claim, context, llm_batch_fn, claim_id):
        return VerificationResult(
            claim_id=claim_id, accepted=False,
            agreement_count=0, dispatch_count=3,
            disagreement_reason="always fails",
        )

    dag = Dag(nodes=[DagNode(id="a", question="Q?")])
    result = execute_dag(
        dag,
        lambda p: "u",
        lambda ps: ["raw answer"] * len(ps),
        verify_fn=verify_fn,
        max_retries_per_node=1,
    )
    assert result.answers["a"].startswith("[HEDGED")
    assert "raw answer" in result.answers["a"]
    assert result.nodes_failed_verification == ["a"]


def test_execute_dag_parent_context_threaded():
    captured: list[str] = []
    dag = Dag(nodes=[
        DagNode(id="a", question="What is X?"),
        DagNode(id="b", question="How does X relate to Y?", deps=["a"]),
    ])

    def llm_batch(prompts):
        captured.extend(prompts)
        return ["resolved"] * len(prompts)

    execute_dag(
        dag, lambda p: "u", llm_batch,
        verify_fn=_accept_verify_fn(),
    )
    # The b-layer prompt (second batch element overall) should reference
    # the verified parent answer.
    parent_aware = [p for p in captured if "Verified answer for [a]" in p]
    assert len(parent_aware) == 1
    assert "resolved" in parent_aware[0]


def test_execute_dag_total_calls_no_retry():
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1"),
        DagNode(id="b", question="Q2", deps=["a"]),
        DagNode(id="c", question="Q3", deps=["a"]),
    ])
    result = execute_dag(
        dag,
        lambda p: "u",
        lambda ps: ["x"] * len(ps),
        verify_fn=_accept_verify_fn(),
    )
    assert result.total_sub_llm_calls == 3


# ---------------------------------------------------------------------------
# G. classify_complexity
# ---------------------------------------------------------------------------


def test_classify_complexity_o1_tiny_dag():
    dag = Dag(nodes=[DagNode(id="a", question="Q")])
    assert classify_complexity("trivial", dag) == "O(1)"


def test_classify_complexity_on_linear_chain():
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1"),
        DagNode(id="b", question="Q2", deps=["a"]),
        DagNode(id="c", question="Q3", deps=["b"]),
    ])
    # 3 layers triggers O(N²) via layer threshold, per heuristic.
    assert classify_complexity("Q?", dag) == "O(N²)"


def test_classify_complexity_on_two_layer_dag():
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1"),
        DagNode(id="b", question="Q2"),
        DagNode(id="c", question="Q3", deps=["a"]),
        DagNode(id="d", question="Q4", deps=["b"]),
    ])
    # 2 layers, no multi-parent (each c/d has 1 parent), no cross-domain.
    assert classify_complexity("Q?", dag) == "O(N)"


def test_classify_complexity_on2_via_multi_parents():
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1"),
        DagNode(id="b", question="Q2"),
        DagNode(id="c", question="Q3"),
        DagNode(id="d", question="Q4", deps=["a", "b"]),
        DagNode(id="e", question="Q5", deps=["b", "c"]),
        DagNode(id="f", question="Q6", deps=["a", "c"]),
    ])
    assert classify_complexity("Q?", dag) == "O(N²)"


def test_classify_complexity_on2_via_cross_domain():
    dag = Dag(nodes=[
        DagNode(id="a", question="Q1",
                category="cross_domain_connection"),
        DagNode(id="b", question="Q2",
                category="cross_domain_connection"),
        DagNode(id="c", question="Q3", deps=["a"]),
    ])
    assert classify_complexity("Q?", dag) == "O(N²)"
