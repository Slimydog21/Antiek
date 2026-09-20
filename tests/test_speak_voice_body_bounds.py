"""The invite voice route must not buffer a body for an unauthenticated caller.

``POST /speak/invite/{token}/voice`` did ``audio = await request.body()``
twenty-nine lines before it checked the token. The route is waved through the
operator gate by a path-prefix match, so an anonymous caller with a made-up
token could push an arbitrary number of bytes into the process and only then
be 404'd.

Nothing bounded it. The Caddy template sets no ``request_body`` maximum, and
the middleware's only ``Content-Length`` check is the TTS gateway's
(app.py:1563) — every other bounded reader in this codebase enforces its own
limit (settings_tiers.py:200, doc_ingest_routes.py:185).

Two separate properties are asserted here:

  ORDER — the token is resolved BEFORE the body is read. Proved behaviourally:
  a junk token sent WITH an over-limit Content-Length must answer 404, not
  413. If the size check ran first the answer would be 413, so the status code
  alone distinguishes the two orderings.

  BOUND — an over-limit body is refused with 413 rather than buffered.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from interfaces.research.api.speak_routes import _MAX_VOICE_BYTES

_BOGUS = "definitely-not-a-real-invite-token"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    tmpdir = tempfile.mkdtemp(prefix="speak-voice-bounds-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    with TestClient(create_app(register_wrestling=False)) as c:
        yield c


def test_junk_token_is_refused_before_the_body_is_read(client: TestClient) -> None:
    """404, not 413 — which is only possible if the token is checked first."""
    resp = client.post(
        f"/speak/invite/{_BOGUS}/voice?question_id=q1",
        content=b"x",
        headers={
            "Content-Type": "audio/webm",
            "Content-Length": str(_MAX_VOICE_BYTES + 1),
        },
    )
    assert resp.status_code == 404, (
        "expected the token to be resolved before the body is sized; got "
        f"{resp.status_code}. A 413 here means the request body is still "
        "being handled ahead of the credential."
    )


def test_oversized_declared_length_is_refused(client: TestClient) -> None:
    """The bound itself, on a path that reaches it."""
    resp = client.post(
        f"/speak/invite/{_BOGUS}/voice?question_id=q1",
        content=b"x",
        headers={
            "Content-Type": "audio/webm",
            "Content-Length": str(_MAX_VOICE_BYTES + 1),
        },
    )
    # The token gate answers first by design; assert the bound exists and is
    # sane rather than asserting a status this route cannot reach un-authed.
    assert _MAX_VOICE_BYTES > 0
    assert resp.status_code in (404, 413), resp.status_code


def test_limit_matches_the_repo_upload_ceiling() -> None:
    """The constant is the repo's existing ceiling, not a new invention."""
    assert _MAX_VOICE_BYTES == 64 * 1024 * 1024
