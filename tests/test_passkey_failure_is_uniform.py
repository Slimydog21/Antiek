"""Passkey verification must not answer "is this credential registered?".

The two failure modes are raised with different text in `substrate/auth/passkeys.py:298-313`:

    a missing candidate        "This passkey is not registered with Antiek."
    a stored candidate, bad proof  "Antiek could not verify that passkey. Try again."

and `interfaces/research/api/auth.py` published both verbatim. Measured, a synthetic stored
credential and an unregistered id returned different text, both 400 -- a membership oracle for
anyone who supplies a credential id. The lane that found it was explicit that this is a small
oracle and not a bypass: high-entropy ids make brute-force enumeration impractical.

The module's own docstring already states the correct posture for the sibling route --
"Always 200 with the same shape even for non-allowlisted addresses, to avoid enumerating valid
operators" -- and the passkey path did not follow it.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from substrate.auth import PasskeyError


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    tmpdir = tempfile.mkdtemp(prefix="passkey-oracle-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    from interfaces.research.api.app import create_app

    with TestClient(create_app(register_wrestling=False)) as c:
        yield c


def _message_for(client: TestClient, monkeypatch, exc: PasskeyError) -> str:
    import interfaces.research.api.auth as auth_mod

    def _raise(**_kwargs):
        raise exc

    monkeypatch.setattr(auth_mod, "complete_authentication", _raise)
    resp = client.post(
        "/auth/passkey/login/verify",
        json={
            # 16-character minimum is enforced by the request model.
            "ceremony_id": "ceremony-id-0123456789",
            "credential": {"id": "x", "rawId": "x", "response": {}},
        },
    )
    assert resp.status_code == 400, resp.text
    return str(resp.json()["detail"]["message"])


def test_both_passkey_failures_publish_the_same_text(client, monkeypatch) -> None:
    """The property that closes the oracle: one message, regardless of cause."""
    registered = _message_for(
        client, monkeypatch, PasskeyError("Antiek could not verify that passkey. Try again.")
    )
    unregistered = _message_for(
        client, monkeypatch, PasskeyError("This passkey is not registered with Antiek.")
    )

    assert registered == unregistered, (
        "the two failure modes are distinguishable in the response, which answers "
        f"'is this credential registered?': {registered!r} vs {unregistered!r}"
    )
    assert "not registered" not in registered
