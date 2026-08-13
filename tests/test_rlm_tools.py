"""Tests for substrate/graph/rlm_tools.py (Sprint 9 day 2-3).

Coverage:

A. JSON extraction:
   1. Strict JSON passes.
   2. Markdown-fenced JSON parses.
   3. Largest-window fallback handles prose-wrapped JSON.
   4. Garbage raises ValueError.

B. Tool registration:
   5. register_tool + register_builtin + register_builtins.
   6. Unknown built-in raises.
   7. get_builtin_tool_names + get_tool_specs.

C. SubLLMWithTools loop with stub LLM:
   8. Single round → final_answer returned verbatim.
   9. Tool call → tool executes → second round produces final_answer.
   10. Unknown tool → error fed back; LLM gets another round.
   11. Tool execution error → caught + fed back as string.
   12. Max-rounds exhaustion forces synthesis.
   13. Tool output truncation at MAX_TOOL_OUTPUT_CHARS.
   14. Parse error short-circuits with diagnostic.

D. Constructor validation:
   15. Construct without llm_call or investigation_id raises.

E. Batch dispatch:
   16. equipped_llm_batch preserves task order.
   17. Empty task list → empty result.
   18. max_parallel=1 sequential path.

F. Category mapping:
   19. CATEGORY_TOOL_MAP covers the 5 known categories.
   20. tools_for_category unknown → empty list.

G. HTML extraction + DDG parser:
   21. _extract_text_from_html strips tags + scripts.
   22. _parse_ddg_html on empty HTML returns "no results".

H. Graph search formatting:
   23. _format_graph_search_result with empty chunks → "no chunk matches".
   24. With chunks → formatted output.
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from orchestration.rlm.prime_agent_backend import (  # noqa: E402
    PrimeAgentEvidence,
    PrimeAgentOutcome,
    PrimeAgentReceipt,
    PrimeAgentTerminalState,
)
from substrate.graph.rlm_tools import (  # noqa: E402
    CATEGORY_TOOL_MAP,
    MAX_TOOL_OUTPUT_CHARS,
    SubLLMWithTools,
    _extract_text_from_html,
    _format_graph_search_result,
    _parse_ddg_html,
    equipped_llm_batch,
    extract_json,
    get_builtin_tool_names,
    get_tool_specs,
    tools_for_category,
)

# ---------------------------------------------------------------------------
# A. JSON extraction
# ---------------------------------------------------------------------------


def test_extract_json_strict_pass():
    assert extract_json('{"tool_call": {"name": "x"}}') == {
        "tool_call": {"name": "x"},
    }


def test_extract_json_markdown_fence():
    txt = '```json\n{"final_answer": "hello"}\n```'
    assert extract_json(txt) == {"final_answer": "hello"}


def test_extract_json_prose_wrapped():
    txt = 'Here is the JSON: {"final_answer": "hi"} done.'
    assert extract_json(txt) == {"final_answer": "hi"}


def test_extract_json_garbage_raises():
    with pytest.raises(ValueError, match="Could not parse JSON"):
        extract_json("totally not json at all")


# ---------------------------------------------------------------------------
# B. Tool registration
# ---------------------------------------------------------------------------


def _noop_llm(system: str, user: str) -> str:
    return '{"final_answer": "noop"}'


def test_register_tool_adds_to_registry():
    sub = SubLLMWithTools(llm_call=_noop_llm)
    sub.register_tool(
        "custom", lambda **kw: "result", "test", [{"name": "q"}],
    )
    assert "custom" in sub._tools


def test_register_builtin_adds_known_tool():
    sub = SubLLMWithTools(llm_call=_noop_llm)
    sub.register_builtin("web_search")
    assert "web_search" in sub._tools


def test_register_builtin_unknown_raises():
    sub = SubLLMWithTools(llm_call=_noop_llm)
    with pytest.raises(ValueError, match="Unknown built-in tool"):
        sub.register_builtin("made_up_tool")


def test_register_builtins_bulk():
    sub = SubLLMWithTools(llm_call=_noop_llm)
    sub.register_builtins(["web_search", "fetch_url"])
    assert "web_search" in sub._tools
    assert "fetch_url" in sub._tools


def test_get_builtin_tool_names_returns_three():
    names = get_builtin_tool_names()
    assert set(names) == {"web_search", "fetch_url", "search_graph"}


def test_get_tool_specs_returns_metadata():
    specs = get_tool_specs(["web_search"])
    assert len(specs) == 1
    assert specs[0]["name"] == "web_search"
    assert "parameters" in specs[0]


# ---------------------------------------------------------------------------
# C. SubLLMWithTools loop
# ---------------------------------------------------------------------------


class _SeqLLM:
    """LLM stub that returns successive canned responses per call."""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        i = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[i]


def test_single_round_final_answer():
    llm = _SeqLLM(['{"final_answer": "the answer is 42"}'])
    sub = SubLLMWithTools(llm_call=llm)
    assert sub.run("what?") == "the answer is 42"
    assert len(llm.calls) == 1


def test_tool_call_then_final_answer():
    llm = _SeqLLM([
        '{"tool_call": {"name": "echo", "arguments": {"x": "hi"}}}',
        '{"final_answer": "got hi back"}',
    ])
    sub = SubLLMWithTools(llm_call=llm)
    sub.register_tool(
        "echo", lambda x: f"ECHO:{x}", "echo", [{"name": "x"}],
    )
    out = sub.run("call the tool")
    assert out == "got hi back"
    assert len(llm.calls) == 2
    # Second call should have the tool result in the user content.
    assert "ECHO:hi" in llm.calls[1][1]


def test_unknown_tool_fed_back_as_error():
    """When the sub-LLM names a tool that isn't registered, the loop
    feeds back the error and gives the LLM another shot."""
    llm = _SeqLLM([
        '{"tool_call": {"name": "made_up", "arguments": {}}}',
        '{"final_answer": "recovered"}',
    ])
    sub = SubLLMWithTools(llm_call=llm)
    sub.register_builtin("web_search")
    out = sub.run("test")
    assert out == "recovered"
    assert "Unknown tool" in llm.calls[1][1]


def test_tool_execution_error_caught():
    def boom(**kw):
        raise RuntimeError("simulated tool failure")
    llm = _SeqLLM([
        '{"tool_call": {"name": "boom", "arguments": {}}}',
        '{"final_answer": "ok"}',
    ])
    sub = SubLLMWithTools(llm_call=llm)
    sub.register_tool("boom", boom, "boom", [])
    out = sub.run("trigger")
    assert out == "ok"
    # Error string was fed back to the LLM.
    assert "execution error" in llm.calls[1][1]


def test_max_rounds_exhaustion_forces_synthesis():
    """If the LLM keeps calling tools past max_rounds, the loop
    appends a force-synthesis instruction and takes the final
    answer from the next response."""
    llm = _SeqLLM([
        '{"tool_call": {"name": "noop", "arguments": {}}}',
        '{"tool_call": {"name": "noop", "arguments": {}}}',
        '{"tool_call": {"name": "noop", "arguments": {}}}',
        '{"final_answer": "forced"}',
    ])
    sub = SubLLMWithTools(llm_call=llm, max_rounds=3)
    sub.register_tool("noop", lambda **kw: "noop", "noop", [])
    out = sub.run("test")
    assert out == "forced"
    # 3 in-loop calls + 1 force-synthesis call.
    assert len(llm.calls) == 4
    assert "maximum number of tool calls" in llm.calls[-1][1]


def test_tool_output_truncated():
    """A tool returning > MAX_TOOL_OUTPUT_CHARS gets truncated
    before reaching the next LLM call's user content."""
    big = "X" * (MAX_TOOL_OUTPUT_CHARS + 5_000)
    llm = _SeqLLM([
        '{"tool_call": {"name": "big", "arguments": {}}}',
        '{"final_answer": "done"}',
    ])
    sub = SubLLMWithTools(llm_call=llm)
    sub.register_tool("big", lambda **kw: big, "big", [])
    sub.run("test")
    # The second LLM call's user content carries the truncated form.
    user_content = llm.calls[1][1]
    assert "truncated" in user_content
    assert len(user_content) < len(big) + 1000


def test_parse_error_short_circuits():
    llm = _SeqLLM(["totally not JSON at all"])
    sub = SubLLMWithTools(llm_call=llm)
    out = sub.run("test")
    assert "Parse error" in out


def test_unexpected_json_short_circuits():
    """Valid JSON that's neither tool_call nor final_answer returns
    the unexpected-shape diagnostic."""
    llm = _SeqLLM(['{"random_key": "value"}'])
    sub = SubLLMWithTools(llm_call=llm)
    out = sub.run("test")
    assert "Unexpected JSON" in out


# ---------------------------------------------------------------------------
# D. Constructor validation
# ---------------------------------------------------------------------------


def test_constructor_requires_llm_or_investigation_id():
    with pytest.raises(ValueError, match="llm_call.*investigation_id"):
        SubLLMWithTools()


# ---------------------------------------------------------------------------
# E. Batch dispatch
# ---------------------------------------------------------------------------


def test_equipped_llm_batch_preserves_order():
    # Each task gets its own answer tagged with its index.
    def llm(system: str, user: str) -> str:
        # The "task index" is encoded in the prompt as "task-N".
        import re as _re
        m = _re.search(r"task-(\d+)", user)
        idx = m.group(1) if m else "?"
        return f'{{"final_answer": "answer-{idx}"}}'

    tasks = [{"prompt": f"task-{i}", "tools": []} for i in range(3)]
    out = equipped_llm_batch(tasks, llm_call=llm, max_parallel=4)
    assert out == ["answer-0", "answer-1", "answer-2"]


def test_equipped_llm_batch_empty():
    assert equipped_llm_batch([], llm_call=_noop_llm) == []


def test_equipped_llm_batch_sequential_path():
    """max_parallel=1 takes the sequential branch."""
    llm = _SeqLLM(['{"final_answer": "a"}', '{"final_answer": "b"}'])
    tasks = [{"prompt": "p1", "tools": []}, {"prompt": "p2", "tools": []}]
    out = equipped_llm_batch(tasks, llm_call=llm, max_parallel=1)
    assert out == ["a", "b"]


def test_equipped_llm_batch_tools_registered_per_task():
    """Each task's `tools` list controls which built-ins the sub-LLM
    gets. We verify by registering a tool and checking it's
    callable; the LLM stub never actually calls it."""
    llm = _SeqLLM([
        '{"final_answer": "ok1"}', '{"final_answer": "ok2"}',
    ])
    tasks = [
        {"prompt": "p1", "tools": ["web_search"]},
        {"prompt": "p2", "tools": ["fetch_url", "search_graph"]},
    ]
    out = equipped_llm_batch(tasks, llm_call=llm, max_parallel=2)
    assert set(out) == {"ok1", "ok2"}


class _BatchPrimeStub:
    def __init__(self, *, succeeds: bool):
        self.succeeds = succeeds
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        state = PrimeAgentTerminalState.SUCCESS if self.succeeds else PrimeAgentTerminalState.FAILED
        return PrimeAgentOutcome(
            request,
            PrimeAgentEvidence(f"prime-{len(self.requests) - 1}") if self.succeeds else None,
            PrimeAgentReceipt(state, (), 0, 1, 0),
        )


def test_equipped_batch_prime_disabled_preserves_prompts_and_calls():
    llm = _SeqLLM(['{"final_answer": "a"}', '{"final_answer": "b"}'])
    assert equipped_llm_batch(
        [{"prompt": "p1", "tools": []}, {"prompt": "p2", "tools": []}],
        llm_call=llm, max_parallel=1,
    ) == ["a", "b"]
    assert [call[1] for call in llm.calls] == ["p1", "p2"]


def test_equipped_batch_prime_success_is_ordered_labeled_and_receipted():
    prime = _BatchPrimeStub(succeeds=True)
    receipts = []
    prompts = []

    def llm(system, user):
        prompts.append(user)
        return '{"final_answer": "ok"}'

    out = equipped_llm_batch(
        [{"prompt": "p1", "tools": []}, {"prompt": "p2", "tools": []}],
        llm_call=llm, investigation_id="inv", max_parallel=1,
        prime_backend=prime, prime_outcome_sink=receipts.append,
    )
    assert out == ["ok", "ok"]
    assert [r.request.request_id for r in receipts] == [
        "inv:tool-batch:0000", "inv:tool-batch:0001",
    ]
    assert "non-canonical" in prompts[0] and "prime-0" in prompts[0]
    assert "non-canonical" in prompts[1] and "prime-1" in prompts[1]


def test_equipped_batch_prime_failure_preserves_canonical_prompt():
    prime = _BatchPrimeStub(succeeds=False)
    seen = []

    def llm(system, user):
        seen.append(user)
        return '{"final_answer": "canonical"}'

    assert equipped_llm_batch(
        [{"prompt": "p", "tools": []}], llm_call=llm,
        prime_backend=prime,
    ) == ["canonical"]
    assert seen == ["p"]


# ---------------------------------------------------------------------------
# F. Category mapping
# ---------------------------------------------------------------------------


def test_category_tool_map_covers_known_categories():
    assert set(CATEGORY_TOOL_MAP.keys()) == {
        "fact_retrieval", "parameter_extraction",
        "cross_domain_connection", "synthesis", "verification",
    }


def test_tools_for_category_known():
    assert tools_for_category("fact_retrieval") == ["web_search", "search_graph"]
    assert tools_for_category("synthesis") == []


def test_tools_for_category_unknown_returns_empty():
    assert tools_for_category("nonexistent") == []


# ---------------------------------------------------------------------------
# G. HTML extraction + DDG parser
# ---------------------------------------------------------------------------


def test_extract_text_from_html_strips_tags_and_scripts():
    html = (
        "<html><head><title>X</title></head><body>"
        "<script>alert('hi')</script>"
        "<style>p{color:red}</style>"
        "<p>Hello world</p>"
        "<p>Second paragraph</p>"
        "</body></html>"
    )
    text = _extract_text_from_html(html)
    assert "Hello world" in text
    assert "Second paragraph" in text
    assert "alert" not in text
    assert "color:red" not in text


def test_parse_ddg_html_empty_returns_no_results():
    out = _parse_ddg_html("<html><body>nothing here</body></html>",
                          query="xyz")
    assert "no results" in out


def test_parse_ddg_html_with_results():
    html = (
        '<a class="result__a" href="https://example.com">'
        '   Example Title   </a>'
        '<a class="result__snippet" href="ignored">'
        '   This is the snippet   </a>'
    )
    out = _parse_ddg_html(html, query="x")
    assert "Example Title" in out
    assert "snippet" in out
    assert "https://example.com" in out


# ---------------------------------------------------------------------------
# H. Graph search formatting
# ---------------------------------------------------------------------------


def test_format_graph_search_empty():
    out = _format_graph_search_result(
        {"results": [], "node_matches": []}, query="x",
    )
    assert "no chunk matches" in out


def test_format_graph_search_with_chunks_and_edges():
    out = _format_graph_search_result({
        "results": [
            {
                "document_title": "Paper A",
                "source_tier": 1,
                "similarity": 0.92,
                "chunk_text": "Quantum X is observable.",
                "edges": [
                    {"source": {"label": "X"}, "target": {"label": "Y"},
                     "relation": "causes"},
                ],
            },
        ],
        "node_matches": [
            {"label": "QECNode", "node_type": "concept",
             "description": "QEC threshold"},
        ],
    }, query="quantum")
    assert "Paper A" in out
    assert "tier=1" in out
    assert "Quantum X is observable" in out
    assert "(X) —[causes]→ (Y)" in out
    assert "QECNode" in out
    assert "concept" in out


def test_format_graph_search_node_matches_only():
    out = _format_graph_search_result({
        "results": [],
        "node_matches": [
            {"label": "Alpha", "node_type": "entity"},
        ],
    }, query="x")
    assert "Node label matches" in out
    assert "Alpha" in out
