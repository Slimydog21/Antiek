"""Opt the BYOK OAuth tests into the Claude capability gate.

``runtime/byok/anthropic_oauth.py`` performs a Claude.ai credential flow, so it is
DISABLED unless ``ANTIEK_BYOK_CLAUDE=1`` and the operator's own OAuth
registration is present, and it carries no client_id of its own.  That is a
compliance gate, not a test inconvenience, so the tests that exercise the flow
opt in here — explicitly, and scoped to this directory — rather than the gate
being weakened to keep them green.

Deliberately NOT process-wide: enabling a credential-accepting capability for the
whole suite would hide it from every test that should see it closed.  The
off-state assertions live in ``test_byok_claude_capability_gate.py``.

The client id and secret below are TEST values.  They are not a registration,
and nothing reaches the network: every test mocks the transport.
"""

from __future__ import annotations

import pytest

TEST_CLIENT_ID = "test-client-id-not-a-real-registration"
TEST_CLIENT_SECRET = "test-client-secret-not-a-real-registration"


@pytest.fixture(autouse=True)
def _enable_byok_claude_capability(monkeypatch: pytest.MonkeyPatch):
    """Set the flag and a complete registration for tests in this directory."""
    monkeypatch.setenv("ANTIEK_BYOK_CLAUDE", "1")
    monkeypatch.setenv("ANTIEK_ANTHROPIC_OAUTH_CLIENT_ID", TEST_CLIENT_ID)
    monkeypatch.setenv("ANTIEK_ANTHROPIC_OAUTH_CLIENT_SECRET", TEST_CLIENT_SECRET)
    yield
