"""Verify the exec-backend flag branch at the cascade launch site.

The CRITICAL invariant this lane must hold is BEHAVIOR-NEUTRALITY: with
``ANTIEK_EXEC_BACKEND`` unset, the production research launch path is unchanged
(``HostLocalRunner`` is constructed exactly as before, and no ExecutionBackend
is built). The exec-backend factory is only reachable behind the flag, and even
when set it is wired *alongside* the runner, never replacing it.

Rather than re-simulate the branch logic inline (which would only test a copy of
the code), these tests parse the REAL ``cascade_routes.launch`` source with the
``ast`` module and mechanically prove the invariant:

  * every ``build_execution_backend`` call sits inside the ``ANTIEK_EXEC_BACKEND``
    guard — so the default path never constructs a backend;
  * ``runner`` is never (re)assigned inside that guard — so the flag cannot
    change which runner the session gets;
  * ``runner`` IS assigned on the unguarded path — the default HostLocalRunner.

This is the same mechanical-proof discipline the base ExecutionBackend commit
used (AST over substring greps). It also exercises the real factory end to end.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

import interfaces.research.api.cascade_routes as cascade_mod
from runtime.exec_backend.factory import BACKEND_ENV, build_execution_backend
from runtime.exec_backend.local_process import LocalProcessBackend

# ---------------------------------------------------------------------------
# AST helpers — parse the real launch() source, not a re-implementation.
# ---------------------------------------------------------------------------


def _launch_fn_ast() -> ast.AST:
    """Return the AST FunctionDef for the real ``launch`` handler.

    Parsed straight from the module file so decorators (router registration)
    cannot hide the source, and so the test tracks the shipped code exactly.
    """
    src = pathlib.Path(cascade_mod.__file__).read_text()
    tree = ast.parse(src)
    candidates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        and node.name == "launch"
    ]
    # Pick the launch function that actually contains the exec-backend call.
    for fn in candidates:
        if any(_is_build_backend_call(n) for n in ast.walk(fn)):
            return fn
    assert candidates, "no launch() function found in cascade_routes"
    return candidates[0]


def _is_build_backend_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_execution_backend"
    )


def _backend_env_guards(fn: ast.AST) -> list[ast.If]:
    """Every ``if ...`` whose test references ``BACKEND_ENV``."""
    guards: list[ast.If] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.If):
            names = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
            if "BACKEND_ENV" in names:
                guards.append(node)
    return guards


def _runner_assign_names(scope: ast.AST) -> list[ast.Assign]:
    out: list[ast.Assign] = []
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "runner":
                    out.append(node)
    return out


# ---------------------------------------------------------------------------
# BEHAVIOR-NEUTRAL invariant — proven against the real source
# ---------------------------------------------------------------------------


class TestBehaviorNeutralInvariant:
    def test_backend_call_is_env_guarded(self) -> None:
        """No ``build_execution_backend`` call outside the BACKEND_ENV guard —
        the default (flag-unset) path never constructs a backend."""
        fn = _launch_fn_ast()
        all_calls = [n for n in ast.walk(fn) if _is_build_backend_call(n)]
        assert all_calls, "expected a build_execution_backend call in launch()"
        guards = _backend_env_guards(fn)
        assert guards, "expected an ANTIEK_EXEC_BACKEND-guarded branch in launch()"
        guarded_calls = [
            n
            for g in guards
            for n in ast.walk(g)
            if _is_build_backend_call(n)
        ]
        assert len(guarded_calls) == len(all_calls), (
            "every build_execution_backend call must be inside the "
            "ANTIEK_EXEC_BACKEND guard; found unguarded call(s)"
        )

    def test_runner_never_assigned_inside_guard(self) -> None:
        """The flag must not change which runner the session gets — ``runner``
        is never (re)assigned inside the exec-backend guard."""
        fn = _launch_fn_ast()
        for guard in _backend_env_guards(fn):
            assert not _runner_assign_names(guard), (
                "runner is reassigned inside the ANTIEK_EXEC_BACKEND guard — "
                "this would break behavior-neutrality of the default path"
            )

    def test_runner_assigned_on_default_path(self) -> None:
        """``runner`` is assigned unconditionally on the default path (the
        HostLocalRunner construction), not gated by the flag."""
        fn = _launch_fn_ast()
        guarded = {id(a) for g in _backend_env_guards(fn) for a in _runner_assign_names(g)}
        all_assigns = _runner_assign_names(fn)
        unguarded = [a for a in all_assigns if id(a) not in guarded]
        assert unguarded, "expected an unguarded `runner = ...` construction in launch()"


# ---------------------------------------------------------------------------
# The wiring is actually imported into the cascade module
# ---------------------------------------------------------------------------


class TestWiringPresent:
    def test_factory_symbols_imported_in_cascade(self) -> None:
        assert cascade_mod.build_execution_backend is build_execution_backend
        assert cascade_mod.BACKEND_ENV == "ANTIEK_EXEC_BACKEND"


# ---------------------------------------------------------------------------
# Flag SET: the factory really returns a LocalProcessBackend (end to end)
# ---------------------------------------------------------------------------


class TestFlagSetEndToEnd:
    def test_flag_set_factory_returns_local_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(BACKEND_ENV, "local")
        backend = build_execution_backend(
            seal_on_complete=False,
            retrieval_substrate=None,
        )
        assert isinstance(backend, LocalProcessBackend)
        assert backend.name == "local"

    def test_forwarded_runner_kwargs_do_not_raise(self) -> None:
        """The launch site forwards seal_on_complete/retrieval_substrate; the
        factory must accept them without a TypeError."""
        backend = build_execution_backend(
            seal_on_complete=False,
            retrieval_substrate=object(),
        )
        assert isinstance(backend, LocalProcessBackend)
