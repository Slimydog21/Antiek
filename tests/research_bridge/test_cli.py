"""CLI integration tests.

Verifies the four subcommands work end-to-end against a tmp DB.
``ANTIEK_DUCKDB_PATH`` redirects the CLI's path resolver at a
test-owned DB; no operator-state pollution.
"""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture
def cli_env(tmp_path: Path) -> Iterator[Path]:
    db = tmp_path / "cli.duckdb"
    os.environ["ANTIEK_DUCKDB_PATH"] = str(db)
    # Pre-init so first CLI call doesn't have to do the dance.
    from substrate.graph import init_database_at_path
    from substrate.research_bridge import init_research_bridge_at_path

    init_database_at_path(str(db))
    init_research_bridge_at_path(str(db))
    yield db
    del os.environ["ANTIEK_DUCKDB_PATH"]


def _run_cli(argv: list[str], stdin_text: str = "") -> tuple[int, str, str]:
    """Run the CLI in-process. Returns (exit_code, stdout, stderr)."""
    import sys
    from tools.research_bridge_cli.main import main

    old_stdin = sys.stdin
    sys.stdin = io.StringIO(stdin_text)
    out = io.StringIO()
    err = io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    except SystemExit as e:
        code = int(e.code) if e.code is not None else 0
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue(), err.getvalue()


def test_cli_paste_and_list(cli_env: Path, fixture_text) -> None:
    text = fixture_text("anthropic")
    code, out, err = _run_cli(
        ["paste", "--label", "from-cli", "--json"], stdin_text=text,
    )
    assert code == 0, f"err={err!r} out={out!r}"
    payload = json.loads(out)
    assert payload["source"] == "anthropic"
    doc_id = payload["document_id"]

    # list returns the new paste
    code, out, _ = _run_cli(["list", "--json"], stdin_text="")
    assert code == 0
    rows = json.loads(out)
    assert any(r["document_id"] == doc_id for r in rows)


def test_cli_show_with_raw(cli_env: Path, fixture_text) -> None:
    text = fixture_text("alphasense")
    code, out, _ = _run_cli(["paste", "--json"], stdin_text=text)
    assert code == 0
    doc_id = json.loads(out)["document_id"]

    code, out, err = _run_cli(["show", doc_id, "--json"], stdin_text="")
    assert code == 0, f"err={err}"
    detail = json.loads(out)
    assert detail["source"] == "alphasense"
    assert detail["raw_text"] == text
    assert len(detail["events"]) >= 1


def test_cli_show_not_found(cli_env: Path) -> None:
    code, _, err = _run_cli(["show", "doc-doesnotexist"], stdin_text="")
    assert code == 4
    assert "not found" in err


def test_cli_paste_empty_stdin(cli_env: Path) -> None:
    code, _, err = _run_cli(["paste"], stdin_text="    ")
    assert code == 3
    assert "empty" in err.lower()


def test_cli_detect_does_not_write(cli_env: Path, fixture_text) -> None:
    text = fixture_text("grok")
    code, out, _ = _run_cli(["detect", "--json"], stdin_text=text)
    assert code == 0
    payload = json.loads(out)
    assert payload["source"] == "grok"

    # List is empty — detect did not write.
    code, out, _ = _run_cli(["list", "--json"], stdin_text="")
    assert code == 0
    assert json.loads(out) == []


def test_cli_paste_unknown_override_rejected(cli_env: Path, fixture_text) -> None:
    """Argparse rejects unknown choices with exit code 2 (SystemExit)."""
    code, _, err = _run_cli(
        ["paste", "--source-override", "definitely_unknown"],
        stdin_text=fixture_text("anthropic"),
    )
    # argparse exits 2 on invalid choice.
    assert code == 2


# ---------------------------------------------------------------------------
# extract + eval-precision (SPR-02)
# ---------------------------------------------------------------------------


def _patch_dispatch_with_fake(monkeypatch, response_text: str) -> None:
    """Patch the dispatch factory so the CLI extract command uses a fake LLM."""
    from substrate.research_bridge import LlmCallResult
    import substrate.research_bridge.llm_dispatch as llm_dispatch
    import tools.research_bridge_cli.main as cli_main

    def _factory():
        def _call(_prompt: str) -> LlmCallResult:
            return LlmCallResult(
                text=response_text,
                input_tokens=42, output_tokens=12, cost_usd=0.001,
                model_id="fake/test-model",
            )
        return _call

    monkeypatch.setattr(llm_dispatch, "build_dispatch_llm_callable", _factory)
    # Also patch the local import in cli_main (the function was
    # imported at call-time inside _cmd_extract, so the monkeypatch
    # on llm_dispatch suffices for that call path).


def test_cli_extract_happy_path(cli_env: Path, fixture_text, monkeypatch) -> None:
    text = fixture_text("anthropic")
    code, out, _ = _run_cli(["paste", "--json"], stdin_text=text)
    assert code == 0
    doc_id = json.loads(out)["document_id"]

    import json as _json
    quote = "Prime Intellect is the named incumbent at the substrate layer."
    _patch_dispatch_with_fake(monkeypatch, _json.dumps({
        "insights": [{"summary": "PI lead", "quote": quote,
                      "llm_confidence": 0.9}],
        "open_questions": [],
    }))

    code, out, err = _run_cli(["extract", doc_id, "--json"], stdin_text="")
    assert code == 0, f"err={err}"
    payload = _json.loads(out)
    assert payload["status"] == "ok"
    assert len(payload["insights"]) == 1
    assert payload["insights"][0]["summary"] == "PI lead"


def test_cli_extract_unknown_doc(cli_env: Path, monkeypatch) -> None:
    _patch_dispatch_with_fake(
        monkeypatch, '{"insights": [], "open_questions": []}'
    )
    code, _, err = _run_cli(["extract", "doc-deadbeef"], stdin_text="")
    assert code == 4
    assert "not found" in err.lower()


def test_cli_eval_precision_missing_file(cli_env: Path, tmp_path: Path) -> None:
    code, _, err = _run_cli(
        ["eval-precision", "--labels", str(tmp_path / "nope.yaml")],
        stdin_text="",
    )
    assert code == 4
    assert "not found" in err.lower()


def _patch_dispatch_sequence(monkeypatch, responses: list) -> None:
    """Patch the dispatch LLM factory to return a sequence of canned
    responses. The CLI find_gaps path will consume two (cluster +
    cascade)."""
    from substrate.research_bridge import LlmCallResult
    import substrate.research_bridge.llm_dispatch as llm_dispatch

    state = {"i": 0}

    def _factory():
        def _call(prompt: str) -> LlmCallResult:
            i = state["i"]
            state["i"] = i + 1
            if i >= len(responses):
                return LlmCallResult(text='{"prompts": []}', model_id="fake")
            r = responses[i]
            text = r.get("text", "")
            if "__placeholder__" in text:
                import re
                m = re.search(r"cluster_id:\s*(rgcl-[a-f0-9]+)", prompt)
                if m:
                    text = text.replace("__placeholder__", m.group(1))
            return LlmCallResult(
                text=text,
                input_tokens=r.get("input_tokens", 0),
                output_tokens=r.get("output_tokens", 0),
                cost_usd=r.get("cost_usd", 0.0),
                model_id=r.get("model_id", "fake"),
            )
        return _call

    monkeypatch.setattr(llm_dispatch, "build_dispatch_llm_callable", _factory)


def _ingest_and_extract_via_cli(monkeypatch, source: str, fixture_text) -> str:
    """Helper: paste a fixture + extract one open question via CLI.
    Returns the document_id."""
    text = fixture_text(source)
    code, out, _ = _run_cli(["paste", "--json"], stdin_text=text)
    assert code == 0
    doc_id = json.loads(out)["document_id"]

    if source == "anthropic":
        quote = "Anthropic-internal verifier work has appeared in three 2024 papers but has not been productised"
        summary = "Will Anthropic ship internal verifier as product"
    elif source == "alphasense":
        quote = "management indicated they will disclose Compute Marketplace customer commitments."
        summary = "Will compute marketplace customer commitments materialize"
    else:
        raise ValueError(f"unhandled fixture source {source!r}")

    _patch_dispatch_with_fake(monkeypatch, json.dumps({
        "insights": [],
        "open_questions": [{"summary": summary, "quote": quote,
                            "llm_confidence": 0.9}],
    }))
    code, _, _ = _run_cli(["extract", doc_id], stdin_text="")
    assert code == 0
    return doc_id


def test_cli_find_gaps_happy_path(
    cli_env: Path, fixture_text, monkeypatch
) -> None:
    doc_a = _ingest_and_extract_via_cli(monkeypatch, "anthropic", fixture_text)
    doc_b = _ingest_and_extract_via_cli(monkeypatch, "alphasense", fixture_text)

    # Read the actual question_ids we just extracted.
    import duckdb
    db_path = os.environ["ANTIEK_DUCKDB_PATH"]
    con = duckdb.connect(db_path, read_only=True)
    try:
        qids = [
            row[0] for row in con.execute(
                "SELECT question_id FROM research_paste_open_questions "
                "WHERE document_id IN (?, ?)",
                [doc_a, doc_b],
            ).fetchall()
        ]
    finally:
        con.close()
    assert len(qids) == 2

    _patch_dispatch_sequence(monkeypatch, [
        {"text": json.dumps({"clusters": [{
            "label": "Verifier productisation timeline",
            "priority_rank": 0,
            "question_ids": qids,
        }]}), "input_tokens": 100, "output_tokens": 30, "cost_usd": 0.001,
         "model_id": "fake/cluster"},
        {"text": json.dumps({"prompts": [{
            "cluster_id": "__placeholder__",
            "order_index": 0,
            "prompt_text": "Verifier productisation status check for Q1 2025",
            "target_provider": "anthropic",
            "rationale": "x",
        }]}), "input_tokens": 200, "output_tokens": 50, "cost_usd": 0.003,
         "model_id": "fake/cascade"},
    ])
    code, out, err = _run_cli(
        ["find-gaps", doc_a, doc_b, "--label", "cli test", "--json"],
        stdin_text="",
    )
    assert code == 0, err
    payload = json.loads(out)
    assert len(payload["clusters"]) == 1
    assert len(payload["prompts"]) == 1
    run_id = payload["run_id"]

    # Show
    code, out, _ = _run_cli(["gaps-show", run_id, "--json"], stdin_text="")
    assert code == 0
    show = json.loads(out)
    assert show["run_id"] == run_id
    assert len(show["prompts"]) == 1
    prompt_id = show["prompts"][0]["prompt_id"]

    # Signal would_run; check the would-run helper.
    code, _, _ = _run_cli(
        ["signal", prompt_id, "--type", "would_run"], stdin_text="",
    )
    assert code == 0
    code, out, _ = _run_cli(["would-run", "--json"], stdin_text="")
    assert code == 0
    body = json.loads(out)
    assert body["would_run_count"] == 1
    assert body["total_signalled"] == 1
    assert body["percentage"] == 1.0


def test_cli_gaps_show_not_found(cli_env: Path) -> None:
    code, _, err = _run_cli(["gaps-show", "rgrun-nope"], stdin_text="")
    assert code == 4
    assert "not found" in err.lower()


def test_cli_signal_bad_type(cli_env: Path) -> None:
    # argparse rejects with exit 2
    code, _, _ = _run_cli(
        ["signal", "rgpr-fake", "--type", "lol"], stdin_text="",
    )
    assert code == 2


def test_cli_eval_precision_perfect_match(
    cli_env: Path, fixture_text, monkeypatch, tmp_path: Path
) -> None:
    text = fixture_text("alphasense")
    code, out, _ = _run_cli(["paste", "--json"], stdin_text=text)
    doc_id = json.loads(out)["document_id"]

    # Extract via fake LLM with two known-substring items.
    import json as _json
    quote_ins = "Buy / Hold / Sell consensus (sell-side): 9 Buy / 4 Hold / 1 Sell."
    quote_q = "Will Compute Marketplace customer commitments materialize"  # NOT in text
    # Make the labelled-question match work via SubstringJudge over
    # known summaries — we pick an extracted question whose summary
    # equals the labelled summary.
    extracted_q_summary = "Will compute marketplace land"
    _patch_dispatch_with_fake(monkeypatch, _json.dumps({
        "insights": [{"summary": "Mixed consensus", "quote": quote_ins,
                      "llm_confidence": 0.9}],
        "open_questions": [],
    }))
    code, _, _ = _run_cli(["extract", doc_id], stdin_text="")
    assert code == 0

    # Labels file: extracted "Mixed consensus" vs labelled "Mixed consensus"
    labels_file = tmp_path / "labels.yaml"
    labels_file.write_text(
        f"""
pastes:
  - document_id: {doc_id}
    operator_label: test
    expected_insights:
      - "Mixed consensus"
    expected_open_questions: []
""",
        encoding="utf-8",
    )

    code, out, err = _run_cli(
        ["eval-precision", "--labels", str(labels_file), "--json"],
        stdin_text="",
    )
    # Aggregate question precision is 0 (no extracted nor labelled
    # questions), so the gate predicate returns False → exit 6. But
    # insights precision should be 1.0.
    payload = _json.loads(out)
    assert payload["aggregate"]["insight_precision"] == 1.0
    # No questions either side → question_precision = 0.0 → S3 gate fails.
    assert payload["aggregate"]["s3_gate_passed"] is False
    assert code == 6
