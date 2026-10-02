"""A non-ASCII token must not reveal whether dev-login is enabled.

The route states its posture in a comment:

    "Constant-time compare; an empty/incorrect token is also a 404 so a probe can't
     distinguish 'feature off' from 'wrong token'."

`secrets.compare_digest` accepts str only when both operands are ASCII and raises TypeError
otherwise, so a non-ASCII token reached the exception handler instead of the 404. Measured by the
`astra5-postures` lane: the same input returned **500 when the feature was enabled and 404 when it
was disabled**, which discloses the flag while the comment promises it does not.

Comparing encoded bytes keeps the constant-time property and accepts any input, so both states
answer identically.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


def _client(monkeypatch: pytest.MonkeyPatch, token: str | None) -> TestClient:
    tmpdir = tempfile.mkdtemp(prefix="dev-login-oracle-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    if token is None:
        monkeypatch.delenv("ANTIEK_DEV_LOGIN_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ANTIEK_DEV_LOGIN_TOKEN", token)
    from interfaces.research.api.app import create_app

    return TestClient(create_app(register_wrestling=False))


NON_ASCII = "\u00fcn\u00efc\u00f8de-wrong-token"


@pytest.mark.parametrize("configured", [None, "a-real-ascii-dev-token"])
def test_non_ascii_token_answers_the_same_whether_enabled_or_not(monkeypatch, configured) -> None:
    """The property the route's own comment claims, tested for the input that broke it."""
    with _client(monkeypatch, configured) as client:
        resp = client.get("/auth/dev-login", params={"token": NON_ASCII})

    assert resp.status_code == 404, (
        f"a non-ASCII token must be an ordinary 404, not {resp.status_code}; a distinct "
        "status here discloses whether the feature is enabled"
    )


def test_a_correct_token_still_works_when_enabled(monkeypatch) -> None:
    """The control: the fix must not break the feature it guards."""
    good = "a-real-ascii-dev-token"
    with _client(monkeypatch, good) as client:
        resp = client.get("/auth/dev-login", params={"token": good}, follow_redirects=False)

    assert resp.status_code in (200, 302, 303, 307), resp.status_code
