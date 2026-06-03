"""Gap-finder + cascaded prompt generation (SPR-05)."""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

try:
    from ...runtime.db_lock import LockedConnection
    from ..graph.ops import new_random_id
    from .extractor import (
        EXTRACTOR_VERSION,
        LlmCallable,
        LlmCallResult,
        _extract_json_object,
    )
    from .source_detection import KNOWN_SOURCES
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    from substrate.graph.ops import new_random_id  # type: ignore[no-redef]
    from substrate.research_bridge.extractor import (  # type: ignore[no-redef]
        EXTRACTOR_VERSION,
        LlmCallable,
        LlmCallResult,
        _extract_json_object,
    )
    from substrate.research_bridge.source_detection import KNOWN_SOURCES  # type: ignore[no-redef]


CLUSTER_VERSION: int = 1
CASCADE_VERSION: int = 1

_CLUSTER_PROMPT_FILE = os.path.join(
    os.path.dirname(__file__), "prompts", f"cluster_v{CLUSTER_VERSION}.md"
)
_CASCADE_PROMPT_FILE = os.path.join(
    os.path.dirname(__file__), "prompts", f"cascade_v{CASCADE_VERSION}.md"
)

MAX_CLUSTERS: int = 7
MAX_PROMPTS_PER_CLUSTER: int = 3
MAX_PROMPTS_PER_RUN: int = MAX_CLUSTERS * MAX_PROMPTS_PER_CLUSTER * 2


@dataclass(frozen=True)
class GapPrompt:
    cluster_id: str
    order_index: int
    prompt_text: str
    target_provider: str
    expected_output_shape: str | None
    depends_on_prior_order_index: int | None
    rationale: str | None


@dataclass(frozen=True)
class GapCluster:
    cluster_id: str
    label: str
    rationale: str | None
    priority_rank: int
    question_ids: tuple[str, ...]


@dataclass(frozen=True)
class GapRunResult:
    run_id: str
    clusters: tuple[GapCluster, ...]
    prompts: tuple[GapPrompt, ...]
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    grounding_drops: int


class GapFinderError(RuntimeError):
    pass


# --- prompt rendering ---


def _load_cluster_prompt() -> str:
    with open(_CLUSTER_PROMPT_FILE, encoding="utf-8") as f:
        return f.read()


def _load_cascade_prompt() -> str:
    with open(_CASCADE_PROMPT_FILE, encoding="utf-8") as f:
        return f.read()


def _render_cluster_input(questions: list[dict]) -> str:
    lines = [f"Open questions ({len(questions)}):", ""]
    for q in questions:
        lines.append(q["question_id"])
        lines.append(f"  summary: {q['summary']}")
        lines.append(f"  from_paste: {q['document_id']}")
        lines.append("")
    return "\n".join(lines)


def _render_cascade_input(
    clusters: list[GapCluster],
    cluster_questions: dict[str, list[dict]],
    insights_excerpt: list[dict],
) -> str:
    lines = [f"Clusters ({len(clusters)}):", ""]
    for c in clusters:
        lines.append(f"cluster_id: {c.cluster_id}")
        lines.append(f"  label: {c.label}")
        lines.append(f"  priority_rank: {c.priority_rank}")
        if c.rationale:
            lines.append(f"  rationale: {c.rationale}")
        lines.append("  questions:")
        for q in cluster_questions.get(c.cluster_id, []):
            lines.append(f"    - [{q['question_id']}] {q['summary']}")
        lines.append("")
    lines.append("Source insights (for grounding):")
    for ins in insights_excerpt[:20]:
        lines.append(f"  - {ins['summary']}")
    return "\n".join(lines)


# --- validation ---

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")


def _terms_of_art(s: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(s)}


def _grounding_check(prompt_text: str, source_corpus: str) -> bool:
    p = _terms_of_art(prompt_text)
    s = _terms_of_art(source_corpus)
    generic = {"please", "analyze", "explain", "describe", "summarize",
               "summarise", "research", "report", "context", "provide",
               "discuss", "consider", "factor", "factors", "questions",
               "question", "answer", "output"}
    p -= generic
    s -= generic
    return bool(p & s)


def _parse_cluster_response(
    text: str,
    valid_question_ids: set[str],
    run_id: str,  # unused; kept for future audit
) -> list[GapCluster]:
    _ = run_id
    obj = _extract_json_object(text)
    raw_clusters = obj.get("clusters") or []
    out: list[GapCluster] = []
    used_ranks: set[int] = set()
    for raw in raw_clusters[: MAX_CLUSTERS * 4]:
        if len(out) >= MAX_CLUSTERS:
            break
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or "").strip()
        if not label:
            continue
        try:
            rank = int(raw.get("priority_rank", -1))
        except (TypeError, ValueError):
            continue
        if rank < 0 or rank in used_ranks:
            continue
        used_ranks.add(rank)
        raw_qids = raw.get("question_ids") or []
        qids = tuple(
            str(q) for q in raw_qids
            if isinstance(q, str) and q in valid_question_ids
        )
        if not qids:
            continue
        rationale = raw.get("rationale")
        rationale_str = str(rationale).strip() if rationale else None
        out.append(GapCluster(
            cluster_id=new_random_id("rgcl"),
            label=label[:300],
            rationale=rationale_str[:1000] if rationale_str else None,
            priority_rank=rank,
            question_ids=qids,
        ))
    out.sort(key=lambda c: c.priority_rank)
    return [
        GapCluster(
            cluster_id=c.cluster_id, label=c.label, rationale=c.rationale,
            priority_rank=i, question_ids=c.question_ids,
        )
        for i, c in enumerate(out)
    ]


def _parse_cascade_response(
    text: str,
    clusters: list[GapCluster],
    cluster_corpus: dict[str, str],
) -> tuple[list[GapPrompt], int]:
    obj = _extract_json_object(text)
    raw_prompts = obj.get("prompts") or []
    by_cluster_id = {c.cluster_id: c for c in clusters}
    kept: list[GapPrompt] = []
    grounding_drops = 0
    for raw in raw_prompts[: MAX_PROMPTS_PER_RUN * 2]:
        if len(kept) >= MAX_PROMPTS_PER_RUN:
            break
        if not isinstance(raw, dict):
            continue
        cluster_id = str(raw.get("cluster_id") or "")
        if cluster_id not in by_cluster_id:
            continue
        prompt_text = str(raw.get("prompt_text") or "").strip()
        if not prompt_text:
            continue
        provider = str(raw.get("target_provider") or "").strip().lower()
        if provider not in KNOWN_SOURCES:
            continue
        if not _grounding_check(prompt_text, cluster_corpus[cluster_id]):
            grounding_drops += 1
            continue
        depends = raw.get("depends_on_prior_order_index")
        try:
            depends_int = int(depends) if depends is not None else None
        except (TypeError, ValueError):
            depends_int = None
        rationale = raw.get("rationale")
        expected = raw.get("expected_output_shape")
        try:
            order = int(raw.get("order_index", len(kept)))
        except (TypeError, ValueError):
            order = len(kept)
        kept.append(GapPrompt(
            cluster_id=cluster_id, order_index=order,
            prompt_text=prompt_text[:8000], target_provider=provider,
            expected_output_shape=(str(expected)[:500] if expected else None),
            depends_on_prior_order_index=depends_int,
            rationale=str(rationale)[:1000] if rationale else None,
        ))
    kept.sort(key=lambda p: p.order_index)
    return (
        [
            GapPrompt(
                cluster_id=p.cluster_id, order_index=i,
                prompt_text=p.prompt_text, target_provider=p.target_provider,
                expected_output_shape=p.expected_output_shape,
                depends_on_prior_order_index=p.depends_on_prior_order_index,
                rationale=p.rationale,
            )
            for i, p in enumerate(kept)
        ],
        grounding_drops,
    )


# --- DB I/O (private; single writer in this file) ---


def _collect_scope_questions(
    con: LockedConnection, document_ids: Sequence[str],
) -> tuple[list[dict], list[dict]]:
    if not document_ids:
        return [], []
    questions: list[dict] = []
    insights: list[dict] = []
    placeholders = ", ".join("?" for _ in document_ids)
    q_rows = con.execute(
        f"""
        SELECT q.question_id, q.summary, q.document_id
        FROM research_paste_open_questions q
        WHERE q.document_id IN ({placeholders})
          AND q.extractor_version = ?
        ORDER BY q.extracted_at DESC
        """,
        list(document_ids) + [int(EXTRACTOR_VERSION)],
    ).fetchall()
    for r in q_rows:
        questions.append({
            "question_id": r[0], "summary": r[1], "document_id": r[2],
        })
    i_rows = con.execute(
        f"""
        SELECT i.insight_id, i.summary, i.document_id
        FROM research_paste_insights i
        WHERE i.document_id IN ({placeholders})
          AND i.extractor_version = ?
        ORDER BY i.extracted_at DESC
        LIMIT 200
        """,
        list(document_ids) + [int(EXTRACTOR_VERSION)],
    ).fetchall()
    for r in i_rows:
        insights.append({
            "insight_id": r[0], "summary": r[1], "document_id": r[2],
        })
    return questions, insights


def _insert_run(
    con: LockedConnection,
    *,
    run_id: str,
    operator_label: str | None,
    session_id: str | None,
    scope_block_ids: Sequence[str],
    scope_question_ids: Sequence[str],
    cluster_model_id: str,
    total_input_tokens: int,
    total_output_tokens: int,
    total_cost_usd: float,
) -> None:
    con.execute(
        "INSERT INTO research_gap_runs "
        "(run_id, operator_label, session_id, scope_block_ids, "
        " scope_question_ids, cluster_model_id, total_input_tokens, "
        " total_output_tokens, total_cost_usd) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            run_id, operator_label, session_id,
            json.dumps(list(scope_block_ids)),
            json.dumps(list(scope_question_ids)),
            cluster_model_id,
            int(total_input_tokens), int(total_output_tokens),
            float(total_cost_usd),
        ],
    )


def _insert_cluster(con: LockedConnection, cluster: GapCluster, run_id: str) -> None:
    con.execute(
        "INSERT INTO research_gap_clusters "
        "(cluster_id, run_id, label, priority_rank, rationale) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            cluster.cluster_id, run_id, cluster.label,
            int(cluster.priority_rank), cluster.rationale,
        ],
    )


def _insert_cluster_question(
    con: LockedConnection, cluster_id: str, question_id: str, order_index: int
) -> None:
    con.execute(
        "INSERT INTO research_gap_cluster_questions "
        "(cluster_id, question_id, order_index) "
        "VALUES (?, ?, ?)",
        [cluster_id, question_id, int(order_index)],
    )


def _insert_prompt(
    con: LockedConnection,
    *,
    prompt_id: str,
    run_id: str,
    prompt: GapPrompt,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    con.execute(
        "INSERT INTO research_gap_prompts "
        "(prompt_id, run_id, cluster_id, order_index, prompt_text, "
        " target_provider, expected_output_shape, "
        " depends_on_prior_order_index, rationale, "
        " input_tokens, output_tokens, cost_usd) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            prompt_id, run_id, prompt.cluster_id, int(prompt.order_index),
            prompt.prompt_text, prompt.target_provider,
            prompt.expected_output_shape,
            prompt.depends_on_prior_order_index,
            prompt.rationale,
            int(input_tokens), int(output_tokens), float(cost_usd),
        ],
    )


# --- public API ---


def find_gaps(
    con: LockedConnection,
    *,
    scope_block_ids: Sequence[str],
    llm_callable: LlmCallable,
    operator_label: str | None = None,
    session_id: str | None = None,
) -> GapRunResult:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            "find_gaps requires a LockedConnection (got "
            f"{type(con).__name__}). Use runtime.db_lock.connect_write."
        )
    if not scope_block_ids:
        raise ValueError("scope_block_ids must be non-empty")

    questions, insights = _collect_scope_questions(con, scope_block_ids)
    if not questions:
        run_id = new_random_id("rgrun")
        _insert_run(
            con,
            run_id=run_id, operator_label=operator_label,
            session_id=session_id,
            scope_block_ids=scope_block_ids,
            scope_question_ids=[],
            cluster_model_id="empty",
            total_input_tokens=0, total_output_tokens=0, total_cost_usd=0.0,
        )
        return GapRunResult(
            run_id=run_id, clusters=(), prompts=(),
            total_input_tokens=0, total_output_tokens=0,
            total_cost_usd=0.0, grounding_drops=0,
        )

    valid_qids = {q["question_id"] for q in questions}

    cluster_prompt = _load_cluster_prompt() + "\n\n" + _render_cluster_input(questions)
    try:
        cluster_call = llm_callable(cluster_prompt)
    except Exception as e:
        raise GapFinderError(
            f"cluster LLM call failed: {type(e).__name__}: {e}"
        ) from e

    clusters = _parse_cluster_response(cluster_call.text, valid_qids, run_id="pending")

    by_qid = {q["question_id"]: q for q in questions}
    cluster_questions = {
        c.cluster_id: [by_qid[qid] for qid in c.question_ids if qid in by_qid]
        for c in clusters
    }
    cluster_corpus = {
        c.cluster_id: "\n".join(
            [c.label] + [by_qid[qid]["summary"] for qid in c.question_ids if qid in by_qid]
        )
        for c in clusters
    }

    grounding_drops = 0
    prompts: list[GapPrompt] = []
    cascade_in = LlmCallResult(text="", model_id="unknown")
    if clusters:
        cascade_prompt = (
            _load_cascade_prompt()
            + "\n\n"
            + _render_cascade_input(clusters, cluster_questions, insights)
        )
        try:
            cascade_in = llm_callable(cascade_prompt)
        except Exception as e:
            raise GapFinderError(
                f"cascade LLM call failed: {type(e).__name__}: {e}"
            ) from e
        prompts, grounding_drops = _parse_cascade_response(
            cascade_in.text, clusters, cluster_corpus,
        )

    run_id = new_random_id("rgrun")
    total_in = int(cluster_call.input_tokens) + int(cascade_in.input_tokens)
    total_out = int(cluster_call.output_tokens) + int(cascade_in.output_tokens)
    total_cost = float(cluster_call.cost_usd) + float(cascade_in.cost_usd)

    _insert_run(
        con,
        run_id=run_id, operator_label=operator_label,
        session_id=session_id,
        scope_block_ids=scope_block_ids,
        scope_question_ids=list(valid_qids),
        cluster_model_id=cluster_call.model_id,
        total_input_tokens=total_in, total_output_tokens=total_out,
        total_cost_usd=total_cost,
    )
    for cluster in clusters:
        _insert_cluster(con, cluster, run_id)
        for idx, qid in enumerate(cluster.question_ids):
            _insert_cluster_question(con, cluster.cluster_id, qid, idx)
    per_prompt_in = (cascade_in.input_tokens // max(len(prompts), 1)) if prompts else 0
    per_prompt_out = (cascade_in.output_tokens // max(len(prompts), 1)) if prompts else 0
    per_prompt_cost = (cascade_in.cost_usd / max(len(prompts), 1)) if prompts else 0.0
    for prompt in prompts:
        _insert_prompt(
            con,
            prompt_id=new_random_id("rgpr"), run_id=run_id, prompt=prompt,
            input_tokens=per_prompt_in, output_tokens=per_prompt_out,
            cost_usd=per_prompt_cost,
        )

    return GapRunResult(
        run_id=run_id,
        clusters=tuple(clusters),
        prompts=tuple(prompts),
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_cost_usd=total_cost,
        grounding_drops=grounding_drops,
    )


# --- signals + answers ---


def record_prompt_signal(
    con: LockedConnection, *, prompt_id: str, signal_type: str,
) -> str:
    if not isinstance(con, LockedConnection):
        raise TypeError("record_prompt_signal requires a LockedConnection")
    if signal_type not in ("would_run", "skip"):
        raise ValueError(
            f"signal_type must be 'would_run' or 'skip', got {signal_type!r}"
        )
    sid = new_random_id("rgs")
    con.execute(
        "INSERT INTO research_gap_prompt_signals "
        "(signal_id, prompt_id, signal_type) VALUES (?, ?, ?)",
        [sid, prompt_id, signal_type],
    )
    return sid


def record_prompt_answer(
    con: LockedConnection, *, prompt_id: str, answer_document_id: str,
) -> str:
    if not isinstance(con, LockedConnection):
        raise TypeError("record_prompt_answer requires a LockedConnection")
    aid = new_random_id("rga")
    con.execute(
        "INSERT INTO research_gap_prompt_answers "
        "(answer_id, prompt_id, answer_document_id) VALUES (?, ?, ?)",
        [aid, prompt_id, answer_document_id],
    )
    return aid


# --- read-side ---


@dataclass(frozen=True)
class StoredCluster:
    cluster_id: str
    run_id: str
    label: str
    priority_rank: int
    rationale: str | None


@dataclass(frozen=True)
class StoredPrompt:
    prompt_id: str
    run_id: str
    cluster_id: str | None
    order_index: int
    prompt_text: str
    target_provider: str
    expected_output_shape: str | None
    depends_on_prior_order_index: int | None
    rationale: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    operator_label: str | None
    session_id: str | None
    scope_block_ids: tuple[str, ...]
    scope_question_ids: tuple[str, ...]
    cluster_model_id: str
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    created_at: str


def list_gap_runs(con, *, limit: int = 20, session_id: str | None = None) -> list[StoredRun]:
    if session_id is None:
        rows = con.execute(
            "SELECT run_id, operator_label, session_id, scope_block_ids, "
            "       scope_question_ids, cluster_model_id, total_input_tokens, "
            "       total_output_tokens, total_cost_usd, created_at "
            "FROM research_gap_runs ORDER BY created_at DESC LIMIT ?",
            [int(limit)],
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT run_id, operator_label, session_id, scope_block_ids, "
            "       scope_question_ids, cluster_model_id, total_input_tokens, "
            "       total_output_tokens, total_cost_usd, created_at "
            "FROM research_gap_runs WHERE session_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            [session_id, int(limit)],
        ).fetchall()
    out: list[StoredRun] = []
    for r in rows:
        out.append(StoredRun(
            run_id=r[0], operator_label=r[1], session_id=r[2],
            scope_block_ids=tuple(json.loads(r[3]) if r[3] else []),
            scope_question_ids=tuple(json.loads(r[4]) if r[4] else []),
            cluster_model_id=r[5],
            total_input_tokens=int(r[6]),
            total_output_tokens=int(r[7]),
            total_cost_usd=float(r[8]),
            created_at=str(r[9]),
        ))
    return out


def read_gap_run(
    con, run_id: str,
) -> tuple[StoredRun | None, list[StoredCluster], list[StoredPrompt]]:
    run_row = con.execute(
        "SELECT run_id, operator_label, session_id, scope_block_ids, "
        "       scope_question_ids, cluster_model_id, total_input_tokens, "
        "       total_output_tokens, total_cost_usd, created_at "
        "FROM research_gap_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    if run_row is None:
        return None, [], []
    run = StoredRun(
        run_id=run_row[0], operator_label=run_row[1], session_id=run_row[2],
        scope_block_ids=tuple(json.loads(run_row[3]) if run_row[3] else []),
        scope_question_ids=tuple(json.loads(run_row[4]) if run_row[4] else []),
        cluster_model_id=run_row[5],
        total_input_tokens=int(run_row[6]),
        total_output_tokens=int(run_row[7]),
        total_cost_usd=float(run_row[8]),
        created_at=str(run_row[9]),
    )
    c_rows = con.execute(
        "SELECT cluster_id, run_id, label, priority_rank, rationale "
        "FROM research_gap_clusters WHERE run_id = ? "
        "ORDER BY priority_rank",
        [run_id],
    ).fetchall()
    clusters = [
        StoredCluster(
            cluster_id=r[0], run_id=r[1], label=r[2],
            priority_rank=int(r[3]), rationale=r[4],
        )
        for r in c_rows
    ]
    p_rows = con.execute(
        "SELECT prompt_id, run_id, cluster_id, order_index, prompt_text, "
        "       target_provider, expected_output_shape, "
        "       depends_on_prior_order_index, rationale, "
        "       input_tokens, output_tokens, cost_usd "
        "FROM research_gap_prompts WHERE run_id = ? "
        "ORDER BY order_index",
        [run_id],
    ).fetchall()
    prompts = [
        StoredPrompt(
            prompt_id=r[0], run_id=r[1], cluster_id=r[2],
            order_index=int(r[3]), prompt_text=r[4],
            target_provider=r[5], expected_output_shape=r[6],
            depends_on_prior_order_index=(int(r[7]) if r[7] is not None else None),
            rationale=r[8],
            input_tokens=int(r[9]), output_tokens=int(r[10]),
            cost_usd=float(r[11]),
        )
        for r in p_rows
    ]
    return run, clusters, prompts


def would_run_percentage(con, *, run_id: str | None = None) -> tuple[int, int, float]:
    base_filter = ""
    params: list[Any] = []
    if run_id is not None:
        base_filter = "AND p.run_id = ?"
        params.append(run_id)
    rows = con.execute(
        f"""
        SELECT s.signal_type, COUNT(*) AS n
        FROM research_gap_prompt_signals s
        JOIN research_gap_prompts p ON p.prompt_id = s.prompt_id
        JOIN (
            SELECT prompt_id, MAX(occurred_at) AS latest
            FROM research_gap_prompt_signals
            GROUP BY prompt_id
        ) latest ON latest.prompt_id = s.prompt_id
                AND latest.latest = s.occurred_at
        WHERE 1=1 {base_filter}
        GROUP BY s.signal_type
        """,
        params,
    ).fetchall()
    counts = {r[0]: int(r[1]) for r in rows}
    would = counts.get("would_run", 0)
    skip = counts.get("skip", 0)
    total = would + skip
    pct = (would / total) if total > 0 else 0.0
    return would, total, pct
