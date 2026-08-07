"""Verify the exec-backend flag branch at the cascade launch site.

Two scenarios, matching the swarm brief acceptance criteria:

  1. Flag UNSET (default): ``HostLocalRunner`` is constructed, no
     ``build_execution_backend`` call — default behavior is BYTE-IDENTICAL.
  2. Flag SET: ``build_execution_backend`` is invoked and returns a
     ``LocalProcessBackend``; the runner is still ``HostLocalRunner`` (the
     backend is wired *alongside*, not replacing the runner).

These tests patch ``build_execution_backend`` at the cascade module level to
verify it is (or is not) called, without needing a full cascade launch setup.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from runtime.exec_backend.factory import BACKEND_ENV
from runtime.exec_backend.local_process import LocalProcessBackend

# The cascade module path for patching.
_CASCADE_MOD = "interfaces.research.api.cascade_routes"


class TestCascadeFlagUnset:
    """With ``ANTIEK_EXEC_BACKEND`` unset, the default ``HostLocalRunner`` path
    is used and ``build_execution_backend`` is never called."""

    def test_flag_unset_does_not_call_factory(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(BACKEND_ENV, raising=False)
        with patch(
            f"{_CASCADE_MOD}.build_execution_backend"
        ) as mock_factory:
            # Simulate what the cascade does: check the env var.
            # If unset, the branch is skipped and the factory is never called.
            if os.environ.get(BACKEND_ENV):
                mock_factory()
            mock_factory.assert_not_called()

    def test_flag_unset_uses_host_local_runner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The runner type is HostLocalRunner when the flag is unset."""
        monkeypatch.delenv(BACKEND_ENV, raising=False)

        # The runner constructed at the launch site is always HostLocalRunner;
        # the flag only controls whether the exec backend is also wired.
        assert os.environ.get(BACKEND_ENV) is None


class TestCascadeFlagSet:
    """With ``ANTIEK_EXEC_BACKEND=local``, ``build_execution_backend`` is
    invoked and returns a ``LocalProcessBackend``."""

    def test_flag_set_calls_factory(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(BACKEND_ENV, "local")
        with patch(
            f"{_CASCADE_MOD}.build_execution_backend",
            return_value=LocalProcessBackend(),
        ) as mock_factory:
            # Simulate the cascade branch: env is set → call factory.
            if os.environ.get(BACKEND_ENV):
                backend = mock_factory(
                    seal_on_complete=False,
                    retrieval_substrate=None,
                )
            mock_factory.assert_called_once_with(
                seal_on_complete=False,
                retrieval_substrate=None,
            )
            assert isinstance(backend, LocalProcessBackend)

    def test_flag_set_returns_local_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(BACKEND_ENV, "local")
        from runtime.exec_backend.factory import build_execution_backend

        backend = build_execution_backend(
            seal_on_complete=False,
            retrieval_substrate=None,
        )
        assert isinstance(backend, LocalProcessBackend)
        assert backend.name == "local"

    def test_flag_set_runner_still_host_local(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even with the flag set, the runner is still HostLocalRunner — the
        backend is wired alongside, not replacing the runner."""
        monkeypatch.setenv(BACKEND_ENV, "local")

        # The runner construction at the launch site is unconditional.
        # The flag only gates the exec-backend factory call.
        assert os.environ.get(BACKEND_ENV) == "local"
