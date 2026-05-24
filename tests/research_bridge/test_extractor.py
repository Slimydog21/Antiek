"""Extractor tests using a fake LLM callable.

Covers:

- Verbatim quote validation (drops items with non-substring quotes).
- Confidence floor (drops items below MIN_LLM_CONFIDENCE).
- Caching by (raw_sha256, extractor_version) — a second paste of the
  same bytes uses the cache and makes zero LLM calls.
- Idempotency: re-extracting at same version is a no-op cache_hit.
- Regenerate path: writes fresh rows alongside the prior ones.
- Single-writer grep over the insight/question/extraction tables.
- Append-only audit log.
- Cost + token accounting flows to research_paste_extractions.
- Error path: LLM raises → status='error' row + ExtractorError.

The fake LLM lets us run every test deterministically without
burning API credits.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.research_bridge import (
    EXTRACTOR_VERSION,
    ExtractedItem,
    ExtractionResult,
    ExtractorError,
    LlmCallResult,
    extract_paste,
    ingest_paste,
    list_insights,
    list_open_questions,
)


@dataclass
class FakeLlm:
    """Records each call and returns a scripted response. Use
    ``response_for`` to map prompts to canned LlmCallResults."""

    response: LlmCallResult = field(
        default_factory=lambda: LlmCallResult(
            text='{"insights": [], "open_questions": []}',
            model_id="fake/model",
        )
    )
    raise_on_call: Optional[Exception] = None
    calls: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> LlmCallResult:
        self.calls.append(prompt)
        if self.raise_on_call is not None:
            raise self.raise_on_call
        return self.response


def _ingest(db: Path, text: str, **kwargs):
    with connect_write(str(db), purpose="test_extractor/ingest") as con:
        return ingest_paste(con, raw_text=text, call_site="test", **kwargs)


def _extract(db: Path, document_id: str, llm: FakeLlm, **kwargs) -> ExtractionResult:
    with connect_write(str(db), purpose="test_extractor/extract") as con:
        return extract_paste(con, document_id, llm_callable=llm, **kwargs)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_writes_validated_rows(tmp_db_with_bridge: Path, fixture_text) -> None:
    text = fixture_text("anthropic")
    paste = _ingest(tmp_db_with_bridge, text)

    # Pick two known substrings from the fixture as our LLM's "quotes".
    quote1 = "Prime Intellect is the named incumbent at the substrate layer."
    quote2 = "Anthropic-internal verifier work has appeared in three 2024 papers but has not been productised"
    quote3 = "the question of whether the substrate or verifier layer is the more defensible business is still genuinely open"
    assert quote1 in text and quote2 in text and quote3 in text

    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [
                {"summary": "Prime Intellect named incumbent at substrate layer",
                 "quote": quote1, "llm_confidence": 0.92},
                {"summary": "Anthropic verifier work unproductised",
                 "quote": quote2, "llm_confidence": 0.78},
            ],
            "open_questions": [
                {"summary": "Substrate or verifier — which is the more defensible business?",
                 "quote": quote3, "llm_confidence": 0.85},
            ],
        }),
        input_tokens=1234, output_tokens=312, cost_usd=0.018,
        model_id="anthropic/claude-sonnet-4-6",
    ))

    result = _extract(tmp_db_with_bridge, paste.document_id, llm)
    assert result.status == "ok"
    assert len(result.insights) == 2
    assert len(result.open_questions) == 1
    assert result.quote_drops == 0
    assert result.input_tokens == 1234
    assert result.output_tokens == 312
    assert result.cost_usd == pytest.approx(0.018)

    # Offsets are correct
    for item in result.insights + result.open_questions:
        assert text[item.quote_start_offset:item.quote_end_offset] == item.quote


def test_read_back_via_list_helpers(tmp_db_with_bridge: Path, fixture_text) -> None:
    text = fixture_text("alphasense")
    paste = _ingest(tmp_db_with_bridge, text)
    quote = "Buy / Hold / Sell consensus (sell-side): 9 Buy / 4 Hold / 1 Sell."
    assert quote in text

    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [{"summary": "Mixed sell-side consensus",
                          "quote": quote, "llm_confidence": 0.88}],
            "open_questions": [],
        }),
        model_id="anthropic/claude-sonnet-4-6",
    ))
    _extract(tmp_db_with_bridge, paste.document_id, llm)

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        insights = list_insights(con, document_id=paste.document_id)
        questions = list_open_questions(con, document_id=paste.document_id)
    finally:
        con.close()
    assert len(insights) == 1
    assert insights[0].summary == "Mixed sell-side consensus"
    assert insights[0].extractor_version == EXTRACTOR_VERSION
    assert questions == []


# ---------------------------------------------------------------------------
# Verbatim-quote validation
# ---------------------------------------------------------------------------


def test_drops_items_with_non_substring_quote(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    text = fixture_text("chatgpt")
    paste = _ingest(tmp_db_with_bridge, text)

    real_quote = "The market for on-policy reinforcement-learning training of code-completion agents"
    assert real_quote in text
    fake_quote = "This sentence is not anywhere in the paste."

    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [
                {"summary": "Real", "quote": real_quote, "llm_confidence": 0.9},
                {"summary": "Fabricated", "quote": fake_quote, "llm_confidence": 0.9},
            ],
            "open_questions": [],
        }),
        model_id="fake",
    ))
    result = _extract(tmp_db_with_bridge, paste.document_id, llm)
    assert len(result.insights) == 1
    assert result.insights[0].summary == "Real"
    assert result.quote_drops == 1


def test_drops_low_confidence_items(tmp_db_with_bridge: Path, fixture_text) -> None:
    text = fixture_text("grok")
    paste = _ingest(tmp_db_with_bridge, text)
    quote = "Prime Intellect dominates substrate"
    assert quote in text

    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [
                {"summary": "Trustworthy", "quote": quote, "llm_confidence": 0.9},
                {"summary": "Noisy", "quote": quote, "llm_confidence": 0.2},
            ],
            "open_questions": [],
        }),
        model_id="fake",
    ))
    result = _extract(tmp_db_with_bridge, paste.document_id, llm)
    assert len(result.insights) == 1
    assert result.insights[0].summary == "Trustworthy"
    assert result.quote_drops == 1


def test_empty_arrays_on_unparseable_response(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    text = fixture_text("chatgpt")
    paste = _ingest(tmp_db_with_bridge, text)

    llm = FakeLlm(response=LlmCallResult(
        text="I'm sorry, I cannot comply with this request.",
        model_id="fake",
    ))
    result = _extract(tmp_db_with_bridge, paste.document_id, llm)
    assert result.status == "ok"  # we don't fail the call — fallback to empty
    assert result.insights == ()
    assert result.open_questions == ()


def test_tolerates_json_fence_wrapping(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    """Some models wrap JSON in ```json fences``` despite instructions
    to the contrary. We tolerate it."""
    text = fixture_text("anthropic")
    paste = _ingest(tmp_db_with_bridge, text)
    quote = "Prime Intellect is the named incumbent at the substrate layer."

    response_text = (
        "Here is the extracted JSON:\n\n"
        "```json\n"
        + json.dumps({
            "insights": [{"summary": "PI incumbent", "quote": quote,
                          "llm_confidence": 0.9}],
            "open_questions": [],
        })
        + "\n```\n"
    )
    llm = FakeLlm(response=LlmCallResult(text=response_text, model_id="fake"))
    result = _extract(tmp_db_with_bridge, paste.document_id, llm)
    assert len(result.insights) == 1


# ---------------------------------------------------------------------------
# Cache (raw_sha256, extractor_version)
# ---------------------------------------------------------------------------


def test_repeat_same_doc_is_cache_hit(tmp_db_with_bridge: Path, fixture_text) -> None:
    text = fixture_text("chatgpt")
    paste = _ingest(tmp_db_with_bridge, text)
    quote = "The market for on-policy reinforcement-learning training of code-completion agents"

    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [{"summary": "Market shape", "quote": quote,
                          "llm_confidence": 0.9}],
            "open_questions": [],
        }),
        model_id="fake",
    ))
    r1 = _extract(tmp_db_with_bridge, paste.document_id, llm)
    assert r1.status == "ok"
    assert len(llm.calls) == 1

    # Second call at same version should not invoke the LLM.
    r2 = _extract(tmp_db_with_bridge, paste.document_id, llm)
    assert r2.status == "cache_hit"
    assert len(llm.calls) == 1, "extractor called the LLM on a same-doc repeat"
    assert len(r2.insights) == 1


def test_cache_hit_across_different_pastes_same_content(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    """Two ingests of the exact same text dedupe at the document
    layer (same content-addressed id). Verify that even if they were
    distinct documents, extraction would still cache by raw_sha256.

    We force this by ingesting and extracting paste A, then ingesting
    paste B with text that hashes to the same sha by being identical.
    Since the document_id is content-addressed, A and B share an id
    AND share a sha, so the (sha, version) cache fires for both.
    """
    text = fixture_text("anthropic")
    quote = "Prime Intellect is the named incumbent at the substrate layer."

    pA = _ingest(tmp_db_with_bridge, text, operator_label="A")
    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [{"summary": "PI incumbent", "quote": quote,
                          "llm_confidence": 0.9}],
            "open_questions": [],
        }),
        model_id="fake",
    ))
    _extract(tmp_db_with_bridge, pA.document_id, llm)
    assert len(llm.calls) == 1

    # Same text — same document_id and same sha. Second extraction is
    # cache.
    pB = _ingest(tmp_db_with_bridge, text, operator_label="B")
    assert pB.document_id == pA.document_id
    r = _extract(tmp_db_with_bridge, pB.document_id, llm)
    assert r.status == "cache_hit"
    assert len(llm.calls) == 1


def test_regenerate_skips_cache(tmp_db_with_bridge: Path, fixture_text) -> None:
    text = fixture_text("alphasense")
    paste = _ingest(tmp_db_with_bridge, text)
    quote = "Buy / Hold / Sell consensus (sell-side): 9 Buy / 4 Hold / 1 Sell."

    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [{"summary": "Consensus", "quote": quote,
                          "llm_confidence": 0.9}],
            "open_questions": [],
        }),
        model_id="fake",
    ))
    _extract(tmp_db_with_bridge, paste.document_id, llm)
    assert len(llm.calls) == 1

    _extract(tmp_db_with_bridge, paste.document_id, llm, regenerate=True)
    assert len(llm.calls) == 2, "regenerate should bypass the cache"

    # Now two rows at this version (audit trail).
    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM research_paste_insights "
            "WHERE document_id = ? AND extractor_version = ?",
            [paste.document_id, EXTRACTOR_VERSION],
        ).fetchone()[0]
    finally:
        con.close()
    assert n == 2


# ---------------------------------------------------------------------------
# Extraction-log
# ---------------------------------------------------------------------------


def test_extraction_log_records_costs(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    text = fixture_text("chatgpt")
    paste = _ingest(tmp_db_with_bridge, text)
    quote = "The market for on-policy reinforcement-learning training of code-completion agents"

    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({"insights": [{"summary": "x", "quote": quote,
                                       "llm_confidence": 0.9}],
                        "open_questions": []}),
        input_tokens=5000, output_tokens=300, cost_usd=0.045,
        model_id="anthropic/claude-sonnet-4-6",
    ))
    _extract(tmp_db_with_bridge, paste.document_id, llm)

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        row = con.execute(
            "SELECT status, input_tokens, output_tokens, cost_usd, "
            "       insights_count, open_questions_count, quote_drops "
            "FROM research_paste_extractions WHERE document_id = ?",
            [paste.document_id],
        ).fetchone()
    finally:
        con.close()
    assert row[0] == "ok"
    assert row[1] == 5000
    assert row[2] == 300
    assert row[3] == pytest.approx(0.045)
    assert row[4] == 1
    assert row[5] == 0


def test_extraction_log_records_errors(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    text = fixture_text("anthropic")
    paste = _ingest(tmp_db_with_bridge, text)
    llm = FakeLlm(raise_on_call=RuntimeError("provider 503"))

    with pytest.raises(ExtractorError):
        _extract(tmp_db_with_bridge, paste.document_id, llm)

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        row = con.execute(
            "SELECT status, error_message FROM research_paste_extractions "
            "WHERE document_id = ?",
            [paste.document_id],
        ).fetchone()
    finally:
        con.close()
    assert row[0] == "error"
    assert "provider 503" in row[1]


def test_cache_hit_logged(tmp_db_with_bridge: Path, fixture_text) -> None:
    text = fixture_text("grok")
    paste = _ingest(tmp_db_with_bridge, text)
    quote = "Prime Intellect dominates substrate"

    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [{"summary": "Domination", "quote": quote,
                          "llm_confidence": 0.9}],
            "open_questions": [],
        }),
        model_id="fake",
    ))
    _extract(tmp_db_with_bridge, paste.document_id, llm)
    _extract(tmp_db_with_bridge, paste.document_id, llm)  # cache hit

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        rows = con.execute(
            "SELECT status FROM research_paste_extractions "
            "WHERE document_id = ? ORDER BY started_at",
            [paste.document_id],
        ).fetchall()
    finally:
        con.close()
    statuses = [r[0] for r in rows]
    assert statuses[0] == "ok"
    assert statuses[1] == "cache_hit"


# ---------------------------------------------------------------------------
# Single-writer + append-only invariants
# ---------------------------------------------------------------------------


def test_single_writer_for_insights() -> None:
    """Exactly one INSERT INTO research_paste_insights call site, in
    extractor.py."""
    repo = Path(__file__).resolve().parents[2]
    out = subprocess.run(
        ["rg", "--no-heading", "-n", '"INSERT INTO research_paste_insights', str(repo)],
        capture_output=True, text=True, check=False,
    )
    matches = out.stdout.strip().splitlines() if out.returncode == 0 else []
    matches = [m for m in matches if "/.venv/" not in m and "/__pycache__/" not in m
               and "tests/research_bridge/test_extractor.py" not in m]
    # extractor.py writes once for fresh extraction, once for cache copy.
    # Both are inside the same module. We require ALL matches to live in
    # substrate/research_bridge/extractor.py.
    assert all("substrate/research_bridge/extractor.py" in m for m in matches), (
        f"unexpected writer to research_paste_insights: {matches}"
    )


def test_single_writer_for_open_questions() -> None:
    repo = Path(__file__).resolve().parents[2]
    out = subprocess.run(
        ["rg", "--no-heading", "-n",
         '"INSERT INTO research_paste_open_questions', str(repo)],
        capture_output=True, text=True, check=False,
    )
    matches = out.stdout.strip().splitlines() if out.returncode == 0 else []
    matches = [m for m in matches if "/.venv/" not in m and "/__pycache__/" not in m
               and "tests/research_bridge/test_extractor.py" not in m]
    assert all("substrate/research_bridge/extractor.py" in m for m in matches), (
        f"unexpected writer to research_paste_open_questions: {matches}"
    )


def test_extractions_table_append_only_in_code() -> None:
    """No UPDATE / DELETE in the research_bridge module against
    research_paste_extractions."""
    bridge = Path(__file__).resolve().parents[2] / "substrate" / "research_bridge"
    for f in bridge.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "UPDATE research_paste_extractions" not in text, (
            f"append-only violation in {f}"
        )
        assert "DELETE FROM research_paste_extractions" not in text, (
            f"append-only violation in {f}"
        )


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def test_missing_document_id_raises(tmp_db_with_bridge: Path) -> None:
    llm = FakeLlm()
    with pytest.raises(ValueError, match="not found"):
        _extract(tmp_db_with_bridge, "doc-deadbeef", llm)


def test_offsets_round_trip(tmp_db_with_bridge: Path, fixture_text) -> None:
    text = fixture_text("alphasense")
    paste = _ingest(tmp_db_with_bridge, text)
    quote = "Investor day scheduled for January 22 2025"
    assert quote in text

    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [{"summary": "Investor day in Jan", "quote": quote,
                          "llm_confidence": 0.85}],
            "open_questions": [],
        }),
        model_id="fake",
    ))
    r = _extract(tmp_db_with_bridge, paste.document_id, llm)
    insight = r.insights[0]
    assert text[insight.quote_start_offset:insight.quote_end_offset] == quote
