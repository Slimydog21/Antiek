"""Insight → node promotion tests (SPR-04 minimal patch).

Verifies that:

- Every extracted insight produces a corresponding nodes row.
- The insight row carries the promoted_node_id back-reference.
- A second extraction of the same content is idempotent at the
  nodes level (content-addressed dedup), but the second
  research_paste_insights row still gets the existing node_id.
- Open questions are NOT promoted (only insights are claims).
- Antiek's /blocks/search style query against the nodes table
  surfaces paste-derived insights.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.research_bridge import (
    LlmCallResult,
    extract_paste,
    ingest_paste,
    list_insights,
)


def _ingest(db: Path, text: str):
    with connect_write(str(db), purpose="test_promotion/ingest") as con:
        return ingest_paste(con, raw_text=text, call_site="test")


def _extract(db: Path, document_id: str, llm):
    with connect_write(str(db), purpose="test_promotion/extract") as con:
        return extract_paste(con, document_id, llm_callable=llm)


def test_insight_promotes_to_nodes(tmp_db_with_bridge: Path, fixture_text) -> None:
    text = fixture_text("anthropic")
    paste = _ingest(tmp_db_with_bridge, text)
    quote = "Prime Intellect is the named incumbent at the substrate layer."
    assert quote in text

    from tests.research_bridge.test_extractor import FakeLlm  # reuse
    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [{"summary": "Prime Intellect leads the substrate layer",
                          "quote": quote, "llm_confidence": 0.9}],
            "open_questions": [],
        }),
        model_id="fake/test",
    ))
    result = _extract(tmp_db_with_bridge, paste.document_id, llm)

    assert len(result.insights) == 1

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        # promoted_node_id is populated on the insight row
        row = con.execute(
            "SELECT promoted_node_id FROM research_paste_insights "
            "WHERE document_id = ?",
            [paste.document_id],
        ).fetchone()
        assert row[0] is not None
        node_id = row[0]

        # And the nodes row exists with our canonical_label
        node_row = con.execute(
            "SELECT canonical_label, node_type, graph_scope "
            "FROM nodes WHERE node_id = ?",
            [node_id],
        ).fetchone()
    finally:
        con.close()

    assert node_row is not None
    assert node_row[0] == "Prime Intellect leads the substrate layer"
    assert node_row[1] == "claim"
    assert node_row[2] == "depth"


def test_open_question_does_not_promote(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    """Open questions live in research_paste_open_questions only —
    they are NOT pushed into the nodes table. (Questions aren't
    claims; the nodes.node_type CHECK doesn't include 'question'
    anyway.)
    """
    text = fixture_text("anthropic")
    paste = _ingest(tmp_db_with_bridge, text)
    quote = "Anthropic-internal verifier work has appeared in three 2024 papers but has not been productised"
    assert quote in text

    from tests.research_bridge.test_extractor import FakeLlm
    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [],
            "open_questions": [{
                "summary": "When does Anthropic ship internal verifier as product",
                "quote": quote, "llm_confidence": 0.9,
            }],
        }),
        model_id="fake/test",
    ))
    _extract(tmp_db_with_bridge, paste.document_id, llm)

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        n_questions = con.execute(
            "SELECT COUNT(*) FROM research_paste_open_questions"
        ).fetchone()[0]
        n_nodes_with_question_label = con.execute(
            "SELECT COUNT(*) FROM nodes "
            "WHERE canonical_label LIKE '%When does Anthropic%'"
        ).fetchone()[0]
    finally:
        con.close()
    assert n_questions == 1
    assert n_nodes_with_question_label == 0


def test_node_dedup_on_same_summary_across_pastes(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    """Two distinct pastes that produce the same insight summary
    should share ONE nodes row (content-addressed). The
    research_paste_insights rows are distinct (one per paste) but
    each carries the same promoted_node_id.
    """
    text_a = fixture_text("anthropic")
    text_b = fixture_text("chatgpt")  # truly different bytes
    paste_a = _ingest(tmp_db_with_bridge, text_a)
    paste_b = _ingest(tmp_db_with_bridge, text_b)

    # Choose summaries identical across the two pastes; quotes must
    # be substrings of their respective raw_text.
    quote_a = "Prime Intellect is the named incumbent at the substrate layer."
    quote_b = "Prime Intellect [1] is the visible incumbent"
    assert quote_a in text_a and quote_b in text_b

    from tests.research_bridge.test_extractor import FakeLlm
    llm_a = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [{"summary": "Prime Intellect leads substrate",
                          "quote": quote_a, "llm_confidence": 0.9}],
            "open_questions": [],
        }),
        model_id="fake",
    ))
    llm_b = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [{"summary": "Prime Intellect leads substrate",
                          "quote": quote_b, "llm_confidence": 0.9}],
            "open_questions": [],
        }),
        model_id="fake",
    ))
    _extract(tmp_db_with_bridge, paste_a.document_id, llm_a)
    _extract(tmp_db_with_bridge, paste_b.document_id, llm_b)

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        node_ids = con.execute(
            "SELECT DISTINCT promoted_node_id FROM research_paste_insights"
        ).fetchall()
    finally:
        con.close()
    # One distinct node — content-addressed dedup fired.
    assert len(node_ids) == 1


def test_blocks_search_query_surfaces_paste_insight(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    """Emulate the existing /blocks/search query (ILIKE over
    nodes.canonical_label) and verify a paste-derived insight is
    found. This is the SPR-04 acceptance criterion: paste insights
    show up where existing UI surfaces look for them.
    """
    text = fixture_text("anthropic")
    paste = _ingest(tmp_db_with_bridge, text)
    quote = "Prime Intellect is the named incumbent at the substrate layer."
    assert quote in text

    from tests.research_bridge.test_extractor import FakeLlm
    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [{"summary": "Prime Intellect leads the substrate layer",
                          "quote": quote, "llm_confidence": 0.9}],
            "open_questions": [],
        }),
        model_id="fake",
    ))
    _extract(tmp_db_with_bridge, paste.document_id, llm)

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        # The /blocks/search SQL shape, simplified
        rows = con.execute(
            "SELECT node_id, canonical_label, node_type FROM nodes "
            "WHERE canonical_label ILIKE ?",
            ["%substrate layer%"],
        ).fetchall()
    finally:
        con.close()
    assert any("Prime Intellect leads" in r[1] for r in rows), (
        f"paste-derived insight not surfaced by /blocks/search shape: {rows}"
    )