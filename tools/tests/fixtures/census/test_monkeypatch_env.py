"""Fixture: a MONKEYPATCH test file (environmental override + project fake).

``test_reads_env`` takes ``monkeypatch`` and sets an env var — this is an
ENVIRONMENTAL override (configuring the world, not mocking a collaborator's
behavior), and the test still asserts on the unit's real output, so it is
``behavior`` with ``uses_mock=True`` and an environmental target.

``test_uses_local_fake`` builds a project-local ``FakeProvider`` (a behavioral
collaborator fake) and asserts on the real returned value — ``behavior`` with a
behavioral mock target. This is the steelman case: a behavioral mock present,
but the test asserts behavior, so it is NOT structure.

Parsed, not executed (see test_pure_behavior.py header).
"""

from __future__ import annotations

import os


class FakeProvider:
    """A project-local fake of the provider collaborator."""

    def complete(self, prompt: str) -> str:
        return f"echo:{prompt}"


def read_flag() -> bool:
    return os.environ.get("MY_FLAG") == "on"


def run(provider, prompt: str) -> str:
    return provider.complete(prompt)


def test_reads_env(monkeypatch):
    monkeypatch.setenv("MY_FLAG", "on")
    assert read_flag() is True


def test_uses_local_fake():
    provider = FakeProvider()
    assert run(provider, "hi") == "echo:hi"
