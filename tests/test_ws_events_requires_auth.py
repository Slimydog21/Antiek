"""``/ws/events`` must not stream the event bus to an unauthenticated peer.

On 2026-09-20 a credential-free handshake from an arbitrary Origin was
answered by PRODUCTION with ``101 Switching Protocols``:

    curl --http1.1 -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' \\
         -H 'Sec-WebSocket-Key: ...' -H 'Origin: https://attacker.example' \\
         https://api.antiek.ai/ws/events
    -> HTTP/1.1 101 Switching Protocols

The cause is structural, not a forgotten check. The operator gate is
installed with ``@app.middleware("http")``; Starlette's ``BaseHTTPMiddleware``
opens with ``if scope["type"] != "http": await self.app(...); return``, so a
WebSocket scope bypasses it entirely — and ``CORSMiddleware`` skips the same
way, so ``Origin`` is never checked either. Every HTTP route was gated while
the socket beside them was open.

These tests turn enforcement ON, which is what production runs. The rest of
the suite leaves it off, so the socket is reachable there and stays reachable
— that escape is deliberate and is asserted below too, because silently
requiring auth in local dev would be its own regression.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from interfaces.research.api import create_app
from substrate.auth.magic_link import mint_session_cookie

_EMAIL = "owner@example.test"


@pytest.fixture
def enforced(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _EMAIL)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "test-secret-not-a-real-key")
    with TestClient(create_app(register_wrestling=False)) as client:
        yield client


def test_unauthenticated_websocket_is_refused(enforced: TestClient) -> None:
    """No cookie -> the peer must never reach the bus."""
    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        enforced.websocket_connect("/ws/events"),
    ):
        pass
    assert excinfo.value.code == 1008, (
        f"expected policy-violation close 1008, got {excinfo.value.code}"
    )


def test_garbage_cookie_is_refused(enforced: TestClient) -> None:
    """A forged or stale cookie must not pass."""
    enforced.cookies.set("ANTIEK_SESSION", "not-a-real-signed-cookie")
    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        enforced.websocket_connect("/ws/events"),
    ):
        pass
    assert excinfo.value.code == 1008


def test_non_allowlisted_email_is_refused(enforced: TestClient) -> None:
    """A validly-signed cookie for someone off the allowlist must not pass."""
    enforced.cookies.set(
        "ANTIEK_SESSION",
        mint_session_cookie(user_id="intruder", email="someone.else@example.test"),
    )
    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        enforced.websocket_connect("/ws/events"),
    ):
        pass
    assert excinfo.value.code == 1008


def test_allowlisted_session_cookie_is_accepted(enforced: TestClient) -> None:
    """The real frontend path must keep working.

    The session cookie is issued Domain=.antiek.ai / SameSite=Lax, so a
    browser handshake from antiek.ai to api.antiek.ai is same-site and sends
    it. If this test fails the fix has locked out the product.
    """
    enforced.cookies.set(
        "ANTIEK_SESSION",
        mint_session_cookie(user_id="owner", email=_EMAIL),
    )
    with enforced.websocket_connect("/ws/events") as ws:
        assert ws is not None


def test_socket_stays_open_when_enforcement_is_disabled() -> None:
    """The deliberate local-dev escape, asserted so it cannot drift shut."""
    client = TestClient(create_app(register_wrestling=False))
    with client, client.websocket_connect("/ws/events") as ws:
        assert ws is not None
