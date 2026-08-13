"""Tests for interfaces/research/rlm_repl.py (Sprint 9 day 3-4).

Coverage:

A. FunctionRegistry:
   1. install + globals_snapshot.
   2. install rejects non-callable.
   3. install_package idempotent.

B. AST validator (sandbox security):
   4. Allowed constructs pass.
   5. import OS (forbidden) — well actually Import is allowed; verify
      what IS forbidden: with, try/except, async, lambda, class,
      delete-from-namespace.
   6. Multiple forbidden nodes accumulate errors.

C. Execute happy path:
   7. Simple assignment lands in summary.
   8. Print captured in stdout buffer.
   9. answer["content"] mutation persists.
   10. answer["ready"] flips end-of-loop.
   11. Registered function callable inside sandbox.
   12. answer.content cap truncates at RLM_ANSWER_CONTENT_MAX.

D. Recursion + iteration limits:
   13. _check_recursion_depth raises above RLM_MAX_RECURSION_DEPTH.
   14. is_finished() returns True when answer.ready set.
   15. is_finished() returns True at iteration cap.

E. Runtime errors:
   16. Exception in user code captured; doesn't propagate.
   17. _exception_trace populated.
   18. Per-iteration exception state cleared between executions.

F. Summarise:
   19. ReplSummary captures variable sizes + types + prefixes.
   20. answer + __builtins__ excluded from variables.
   21. format_for_prompt yields a readable string.

G. rlm_loop:
   22. Loop runs until generate_code sets answer.ready.
   23. Force-flush when iteration cap hit without ready flag.

H. LLM helpers:
   24. make_llm_query returns callable that proxies the raw caller.
   25. make_llm_batch sequential path.
   26. make_llm_batch parallel path preserves order.
   27. make_llm_batch caught exception → "ERROR: ..." string.
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from interfaces.research.rlm_repl import (  # noqa: E402
    FunctionRegistry,
    ReplSummary,
    RLMRepl,
    SandboxSecurityError,
    _check_recursion_depth,
    _validate_code,
    make_llm_batch,
    make_llm_query,
    rlm_loop,
)
from orchestration.rlm.prime_agent_backend import (  # noqa: E402
    PrimeAgentEvidence,
    PrimeAgentOutcome,
    PrimeAgentReceipt,
    PrimeAgentTerminalState,
)
from substrate.constants import (  # noqa: E402
    RLM_ANSWER_CONTENT_MAX,
    RLM_MAX_RECURSION_DEPTH,
)


class _PrimeBackendStub:
    def __init__(self, state, text=None):
        self.state = state
        self.text = text
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return PrimeAgentOutcome(
            request=request,
            evidence=PrimeAgentEvidence(self.text) if self.text else None,
            receipt=PrimeAgentReceipt(self.state, (), None, 1, 0, "stub"),
        )

# ---------------------------------------------------------------------------
# A. FunctionRegistry
# ---------------------------------------------------------------------------


def test_registry_install_callable():
    r = FunctionRegistry()
    r.install("greet", lambda name: f"hi {name}")
    snap = r.globals_snapshot()
    assert "greet" in snap
    assert snap["greet"]("X") == "hi X"


def test_llm_query_prime_disabled_preserves_prompt_and_receipts():
    calls = []
    receipts = []
    backend = _PrimeBackendStub(PrimeAgentTerminalState.DISABLED)
    query = make_llm_query(
        lambda prompt: calls.append(prompt) or "canonical",
        prime_backend=backend,
        evidence_sink=receipts.append,
    )

    assert query("question") == "canonical"
    assert calls == ["question"]
    assert len(backend.requests) == len(receipts) == 1
    assert receipts[0].receipt.state is PrimeAgentTerminalState.DISABLED


def test_llm_batch_prime_success_is_labeled_and_ordered():
    calls = []
    receipts = []
    backend = _PrimeBackendStub(PrimeAgentTerminalState.SUCCESS, "support")
    batch = make_llm_batch(
        lambda prompt: calls.append(prompt) or "canonical",
        max_parallel=1,
        prime_backend=backend,
        evidence_sink=receipts.append,
    )

    assert batch(["first", "second"]) == ["canonical", "canonical"]
    assert [request.prompt for request in backend.requests] == ["first", "second"]
    assert len({request.request_id for request in backend.requests}) == 2
    assert len(calls) == len(receipts) == 2
    assert all("Supplemental Prime Agent evidence (non-canonical)" in p for p in calls)
    assert all("support" in p for p in calls)

    batch(["first"])
    assert len({request.request_id for request in backend.requests}) == 3


def test_llm_query_prime_failure_does_not_change_canonical_result():
    backend = _PrimeBackendStub(PrimeAgentTerminalState.FAILED)
    calls = []
    query = make_llm_query(
        lambda prompt: calls.append(prompt) or "canonical",
        prime_backend=backend,
    )

    assert query("question") == "canonical"
    assert calls == ["question"]


def test_llm_query_duplicate_prompts_have_distinct_receipt_ids():
    backend = _PrimeBackendStub(PrimeAgentTerminalState.DISABLED)
    query = make_llm_query(lambda _prompt: "canonical", prime_backend=backend)

    assert query("same") == query("same") == "canonical"
    assert len({request.request_id for request in backend.requests}) == 2


def test_registry_rejects_non_callable():
    r = FunctionRegistry()
    with pytest.raises(TypeError):
        r.install("not_a_fn", 42)


def test_registry_install_package_idempotent():
    r = FunctionRegistry()
    r.install_package("foo")
    r.install_package("foo")
    assert r._packages.count("foo") == 1


# ---------------------------------------------------------------------------
# B. AST validator
# ---------------------------------------------------------------------------


def test_validator_allows_typical_code():
    _validate_code("""
x = 1
y = [1, 2, 3]
z = {a: b for a, b in zip([1], [2])}
def f(n): return n * 2
print(f(5))
""")


def test_validator_rejects_try_except():
    with pytest.raises(SandboxSecurityError, match="Try"):
        _validate_code("try:\n    pass\nexcept Exception:\n    pass\n")


def test_validator_rejects_class_def():
    with pytest.raises(SandboxSecurityError, match="ClassDef"):
        _validate_code("class Foo: pass\n")


def test_validator_rejects_lambda():
    with pytest.raises(SandboxSecurityError, match="Lambda"):
        _validate_code("f = lambda x: x + 1\n")


def test_validator_rejects_with_statement():
    with pytest.raises(SandboxSecurityError, match="With"):
        _validate_code("with open('/etc/passwd') as f:\n    pass\n")


def test_validator_rejects_async():
    with pytest.raises(SandboxSecurityError, match="Async"):
        _validate_code("async def f():\n    pass\n")


def test_validator_accumulates_multiple_errors():
    code = "class A: pass\nf = lambda x: x\n"
    try:
        _validate_code(code)
    except SandboxSecurityError as exc:
        assert "ClassDef" in str(exc)
        assert "Lambda" in str(exc)
    else:  # pragma: no cover
        pytest.fail("expected SandboxSecurityError")


# ---------------------------------------------------------------------------
# C. Execute happy path
# ---------------------------------------------------------------------------


def test_execute_assignment_lands_in_summary():
    repl = RLMRepl()
    repl.execute("x = 42")
    summary = repl.summarise()
    assert summary.variable_sizes.get("x") == len(repr(42))
    assert summary.variable_types.get("x") == "int"


def test_execute_print_captured_in_stdout_snippet():
    repl = RLMRepl()
    repl.execute("print('hello world')")
    summary = repl.summarise()
    assert "hello world" in summary.stdout_snippet


def test_execute_answer_content_persists():
    repl = RLMRepl()
    repl.execute("answer['content'] = 'thesis text'")
    assert repl.answer["content"] == "thesis text"


def test_execute_answer_ready_flag_persists():
    repl = RLMRepl()
    repl.execute("answer['ready'] = True")
    assert repl.is_finished() is True


def test_execute_registered_function_callable():
    repl = RLMRepl()
    repl.registry.install("double", lambda n: n * 2)
    repl.execute("answer['content'] = str(double(21))")
    assert repl.answer["content"] == "42"


def test_execute_answer_content_cap_truncates():
    repl = RLMRepl()
    repl.execute(f"answer['content'] = 'X' * {RLM_ANSWER_CONTENT_MAX + 1000}")
    assert len(repl.answer["content"]) == RLM_ANSWER_CONTENT_MAX
    summary = repl.summarise()
    assert "truncated" in summary.stdout_snippet


def test_corpus_seeded_into_sandbox():
    repl = RLMRepl(corpus={"source_text": "Hello corpus"})
    repl.execute("answer['content'] = source_text[:5]")
    assert repl.answer["content"] == "Hello"


# ---------------------------------------------------------------------------
# D. Recursion + iteration limits
# ---------------------------------------------------------------------------


def test_check_recursion_depth_under_limit_ok():
    _check_recursion_depth(RLM_MAX_RECURSION_DEPTH)


def test_check_recursion_depth_over_limit_raises():
    with pytest.raises(RuntimeError, match="recursion depth"):
        _check_recursion_depth(RLM_MAX_RECURSION_DEPTH + 1)


def test_is_finished_when_answer_ready():
    repl = RLMRepl()
    repl.execute("answer['ready'] = True")
    assert repl.is_finished() is True


def test_is_finished_at_iteration_cap():
    repl = RLMRepl(max_iterations=2)
    repl.execute("x = 1")
    repl.execute("y = 2")
    assert repl.is_finished() is True


# ---------------------------------------------------------------------------
# E. Runtime errors
# ---------------------------------------------------------------------------


def test_runtime_error_captured_not_propagated():
    repl = RLMRepl()
    # Division by zero — runtime, not AST-validated.
    repl.execute("answer['content'] = str(1 / 0)")
    summary = repl.summarise()
    assert summary.exception is not None
    assert "ZeroDivisionError" in summary.exception


def test_exception_trace_populated():
    repl = RLMRepl()
    repl.execute("undefined_name_xyz")
    summary = repl.summarise()
    assert summary.last_exception_trace is not None
    assert "NameError" in summary.exception


def test_exception_state_cleared_between_executions():
    repl = RLMRepl()
    repl.execute("1 / 0")
    repl.execute("x = 1")  # clean code
    summary = repl.summarise()
    assert summary.exception is None


# ---------------------------------------------------------------------------
# F. Summarise
# ---------------------------------------------------------------------------


def test_summarise_captures_variable_metadata():
    repl = RLMRepl()
    repl.execute("name = 'alpha'\ncount = 7")
    summary = repl.summarise()
    assert summary.variable_types["name"] == "str"
    assert summary.variable_types["count"] == "int"
    assert summary.variable_prefixes["name"].startswith("'alpha'")


def test_summarise_excludes_answer_and_builtins():
    repl = RLMRepl()
    repl.execute("x = 1")
    summary = repl.summarise()
    assert "answer" not in summary.variable_sizes
    assert "__builtins__" not in summary.variable_sizes


def test_format_for_prompt_renders_string():
    repl = RLMRepl()
    repl.execute("x = 1\nprint('hello')")
    summary = repl.summarise()
    s = summary.format_for_prompt()
    assert "REPL state" in s
    assert "answer.content length" in s
    assert "x: int" in s
    assert "hello" in s


def test_snapshot_serializable_shape():
    repl = RLMRepl()
    repl.execute("a = [1, 2, 3]")
    snap = repl.snapshot()
    assert snap["iteration"] == 1
    assert "a" in snap["variable_names"]


# ---------------------------------------------------------------------------
# G. rlm_loop
# ---------------------------------------------------------------------------


def test_rlm_loop_runs_until_ready():
    """Generate-code callback flips answer.ready after iteration 3."""
    repl = RLMRepl()
    call_count = [0]

    def gen(summary: ReplSummary) -> str:
        call_count[0] += 1
        if call_count[0] >= 3:
            return "answer['content'] = 'done'\nanswer['ready'] = True"
        return f"step_{call_count[0]} = {call_count[0]}"

    answer = rlm_loop(repl, gen)
    assert answer == "done"
    assert call_count[0] == 3


def test_rlm_loop_force_flushes_on_iteration_cap():
    repl = RLMRepl(max_iterations=2)

    def gen(summary):
        return "x = 1"  # never sets ready

    rlm_loop(repl, gen)
    # Force-flush sets ready=True even though code never did.
    assert repl.answer["ready"] is True


# ---------------------------------------------------------------------------
# H. LLM helpers
# ---------------------------------------------------------------------------


def test_make_llm_query_proxies_raw_caller():
    q = make_llm_query(lambda prompt: f"echo:{prompt}")
    assert q("hi") == "echo:hi"


def test_make_llm_batch_sequential_path():
    """max_parallel=1 takes sequential branch."""
    calls = []
    def caller(p):
        calls.append(p)
        return f"r:{p}"

    batch = make_llm_batch(caller, max_parallel=1)
    out = batch(["a", "b", "c"])
    assert out == ["r:a", "r:b", "r:c"]
    assert calls == ["a", "b", "c"]


def test_make_llm_batch_parallel_preserves_order():
    """With max_parallel > 1, results come back in input order."""
    def caller(p):
        return f"resp:{p}"

    batch = make_llm_batch(caller, max_parallel=4)
    out = batch([f"prompt_{i}" for i in range(5)])
    assert out == [f"resp:prompt_{i}" for i in range(5)]


def test_make_llm_batch_caught_exception_becomes_error_string():
    def caller(p):
        if p == "fail":
            raise RuntimeError("simulated")
        return f"ok:{p}"

    batch = make_llm_batch(caller, max_parallel=2)
    out = batch(["good", "fail"])
    assert any(r.startswith("ERROR") for r in out)
    assert any(r == "ok:good" for r in out)


def test_make_llm_batch_empty_list():
    batch = make_llm_batch(lambda p: p, max_parallel=4)
    assert batch([]) == []
