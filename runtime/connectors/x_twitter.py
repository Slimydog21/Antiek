"""X (Twitter) API v2 connector — key validation + search (BYO-tools v1).

A ``runtime/connectors``-level connector for the **settings vertical**: a user
connects their own X API v2 Bearer token (BYOK), and this connector (a)
validates it live against ``GET /2/users/me`` and (b) exposes a recent-search
wrapper. Both surfaces route through the host-global
:class:`~runtime.connectors.rate_governor.VendorRateGovernor` exactly like
``acquisition/twitter/api_client.py``, honoring X's documented 25-req/15-min
app-rate budget.

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
    KeyShapeError,
    PasteKeyConnector,
    RateSpec,
)
from runtime.connectors.rate_governor import VendorRateGovernor

# The X API v2 base (documented public endpoint host).
_API_BASE = "https://api.twitter.com/2"

# X API v2 app-rate limit: 450 req / 15 min for search at the app level; the
# connector uses the conservative 25 req / 15 min ceiling (same as the registry
# catalog and the existing ``acquisition`` connector).
_X_RATE = RateSpec(max_calls=25, window_s=900.0)

# Product-level bounds for the settings surface.
_DEFAULT_MAX_RESULTS = 25
_MAX_RESULTS = 25


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
            kwargs: dict[str, Any] = {}
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

        Returns the raw ``data`` array of tweet objects. ``max_results`` is a
        hard ceiling of 25 (the product-level bound for the settings surface);
        the key's own tier may impose a lower effective limit (a 429 pauses the
        governor). X's documented rate limit for recent-search is 450 req / 15
        min at the app level (75 req / 15 min per-user); the governor enforces
        the conservative 25 req / 15 min host-global ceiling.
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
            },
        )
        data = payload.get("data")
        if not isinstance(data, list):
            return []
        return data

    def close(self) -> None:
        """Close the held httpx client — only if this connector created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> XTwitterConnector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = [
    "XTwitterConnector",
    "XTwitterError",
    "XTwitterKeyRequired",
]
