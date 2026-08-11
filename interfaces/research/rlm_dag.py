"""RLM Decomposition-DAG — structured problem decomposition with
layer-by-layer execution, memoization, and second-opinion verification.

Sprint 9 day 4-5 port of Researchmaxx ``rlm_dag.py``. The empirical
result the upstream cites: the strongest base model scored 38.7% on
long-reasoning benchmarks; the same model wrapped as a depth-1 RLM
with explicit DAG decomposition hints scored 65.6% — a 27-point lift
from the orchestration pattern alone.

Engineering rules (verbatim from the tech brief the upstream cites):

  1. Dispatch one planning sub-LLM that returns a structured JSON
     DAG. The planner solves nothing; it only structures.
  2. Maintain ``answers = {}`` (verified answers, keyed by node_id)
     and ``plan = {}`` (the DAG) across all turns. Do not trust
     variables from earlier turns; memoize everything that will be
     reused.
  3. Solve layer by layer. A node is ready when all its ``deps`` are
     in ``answers``. Dispatch all ready nodes in one ``llm_batch``
     call.
  4. Verify every answer before it propagates to a child via
     independent second-opinion re-dispatch
     (``skills.verification.rlm.verify_claim``).
  5. Assemble the final answer by dict lookup only. No recomputation.

Antiek changes from upstream:
  - ``researchmaxx_constants`` → ``substrate.constants``.
  - ``rlm_verify.verify_claim`` → ``skills.verification.rlm.verify_claim``
    (Sprint 6 day 3-4 migration).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orchestration.rlm.prime_agent_backend import (
        PrimeAgentOutcome,
        PrimeAgentRLMBackend,
    )

# Ensure repo root on path for direct invocation.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)


# ---------------------------------------------------------------------------
# DAG representation
# ---------------------------------------------------------------------------


@dataclass
class DagNode:
    """A single node in the decomposition DAG.

    ``question`` is preserved verbatim from the planner — paraphrasing
    discards the planner's structural signal."""

    id: str
    question: str
    deps: list[str] = field(default_factory=list)
    category: str = ""
    evidence_type_required: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "question": self.question, "deps": self.deps,
            "category": self.category,
            "evidence_type_required": self.evidence_type_required,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DagNode:
        return cls(
            id=d["id"], question=d["question"],
            deps=list(d.get("deps") or []),
            category=d.get("category", ""),
            evidence_type_required=d.get("evidence_type_required", ""),
        )


@dataclass
class Dag:
    """A decomposition DAG with explicit dependency structure."""

    nodes: list[DagNode]
    final_assembly: str = ""
    cycles: list[list[str]] = field(default_factory=list)
    planning_model: str = ""
    planning_latency_s: float = 0.0

    @classmethod
    def from_plan_json(cls, plan: dict[str, Any], **meta) -> Dag:
        nodes = [DagNode.from_dict(n) for n in plan.get("nodes", [])]
        return cls(
            nodes=nodes,
            final_assembly=plan.get("final", ""),
            cycles=list(plan.get("cycles") or []),
            **meta,
        )

    def validate(self) -> list[str]:
        """Return list of structural issues. Empty = valid."""
        issues: list[str] = []
        node_ids = {n.id for n in self.nodes}
        if not node_ids:
            issues.append("DAG has no nodes")
        if self.cycles:
            for cycle in self.cycles:
                issues.append(f"Cycle detected: {' → '.join(cycle)}")
        for n in self.nodes:
            for dep in n.deps:
                if dep not in node_ids:
                    issues.append(
                        f"Node {n.id!r} depends on unknown node {dep!r}"
                    )
        roots = [n for n in self.nodes if not n.deps]
        if not roots:
            issues.append(
                "DAG has no root nodes (all nodes have dependencies)"
            )
        return issues

    def topological_layers(self) -> list[list[DagNode]]:
        """Group nodes into layers by dependency depth. Layer 0 =
        roots; within a layer, all nodes are mutually independent and
        can be dispatched in one ``llm_batch`` call. Unreachable
        nodes (from cycles or bad deps) surface in the last layer."""
        remaining = {n.id: n for n in self.nodes}
        resolved: set[str] = set()
        layers: list[list[DagNode]] = []

        while remaining:
            layer = [
                n for nid, n in remaining.items()
                if all(d in resolved for d in n.deps)
            ]
            if not layer:
                layer = list(remaining.values())
                layers.append(layer)
                break
            layers.append(layer)
            for n in layer:
                resolved.add(n.id)
                del remaining[n.id]

        return layers

    def layer_count(self) -> int:
        return len(self.topological_layers())

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "final": self.final_assembly,
            "cycles": self.cycles,
            "layer_count": self.layer_count(),
        }


# ---------------------------------------------------------------------------
# DAG Planner
# ---------------------------------------------------------------------------


DAG_PLANNER_SYSTEM_PROMPT = """\
You are a decomposition planner for a multi-agent research system. Your job is NOT to answer questions. Your job is to decompose a complex research question into a directed acyclic graph (DAG) of self-contained sub-problems.

Each sub-problem must be:
- Addressable from evidence (not opinion or forecast)
- Self-contained: the sub-LLM solving it only sees its own question and verified answers from its parent nodes
- Verifiable: there must be a factual check that can accept/reject the answer

Rules:
1. Produce 4-12 nodes. Fewer than 4 is decomposition theater; more than 12 fragments into trivia.
2. Each node has: id (short, descriptive slug), question (verbatim — do NOT paraphrase the top-level question), deps (list of node IDs this node depends on), category, evidence_type_required.
3. The DAG must be acyclic. If you detect a cycle, list it in `cycles`.
4. Root nodes (no deps) are the foundational facts — the things you must establish before reasoning.
5. Leaf nodes (no children) are where synthesis happens — they aggregate parent answers.
6. The `final` field explains in one sentence how to assemble the final answer from node answers.

Categories (choose the single best fit for each node):
  fact_retrieval, parameter_extraction, cross_domain_connection, synthesis, verification

Evidence types:
  quantitative, qualitative, mixed

Output a single JSON object conforming to the schema. No prose before or after.\
"""


def _parse_json(text: str) -> Any:
    """Strict JSON parse with largest-window fallback."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for open_ch, close_ch in (("{", "}"), ("[", "]")):
            i = text.find(open_ch)
            j = text.rfind(close_ch)
            if i != -1 and j != -1 and j > i:
                try:
                    return json.loads(text[i: j + 1])
                except json.JSONDecodeError:
                    continue
        raise ValueError(
            f"Could not parse JSON from planner response: {text[:500]}"
        ) from None


def plan_dag(
    question: str,
    llm_query_fn: Callable[[str], str],
    *,
    context: str = "",
    decomposition_examples: list[dict] | None = None,
    model: str = "deepseek/deepseek-v4-pro",
    prime_backend: PrimeAgentRLMBackend | None = None,
    evidence_sink: Callable[[PrimeAgentOutcome], None] | None = None,
) -> Dag:
    """Dispatch the DAG planning sub-LLM. Returns a parsed ``Dag``.

    ``decomposition_examples`` is the single highest-leverage piece
    of text in the pipeline — canonical in-context demonstrations of
    correct decomposition strategy."""
    t0 = time.time()
    user_parts = [f"Top-level question:\n\n{question}"]
    if context:
        user_parts.append(f"\n\nDomain context:\n\n{context}")
    if decomposition_examples:
        user_parts.append(
            "\n\n## Canonical decomposition examples\n\n"
            "These are examples of correct decomposition strategy for similar "
            "tasks. Study the structure — how root nodes establish facts, how "
            "intermediate nodes combine, how leaf nodes synthesize.\n\n"
        )
        for i, ex in enumerate(decomposition_examples, 1):
            user_parts.append(
                f"### Example {i}\n```json\n{json.dumps(ex, indent=2)}\n```\n"
            )
    user_parts.append("\nProduce the DAG decomposition as a single JSON object.")
    user_text = "\n".join(user_parts)
    prompt = DAG_PLANNER_SYSTEM_PROMPT + "\n\n" + user_text

    from interfaces.research.rlm_repl import _with_prime_evidence

    prompt = _with_prime_evidence(
        prompt,
        workflow="rlm_dag.plan",
        invocation_key="plan",
        backend=prime_backend,
        evidence_sink=evidence_sink,
    )
    raw = llm_query_fn(prompt)
    parsed = _parse_json(raw)
    return Dag.from_plan_json(
        parsed,
        planning_model=model,
        planning_latency_s=round(time.time() - t0, 2),
    )


# ---------------------------------------------------------------------------
# Layer-by-layer solver
# ---------------------------------------------------------------------------


@dataclass
class DagExecutionResult:
    """The result of executing a full DAG."""

    dag: Dag
    answers: dict[str, Any]
    verification_results: dict[str, Any]
    layers: int
    total_nodes: int
    nodes_failed_verification: list[str]
    total_sub_llm_calls: int
    elapsed_s: float

    def final_answer(self) -> dict[str, Any]:
        return dict(self.answers)


def execute_dag(
    dag: Dag,
    llm_query_fn: Callable[[str], str],
    llm_batch_fn: Callable[[list[str]], list[str]],
    verify_fn: Callable[..., Any] | None = None,
    *,
    max_retries_per_node: int = 2,
    prime_backend: PrimeAgentRLMBackend | None = None,
    evidence_sink: Callable[[PrimeAgentOutcome], None] | None = None,
) -> DagExecutionResult:
    """Execute a DAG layer by layer with verification at each layer.

    ``verify_fn`` defaults to
    ``skills.verification.rlm.verify_claim``. Failed verification
    after ``max_retries_per_node`` lands the node's answer with a
    ``[HEDGED]`` prefix so downstream consumers can detect the
    failure without losing the partial signal."""
    t0 = time.time()

    if verify_fn is None:
        from skills.verification.rlm import verify_claim as _default_verify
        verify_fn = _default_verify

    _raw_verify = verify_fn

    def _verify(claim: str, ctx: str, cid: str):
        return _raw_verify(
            claim=claim, context=ctx,
            llm_batch_fn=llm_batch_fn, claim_id=cid,
        )

    layers = dag.topological_layers()
    answers: dict[str, Any] = {}
    verification_results: dict[str, Any] = {}
    nodes_failed: list[str] = []
    total_calls = 0

    for layer in layers:
        prompts: list[str] = []
        node_ids_this_layer: list[str] = []
        for node in layer:
            node_ids_this_layer.append(node.id)
            parent_context = ""
            if node.deps:
                parent_blocks = [
                    f"Verified answer for [{dep}]: {answers[dep]}"
                    for dep in node.deps
                    if dep in answers and answers[dep] is not None
                ]
                if parent_blocks:
                    parent_context = "\n".join(parent_blocks) + "\n\n"
            prompt = (
                "Answer this question precisely. Use the verified parent "
                "answers below if provided. Return ONLY the answer — no "
                "explanation, no prose.\n\n"
                f"{parent_context}Question: {node.question}"
            )
            prompts.append(prompt)

        from interfaces.research.rlm_repl import _with_prime_evidence

        prompts = [
            _with_prime_evidence(
                prompt,
                workflow="rlm_dag.node",
                invocation_key=node_id,
                backend=prime_backend,
                evidence_sink=evidence_sink,
            )
            for node_id, prompt in zip(
                node_ids_this_layer, prompts, strict=True
            )
        ]
        batch_results = llm_batch_fn(prompts)
        total_calls += len(prompts)
        layer_answers: dict[str, str] = {
            nid: result
            for nid, result in zip(
                node_ids_this_layer, batch_results, strict=False
            )
        }

        for node in layer:
            answer = layer_answers.get(node.id, "")
            if not answer:
                nodes_failed.append(node.id)
                verification_results[node.id] = {
                    "accepted": False,
                    "disagreement_reason": "empty answer",
                }
                continue

            vctx_parts = [f"Question: {node.question}"]
            for dep in node.deps:
                if dep in answers and answers[dep] is not None:
                    vctx_parts.append(f"Parent [{dep}]: {answers[dep]}")
            vctx = "\n".join(vctx_parts)
            claim = (
                f"For question '{node.question}', the answer is: {answer}"
            )

            verified = False
            vresult: Any = None
            for attempt in range(max_retries_per_node + 1):
                vresult = _verify(claim, vctx, node.id)
                verification_results[node.id] = (
                    vresult.to_dict()
                    if hasattr(vresult, "to_dict") else vresult
                )
                accepted = (
                    vresult.accepted
                    if hasattr(vresult, "accepted")
                    else (vresult or {}).get("accepted")
                )
                if accepted:
                    verified = True
                    break
                if attempt < max_retries_per_node:
                    fail_reason = (
                        vresult.disagreement_reason
                        if hasattr(vresult, "disagreement_reason")
                        else (vresult or {}).get(
                            "disagreement_reason", "verification failed"
                        )
                    )
                    claim = (
                        f"Previous verification failed: {fail_reason}\n\n"
                        f"Original question: {node.question}\n\n"
                        f"Original answer: {answer}\n\n"
                        "Provide a corrected answer."
                    )

            if verified:
                agreed = (
                    vresult.agreed_answer
                    if hasattr(vresult, "agreed_answer")
                    else (vresult or {}).get("agreed_answer", answer)
                )
                answers[node.id] = agreed
            else:
                answers[node.id] = f"[HEDGED — verification failed] {answer}"
                nodes_failed.append(node.id)

    elapsed = round(time.time() - t0, 2)
    return DagExecutionResult(
        dag=dag,
        answers=answers,
        verification_results=verification_results,
        layers=len(layers),
        total_nodes=len(dag.nodes),
        nodes_failed_verification=nodes_failed,
        total_sub_llm_calls=total_calls,
        elapsed_s=elapsed,
    )


# ---------------------------------------------------------------------------
# Task-complexity classifier
# ---------------------------------------------------------------------------


def classify_complexity(question: str, dag: Dag) -> str:
    """Classify a research task by expected complexity class.

    Returns ``"O(1)"`` (single fact), ``"O(N)"`` (N independent
    evidence items), or ``"O(N²)"`` (cross-correlation across many
    entities). Heuristic based on DAG structure: layer count,
    multi-parent nodes, cross-domain category nodes."""
    layers = dag.topological_layers()
    n_nodes = len(dag.nodes)
    n_layers = len(layers)
    multi_parent_nodes = sum(1 for n in dag.nodes if len(n.deps) >= 2)
    cross_domain = sum(
        1 for n in dag.nodes if n.category == "cross_domain_connection"
    )

    if n_layers <= 1 and n_nodes <= 2 and multi_parent_nodes == 0:
        return "O(1)"
    if n_layers >= 3 or multi_parent_nodes >= 3 or cross_domain >= 2:
        return "O(N²)"
    return "O(N)"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_plan(args) -> int:
    if args.dry_run:
        dag = Dag(
            nodes=[
                DagNode(id="n1", question="What is the primary evidence for X?",
                        deps=[], category="fact_retrieval"),
                DagNode(id="n2", question="How does X compare to Y?",
                        deps=["n1"], category="parameter_extraction"),
            ],
            final_assembly="Combine n1 and n2 into a comparative assessment.",
            planning_model="stub://dry-run",
        )
    else:
        print(
            "Live planning requires a wired llm_query function. "
            "Use --dry-run for a stub DAG.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(dag.to_dict(), indent=2))
    print(f"\nComplexity class: {classify_complexity(args.question, dag)}")
    return 0


def _cmd_layers(args) -> int:
    if os.path.isfile(args.dag_json):
        with open(args.dag_json) as f:
            plan = json.load(f)
    else:
        plan = json.loads(args.dag_json)
    dag = Dag.from_plan_json(plan)
    for i, layer in enumerate(dag.topological_layers()):
        print(f"Layer {i}:")
        for n in layer:
            deps_str = f" (deps: {', '.join(n.deps)})" if n.deps else ""
            print(f"  [{n.id}]{deps_str}: {n.question[:80]}")
    return 0


def _cmd_complexity(args) -> int:
    if os.path.isfile(args.dag_json):
        with open(args.dag_json) as f:
            plan = json.load(f)
    else:
        plan = json.loads(args.dag_json)
    dag = Dag.from_plan_json(plan)
    print(classify_complexity(args.question, dag))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="RLM DAG decomposition + execution",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("plan", help="Run the DAG planner on a question")
    sp.add_argument("--question", required=True)
    sp.add_argument("--context", default="")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=_cmd_plan)

    sp = sub.add_parser("layers", help="Show topological layers for a DAG JSON")
    sp.add_argument(
        "--dag-json", required=True,
        help="Path to DAG JSON or inline JSON string",
    )
    sp.set_defaults(func=_cmd_layers)

    sp = sub.add_parser("complexity", help="Classify task complexity from DAG JSON")
    sp.add_argument("--question", required=True)
    sp.add_argument("--dag-json", required=True)
    sp.set_defaults(func=_cmd_complexity)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
