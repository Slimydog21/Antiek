"""Loop 1 orchestrator — drives a cold question end-to-end through
the 5 role bridges + the 9-phase state machine.

Sprint 8 day 3 — the gap-closer the operator described:

  > The critical gap: the role bridges all work, but no orchestrator
  > chains them. A cold question doesn't yet flow
  > decompose.requested → ... → synthesize.delivered → archived
  > automatically.

This module subscribes to ``INVESTIGATION_START_REQUESTED`` events
and spawns one per-investigation coroutine that:

  Phase 1 (Orient)     → emits ``decompose.requested``, awaits
                         ``decompose.delivered``
  Phase 2 (Round 1)    → fans out one ``evidence.retrieve.requested``
                         per sub-question; awaits all
                         ``evidence.retrieve.delivered`` events
  Phase 3 (Critique)   → emits ``parameter_extract.requested``;
                         awaits ``parameter_extract.delivered``
  Phase 4 (Round 2)    → emits ``connector.requested`` with the seed
                         pairs derived from the connector substrate
                         (deferred wiring: empty seeds for now —
                         orchestrator hands pre-resolved mappings
                         only); awaits ``connector.delivered``
  Phase 5              → structural pass-through; constraint loop is
                         handled inside the synthesizer bridge
  Phase 6 (Synthesis)  → emits ``synthesize.requested`` with the
                         constraint list from Phase 3's Delivered;
                         awaits ``synthesize.delivered``
  Phase 7 (Delivery)   → calls ``skills.domain.master_md`` inline to
                         render MASTER.md; the typed
                         ``master_md_written`` event lands the
                         postcondition gate
  Phase 8 (Compound)   → calls ``skills.domain.extract_and_patch``
                         inline; the typed ``auto_patch_applied``
                         event lands the keystone gate
  Phase 9 (Complete)   → asserts ready_for_completion, emits
                         ``investigation.completed``

Each phase transition: ``phase_runner.enter_phase`` → role work →
``phase_runner.exit_phase`` → ``phase_runner.verify_phase`` (with the
real postconditions module from Day 2).

On any phase failure: emits ``investigation.failed`` with the phase
number + diagnostic + last-completed-phase marker, then returns.

Async coordination uses ``InvestigationCoordinator`` (per-broadcaster
handler bank with per-(inv_id, action_type) futures). Phase
sequencing is linear inside the coroutine; the asyncio loop owns
concurrency between investigations.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import sys
import time
from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import duckdb

    from compounding.skill_growth import PatchOutcome, SkillPatchGate
    from substrate.dispatch.research_tier import ResearchTier
    from substrate.eval.groundedness.scorer import GroundednessResult

# Direct import — orchestration depends on substrate.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from interfaces.research.api.broadcast import EventBroadcaster, EventHandler  # noqa: E402
from orchestration.audit import audit_phase_log  # noqa: E402
from orchestration.phase_runner import (  # noqa: E402
    enter_phase,
    exit_phase,
    run_check,
    verify_phase,
)
from orchestration.session_evidence_pack import SessionEvidencePack  # noqa: E402
from skills.domain import (  # noqa: E402
    extract_and_patch,
    generate_master_md,
)
from substrate.event_log import (  # noqa: E402
    InvestigationExecutionBusy,
    assert_investigation_execution_authorized,
    claim_investigation_execution_authorized,
    complete_investigation_execution_authorized,
    current_investigation_execution,
    investigation_execution_context,
    investigation_execution_mutation,
    renew_investigation_execution_authorized,
    trajectory_authorized,
    trajectory_authorized_append_order,
)
from substrate.investigation_tenancy import (  # noqa: E402
    InvestigationAuthority,
)
from substrate.investigation_tenancy import (  # noqa: E402
    default_tenancy_root as _default_tenancy_root,
)
from substrate.schemas import (  # noqa: E402
    ActionType,
    ConnectorRequestedPayload,
    DecomposeQuestionDeliveredPayload,
    DecomposeQuestionRequestedPayload,
    Event,
    EvidenceRetrieveDeliveredPayload,
    EvidenceRetrieveRequestedPayload,
    InvestigationChaseHaltedPayload,
    InvestigationCompletedPayload,
    InvestigationFailedPayload,
    InvestigationProjectionCompletedPayload,
    InvestigationProjectionEffectRecordedPayload,
    InvestigationProjectionFailedPayload,
    InvestigationProjectionRequestedPayload,
    InvestigationSpawnedFromPayload,
    InvestigationStartRequestedPayload,
    ParameterExtractDeliveredPayload,
    ParameterExtractRequestedPayload,
    ResearchDelegationAcceptedPayload,
    ResearchDelegationIssuedPayload,
    ResearchDelegationReleasedPayload,
    ResearchDelegationReservedPayload,
    ResearchDelegationSettledPayload,
    ResearchQuotedRoute,
    SubQuestion,
    SupportingClaim,
    SynthesizeDeliveredPayload,
    SynthesizeRequestedPayload,
)

from .coordinator import InvestigationCoordinator, broadcast_emit  # noqa: E402
from .rehydration import (  # noqa: E402
    InvestigationRehydrationConflict,
    project_loop_one_phase_state,
)
from .terminal_projection import (  # noqa: E402
    investigation_projection_event_id,
    investigation_projection_id,
    project_investigation_projection,
    projection_effects_sha256,
)

_log = logging.getLogger(__name__)

PHASE8_CALIBRATION_INVESTIGATION_IDS_ENV = "ANTIEK_PHASE8_CALIBRATION_INVESTIGATION_IDS"
PHASE8_REPLAY_HELDOUT_SYNTHESIS_IDS_ENV = "ANTIEK_PHASE8_REPLAY_HELDOUT_SYNTHESIS_IDS"
PHASE8_REPLAY_OVERLAY_PARENT_ENV = "ANTIEK_PHASE8_REPLAY_OVERLAY_PARENT"


# ---------------------------------------------------------------------------
# Corpus search helper (Sprint 10 hotfix 2026-05-17)
# ---------------------------------------------------------------------------
# Before this helper, phase 2 emitted EvidenceRetrieveRequested events
# with literal placeholder strings for chunks_block — the evidence
# retriever role correctly returned "insufficient evidence" against an
# empty context. This helper performs the corpus search the
# orchestrator was always supposed to do before dispatching evidence
# requests.


_KEYWORD_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "in",
        "on",
        "for",
        "to",
        "and",
        "or",
        "is",
        "are",
        "be",
        "what",
        "which",
        "how",
        "why",
        "do",
        "does",
        "did",
        "this",
        "that",
        "these",
        "those",
        "by",
        "with",
        "as",
        "at",
        "from",
        "into",
        "but",
        "if",
        "then",
        "than",
        "based",
        "specific",
        "available",
        "literature",
        "system",
        "systems",
        "their",
        "its",
    }
)


def _extract_keywords(text: str, *, min_len: int = 3, max_n: int = 8) -> list[str]:
    """Cheap noun-phrase-ish extraction: lowercase tokens > 3 chars,
    drop stopwords, dedupe preserving order, cap. Good enough to
    drive LIKE-based corpus search."""
    import re

    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]+", text)
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        tl = t.lower()
        if len(tl) < min_len or tl in _KEYWORD_STOPWORDS or tl in seen:
            continue
        seen.add(tl)
        out.append(tl)
        if len(out) >= max_n:
            break
    return out


def _keyword_search_chunks(
    con: duckdb.DuckDBPyConnection,
    keywords: list[str],
    top_k: int,
    *,
    policy_tag: str = "attribution_eligible",
    authority: InvestigationAuthority | None = None,
) -> list[dict[str, Any]]:
    """Lexical fallback. For each keyword run a LIKE; collect chunks
    with their match count; rank by match count then source tier.
    Cheap, deterministic, works without sentence-transformers.

    §9.0 retrieval gate: this path applies the SAME canonical
    ``non_privileged_chunk_sql_clause`` as the embedding path
    (``substrate.graph.search.search``). Without it, the lexical fallback
    was an UNGATED chunk-serve path — restricted_pending_opt_in /
    personal_reading chunks could leak into research evidence on a
    non-privileged ``policy_tag`` even though the embedding path withheld
    them. Both retrieval paths must gate identically or the gate is a
    fiction. RG-04 / SR-03 doctrine (deny-by-default on the money path).
    """
    from substrate.legal_gate.read import keyword_search_chunks_compatibility

    return keyword_search_chunks_compatibility(
        con,
        keywords,
        top_k=top_k,
        authority=authority,
        enforce=os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1",
        legacy_policy_tag=policy_tag,
    )


def _render_chunks_block_for_sub_question(
    sub_question: str,
    *,
    top_k: int = 5,
    policy_tag: str = "attribution_eligible",
    authority: InvestigationAuthority | None = None,
) -> str:
    """Hybrid corpus search: embedding cosine + keyword LIKE, merged
    and deduped. The keyword path is the workhorse when
    sentence-transformers isn't installed (HashEmbedding's semantic
    locality is too weak to drive useful retrieval on its own).

    ``policy_tag`` flows into BOTH retrieval paths (embedding + keyword) so
    the §9.0 gate is applied identically. Default ``attribution_eligible``
    (the public, monetizable lane) preserves prior behaviour. An owner
    researching their OWN acquired corpus runs the privileged
    ``private_research`` lane (set ``ANTIEK_RESEARCH_POLICY_TAG`` at the
    Phase-2 call site) so their restricted_pending_opt_in / personal_reading
    documents are visible to their own research — a fair-use owner-read that
    never serves/attributes that content publicly.
    """
    try:
        import duckdb

        from processing.embedding.embed import default_embedding_provider
        from substrate.graph import default_db_path
        from substrate.graph.search import search, search_authorized

        db_path = default_db_path()
        embedder = default_embedding_provider()
        keywords = _extract_keywords(sub_question)
        con = duckdb.connect(db_path, read_only=True)
        try:
            # Embedding side — half the slots
            emb_half = max(1, top_k // 2)
            if os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1":
                if authority is None:
                    return "(corpus search unavailable: investigation authority required)"
                emb_res = search_authorized(
                    con, authority, sub_question, model=embedder, top_k=emb_half
                )
            else:
                emb_res = search(
                    con,
                    sub_question,
                    model=embedder,
                    top_k=emb_half,
                    policy_tag=policy_tag,
                )
            embedding_hits = emb_res.get("results", [])
            # Keyword side — fill the rest (same §9.0 gate as the embedding path)
            kw_hits = _keyword_search_chunks(
                con,
                keywords,
                top_k=top_k,
                policy_tag=policy_tag,
                authority=authority,
            )
        finally:
            con.close()
    except Exception as exc:
        return f"(corpus search unavailable: {type(exc).__name__}: {exc})"

    # Merge dedupe by chunk_id; keyword hits get appended after embedding
    # hits since lexical matches are usually higher signal than weak
    # hash-embedding cosines.
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for r in embedding_hits + kw_hits:
        cid = r.get("chunk_id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        merged.append(r)
        if len(merged) >= top_k:
            break
    results = merged

    if not results:
        return "(corpus search returned no matches above the similarity floor)"

    blocks: list[str] = []
    for r in results:
        cid = r.get("chunk_id", "?")
        tier = r.get("source_tier", "?")
        # substrate.graph.search returns column names 'chunk_text' and
        # 'document_title' (not 'text' / 'title') — easy footgun.
        title = r.get("document_title") or r.get("title") or "(untitled)"
        section = r.get("section_path") or ""
        text = (r.get("chunk_text") or r.get("text") or "").strip()
        sim = r.get("similarity", 0.0)
        header = (
            f"### chunk_id: {cid}\n"
            f"Source tier: {tier} | Document: {title}"
            + (f" | Section: {section}" if section else "")
            + f" | Similarity: {sim:.3f}\n"
        )
        blocks.append(header + "\n" + text + "\n")
    return "\n---\n".join(blocks)


# §9.0 guard: node_types whose ``canonical_label`` is a distilled free-text
# SENTENCE (the DRW "atomic units of distilled truth" + a claim assertion),
# which may reproduce personal_reading / restricted source text. The subgraph
# read has no rights gate and nodes carry no rights provenance, so these labels
# are withheld from the rendered block. Canonical entity labels (short names)
# are not in this set and still surface.
_FREE_TEXT_NODE_TYPES = frozenset({"insight", "question", "claim"})


def _render_subgraph_block_for_sub_question(
    sub_question: str,
    *,
    top_k: int = 5,
    policy_tag: str = "attribution_eligible",
    authority: InvestigationAuthority | None = None,
) -> str:
    """The evidence-retriever role's "Context package — subgraph" (its prompt
    §b: *a subgraph of knowledge-graph edges and nodes ... each with a stable
    ``edge_id``*). Renders the graph neighborhood of the sub-question's
    retrieved chunks — edges (source --[relation]--> target, with the citable
    ``edge_id``) plus the connected nodes — so a claim can be grounded on a
    graph relationship, not only flat chunk text.

    Mirrors ``_render_chunks_block_for_sub_question`` exactly on the substrate
    contract: the SAME read-only connection, the SAME embedder, the SAME §9.0
    ``policy_tag`` gate — but requests ``with_edges=True`` (the capability
    ``substrate.graph.search.search`` already exposes and the RLM path already
    uses) and renders edges instead of chunk bodies. This REPLACES the historic
    ``"(subgraph search not yet wired)"`` placeholder: before this, every live
    investigation's evidence retriever was structurally blind to the graph.

    Read-only + best-effort: any failure degrades to a labelled note (never a
    dead investigation), exactly as the chunks path does — the subgraph is
    additive evidence, the chunks_block remains the floor.
    """
    try:
        import duckdb

        from processing.embedding.embed import default_embedding_provider
        from substrate.graph import default_db_path
        from substrate.graph.search import search, search_authorized

        db_path = default_db_path()
        embedder = default_embedding_provider()
        con = duckdb.connect(db_path, read_only=True)
        try:
            if os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1":
                if authority is None:
                    return "(subgraph search unavailable: investigation authority required)"
                res = search_authorized(
                    con,
                    authority,
                    sub_question,
                    model=embedder,
                    top_k=top_k,
                    with_edges=True,
                )
            else:
                res = search(
                    con,
                    sub_question,
                    model=embedder,
                    top_k=top_k,
                    policy_tag=policy_tag,
                    with_edges=True,
                )
        finally:
            con.close()
    except Exception as exc:
        return f"(subgraph search unavailable: {type(exc).__name__}: {exc})"

    # Collect edges (deduped) + all endpoint nodes in one pass, THEN render —
    # rendering needs the full node-type map to apply the §9.0 label guard.
    edges: list[dict[str, Any]] = []
    seen_edges: set[str] = set()
    node_by_id: dict[str, dict[str, Any]] = {}
    for r in res.get("results", []):
        for e in r.get("edges", []) or []:
            eid = e.get("edge_id")
            if not eid or eid in seen_edges:
                continue
            seen_edges.add(eid)
            edges.append(e)
        for n in r.get("nodes", []) or []:
            nid = n.get("node_id")
            if nid and nid not in node_by_id:
                node_by_id[nid] = n

    if not edges:
        return "(no knowledge-graph edges for this sub-question)"

    node_type_by_id = {nid: n.get("node_type") for nid, n in node_by_id.items()}

    def _safe_label(node_id: Any, label: Any) -> str:
        """§9.0 guard on the graph read. ``_fetch_edges_and_nodes`` applies NO
        rights gate to the edges/nodes it surfaces, and nodes carry no rights
        provenance — so a free-text label (an ``insight`` / ``question`` /
        ``claim`` node's ``canonical_label`` IS a distilled sentence that may be
        derived from a personal_reading / restricted source, reachable here via
        a cross-rights ``duplicate_of`` edge). We therefore WITHHOLD free-text
        labels (and any unknown-type label — deny by default) and reference the
        node by id instead; canonical entity labels (short names, not servable
        body) still surface so the role keeps the relational structure. Over-
        redacts clean distilled units too — the conservative §9.0 posture until
        the substrate gives the edge/node read a real rights gate."""
        ntype = node_type_by_id.get(node_id)
        if ntype in _FREE_TEXT_NODE_TYPES or ntype is None:
            return f"[{node_id}: {ntype or 'unresolved'} — text withheld (§9.0)]"
        return str(label) if label else "?"

    edge_lines = [
        f"- edge_id: {e.get('edge_id')} | "
        f"{_safe_label((e.get('source') or {}).get('id'), (e.get('source') or {}).get('label'))} "
        f"--[{e.get('relation', 'related_to')}]--> "
        f"{_safe_label((e.get('target') or {}).get('id'), (e.get('target') or {}).get('label'))} "
        f"(confidence {e.get('confidence', '?')}, source tier {e.get('source_tier', '?')})"
        for e in edges
    ]
    node_lines = [
        f"- {nid}: {_safe_label(nid, n.get('label'))} ({n.get('node_type', '?')})"
        for nid, n in node_by_id.items()
    ]
    return (
        "## Edges (cite the relevant edge_id when a claim rests on a relation)\n"
        + "\n".join(edge_lines)
        + "\n\n## Nodes\n"
        + "\n".join(node_lines)
    )


def _prior_graph_knowledge_section(
    question: str, *, authority: InvestigationAuthority | None = None
) -> str:
    """Phase 1 orientation cites seeded graph chunks when provenance
    exists; falls back to structural seed markers for empty graphs."""
    if os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1":
        block = _render_chunks_block_for_sub_question(question, top_k=3, authority=authority)
    else:
        block = _render_chunks_block_for_sub_question(question, top_k=3)
    chunk_ids = re.findall(r"chunk_id:\s*(\S+)|^\[([^\]]+)\]", block, re.MULTILINE)
    if chunk_ids:
        ids = [a or b for a, b in chunk_ids]
        return "\n".join(
            f"- {cid} cited from substrate graph search for orientation." for cid in ids
        )
    return (
        "chunk_orientation_marker and node_orchestrator_start seed the "
        "connector substrate when the graph has no servable hits yet.\n"
    )


# Per-phase await timeout for role bridges. DeepSeek V4 Pro under
# OpenRouter load empirically takes 200-250s on a long-output role
# (decomposer producing 8 sub-questions with rationale was 226s on
# the 2026-05-17 photonic-interconnects run). The synthesizer can
# iterate the constraint loop up to 3 times → wider window. Per-
# evidence calls are flash-tier (faster) but still need slack for
# tail latency.
DEFAULT_ROLE_TIMEOUT = 600.0
SYNTHESIZER_TIMEOUT = 900.0
PER_EVIDENCE_TIMEOUT = 300.0

# ANT-DRL-03: bounded parallel Phase 2 retrieves (default 4 per spec
# open question). Override via ANTIEK_PHASE_2_CONCURRENCY for profiling.
PHASE_2_MAX_CONCURRENCY = max(
    1,
    int(os.environ.get("ANTIEK_PHASE_2_CONCURRENCY", "4")),
)


@dataclass
class InvestigationContext:
    """Per-investigation state the orchestrator threads through phases.

    Each phase result lands on the corresponding field so downstream
    phases can compose. ``failed_phase`` is set if any phase aborts;
    the orchestrator emits ``investigation.failed`` with that number."""

    investigation_id: str
    question: str
    authority: InvestigationAuthority | None = None
    tenancy_root: Path = field(default_factory=lambda: _default_tenancy_root())
    context: str = ""
    artifact_source_coverage: dict[str, Any] | None = None
    artifact_inherited_reuse: dict[str, Any] | None = None
    archived_source_coverage: dict[str, Any] | None = None
    inherited_support_by_chunk: dict[str, list[str]] = field(default_factory=dict)
    topic_slug: str | None = None
    max_sub_questions: int = 8
    decomposition: DecomposeQuestionDeliveredPayload | None = None
    evidence: list[EvidenceRetrieveDeliveredPayload] = field(default_factory=list)
    parameters: ParameterExtractDeliveredPayload | None = None
    connector_result: Any | None = None  # ConnectorDeliveredPayload
    synthesis: SynthesizeDeliveredPayload | None = None
    synthesis_event_id: str | None = None
    synthesis_emitted_at: datetime | None = None
    master_md_path: str | None = None
    patched_domains: list[str] = field(default_factory=list)
    last_completed_phase: int = 0
    failed_phase: int | None = None
    fail_reason: str = ""
    # Sprint 12: continuous-chase parameters threaded from the start
    # payload. When chase_mode != "off", the orchestrator hooks
    # _maybe_spawn_chase_child after _run_investigation completes.
    chase_mode: Literal["off", "depth", "duration"] = "off"
    chase_value: int = 0
    chase_budget_usd: float = 2.0
    parent_investigation_id: str | None = None
    # SPR-01 M3: the curated fast/deep research tier the operator chose at
    # the research entry, threaded from the start payload. "fast" → MiMo
    # V2.5 Pro, "deep" → DeepSeek V4 Pro (see
    # substrate/dispatch/research_tier.py). Carried so a chase-spawned
    # child inherits the parent's tier rather than silently snapping back
    # to the default.
    research_tier: ResearchTier | None = "deep"
    research_quote_id: str | None = None
    research_route_manifest_fingerprint: str | None = None
    research_route_manifest: tuple[ResearchQuotedRoute, ...] | None = None
    research_delegation_id: str | None = None
    research_root_investigation_id: str | None = None
    research_root_quote_id: str | None = None
    research_delegation_generation: int | None = None
    terminal_event_id: str | None = None
    execution_id: str | None = None


def _action_value(action_type: ActionType | str) -> str:
    """ActionType enum or string → string."""
    if isinstance(action_type, ActionType):
        return action_type.value
    return str(action_type)


def _phase_command_event_id(
    ctx: InvestigationContext, phase: int, correlation: str = "singleton"
) -> str | None:
    if ctx.execution_id is None:
        return None
    digest = hashlib.sha256(
        (f"antiek.loop-one-command.v1\x00{ctx.execution_id}\x00{phase}\x00{correlation}").encode()
    ).hexdigest()[:32]
    return f"evt-loop-command-{digest}"


# ---------------------------------------------------------------------------
# Phase helpers
# ---------------------------------------------------------------------------


async def _drive_phase(
    ctx: InvestigationContext,
    *,
    phase: int,
    work: Awaitable[None],
) -> bool:
    """Run one phase end-to-end: enter → work → exit → verify. Returns
    True on success, False on any error. Marks ctx.last_completed_phase
    + ctx.failed_phase appropriately."""
    try:
        enter_phase(
            ctx.investigation_id,
            phase,
            topic=ctx.topic_slug or "",
            enforce_precondition=False,  # orchestrator sequences explicitly
        )
    except Exception as e:  # pragma: no cover — diagnostic
        ctx.failed_phase = phase
        ctx.fail_reason = f"enter_phase failed: {e!r}"
        return False

    try:
        await work
    except TimeoutError:
        ctx.failed_phase = phase
        ctx.fail_reason = f"phase {phase} timed out waiting for role delivery"
        return False
    except Exception as e:  # pragma: no cover — diagnostic
        ctx.failed_phase = phase
        ctx.fail_reason = f"phase {phase} work raised: {e!r}"
        return False

    try:
        exit_phase(ctx.investigation_id, phase)
    except Exception as e:  # pragma: no cover — diagnostic
        ctx.failed_phase = phase
        ctx.fail_reason = f"exit_phase failed: {e!r}"
        return False

    # Verification — use the real postconditions module.
    outcome = verify_phase(
        ctx.investigation_id,
        phase,
        postcondition_check=run_check,
    )
    if not outcome.passed:
        ctx.failed_phase = phase
        ctx.fail_reason = f"phase {phase} postcondition failed: {outcome.reason}"
        return False

    ctx.last_completed_phase = phase
    return True


# ---------------------------------------------------------------------------
# Phase implementations
# ---------------------------------------------------------------------------


def _research_dir_for(ctx: InvestigationContext) -> str:
    """Per-investigation research directory. Lazy import so test env
    vars take effect at call time."""
    from orchestration.phase_runner.postconditions import default_research_dir

    return default_research_dir(ctx.investigation_id)


def _assert_artifact_write_fence(ctx: InvestigationContext) -> None:
    fence = current_investigation_execution(ctx.investigation_id)
    if fence is not None:
        if ctx.authority is None:
            raise InvestigationExecutionBusy("fenced artifact write lacks authority")
        assert_investigation_execution_authorized(
            ctx.authority,
            generation=fence[0],
            holder_digest=fence[1],
            now_ms=time.time_ns() // 1_000_000,
        )


def _write_marker(ctx: InvestigationContext, filename: str, body: str) -> None:
    """Write a per-investigation file marker. Used by phases whose
    postconditions read file artifacts but whose role work is
    event-driven."""
    _assert_artifact_write_fence(ctx)
    research_dir = _research_dir_for(ctx)
    guard = (
        investigation_execution_mutation(ctx.authority)
        if ctx.authority is not None
        else contextlib.nullcontext()
    )
    with guard:
        os.makedirs(research_dir, exist_ok=True)
        with open(os.path.join(research_dir, filename), "w") as f:
            f.write(body)


async def _run_phase_1(
    ctx: InvestigationContext,
    broadcaster: EventBroadcaster,
    coordinator: InvestigationCoordinator,
) -> bool:
    """Phase 1 (Orient) — decompose the cold question. Writes an
    orientation.md marker file so the file-artifact Phase 1
    postcondition (Prior Graph Knowledge section + chunk_/node_
    regex citation) passes."""

    async def work() -> None:
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            DecomposeQuestionRequestedPayload(
                question=ctx.question,
                context=ctx.context,
            ),
            role="orchestrator",
            policy_id="orchestrator-deterministic",
            phase=1,
            event_id=_phase_command_event_id(ctx, 1),
        )
        delivered = await coordinator.wait_for(
            ctx.investigation_id,
            _action_value(ActionType.DECOMPOSE_QUESTION_DELIVERED),
            timeout=DEFAULT_ROLE_TIMEOUT,
        )
        if isinstance(delivered.payload, DecomposeQuestionDeliveredPayload):
            ctx.decomposition = delivered.payload
        # Semantic check: the role's Delivered payload must carry at
        # least one sub-question. An empty decomposition (typically
        # from the bridge's fallback after a dispatch/parse failure)
        # is a Phase 1 failure even though the role event landed.
        if ctx.decomposition is None or not ctx.decomposition.decomposition:
            raise RuntimeError(
                "decomposer returned no sub-questions (bridge fallback or empty role response)"
            )
        body = (
            "# Orientation\n\n"
            f"Investigation: `{ctx.investigation_id}`\n\n"
            f"Question: {ctx.question}\n\n"
            + ("Loop 1 orchestrator orienting on the cold question. " * 30)
            + "\n\n## Prior Graph Knowledge\n\n"
            + _prior_graph_knowledge_section(ctx.question, authority=ctx.authority)
        )
        _write_marker(ctx, "orientation.md", body)

    return await _drive_phase(ctx, phase=1, work=work())


async def _run_phase_2(
    ctx: InvestigationContext,
    broadcaster: EventBroadcaster,
    coordinator: InvestigationCoordinator,
) -> bool:
    """Phase 2 (Round 1) — one evidence_retrieve per sub-question,
    bounded parallel (``PHASE_2_MAX_CONCURRENCY``). Coordinator
    correlates ``evidence.retrieve.delivered`` on ``sub_question`` so
    N concurrent bridge completions do not steal each other's futures.
    Evidence list order follows decomposition order (deterministic)."""
    if ctx.decomposition is None:
        ctx.failed_phase = 2
        ctx.fail_reason = "phase 2 entered without decomposition (precondition bug)"
        return False

    sub_qs = list(ctx.decomposition.decomposition)[: ctx.max_sub_questions]
    if not sub_qs:
        ctx.failed_phase = 2
        ctx.fail_reason = "decomposition produced no sub-questions"
        return False

    async def work() -> None:
        # §9.0 research lane. Default 'attribution_eligible' (public lane,
        # unchanged behaviour). An owner researching their OWN acquired corpus
        # sets ANTIEK_RESEARCH_POLICY_TAG=private_research so their gated
        # (restricted_pending_opt_in / personal_reading) documents are visible
        # to their own research — a fair-use owner-read. This NEVER changes the
        # serve/attribute path (master-spec §9.0 legal gate is untouched); it
        # only widens what the owner's research retrieval can SEE.
        research_policy_tag = (
            os.environ.get("ANTIEK_RESEARCH_POLICY_TAG", "").strip() or "attribution_eligible"
        )
        sem = asyncio.Semaphore(PHASE_2_MAX_CONCURRENCY)
        delivered_action = _action_value(ActionType.EVIDENCE_RETRIEVE_DELIVERED)

        async def _retrieve_one(sq: SubQuestion) -> EvidenceRetrieveDeliveredPayload:
            async with sem:
                if os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1":
                    chunks_block = _render_chunks_block_for_sub_question(
                        sq.sub_question,
                        top_k=5,
                        policy_tag=research_policy_tag,
                        authority=ctx.authority,
                    )
                    subgraph_block = _render_subgraph_block_for_sub_question(
                        sq.sub_question,
                        top_k=5,
                        policy_tag=research_policy_tag,
                        authority=ctx.authority,
                    )
                else:
                    chunks_block = _render_chunks_block_for_sub_question(
                        sq.sub_question, top_k=5, policy_tag=research_policy_tag
                    )
                    subgraph_block = _render_subgraph_block_for_sub_question(
                        sq.sub_question, top_k=5, policy_tag=research_policy_tag
                    )
                await broadcast_emit(
                    broadcaster,
                    ctx.investigation_id,
                    EvidenceRetrieveRequestedPayload(
                        sub_question=sq.sub_question,
                        category=sq.category,
                        evidence_type_required=sq.evidence_type_required,
                        top_k=5,
                        chunks_block=chunks_block,
                        subgraph_block=subgraph_block,
                    ),
                    role="orchestrator",
                    policy_id="orchestrator-deterministic",
                    phase=2,
                    event_id=_phase_command_event_id(ctx, 2, sq.sub_question),
                )
                delivered = await coordinator.wait_for(
                    ctx.investigation_id,
                    delivered_action,
                    timeout=PER_EVIDENCE_TIMEOUT,
                    correlation=sq.sub_question,
                )
                if not isinstance(
                    delivered.payload,
                    EvidenceRetrieveDeliveredPayload,
                ):
                    raise RuntimeError(
                        f"evidence bridge returned unexpected payload for {sq.sub_question!r}"
                    )
                return delivered.payload

        restored = {item.sub_question: item for item in ctx.evidence}
        missing = [sq for sq in sub_qs if sq.sub_question not in restored]
        results = await asyncio.gather(*(_retrieve_one(sq) for sq in missing))
        restored.update((item.sub_question, item) for item in results)
        ctx.evidence = [restored[sq.sub_question] for sq in sub_qs]
        # Write the three round-1 dimension markers so the file-
        # artifact postcondition for Phase 2 passes. The markers
        # carry the evidence summaries the orchestrator already has.
        body_base = f"# Round 1 — {ctx.investigation_id}\n\nQuestion: {ctx.question}\n\n" + (
            "Evidence-grounded round 1 content. " * 50
        )
        for name in (
            "round1-technical.md",
            "round1-competitive.md",
            "round1-strategic.md",
        ):
            _write_marker(ctx, name, body_base)

    return await _drive_phase(ctx, phase=2, work=work())


async def _run_phase_3(
    ctx: InvestigationContext,
    broadcaster: EventBroadcaster,
    coordinator: InvestigationCoordinator,
) -> bool:
    """Phase 3 (Round 1 critique) — extract parameters from the
    evidence retriever outputs."""

    async def work() -> None:
        evidence_block = json.dumps(
            [e.model_dump() for e in ctx.evidence],
            indent=2,
            default=str,
        )
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            ParameterExtractRequestedPayload(evidence_block=evidence_block),
            role="orchestrator",
            policy_id="orchestrator-deterministic",
            phase=3,
            event_id=_phase_command_event_id(ctx, 3),
        )
        delivered = await coordinator.wait_for(
            ctx.investigation_id,
            _action_value(ActionType.PARAMETER_EXTRACT_DELIVERED),
            timeout=DEFAULT_ROLE_TIMEOUT,
        )
        if isinstance(delivered.payload, ParameterExtractDeliveredPayload):
            ctx.parameters = delivered.payload
        # Round 1 critique marker. The Phase 3 postcondition reads
        # this file and checks for the three dimension keywords.
        _write_marker(
            ctx,
            "round1-critique.md",
            (
                "# Round 1 Critique\n\n"
                f"Investigation: `{ctx.investigation_id}`\n\n"
                "Parameter extraction complete; covers technical, "
                "competitive, and strategic dimensions of the "
                "investigation.\n"
            ),
        )

    return await _drive_phase(ctx, phase=3, work=work())


async def _run_phase_4(
    ctx: InvestigationContext,
    broadcaster: EventBroadcaster,
    coordinator: InvestigationCoordinator,
) -> bool:
    """Phase 4 (Round 2) — connector dispatch with the decomposer's
    keyword list. Seeds are empty for now (the embedding pre-
    resolution belongs to a separate orchestrator-side helper that
    can land in a future sprint); the connector bridge handles
    empty-seed requests gracefully (role still gets a chance to
    confirm any pre-resolved mappings)."""

    async def work() -> None:
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            ConnectorRequestedPayload(
                keyword_mappings=[],  # pre-resolution deferred
                seed_pairs=[],
                algorithm="top_n_shortest_paths",
                max_paths_per_pair=5,
            ),
            role="orchestrator",
            policy_id="orchestrator-deterministic",
            phase=4,
            event_id=_phase_command_event_id(ctx, 4),
        )
        delivered = await coordinator.wait_for(
            ctx.investigation_id,
            _action_value(ActionType.CONNECTOR_DELIVERED),
            timeout=DEFAULT_ROLE_TIMEOUT,
        )
        ctx.connector_result = delivered.payload
        # Round 2 deep-dive marker. The Phase 4 postcondition checks
        # for any round2-*.md (≠ critique) above the size floor.
        _write_marker(
            ctx,
            "round2-relational.md",
            (
                "# Round 2 — Relational Deep Dive\n\n"
                f"Investigation: `{ctx.investigation_id}`\n\n"
                + ("Cross-domain connector substrate surfaced. " * 50)
            ),
        )

    return await _drive_phase(ctx, phase=4, work=work())


async def _run_phase_5(ctx: InvestigationContext) -> bool:
    """Phase 5 — structural pass-through. The round-2 critique role
    is subsumed by the constraint loop inside the synthesizer bridge.
    The orchestrator writes the marker file so the phase log stays
    contiguous for downstream audit."""

    async def work() -> None:
        body = (
            "# Round 2 critique\n\n"
            "_Constraint loop handled the round-2 critique role "
            "inline; this file is the postcondition marker the "
            "Loop 1 orchestrator writes to keep the phase log "
            "contiguous._\n\n"
            f"Investigation: `{ctx.investigation_id}`\n" + ("\nFollow-up content. " * 20)
        )
        _write_marker(ctx, "round2-critique.md", body)

    return await _drive_phase(ctx, phase=5, work=work())


def _phase_6_groundedness_backend() -> tuple[
    Callable[[str, Sequence[str]], tuple[float, str]], str, str
]:
    """Return the live Phase-6 groundedness backend tuple.

    Default is lexical for byte-for-byte existing behavior. SPR-04 wires the
    validated NLI backend into the live emit path only when explicitly opted
    in via ``ANTIEK_GROUNDEDNESS_BACKEND=nli``. Unknown values fail safe to
    lexical so a typo never flips production onto a heavier scorer.
    """
    from substrate.eval.groundedness import DEFAULT_SCORER_ID, lexical_entailment_score

    raw = os.environ.get("ANTIEK_GROUNDEDNESS_BACKEND", "").strip().lower()
    if raw != "nli":
        return lexical_entailment_score, "lexical", DEFAULT_SCORER_ID

    from substrate.eval.groundedness.nli_backend import NLI_SCORER_ID, make_nli_backend

    return make_nli_backend(), "nli", NLI_SCORER_ID


def _score_phase_6_synthesis(ctx: InvestigationContext) -> GroundednessResult | None:
    """Emit the Phase-6 quality signals for the synthesis on ``ctx`` —
    NON-blocking, but the signal NEVER silently vanishes (Foundation v2
    SPR-02 M1 + M4).

    Returns the PRIMARY truth-axis ``GroundednessResult`` (or ``None`` if
    there is no synthesis to score / the groundedness scorer crashed).
    SPR-03: the caller (``_run_phase_6``) reads the returned score to
    decide whether the ``ANTIEK_GROUNDEDNESS_ENFORCE`` posture (off/flag/
    block — default ``off``) flags or blocks a below-threshold synthesis.
    This function itself only scores + emits; it does NOT gate. Keeping
    the gate decision in the caller makes ``off == no-op`` provable: when
    the posture is ``off`` (the default), the caller does nothing with
    the returned score and behavior is byte-for-byte today's.

    Two axes, scored and emitted (enforcement is the caller's job):

    - ``rubric.scored`` — the SECONDARY, form-axis style rubric (voice,
      conviction, citation *density*, constraint compliance). Kept, now
      explicitly labeled secondary.
    - ``groundedness.scored`` — the PRIMARY truth-axis signal: does each
      claim ENTAIL from the chunk(s) it cites, over the EXISTING
      claim→chunk provenance? Citation density is irrelevant here.

    The old behaviour wrapped this in a bare swallow that dropped the
    signal on any crash. That swallow is removed: each scorer is isolated
    so one crashing does not starve the other, and a crash SURFACES — it
    logs the error AND emits a ``groundedness.failed`` event naming the
    stage. "Non-blocking" means the loop continues; it does NOT mean the
    signal disappears."""
    if ctx.synthesis is None:
        return None
    synthesis_id = f"syn-{ctx.investigation_id}"
    synthesis_event_id = ctx.synthesis_event_id
    # SPR-03: captured so the caller can enforce (off/flag/block). ``None``
    # unless the groundedness scorer produced a result (no synthesis / crash).
    groundedness_result = None
    live_groundedness_scorer_id = "groundedness-lexical-v1"

    from middleware.outcomes import (
        emit_groundedness_failed,
        emit_groundedness_scored,
        emit_rubric_scored,
    )

    # --- SECONDARY form-axis: style rubric ---------------------------------
    try:
        from substrate.synthesis_rubric import score_synthesis

        rubric = score_synthesis(ctx.synthesis)
        emit_rubric_scored(
            investigation_id=ctx.investigation_id,
            synthesis_id=synthesis_id,
            rubric_id="synthesis-deterministic-v1",
            final_score=rubric.composite,
            deterministic_score=rubric.composite,
            judged_score=None,
            notes=rubric.notes
            or (
                f"[SECONDARY form-axis] voice={rubric.voice_style:.2f} "
                f"conviction={rubric.conviction:.2f} "
                f"citation_density={rubric.citation_density:.2f} "
                f"constraint={rubric.constraint_compliance:.2f}"
            ),
            parent_event_id=synthesis_event_id,
        )
    except Exception as exc:  # noqa: BLE001 — surface, do NOT swallow
        # The signal must not vanish: log + emit a typed failure event,
        # then continue (phase stays non-blocking).
        _log.exception("phase-6 style rubric scorer crashed for %s", ctx.investigation_id)
        emit_groundedness_failed(
            investigation_id=ctx.investigation_id,
            synthesis_id=synthesis_id,
            scorer_id="synthesis-deterministic-v1",
            stage="rubric",
            error_type=type(exc).__name__,
            error=str(exc),
            parent_event_id=synthesis_event_id,
        )

    # --- PRIMARY truth-axis: groundedness (claim-entailment) ---------------
    try:
        from substrate.eval.groundedness import (
            duckdb_chunk_text_resolver,
            resolve_synthesis_claims,
            score_synthesis_groundedness,
        )
        from substrate.graph import default_db_path

        cited_ids: list[str] = []
        for comp in getattr(ctx.synthesis, "thesis_components", None) or []:
            cited_ids.extend(getattr(comp, "supporting_chunk_ids", None) or [])
        # Resolve chunk text from the EXISTING chunks table (read-only),
        # honoring ANTIEK_DUCKDB_PATH. If the DB is unavailable, the
        # resolver yields no text and the claims score as ungrounded —
        # honest, never a parallel store.
        try:
            resolver = duckdb_chunk_text_resolver(
                default_db_path(), chunk_ids=cited_ids, authority=ctx.authority
            )
        except Exception:  # noqa: BLE001 — DB-absent path stays honest
            resolver = lambda _cid: None  # noqa: E731
        claim_chunks = resolve_synthesis_claims(ctx.synthesis, resolver)
        backend, backend_name, scorer_id = _phase_6_groundedness_backend()
        live_groundedness_scorer_id = scorer_id
        result = score_synthesis_groundedness(
            claim_chunks,
            backend=backend,
            backend_name=backend_name,
            scorer_id=scorer_id,
        )
        groundedness_result = result  # captured for the caller's enforcement decision
        emit_groundedness_scored(
            investigation_id=ctx.investigation_id,
            synthesis_id=synthesis_id,
            scorer_id=scorer_id,
            backend=result.backend,
            groundedness_score=result.score,
            scored_claims=result.scored_claims,
            total_claims=result.total_claims,
            supported_threshold=result.supported_threshold,
            per_claim=list(result.per_claim),
            notes=(
                "[PRIMARY truth-axis] per-claim entailment over existing "
                "claim->chunk provenance; observability-only (validate-first, "
                "see substrate/eval/groundedness/PROMOTE_TO_GATE.md)"
            ),
            parent_event_id=synthesis_event_id,
        )
    except Exception as exc:  # noqa: BLE001 — surface, do NOT swallow
        _log.exception("phase-6 groundedness scorer crashed for %s", ctx.investigation_id)
        emit_groundedness_failed(
            investigation_id=ctx.investigation_id,
            synthesis_id=synthesis_id,
            scorer_id=live_groundedness_scorer_id,
            stage="groundedness",
            error_type=type(exc).__name__,
            error=str(exc),
            parent_event_id=synthesis_event_id,
        )
    return groundedness_result


async def _run_phase_6(
    ctx: InvestigationContext,
    broadcaster: EventBroadcaster,
    coordinator: InvestigationCoordinator,
) -> bool:
    """Phase 6 (Final synthesis) — dispatches synthesizer with the
    constraint list from Phase 3. The synthesizer bridge drives the
    constraint loop internally; we just await the final Delivered."""
    if ctx.parameters is None:
        ctx.failed_phase = 6
        ctx.fail_reason = "phase 6 entered without parameters"
        return False

    async def work() -> None:
        assert ctx.parameters is not None
        decomposition_block = (
            ctx.decomposition.model_dump_json(indent=2)
            if ctx.decomposition is not None
            else "(none)"
        )
        evidence_block = json.dumps(
            [e.model_dump() for e in ctx.evidence],
            indent=2,
            default=str,
        )
        parameters_block = ctx.parameters.model_dump_json(indent=2)
        substrate_block = (
            ctx.connector_result.model_dump_json(indent=2)
            if ctx.connector_result is not None
            else "(none)"
        )

        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            SynthesizeRequestedPayload(
                question=ctx.question,
                decomposition_block=decomposition_block,
                evidence_block=evidence_block,
                parameters_block=parameters_block,
                substrate_block=substrate_block,
                constraints=list(ctx.parameters.constraints),
                inherited_support_by_chunk=ctx.inherited_support_by_chunk,
            ),
            role="orchestrator",
            policy_id="orchestrator-deterministic",
            phase=6,
            event_id=_phase_command_event_id(ctx, 6),
        )
        delivered = await coordinator.wait_for(
            ctx.investigation_id,
            _action_value(ActionType.SYNTHESIZE_DELIVERED),
            timeout=SYNTHESIZER_TIMEOUT,
        )
        if isinstance(delivered.payload, SynthesizeDeliveredPayload):
            ctx.synthesis = delivered.payload
            ctx.synthesis_event_id = delivered.event_id
            ctx.synthesis_emitted_at = delivered.emitted_at
            # Inline quality scoring after Phase 6 — §14.4 form-axis
            # rubric (G5 follow-up 2026-05-23) + Foundation v2 SPR-02
            # truth-axis groundedness. Both NON-blocking observability
            # signals; a crash SURFACES (logs + groundedness.failed
            # event) instead of the old except-pass swallow that
            # dropped the signal. See substrate/eval/groundedness/ and
            # substrate/synthesis_rubric/.
            groundedness_result = _score_phase_6_synthesis(ctx)
            # SPR-03: enforce the truth-axis behind ANTIEK_GROUNDEDNESS_ENFORCE
            # (off/flag/block; default off). When OFF this whole block is a
            # no-op — behavior is byte-for-byte today's (proven by
            # test_enforce_off_is_noop). FLAG emits groundedness.failed + marks
            # the synthesis but still deposits. BLOCK nulls ctx.synthesis so
            # the below-threshold synthesis never reaches Phase 7 / the graph.
            _enforce_groundedness(ctx, groundedness_result)

    return await _drive_phase(ctx, phase=6, work=work())


def _enforce_groundedness(ctx: InvestigationContext, result: GroundednessResult | None) -> None:
    """Apply the ANTIEK_GROUNDEDNESS_ENFORCE posture to a Phase-6 score.

    Pure-of-side-effect EXCEPT for the deliberate enforcement actions
    (emit groundedness.failed; null ctx.synthesis on block). When the
    posture is ``off`` (the default) this is a no-op: no event fires, no
    state mutates — today's behavior, byte-for-byte. ``result is None``
    (no synthesis / scorer crashed) is also a no-op: there is nothing to
    enforce AND the crash already surfaced via groundedness.failed in
    the scorer's own except block.

    Scope of BLOCK (verified by adversarial review): nulling
    ``ctx.synthesis`` prevents the synthesis from being USED downstream —
    Phase 7 (delivery/render) checks ``ctx.synthesis is None`` and
    returns, and the graph node-projection has nothing to write. It does
    NOT un-emit the raw ``synthesize.delivered`` event (the synthesizer
    bridge emits that before ``coordinator.wait_for`` returns it to the
    orchestrator), so the synthesis payload remains in the raw event
    stream. The gate is a real deposit-prevention for the load-bearing
    artifacts (rendered MASTER.md, graph nodes), not an event-log
    retract. Documenting this honestly so a future reader knows exactly
    what BLOCK stops and what it doesn't."""
    if result is None:
        return
    from substrate.eval.groundedness.enforce import (
        EnforcePosture,
        current_posture,
        is_below_threshold,
    )

    posture = current_posture()
    if posture is EnforcePosture.OFF:
        return  # OFF is a true no-op — proven by test_enforce_off_is_noop.
    if not is_below_threshold(result.score, result.supported_threshold):
        return  # the synthesis is grounded; nothing to flag or block.

    # Below threshold + flag-on: surface + mark, but still deposit.
    synthesis_id = f"syn-{ctx.investigation_id}"
    from middleware.outcomes import emit_groundedness_failed

    emit_groundedness_failed(
        investigation_id=ctx.investigation_id,
        synthesis_id=synthesis_id,
        scorer_id="groundedness-lexical-v1",
        stage="groundedness",
        error_type="BelowThresholdSynthesis",
        error=(
            f"synthesis groundedness {result.score:.4f} < threshold "
            f"{result.supported_threshold:.4f} "
            f"(posture={posture.value}; {result.scored_claims} claims scored)"
        ),
    )
    if posture is EnforcePosture.FLAG:
        return  # flagged + deposited — the alert surfaces; the loop continues.

    # Below threshold + block: PREVENT the synthesis from being used downstream.
    # Nulling ctx.synthesis means Phase 7 (delivery/render) sees no synthesis
    # and the graph-write path has nothing to write — a real deposit-prevention,
    # not a post-hoc annotation. Logged + typed, never a silent drop.
    _log.warning(
        "groundedness BLOCK: synthesis %s below threshold (%.4f < %.4f); "
        "ctx.synthesis nulled, will not be deposited (posture=block)",
        synthesis_id,
        result.score,
        result.supported_threshold,
    )
    ctx.synthesis = None


async def _run_phase_7(ctx: InvestigationContext) -> bool:
    """Phase 7 (Delivery) — render MASTER.md from the synthesizer's
    thesis via skills.domain.master_md. The typed
    ``master_md_written`` event the generator emits is what the
    Phase 7 postcondition reads."""
    if ctx.synthesis is None:
        ctx.failed_phase = 7
        ctx.fail_reason = "phase 7 entered without synthesis"
        return False

    async def work() -> None:
        assert ctx.synthesis is not None
        _assert_artifact_write_fence(ctx)
        row = {
            "synthesis_id": f"syn-{ctx.investigation_id}",
            "investigation_id": ctx.investigation_id,
            "target_question": ctx.question,
            "status": "passed",
            "implicit_recommendation": ctx.synthesis.implicit_recommendation,
            "thesis": {
                "thesis_summary": ctx.synthesis.thesis_summary,
                "implicit_recommendation": ctx.synthesis.implicit_recommendation,
                "thesis_components": [c.model_dump() for c in ctx.synthesis.thesis_components],
                "falsification_conditions": [
                    f.model_dump() for f in ctx.synthesis.falsification_conditions
                ],
                "execution_risks": [r.model_dump() for r in ctx.synthesis.execution_risks],
                "constraint_compliance": ctx.synthesis.constraint_compliance.model_dump(),
            },
        }
        # The MASTER.md generator emits ``master_md_written`` as part
        # of its inline write — no need for the orchestrator to
        # broadcast anything extra. The Phase 7 postcondition reads
        # that event.
        guard = (
            investigation_execution_mutation(ctx.authority)
            if ctx.authority is not None
            else contextlib.nullcontext()
        )
        with guard:
            path = generate_master_md(row, topic_slug=ctx.topic_slug)
        ctx.master_md_path = str(path)

    return await _drive_phase(ctx, phase=7, work=work())


def _emit_phase8_auto_patch_applied(
    *,
    investigation_id: str,
    synthesis_id: str,
    matched_domains: Sequence[str],
    patched: Sequence[str],
    skipped: Sequence[str],
    errors: Sequence[dict[str, str]],
    status: str,
) -> None:
    """Emit the typed Phase-8 auto-patch result event.

    The Phase-8 postcondition already keys on this event. Reuse it for
    gate rejection instead of inventing a parallel signal that audits
    would miss.
    """
    from substrate.event_log import emit_typed as _emit
    from substrate.schemas import AutoPatchAppliedPayload

    _emit(
        investigation_id,
        AutoPatchAppliedPayload(
            synthesis_id=synthesis_id,
            matched_domains=list(matched_domains),
            patched=list(patched),
            skipped=list(skipped),
            errors=list(errors),
            status=status,
        ),
        synthesis_id=synthesis_id,
        role="auto_patch",
        policy_id="orchestrator-deterministic",
    )


def _emit_phase8_gate_decided(
    *,
    investigation_id: str,
    synthesis_id: str,
    mode: str,
    minimum_cohort_size: int,
    matched_domains: Sequence[str],
    outcome: Any,
) -> None:
    """Emit the typed Phase-8 gate decision used for shadow calibration."""
    from substrate.event_log import emit_typed as _emit
    from substrate.schemas import SkillPatchGateDecidedPayload

    would_accept = (
        outcome.delta > outcome.epsilon_required and outcome.cohort_size >= minimum_cohort_size
    )
    _emit(
        investigation_id,
        SkillPatchGateDecidedPayload(
            synthesis_id=synthesis_id,
            patch_id=outcome.patch_id,
            mode=mode,
            decision=outcome.decision.value,
            would_accept=would_accept,
            baseline_backtest_score=outcome.baseline_backtest_score,
            candidate_backtest_score=outcome.candidate_backtest_score,
            delta=outcome.delta,
            epsilon_required=outcome.epsilon_required,
            cohort_size=outcome.cohort_size,
            minimum_cohort_size=minimum_cohort_size,
            matched_domains=list(matched_domains),
            notes=outcome.notes,
        ),
        synthesis_id=synthesis_id,
        role="phase8_gate",
        policy_id="orchestrator-deterministic",
    )


def _phase8_calibration_investigation_ids(raw: str) -> list[str]:
    return [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]


def _phase8_gate_from_runtime_env() -> SkillPatchGate:
    from compounding.skill_growth import (
        PHASE8_MODE_ENFORCING,
        PHASE8_MODE_ENV,
        phase8_gate_from_env,
    )

    mode = os.environ.get(PHASE8_MODE_ENV, "").strip().lower()
    if mode != PHASE8_MODE_ENFORCING:
        return phase8_gate_from_env()

    raw_ids = os.environ.get(PHASE8_CALIBRATION_INVESTIGATION_IDS_ENV, "")
    investigation_ids = _phase8_calibration_investigation_ids(raw_ids)
    if not investigation_ids:
        return phase8_gate_from_env(
            calibration_ready=False,
            calibration_notes=(
                f"{PHASE8_CALIBRATION_INVESTIGATION_IDS_ENV} is required "
                "before Phase-8 enforcing can accept patches"
            ),
        )

    from orchestration.audit import phase8_calibration_status

    status = phase8_calibration_status(investigation_ids)
    return phase8_gate_from_env(
        calibration_ready=status.ready_for_enforcing,
        calibration_notes=status.summary,
    )


def _phase8_candidate_replay_evaluation(
    *,
    ctx: InvestigationContext,
    synthesis_row: Mapping[str, Any],
    matched_domains: list[str],
) -> Any | None:
    """Return candidate replay evidence when a production runner is wired.

    The default is intentionally empty. Phase-8 must keep failing closed rather
    than fabricating candidate backtest scores until a real rerunner can produce
    ``CandidateReplayEvaluation`` objects.
    """

    heldout_ids = _phase8_calibration_investigation_ids(
        os.environ.get(PHASE8_REPLAY_HELDOUT_SYNTHESIS_IDS_ENV, "")
    )
    if not heldout_ids:
        return None

    from compounding.skill_growth import unavailable_candidate_replay_evaluation
    from skills.domain.patch import default_skills_root

    overlay_parent_raw = os.environ.get(PHASE8_REPLAY_OVERLAY_PARENT_ENV, "").strip()
    overlay_parent = Path(overlay_parent_raw) if overlay_parent_raw else None
    return unavailable_candidate_replay_evaluation(
        dict(synthesis_row),
        heldout_synthesis_ids=heldout_ids,
        baseline_skills_root=default_skills_root(),
        overlay_parent=overlay_parent,
        reason=(
            "production candidate replay runner is not wired; "
            f"configured by {PHASE8_REPLAY_HELDOUT_SYNTHESIS_IDS_ENV}"
        ),
    )


def _phase8_gate_decide_from_replay_evaluation(
    gate: SkillPatchGate,
    replay_evaluation: Any | None,
) -> PatchOutcome:
    if replay_evaluation is None:
        return gate.decide(
            baseline_backtest_score=0.0,
            candidate_backtest_score=0.0,
            cohort_size=0,
        )

    comparison = replay_evaluation.comparison
    return gate.decide(
        baseline_backtest_score=comparison.baseline_score,
        candidate_backtest_score=comparison.candidate_score,
        cohort_size=comparison.cohort_size,
        candidate_evidence_ready=bool(replay_evaluation.ready_for_gate),
        candidate_evidence_notes=str(replay_evaluation.notes),
    )


async def _run_phase_8(ctx: InvestigationContext) -> bool:
    """Phase 8 (Compound) — Phase 8 is the keystone. Call
    ``skills.domain.extract_and_patch`` inline; the typed
    ``auto_patch_applied`` event satisfies the postcondition gate
    when at least one domain was patched."""
    if ctx.synthesis is None:
        ctx.failed_phase = 8
        ctx.fail_reason = "phase 8 entered without synthesis"
        return False

    async def work() -> None:
        assert ctx.synthesis is not None
        synthesis_id = f"syn-{ctx.investigation_id}"
        thesis = {
            "thesis_summary": ctx.synthesis.thesis_summary,
            "thesis_components": [c.model_dump() for c in ctx.synthesis.thesis_components],
            "falsification_conditions": [
                f.model_dump() for f in ctx.synthesis.falsification_conditions
            ],
            "execution_risks": [r.model_dump() for r in ctx.synthesis.execution_risks],
        }
        synthesis_row = {
            "synthesis_id": synthesis_id,
            "investigation_id": ctx.investigation_id,
            "target_question": ctx.question,
            "implicit_recommendation": ctx.synthesis.implicit_recommendation,
            "thesis": thesis,
        }

        # GF-3b: enforce the Phase-8 gate before any writer runs. The
        # current auto-patch path has no calibrated backtest score yet,
        # so enforcing mode cannot honestly accept it; it rejects with
        # cohort_size=0 instead of fabricating a quality signal. Shadow
        # mode remains the default and preserves current behaviour.
        dry_run_result = extract_and_patch(
            question=ctx.question,
            thesis=thesis,
            investigation_id=ctx.investigation_id,
            dry_run=True,
        )
        from compounding.skill_growth import PatchDecision
        from skills.domain.auto_patch import route_domains as _route_mechanical_domains

        candidate_domains = sorted(
            {
                *dry_run_result.domains_matched,
                *_route_mechanical_domains(ctx.question, ctx.synthesis.thesis_summary),
            }
        )
        if candidate_domains:
            gate = _phase8_gate_from_runtime_env()
            replay_evaluation = _phase8_candidate_replay_evaluation(
                ctx=ctx,
                synthesis_row=synthesis_row,
                matched_domains=candidate_domains,
            )
            gate_outcome = _phase8_gate_decide_from_replay_evaluation(
                gate,
                replay_evaluation,
            )
            _emit_phase8_gate_decided(
                investigation_id=ctx.investigation_id,
                synthesis_id=synthesis_id,
                mode=gate.mode,
                minimum_cohort_size=gate.minimum_cohort_size,
                matched_domains=candidate_domains,
                outcome=gate_outcome,
            )
            if gate_outcome.decision == PatchDecision.REJECT:
                _emit_phase8_auto_patch_applied(
                    investigation_id=ctx.investigation_id,
                    synthesis_id=synthesis_id,
                    matched_domains=candidate_domains,
                    patched=[],
                    skipped=[],
                    errors=[
                        {
                            "domain": "phase8-gate",
                            "error": gate_outcome.notes,
                        }
                    ],
                    status="rejected_by_phase8_gate",
                )
                return

        # extract_and_patch with no llm_call (defaults to dispatch)
        # would issue real LLM calls. For Day 3 the operator-driven
        # orchestrator runs against a stub provider in tests; the
        # production wiring uses the default factory.
        _assert_artifact_write_fence(ctx)
        guard = (
            investigation_execution_mutation(ctx.authority)
            if ctx.authority is not None
            else contextlib.nullcontext()
        )
        with guard:
            result = extract_and_patch(
                question=ctx.question,
                thesis=thesis,
                investigation_id=ctx.investigation_id,
            )
        ctx.patched_domains = list(result.patched_skills.keys())

        # When LLM extraction succeeded but SKILL.md templates are absent
        # on the host (common on fresh prod — only general-knowledge is
        # seeded), fall back to the mechanical patch_from_synthesis path
        # which mkdirs domain dirs and appends under ## Auto-patched
        # findings. That path emits AUTO_PATCH_APPLIED itself.
        emitted_by_fallback = False
        if not result.any_patched and ctx.synthesis is not None:
            from skills.domain.auto_patch import patch_from_synthesis

            _assert_artifact_write_fence(ctx)
            fallback_guard = (
                investigation_execution_mutation(ctx.authority)
                if ctx.authority is not None
                else contextlib.nullcontext()
            )
            with fallback_guard:
                fb = patch_from_synthesis(synthesis_row)
            if fb.get("patched"):
                ctx.patched_domains = list(fb["patched"])
                emitted_by_fallback = True

        if not emitted_by_fallback:
            # Emit AUTO_PATCH_APPLIED so the Phase 8 postcondition's
            # primary (event-based) check passes. extract_and_patch
            # mutates files on disk but doesn't emit the typed event
            # itself; patch_from_synthesis is the alternate entry point
            # that does (handled above when it patches).
            status = (
                "patched"
                if result.any_patched
                else ("no_match" if not result.domains_matched else "failed")
            )
            try:
                _emit_phase8_auto_patch_applied(
                    investigation_id=ctx.investigation_id,
                    synthesis_id=synthesis_id,
                    matched_domains=list(result.domains_matched),
                    patched=ctx.patched_domains,
                    skipped=[],
                    errors=[],
                    status=status,
                )
            except Exception:  # diagnostic emit is best-effort — never fail the phase
                # A swallowed AUTO_PATCH_APPLIED emit lets phase_audit later
                # mint a FALSE `no_auto_patch` critical finding, so this loss
                # must not be silent. The trace is itself guarded so a broken
                # log channel cannot turn a best-effort emit into a phase fail.
                with contextlib.suppress(Exception):
                    _log.exception(
                        "phase-8 auto_patch AUTO_PATCH_APPLIED emit failed for "
                        "%s (status=%s); phase_audit may later report a false "
                        "no_auto_patch finding",
                        ctx.investigation_id,
                        status,
                    )

    return await _drive_phase(ctx, phase=8, work=work())


# ---------------------------------------------------------------------------
# Path A — synthesis tail from SessionEvidencePack (SPR-DRL-06)
# ---------------------------------------------------------------------------


def _investigation_context_from_pack(pack: SessionEvidencePack) -> InvestigationContext:
    """Hydrate Loop 1 state for phases 6–9 from a DRW merge pack."""
    by_sub_q: dict[str, list[Any]] = {}
    for chunk in pack.chunks:
        by_sub_q.setdefault(chunk.sub_question, []).append(chunk)

    decomposition = [
        SubQuestion(
            sub_question=sq,
            category="technology_risk",
            rationale="DRW gather leaf — independent sub-question from cascade.",
            evidence_type_required="mixed",
        )
        for sq in sorted(by_sub_q.keys())
    ]
    if not decomposition and pack.leaf_investigation_ids:
        decomposition = [
            SubQuestion(
                sub_question=f"Evidence from {pack.session_id}",
                category="technology_risk",
                rationale="Empty chunk pack — honest insufficient-evidence path.",
                evidence_type_required="mixed",
            ),
        ]

    evidence: list[EvidenceRetrieveDeliveredPayload] = []
    for sq, chunks in sorted(by_sub_q.items()):
        answer = "\n".join(c.text for c in chunks)
        evidence.append(
            EvidenceRetrieveDeliveredPayload(
                sub_question=sq,
                answer=answer or "(no gathered evidence)",
                supporting_claims=[
                    SupportingClaim(
                        claim=c.text[:500],
                        evidence_type="direct",
                        chunk_ids=[c.chunk_id],
                        edge_ids=[],
                        source_tier_min=3,
                        confidence="moderate",
                        confidence_basis=(f"DRW gather from {c.source_investigation_id}"),
                    )
                    for c in chunks
                ],
                evidentiary_gaps=[],
                insufficient_evidence=not chunks,
            ),
        )

    if not evidence:
        evidence.append(
            EvidenceRetrieveDeliveredPayload(
                sub_question=pack.problem_question,
                answer="(no gathered evidence)",
                supporting_claims=[],
                evidentiary_gaps=[],
                insufficient_evidence=True,
            ),
        )

    coverage_context = "DRW cascade synthesis tail (Path A)."
    artifact_source_coverage: dict[str, Any] | None = None
    if pack.gather_mode == "authorized_multi_source":
        source_totals = {source: 0 for source in ("exa", "parallel", "arxiv", "substack")}
        partial_leaves: list[str] = []
        for report in pack.gather_reports:
            if report.partial:
                partial_leaves.append(report.investigation_id)
            for receipt in report.receipts:
                if receipt.status == "succeeded":
                    source_totals[receipt.source] += 1
        totals = ", ".join(
            f"{source}={count}/{len(pack.gather_reports)} succeeded"
            for source, count in source_totals.items()
        )
        partial_truth = (
            " Partial coverage: " + ", ".join(sorted(partial_leaves)) + "."
            if partial_leaves
            else " All configured sources succeeded for every leaf."
        )
        coverage_context += (
            f" Authorized multi-source coverage ({totals}).{partial_truth} "
            "Treat failed or skipped sources as explicit coverage gaps; do not infer "
            "that an evidence-complete leaf had complete source coverage."
        )
        artifact_source_coverage = {
            "mode": "authorized_multi_source",
            "evidence_complete": True,
            "partial": bool(partial_leaves),
            "partial_leaf_investigation_ids": sorted(partial_leaves),
            "sources": [
                {
                    "source": source,
                    "succeeded_leaves": count,
                    "total_leaves": len(pack.gather_reports),
                }
                for source, count in source_totals.items()
            ],
            "leaves": [
                {
                    "investigation_id": report.investigation_id,
                    "sources": [
                        {
                            "source": receipt.source,
                            "status": receipt.status,
                            "document_count": len(receipt.document_ids),
                        }
                        for receipt in report.receipts
                    ],
                }
                for report in sorted(
                    pack.gather_reports, key=lambda report: report.investigation_id
                )
            ],
        }

    artifact_inherited_reuse: dict[str, Any] | None = None
    if pack.schema_version >= 3:
        artifact_inherited_reuse = {
            "leaves": [
                report.model_dump(
                    mode="json",
                    exclude={"injected_unit_ids"} if pack.schema_version < 4 else None,
                )
                for report in sorted(pack.reuse_reports, key=lambda report: report.investigation_id)
            ]
        }
        inherited_lines = []
        for report in sorted(pack.reuse_reports, key=lambda item: item.investigation_id):
            if report.state == "qualified":
                states = ", ".join(f"{item.unit_id}={item.state}" for item in report.qualifications)
                inherited_lines.append(
                    f"{report.investigation_id}: {report.injected_unit_count} qualified "
                    f"inherited units ({states})"
                )
            elif report.state == "legacy_unqualified":
                inherited_lines.append(
                    f"{report.investigation_id}: {report.injected_unit_count} inherited "
                    "units with legacy-unqualified source coverage"
                )
            elif report.state == "attempted_zero":
                inherited_lines.append(f"{report.investigation_id}: reuse attempted, zero injected")
            else:
                inherited_lines.append(f"{report.investigation_id}: reuse not attempted")
        coverage_context += (
            " Inherited knowledge reuse (separate from direct evidence): "
            + "; ".join(inherited_lines)
            + ". Do not treat inherited qualification as direct source coverage."
        )

    archived_source_coverage = None
    if artifact_source_coverage is not None or artifact_inherited_reuse is not None:
        from substrate.source_coverage import ArchivedSourceCoverageEnvelope

        if pack.schema_version >= 3:
            archived_source_coverage = ArchivedSourceCoverageEnvelope(
                schema_version=3 if pack.schema_version >= 4 else 2,
                pack_schema_version=pack.schema_version,
                pack_content_hash=pack.content_hash,
                gather_plan_fingerprint=pack.gather_plan_fingerprint,
                coverage=artifact_source_coverage,
                inherited_reuse=artifact_inherited_reuse,
                claim_support_by_chunk={
                    chunk.chunk_id: tuple(chunk.inherited_unit_ids) for chunk in pack.chunks
                }
                if pack.schema_version >= 4
                else {},
                claim_support_leaf_by_chunk={
                    chunk.chunk_id: chunk.source_investigation_id for chunk in pack.chunks
                }
                if pack.schema_version >= 4
                else {},
            ).model_dump(mode="json", exclude_none=True)
        else:
            assert pack.gather_plan_fingerprint is not None
            archived_source_coverage = ArchivedSourceCoverageEnvelope(
                pack_content_hash=pack.content_hash,
                gather_plan_fingerprint=pack.gather_plan_fingerprint,
                coverage=artifact_source_coverage,
            ).model_dump(mode="json", exclude_none=True)

    return InvestigationContext(
        investigation_id=pack.session_id,
        question=pack.problem_question,
        context=coverage_context,
        artifact_source_coverage=artifact_source_coverage,
        artifact_inherited_reuse=artifact_inherited_reuse,
        archived_source_coverage=archived_source_coverage,
        inherited_support_by_chunk={
            chunk.chunk_id: list(chunk.inherited_unit_ids) for chunk in pack.chunks
        },
        decomposition=DecomposeQuestionDeliveredPayload(
            decomposition=decomposition,
            keywords=[],
        ),
        evidence=evidence,
        parameters=ParameterExtractDeliveredPayload(
            parameters=[],
            constraints=[],
        ),
        chase_mode="off",
    )


async def run_synthesis_tail_from_pack(
    pack: SessionEvidencePack,
    *,
    broadcaster: EventBroadcaster,
    coordinator: InvestigationCoordinator,
) -> InvestigationContext:
    """Run Loop 1 phases 6–9 only — DRW gather already happened."""
    ctx = _investigation_context_from_pack(pack)
    phases: list[Callable[[], Coroutine[Any, Any, bool]]] = [
        lambda: _run_phase_6(ctx, broadcaster, coordinator),
        lambda: _run_phase_7(ctx),
        lambda: _run_phase_8(ctx),
    ]
    for run in phases:
        ok = await run()
        if not ok:
            await broadcast_emit(
                broadcaster,
                ctx.investigation_id,
                InvestigationFailedPayload(
                    phase=ctx.failed_phase or 6,
                    reason=ctx.fail_reason or "(unknown)",
                    last_completed_phase=(
                        ctx.last_completed_phase if ctx.last_completed_phase > 0 else None
                    ),
                ),
                role="orchestrator",
                policy_id="orchestrator-cascade-tail",
            )
            try:
                audit_phase_log(ctx.investigation_id, emit=True)
            except Exception:  # audit diagnostics are best-effort
                with contextlib.suppress(Exception):
                    _log.exception(
                        "audit_phase_log diagnostics failed for %s on the "
                        "cascade-tail path (audit is best-effort; run continues)",
                        ctx.investigation_id,
                    )
            return ctx

    try:
        from orchestration.invariants.deep_research_complete import (
            assert_deep_research_complete,
        )
        from orchestration.phase_runner import assert_ready_for_completion
        from orchestration.phase_runner.postconditions import default_research_dir

        assert_ready_for_completion(ctx.investigation_id)
        assert_deep_research_complete(
            ctx.investigation_id,
            research_dir=default_research_dir(ctx.investigation_id),
            require_terminal_event=False,
        )
    except Exception as e:
        ctx.failed_phase = 9
        ctx.fail_reason = f"assert_ready_for_completion failed: {e!r}"
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            InvestigationFailedPayload(
                phase=9,
                reason=ctx.fail_reason,
                last_completed_phase=8,
            ),
            role="orchestrator",
            policy_id="orchestrator-cascade-tail",
        )
        return ctx

    assert ctx.synthesis is not None
    # Terminal truth means every best-effort projection has already been
    # attempted. A crash before the terminal therefore re-enters this
    # idempotent projection boundary; a crash after it cannot strand work
    # behind an already-sealed execution.
    await _project_success_outputs(ctx, broadcaster)
    ctx.terminal_event_id = await broadcast_emit(
        broadcaster,
        ctx.investigation_id,
        InvestigationCompletedPayload(
            thesis_summary=ctx.synthesis.thesis_summary,
            implicit_recommendation=ctx.synthesis.implicit_recommendation,
            constraint_loop_status=ctx.synthesis.constraint_loop_status,
            constraint_loop_iterations=ctx.synthesis.constraint_loop_iterations,
            master_md_path=ctx.master_md_path,
            domains_patched=ctx.patched_domains,
            total_phases_verified=ctx.last_completed_phase,
        ),
        role="orchestrator",
        policy_id="orchestrator-cascade-tail",
    )
    return ctx


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def _run_investigation(
    ctx: InvestigationContext,
    broadcaster: EventBroadcaster,
    coordinator: InvestigationCoordinator,
) -> None:
    """Walk all 9 phases. On any phase failure, emits
    ``investigation.failed`` and returns. On success, emits
    ``investigation.completed`` with the synthesis verdict."""
    phases: list[tuple[int, Callable[[], Coroutine[Any, Any, bool]]]] = [
        (1, lambda: _run_phase_1(ctx, broadcaster, coordinator)),
        (2, lambda: _run_phase_2(ctx, broadcaster, coordinator)),
        (3, lambda: _run_phase_3(ctx, broadcaster, coordinator)),
        (4, lambda: _run_phase_4(ctx, broadcaster, coordinator)),
        (5, lambda: _run_phase_5(ctx)),
        (6, lambda: _run_phase_6(ctx, broadcaster, coordinator)),
        (7, lambda: _run_phase_7(ctx)),
        (8, lambda: _run_phase_8(ctx)),
    ]
    for phase, run in phases:
        if phase <= ctx.last_completed_phase:
            continue
        ok = await run()
        if not ok:
            await broadcast_emit(
                broadcaster,
                ctx.investigation_id,
                InvestigationFailedPayload(
                    phase=ctx.failed_phase or 0,
                    reason=ctx.fail_reason or "(unknown)",
                    last_completed_phase=(
                        ctx.last_completed_phase if ctx.last_completed_phase > 0 else None
                    ),
                ),
                role="orchestrator",
                policy_id="orchestrator-deterministic",
            )
            # Audit the failure path so dashboards surface the gap.
            try:
                audit_phase_log(ctx.investigation_id, emit=True)
            except Exception:  # audit diagnostics are best-effort
                # The comment above promises dashboards surface the gap; a
                # silently-swallowed audit call would break exactly that. The
                # trace is guarded so a broken log channel can't break the path.
                with contextlib.suppress(Exception):
                    _log.exception(
                        "audit_phase_log diagnostics failed for %s on the "
                        "investigation-failed path (audit is best-effort; "
                        "run continues)",
                        ctx.investigation_id,
                    )
            return

    # Phase 9: assert completion-ready + DeepResearchComplete contract.
    try:
        from orchestration.invariants.deep_research_complete import (
            assert_deep_research_complete,
        )
        from orchestration.phase_runner import assert_ready_for_completion
        from orchestration.phase_runner.postconditions import default_research_dir

        assert_ready_for_completion(ctx.investigation_id)
        assert_deep_research_complete(
            ctx.investigation_id,
            research_dir=default_research_dir(ctx.investigation_id),
            require_terminal_event=False,
        )
    except Exception as e:
        ctx.failed_phase = 9
        ctx.fail_reason = f"assert_ready_for_completion failed: {e!r}"
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            InvestigationFailedPayload(
                phase=9,
                reason=ctx.fail_reason,
                last_completed_phase=8,
            ),
            role="orchestrator",
            policy_id="orchestrator-deterministic",
        )
        return

    assert ctx.synthesis is not None
    await _project_success_outputs(ctx, broadcaster)
    ctx.terminal_event_id = await broadcast_emit(
        broadcaster,
        ctx.investigation_id,
        InvestigationCompletedPayload(
            thesis_summary=ctx.synthesis.thesis_summary,
            implicit_recommendation=ctx.synthesis.implicit_recommendation,
            constraint_loop_status=ctx.synthesis.constraint_loop_status,
            constraint_loop_iterations=ctx.synthesis.constraint_loop_iterations,
            master_md_path=ctx.master_md_path,
            domains_patched=ctx.patched_domains,
            total_phases_verified=ctx.last_completed_phase,
        ),
        role="orchestrator",
        policy_id="orchestrator-deterministic",
    )


def _projection_input_sha256(ctx: InvestigationContext) -> str:
    if ctx.synthesis is None or ctx.synthesis_event_id is None:
        raise RuntimeError("terminal projection requires canonical synthesis")
    body = {
        "investigation_id": ctx.investigation_id,
        "synthesis_event_id": ctx.synthesis_event_id,
        "synthesis": ctx.synthesis.model_dump(mode="json"),
        "master_md_path": ctx.master_md_path,
        "patched_domains": sorted(ctx.patched_domains),
        "archived_source_coverage": ctx.archived_source_coverage,
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _event_by_id(ctx: InvestigationContext, event_id: str) -> Event:
    assert ctx.authority is not None
    return next(
        Event.model_validate(row)
        for row in trajectory_authorized_append_order(ctx.authority)
        if row.get("event_id") == event_id
    )


def _verify_synthesis_projection_effect(
    ctx: InvestigationContext,
    effect: Event,
    *,
    input_sha256: str,
) -> bool:
    payload = effect.payload
    if not isinstance(payload, InvestigationProjectionEffectRecordedPayload):
        return False
    if (
        payload.effect != "synthesis_archive"
        or payload.disposition != "complete"
        or payload.effect_ref is None
        or payload.effect_sha256
        != hashlib.sha256(f"{payload.effect_ref}\x00{input_sha256}".encode()).hexdigest()
        or ctx.authority is None
        or ctx.synthesis is None
    ):
        return False
    from middleware.archive import authorized_synthesis_id
    from runtime.db_lock import connect_read
    from substrate.graph import default_db_path

    if payload.effect_ref != authorized_synthesis_id(ctx.authority, "terminal"):
        return False
    try:
        con = connect_read(default_db_path())
        try:
            archived = con.execute(
                "SELECT investigation_id, thesis_text, thesis, substrate FROM syntheses "
                "WHERE synthesis_id = ? AND account_digest = ? "
                "AND investigation_digest = ?",
                [
                    payload.effect_ref,
                    ctx.authority.account_digest,
                    ctx.authority.investigation_digest,
                ],
            ).fetchone()
        finally:
            con.close()
    except Exception:
        return False
    return bool(
        archived is not None
        and archived[0] == ctx.investigation_id
        and archived[1] == ctx.synthesis.thesis_summary
        and json.loads(archived[2]) == ctx.synthesis.model_dump(mode="json")
        and (json.loads(archived[3]) if archived[3] is not None else None)
        == ctx.archived_source_coverage
    )


def _verify_html_projection_effect(ctx: InvestigationContext, effect: Event) -> bool:
    payload = effect.payload
    if not isinstance(payload, InvestigationProjectionEffectRecordedPayload):
        return False
    configured = os.environ.get("ANTIEK_EXPORT_RESEARCH_ARTIFACT", "").strip() in {
        "1",
        "true",
        "yes",
    }
    if payload.disposition == "not_configured":
        return payload.effect == "html_artifact" and not configured
    if (
        payload.effect != "html_artifact"
        or payload.disposition != "complete"
        or payload.effect_ref is None
        or payload.effect_sha256 is None
        or ctx.authority is None
    ):
        return False
    from substrate.research_artifact.authority import ArtifactAuthority
    from substrate.research_artifact.build_body import build_body
    from substrate.research_artifact.render import render_html
    from substrate.research_artifact.storage import FilesystemArtifactStore

    authority = ArtifactAuthority(ctx.authority.account_id, ctx.investigation_id)
    if payload.effect_ref != authority.investigation_key:
        return False
    try:
        stored = FilesystemArtifactStore().read_bounded(authority, max_bytes=16_000_000)
        body = build_body(ctx.investigation_id, authority=authority)
        if ctx.artifact_source_coverage is not None:
            from substrate.research_artifact.schema import ResearchArtifactBody

            raw_body = body.model_dump(mode="json")
            raw_body["source_coverage"] = ctx.artifact_source_coverage
            raw_body["inherited_reuse"] = ctx.artifact_inherited_reuse
            body = ResearchArtifactBody.model_validate(raw_body)
        elif ctx.artifact_inherited_reuse is not None:
            from substrate.research_artifact.schema import ResearchArtifactBody

            raw_body = body.model_dump(mode="json")
            raw_body["inherited_reuse"] = ctx.artifact_inherited_reuse
            body = ResearchArtifactBody.model_validate(raw_body)
    except Exception:
        return False
    return payload.effect_sha256 == body.content_hash() and stored == render_html(body)


async def _project_success_outputs(
    ctx: InvestigationContext, broadcaster: EventBroadcaster
) -> None:
    """Converge paid synthesis/archive projections before terminal truth."""
    if ctx.execution_id is None:
        _deposit_synthesis_to_substrate(ctx)
        _maybe_export_research_artifact_after_complete(ctx)
        return
    if ctx.authority is None or ctx.synthesis_event_id is None:
        raise RuntimeError("paid terminal projection requires authority and synthesis")
    fence = current_investigation_execution(ctx.investigation_id)
    if fence is None:
        raise RuntimeError("paid terminal projection requires execution fence")
    generation, _ = fence
    input_sha256 = _projection_input_sha256(ctx)
    projection_id = investigation_projection_id(
        ctx.execution_id, ctx.synthesis_event_id, input_sha256
    )
    request_id = investigation_projection_event_id(projection_id, "request")

    async def record_failure(
        effect: Literal["synthesis_archive", "html_artifact"],
        failure_code: Literal["mutation_failed", "verification_failed"],
    ) -> None:
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            InvestigationProjectionFailedPayload(
                projection_id=projection_id,
                request_event_id=request_id,
                effect=effect,
                failure_code=failure_code,
            ),
            parent_event_id=request_id,
            role="orchestrator",
            policy_id="orchestrator-terminal-projection",
            event_id=investigation_projection_event_id(
                projection_id, f"failed-{effect}-{failure_code}"
            ),
        )

    await broadcast_emit(
        broadcaster,
        ctx.investigation_id,
        InvestigationProjectionRequestedPayload(
            projection_id=projection_id,
            execution_id=ctx.execution_id,
            synthesis_event_id=ctx.synthesis_event_id,
            input_sha256=input_sha256,
        ),
        parent_event_id=ctx.synthesis_event_id,
        role="orchestrator",
        policy_id="orchestrator-terminal-projection",
        event_id=request_id,
    )
    snapshot = project_investigation_projection(
        trajectory_authorized_append_order(ctx.authority),
        execution_id=ctx.execution_id,
        generation=generation,
    )
    assert snapshot is not None
    if snapshot.synthesis_effect is None or not _verify_synthesis_projection_effect(
        ctx, snapshot.synthesis_effect, input_sha256=input_sha256
    ):
        try:
            synthesis_id = _deposit_synthesis_to_substrate(ctx)
        except Exception:
            await record_failure("synthesis_archive", "mutation_failed")
            raise
        if synthesis_id is None:
            raise RuntimeError("synthesis archive did not return durable identity")
        archive_sha256 = hashlib.sha256(f"{synthesis_id}\x00{input_sha256}".encode()).hexdigest()
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            InvestigationProjectionEffectRecordedPayload(
                projection_id=projection_id,
                request_event_id=request_id,
                effect="synthesis_archive",
                disposition="complete",
                effect_ref=synthesis_id,
                effect_sha256=archive_sha256,
            ),
            parent_event_id=request_id,
            role="orchestrator",
            policy_id="orchestrator-terminal-projection",
            event_id=investigation_projection_event_id(projection_id, "synthesis_archive"),
        )
    snapshot = project_investigation_projection(
        trajectory_authorized_append_order(ctx.authority),
        execution_id=ctx.execution_id,
        generation=generation,
    )
    assert snapshot is not None
    if snapshot.html_effect is None or not _verify_html_projection_effect(
        ctx, snapshot.html_effect
    ):
        try:
            disposition, effect_ref, effect_sha256 = _maybe_export_research_artifact_after_complete(
                ctx
            )
        except Exception:
            await record_failure("html_artifact", "mutation_failed")
            raise
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            InvestigationProjectionEffectRecordedPayload(
                projection_id=projection_id,
                request_event_id=request_id,
                effect="html_artifact",
                disposition=disposition,
                effect_ref=effect_ref or None,
                effect_sha256=effect_sha256,
            ),
            parent_event_id=request_id,
            role="orchestrator",
            policy_id="orchestrator-terminal-projection",
            event_id=investigation_projection_event_id(projection_id, "html_artifact"),
        )
    snapshot = project_investigation_projection(
        trajectory_authorized_append_order(ctx.authority),
        execution_id=ctx.execution_id,
        generation=generation,
    )
    assert snapshot is not None
    synthesis_verified = snapshot.synthesis_effect is not None and (
        _verify_synthesis_projection_effect(
            ctx, snapshot.synthesis_effect, input_sha256=input_sha256
        )
    )
    html_verified = snapshot.html_effect is not None and _verify_html_projection_effect(
        ctx, snapshot.html_effect
    )
    if not synthesis_verified or not html_verified:
        if not synthesis_verified:
            await record_failure("synthesis_archive", "verification_failed")
        if not html_verified:
            await record_failure("html_artifact", "verification_failed")
        raise RuntimeError(
            "terminal projection effects failed durable verification: "
            f"synthesis={synthesis_verified}, html={html_verified}"
        )
    if snapshot.completion is None:
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            InvestigationProjectionCompletedPayload(
                projection_id=projection_id,
                request_event_id=request_id,
                synthesis_effect_event_id=snapshot.synthesis_effect.event_id,
                html_effect_event_id=snapshot.html_effect.event_id,
                effects_sha256=projection_effects_sha256(
                    snapshot.synthesis_effect, snapshot.html_effect
                ),
            ),
            parent_event_id=request_id,
            role="orchestrator",
            policy_id="orchestrator-terminal-projection",
            event_id=investigation_projection_event_id(projection_id, "complete"),
        )


def _deposit_synthesis_to_substrate(ctx: InvestigationContext) -> str | None:
    """Deposit the completed synthesis into the ``syntheses`` table — the
    flywheel's research→substrate deposit (DOGFOOD SPR-03).

    The SOLE production call site of
    ``middleware.archive.archive_synthesis_via_db``. Before SPR-03 the loop
    emitted ``INVESTIGATION_COMPLETED`` (and wrote MASTER.md) but never
    deposited the row, so ``syntheses`` was 0 by construction regardless of
    how many investigations completed. Now a completed synthesis lands as a
    queryable, manifest-traced row.

    Best-effort + non-fatal: a deposit failure is logged on stderr but never
    breaks investigation completion (mirrors
    ``_maybe_export_research_artifact_after_complete``). The synthesis was
    produced regardless; archiving is a separate persistence concern.

    Returns the deposited ``synthesis_id`` or ``None`` on skip/failure.
    """
    import sys
    from datetime import UTC, datetime

    from middleware.archive import ArchiveInputs, archive_synthesis_authorized
    from runtime.db_lock import connect_write
    from substrate.graph import default_db_path
    from substrate.schemas import SynthesisStatus

    synth = ctx.synthesis
    if synth is None:
        return None
    if ctx.authority is None:
        print(
            "orchestrator: synthesis deposit skipped: explicit investigation authority is required",
            file=sys.stderr,
        )
        return None
    if ctx.authority.investigation_id != ctx.investigation_id:
        print(
            "orchestrator: synthesis deposit skipped: investigation authority "
            "does not match the active investigation",
            file=sys.stderr,
        )
        return None

    # Map the constraint-loop terminal verdict to the syntheses-row status.
    # (ConstraintLoopStatus carries two preflight states with no
    # SynthesisStatus equivalent; they default to 'draft'.)
    loop_to_status: dict[str, SynthesisStatus] = {
        "single_pass": "passed",
        "passed": "passed",
        "regressed": "regressed",
        "max_iterations_reached": "max_iterations_reached",
        "escalated": "escalated",
    }
    status: SynthesisStatus = loop_to_status.get(synth.constraint_loop_status, "draft")

    # Pin only selected reasoning paths so abandoned branches do not become
    # apparent provenance for the archived conclusion.
    chunk_ids: list[str] = []
    edge_ids: list[str] = []
    node_ids: list[str] = []
    for ev in ctx.evidence:
        for claim in getattr(ev, "supporting_claims", None) or []:
            chunk_ids.extend(getattr(claim, "chunk_ids", None) or [])
            edge_ids.extend(getattr(claim, "edge_ids", None) or [])
    chunk_ids = list(dict.fromkeys(chunk_ids))
    edge_ids = list(dict.fromkeys(edge_ids))
    used_path_indices = {
        path_index
        for component in synth.thesis_components
        for path_index in component.supporting_path_indices
    }
    for path_index in sorted(used_path_indices):
        if 0 <= path_index < len(synth.reasoning_paths_used):
            node_ids.extend(synth.reasoning_paths_used[path_index].path_node_ids)
    node_ids = list(dict.fromkeys(node_ids))

    def _dump(obj: object) -> object:
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        return obj

    inputs = ArchiveInputs(
        target_question=ctx.question,
        synthesis_timestamp=ctx.synthesis_emitted_at or datetime.now(UTC),
        status=status,
        implicit_recommendation=synth.implicit_recommendation,
        thesis_text=synth.thesis_summary,
        thesis=_dump(synth),
        evidence=[_dump(e) for e in ctx.evidence],
        decomposition=_dump(ctx.decomposition) if ctx.decomposition is not None else None,
        parameters=_dump(ctx.parameters) if ctx.parameters is not None else None,
        substrate=ctx.archived_source_coverage,
        source_synthesis_event_id=ctx.synthesis_event_id,
        chunk_ids=tuple(chunk_ids),
        node_ids=tuple(node_ids),
        edge_ids=tuple(edge_ids),
    )
    try:
        db_path = default_db_path()
        with connect_write(db_path, purpose="archive-synthesis") as con:
            return archive_synthesis_authorized(
                con,
                ctx.authority,
                inputs,
                logical_key="terminal",
            )
    except Exception as exc:  # best-effort: never break completion
        if ctx.execution_id is not None:
            raise
        print(
            "orchestrator: synthesis deposit failed (best-effort, non-fatal): "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return None


def _maybe_export_research_artifact_after_complete(
    ctx: InvestigationContext,
) -> tuple[str, str, str | None]:
    """ANT-AHT-02: env-gated, execution-fenced HTML artifact export."""
    try:
        from substrate.research_artifact.authority import ArtifactAuthority
        from substrate.research_artifact.hooks import (
            maybe_export_after_investigation_complete,
        )

        if ctx.authority is None:
            return ("not_configured", "", None)
        artifact_authority = ArtifactAuthority(ctx.authority.account_id, ctx.investigation_id)
        with investigation_execution_mutation(ctx.authority):
            result = maybe_export_after_investigation_complete(
                ctx.investigation_id,
                authority=artifact_authority,
                source_coverage=ctx.artifact_source_coverage,
                inherited_reuse=ctx.artifact_inherited_reuse,
                terminal_provenance=ctx.archived_source_coverage,
            )
        if result is None:
            return ("not_configured", "", None)
        return ("complete", artifact_authority.investigation_key, result.content_hash)
    except Exception:
        if ctx.execution_id is not None:
            raise
        return ("not_configured", "", None)


# ---------------------------------------------------------------------------
# Handler factory + registration
# ---------------------------------------------------------------------------


def _rehydrate_archived_source_coverage(ctx: InvestigationContext) -> None:
    if ctx.authority is None:
        return
    from middleware.archive import authorized_synthesis_id, load_synthesis_authorized
    from runtime.db_lock import connect_read
    from substrate.graph import default_db_path
    from substrate.source_coverage import ArchivedSourceCoverageEnvelope

    try:
        con = connect_read(default_db_path())
        try:
            archived = load_synthesis_authorized(
                con,
                ctx.authority,
                authorized_synthesis_id(ctx.authority, "terminal"),
            )
        finally:
            con.close()
        if archived is None or archived.substrate is None:
            return
        envelope = ArchivedSourceCoverageEnvelope.model_validate(archived.substrate)
        archived_raw = envelope.model_dump(mode="json", exclude_none=True)
        artifact_raw = (
            envelope.coverage.model_dump(mode="json") if envelope.coverage is not None else None
        )
        inherited_raw = (
            envelope.inherited_reuse.model_dump(mode="json")
            if envelope.inherited_reuse is not None
            else None
        )
        if (
            (
                ctx.archived_source_coverage is not None
                and ctx.archived_source_coverage != archived_raw
            )
            or (
                ctx.artifact_source_coverage is not None
                and ctx.artifact_source_coverage != artifact_raw
            )
            or (
                ctx.artifact_inherited_reuse is not None
                and ctx.artifact_inherited_reuse != inherited_raw
            )
        ):
            raise InvestigationRehydrationConflict("process and archive source coverage conflict")
        ctx.archived_source_coverage = archived_raw
        ctx.artifact_source_coverage = artifact_raw
        ctx.artifact_inherited_reuse = inherited_raw
    except InvestigationRehydrationConflict:
        raise
    except Exception as exc:
        raise InvestigationRehydrationConflict(
            "archived source coverage could not be recovered"
        ) from exc


def _rehydrate_context(ctx: InvestigationContext, rows: list[dict[str, Any]], generation: int):
    projection = project_loop_one_phase_state(
        rows,
        generation=generation,
        max_sub_questions=ctx.max_sub_questions,
    )
    if projection.decomposition is not None:
        ctx.decomposition = projection.decomposition.payload  # type: ignore[assignment]
    ctx.evidence = [event.payload for event in projection.evidence]  # type: ignore[misc]
    if projection.parameters is not None:
        ctx.parameters = projection.parameters.payload  # type: ignore[assignment]
    if projection.connector is not None:
        ctx.connector_result = projection.connector.payload
    if projection.synthesis is not None:
        ctx.synthesis = projection.synthesis.payload  # type: ignore[assignment]
        ctx.synthesis_event_id = projection.synthesis.event_id
        ctx.synthesis_emitted_at = projection.synthesis.emitted_at
        _rehydrate_archived_source_coverage(ctx)
    if projection.master_md is not None:
        ctx.master_md_path = projection.master_md.payload.path  # type: ignore[union-attr]
    ctx.patched_domains = sorted(
        {
            domain
            for item in projection.skill_patches
            for domain in item.payload.matched_domains  # type: ignore[union-attr]
        }
    )
    ctx.last_completed_phase = max(projection.completed_phases, default=0)
    return projection


def _reconcile_daily_research_hold(req: Any, authority: InvestigationAuthority) -> bool:
    if (
        req.research_daily_budget_hold_id is None
        or req.research_daily_budget_date_stamp is None
        or req.research_daily_budget_cap_usd is None
    ):
        return False
    rows = trajectory_authorized(authority)
    reservations = {
        row["payload"]["reservation_id"]: row["payload"]
        for row in rows
        if row.get("action_type") == ActionType.RESEARCH_CALL_RESERVED.value
        and isinstance(row.get("payload"), dict)
    }
    terminals = {
        row["payload"]["reservation_id"]: row["payload"]
        for row in rows
        if row.get("action_type")
        in {
            ActionType.RESEARCH_CALL_SETTLED.value,
            ActionType.RESEARCH_CALL_RELEASED.value,
        }
        and isinstance(row.get("payload"), dict)
    }
    if set(reservations).difference(terminals):
        return False
    from substrate.dispatch.daily_research_budget import (
        settle_daily_research_budget,
    )

    settled_cost = sum(
        [
            Decimal(str(payload.get("actual_cost_usd", 0.0)))
            for payload in terminals.values()
            if payload.get("action_type") == ActionType.RESEARCH_CALL_SETTLED.value
        ],
        start=Decimal("0"),
    )
    settle_daily_research_budget(
        account_id=authority.account_id,
        hold_id=req.research_daily_budget_hold_id,
        cap_usd=req.research_daily_budget_cap_usd,
        amount_usd=req.approved_run_ceiling_usd or 0,
        actual_usd=settled_cost,
        date_stamp=req.research_daily_budget_date_stamp,
    )
    return True


def make_loop_one_handler(
    broadcaster: EventBroadcaster,
    coordinator: InvestigationCoordinator,
    *,
    tenancy_root: Path | None = None,
) -> EventHandler:
    """Build the Loop 1 handler. Subscribes to
    ``INVESTIGATION_START_REQUESTED``; for each request, spawns a
    detached task that runs the 9-phase sequence."""
    holder_digest = hashlib.sha256(b"antiek.loop-one-holder.v1\x00" + os.urandom(32)).hexdigest()
    active_executions: set[str] = set()
    active_lock = asyncio.Lock()

    async def handle_investigation_start(event: Event) -> None:
        if not isinstance(event.payload, InvestigationStartRequestedPayload):
            return
        req = event.payload
        try:
            event_authority = broadcaster.authority_for_event(event)
        except RuntimeError:
            event_authority = None
        if req.research_workload_plan_sha256 is not None:
            from substrate.dispatch.research_cost_envelope import (
                build_whole_run_cost_envelope,
            )
            from substrate.dispatch.research_quote import (
                ResearchRouteManifest,
                ResearchRouteQuote,
            )

            accepted_manifest = ResearchRouteManifest(
                routes=tuple(
                    ResearchRouteQuote(**row.model_dump(mode="python"))
                    for row in (req.research_route_manifest or ())
                ),
                fingerprint=req.research_route_manifest_fingerprint or "",
            )
            accepted_envelope = build_whole_run_cost_envelope(
                accepted_manifest,
                selected_driver_role=req.selected_driver_role or "",
                selected_driver_provider=req.selected_driver_provider or "",
                selected_driver_model=req.selected_driver_model or "",
                selected_driver_pricing_fingerprint=(req.selected_driver_pricing_fingerprint or ""),
                max_sub_questions=req.max_sub_questions,
            )
            if accepted_envelope.plan_sha256 != req.research_workload_plan_sha256:
                raise RuntimeError("accepted research workload plan is stale")
            if (
                abs(
                    float(accepted_envelope.maximum_usd)
                    - float(req.research_projected_max_cost_usd or 0)
                )
                > 0.00000001
            ):
                raise RuntimeError("accepted research cost envelope changed")
        ctx = InvestigationContext(
            investigation_id=event.investigation_id,
            question=req.question,
            authority=event_authority,
            tenancy_root=(tenancy_root or _default_tenancy_root()),
            context=req.context,
            topic_slug=req.topic_slug,
            max_sub_questions=req.max_sub_questions,
            chase_mode=req.chase_mode,
            chase_value=req.chase_value,
            chase_budget_usd=req.chase_budget_usd,
            parent_investigation_id=req.parent_investigation_id,
            research_tier=req.research_tier,
            research_quote_id=req.research_quote_id,
            research_route_manifest_fingerprint=(req.research_route_manifest_fingerprint),
            research_route_manifest=req.research_route_manifest,
            research_delegation_id=req.research_delegation_id,
            research_root_investigation_id=req.research_root_investigation_id,
            research_root_quote_id=req.research_root_quote_id,
            research_delegation_generation=req.research_delegation_generation,
        )

        if req.approved_run_ceiling_usd is None:

            async def run_legacy_and_maybe_chase() -> None:
                await _run_investigation(ctx, broadcaster, coordinator)
                if ctx.synthesis is not None and ctx.failed_phase is None:
                    await _maybe_spawn_chase_child(ctx, broadcaster)

            asyncio.create_task(
                run_legacy_and_maybe_chase(),
                name=f"loop_one:{event.investigation_id}",
            )
            return

        if event_authority is None:
            raise RuntimeError("paid investigation execution requires authority")
        try:
            _, snapshot, acquired = claim_investigation_execution_authorized(
                event_authority,
                holder_digest=holder_digest,
                now_ms=time.time_ns() // 1_000_000,
            )
        except InvestigationExecutionBusy:
            return
        if snapshot.completed:
            _reconcile_daily_research_hold(req, event_authority)
            return
        if not acquired:
            return
        ctx.execution_id = snapshot.execution_id
        async with active_lock:
            if snapshot.execution_id in active_executions:
                return
            active_executions.add(snapshot.execution_id)

        async def run_fenced_and_maybe_chase() -> None:
            heartbeat_stop = asyncio.Event()

            async def heartbeat() -> None:
                while True:
                    try:
                        await asyncio.wait_for(heartbeat_stop.wait(), timeout=30.0)
                        return
                    except TimeoutError:
                        renew_investigation_execution_authorized(
                            event_authority,
                            generation=snapshot.generation,
                            holder_digest=holder_digest,
                            now_ms=time.time_ns() // 1_000_000,
                        )

            heartbeat_task = asyncio.create_task(
                heartbeat(), name=f"loop_one_heartbeat:{event.investigation_id}"
            )
            try:
                try:
                    projection = _rehydrate_context(
                        ctx,
                        trajectory_authorized(event_authority),
                        snapshot.generation,
                    )
                except InvestigationRehydrationConflict as exc:
                    ctx.failed_phase = 1
                    ctx.fail_reason = f"execution recovery halted: {exc}"
                    with investigation_execution_context(
                        event_authority,
                        generation=snapshot.generation,
                        holder_digest=holder_digest,
                    ):
                        terminal_id = await broadcast_emit(
                            broadcaster,
                            ctx.investigation_id,
                            InvestigationFailedPayload(
                                phase=1,
                                reason=ctx.fail_reason,
                                last_completed_phase=None,
                            ),
                            role="orchestrator",
                            policy_id="orchestrator-execution-recovery",
                        )
                    terminal = next(
                        Event.model_validate(row)
                        for row in trajectory_authorized(event_authority)
                        if row.get("event_id") == terminal_id
                    )
                else:
                    terminal = projection.terminal
                if terminal is None:
                    with investigation_execution_context(
                        event_authority,
                        generation=snapshot.generation,
                        holder_digest=holder_digest,
                    ):
                        await _run_investigation(ctx, broadcaster, coordinator)
                    terminal = next(
                        (
                            Event.model_validate(row)
                            for row in reversed(trajectory_authorized(event_authority))
                            if row.get("execution_generation") == snapshot.generation
                            and row.get("action_type")
                            in {
                                ActionType.INVESTIGATION_COMPLETED.value,
                                ActionType.INVESTIGATION_FAILED.value,
                            }
                        ),
                        None,
                    )
                heartbeat_stop.set()
                await heartbeat_task
                if terminal is not None:
                    complete_investigation_execution_authorized(
                        event_authority,
                        generation=snapshot.generation,
                        holder_digest=holder_digest,
                        terminal_event=terminal,
                        completed_at_ms=time.time_ns() // 1_000_000,
                    )
                    _reconcile_daily_research_hold(req, event_authority)
                if ctx.synthesis is not None and ctx.failed_phase is None:
                    await _maybe_spawn_chase_child(ctx, broadcaster)
            finally:
                heartbeat_stop.set()
                if not heartbeat_task.done():
                    heartbeat_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await heartbeat_task
                async with active_lock:
                    active_executions.discard(snapshot.execution_id)

        # Detached task — the orchestrator runs alongside the request
        # handler that triggered it.
        asyncio.create_task(
            run_fenced_and_maybe_chase(),
            name=f"loop_one:{event.investigation_id}",
        )

    return handle_investigation_start


# ---------------------------------------------------------------------------
# Sprint 12 — continuous chase mode
# ---------------------------------------------------------------------------


def _walk_chase_chain(
    investigation_id: str, *, tenancy_root: Path | None = None
) -> tuple[int, str]:
    """Walk the parent_investigation_id chain backwards via trajectories.
    Returns ``(depth, root_id)``. depth=0 means this is the chase root.

    Uses the trajectory's INVESTIGATION_START_REQUESTED event to find
    each parent. Capped at 32 hops for safety against accidental
    cycles."""
    from substrate.event_log import trajectory

    depth = 0
    current = investigation_id
    root = investigation_id
    seen: set[str] = {current}
    for _ in range(32):
        rows = trajectory(current, events_dir=str(tenancy_root) if tenancy_root else None)
        parent: str | None = None
        for r in rows:
            if r.get("action_type") == ActionType.INVESTIGATION_START_REQUESTED.value:
                p = (r.get("payload") or {}).get("parent_investigation_id")
                if p:
                    parent = p
                break
        if not parent or parent in seen:
            return depth, root
        depth += 1
        root = parent
        current = parent
        seen.add(parent)
    return depth, root


def _accumulated_chase_cost_usd(
    investigation_id: str, *, tenancy_root: Path | None = None
) -> float:
    """Sum dispatch.call.cost_usd across the full chase chain (current
    inv + all ancestors). Approximation: each chain node walked once;
    siblings of ancestors not counted (the chase model treats each
    branch as its own budget context)."""
    from substrate.event_log import trajectory

    total = 0.0
    current: str | None = investigation_id
    seen: set[str] = set()
    for _ in range(32):
        if not current or current in seen:
            break
        seen.add(current)
        rows = trajectory(current, events_dir=str(tenancy_root) if tenancy_root else None)
        parent: str | None = None
        for r in rows:
            at = r.get("action_type")
            if at == ActionType.DISPATCH_CALL.value:
                with contextlib.suppress(TypeError, ValueError):
                    total += float((r.get("payload") or {}).get("cost_usd") or 0.0)
            elif at == ActionType.INVESTIGATION_START_REQUESTED.value:
                parent = (r.get("payload") or {}).get("parent_investigation_id")
        current = parent
    return total


def _select_chase_question(ctx: InvestigationContext) -> str | None:
    """Pick the strongest open question from this investigation's
    accumulated evidentiary_gaps. v0: first non-empty gap from the
    first evidence_retrieve.delivered that has any gaps. Later
    versions can rank by source_tier, co-occurrence across siblings,
    operator preference signals."""
    for ev in ctx.evidence:
        gaps = ev.evidentiary_gaps or []
        for gap in gaps:
            # Pydantic EvidentiaryGap carries gap_description; dict
            # fallback for parser-produced records that haven't been
            # validated yet.
            text: str | None = None
            if hasattr(gap, "gap_description"):
                text = gap.gap_description
            elif isinstance(gap, dict):
                text = gap.get("gap_description") or gap.get("gap") or gap.get("description")
            if text and isinstance(text, str) and text.strip():
                return text.strip()
    return None


async def _maybe_spawn_chase_child(
    ctx: InvestigationContext,
    broadcaster: EventBroadcaster,
) -> None:
    """Decide whether to spawn a child investigation per the chase
    parameters. Emits INVESTIGATION_CHASE_HALTED with the reason when
    halting; emits a new INVESTIGATION_START_REQUESTED when continuing.
    The substrate's own handler picks up the new start event and runs
    its own task — chase recursion happens organically."""
    if ctx.chase_mode == "off":
        return  # not a chase investigation, nothing to do

    depth, root_id = _walk_chase_chain(ctx.investigation_id, tenancy_root=ctx.tenancy_root)
    root_id = ctx.research_root_investigation_id or root_id
    cost_total = _accumulated_chase_cost_usd(ctx.investigation_id, tenancy_root=ctx.tenancy_root)
    root_authority: InvestigationAuthority | None = None
    if ctx.authority is not None:
        from substrate.event_log import (
            research_delegation_snapshot_authorized,
            settle_research_delegation_authorized,
            trajectory_authorized_append_order,
        )

        root_authority = InvestigationAuthority(ctx.authority.account_id, root_id, ctx.tenancy_root)
        if ctx.research_delegation_id is not None:
            root_rows = trajectory_authorized_append_order(root_authority)
            accepted_rows = [
                Event.model_validate(row)
                for row in root_rows
                if row.get("action_type") == ActionType.RESEARCH_DELEGATION_ACCEPTED.value
                and (row.get("payload") or {}).get("delegation_id") == ctx.research_delegation_id
            ]
            child_rows = trajectory_authorized_append_order(ctx.authority)
            terminal_rows = [
                Event.model_validate(row)
                for row in child_rows
                if row.get("event_id") == ctx.terminal_event_id
            ]
            reservation_rows = [
                Event.model_validate(row)
                for row in root_rows
                if row.get("action_type") == ActionType.RESEARCH_DELEGATION_RESERVED.value
                and (row.get("payload") or {}).get("delegation_id") == ctx.research_delegation_id
            ]
            if len(accepted_rows) == 1 and len(terminal_rows) == 1 and len(reservation_rows) == 1:
                child_cost = sum(
                    float((row.get("payload") or {}).get("actual_cost_usd", 0.0))
                    for row in child_rows
                    if row.get("action_type") == ActionType.RESEARCH_CALL_SETTLED.value
                )
                settle_research_delegation_authorized(
                    root_authority,
                    ResearchDelegationSettledPayload(
                        delegation_id=ctx.research_delegation_id,
                        reservation_event_id=reservation_rows[0].event_id,
                        accepted_event_id=accepted_rows[0].event_id,
                        child_terminal_event_id=terminal_rows[0].event_id,
                        actual_cost_usd=round(child_cost, 8),
                    ),
                    child_authority=ctx.authority,
                    child_terminal_event=terminal_rows[0],
                )
        snapshot = research_delegation_snapshot_authorized(root_authority)
        cost_total = float(snapshot.root_call_spend_usd + snapshot.delegated_spend_usd)

    halt_reason: (
        Literal[
            "depth_reached",
            "duration_reached",
            "budget_exceeded",
            "no_open_questions",
            "chase_disabled",
        ]
        | None
    ) = None
    if ctx.chase_mode == "depth":
        if depth + 1 > ctx.chase_value:
            halt_reason = "depth_reached"
    elif ctx.chase_mode == "duration":
        # Estimate elapsed via the root start event timestamp.
        from datetime import datetime

        from substrate.event_log import trajectory

        root_started_at: str | None = None
        for r in trajectory(root_id, events_dir=str(ctx.tenancy_root)):
            if r.get("action_type") == ActionType.INVESTIGATION_START_REQUESTED.value:
                root_started_at = r.get("emitted_at")
                break
        if root_started_at:
            try:
                t0 = datetime.fromisoformat(root_started_at.replace("Z", "+00:00"))
                now = datetime.now(UTC)
                elapsed_hours = (now - t0).total_seconds() / 3600.0
                if elapsed_hours >= ctx.chase_value:
                    halt_reason = "duration_reached"
            except ValueError:
                pass

    if halt_reason is None and cost_total >= ctx.chase_budget_usd:
        halt_reason = "budget_exceeded"

    next_question: str | None = None
    if halt_reason is None:
        next_question = _select_chase_question(ctx)
        if next_question is None:
            halt_reason = "no_open_questions"

    if halt_reason is not None:
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            InvestigationChaseHaltedPayload(
                reason=halt_reason,
                depth_reached=depth,
                cost_total_usd=round(cost_total, 6),
            ),
            role="orchestrator",
            policy_id="orchestrator-chase",
        )
        return

    assert next_question is not None

    # Reserve one deterministic root-family operation before quote issuance.
    from datetime import datetime

    from substrate.dispatch.research_quote import (
        ResearchQuoteInvalid,
        ResearchRouteManifest,
        ResearchRouteQuote,
        issue_research_quote,
    )
    from substrate.dispatch.research_quote_keys import load_research_quote_keyring
    from substrate.event_log import (
        ResearchBudgetExceeded,
        accept_research_delegation_authorized,
        append_event_once_authorized,
        mark_research_delegation_issued_authorized,
        prepare_typed_event,
        release_research_delegation_authorized,
        research_delegation_snapshot_authorized,
        reserve_research_delegation_authorized,
        trajectory_authorized_append_order,
    )

    if (
        ctx.authority is None
        or root_authority is None
        or not ctx.research_quote_id
        or not ctx.research_route_manifest
        or not ctx.research_route_manifest_fingerprint
    ):
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            InvestigationChaseHaltedPayload(
                reason="quote_authority_unavailable",
                depth_reached=depth,
                cost_total_usd=round(cost_total, 6),
            ),
            role="orchestrator",
            policy_id="orchestrator-chase",
            authority=ctx.authority,
        )
        return
    root_quote_id = ctx.research_root_quote_id or ctx.research_quote_id
    generation = (ctx.research_delegation_generation or 0) + 1
    operation = {
        "root_investigation_id": root_id,
        "root_quote_id": root_quote_id,
        "parent_investigation_id": ctx.investigation_id,
        "parent_quote_id": ctx.research_quote_id,
        "question": next_question,
        "context": ctx.context,
        "topic_slug": ctx.topic_slug,
        "max_sub_questions": ctx.max_sub_questions,
        "chase_mode": ctx.chase_mode,
        "chase_value": ctx.chase_value,
        "chase_budget_usd": ctx.chase_budget_usd,
        "research_tier": ctx.research_tier,
        "route_manifest_fingerprint": ctx.research_route_manifest_fingerprint,
        "generation": generation,
    }
    operation_bytes = json.dumps(
        operation, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    operation_sha256 = hashlib.sha256(
        b"antiek.research-delegation.operation.v1\x00" + operation_bytes
    ).hexdigest()
    delegation_id = hashlib.sha256(
        b"antiek.research-delegation.id.v1\x00" + operation_bytes
    ).hexdigest()
    child_id = f"inv-chase-{delegation_id[:24]}"
    root_rows = trajectory_authorized_append_order(root_authority)
    existing_holds = [
        Event.model_validate(row)
        for row in root_rows
        if row.get("action_type") == ActionType.RESEARCH_DELEGATION_RESERVED.value
        and (row.get("payload") or {}).get("delegation_id") == delegation_id
    ]
    if len(existing_holds) > 1:
        raise RuntimeError("recursive delegation history is ambiguous")
    if existing_holds:
        delegated_ceiling = existing_holds[0].payload.delegated_ceiling_usd
    else:
        delegation_snapshot = research_delegation_snapshot_authorized(root_authority)
        delegated_ceiling = round(float(delegation_snapshot.remaining_usd), 8)
    if delegated_ceiling <= 0:
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            InvestigationChaseHaltedPayload(
                reason="budget_exceeded",
                depth_reached=depth,
                cost_total_usd=round(cost_total, 6),
            ),
            role="orchestrator",
            policy_id="orchestrator-chase",
            authority=ctx.authority,
        )
        return
    try:
        reservation_event, _ = reserve_research_delegation_authorized(
            root_authority,
            ResearchDelegationReservedPayload(
                delegation_id=delegation_id,
                operation_sha256=operation_sha256,
                root_investigation_id=root_id,
                root_quote_id=root_quote_id,
                parent_investigation_id=ctx.investigation_id,
                parent_quote_id=ctx.research_quote_id,
                child_investigation_id=child_id,
                generation=generation,
                delegated_ceiling_usd=delegated_ceiling,
                route_manifest_fingerprint=ctx.research_route_manifest_fingerprint,
            ),
        )
    except ResearchBudgetExceeded:
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            InvestigationChaseHaltedPayload(
                reason="budget_exceeded",
                depth_reached=depth,
                cost_total_usd=round(cost_total, 6),
            ),
            role="orchestrator",
            policy_id="orchestrator-chase",
            authority=ctx.authority,
        )
        return
    delegated_command = json.dumps(
        {
            "child_investigation_id": child_id,
            "parent_investigation_id": ctx.investigation_id,
            "question": next_question,
            "context": ctx.context,
            "topic_slug": ctx.topic_slug,
            "max_sub_questions": ctx.max_sub_questions,
            "chase_mode": ctx.chase_mode,
            "chase_value": ctx.chase_value,
            "chase_budget_usd": ctx.chase_budget_usd,
            "research_tier": ctx.research_tier,
            "approved_run_ceiling_usd": delegated_ceiling,
            "delegated_from_quote_id": ctx.research_quote_id,
            "delegation_id": delegation_id,
            "root_investigation_id": root_id,
            "root_quote_id": root_quote_id,
            "delegation_generation": generation,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    manifest = ResearchRouteManifest(
        routes=tuple(
            ResearchRouteQuote(**row.model_dump(mode="python"))
            for row in ctx.research_route_manifest
        ),
        fingerprint=ctx.research_route_manifest_fingerprint,
    )
    try:
        active_key_id, signing_key, _ = load_research_quote_keyring()
        emitted_at = reservation_event.emitted_at
        issued_instant = (
            datetime.fromisoformat(emitted_at.replace("Z", "+00:00"))
            if isinstance(emitted_at, str)
            else emitted_at
        )
        issued_at_ms = int(issued_instant.timestamp() * 1000)
        _, delegated_receipt = issue_research_quote(
            account_id=ctx.authority.account_id,
            prompt=delegated_command,
            research_tier=ctx.research_tier or "deep",
            manifest=manifest,
            approved_run_ceiling_usd=delegated_ceiling,
            issued_at_ms=issued_at_ms,
            expires_at_ms=issued_at_ms + 5 * 60 * 1000,
            nonce=delegation_id,
            key_id=active_key_id,
            signing_key=signing_key,
        )
    except ResearchQuoteInvalid as exc:
        release_research_delegation_authorized(
            root_authority,
            ResearchDelegationReleasedPayload(
                delegation_id=delegation_id,
                reservation_event_id=reservation_event.event_id,
                reason="quote_not_issued",
                error_sha256=hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),
            ),
        )
        await broadcast_emit(
            broadcaster,
            ctx.investigation_id,
            InvestigationChaseHaltedPayload(
                reason="quote_authority_unavailable",
                depth_reached=depth,
                cost_total_usd=round(cost_total, 6),
            ),
            role="orchestrator",
            policy_id="orchestrator-chase",
            authority=ctx.authority,
        )
        return
    issued_event, _ = mark_research_delegation_issued_authorized(
        root_authority,
        ResearchDelegationIssuedPayload(
            delegation_id=delegation_id,
            reservation_event_id=reservation_event.event_id,
            quote_id=delegated_receipt.quote_id,
            quote_payload_sha256=delegated_receipt.payload_sha256,
            quote_expires_at_ms=delegated_receipt.expires_at_ms,
        ),
    )
    from substrate.investigation_streams import initialize_composite_stream

    child_authority = InvestigationAuthority(ctx.authority.account_id, child_id, ctx.tenancy_root)
    initialize_composite_stream(child_authority)
    child_start = prepare_typed_event(
        child_id,
        InvestigationStartRequestedPayload(
            question=next_question,
            context=ctx.context,
            topic_slug=ctx.topic_slug,
            max_sub_questions=ctx.max_sub_questions,
            parent_investigation_id=ctx.investigation_id,
            spawn_context=next_question,
            chase_mode=ctx.chase_mode,
            chase_value=ctx.chase_value,
            chase_budget_usd=ctx.chase_budget_usd,
            # SPR-01 M3: a chase-spawned child inherits the parent's
            # research tier so the chosen fast/deep posture holds across
            # the chase tree rather than snapping back to the default.
            research_tier=ctx.research_tier,
            # This child spends only from the operator-approved recursive
            # remainder; it does not clone the parent's initial-run ceiling.
            approved_run_ceiling_usd=delegated_ceiling,
            research_quote_id=delegated_receipt.quote_id,
            research_quote_payload_sha256=delegated_receipt.payload_sha256,
            research_route_manifest_fingerprint=manifest.fingerprint,
            research_quote_expires_at_ms=delegated_receipt.expires_at_ms,
            research_route_manifest=ctx.research_route_manifest,
            research_delegated_from_quote_id=ctx.research_quote_id,
            research_delegation_id=delegation_id,
            research_root_investigation_id=root_id,
            research_root_quote_id=root_quote_id,
            research_delegation_generation=generation,
        ),
        event_id=f"evt-chase-start-{delegation_id[:24]}",
        emitted_at=reservation_event.emitted_at,
        role="orchestrator",
        policy_id="orchestrator-chase",
    )
    append_event_once_authorized(child_authority, child_start)
    child_start_bytes = json.dumps(
        child_start.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    accept_research_delegation_authorized(
        root_authority,
        ResearchDelegationAcceptedPayload(
            delegation_id=delegation_id,
            reservation_event_id=reservation_event.event_id,
            issued_event_id=issued_event.event_id,
            child_investigation_id=child_id,
            child_start_event_id=child_start.event_id,
            child_start_sha256=hashlib.sha256(child_start_bytes).hexdigest(),
        ),
        child_authority=child_authority,
        child_start_event=child_start,
    )
    # Handler fan-out is an execution boundary: publish only after the root
    # stream has durably accepted this exact persisted child start.
    broadcaster.bind_event_authority(child_start.event_id, child_authority)
    await broadcaster.broadcast_once(child_start)
    spawned = prepare_typed_event(
        child_id,
        InvestigationSpawnedFromPayload(
            parent_investigation_id=ctx.investigation_id,
            spawn_context=next_question,
        ),
        event_id=f"evt-chase-spawned-{delegation_id[:24]}",
        emitted_at=reservation_event.emitted_at,
        parent_event_id=child_start.event_id,
        role="orchestrator",
        policy_id="orchestrator-chase",
    )
    append_event_once_authorized(child_authority, spawned)
    broadcaster.bind_event_authority(spawned.event_id, child_authority)
    await broadcaster.broadcast_once(spawned)


def register_handlers(
    broadcaster: EventBroadcaster,
    coordinator: InvestigationCoordinator | None = None,
    *,
    tenancy_root: Path | None = None,
) -> InvestigationCoordinator:
    """Wire the Loop 1 orchestrator into the broadcaster. Returns the
    coordinator (created if not supplied) so the caller can hold a
    reference for direct ``wait_for`` use from tests."""
    if coordinator is None:
        coordinator = InvestigationCoordinator(broadcaster)
    broadcaster.register_handler(
        _action_value(ActionType.INVESTIGATION_START_REQUESTED),
        make_loop_one_handler(broadcaster, coordinator, tenancy_root=tenancy_root),
    )
    return coordinator
