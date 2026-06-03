"""AFF SPR-09 M2 — the multi-arm compounding harness over the host-local runner.

For each frozen question, runs the EXISTING host-local research loop once per
arm. Three arms:

  * ``ColdSeed``      — empty graph, ``retrieval_substrate=None`` → no reuse
                        (the automatic cold path). The control the warm arm is
                        measured against.
  * ``WarmSeed``      — graph seeded with the question's labelled prior units
                        through the deposit→retrieve→reuse surface
                        (``promote_insight`` → ``BruteForceSubstrate`` →
                        ``retrieve_prior_units``). The arm whose cost the
                        flywheel claim is about.
  * ``IrrelevantSeed``— graph seeded with the SAME NUMBER of OFF-TOPIC units
                        (the §2 graph-size control). Isolates "relevance" from
                        "graph-presence/noise": if the warm arm is cheaper ONLY
                        because the graph is non-empty, this arm is cheaper too,
                        and the run is flagged invalid (validity.py / M5).

Hard invariants this module holds (verification gates):

  * §16 no second runtime. The harness drives the existing
    ``runtime.research_runner.HostLocalRunner`` (which conforms to
    ``protocol.ResearchRunner``). It introduces no external process launch, no
    remote-exec provider, and no second runtime entrypoint — the §16 grep gate
    over this package is empty.
  * Single-writer per graph. Each arm acquires an isolated ``PersonalGraphHandle``
    via ``graph_router.personal_graph_path(user_id)`` → distinct
    ``{user_id}.duckdb``. ``test_arms_distinct_graph_handles`` asserts the cold /
    warm / irrelevant arms hold DISTINCT ``db_path`` identities.
  * Warm seeded ONLY through the real surface. The warm/irrelevant graphs are
    populated with ``promote_insight`` (the deposit surface) and reached via
    ``retrieve_prior_units`` (the SPR-07/08 retrieve path) — never by
    hand-injecting an answer.

THE KEYSTONE CAVEAT (intellectual honesty #1 — documented, not hidden): the
deterministic ``make_demo_loop`` charges a FIXED ``cost_per_step`` regardless of
whether a reuse pack was assembled. The reuse path IS exercised — ``start``
retrieves prior units and emits ``knowledge.reused`` for the warm arm — but the
demo loop's cost is reuse-blind, so a mock run honestly shows warm ≈ cold
(delta ≈ 0). This harness does NOT modify the demo loop to consume reuse; doing
so would rig the mock. The instrument's falsifiability is proven independently by
``tests/test_falsifiability.py`` injecting synthetic measurements into the
aggregator/validity layer. Real compounding is an operator-window measurement: a
``mock_run=false`` run with a reuse-CONSUMING browse loop + provider creds.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import connect_write
from runtime.research_runner import HostLocalRunner
from runtime.research_runner.host_local import make_demo_loop
from runtime.research_runner.protocol import BudgetCap, ResearchPlan
from substrate.graph.insight_question import promote_insight
from substrate.graph.ops import insert_node
from substrate.graph.retrieval_substrate import make_substrate
from substrate.graph.schema import init_database
from substrate.multi_user.graph_router import GraphRouter, resolve_personal_graph

from .measure import CostToResolve, measure_investigation
from .question_set import BenchmarkQuestion

try:
    from processing.embedding.embed import HashEmbedding
except ImportError:  # pragma: no cover — direct-script fallback
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from processing.embedding.embed import HashEmbedding  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Arm seeds — the three measured conditions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColdSeed:
    """No prior knowledge. Empty graph, no retrieval substrate → cold loop."""

    name: str = "cold"


@dataclass(frozen=True)
class WarmSeed:
    """Seeded with the question's labelled ON-TOPIC prior units. Reached only via
    the deposit→retrieve→reuse surface."""

    name: str = "warm"


@dataclass(frozen=True)
class IrrelevantSeed:
    """Seeded with the SAME COUNT of OFF-TOPIC units as the warm arm. The §2
    graph-size control: differs from warm only in topical relevance."""

    name: str = "irrelevant"


ArmSeed = "ColdSeed | WarmSeed | IrrelevantSeed"


# Off-topic unit texts for the irrelevant arm. Drawn from the zero-overlap
# control domains so they are GENUINELY unrelated to any high/partial question —
# the graph is non-empty but topically disjoint. Cycled to match the warm arm's
# seeded-unit count for any given question (graph-size parity).
_OFF_TOPIC_UNITS: tuple[str, ...] = (
    "the Mariner 1 launch failure traced to a transcription error in guidance equations",
    "tardigrade anhydrobiosis relies on trehalose and intrinsically disordered proteins",
    "the Hanseatic Kontor resolved member disputes through an internal aldermen council",
    "Roman maritime concrete gains seawater durability from pozzolanic ash crystal growth",
    "medieval guild apprenticeship terms were fixed by charter rather than negotiation",
    "the basalt aggregate in volcanic concrete reacts slowly with intruding seawater",
)


# Deterministic demo-loop parameters. Small ``steps`` keeps CI fast; the cost is
# the SAME for every arm (the demo loop is reuse-blind, by design — see the
# module docstring). ``delay_s=0`` so wall_ms is event-emission span only.
DEMO_STEPS = 3
DEMO_COST_PER_STEP = 0.01


# ---------------------------------------------------------------------------
# Arm result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArmResult:
    """One arm-run's outcome: the measured cost-to-resolve plus the provenance a
    reviewer needs to trust it — which graph file the arm wrote (distinct per
    arm), the investigation id, the seeded unit count, and whether the reuse pack
    was assembled (warm/irrelevant) or absent (cold)."""

    question_id: str
    arm: str
    investigation_id: str
    db_path: str
    cost: CostToResolve
    seeded_unit_count: int
    reuse_substrate_active: bool
    cache_enabled: bool


# ---------------------------------------------------------------------------
# Seeding — through the REAL deposit surface (no back door)
# ---------------------------------------------------------------------------


def _seed_units(
    db_path: str,
    emb: HashEmbedding,
    *,
    unit_texts: Sequence[str],
    prior_investigation: str,
) -> list[str]:
    """Seed a graph with insight knowledge units, each grounded on a claim node +
    a servable document, in ONE write transaction (the single writer). Mirrors
    ``tests/test_knowledge_reuse_spr06.py::_seed_graph`` — the proven seeding
    convention — so the warm arm reaches units through the SAME path SPR-06's
    own tests exercise. Returns the deposited node ids."""
    con = connect_write(db_path, purpose="spr09_seed")
    node_ids: list[str] = []
    try:
        init_database(con)
        con.execute("BEGIN")
        for i, text in enumerate(unit_texts):
            doc_id = f"doc-{prior_investigation}-{i}"
            chunk_id = f"chunk-{prior_investigation}-{i}"
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, "
                "document_type, content_class) VALUES (?, ?, 1, 'paper', 'public_domain')",
                [doc_id, f"seed {i}"],
            )
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
                "embedding, token_count) VALUES (?, ?, ?, ?, ?, ?)",
                [chunk_id, doc_id, i, text, emb.encode(text), max(1, len(text) // 4)],
            )
            claim_id = insert_node(
                con, canonical_label=f"claim {i}: {text}", node_type="claim",
                graph_scope="depth", investigation_id=prior_investigation,
                embedding=emb.encode(text), on_conflict="ignore",
            )
            nid = promote_insight(
                text=text, investigation_id=prior_investigation, confidence="high",
                supported_by=[claim_id], source_document_id=doc_id, chunk_id=chunk_id,
                embedding_provider=emb, con=con,
            )
            node_ids.append(nid)
        con.execute("COMMIT")
    finally:
        con.close()
    return node_ids


def _init_empty_graph(db_path: str) -> None:
    """Initialise an empty graph for the cold arm — the schema exists but no
    units. The cold arm runs with ``retrieval_substrate=None`` regardless; the
    empty file just keeps the arms symmetric (every arm owns a real graph file)."""
    con = connect_write(db_path, purpose="spr09_cold_init")
    try:
        init_database(con)
    finally:
        con.close()


# ---------------------------------------------------------------------------
# M2 — run one arm over the existing ResearchRunner
# ---------------------------------------------------------------------------


def _warm_unit_texts(question: BenchmarkQuestion) -> list[str]:
    """The on-topic seed texts for the warm arm. We derive a topical unit text
    from each ``seeded_unit_id`` label PLUS the question text, so the seeded
    units share vocabulary with the question (real similarity, not a back-door
    answer). A question with no seeded units (the zero-overlap control) seeds
    nothing in the warm arm — it cannot compound and must stay flat."""
    texts: list[str] = []
    for unit_id in question.seeded_unit_ids:
        topic = unit_id.replace("u-", "").replace("-", " ")
        texts.append(f"{topic}: {question.text}")
    return texts


def _irrelevant_unit_texts(count: int) -> list[str]:
    """``count`` off-topic units (graph-size parity with the warm arm)."""
    if count <= 0:
        return []
    return [_OFF_TOPIC_UNITS[i % len(_OFF_TOPIC_UNITS)] for i in range(count)]


def run_arm(
    question: BenchmarkQuestion,
    seed: ArmSeed,
    *,
    events_dir: str,
    graphs_dir: str,
    cache_enabled: bool = False,
    steps: int = DEMO_STEPS,
    cost_per_step: float = DEMO_COST_PER_STEP,
    run_index: int = 0,
) -> ArmResult:
    """Run one arm of one question and measure its cost-to-resolve.

    Drives the EXISTING ``HostLocalRunner`` (§16: no new runtime). The arm's
    graph is acquired via ``PersonalGraphHandle`` (distinct ``{user_id}.duckdb``).
    For the warm/irrelevant arms a ``BruteForceSubstrate`` over the seeded graph
    is injected as ``retrieval_substrate`` so ``start`` exercises the reuse path
    (retrieve_prior_units → filter_reusable → knowledge.reused). The cold arm
    passes ``retrieval_substrate=None`` (the automatic no-reuse path).

    ``cache_enabled`` records the §2 dual-cache mode on the result; the
    deterministic demo loop makes no provider calls, so the flag is provenance
    for the artifact, not an active prompt cache (documented in the README)."""
    arm_name = seed.name
    emb = HashEmbedding()

    # Distinct per-arm graph identity (single-writer-per-graph). The user_id ties
    # in the question, arm, and run index so concurrent/repeated arms never share
    # a writer.
    router = GraphRouter(personal_graphs_dir=graphs_dir)
    user_id = f"spr09-{question.question_id}-{arm_name}-{run_index}"
    handle = resolve_personal_graph(router, user_id=user_id)
    db_path = handle.db_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    seeded_node_ids: list[str] = []
    prior_inv = f"prior-{user_id}"
    if isinstance(seed, WarmSeed):
        texts = _warm_unit_texts(question)
        if texts:
            seeded_node_ids = _seed_units(db_path, emb, unit_texts=texts, prior_investigation=prior_inv)
        else:
            _init_empty_graph(db_path)
    elif isinstance(seed, IrrelevantSeed):
        # Graph-size parity with warm: same COUNT of units, off-topic.
        texts = _irrelevant_unit_texts(len(question.seeded_unit_ids))
        if texts:
            seeded_node_ids = _seed_units(db_path, emb, unit_texts=texts, prior_investigation=prior_inv)
        else:
            _init_empty_graph(db_path)
    else:  # ColdSeed
        _init_empty_graph(db_path)

    # Warm/irrelevant arms get a live retrieval substrate over their seeded graph
    # (reuse path active); the cold arm gets None (automatic no-reuse).
    reuse_substrate = None
    if not isinstance(seed, ColdSeed):
        reuse_substrate = make_substrate("brute_force", db_path, model=emb)

    investigation_id = f"{user_id}-{uuid.uuid4().hex[:8]}"
    try:
        cost = asyncio.run(
            _drive_one(
                investigation_id=investigation_id,
                question=question,
                reuse_substrate=reuse_substrate,
                events_dir=events_dir,
                steps=steps,
                cost_per_step=cost_per_step,
                seeded_node_ids=seeded_node_ids,
            )
        )
    finally:
        if reuse_substrate is not None:
            reuse_substrate.close()

    return ArmResult(
        question_id=question.question_id,
        arm=arm_name,
        investigation_id=investigation_id,
        db_path=db_path,
        cost=cost,
        seeded_unit_count=len(seeded_node_ids),
        reuse_substrate_active=reuse_substrate is not None,
        cache_enabled=cache_enabled,
    )


async def _drive_one(
    *,
    investigation_id: str,
    question: BenchmarkQuestion,
    reuse_substrate: Any | None,
    events_dir: str,
    steps: int,
    cost_per_step: float,
    seeded_node_ids: Sequence[str],
) -> CostToResolve:
    """Start one research on the host-local runner, drain its stream to ``done``,
    then measure the trajectory it wrote. This is the verified integration path:
    ``runner.start(...)`` → ``async for ev in runner.stream(handle)`` until
    ``ev.kind == "done"``; events land on ``{events_dir}/{investigation_id}.jsonl``."""
    runner = HostLocalRunner(
        loop_fn=make_demo_loop(steps=steps, cost_per_step=cost_per_step, delay_s=0.0),
        events_dir=events_dir,
        retrieval_substrate=reuse_substrate,
        seal_on_complete=False,  # keep JSONL so trajectory() reads it without pyarrow
    )
    plan = ResearchPlan(
        investigation_id=investigation_id,
        sub_question=question.text,
        budget=BudgetCap(cost_usd=10.0, max_steps=max(steps + 5, 50)),
    )
    handle = await runner.start(investigation_id, plan)
    async for ev in runner.stream(handle):
        if ev.kind == "done":
            break
    await runner.join()

    return measure_investigation(
        investigation_id, events_dir=events_dir, seeded_node_ids=seeded_node_ids
    )
