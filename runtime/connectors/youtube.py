"""YouTube Data API v3 connector — key validation + search (BYO-tools v1).

A ``runtime/connectors``-level connector for the **settings vertical**: a user
connects their own GCP API key (BYOK), and this connector (a) validates it live
against ``GET /youtube/v3/videos?chart=mostPopular&maxResults=1`` and (b)
exposes a search wrapper. Both surfaces route through the daily-quota
:class:`~runtime.connectors.quota_meter.QuotaMeter` exactly like
``acquisition/youtube/data_api.py``, metering every call in quota units against
the 10,000-unit/day budget reset at midnight Pacific.

SECRETS — same posture as every ``PasteKeyConnector``: the GCP key is held ONLY
as a non-secret ``cred_id`` into the encrypted byok store, decrypted lazily at
call time via ``_resolve_key()`` and revealed ONLY into the ``key`` query param.
Because the key lives in the query string, every error carries the status code +
endpoint PATH only — never the query string, never the key.

ENDPOINT SHAPES — fixture-validated, live-unverified (the honesty bar of
``acquisition/edgar/client.py:22-33``). The request paths and param names follow
the public YouTube Data API v3 documentation; the deterministic tests drive this
connector over ``httpx.MockTransport`` (no network), and the live round-trip is
the operator's smoke test.

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
)
from runtime.connectors.quota_meter import (
    YOUTUBE_UNIT_COSTS,
    QuotaMeter,
    QuotaSnapshot,
)

# The official Data API v3 base.
_API_BASE = "https://www.googleapis.com/youtube/v3"

# Unit costs (spec §5.5): videos.list = 1, search.list = 100.
_VIDEOS_UNITS = YOUTUBE_UNIT_COSTS["videos.list"]  # 1
_SEARCH_UNITS = YOUTUBE_UNIT_COSTS["search.list"]  # 100

# Data API page bounds (vendor-documented: 1-50, default 25).
_MAX_RESULTS_MAX = 50
_MAX_RESULTS_DEFAULT = 25


class YouTubeError(ConnectorError):
    """A non-200 or unparseable response from the Data API.

    Carries the status code + the endpoint PATH only — NEVER the query string,
    which holds the user's key (``api_key_query`` auth).
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class YouTubeKeyRequired(YouTubeError):
    """No key is attached to the connector. A Data API call without a key is
    refused BEFORE any request is built (fail closed)."""


class YouTubeQuotaExhausted(YouTubeError):
    """The API answered 403 ``quotaExceeded`` — Google's ledger is out for the
    day even if the local meter disagreed. The meter has been hard-set to
    exhausted; ``reset_at`` is the PT-midnight the day reopens."""

    def __init__(self, reset_at: str) -> None:
        self.reset_at = reset_at
        super().__init__(
            f"YouTube Data API daily quota exceeded (vendor 403 quotaExceeded); "
            f"meter hard-set until reset {reset_at}",
            status_code=403,
        )


class YouTubeDataConnector(PasteKeyConnector):
    """YouTube Data API v3 connector for the settings vertical.

    ``descriptor`` declares ``auth="api_key_query"``: the user's GCP key is
    attached via the paste-a-key chassis (``attach_key`` → encrypted byok store
    → non-secret ``cred_id``) and revealed AT CALL TIME only into the ``key``
    query param. ``validate_key()`` and ``search()`` route every send through
    the :class:`QuotaMeter`, reserving units before the request is built.

    Injection seams (tests): ``client`` (an ``httpx.Client`` over
    ``MockTransport``), ``meter`` (a meter pinned to a temp state dir + fake
    clock), or ``state_dir`` + ``clock`` to build one. An injected client is NOT
    closed by :meth:`close`.
    """

    descriptor = ConnectorDescriptor(
        vendor="youtube",
        chassis="paste_key",
        auth="api_key_query",
        key_shape=KeyShape(min_len=20, max_len=KEY_MAX_LEN, prefix="AIza"),
        rate=None,  # daily units, not a time window — the QuotaMeter is the guard
        docs_url="https://console.cloud.google.com/apis/credentials",
    )

    def __init__(
        self,
        *,
        cred_id: str | None = None,
        artifact_path: str | None = None,
        key_bytes: bytes | None = None,
        key_file: str | None = None,
        client: httpx.Client | None = None,
        meter: QuotaMeter | None = None,
        state_dir: str | None = None,
        clock: Any = None,
        timeout_s: float = 20.0,
    ) -> None:
        super().__init__(
            cred_id=cred_id,
            artifact_path=artifact_path,
            key_bytes=key_bytes,
            key_file=key_file,
        )
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=timeout_s)
        if meter is not None:
            self._meter = meter
        else:
            meter_kwargs: dict[str, Any] = {}
            if state_dir is not None:
                meter_kwargs["state_dir"] = state_dir
            if clock is not None:
                meter_kwargs["clock"] = clock
            self._meter = QuotaMeter(self.descriptor.vendor, **meter_kwargs)

    @property
    def meter(self) -> QuotaMeter:
        return self._meter

    def quota_remaining(self) -> QuotaSnapshot:
        """Today's remaining daily quota units + the PT reset time."""
        return self._meter.remaining()

    def _require_key(self) -> str:
        """The attached key, revealed HERE and only here, scoped to the param
        line the caller builds. None → refuse (fail closed)."""
        secret = self._resolve_key()
        if secret is None:
            raise YouTubeKeyRequired(
                f"{self.descriptor.vendor} connector has no key attached"
            )
        return secret.reveal()

    def _get(self, path: str, params: dict[str, str], *, units: int) -> dict[str, Any]:
        """One quota-metered GET against the Data API v3 base.

        Reserves ``units`` before the request is built. On a failed send
        (transport error, non-quota HTTP error) the hold is released. On a 403
        ``quotaExceeded`` the meter is hard-set exhausted. The key is revealed
        ONLY into the ``key`` query param.
        """
        key = self._require_key()
        self._meter.check_and_reserve(units)
        full_params = {**params, "key": key}
        url = f"{_API_BASE}{path}"
        headers = {"Accept": "application/json"}

        def _send() -> httpx.Response:
            return self._client.get(url, params=full_params, headers=headers)

        try:
            resp = _send()
        except Exception:
            self._meter.record_actual(-units)
            raise

        if resp.status_code == 403 and _is_quota_exceeded(resp):
            reset_at = self._meter.remaining().reset_at
            self._meter.mark_exhausted()
            raise YouTubeQuotaExhausted(reset_at)
        if resp.status_code != 200:
            self._meter.record_actual(-units)
            raise YouTubeError(
                f"YouTube API request to {path} failed: HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        try:
            payload: dict[str, Any] = resp.json()
        except ValueError as exc:
            self._meter.record_actual(-units)
            raise YouTubeError("YouTube API returned a non-JSON body") from exc
        return payload

    # ── public surfaces ────────────────────────────────────────────────────

    def validate_key(self) -> dict[str, Any]:
        """Validate the attached key via ``GET /youtube/v3/videos``.

        Requests ``part=id, chart=mostPopular, maxResults=1`` — a single-unit
        call (``videos.list`` costs 1 quota unit). Returns the parsed JSON
        payload. Raises :class:`YouTubeError` on any non-200 or parse failure,
        :class:`YouTubeQuotaExhausted` on a vendor 403 ``quotaExceeded``.
        """
        return self._get(
            "/videos",
            {"part": "id", "chart": "mostPopular", "maxResults": "1"},
            units=_VIDEOS_UNITS,
        )

    def search(
        self,
        query: str,
        *,
        max_results: int = _MAX_RESULTS_DEFAULT,
        order: str | None = None,
        type_: str = "video",
    ) -> list[dict[str, Any]]:
        """Search wrapper: ``GET /youtube/v3/search``.

        Reserves 100 quota units (``search.list`` cost) before the request is
        built. Returns the raw ``items`` array. ``max_results`` is bounded 1-50
        (vendor-documented). ``order`` is one of the vendor's values (``date``,
        ``rating``, ``relevance``, ``title``, ``viewCount``).
        """
        if not query or not query.strip():
            raise ValueError("query must be a non-empty string")
        if not 1 <= max_results <= _MAX_RESULTS_MAX:
            raise ValueError(f"max_results must be 1-{_MAX_RESULTS_MAX}")
        if type_ and type_ not in ("video", "channel", "playlist"):
            raise ValueError("type_ must be 'video', 'channel', or 'playlist'")

        params: dict[str, str] = {
            "part": "snippet",
            "q": query,
            "maxResults": str(max_results),
        }
        if order:
            params["order"] = order
        if type_:
            params["type"] = type_

        payload = self._get("/search", params, units=_SEARCH_UNITS)
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        return items

    def close(self) -> None:
        """Close the held httpx client — only if this connector created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> YouTubeDataConnector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _is_quota_exceeded(resp: httpx.Response) -> bool:
    """True when the response body's error block names ``quotaExceeded``."""
    try:
        payload = resp.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    raw_errors = error.get("errors")
    if not isinstance(raw_errors, list):
        return False
    for entry in raw_errors:
        if isinstance(entry, dict) and str(entry.get("reason") or "") == "quotaExceeded":
            return True
    return False


__all__ = [
    "YouTubeDataConnector",
    "YouTubeError",
    "YouTubeKeyRequired",
    "YouTubeQuotaExhausted",
]
