"""Tests for ``runtime.exec_backend.factory`` — the ``build_execution_backend`` seam.

Acceptance criteria from the swarm brief:

  * Factory default (``ANTIEK_EXEC_BACKEND`` unset) returns a ``LocalProcessBackend``.
  * Explicit ``kind="local"`` returns a ``LocalProcessBackend``.
  * Unknown kind raises ``BackendUnavailable`` (no silent downgrade).
  * ``seal_on_complete`` / ``retrieval_substrate`` kwargs are accepted without
    ``TypeError`` (the cascade launch site forwards them).
  * ``BACKEND_ENV`` is ``"ANTIEK_EXEC_BACKEND"``.
"""

from __future__ import annotations

import pytest

from runtime.exec_backend.factory import BACKEND_ENV, build_execution_backend
from runtime.exec_backend.interface import BackendUnavailable, ExecutionBackend
from runtime.exec_backend.local_process import LocalProcessBackend

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
        with pytest.raises(BackendUnavailable, match="unknown ExecutionBackend kind"):
            build_execution_backend(kind="docker")

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
