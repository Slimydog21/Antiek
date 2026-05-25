"""Insight + open-question extractor.

``extract_paste(con, document_id, llm_callable=...)`` is the entry
point. It reads the paste, looks up (raw_sha256, extractor_version)
cache, otherwise calls the injected LLM, validates verbatim quotes,
inserts surviving rows, promotes each insight to a graph node, and
writes one row to research_paste_extractions.

The LLM is injected as ``LlmCallable`` so tests don't burn API
credits; production wires ``substrate/research_bridge/llm_dispatch.py``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional

try:
    from ...runtime.db_lock import LockedConnection
    from ..constants import SYSTEM_INVESTIGATION_ID
    from ..graph.ops import content_addressed_id, insert_node, new_random_id
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    from substrate.constants import SYSTEM_INVESTIGATION_ID  # type: ignore[no-redef]
    from substrate.graph.ops import (  # type: ignore[no-redef]
        content_addressed_id, insert_node, new_random_id,
    )


EXTRACTOR_VERSION: int = 1
_PROMPT_FILE = os.path.join(
    os.path.dirname(__file__), "prompts", f"extractor_v{EXTRACTOR_VERSION}.md"
)
MIN_LLM_CONFIDENCE: float = 0.4
MAX_INSIGHTS_PER_PASTE: int = 50
MAX_OPEN_QUESTIONS_PER_PASTE: int = 50

_PROMOTED_NODE_SCOPE: str = "depth"
_PROMOTED_NODE_TYPE: str = "claim"


@dataclass(frozen=True)
class LlmCallResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model_id: str = "unknown"


LlmCallable = Callable[[str], LlmCallResult]


@dataclass(frozen=True)
class ExtractedItem:
    summary: str
    quote: str
    quote_start_offset: int
    quote_end_offset: int
    llm_confidence: float


@dataclass(frozen=True)
class ExtractionResult:
    extraction_id: str
    document_id: str
    extractor_version: int
    model_id: str
    status: str  # 'ok' | 'cache_hit' | 'error'
    insights: tuple[ExtractedItem, ...]
    open_questions: tuple[ExtractedItem, ...]
    quote_drops: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error_message: Optional[str] = None


class ExtractorError(RuntimeError):
    pass


# --- prompt rendering ---


def _load_prompt_template() -> str:
    with open(_PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read()


def render_prompt(
    *,
    raw_text: str,
    source: str,
    operator_label: Optional[str],
    document_id: str,
) -> str:
    template = _load_prompt_template()
    user_block = (
        f"\nSource provider: {source}\n"
        f"Operator label: {operator_label or '(none)'}\n"
        f"Document id: {document_id}\n\n"
        f"<<<INPUT>>>\n{raw_text}\n<<<END INPUT>>>\n"
    )
    return template + "\n\n" + user_block


# --- response parsing ---

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    m = _JSON_FENCE_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(1).strip())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return {"insights": [], "open_questions": []}


def _validate_items(
    raw_items: list,
    *,
    raw_text: str,
    confidence_floor: float,
    cap: int,
) -> tuple[list[ExtractedItem], int]:
    kept: list[ExtractedItem] = []
    drops = 0
    for raw in raw_items[: cap * 4]:
        if len(kept) >= cap:
            break
        if not isinstance(raw, dict):
            drops += 1
            continue
        summary = str(raw.get("summary") or "").strip()
        quote = str(raw.get("quote") or "")
        try:
            conf = float(raw.get("llm_confidence", 0.0))
        except (TypeError, ValueError):
            drops += 1
            continue
        if not summary or not quote:
            drops += 1
            continue
        if conf < confidence_floor:
            drops += 1
            continue
        idx = raw_text.find(quote)
        if idx < 0:
            drops += 1
            continue
        kept.append(
            ExtractedItem(
                summary=summary[:2000],
                quote=quote,
                quote_start_offset=idx,
                quote_end_offset=idx + len(quote),
                llm_confidence=max(0.0, min(1.0, conf)),
            )
        )
    return kept, drops


# --- DB helpers (private; this module is the single writer) ---


def _promote_insight_to_node(
    con: LockedConnection,
    *,
    summary: str,
    quote: str,
    document_id: str,
    llm_confidence: float,
    extractor_version: int,
    model_id: str,
) -> Optional[str]:
    """Best-effort: insert a nodes row for the insight. Returns node_id
    or None if promotion failed (which leaves promoted_node_id NULL).
    Failures must not poison the extraction.
    """
    try:
        return insert_node(
            con,
            canonical_label=summary[:500],
            node_type=_PROMOTED_NODE_TYPE,
            graph_scope=_PROMOTED_NODE_SCOPE,
            investigation_id=SYSTEM_INVESTIGATION_ID,
            metadata={
                "research_bridge": {
                    "from_document_id": document_id,
                    "quote": quote[:1000],
                    "llm_confidence": llm_confidence,
                    "extractor_version": extractor_version,
                    "model_id": model_id,
                }
            },
            on_conflict="ignore",
        )
    except Exception as e:  # pragma: no cover
        import sys as _sys
        _sys.stderr.write(
            f"research_bridge: insight node promotion failed "
            f"(non-fatal): {type(e).__name__}: {e}\n"
        )
        return None


def _fetch_paste_row(con: LockedConnection, document_id: str) -> Optional[dict]:
    row = con.execute(
        """
        SELECT rp.document_id, rp.source, rp.raw_sha256, d.raw_text
        FROM research_pastes rp
        JOIN documents d ON d.document_id = rp.document_id
        WHERE rp.document_id = ?
        """,
        [document_id],
    ).fetchone()
    if row is None:
        return None
    return {
        "document_id": row[0],
        "source": row[1],
        "raw_sha256": row[2],
        "raw_text": row[3] or "",
    }


def _cache_lookup_document_id(
    con: LockedConnection, raw_sha256: str, extractor_version: int, this_doc_id: str
) -> Optional[str]:
    row = con.execute(
        """
        SELECT rp.document_id
        FROM research_pastes rp
        WHERE rp.raw_sha256 = ?
          AND rp.document_id != ?
          AND EXISTS (
            SELECT 1 FROM research_paste_insights i
            WHERE i.document_id = rp.document_id
              AND i.extractor_version = ?
          )
        LIMIT 1
        """,
        [raw_sha256, this_doc_id, int(extractor_version)],
    ).fetchone()
    return row[0] if row else None


def _copy_cached_rows(
    con: LockedConnection,
    *,
    from_document_id: str,
    to_document_id: str,
    extractor_version: int,
    model_id: str,
) -> tuple[list[ExtractedItem], list[ExtractedItem]]:
    insight_rows = con.execute(
        "SELECT summary, quote, quote_start_offset, quote_end_offset, llm_confidence "
        "FROM research_paste_insights "
        "WHERE document_id = ? AND extractor_version = ?",
        [from_document_id, int(extractor_version)],
    ).fetchall()
    question_rows = con.execute(
        "SELECT summary, quote, quote_start_offset, quote_end_offset, llm_confidence "
        "FROM research_paste_open_questions "
        "WHERE document_id = ? AND extractor_version = ?",
        [from_document_id, int(extractor_version)],
    ).fetchall()
    kept_insights = []
    for summary, quote, qs, qe, conf in insight_rows:
        promoted = _promote_insight_to_node(
            con, summary=summary, quote=quote, document_id=to_document_id,
            llm_confidence=float(conf),
            extractor_version=int(extractor_version), model_id=model_id,
        )
        con.execute(
            "INSERT INTO research_paste_insights "
            "(insight_id, document_id, summary, quote, "
            " quote_start_offset, quote_end_offset, llm_confidence, "
            " extractor_version, model_id, promoted_node_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                new_random_id("rpins"), to_document_id, summary, quote,
                int(qs), int(qe), float(conf),
                int(extractor_version), model_id, promoted,
            ],
        )
        kept_insights.append(ExtractedItem(
            summary=summary, quote=quote,
            quote_start_offset=int(qs), quote_end_offset=int(qe),
            llm_confidence=float(conf),
        ))
    kept_questions = []
    for summary, quote, qs, qe, conf in question_rows:
        con.execute(
            "INSERT INTO research_paste_open_questions "
            "(question_id, document_id, summary, quote, "
            " quote_start_offset, quote_end_offset, llm_confidence, "
            " extractor_version, model_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                new_random_id("rpoq"), to_document_id, summary, quote,
                int(qs), int(qe), float(conf),
                int(extractor_version), model_id,
            ],
        )
        kept_questions.append(ExtractedItem(
            summary=summary, quote=quote,
            quote_start_offset=int(qs), quote_end_offset=int(qe),
            llm_confidence=float(conf),
        ))
    return kept_insights, kept_questions


def _existing_at_version(
    con: LockedConnection, document_id: str, extractor_version: int
) -> bool:
    row = con.execute(
        """
        SELECT
            EXISTS (
                SELECT 1 FROM research_paste_insights
                WHERE document_id = ? AND extractor_version = ?
            )
            OR EXISTS (
                SELECT 1 FROM research_paste_open_questions
                WHERE document_id = ? AND extractor_version = ?
            )
        """,
        [document_id, int(extractor_version),
         document_id, int(extractor_version)],
    ).fetchone()
    return bool(row[0])


def _log_extraction(
    con: LockedConnection,
    *,
    extraction_id: str,
    document_id: str,
    extractor_version: int,
    model_id: str,
    started_at_epoch: float,
    status: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    insights_count: int,
    open_questions_count: int,
    quote_drops: int,
    error_message: Optional[str],
) -> None:
    _ = started_at_epoch  # reserved for future latency analytics
    con.execute(
        "INSERT INTO research_paste_extractions "
        "(extraction_id, document_id, extractor_version, model_id, "
        " status, input_tokens, output_tokens, cost_usd, "
        " insights_count, open_questions_count, quote_drops, "
        " error_message, finished_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        [
            extraction_id, document_id, int(extractor_version), model_id,
            status, int(input_tokens), int(output_tokens), float(cost_usd),
            int(insights_count), int(open_questions_count), int(quote_drops),
            error_message,
        ],
    )


# --- public API ---


def extract_paste(
    con: LockedConnection,
    document_id: str,
    *,
    llm_callable: LlmCallable,
    regenerate: bool = False,
    operator_label: Optional[str] = None,
) -> ExtractionResult:
    """Run extraction for one paste. Idempotent via (sha, version) cache."""
    if not isinstance(con, LockedConnection):
        raise TypeError(
            "extract_paste requires a LockedConnection (got "
            f"{type(con).__name__}). Use runtime.db_lock.connect_write."
        )
    paste = _fetch_paste_row(con, document_id)
    if paste is None:
        raise ValueError(f"document_id {document_id!r} not found in research_pastes")

    # Cached at this document + version?
    if not regenerate and _existing_at_version(con, document_id, EXTRACTOR_VERSION):
        extraction_id = new_random_id("rpex")
        insights, questions = _read_back(con, document_id, EXTRACTOR_VERSION)
        _log_extraction(
            con,
            extraction_id=extraction_id, document_id=document_id,
            extractor_version=EXTRACTOR_VERSION, model_id="cache",
            started_at_epoch=time.time(),
            status="cache_hit", input_tokens=0, output_tokens=0, cost_usd=0.0,
            insights_count=len(insights), open_questions_count=len(questions),
            quote_drops=0, error_message=None,
        )
        return ExtractionResult(
            extraction_id=extraction_id, document_id=document_id,
            extractor_version=EXTRACTOR_VERSION, model_id="cache",
            status="cache_hit",
            insights=tuple(insights), open_questions=tuple(questions),
            quote_drops=0, input_tokens=0, output_tokens=0, cost_usd=0.0,
        )

    # Cross-document cache: same sha + version already extracted?
    cached_from = _cache_lookup_document_id(
        con, paste["raw_sha256"], EXTRACTOR_VERSION, document_id,
    )
    if cached_from is not None and not regenerate:
        kept_insights, kept_questions = _copy_cached_rows(
            con, from_document_id=cached_from, to_document_id=document_id,
            extractor_version=EXTRACTOR_VERSION, model_id="cache",
        )
        extraction_id = new_random_id("rpex")
        _log_extraction(
            con,
            extraction_id=extraction_id, document_id=document_id,
            extractor_version=EXTRACTOR_VERSION, model_id="cache",
            started_at_epoch=time.time(),
            status="cache_hit", input_tokens=0, output_tokens=0, cost_usd=0.0,
            insights_count=len(kept_insights),
            open_questions_count=len(kept_questions),
            quote_drops=0, error_message=None,
        )
        return ExtractionResult(
            extraction_id=extraction_id, document_id=document_id,
            extractor_version=EXTRACTOR_VERSION, model_id="cache",
            status="cache_hit",
            insights=tuple(kept_insights), open_questions=tuple(kept_questions),
            quote_drops=0, input_tokens=0, output_tokens=0, cost_usd=0.0,
        )

    # Fresh extraction
    prompt = render_prompt(
        raw_text=paste["raw_text"], source=paste["source"],
        operator_label=operator_label, document_id=document_id,
    )
    started_at = time.time()
    extraction_id = new_random_id("rpex")
    try:
        llm_result = llm_callable(prompt)
    except Exception as e:
        _log_extraction(
            con,
            extraction_id=extraction_id, document_id=document_id,
            extractor_version=EXTRACTOR_VERSION, model_id="unknown",
            started_at_epoch=started_at,
            status="error", input_tokens=0, output_tokens=0, cost_usd=0.0,
            insights_count=0, open_questions_count=0, quote_drops=0,
            error_message=f"{type(e).__name__}: {e}",
        )
        raise ExtractorError(
            f"LLM call failed for document {document_id}: {type(e).__name__}: {e}"
        ) from e

    parsed = _extract_json_object(llm_result.text)
    raw_insights = parsed.get("insights") or []
    raw_questions = parsed.get("open_questions") or []
    insights, drops_a = _validate_items(
        raw_insights, raw_text=paste["raw_text"],
        confidence_floor=MIN_LLM_CONFIDENCE, cap=MAX_INSIGHTS_PER_PASTE,
    )
    questions, drops_b = _validate_items(
        raw_questions, raw_text=paste["raw_text"],
        confidence_floor=MIN_LLM_CONFIDENCE, cap=MAX_OPEN_QUESTIONS_PER_PASTE,
    )
    total_drops = drops_a + drops_b

    for item in insights:
        promoted = _promote_insight_to_node(
            con, summary=item.summary, quote=item.quote, document_id=document_id,
            llm_confidence=float(item.llm_confidence),
            extractor_version=int(EXTRACTOR_VERSION),
            model_id=llm_result.model_id,
        )
        con.execute(
            "INSERT INTO research_paste_insights "
            "(insight_id, document_id, summary, quote, "
            " quote_start_offset, quote_end_offset, llm_confidence, "
            " extractor_version, model_id, promoted_node_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                new_random_id("rpins"), document_id, item.summary, item.quote,
                item.quote_start_offset, item.quote_end_offset,
                float(item.llm_confidence),
                int(EXTRACTOR_VERSION), llm_result.model_id, promoted,
            ],
        )
    for item in questions:
        con.execute(
            "INSERT INTO research_paste_open_questions "
            "(question_id, document_id, summary, quote, "
            " quote_start_offset, quote_end_offset, llm_confidence, "
            " extractor_version, model_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                new_random_id("rpoq"), document_id, item.summary, item.quote,
                item.quote_start_offset, item.quote_end_offset,
                float(item.llm_confidence),
                int(EXTRACTOR_VERSION), llm_result.model_id,
            ],
        )

    _log_extraction(
        con,
        extraction_id=extraction_id, document_id=document_id,
        extractor_version=EXTRACTOR_VERSION, model_id=llm_result.model_id,
        started_at_epoch=started_at,
        status="ok",
        input_tokens=llm_result.input_tokens,
        output_tokens=llm_result.output_tokens,
        cost_usd=llm_result.cost_usd,
        insights_count=len(insights), open_questions_count=len(questions),
        quote_drops=total_drops, error_message=None,
    )
    return ExtractionResult(
        extraction_id=extraction_id, document_id=document_id,
        extractor_version=EXTRACTOR_VERSION, model_id=llm_result.model_id,
        status="ok",
        insights=tuple(insights), open_questions=tuple(questions),
        quote_drops=total_drops,
        input_tokens=llm_result.input_tokens,
        output_tokens=llm_result.output_tokens,
        cost_usd=llm_result.cost_usd,
    )


def _read_back(
    con: LockedConnection, document_id: str, extractor_version: int
) -> tuple[list[ExtractedItem], list[ExtractedItem]]:
    ins_rows = con.execute(
        "SELECT summary, quote, quote_start_offset, quote_end_offset, llm_confidence "
        "FROM research_paste_insights "
        "WHERE document_id = ? AND extractor_version = ? "
        "ORDER BY extracted_at DESC",
        [document_id, int(extractor_version)],
    ).fetchall()
    q_rows = con.execute(
        "SELECT summary, quote, quote_start_offset, quote_end_offset, llm_confidence "
        "FROM research_paste_open_questions "
        "WHERE document_id = ? AND extractor_version = ? "
        "ORDER BY extracted_at DESC",
        [document_id, int(extractor_version)],
    ).fetchall()
    return (
        [ExtractedItem(summary=r[0], quote=r[1], quote_start_offset=int(r[2]),
                       quote_end_offset=int(r[3]), llm_confidence=float(r[4]))
         for r in ins_rows],
        [ExtractedItem(summary=r[0], quote=r[1], quote_start_offset=int(r[2]),
                       quote_end_offset=int(r[3]), llm_confidence=float(r[4]))
         for r in q_rows],
    )


@dataclass(frozen=True)
class StoredItem:
    item_id: str
    document_id: str
    summary: str
    quote: str
    quote_start_offset: int
    quote_end_offset: int
    llm_confidence: float
    extractor_version: int
    model_id: str


def list_insights(con, *, document_id: str, version: Optional[int] = None) -> list[StoredItem]:
    if version is None:
        rows = con.execute(
            "SELECT insight_id, document_id, summary, quote, "
            "       quote_start_offset, quote_end_offset, llm_confidence, "
            "       extractor_version, model_id "
            "FROM research_paste_insights WHERE document_id = ? "
            "ORDER BY extractor_version DESC, extracted_at DESC",
            [document_id],
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT insight_id, document_id, summary, quote, "
            "       quote_start_offset, quote_end_offset, llm_confidence, "
            "       extractor_version, model_id "
            "FROM research_paste_insights "
            "WHERE document_id = ? AND extractor_version = ? "
            "ORDER BY extracted_at DESC",
            [document_id, int(version)],
        ).fetchall()
    return [
        StoredItem(
            item_id=r[0], document_id=r[1], summary=r[2], quote=r[3],
            quote_start_offset=int(r[4]), quote_end_offset=int(r[5]),
            llm_confidence=float(r[6]), extractor_version=int(r[7]),
            model_id=r[8],
        )
        for r in rows
    ]


def list_open_questions(
    con, *, document_id: str, version: Optional[int] = None
) -> list[StoredItem]:
    if version is None:
        rows = con.execute(
            "SELECT question_id, document_id, summary, quote, "
            "       quote_start_offset, quote_end_offset, llm_confidence, "
            "       extractor_version, model_id "
            "FROM research_paste_open_questions WHERE document_id = ? "
            "ORDER BY extractor_version DESC, extracted_at DESC",
            [document_id],
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT question_id, document_id, summary, quote, "
            "       quote_start_offset, quote_end_offset, llm_confidence, "
            "       extractor_version, model_id "
            "FROM research_paste_open_questions "
            "WHERE document_id = ? AND extractor_version = ? "
            "ORDER BY extracted_at DESC",
            [document_id, int(version)],
        ).fetchall()
    return [
        StoredItem(
            item_id=r[0], document_id=r[1], summary=r[2], quote=r[3],
            quote_start_offset=int(r[4]), quote_end_offset=int(r[5]),
            llm_confidence=float(r[6]), extractor_version=int(r[7]),
            model_id=r[8],
        )
        for r in rows
    ]
