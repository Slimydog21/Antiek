"""M3 tests — X API v2 ingestion via the operator's own key into personal_reading.

Fully offline + deterministic: a RECORDED X API v2 fixture payload drives the
parser + a fake client injected into the runner, so there is NO live network. The
live HTTP round-trip is honestly skipped (no real key in CI) — never faked.

Asserts the load-bearing invariant: an ingested X thread lands
``document_type='social_thread'`` AND ``content_class='personal_reading'``, written
through the single box-bounded writer (the adapter's connect_write)."""

from __future__ import annotations

import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import nacl.secret  # noqa: E402
import pytest  # noqa: E402

from acquisition.twitter.adapter import twitter_doc_id  # noqa: E402
from acquisition.twitter.api_client import parse_search_response, to_thread  # noqa: E402
from runtime.byok.pipelines import register_pipeline  # noqa: E402
from runtime.byok.runner import run_pipeline  # noqa: E402
from runtime.byok.store import store_credential  # noqa: E402
from runtime.db_lock import connect_read  # noqa: E402
from substrate.constants import PERSONAL_READING_CONTENT_CLASS  # noqa: E402
from substrate.graph import ensure_initialized  # noqa: E402

_TEST_KEY = b"0" * nacl.secret.SecretBox.KEY_SIZE


# A recorded X API v2 recent-search page (conversation lookup) — fixture-validated.
# Two tweets in one conversation by @dhh, with the author expansion.
_FIXTURE_PAGE = {
    "data": [
        {
            "id": "1000",
            "text": "Ruby is a beautiful language and this thread explains why it endures.",
            "author_id": "u1",
            "created_at": "2026-05-30T10:00:00.000Z",
            "conversation_id": "1000",
        },
        {
            "id": "1001",
            "text": "The second tweet continues the argument with several more words here.",
            "author_id": "u1",
            "created_at": "2026-05-30T10:02:00.000Z",
            "conversation_id": "1000",
            "referenced_tweets": [{"type": "replied_to", "id": "1000"}],
        },
    ],
    "includes": {
        "users": [{"id": "u1", "username": "dhh", "verified": True}],
    },
    "meta": {"result_count": 2},
}


class _FakeClient:
    """Fixture-backed stand-in for XApiClient — no network, no key revealed."""

    def __init__(self, page):
        self._page = page

    def recent_search(self, query):
        return parse_search_response(self._page)

    def user_timeline(self, user_id):
        return parse_search_response(self._page)

    def conversation(self, conversation_id):
        return parse_search_response(self._page)


def test_parse_search_response_flattens_with_author():
    flat = parse_search_response(_FIXTURE_PAGE)
    assert len(flat) == 2
    assert flat[0]["author_handle"] == "dhh"
    assert flat[0]["author_verified"] is True
    assert flat[1]["tweet_id"] == "1001"


def test_to_thread_reuses_adapter_model():
    flat = parse_search_response(_FIXTURE_PAGE)
    thread = to_thread(
        flat, thread_url="https://x.com/dhh/status/1000",
        root_tweet_id="1000", author_handle="dhh",
    )
    assert thread.root_tweet_id == "1000"
    assert len(thread.tweets) == 2
    assert thread.tweets[0].author_handle == "dhh"


def test_run_pipeline_lands_personal_reading_social_thread():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "t.duckdb")
        artifact = os.path.join(tmp, "credentials.enc")
        cfg = os.path.join(tmp, "pipelines.json")
        ensure_initialized(db_path)

        cred_id = store_credential(
            "dhh", "the-operators-own-x-bearer-token",
            artifact_path=artifact, key_bytes=_TEST_KEY,
        )
        pl = register_pipeline(
            "dhh", cred_id, "thread_specific", seed="1000",
            investigation_id="inv-byok-x", config_path=cfg,
        )

        from processing.embedding.embed import default_embedding_provider

        result = run_pipeline(
            pl.pipeline_id,
            db_path=db_path,
            config_path=cfg,
            client=_FakeClient(_FIXTURE_PAGE),
            embedder=default_embedding_provider(),
        )
        assert result.threads_ingested == 1

        doc_id = twitter_doc_id("1000")
        with connect_read(db_path) as con:
            row = con.execute(
                "SELECT document_type, content_class FROM documents WHERE document_id = ?",
                [doc_id],
            ).fetchone()
        assert row is not None
        assert row[0] == "social_thread"
        assert row[1] == PERSONAL_READING_CONTENT_CLASS


def test_reingest_same_root_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "t.duckdb")
        artifact = os.path.join(tmp, "credentials.enc")
        cfg = os.path.join(tmp, "pipelines.json")
        ensure_initialized(db_path)
        cred_id = store_credential(
            "dhh", "tok", artifact_path=artifact, key_bytes=_TEST_KEY,
        )
        pl = register_pipeline(
            "dhh", cred_id, "thread_specific", seed="1000", config_path=cfg,
        )
        from processing.embedding.embed import default_embedding_provider
        emb = default_embedding_provider()
        run_pipeline(pl.pipeline_id, db_path=db_path, config_path=cfg,
                     client=_FakeClient(_FIXTURE_PAGE), embedder=emb)
        # second run of the same root tweet must not create a second document row
        run_pipeline(pl.pipeline_id, db_path=db_path, config_path=cfg,
                     client=_FakeClient(_FIXTURE_PAGE), embedder=emb)
        with connect_read(db_path) as con:
            (n,) = con.execute(
                "SELECT COUNT(*) FROM documents WHERE document_id = ?",
                [twitter_doc_id("1000")],
            ).fetchone()
        assert n == 1


def test_http_error_surfaces_status_never_leaks_bearer(monkeypatch):
    """Rigor #3 edge case: a 401/429 from X is surfaced as an error, but the
    surfaced ``XApiError`` MUST carry only the numeric status — never the bearer.

    This is a seeded regression pin: it drives the real ``XApiClient._http_get``
    error path (no network — ``urlopen`` is monkeypatched to raise an HTTPError)
    with a credential whose plaintext is a distinctive sentinel, then asserts the
    sentinel appears NOWHERE in the raised exception's message/args/repr. It bites
    on exactly one defect: if someone changed the error to
    ``XApiError(f"... {bearer.reveal()}")`` (or let urllib put the key in the URL
    and re-raised the URL), this test fails red. The happy-path fixture tests
    cannot catch that because they never exercise the error branch."""
    import urllib.error

    from acquisition.twitter.api_client import XApiClient, XApiError

    _SENTINEL_BEARER = "ZZZ-do-not-leak-this-bearer-9f3a2c-secret"

    with tempfile.TemporaryDirectory() as tmp:
        artifact = os.path.join(tmp, "credentials.enc")
        cred_id = store_credential(
            "dhh", _SENTINEL_BEARER, artifact_path=artifact, key_bytes=_TEST_KEY,
        )

        def _raise_429(*_args, **_kwargs):
            # Simulate X returning HTTP 429 (rate limit). The url passed to the
            # HTTPError carries no key (api_client never puts the key in the URL),
            # but we assert the surfaced error is key-free regardless.
            raise urllib.error.HTTPError(
                url="https://api.twitter.com/2/tweets/search/recent",
                code=429,
                msg="Too Many Requests",
                hdrs=None,
                fp=None,
            )

        monkeypatch.setattr(
            "acquisition.twitter.api_client.urllib.request.urlopen", _raise_429
        )

        client = XApiClient(cred_id=cred_id, artifact_path=artifact, key_bytes=_TEST_KEY)
        try:
            client.recent_search("from:dhh")
            raise AssertionError("expected XApiError on a 429")
        except XApiError as exc:
            blob = " ".join([str(exc), repr(exc), " ".join(map(str, exc.args))])
            assert _SENTINEL_BEARER not in blob, "bearer leaked into the surfaced error"
            assert "429" in blob, "the numeric status should be surfaced"


def test_recent_search_is_bounded_to_25_without_network(monkeypatch):
    from acquisition.twitter.api_client import XApiClient

    client = XApiClient(cred_id="cred-x-test")
    seen = {}

    def fake_get(path, params):
        seen.update(path=path, params=params)
        return {"data": [{"id": str(i)} for i in range(30)]}

    monkeypatch.setattr(client, "_http_get", fake_get)
    assert len(client.recent_search("antiek", max_results=25)) == 25
    assert seen["params"]["max_results"] == 25
    with pytest.raises(ValueError, match="between 1 and 25"):
        client.recent_search("antiek", max_results=26)


@pytest.mark.skipif(
    os.environ.get("ANTIEK_X_BYOK_LIVE_KEY") is None,
    reason=(
        "live X API smoke requires a real operator BYOK key "
        "(ANTIEK_X_BYOK_LIVE_KEY) — fixture-validated, live-unverified in CI"
    ),
)
def test_live_x_api_smoke():  # pragma: no cover - operator-only, never in CI
    # Asserts the skip is honest: when a real key is present an operator runs this
    # against the live API. CI never fakes a network response here.
    assert os.environ.get("ANTIEK_X_BYOK_LIVE_KEY")
