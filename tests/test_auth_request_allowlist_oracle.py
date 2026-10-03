"""An allowlisted address must fail the same way an unlisted one succeeds.

`/auth/request`'s docstring:

    "Always 200 with the same shape even for non-allowlisted addresses, to avoid enumerating
     valid operators."

That was true on the success path. On the failure path the route answered 503 for an allowlisted
address and 200 for everyone else, so the status code answered the question the docstring promises
not to answer. Fixing that by redacting the provider's message left the oracle intact -- "redacting
the text alone preserves the oracle" -- and the replacement guarded only `provider.send()`, while
three calls in that branch run exclusively for allowlisted addresses:

    mint_magic_link_token(email)     unguarded
    _build_magic_link(...)           unguarded
    get_email_provider()             unguarded, and raises on a misconfigured provider -- the
                                     ordinary state of a dev box

Each of those produced a 500 that an unlisted address never sees. This file pins the property rather
than any one exception: whatever breaks inside the allowlisted branch, both addresses answer alike.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    tmpdir = tempfile.mkdtemp(prefix="allowlist-oracle-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "operator@example.test")
    from interfaces.research.api.app import create_app

    with TestClient(create_app(register_wrestling=False)) as c:
        yield c


def _status_for(client: TestClient, email: str) -> int:
    return client.post("/auth/request", json={"email": email}).status_code


def test_provider_construction_failure_is_indistinguishable_from_unlisted(client, monkeypatch) -> None:
    """The reviewer's finding: `get_email_provider()` raised 500 for allowlisted only."""
    import interfaces.research.api.auth as auth_mod

    def _boom(*_args, **_kwargs):
        raise RuntimeError("mail provider is not configured")

    monkeypatch.setattr(auth_mod, "get_email_provider", _boom)

    allowlisted = _status_for(client, "operator@example.test")
    unlisted = _status_for(client, "stranger@example.test")

    assert allowlisted == unlisted, (
        "the two addresses answer differently when the provider cannot be built, which "
        f"discloses allowlist membership: {allowlisted} vs {unlisted}"
    )
    assert allowlisted == 200, allowlisted


def test_a_malformed_token_mint_failure_is_indistinguishable_too(client, monkeypatch) -> None:
    """The second unguarded call in the same branch."""
    import interfaces.research.api.auth as auth_mod

    def _boom(*_args, **_kwargs):
        raise RuntimeError("token minting unavailable")

    monkeypatch.setattr(auth_mod, "mint_magic_link_token", _boom)

    assert _status_for(client, "operator@example.test") == _status_for(client, "stranger@example.test")


def test_the_success_path_still_returns_the_attempt(client) -> None:
    """The control: guarding the branch must not swallow the normal response."""
    resp = client.post("/auth/request", json={"email": "operator@example.test"})

    assert resp.status_code == 200
    assert set(resp.json()) >= {"sent", "attempt_id", "claim_secret"}
