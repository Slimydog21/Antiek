"""X (Twitter) API v2 client for BYOK ingestion (Personal-Reading Lane SPR-08, M3).

Wraps a small slice of the X API v2 — recent-search, a user timeline, and a
conversation/thread lookup — behind a tiny interface. The bearer/key is the
OPERATOR's OWN BYOK credential: it is read via :func:`runtime.byok.load_credential`
AT CALL TIME, used only to build the ``Authorization`` header, and is NEVER passed
to a logger, ``print``, ``emit_typed``, an exception message, or any return value.

LEGITIMACY (defensibility / rigor #5): this client only ever authenticates with
the operator's OWN developer key (BYOK), which makes the fetch an AUTHORIZED source
under X's developer agreement. There is NO unauthenticated scrape path and NO
shared platform key here — those would be Terms-of-Service breaches independent of
the copyright lane. The content it pulls lands ``personal_reading`` (owner-only,
never served / attributed) AND is excluded from training per X's no-training
clause (pinned by M4).

ENDPOINT SHAPES — fixture-validated, live-unverified (rigor #1, intellectual
honesty). The request paths / param names / response envelope below follow the
public X API v2 shape (``/2/tweets/search/recent``, ``/2/users/:id/tweets``,
``/2/tweets/search/recent?query=conversation_id:<id>``) FROM MEMORY, not from a
freshly verified live doc. The deterministic tests drive this client with RECORDED
fixture JSON, so the mapping logic is proven; the live HTTP round-trip is
``@pytest.mark.skipif``-skipped in CI (no real key) and must be smoke-tested by
the operator before relying on it. ``parse_search_response`` / ``to_thread`` are
the pure, fully-tested seam; ``_http_get`` is the thin, live-unverified edge.

§16 BOX-BOUNDED: this client does NO DB writes and opens NO DB connection — it
only fetches + parses. The single-writer write happens in ``runner.py`` through
``acquisition/twitter/adapter.ingest_twitter_thread`` →
``runtime.db_lock.connect_write``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from acquisition.twitter.adapter import Tweet, TwitterThread
from runtime.connectors.base import ConnectorDescriptor, KeyShape, PasteKeyConnector, RateSpec
from runtime.connectors.rate_governor import VendorRateGovernor

_API_BASE = "https://api.twitter.com/2"

# Product-level bounds for the research-tool surface. Even if X permits a larger
# page for a particular tier, one call can request at most 25 results and one page
# by default, preventing an operator invocation from fanning out unexpectedly.
_DEFAULT_PAGE_SIZE = 25
_DEFAULT_MAX_PAGES = 1
_MAX_RECENT_SEARCH_RESULTS = 25
X_RATE = RateSpec(max_calls=25, window_s=900.0)


class XApiError(RuntimeError):
    """An error talking to X. The message NEVER contains the key — only the
    status code + a short reason — so a surfaced error cannot leak the bearer."""


class XApiClient(PasteKeyConnector):
    """A BYOK X API v2 client bound to a single stored credential.

    Construct with the ``cred_id`` of a credential in the encrypted store (plus
    the artifact/key locations a test injects); the plaintext key is decrypted
    lazily per request via :func:`load_credential` and held only as a
    :class:`SecretStr` whose ``.reveal()`` is read ONLY to build the auth header.
    """

    descriptor = ConnectorDescriptor(
        vendor="x",
        chassis="paste_key",
        auth="bearer_token",
        key_shape=KeyShape(min_len=20),
        rate=X_RATE,
        docs_url="https://developer.x.com/en/portal/dashboard",
    )

    def __init__(
        self,
        *,
        cred_id: str | None = None,
        artifact_path: str | None = None,
        key_bytes: bytes | None = None,
        key_file: str | None = None,
        page_size: int = _DEFAULT_PAGE_SIZE,
        max_pages: int = _DEFAULT_MAX_PAGES,
        governor: VendorRateGovernor | None = None,
        state_dir: str | None = None,
        clock: Any = None,
        sleeper: Any = None,
    ) -> None:
        super().__init__(
            cred_id=cred_id,
            artifact_path=artifact_path,
            key_bytes=key_bytes,
            key_file=key_file,
        )
        self.page_size = min(max(1, int(page_size)), _MAX_RECENT_SEARCH_RESULTS)
        self.max_pages = max(1, int(max_pages))
        kwargs: dict[str, Any] = {"state_dir": state_dir}
        if clock is not None:
            kwargs["clock"] = clock
        if sleeper is not None:
            kwargs["sleeper"] = sleeper
        self._governor = governor or VendorRateGovernor("x", X_RATE, **kwargs)

    def _http_get(self, path: str, params: dict[str, Any]) -> dict:
        """LIVE, fixture-validated-only edge. Issues a GET with the BYOK bearer.

        The bearer is read from the SecretStr ONLY to build the header dict; it is
        never logged, never put in the URL, never in the raised error. On a non-2xx
        the status code + a generic reason are surfaced — never the key.
        """
        url = f"{_API_BASE}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        bearer = self._resolve_key()
        if bearer is None:
            raise XApiError("X connector has no key attached")
        req = urllib.request.Request(url, method="GET")
        # .reveal() is the single intentional egress of the plaintext, scoped to
        # this header line; the SecretStr goes out of scope at function return.
        req.add_header("Authorization", f"Bearer {bearer.reveal()}")

        # HOST-GLOBAL arXiv GOVERNANCE (compliance boundary): every raw external
        # HTTP egress in the tree must route through the host-global arXiv
        # governor so an arXiv host can never be hit un-spaced (the historical
        # IP-ban hole), REGARDLESS of which module it lives in. The X API host
        # (api.x.ai / api.twitter.com) is never arXiv, so ``govern_if_arxiv``
        # calls ``_send`` directly with zero overhead — but the wrap is the
        # sanctioned, scanner-visible pattern (tools/lint/rate_governor_check),
        # not an allowlist exception, so a future base-URL change cannot silently
        # re-open the hole.
        from acquisition.arxiv.rate_governor import govern_if_arxiv

        class _Response:
            def __init__(self, status_code: int, headers: Any, body: str) -> None:
                self.status_code = status_code
                self.headers = headers
                self.body = body

        def _send() -> _Response:
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                    return _Response(resp.status, resp.headers, resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                return _Response(exc.code, exc.headers, "")

        try:
            response = self._governor.governed_send(
                lambda: govern_if_arxiv(url, _send)
            )
            if response.status_code < 200 or response.status_code >= 300:
                raise XApiError(f"X API HTTP {response.status_code}")
            try:
                payload = json.loads(response.body)
            except (TypeError, ValueError):
                raise XApiError("X API returned an invalid response") from None
            if not isinstance(payload, dict):
                raise XApiError("X API returned an invalid response")
            return payload
        except urllib.error.URLError as e:
            raise XApiError(f"X API network error: {e.reason}") from None

    # ── live fetch surfaces (live-unverified; covered by fixtures via parse_*) ──
    def recent_search(self, query: str, *, max_results: int = _DEFAULT_PAGE_SIZE) -> list[dict]:
        """Recent-search: return the raw tweet objects across up to ``max_pages``.

        ``max_results`` is a hard product ceiling of 25; the key's own tier may
        impose a lower effective limit (a 429 stops the loop)."""
        if not 1 <= max_results <= _MAX_RECENT_SEARCH_RESULTS:
            raise ValueError("max_results must be between 1 and 25")
        return self._paged(
            "/tweets/search/recent",
            {"query": query, "max_results": max(10, min(max_results, self.page_size))},
            result_limit=max_results,
        )

    def user_timeline(self, user_id: str) -> list[dict]:
        """A user's recent tweets (the general-feed source)."""
        return self._paged(
            f"/users/{user_id}/tweets",
            {"max_results": self.page_size},
        )

    def conversation(self, conversation_id: str) -> list[dict]:
        """All tweets in one conversation/thread (the thread-specific source)."""
        return self._paged(
            "/tweets/search/recent",
            {
                "query": f"conversation_id:{conversation_id}",
                "max_results": self.page_size,
            },
        )

    def _paged(
        self, path: str, base_params: dict[str, Any], *, result_limit: int | None = None
    ) -> list[dict]:
        out: list[dict] = []
        params = dict(base_params)
        # X API v2 fields we ask for so the parser has author handle + timestamps.
        params.setdefault(
            "tweet.fields", "created_at,author_id,conversation_id,referenced_tweets"
        )
        params.setdefault("expansions", "author_id")
        params.setdefault("user.fields", "username,verified")
        token: str | None = None
        for _ in range(max(1, self.max_pages)):
            p = dict(params)
            if token:
                p["pagination_token"] = token
            page = self._http_get(path, p)
            out.extend(parse_search_response(page))
            if result_limit is not None and len(out) >= result_limit:
                return out[:result_limit]
            token = (page.get("meta") or {}).get("next_token")
            if not token:
                break
        return out


# ───────────────────────────────────────────────────────────────────────────
# Pure parsing seam — fully fixture-tested, no network, no key.
# ───────────────────────────────────────────────────────────────────────────


def parse_search_response(page: dict) -> list[dict]:
    """Flatten one X API v2 page into a list of tweet dicts enriched with the
    author username/verified from the ``includes.users`` expansion.

    Pure: takes a parsed JSON page (a fixture in tests), returns plain dicts. No
    network, no key, deterministic."""
    data = page.get("data") or []
    users_by_id: dict[str, dict] = {}
    for u in (page.get("includes") or {}).get("users") or []:
        users_by_id[str(u.get("id"))] = u
    enriched: list[dict] = []
    for tw in data:
        author = users_by_id.get(str(tw.get("author_id")), {})
        enriched.append(
            {
                "tweet_id": str(tw.get("id", "")),
                "text": str(tw.get("text", "")),
                "author_handle": str(author.get("username", "")),
                "author_verified": bool(author.get("verified", False)),
                "created_at": tw.get("created_at"),
                "conversation_id": tw.get("conversation_id"),
                "referenced_tweets": tw.get("referenced_tweets") or [],
            }
        )
    return enriched


def to_thread(
    tweets: list[dict],
    *,
    thread_url: str,
    root_tweet_id: str,
    author_handle: str,
) -> TwitterThread:
    """Map flattened tweet dicts → the EXISTING adapter ``TwitterThread`` model.

    Reuses ``Tweet`` / ``TwitterThread`` from ``acquisition/twitter/adapter`` so
    the BYOK path feeds the SAME ingest data model the browser-extension capture
    path uses — no parallel model, no forked ingest path."""
    model_tweets: list[Tweet] = []
    for tw in tweets:
        posted_at = _parse_ts(tw.get("created_at"))
        reply_to = None
        for ref in tw.get("referenced_tweets") or []:
            if ref.get("type") == "replied_to":
                reply_to = str(ref.get("id"))
        model_tweets.append(
            Tweet(
                tweet_id=str(tw.get("tweet_id", "")),
                text=str(tw.get("text", "")),
                author_handle=str(tw.get("author_handle", author_handle)).lstrip("@"),
                author_verified=bool(tw.get("author_verified", False)),
                posted_at=posted_at,
                reply_to=reply_to,
            )
        )
    return TwitterThread(
        thread_url=thread_url,
        root_tweet_id=str(root_tweet_id),
        author_handle=str(author_handle).lstrip("@"),
        tweets=model_tweets,
    )


def _parse_ts(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


__all__ = [
    "XApiClient",
    "XApiError",
    "parse_search_response",
    "to_thread",
]
