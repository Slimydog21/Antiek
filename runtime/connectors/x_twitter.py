"""X (Twitter) API v2 connector — key validation + search (BYO-tools v1).

A ``runtime/connectors``-level connector for the **settings vertical**: a user
connects their own X API v2 Bearer token (BYOK), and this connector (a)
validates it live against ``GET /2/users/me`` and (b) exposes a recent-search
wrapper. Both surfaces route through the host-global
:class:`~runtime.connectors.rate_governor.VendorRateGovernor` exactly like
``acquisition/twitter/api_client.py``, at Antiek's own conservative
25-req/15-min brake.

COST — since 2026-02-06 X sells API access as pay-per-use credits rather than a
flat tier, and read calls are billed per post returned. The brake above is
therefore not the number a connected user needs; the number they need is
:func:`estimated_search_cost_usd`, derived from the dated published per-read
rate in ``X_POST_READ_USD``. This connector does NOT read a credit balance,
because X publishes no endpoint that exposes one.

SECRETS — same posture as every ``PasteKeyConnector``: the bearer is held ONLY
as a non-secret ``cred_id`` into the encrypted byok store, decrypted lazily at
call time via ``_resolve_key()`` and revealed ONLY into the ``Authorization``
header line. Never logged, never in the URL, never in an exception message.

ENDPOINT SHAPES — fixture-validated, live-unverified (the honesty bar of
``acquisition/edgar/client.py:22-33``). The request paths and param names follow
the public X API v2 documentation; the deterministic tests drive this connector
over ``httpx.MockTransport`` (no network), and the live round-trip is the
operator's smoke test.

§16 BOX-BOUNDED: this connector does NO DB writes and opens NO DB connection.
"""

from __future__ import annotations

from typing import Any

import httpx

from runtime.connectors.base import (
    KEY_MAX_LEN,
    ConnectorDescriptor,
    ConnectorError,
    KeyShape,
    PasteKeyConnector,
    RateSpec,
)
from runtime.connectors.rate_governor import VendorRateGovernor

# The X API v2 base (documented public endpoint host).
_API_BASE = "https://api.twitter.com/2"

# Antiek's OWN throttle, not a vendor allowance. X retired flat-rate Basic
# (200 USD/month) and Pro (5,000 USD/month) to new signups on 2026-02-06 and
# migrated the remaining Basic subscribers onto pay-per-use credits on
# 2026-06-01, so a connected key no longer carries a monthly request quota that
# a ceiling could be a fraction of. This 25-call window is a conservative
# host-side brake matching the registry catalog and the existing
# ``acquisition`` connector; describing it to a user as their quota would be a
# lie about what X now bills. What X bills is ``X_POST_READ_USD``, below.
_X_RATE = RateSpec(max_calls=25, window_s=900.0)

# Product-level bounds for the settings surface.
_DEFAULT_MAX_RESULTS = 25
_MAX_RESULTS = 25

#: The page ceiling, public so a caller that must quote the cost of one
#: full-size search does not have to reach into a private name.
SEARCH_MAX_RESULTS = _MAX_RESULTS

#: USD charged for one Post read under pay-per-use credits. Source:
#: https://docs.x.com/x-api/getting-started/pricing, read 2026-09-21, which
#: lists "Posts: Read" at "$0.005 per resource" and states that reads are
#: billed PER RESOURCE RETURNED rather than per request. That distinction is
#: the whole point: one search that returns a full page is 25 billed reads, not
#: one. The figure is vendor-published and can change without a version this
#: repo can pin, so every surface must present it as an estimate from a dated
#: published rate and never as a charge Antiek has observed.
X_POST_READ_USD = 0.005
X_PRICING_SOURCE_URL = "https://docs.x.com/x-api/getting-started/pricing"
X_PRICING_CHECKED_ON = "2026-09-21"


def estimated_search_cost_usd(max_results: int = _DEFAULT_MAX_RESULTS) -> float:
    """Upper bound, in USD, on what one recent-search spends of the owner's credit.

    Pure and offline: a count in, a number out, no key and no network, so the
    settings surface can quote a cost without holding a connector open.

    It is an UPPER bound, not a prediction. X bills per post returned, so a call
    asking for ``max_results`` posts that comes back with fewer costs
    proportionally less. There is deliberately no lower bound and no balance
    read here: X publishes no endpoint from which a credit balance could be
    fetched, and a fabricated balance would be worse than the silence.
    """
    if not 1 <= max_results <= _MAX_RESULTS:
        raise ValueError(f"max_results must be 1-{_MAX_RESULTS}")
    return round(max_results * X_POST_READ_USD, 4)


class XTwitterError(ConnectorError):
    """An error talking to X. The message carries the status code + a short
    reason only — NEVER the bearer token, never the request URL's auth."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class XTwitterKeyRequired(XTwitterError):
    """No bearer is attached to the connector. A call without a credential is
    refused BEFORE any request is built (fail closed)."""


class XTwitterConnector(PasteKeyConnector):
    """BYO X API v2 connector for the settings vertical.

    Construct with the ``cred_id`` of a stored credential (plus the
    artifact/key locations a test injects); the plaintext bearer is decrypted
    lazily per request via ``_resolve_key()`` and held only as a
    :class:`~runtime.byok.secret_str.SecretStr` whose ``.reveal()`` is read
    ONLY to build the auth header.

    Injection seams (tests): ``client`` (an ``httpx.Client`` over
    ``MockTransport``), ``governor`` (a governor pinned to a temp state dir +
    fake clock), or ``state_dir`` to build one. An injected client is NOT
    closed by :meth:`close` (we close only what we created).
    """

    descriptor = ConnectorDescriptor(
        vendor="x",
        chassis="paste_key",
        auth="bearer_token",
        key_shape=KeyShape(min_len=20, max_len=KEY_MAX_LEN),
        rate=_X_RATE,
        docs_url="https://developer.x.com/en/portal/dashboard",
    )

    def __init__(
        self,
        *,
        cred_id: str | None = None,
        artifact_path: str | None = None,
        key_bytes: bytes | None = None,
        key_file: str | None = None,
        client: httpx.Client | None = None,
        governor: VendorRateGovernor | None = None,
        owner: str | None = None,
        state_dir: str | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        super().__init__(
            cred_id=cred_id,
            artifact_path=artifact_path,
            key_bytes=key_bytes,
            key_file=key_file,
        )
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=timeout_s)
        self._owns_governor = governor is None
        if governor is not None:
            self._governor = governor
        else:
            # The owner keys the window: their bearer, their brake.
            kwargs: dict[str, Any] = {"owner": owner}
            if state_dir is not None:
                kwargs["state_dir"] = state_dir
            self._governor = VendorRateGovernor("x", _X_RATE, **kwargs)

    @property
    def governor(self) -> VendorRateGovernor:
        return self._governor

    def _require_bearer(self) -> str:
        """The attached bearer, revealed HERE and only here, scoped to the
        header the caller builds. None → refuse (fail closed)."""
        secret = self._resolve_key()
        if secret is None:
            raise XTwitterKeyRequired(
                f"{self.descriptor.vendor} connector has no key attached"
            )
        return secret.reveal()

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        """One rate-governed GET against the X API v2 base.

        The bearer is revealed ONLY into the ``Authorization`` header. The
        URL's query params never carry credentials (bearer auth). On a non-2xx
        the status code + a generic reason are surfaced — never the key.
        """
        url = f"{_API_BASE}{path}"
        bearer = self._require_bearer()
        headers = {"Authorization": f"Bearer {bearer}", "Accept": "application/json"}

        def _send() -> httpx.Response:
            return self._client.get(url, params=params, headers=headers)

        resp = self._governor.governed_send(_send)
        if resp.status_code < 200 or resp.status_code >= 300:
            raise XTwitterError(
                f"X API request to {path} failed: HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise XTwitterError("X API returned a non-JSON body") from exc
        if not isinstance(payload, dict):
            raise XTwitterError("X API returned a non-object JSON body")
        return payload

    # ── public surfaces ────────────────────────────────────────────────────

    def validate_key(self) -> dict[str, Any]:
        """Validate the attached bearer via ``GET /2/users/me``.

        Returns the caller's X identity (``data`` object: ``id``, ``name``,
        ``username``). Raises :class:`XTwitterError` on any non-2xx or parse
        failure. The rate governor spaces the call within X's 75-req/15-min
        user-budget for this endpoint (the host-global ceiling is 25/15 min).
        """
        payload = self._get("/users/me", {"user.fields": "id,name,username"})
        data = payload.get("data")
        if not isinstance(data, dict):
            raise XTwitterError("X API /users/me returned no data object")
        return data

    def search_tweets(
        self,
        query: str,
        *,
        max_results: int = _DEFAULT_MAX_RESULTS,
    ) -> list[dict[str, Any]]:
        """Recent-search wrapper: ``GET /2/tweets/search/recent``.

        Returns flat tweet records — ``tweet_id``, ``text``, ``author_handle``,
        ``created_at``, ``conversation_id`` — rather than the vendor's own
        tweet objects. X keys a tweet by ``id`` and names its author only by
        ``author_id``; the handle a reader needs arrives separately, in the
        ``includes.users`` expansion this call now asks for. Handing a caller
        the raw objects therefore hands it a join it cannot do once the
        envelope is gone, so :func:`_flatten_search_page` does the join here
        and every caller gets a record it can render.

        ``max_results`` is a hard ceiling of 25 (the product-level bound for
        the settings surface); the key's own configuration may impose a lower
        effective limit (a 429 pauses the governor).

        COST — this call spends the owner's money, and how much is a function
        of ``max_results``. Under pay-per-use credits X bills one Post read per
        post RETURNED, so a full page is 25 billed reads rather than one;
        :func:`estimated_search_cost_usd` turns that into the figure the
        settings surface quotes. The governor's 25 req / 15 min window is
        Antiek's own brake and is not a vendor allowance, so it must never be
        shown in place of the cost. Antiek cannot check the balance before
        spending it: X exposes no billing endpoint to the connector.
        """
        if not query or not query.strip():
            raise ValueError("query must be a non-empty string")
        if not 1 <= max_results <= _MAX_RESULTS:
            raise ValueError(f"max_results must be 1-{_MAX_RESULTS}")
        payload = self._get(
            "/tweets/search/recent",
            {
                "query": query,
                "max_results": str(max_results),
                "tweet.fields": "created_at,author_id,conversation_id",
                "expansions": "author_id",
                "user.fields": "username",
            },
        )
        return _flatten_search_page(payload)

    def close(self) -> None:
        """Close the held httpx client — only if this connector created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> XTwitterConnector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _flatten_search_page(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Join one recent-search page's tweets to their expanded authors.

    Pure: a parsed page in, plain records out — no network, no key, no clock,
    so a fixture exercises it exactly as a live page would. The five keys are
    named as ``acquisition.twitter.api_client.parse_search_response`` names
    them, and carry the same meaning, because the two lanes read the same
    endpoint and a reader downstream should not have to ask which client
    fetched a tweet. They are a subset of it, not a drop-in for it: the
    acquisition record also carries ``author_verified`` and
    ``referenced_tweets``, which ingest needs and a candidate list does not,
    so code that consumes one is not safe to point at the other unread. The
    parse is duplicated rather than imported: ``acquisition`` builds on
    ``runtime.connectors``, and reaching back up from here would invert that
    and drag the acquisition adapter into a connector that promises to stay
    box-bounded.

    A tweet X declines to expand keeps its row and loses only the handle.
    """
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    users: dict[str, dict[str, Any]] = {}
    includes = payload.get("includes")
    if isinstance(includes, dict) and isinstance(includes.get("users"), list):
        for user in includes["users"]:
            if isinstance(user, dict) and user.get("id") is not None:
                users[str(user["id"])] = user
    records: list[dict[str, Any]] = []
    for tweet in data:
        if not isinstance(tweet, dict):
            continue
        author = users.get(str(tweet.get("author_id")), {})
        records.append(
            {
                "tweet_id": str(tweet.get("id", "")),
                "text": str(tweet.get("text", "")),
                "author_handle": str(author.get("username", "")).lstrip("@"),
                "created_at": tweet.get("created_at"),
                "conversation_id": tweet.get("conversation_id"),
            }
        )
    return records


__all__ = [
    "XTwitterConnector",
    "XTwitterError",
    "XTwitterKeyRequired",
]
