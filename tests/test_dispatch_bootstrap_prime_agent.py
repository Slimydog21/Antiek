"""SPR-01 Task 4: the Prime dispatch provider registers on the NORMAL path.

``substrate/dispatch/providers/prime_agent.py`` registered itself only at its own
import time, and nothing on the production path imported it — so with
``ANTIEK_PRIME_AGENT_RLM_ENABLED=1`` set, ``register_default_providers()`` (what
``create_app`` calls) still returned no ``prime_agent`` and prod ``/health``
listed none. These tests pin the flag in both directions through the real
bootstrap entry point, on a clean registry.
"""

from __future__ import annotations

import pytest

from substrate.dispatch.providers.bootstrap import register_default_providers
from substrate.dispatch.router import get_provider, reset_provider_registry


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test starts from an empty registry so order doesn't matter."""
    reset_provider_registry()
    yield
    reset_provider_registry()


def test_flag_set_registers_prime_agent_on_the_default_path(monkeypatch) -> None:
    monkeypatch.setenv("ANTIEK_PRIME_AGENT_RLM_ENABLED", "1")
    registered = register_default_providers(quiet=True)
    assert "prime_agent" in registered
    assert get_provider("prime_agent").name == "prime_agent"


def test_flag_unset_leaves_prime_agent_out(monkeypatch) -> None:
    monkeypatch.delenv("ANTIEK_PRIME_AGENT_RLM_ENABLED", raising=False)
    registered = register_default_providers(quiet=True)
    assert "prime_agent" not in registered
    with pytest.raises(KeyError):
        get_provider("prime_agent")


def test_only_subset_can_select_prime_agent(monkeypatch) -> None:
    """The smoke runner's ``only=`` filter must know the new entry by name."""
    monkeypatch.setenv("ANTIEK_PRIME_AGENT_RLM_ENABLED", "1")
    assert register_default_providers(quiet=True, only=["prime_agent"]) == {"prime_agent"}
