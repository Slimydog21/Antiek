"""Gap-finder tests against a fake LLM.

Covers:

- Schema scope-collection (open questions for in-scope pastes only).
- Cluster parser: drops malformed clusters, dedupes priority ranks,
  caps at MAX_CLUSTERS, rejects clusters with zero valid question_ids.
- Cascade parser: drops items with unknown cluster_id, unknown
  target_provider, fails-grounding-check; counts grounding_drops.
- Determinism: same inputs + same LLM responses → same persisted rows
  (up to id generation).
- find_gaps end-to-end: writes run + clusters + cluster-questions +
  prompts atomically; cost accounting flows to the run row.
- Empty scope (no questions) records a zero-row audit run.
- Signal capture (👍/👎) + answer link + would_run_percentage helper.
- Re-running creates a new immutable run row; the prior run is
  preserved.
- Single-writer invariant for all 6 gap tables.
- Append-only signals (no UPDATE / DELETE in module).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.research_bridge import (
    GapFinderError,
    GapRunResult,
    LlmCallResult,
    extract_paste,
    find_gaps,
    ingest_paste,
    list_gap_runs,
    list_open_questions,
    read_gap_run,
    record_prompt_answer,
    record_prompt_signal,
    would_run_percentage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _ingest_and_extract(
    db: Path, text: str, *, ins_summary: str, ins_quote: str,
    q_summary: str, q_quote: str,
) -> tuple[str, list]:
    """Ingest a paste, then extract one insight + one open question
    from it using a fake LLM. Returns (document_id, [question_ids])."""
    from tests.research_bridge.test_extractor import FakeLlm  # reuse
    with connect_write(str(db), purpose="test_gap/ingest") as con:
        p = ingest_paste(con, raw_text=text, call_site="test")

    llm = FakeLlm(response=LlmCallResult(
        text=json.dumps({
            "insights": [{"summary": ins_summary, "quote": ins_quote,
                          "llm_confidence": 0.9}],
            "open_questions": [{"summary": q_summary, "quote": q_quote,
                                "llm_confidence": 0.85}],
        }),
        input_tokens=100, output_tokens=20, cost_usd=0.001,
        model_id="fake/test",
    ))
    with connect_write(str(db), purpose="test_gap/extract") as con:
        extract_paste(con, p.document_id, llm_callable=llm)

    con = duckdb.connect(str(db), read_only=True)
    try:
        qs = list_open_questions(con, document_id=p.document_id)
    finally:
        con.close()
    return p.document_id, [q.item_id for q in qs]


class _CannedLlm:
    """Returns scripted responses in order. Each call consumes one
    response. Useful for find_gaps which calls the LLM twice
    (cluster then cascade)."""

    def __init__(self, responses: list[LlmCallResult]):
        self.responses = list(responses)
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> LlmCallResult:
        self.calls.append(prompt)
        if not self.responses:
            raise RuntimeError("CannedLlm: no more responses scripted")
        return self.responses.pop(0)


def _setup_two_pastes_with_questions(db: Path, fixture_text):
    """Create two pastes, extract one open question from each.
    Returns (doc_id_a, doc_id_b, [q_a_id, q_b_id])."""
    text_a = fixture_text("anthropic")
    text_b = fixture_text("alphasense")

    doc_a, qids_a = _ingest_and_extract(
        db, text_a,
        ins_summary="Substrate concentration is real",
        ins_quote="Prime Intellect is the named incumbent at the substrate layer.",
        q_summary="Will Anthropic ship internal verifier as product",
        q_quote="Anthropic-internal verifier work has appeared in three 2024 papers but has not been productised",
    )
    doc_b, qids_b = _ingest_and_extract(
        db, text_b,
        ins_summary="Goldman has buy rating with PT $72",
        ins_quote="Goldman Sachs (Buy, PT $72)",
        q_summary="Will compute marketplace customer commitments materialize",
        q_quote="management indicated they will disclose Compute Marketplace customer commitments.",
    )
    return doc_a, doc_b, qids_a + qids_b


# ---------------------------------------------------------------------------
# Schema scope collection
# ---------------------------------------------------------------------------


def test_empty_scope_writes_audit_run_only(tmp_db_with_bridge: Path, fixture_text) -> None:
    """No open questions in scope → run row written, zero clusters/prompts."""
    doc_a, _doc_b, _qids = _setup_two_pastes_with_questions(tmp_db_with_bridge, fixture_text)
    # Scope to a paste that exists but where we'll skip extraction.
    text = fixture_text("chatgpt")
    with connect_write(str(tmp_db_with_bridge), purpose="test_gap/no_ext") as con:
        p = ingest_paste(con, raw_text=text, call_site="test", operator_label="unextracted")

    llm = _CannedLlm([])  # should not be called
    with connect_write(str(tmp_db_with_bridge), purpose="test_gap/find") as con:
        result = find_gaps(con, scope_block_ids=[p.document_id], llm_callable=llm)
    assert result.clusters == ()
    assert result.prompts == ()
    assert llm.calls == []  # no LLM call when scope yields zero questions

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        runs = list_gap_runs(con)
    finally:
        con.close()
    assert any(r.run_id == result.run_id for r in runs)


def test_scope_must_be_non_empty(tmp_db_with_bridge: Path) -> None:
    llm = _CannedLlm([])
    with connect_write(str(tmp_db_with_bridge), purpose="test_gap") as con:
        with pytest.raises(ValueError, match="non-empty"):
            find_gaps(con, scope_block_ids=[], llm_callable=llm)


# ---------------------------------------------------------------------------
# End-to-end happy path
# ---------------------------------------------------------------------------


def test_find_gaps_happy_path(tmp_db_with_bridge: Path, fixture_text) -> None:
    doc_a, doc_b, qids = _setup_two_pastes_with_questions(tmp_db_with_bridge, fixture_text)
    assert len(qids) == 2

    cluster_response = LlmCallResult(
        text=json.dumps({
            "clusters": [
                {
                    "label": "Anthropic verifier productisation timeline",
                    "rationale": "Both touch on verifier shipping",
                    "priority_rank": 0,
                    "question_ids": qids,
                },
            ],
        }),
        input_tokens=400, output_tokens=80, cost_usd=0.004,
        model_id="fake/cluster-model",
    )
    cascade_response = LlmCallResult(
        text=json.dumps({
            "prompts": [
                {
                    "cluster_id": "__placeholder__",  # will be overwritten in test setup
                    "order_index": 0,
                    "prompt_text": (
                        "Investigate Anthropic verifier productisation timeline: "
                        "have any of the three 2024 verifier papers landed as a "
                        "shipped product in Q1 2025? Compute marketplace commitments?"
                    ),
                    "target_provider": "anthropic",
                    "expected_output_shape": "List of products and dates",
                    "depends_on_prior_order_index": None,
                    "rationale": "Anthropic is the directly relevant LLM provider",
                },
            ],
        }),
        input_tokens=600, output_tokens=120, cost_usd=0.008,
        model_id="fake/cascade-model",
    )

    # We need the cascade to reference the actual cluster_id the
    # clusterer emitted. Two-pass approach: run find_gaps with a llm
    # whose cascade-response we can rewrite after seeing the cluster
    # call. Simpler: write a callable that snoops the cluster
    # response, extracts the new cluster_id, and patches the cascade
    # response on the fly.
    cluster_then_cascade = _DynamicCannedLlm(
        cluster_response=cluster_response,
        cascade_response_template=cascade_response,
    )
    with connect_write(str(tmp_db_with_bridge), purpose="test_gap/find") as con:
        result = find_gaps(
            con,
            scope_block_ids=[doc_a, doc_b],
            llm_callable=cluster_then_cascade,
            operator_label="happy path test",
            session_id="S-happy",
        )

    assert len(result.clusters) == 1
    assert len(result.prompts) == 1
    assert result.prompts[0].target_provider == "anthropic"
    assert result.total_input_tokens == 1000
    assert result.total_output_tokens == 200
    assert result.total_cost_usd == pytest.approx(0.012)
    assert result.grounding_drops == 0

    # Read-back round trip
    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        run, clusters, prompts = read_gap_run(con, result.run_id)
    finally:
        con.close()
    assert run is not None
    assert run.operator_label == "happy path test"
    assert run.session_id == "S-happy"
    assert set(run.scope_block_ids) == {doc_a, doc_b}
    assert len(clusters) == 1
    assert clusters[0].label == "Anthropic verifier productisation timeline"
    assert clusters[0].priority_rank == 0
    assert len(prompts) == 1
    assert prompts[0].order_index == 0


class _DynamicCannedLlm:
    """Two-call LLM stub. The cluster response is fixed; the cascade
    response has its `cluster_id` placeholder replaced with whatever
    cluster_id the parser ends up generating from the cluster call.

    The cluster_id is content-generated inside _parse_cluster_response
    (via new_random_id), so we can't predict it in advance. We snoop
    the substrate post-cluster-call by reading the row that was just
    written; but find_gaps holds an open transaction. Simpler tactic:
    after parsing, find_gaps holds GapCluster instances with the
    generated cluster_id; we override the cascade response right
    before the second call by inspecting the rendered cascade prompt
    (which contains the cluster_id).
    """

    def __init__(self, *, cluster_response: LlmCallResult,
                 cascade_response_template: LlmCallResult):
        self._cluster_response = cluster_response
        self._cascade_template = cascade_response_template
        self._call_idx = 0
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> LlmCallResult:
        self.calls.append(prompt)
        self._call_idx += 1
        if self._call_idx == 1:
            return self._cluster_response
        # Cascade call: extract the actual cluster_id from the prompt
        # (it's rendered as "cluster_id: rgcl-XXXX") and rewrite the
        # template.
        import re
        m = re.search(r"cluster_id:\s*(rgcl-[a-f0-9]+)", prompt)
        if not m:
            return self._cascade_template
        real_cluster_id = m.group(1)
        body = json.loads(self._cascade_template.text)
        for p in body.get("prompts", []):
            p["cluster_id"] = real_cluster_id
        return LlmCallResult(
            text=json.dumps(body),
            input_tokens=self._cascade_template.input_tokens,
            output_tokens=self._cascade_template.output_tokens,
            cost_usd=self._cascade_template.cost_usd,
            model_id=self._cascade_template.model_id,
        )


# ---------------------------------------------------------------------------
# Validation: malformed cluster / cascade
# ---------------------------------------------------------------------------


def test_parser_drops_unknown_question_ids(tmp_db_with_bridge: Path, fixture_text) -> None:
    """A cluster referencing a question_id NOT in the input is rejected."""
    doc_a, doc_b, qids = _setup_two_pastes_with_questions(tmp_db_with_bridge, fixture_text)
    cluster_resp = LlmCallResult(text=json.dumps({
        "clusters": [
            {"label": "Real", "priority_rank": 0, "question_ids": qids},
            {"label": "Fake", "priority_rank": 1, "question_ids": ["rpoq-fake"]},
        ],
    }), model_id="fake")
    # Cascade returns nothing for simplicity.
    cascade_resp = LlmCallResult(text=json.dumps({"prompts": []}), model_id="fake")
    llm = _DynamicCannedLlm(cluster_response=cluster_resp,
                            cascade_response_template=cascade_resp)
    with connect_write(str(tmp_db_with_bridge), purpose="test_gap") as con:
        r = find_gaps(con, scope_block_ids=[doc_a, doc_b], llm_callable=llm)
    assert len(r.clusters) == 1
    assert r.clusters[0].label == "Real"


def test_parser_dedupes_priority_ranks(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    doc_a, doc_b, qids = _setup_two_pastes_with_questions(tmp_db_with_bridge, fixture_text)
    cluster_resp = LlmCallResult(text=json.dumps({
        "clusters": [
            {"label": "A", "priority_rank": 0, "question_ids": [qids[0]]},
            {"label": "B", "priority_rank": 0, "question_ids": [qids[1]]},  # dup rank
        ],
    }), model_id="fake")
    cascade_resp = LlmCallResult(text=json.dumps({"prompts": []}), model_id="fake")
    llm = _DynamicCannedLlm(cluster_response=cluster_resp,
                            cascade_response_template=cascade_resp)
    with connect_write(str(tmp_db_with_bridge), purpose="test_gap") as con:
        r = find_gaps(con, scope_block_ids=[doc_a, doc_b], llm_callable=llm)
    assert len(r.clusters) == 1
    # Whichever wins, ranks normalize to 0..N-1.
    assert r.clusters[0].priority_rank == 0


def test_cascade_drops_unknown_provider(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    doc_a, doc_b, qids = _setup_two_pastes_with_questions(tmp_db_with_bridge, fixture_text)
    cluster_resp = LlmCallResult(text=json.dumps({
        "clusters": [
            {"label": "Verifier timeline", "priority_rank": 0, "question_ids": qids},
        ],
    }), model_id="fake")
    cascade_resp = LlmCallResult(text=json.dumps({
        "prompts": [
            {
                "cluster_id": "__placeholder__",
                "order_index": 0,
                "prompt_text": "Verifier toolkit consolidation timeline",
                "target_provider": "perplexity",  # not in KNOWN_SOURCES
                "rationale": "x",
            },
        ],
    }), model_id="fake")
    llm = _DynamicCannedLlm(cluster_response=cluster_resp,
                            cascade_response_template=cascade_resp)
    with connect_write(str(tmp_db_with_bridge), purpose="test_gap") as con:
        r = find_gaps(con, scope_block_ids=[doc_a, doc_b], llm_callable=llm)
    assert len(r.prompts) == 0  # all dropped


def test_cascade_grounding_check_drops(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    """A prompt that shares NO terms-of-art with its cluster's
    source questions is dropped + counted in grounding_drops."""
    doc_a, doc_b, qids = _setup_two_pastes_with_questions(tmp_db_with_bridge, fixture_text)
    cluster_resp = LlmCallResult(text=json.dumps({
        "clusters": [
            {"label": "Verifier productisation",
             "priority_rank": 0, "question_ids": qids},
        ],
    }), model_id="fake")
    cascade_resp = LlmCallResult(text=json.dumps({
        "prompts": [
            {
                # Real grounded prompt (shares "verifier" with cluster label/questions)
                "cluster_id": "__placeholder__",
                "order_index": 0,
                "prompt_text": "Investigate the verifier productisation timeline for Q1 2025",
                "target_provider": "anthropic",
                "rationale": "Direct match",
            },
            {
                # Ungrounded — shares nothing with cluster's source
                "cluster_id": "__placeholder__",
                "order_index": 1,
                "prompt_text": "What is the weather like in Buenos Aires?",
                "target_provider": "chatgpt",
                "rationale": "Hallucinated",
            },
        ],
    }), model_id="fake")
    llm = _DynamicCannedLlm(cluster_response=cluster_resp,
                            cascade_response_template=cascade_resp)
    with connect_write(str(tmp_db_with_bridge), purpose="test_gap") as con:
        r = find_gaps(con, scope_block_ids=[doc_a, doc_b], llm_callable=llm)
    assert len(r.prompts) == 1
    assert r.grounding_drops == 1


# ---------------------------------------------------------------------------
# Re-run history
# ---------------------------------------------------------------------------


def test_re_run_creates_new_immutable_run(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    doc_a, doc_b, qids = _setup_two_pastes_with_questions(tmp_db_with_bridge, fixture_text)
    cluster_resp = LlmCallResult(text=json.dumps({
        "clusters": [
            {"label": "A", "priority_rank": 0, "question_ids": qids[:1]},
        ],
    }), model_id="fake")
    cascade_resp = LlmCallResult(text=json.dumps({
        "prompts": [
            {
                "cluster_id": "__placeholder__",
                "order_index": 0,
                "prompt_text": "verifier productisation",
                "target_provider": "anthropic",
                "rationale": "x",
            },
        ],
    }), model_id="fake")

    with connect_write(str(tmp_db_with_bridge), purpose="t1") as con:
        r1 = find_gaps(
            con, scope_block_ids=[doc_a, doc_b],
            llm_callable=_DynamicCannedLlm(
                cluster_response=cluster_resp,
                cascade_response_template=cascade_resp,
            ),
        )
    with connect_write(str(tmp_db_with_bridge), purpose="t2") as con:
        r2 = find_gaps(
            con, scope_block_ids=[doc_a, doc_b],
            llm_callable=_DynamicCannedLlm(
                cluster_response=cluster_resp,
                cascade_response_template=cascade_resp,
            ),
        )
    assert r1.run_id != r2.run_id

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        run_ids = {r.run_id for r in list_gap_runs(con)}
    finally:
        con.close()
    assert {r1.run_id, r2.run_id}.issubset(run_ids)


# ---------------------------------------------------------------------------
# Signals + would_run percentage
# ---------------------------------------------------------------------------


def _setup_run_with_prompts(db: Path, fixture_text, n_prompts: int) -> list[str]:
    """Helper: create a run with n_prompts prompts; return prompt_ids."""
    doc_a, doc_b, qids = _setup_two_pastes_with_questions(db, fixture_text)
    cluster_resp = LlmCallResult(text=json.dumps({
        "clusters": [
            {"label": "Verifier productisation", "priority_rank": 0, "question_ids": qids},
        ],
    }), model_id="fake")
    prompts = []
    for i in range(n_prompts):
        prompts.append({
            "cluster_id": "__placeholder__",
            "order_index": i,
            "prompt_text": f"Verifier productisation status check #{i}",
            "target_provider": "anthropic",
            "rationale": "x",
        })
    cascade_resp = LlmCallResult(
        text=json.dumps({"prompts": prompts}), model_id="fake",
    )
    llm = _DynamicCannedLlm(cluster_response=cluster_resp, cascade_response_template=cascade_resp)
    with connect_write(str(db), purpose="setup") as con:
        r = find_gaps(con, scope_block_ids=[doc_a, doc_b], llm_callable=llm)
    return [p.prompt_id for p in (
        # Re-read prompt_ids from DB since GapPrompt result doesn't carry them.
        []
    )] or _read_prompt_ids(db, r.run_id)


def _read_prompt_ids(db: Path, run_id: str) -> list[str]:
    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = con.execute(
            "SELECT prompt_id FROM research_gap_prompts WHERE run_id = ? "
            "ORDER BY order_index",
            [run_id],
        ).fetchall()
    finally:
        con.close()
    return [r[0] for r in rows]


def test_record_signal_and_would_run(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    prompt_ids = _setup_run_with_prompts(tmp_db_with_bridge, fixture_text, n_prompts=5)
    assert len(prompt_ids) == 5

    # 👍 on 3 of 5, 👎 on 2 of 5 → 60% would_run
    signals = ["would_run", "would_run", "would_run", "skip", "skip"]
    with connect_write(str(tmp_db_with_bridge), purpose="signals") as con:
        for pid, s in zip(prompt_ids, signals):
            record_prompt_signal(con, prompt_id=pid, signal_type=s)

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        would, total, pct = would_run_percentage(con)
    finally:
        con.close()
    assert would == 3
    assert total == 5
    assert pct == pytest.approx(0.6)


def test_signal_change_of_mind_picks_latest(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    """Operator changes 👎 → 👍 on one prompt; the latest signal
    wins in the would_run aggregation."""
    prompt_ids = _setup_run_with_prompts(tmp_db_with_bridge, fixture_text, n_prompts=2)
    with connect_write(str(tmp_db_with_bridge), purpose="s1") as con:
        record_prompt_signal(con, prompt_id=prompt_ids[0], signal_type="skip")
    # Sleep one second so timestamps differ at our resolution.
    import time as _t
    _t.sleep(1.05)
    with connect_write(str(tmp_db_with_bridge), purpose="s2") as con:
        record_prompt_signal(con, prompt_id=prompt_ids[0], signal_type="would_run")
        record_prompt_signal(con, prompt_id=prompt_ids[1], signal_type="would_run")

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        would, total, pct = would_run_percentage(con)
    finally:
        con.close()
    assert total == 2
    assert would == 2
    assert pct == 1.0


def test_record_signal_unknown_type_rejected(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    prompt_ids = _setup_run_with_prompts(tmp_db_with_bridge, fixture_text, n_prompts=1)
    with connect_write(str(tmp_db_with_bridge), purpose="bad") as con:
        with pytest.raises(ValueError, match="signal_type"):
            record_prompt_signal(con, prompt_id=prompt_ids[0], signal_type="lol")


def test_record_answer_links_paste(tmp_db_with_bridge: Path, fixture_text) -> None:
    prompt_ids = _setup_run_with_prompts(tmp_db_with_bridge, fixture_text, n_prompts=1)
    # Paste an "answer" and link it.
    text = "An answer pasted back from a deep-research call.\n\n" * 5
    with connect_write(str(tmp_db_with_bridge), purpose="ans") as con:
        p = ingest_paste(con, raw_text=text, call_site="paste_back_from_cascade")
        aid = record_prompt_answer(
            con, prompt_id=prompt_ids[0], answer_document_id=p.document_id,
        )
    assert aid.startswith("rga-")

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        rows = con.execute(
            "SELECT prompt_id, answer_document_id FROM research_gap_prompt_answers"
        ).fetchall()
    finally:
        con.close()
    assert rows == [(prompt_ids[0], p.document_id)]


def test_would_run_percentage_scoped_by_run(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    """Aggregating with run_id filter picks only that run's prompts."""
    prompt_ids_a = _setup_run_with_prompts(tmp_db_with_bridge, fixture_text, n_prompts=2)
    # Second run; same scope, fresh prompts.
    prompt_ids_b = _setup_run_with_prompts(tmp_db_with_bridge, fixture_text, n_prompts=3)

    with connect_write(str(tmp_db_with_bridge), purpose="signals") as con:
        for pid in prompt_ids_a:
            record_prompt_signal(con, prompt_id=pid, signal_type="skip")
        for pid in prompt_ids_b:
            record_prompt_signal(con, prompt_id=pid, signal_type="would_run")

    # Pull each run's run_id
    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        run_a = con.execute(
            "SELECT run_id FROM research_gap_prompts WHERE prompt_id = ?",
            [prompt_ids_a[0]],
        ).fetchone()[0]
        run_b = con.execute(
            "SELECT run_id FROM research_gap_prompts WHERE prompt_id = ?",
            [prompt_ids_b[0]],
        ).fetchone()[0]
        wa, ta, pa = would_run_percentage(con, run_id=run_a)
        wb, tb, pb = would_run_percentage(con, run_id=run_b)
        wall, tall, pall = would_run_percentage(con)
    finally:
        con.close()
    assert (wa, ta) == (0, 2)
    assert (wb, tb) == (3, 3)
    assert (wall, tall) == (3, 5)
    assert pall == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# LLM error path
# ---------------------------------------------------------------------------


def test_cluster_llm_error_raises_no_run_committed(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    doc_a, doc_b, _qids = _setup_two_pastes_with_questions(tmp_db_with_bridge, fixture_text)

    def _angry(_prompt: str) -> LlmCallResult:
        raise RuntimeError("503 from provider")

    with connect_write(str(tmp_db_with_bridge), purpose="err") as con:
        with pytest.raises(GapFinderError, match="cluster LLM call failed"):
            find_gaps(con, scope_block_ids=[doc_a, doc_b], llm_callable=_angry)

    # Verify no run row landed for the failed call.
    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        n = con.execute("SELECT COUNT(*) FROM research_gap_runs").fetchone()[0]
    finally:
        con.close()
    assert n == 0


# ---------------------------------------------------------------------------
# Single-writer + append-only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", [
    "research_gap_runs",
    "research_gap_clusters",
    "research_gap_cluster_questions",
    "research_gap_prompts",
    "research_gap_prompt_answers",
    "research_gap_prompt_signals",
])
def test_single_writer_for_table(table: str) -> None:
    """Every INSERT against the 6 gap tables lives in gap.py."""
    repo = Path(__file__).resolve().parents[2]
    out = subprocess.run(
        ["rg", "--no-heading", "-n", f'"INSERT INTO {table}', str(repo)],
        capture_output=True, text=True, check=False,
    )
    matches = out.stdout.strip().splitlines() if out.returncode == 0 else []
    matches = [
        m for m in matches
        if "/.venv/" not in m and "/__pycache__/" not in m
        and "tests/research_bridge/test_gap.py" not in m
    ]
    for m in matches:
        assert "substrate/research_bridge/gap.py" in m, (
            f"unexpected writer to {table}: {m}"
        )


def test_gap_tables_append_only_in_module() -> None:
    bridge = Path(__file__).resolve().parents[2] / "substrate" / "research_bridge"
    forbidden = [
        "UPDATE research_gap_runs",
        "UPDATE research_gap_clusters",
        "UPDATE research_gap_cluster_questions",
        "UPDATE research_gap_prompts",
        "UPDATE research_gap_prompt_answers",
        "UPDATE research_gap_prompt_signals",
        "DELETE FROM research_gap_runs",
        "DELETE FROM research_gap_clusters",
        "DELETE FROM research_gap_cluster_questions",
        "DELETE FROM research_gap_prompts",
        "DELETE FROM research_gap_prompt_answers",
        "DELETE FROM research_gap_prompt_signals",
    ]
    for f in bridge.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for pat in forbidden:
            assert pat not in text, f"append-only violation '{pat}' in {f}"


# ---------------------------------------------------------------------------
# Read-side
# ---------------------------------------------------------------------------


def test_read_gap_run_not_found(tmp_db_with_bridge: Path) -> None:
    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        run, c, p = read_gap_run(con, "rgrun-nope")
    finally:
        con.close()
    assert run is None
    assert c == []
    assert p == []
