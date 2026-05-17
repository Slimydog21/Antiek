"""RLM REPL — the core recursive language model execution sandbox.

Sprint 9 day 3-4 port of Researchmaxx ``rlm_repl.py``. Implements
the three invariants of the RLM paradigm:

  1. User prompt / corpus is exposed as **variables**, NOT loaded
     into the orchestrator's context window.
  2. Final output is **extracted from** ``answer["content"]``, NOT
     generated as the orchestrator's terminal autoregressive output.
  3. Sub-LLM calls are programmatic function calls (``llm_query``,
     ``llm_batch``) inside the REPL, NOT verbalized actions in the
     orchestrator's autoregressive stream.

Contract (the minimum viable RLM cycle)::

    repl = RLMRepl(corpus={"source_text": "..."})
    repl.registry.install("llm_query", callable)
    repl.registry.install("llm_batch", callable)
    while not repl.is_finished():
        meta = repl.summarise()       # constant-size metadata
        code = orchestrator(meta)     # orchestrator generates Python code
        repl.execute(code)            # code runs; state mutates
    return repl.answer["content"]

The orchestrator sees ONLY metadata — variable lengths, types,
short prefixes of stdout — never the full corpus. This is what
prevents context rot.

**Antiek changes from upstream:**

- Constants imported from ``substrate.constants`` (same names —
  the upstream RLM_* values were preserved verbatim in Sprint 1).
- No other behavioral changes; the sandbox + summary + loop logic
  is verbatim.
"""

from __future__ import annotations

import ast
import io
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

# Ensure substrate root on path for direct invocation.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.constants import (  # noqa: E402
    RLM_ANSWER_CONTENT_MAX,
    RLM_MAX_RECURSION_DEPTH,
    RLM_REPL_AVAILABLE_PACKAGES,
    RLM_REPL_STDOUT_TRUNCATE,
)


# ---------------------------------------------------------------------------
# Function registry
# ---------------------------------------------------------------------------


class FunctionRegistry:
    """White-list of callables visible inside the REPL sandbox."""

    def __init__(self):
        self._fns: Dict[str, Callable] = {}
        self._packages: List[str] = list(RLM_REPL_AVAILABLE_PACKAGES)

    def install(self, name: str, fn: Callable) -> None:
        if not callable(fn):
            raise TypeError(f"{name!r} must be callable")
        self._fns[name] = fn

    def install_package(self, name: str) -> None:
        if name not in self._packages:
            self._packages.append(name)

    def installed_function_names(self) -> List[str]:
        return list(self._fns.keys())

    def globals_snapshot(self) -> Dict[str, Any]:
        """Dict fed into ``exec(code, sandbox_globals)``."""
        return dict(self._fns)


# ---------------------------------------------------------------------------
# Sandbox — AST validator
# ---------------------------------------------------------------------------


# Allowed top-level node types. Everything else is forbidden.
_ALLOWED_NODE_TYPES = frozenset({
    ast.Module, ast.Expr, ast.Import, ast.ImportFrom,
    ast.Assign, ast.AugAssign, ast.AnnAssign,
    ast.FunctionDef, ast.Return,
    ast.For, ast.While, ast.If, ast.Break, ast.Continue, ast.Pass,
    ast.Call, ast.Attribute, ast.Subscript, ast.Name, ast.Constant,
    ast.List, ast.Tuple, ast.Dict, ast.Set, ast.ListComp, ast.DictComp,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Slice, ast.JoinedStr, ast.FormattedValue,
    ast.Starred, ast.keyword,
    ast.Load, ast.Store, ast.Del,
    ast.arguments, ast.arg, ast.comprehension,
    ast.alias,
    # Comparison + binary operators
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.LShift, ast.RShift, ast.BitOr, ast.BitXor, ast.BitAnd,
    ast.MatMult,
    ast.And, ast.Or, ast.Not, ast.UAdd, ast.USub, ast.Invert,
})


class SandboxSecurityError(RuntimeError):
    """Raised when code contains forbidden AST nodes."""


class SandboxValidator(ast.NodeVisitor):
    def __init__(self):
        self.errors: List[str] = []

    def generic_visit(self, node):
        if type(node) not in _ALLOWED_NODE_TYPES:
            self.errors.append(
                f"node type {type(node).__name__!r} is forbidden in the "
                f"REPL sandbox (line ~{getattr(node, 'lineno', '?')})"
            )
        super().generic_visit(node)


def _validate_code(code: str) -> None:
    """Raise ``SandboxSecurityError`` if the code contains forbidden
    constructs."""
    tree = ast.parse(code)
    v = SandboxValidator()
    v.visit(tree)
    if v.errors:
        raise SandboxSecurityError("; ".join(v.errors))


def _check_recursion_depth(depth: int) -> None:
    if depth > RLM_MAX_RECURSION_DEPTH:
        raise RuntimeError(
            f"RLM recursion depth {depth} exceeds max "
            f"{RLM_MAX_RECURSION_DEPTH}. Escalate or restructure the DAG."
        )


# ---------------------------------------------------------------------------
# State summary — the metadata the orchestrator sees
# ---------------------------------------------------------------------------


@dataclass
class ReplSummary:
    """Constant-size metadata shown to the orchestrator each iteration."""

    iteration: int
    depth: int
    answer_content_len: int
    answer_content_prefix: str  # first 200 chars
    answer_ready: bool
    variable_sizes: Dict[str, int]
    variable_types: Dict[str, str]
    variable_prefixes: Dict[str, str]
    stdout_snippet: str  # truncated to RLM_REPL_STDOUT_TRUNCATE
    exception: Optional[str] = None
    last_exception_trace: Optional[str] = None

    def format_for_prompt(self) -> str:
        parts = [
            f"## REPL state (iteration {self.iteration}, depth {self.depth})",
            f"answer.content length: {self.answer_content_len}",
            f"answer.ready: {self.answer_ready}",
        ]
        if self.answer_content_prefix:
            parts.append(f"answer.content prefix: {self.answer_content_prefix}")
        if self.exception:
            parts.append(f"LAST EXCEPTION: {self.exception}")
            if self.last_exception_trace:
                parts.append(
                    self.last_exception_trace[: RLM_REPL_STDOUT_TRUNCATE // 2]
                )

        parts.append("\n### Variables")
        for name in sorted(self.variable_sizes):
            sz = self.variable_sizes[name]
            typ = self.variable_types.get(name, "?")
            parts.append(f"  {name}: {typ}, size={sz}")
            prefix = self.variable_prefixes.get(name, "")
            if prefix:
                parts.append(f"    prefix: {prefix}")

        if self.stdout_snippet.strip():
            parts.append(
                f"\n### stdout (truncated to {RLM_REPL_STDOUT_TRUNCATE} chars)"
            )
            parts.append(self.stdout_snippet[:RLM_REPL_STDOUT_TRUNCATE])

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# The REPL
# ---------------------------------------------------------------------------


class RLMRepl:
    """Persistent Python REPL implementing the RLM contract.

    The orchestrator LLM sees only a ``ReplSummary`` each iteration.
    It generates Python code; the code executes inside this sandbox;
    state updates; the loop repeats until ``answer["ready"]`` is True.

    Parameters
    ----------
    corpus : dict, optional
        Variables seeded into the sandbox (e.g.
        ``{"source_text": "..."}``). These are NOT loaded into the
        orchestrator's context window — they live only inside the
        REPL.
    max_iterations : int
        Hard cap on loop iterations (default 20).
    depth : int
        Recursion depth counter. Sub-DAGs may nest up to
        ``RLM_MAX_RECURSION_DEPTH``.
    """

    def __init__(
        self,
        corpus: Optional[Dict[str, Any]] = None,
        *,
        max_iterations: int = 20,
        depth: int = 0,
    ):
        self.registry = FunctionRegistry()
        self.max_iterations = max_iterations
        self.depth = depth
        self.iteration = 0
        self._globals: Dict[str, Any] = {}
        self._locals: Dict[str, Any] = {}
        self._stdout_buffer = io.StringIO()
        self._exception: Optional[str] = None
        self._exception_trace: Optional[str] = None

        # The diffusion-answer pattern.
        self.answer: Dict[str, Any] = {"content": "", "ready": False}

        if corpus:
            for name, value in corpus.items():
                self._globals[name] = value

        self._globals["answer"] = self.answer

    # -- public API --------------------------------------------------------

    def summarise(self) -> ReplSummary:
        """Produce constant-size metadata for the orchestrator."""
        var_sizes: Dict[str, int] = {}
        var_types: Dict[str, str] = {}
        var_prefixes: Dict[str, str] = {}
        for name, value in self._globals.items():
            if name in ("answer", "__builtins__"):
                continue
            try:
                r = repr(value)
                var_sizes[name] = len(r)
                var_types[name] = type(value).__name__
                var_prefixes[name] = r[:120]
            except Exception:
                var_sizes[name] = -1
                var_types[name] = type(value).__name__
                var_prefixes[name] = "<repr failed>"

        stdout = self._stdout_buffer.getvalue()
        ans_content = str(self.answer.get("content", ""))
        return ReplSummary(
            iteration=self.iteration,
            depth=self.depth,
            answer_content_len=len(ans_content),
            answer_content_prefix=ans_content[:200] if ans_content else "",
            answer_ready=bool(self.answer.get("ready")),
            variable_sizes=var_sizes,
            variable_types=var_types,
            variable_prefixes=var_prefixes,
            stdout_snippet=stdout[-RLM_REPL_STDOUT_TRUNCATE:],
            exception=self._exception,
            last_exception_trace=self._exception_trace,
        )

    def execute(self, code: str) -> str:
        """Execute Python code inside the sandbox.

        Returns the captured-stdout suffix (truncated). Side-effects
        mutate ``self._globals`` (sandbox namespace), ``self.answer``
        (diffusion-answer variable), and ``self._stdout_buffer``.

        Raises ``SandboxSecurityError`` for forbidden constructs.
        Runtime errors are captured into ``self._exception`` and the
        traceback into ``self._exception_trace`` — the orchestrator
        reads both via the next ``summarise()`` call.
        """
        _check_recursion_depth(self.depth)
        self._exception = None
        self._exception_trace = None

        # Security gate
        _validate_code(code)

        # Build sandbox globals: registry functions + user variables
        sandbox_globals = self.registry.globals_snapshot()
        sandbox_globals.update(self._globals)
        sandbox_globals["__builtins__"] = {
            "print": print, "len": len, "range": range,
            "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
            "sorted": sorted, "reversed": reversed,
            "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
            "int": int, "float": float, "str": str, "bool": bool,
            "list": list, "dict": dict, "set": set, "tuple": tuple,
            "type": type, "isinstance": isinstance,
            "hasattr": hasattr, "getattr": getattr,
            "Exception": Exception, "ValueError": ValueError,
            "TypeError": TypeError, "KeyError": KeyError,
            "IndexError": IndexError, "RuntimeError": RuntimeError,
            "StopIteration": StopIteration,
            "True": True, "False": False, "None": None,
        }

        # Capture stdout
        saved_stdout = sys.stdout
        sys.stdout = self._stdout_buffer
        try:
            # Single-dict exec: top-level assignments land in
            # ``sandbox_globals`` so the post-exec pull-back picks
            # them up. (Two-dict exec puts top-level names in
            # ``locals`` and they never reach the summary.)
            exec(compile(code, "<rlm_repl>", "exec"), sandbox_globals)
        except Exception as exc:
            self._exception = f"{type(exc).__name__}: {exc}"
            self._exception_trace = traceback.format_exc()
        finally:
            sys.stdout = saved_stdout
            if "answer" in sandbox_globals:
                self.answer = sandbox_globals["answer"]
                self._globals["answer"] = self.answer
            for k, v in sandbox_globals.items():
                if k not in ("__builtins__",) and not k.startswith("__"):
                    self._globals[k] = v

        self.iteration += 1

        # Enforce answer content cap
        content = str(self.answer.get("content", ""))
        if len(content) > RLM_ANSWER_CONTENT_MAX:
            self.answer["content"] = content[:RLM_ANSWER_CONTENT_MAX]
            self._stdout_buffer.write(
                f"\n[RLM] answer.content truncated to "
                f"{RLM_ANSWER_CONTENT_MAX} chars\n"
            )

        return self._stdout_buffer.getvalue()[-RLM_REPL_STDOUT_TRUNCATE:]

    def is_finished(self) -> bool:
        """True when ``answer["ready"]`` is set OR iteration cap hit."""
        if self.answer.get("ready"):
            return True
        if self.iteration >= self.max_iterations:
            return True
        return False

    def final_answer(self) -> str:
        """Extract the final answer. Call after the loop terminates."""
        return str(self.answer.get("content", ""))

    def snapshot(self) -> Dict[str, Any]:
        """JSON-serializable snapshot for archival."""
        return {
            "iteration": self.iteration,
            "depth": self.depth,
            "max_iterations": self.max_iterations,
            "answer_ready": self.answer.get("ready"),
            "answer_content_len": len(str(self.answer.get("content", ""))),
            "variable_names": [k for k in self._globals if k != "answer"],
            "variable_sizes": {
                k: len(repr(v))
                for k, v in self._globals.items()
                if k not in ("answer", "__builtins__")
            },
            "exception_count": 0 if not self._exception else 1,
        }


# ---------------------------------------------------------------------------
# Loop driver
# ---------------------------------------------------------------------------


def rlm_loop(
    repl: RLMRepl,
    generate_code: Callable[[ReplSummary], str],
    *,
    max_iterations: Optional[int] = None,
) -> str:
    """Run the full RLM loop to completion.

    If the loop exhausts iterations without flipping
    ``answer["ready"]``, the answer is force-flushed so the caller
    never gets stuck in an unbounded loop."""
    limit = max_iterations or repl.max_iterations
    while not repl.is_finished() and repl.iteration < limit:
        summary = repl.summarise()
        code = generate_code(summary)
        repl.execute(code)

    if not repl.answer.get("ready"):
        repl.answer["ready"] = True
    return repl.final_answer()


# ---------------------------------------------------------------------------
# Sub-LLM call helpers
# ---------------------------------------------------------------------------


def make_llm_query(llm_caller: Callable[[str], str]) -> Callable[[str], str]:
    """Wrap a raw LLM caller into the REPL signature::

        llm_query(prompt: str) -> str

    The orchestrator never sees the raw LLM output; it sees only the
    returned string (which may be further sliced in Python before
    the orchestrator revisits it)."""
    def _llm_query(prompt: str) -> str:
        return llm_caller(prompt)
    return _llm_query


def make_llm_batch(
    llm_caller: Callable[[str], str],
    *,
    max_parallel: int = 6,
) -> Callable[[List[str]], List[str]]:
    """Wrap a raw LLM caller into the batched signature::

        llm_batch(prompts: list[str]) -> list[str]

    Dispatches prompts in parallel via ``ThreadPoolExecutor`` bounded
    by ``max_parallel``. Each prompt is an independent LLM call."""

    def _llm_batch(prompts: List[str]) -> List[str]:
        results: List[Optional[str]] = [None] * len(prompts)
        workers = min(max_parallel, len(prompts)) if prompts else 0
        if workers <= 1:
            for i, p in enumerate(prompts):
                results[i] = llm_caller(p)
            return [r for r in results if r is not None]

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(llm_caller, p): i for i, p in enumerate(prompts)}
            for fut in as_completed(futures):
                i = futures[fut]
                try:
                    results[i] = fut.result()
                except Exception as exc:
                    results[i] = f"ERROR: {exc}"
        return [r for r in results if r is not None]

    return _llm_batch


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(
        description=(
            "RLM REPL — execute a single Python snippet inside the sandbox "
            "and print the resulting ReplSummary."
        ),
    )
    p.add_argument("--code", required=True, help="Python code to execute")
    p.add_argument("--depth", type=int, default=0,
                   help="Recursion depth counter (default 0)")
    args = p.parse_args()

    repl = RLMRepl(depth=args.depth)
    repl.execute(args.code)
    print(repl.summarise().format_for_prompt())
    return 0


if __name__ == "__main__":
    sys.exit(main())
