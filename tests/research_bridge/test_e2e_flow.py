"""End-to-end flow test for the Deep Research Bridge.

This is the integration proof the per-layer unit tests cannot give:
that the output of each sprint actually feeds the input of the next,
driven through the REAL FastAPI app + the REAL CLI against ONE DuckDB
file — exactly as the operator drives it.

The journey under test (the canonical operator path):

    detect-preview            (SPR-01 — see the source before commit)
      → paste x2              (SPR-01 — two real provider fixtures)
      → extract x2            (SPR-02 — insights + open questions)
      → insights in /blocks/search   (SPR-04 — node promotion seam)
      → /items returns them   (SPR-02 read seam)
      → find-gaps             (SPR-05 — cluster + cascade over the
                               questions the extractor produced)
      → 👍/👎 signals          (SPR-05 — the S3 substrate)
      → paste-back an answer  (SPR-05 — loop closure: answer ingests,
                               links to the prompt, extracts, lands new
                               open questions)
      → re-find-gaps          (SPR-05 — new run sees the larger scope)
      → dogfood-report (CLI)  (SPR-06 — metrics over the same DB)

Every assertion proves a seam between two sprints. The single LLM
stub routes by prompt shape — extraction prompts carry the INPUT
delimiter, cluster prompts carry "Open questions (", cascade prompts
carry "Clusters (" — so one fake stands in for all three model
calls without burning credits.

If this test ever goes red, the product is broken as a *system* even
if every unit test stays green. That's the whole point of it.
"""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Iterator

import duckdb
import pytest
from fastapi.testclient import TestClient

from substrate.research_bridge import LlmCallResult


@pytest.fixture
def e2e_env(tmp_path: Path) -> Iterator[Path]:
    """One DuckDB file shared by the API app AND the CLI, so the test
    drives both surfaces against identical state."""
    db = tmp_path / "e2e.duckdb"
    os.environ["ANTIEK_DUCKDB_PATH"] = str(db)
    from substrate.graph import init_database_at_path
    from substrate.research_bridge import init_research_bridge_at_path
    init_database_at_path(str(db))
    init_research_bridge_at_path(str(db))
    yield db
    del os.environ["ANTIEK_DUCKDB_PATH"]


def _content_routed_llm(extraction_by_quote: dict[str, dict]):
    """Build a dispatch-shaped LLM fake that routes by prompt shape.

    - Extraction calls (contain '<<<INPUT>>>'): emit insights +
      open_questions whose quotes are substrings of the pasted text.
      We pick which payload by detecting a stable phrase from the
      input — so the right fixture gets the right extraction.
    - Cluster calls (contain 'Open questions ('): group every
      provided question id into one cluster.
    - Cascade calls (contain 'Clusters ('): emit one grounded prompt
      for the cluster, with the placeholder cluster_id replaced by
      the real one parsed from the rendered prompt.
    """
    import re

    def _call(prompt: str) -> LlmCallResult:
        if "<<<INPUT>>>" in prompt:
            for needle, payload in extraction_by_quote.items():
                if needle in prompt:
                    return LlmCallResult(
                        text=json.dumps(payload),
                        input_tokens=200, output_tokens=60, cost_usd=0.003,
                        model_id="fake/extractor",
                    )
            return LlmCallResult(
                text='{"insights": [], "open_questions": []}', model_id="fake/extractor",
            )
        if "Open questions (" in prompt:
            qids = re.findall(r"\brpoq-[a-f0-9]+\b", prompt)
            qids = list(dict.fromkeys(qids))  # dedupe, preserve order
            return LlmCallResult(
                text=json.dumps({"clusters": [{
                    "label": "Verifier productisation timeline",
                    "rationale": "All open questions converge on verifier shipping.",
                    "priority_rank": 0, "question_ids": qids,
                }]}),
                input_tokens=300, output_tokens=70, cost_usd=0.004,
                model_id="fake/cluster",
            )
        if "Clusters (" in prompt:
            m = re.search(r"cluster_id:\s*(rgcl-[a-f0-9]+)", prompt)
            cluster_id = m.group(1) if m else "rgcl-unknown"
            return LlmCallResult(
                text=json.dumps({"prompts": [{
                    "cluster_id": cluster_id, "order_index": 0,
                    "prompt_text": (
                        "Investigate the verifier productisation timeline: have "
                        "any of the 2024 verifier papers shipped as a product in Q1 2025?"
                    ),
                    "target_provider": "anthropic",
                    "expected_output_shape": "List of products + dates",
                    "depends_on_prior_order_index": None,
                    "rationale": "Anthropic deep-research tracks verifier launches best.",
                }]}),
                input_tokens=400, output_tokens=90, cost_usd=0.006,
                model_id="fake/cascade",
            )
        return LlmCallResult(text='{"insights": [], "open_questions": []}', model_id="fake")

    return _call


def _run_cli(argv: list[str], stdin_text: str = "") -> tuple[int, str, str]:
    import sys
    from tools.research_bridge_cli.main import main
    old = sys.stdin
    sys.stdin = io.StringIO(stdin_text)
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    except SystemExit as e:
        code = int(e.code) if e.code is not None else 0
    finally:
        sys.stdin = old
    return code, out.getvalue(), err.getvalue()


def test_full_operator_journey(e2e_env: Path, fixture_text, monkeypatch) -> None:
    # The two pastes + the verbatim quotes the stubbed extractor will
    # return for each (must be exact substrings of the fixtures).
    anthropic_text = fixture_text("anthropic")
    alphasense_text = fixture_text("alphasense")

    a_ins_quote = "Prime Intellect is the named incumbent at the substrate layer."
    a_q_quote = "Anthropic-internal verifier work has appeared in three 2024 papers but has not been productised"
    s_ins_quote = "Goldman Sachs (Buy, PT $72)"
    s_q_quote = "management indicated they will disclose Compute Marketplace customer commitments."
    assert a_ins_quote in anthropic_text and a_q_quote in anthropic_text
    assert s_ins_quote in alphasense_text and s_q_quote in alphasense_text

    extraction_map = {
        # routed by a stable phrase unique to each fixture's INPUT block
        "settled into a recognisable three-layer structure": {
            "insights": [{"summary": "Prime Intellect leads the substrate layer",
                          "quote": a_ins_quote, "llm_confidence": 0.9}],
            "open_questions": [{"summary": "When does Anthropic ship its internal verifier as a product?",
                                "quote": a_q_quote, "llm_confidence": 0.86}],
        },
        "Q3 2024 Earnings Call Analysis": {
            "insights": [{"summary": "Goldman rates PRIM Buy with a $72 price target",
                          "quote": s_ins_quote, "llm_confidence": 0.88}],
            "open_questions": [{"summary": "Will Compute Marketplace customer commitments materialize?",
                                "quote": s_q_quote, "llm_confidence": 0.84}],
        },
    }
    fake = _content_routed_llm(extraction_map)

    # Patch the dispatch factory at BOTH the API route module and the
    # llm_dispatch module so whichever path the code takes uses the fake.
    import interfaces.research.api.research_bridge as bridge_routes
    import substrate.research_bridge.llm_dispatch as llm_dispatch
    monkeypatch.setattr(bridge_routes, "build_dispatch_llm_callable", lambda: fake)
    monkeypatch.setattr(llm_dispatch, "build_dispatch_llm_callable", lambda: fake)

    from interfaces.research.api.app import create_app
    app = create_app(register_providers=False, register_wrestling=False)
    client = TestClient(app)

    # ---- 1. detect-preview agrees before we commit (SPR-01) ----
    d = client.post("/research/detect", json={"raw_text": anthropic_text})
    assert d.status_code == 200
    assert d.json()["source"] == "anthropic"

    # ---- 2. paste both (SPR-01) ----
    pa = client.post("/research/pastes", json={
        "raw_text": anthropic_text, "operator_label": "PI substrate", "session_id": "S-e2e",
    })
    assert pa.status_code == 201
    doc_a = pa.json()["document_id"]
    assert pa.json()["source"] == "anthropic"

    ps = client.post("/research/pastes", json={
        "raw_text": alphasense_text, "operator_label": "PRIM Q3", "session_id": "S-e2e",
    })
    assert ps.status_code == 201
    doc_s = ps.json()["document_id"]
    assert ps.json()["source"] == "alphasense"

    # both visible under the session filter
    listed = client.get("/research/pastes?session_id=S-e2e").json()
    assert listed["count"] == 2

    # ---- 3. extract from both (SPR-02) ----
    ea = client.post(f"/research/pastes/{doc_a}/extract", json={})
    assert ea.status_code == 200
    assert ea.json()["status"] == "ok"
    assert len(ea.json()["insights"]) == 1
    assert len(ea.json()["open_questions"]) == 1

    es = client.post(f"/research/pastes/{doc_s}/extract", json={})
    assert es.status_code == 200
    assert len(es.json()["open_questions"]) == 1

    # ---- 4. insight promoted to a node, visible to /blocks/search (SPR-04) ----
    db_path = os.environ["ANTIEK_DUCKDB_PATH"]
    con = duckdb.connect(db_path, read_only=True)
    try:
        node_hits = con.execute(
            "SELECT canonical_label FROM nodes WHERE canonical_label ILIKE ?",
            ["%substrate layer%"],
        ).fetchall()
    finally:
        con.close()
    assert any("Prime Intellect leads" in r[0] for r in node_hits), (
        "SPR-04 seam broken: extracted insight did not land as a searchable node"
    )

    # ---- 5. /items read seam (SPR-02) ----
    items = client.get(f"/research/pastes/{doc_a}/items").json()
    assert len(items["insights"]) == 1
    assert len(items["open_questions"]) == 1
    q_summary_a = items["open_questions"][0]["summary"]

    # ---- 6. find-gaps over both pastes (SPR-05) ----
    fg = client.post("/research/gaps", json={
        "scope_block_ids": [doc_a, doc_s],
        "operator_label": "e2e run", "session_id": "S-e2e",
    })
    assert fg.status_code == 201, fg.text
    run = fg.json()
    assert len(run["clusters"]) == 1
    assert len(run["prompts"]) == 1, "cascade did not produce a grounded prompt"
    prompt_id = run["prompts"][0]["prompt_id"]
    assert run["prompts"][0]["target_provider"] == "anthropic"
    # the run scoped BOTH questions the extractor produced
    assert len(run["run"]["scope_question_ids"]) == 2

    # ---- 7. signal the prompt 👍 (SPR-05 S3 substrate) ----
    sig = client.post(f"/research/gaps/prompts/{prompt_id}/signal",
                      json={"signal_type": "would_run"})
    assert sig.status_code == 201
    pct = client.get("/research/gaps/signals/percentage").json()
    assert pct["would_run_count"] == 1
    assert pct["total_signalled"] == 1

    # ---- 8. paste-back an answer → links + extracts (SPR-05 loop closure) ----
    answer_text = (
        "Anthropic shipped VerifyKit on 2025-01-15, productising the three "
        "2024 verifier papers. Prime Intellect remains the substrate incumbent.\n\n"
        "An open thread: does VerifyKit compress PRIM's verifier-licensing revenue?\n"
    ) * 3
    ab = client.post("/research/pastes", json={
        "raw_text": answer_text, "source_override": "anthropic", "session_id": "S-e2e",
    })
    answer_doc = ab.json()["document_id"]
    link = client.post(f"/research/gaps/prompts/{prompt_id}/answer",
                       json={"answer_document_id": answer_doc})
    assert link.status_code == 201
    assert link.json()["answer_id"].startswith("rga-")

    # extract the answer so the next find-gaps can see its questions
    quote = "does VerifyKit compress PRIM's verifier-licensing revenue?"
    assert quote in answer_text
    extraction_map["VerifyKit on 2025-01-15"] = {
        "insights": [],
        "open_questions": [{"summary": "Does VerifyKit compress PRIM's verifier-licensing revenue?",
                            "quote": quote, "llm_confidence": 0.8}],
    }
    ea2 = client.post(f"/research/pastes/{answer_doc}/extract", json={})
    assert ea2.status_code == 200
    assert len(ea2.json()["open_questions"]) == 1

    # ---- 9. re-find-gaps sees the larger scope (SPR-05) ----
    fg2 = client.post("/research/gaps", json={
        "scope_block_ids": [doc_a, doc_s, answer_doc], "session_id": "S-e2e",
    })
    assert fg2.status_code == 201
    run2 = fg2.json()
    assert run2["run"]["run_id"] != run["run"]["run_id"], "re-run must be a new immutable run"
    assert len(run2["run"]["scope_question_ids"]) == 3, "new paste's question not in scope"

    # both runs are preserved (audit)
    runs = client.get("/research/gaps?session_id=S-e2e").json()
    assert runs["count"] == 2

    # ---- 10. dogfood-report over the SAME db, via the CLI (SPR-06) ----
    code, out, _ = _run_cli(["dogfood-report", "--json"])
    assert code == 0
    report = json.loads(out)
    assert report["n_pastes"] == 3
    assert report["n_gap_runs"] == 2
    assert report["total_signalled"] == 1
    assert report["would_run_count"] == 1
    # S3 gate: 1/1 = 100% ≥ 60% floor
    assert report["s3_gate_passed"] is True
    # extraction cost accrued across the three extract calls
    assert report["extraction_cost_usd"] > 0
    assert report["gap_cost_usd"] > 0

    # sanity: the human-readable report renders the PASS banner
    code, human, _ = _run_cli(["dogfood-report"])
    assert code == 0
    assert "S3 gate — PASS" in human
    assert "Total pastes: **3**" in human


def test_paste_back_question_threads_into_next_run(e2e_env: Path, fixture_text, monkeypatch) -> None:
    """Tighter seam assertion: a question extracted from a pasted-back
    answer is a NEW question id that the re-run's cluster step
    actually receives. Guards against the loop silently dropping the
    new evidence."""
    anthropic_text = fixture_text("anthropic")
    a_q_quote = "Anthropic-internal verifier work has appeared in three 2024 papers but has not been productised"
    extraction_map = {
        "settled into a recognisable three-layer structure": {
            "insights": [],
            "open_questions": [{"summary": "When does Anthropic ship its internal verifier?",
                                "quote": a_q_quote, "llm_confidence": 0.86}],
        },
    }
    fake = _content_routed_llm(extraction_map)
    import interfaces.research.api.research_bridge as bridge_routes
    import substrate.research_bridge.llm_dispatch as llm_dispatch
    monkeypatch.setattr(bridge_routes, "build_dispatch_llm_callable", lambda: fake)
    monkeypatch.setattr(llm_dispatch, "build_dispatch_llm_callable", lambda: fake)

    from interfaces.research.api.app import create_app
    client = TestClient(create_app(register_providers=False, register_wrestling=False))

    doc = client.post("/research/pastes", json={"raw_text": anthropic_text}).json()["document_id"]
    client.post(f"/research/pastes/{doc}/extract", json={})
    run1 = client.post("/research/gaps", json={"scope_block_ids": [doc]}).json()
    assert len(run1["run"]["scope_question_ids"]) == 1
    first_qids = set(run1["run"]["scope_question_ids"])

    # Paste back a NEW answer with a distinct question.
    ans = "Open question: will the verifier-licensing line compress in 2026?\n\n" * 4
    quote = "will the verifier-licensing line compress in 2026?"
    extraction_map["verifier-licensing line compress in 2026"] = {
        "insights": [],
        "open_questions": [{"summary": "Will verifier-licensing revenue compress in 2026?",
                            "quote": quote, "llm_confidence": 0.8}],
    }
    ans_doc = client.post("/research/pastes",
                          json={"raw_text": ans, "source_override": "anthropic"}).json()["document_id"]
    client.post(f"/research/pastes/{ans_doc}/extract", json={})

    run2 = client.post("/research/gaps", json={"scope_block_ids": [doc, ans_doc]}).json()
    second_qids = set(run2["run"]["scope_question_ids"])
    assert len(second_qids) == 2
    # the new question id is genuinely new, not a re-use of the first
    assert first_qids.issubset(second_qids)
    assert len(second_qids - first_qids) == 1
