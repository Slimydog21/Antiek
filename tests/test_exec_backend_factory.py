"""Tests for ``runtime.exec_backend.factory`` — the ``build_execution_backend`` seam.

Acceptance criteria from the swarm brief:

  * Factory default (``ANTIEK_EXEC_BACKEND`` unset) returns a ``LocalProcessBackend``.
  * Explicit ``kind="local"`` returns a ``LocalProcessBackend``.
  * Unknown kind raises ``BackendUnavailable`` (no silent downgrade).
  * ``kind="docker"`` is a registered kind, and with the daemon or CLI absent it
    raises ``BackendUnavailable`` rather than handing back a local backend. That
    refusal is the security property of this seam: a silent downgrade would run
    untrusted agent code on the bare host while the operator believed it was
    contained, which is strictly worse than refusing to start.
  * The default path builds a local backend without importing the docker
    adapter — the factory's docker import is nested in its own branch.
  * ``seal_on_complete`` / ``retrieval_substrate`` kwargs are accepted without
    ``TypeError`` (the cascade launch site forwards them).
  * ``BACKEND_ENV`` is ``"ANTIEK_EXEC_BACKEND"``.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from runtime.exec_backend import factory as factory_module
from runtime.exec_backend.factory import BACKEND_ENV, build_execution_backend
from runtime.exec_backend.interface import BackendUnavailable, ExecutionBackend
from runtime.exec_backend.local_process import LocalProcessBackend

#: The adapter module the default path must not need.
_DOCKER_MODULE = "runtime.exec_backend.docker_backend"

# ---------------------------------------------------------------------------
# Factory returns the right type
# ---------------------------------------------------------------------------


class TestFactoryDefault:
    """The factory default is ``LocalProcessBackend``."""

    def test_default_returns_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(BACKEND_ENV, raising=False)
        backend = build_execution_backend()
        assert isinstance(backend, LocalProcessBackend)

    def test_default_name_is_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(BACKEND_ENV, raising=False)
        backend = build_execution_backend()
        assert backend.name == "local"

    def test_default_satisfies_protocol(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(BACKEND_ENV, raising=False)
        backend = build_execution_backend()
        assert isinstance(backend, ExecutionBackend)


class TestFactoryExplicitKind:
    """Explicit ``kind`` overrides the env var."""

    def test_explicit_local(self) -> None:
        backend = build_execution_backend(kind="local")
        assert isinstance(backend, LocalProcessBackend)

    def test_env_var_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(BACKEND_ENV, "local")
        backend = build_execution_backend()
        assert isinstance(backend, LocalProcessBackend)

    def test_explicit_kind_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(BACKEND_ENV, "local")
        backend = build_execution_backend(kind="local")
        assert isinstance(backend, LocalProcessBackend)


class TestFactoryUnknownKind:
    """Unknown kind raises ``BackendUnavailable`` — no silent downgrade."""

    def test_unknown_kind_raises(self) -> None:
        # Deliberately changed from ``kind="docker"``: docker is now a
        # registered kind (it reaches its own branch and its own probe), so it
        # no longer exercises the unknown-kind path. ``e2b`` is the next rung
        # of the ladder and is genuinely not built, so it plays the same role
        # the old exemplar did. The assertion itself is untouched.
        with pytest.raises(BackendUnavailable, match="unknown ExecutionBackend kind"):
            build_execution_backend(kind="e2b")

    def test_unknown_env_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(BACKEND_ENV, "nonexistent")
        with pytest.raises(BackendUnavailable, match="unknown ExecutionBackend kind"):
            build_execution_backend()

    def test_error_message_mentions_valid_kinds(self) -> None:
        with pytest.raises(BackendUnavailable, match="local"):
            build_execution_backend(kind="bogus")


# ---------------------------------------------------------------------------
# Runner-kwargs forwarding (the cascade reconciliation)
# ---------------------------------------------------------------------------


class TestRunnerKwargsForwarding:
    """The factory accepts ``seal_on_complete`` / ``retrieval_substrate`` so the
    cascade launch site can forward without ``TypeError``."""

    def test_seal_on_complete_accepted(self) -> None:
        backend = build_execution_backend(seal_on_complete=False)
        assert isinstance(backend, LocalProcessBackend)

    def test_retrieval_substrate_accepted(self) -> None:
        backend = build_execution_backend(retrieval_substrate=object())
        assert isinstance(backend, LocalProcessBackend)

    def test_both_forwarded(self) -> None:
        backend = build_execution_backend(
            seal_on_complete=False,
            retrieval_substrate=object(),
        )
        assert isinstance(backend, LocalProcessBackend)

    def test_extra_kwargs_do_not_raise(self) -> None:
        # Forward-compat: unexpected kwargs are logged, not errors.
        backend = build_execution_backend(some_future_kwarg="value")
        assert isinstance(backend, LocalProcessBackend)


# ---------------------------------------------------------------------------
# Constant
# ---------------------------------------------------------------------------


class TestConstants:
    def test_backend_env_value(self) -> None:
        assert BACKEND_ENV == "ANTIEK_EXEC_BACKEND"


# ---------------------------------------------------------------------------
# kind="docker" — registered, and loud when the dependency is missing
# ---------------------------------------------------------------------------


def _empty_path_env(monkeypatch: pytest.MonkeyPatch, bindir: Path) -> None:
    """Point ``PATH`` at an empty directory so the ``docker`` CLI cannot be
    found. This is the dependency-absent case with no daemon in the loop and
    no mocking of the code under test: the real ``_SubprocessDockerClient``
    really fails to spawn, so the assertion holds on any machine, with or
    without Docker installed."""
    monkeypatch.setenv("PATH", str(bindir))


class TestFactoryDockerKind:
    """``docker`` reaches its own branch, and an unusable daemon is refused."""

    def test_docker_is_a_registered_kind(self) -> None:
        """The valid-kinds list the error message prints now names docker — the
        one-line proof that the kind is wired, needing no daemon."""
        with pytest.raises(BackendUnavailable) as excinfo:
            build_execution_backend(kind="e2b")
        assert "docker" in str(excinfo.value)

    def test_docker_kind_raises_when_cli_absent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _empty_path_env(monkeypatch, tmp_path)
        with pytest.raises(BackendUnavailable, match="docker unavailable"):
            build_execution_backend(kind="docker")

    def test_docker_env_var_raises_when_cli_absent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The env route is the operator-facing one, so it gets its own test."""
        _empty_path_env(monkeypatch, tmp_path)
        monkeypatch.setenv(BACKEND_ENV, "docker")
        with pytest.raises(BackendUnavailable, match="docker unavailable"):
            build_execution_backend()

    def test_docker_kind_never_downgrades_to_local(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The rule this seam exists for: an unavailable docker backend yields
        nothing at all, never a local backend wearing docker's name. Asserted
        against the raise rather than a returned object, so a future silent
        fallback fails here loudly."""
        _empty_path_env(monkeypatch, tmp_path)
        with pytest.raises(BackendUnavailable):
            backend = build_execution_backend(kind="docker")
            # Unreached while the contract holds; if a fallback is ever
            # introduced, this pins the failure to the real mistake.
            raise AssertionError(
                f"factory downgraded docker to {type(backend).__name__} "
                f"(name={backend.name!r}) instead of raising"
            )

    def test_docker_kind_on_this_machine_raises_or_returns_docker(self) -> None:
        """Unmocked, against whatever docker state this host actually has. On a
        machine with no reachable daemon (the swarm host) this is the real
        BackendUnavailable path end to end; on a host with docker up it proves
        the branch returns a genuine DockerBackend. Neither branch may produce
        a LocalProcessBackend."""
        try:
            backend = build_execution_backend(kind="docker")
        except BackendUnavailable as exc:
            assert "docker unavailable" in str(exc)
            return
        assert backend.name == "docker"
        assert not isinstance(backend, LocalProcessBackend)


# ---------------------------------------------------------------------------
# The default path does not import the docker adapter
# ---------------------------------------------------------------------------


def _factory_imports() -> tuple[list[ast.stmt], list[ast.stmt]]:
    """Every import statement in ``factory.py``, split into the ones at module
    level and the ones nested inside a function body."""
    tree = ast.parse(Path(factory_module.__file__).read_text(encoding="utf-8"))
    nested_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Import | ast.ImportFrom):
                    nested_ids.add(id(inner))
    module_level: list[ast.stmt] = []
    nested: list[ast.stmt] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            (nested if id(node) in nested_ids else module_level).append(node)
    return module_level, nested


def _mentions_docker(node: ast.stmt) -> bool:
    return "docker" in ast.dump(node).lower()


class TestDefaultPathDoesNotImportDocker:
    """The docker adapter is pulled in only when docker is actually asked for."""

    def test_factory_binds_no_docker_symbol_at_module_level(self) -> None:
        assert "DockerBackend" not in vars(factory_module)

    def test_factory_docker_import_is_nested_in_its_branch(self) -> None:
        module_level, nested = _factory_imports()
        assert not [n for n in module_level if _mentions_docker(n)], (
            "factory.py imports docker at module level; the import belongs "
            "inside the docker branch"
        )
        assert [n for n in nested if _mentions_docker(n)], (
            "expected a function-local docker import in factory.py — the "
            "docker branch is missing"
        )

    def test_default_build_imports_no_docker_module(self) -> None:
        """Run the default build in a fresh interpreter with the adapter
        evicted from ``sys.modules`` first, then assert it is still absent.
        Eviction is what makes this a real measurement: the package
        ``__init__`` re-exports ``DockerBackend`` eagerly, so without it the
        check would pass on the package's import rather than on the factory's
        behavior."""
        root = Path(__file__).resolve().parents[1]
        script = (
            "import sys\n"
            "from runtime.exec_backend import factory\n"
            f"sys.modules.pop({_DOCKER_MODULE!r}, None)\n"
            "backend = factory.build_execution_backend()\n"
            f"print(backend.name, {_DOCKER_MODULE!r} in sys.modules)\n"
        )
        env = dict(os.environ)
        env.pop(BACKEND_ENV, None)
        env["PYTHONPATH"] = str(root)
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "local False", proc.stdout
