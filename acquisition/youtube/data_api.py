"""YouTube Data API v3 connector — the ToS-clean lane (spec §5.7 row 2, S2).

The BYO-tools YouTube connector: official ``youtube.googleapis.com`` Data
API v3 on the paste-a-key chassis (user's own GCP key), SEPARATE from the
scrape path in ``acquisition/youtube/client.py`` on purpose (spec §3
verdict: the scrape client stays operator-only with its 25-fetch cap and its
ToS flag untouched; the Data API is the ToS-clean lane for search on the
user's own key — the two paths live in different modules on purpose).

GUARDS, both spec-assigned (row 2: ``QuotaMeter (PT reset)``):

  * QUOTA UNITS. YouTube meters every call in units of a 10,000-unit/day
    budget reset at midnight America/Los_Angeles. A ``search.list`` costs
    100 units (``YOUTUBE_UNIT_COSTS``, spec §5.5). ``search()`` reserves
    100 units through :class:`runtime.connectors.quota_meter.QuotaMeter`
    BEFORE any request is built — an exhausted meter refuses with the PT
    reset time, and the refusal fires before the transport is touched. A
    failed send releases its hold (``record_actual(-units)`` — the call
    spent nothing); a 403 ``quotaExceeded`` from the API hard-sets the
    meter exhausted until reset (spec §10 risk 3: the vendor's signal wins
    over any local counter).
  * KEY. The GCP key rides the ``key`` QUERY PARAM (``api_key_query``
    auth), decrypted AT CALL TIME via ``_resolve_key()`` and revealed only
    into the param line it builds. Because the key lives in the query
    string, every error carries status + PATH only — never the query, never
    the key (the chassis-wide redaction rule, load-bearing here).

ENDPOINT SHAPES — fixture-validated, live-unverified (the honesty bar of
``acquisition/edgar/client.py:22-33``). The request params (``part`` /
``q`` / ``maxResults`` / ``type`` / ``order`` / ``publishedAfter`` /
``publishedBefore`` / ``regionCode`` / ``relevanceLanguage`` against
``https://www.googleapis.com/youtube/v3/search``) and the response envelope
(``items[*].{id.{kind,videoId|channelId|playlistId}, snippet.{title,
description,channelId,channelTitle,publishedAt,thumbnails}}``) follow the
public Data API v3 documentation, not a fresh live probe. The deterministic
tests drive this client with RECORDED fixture JSON over
``httpx.MockTransport`` (no network); the live round-trip is the operator's
smoke test. Transcripts stay OUT of the Data API (``captions.download`` is
owner-only per ``client.py:24-29``) — the scrape client remains the only
transcript route, untouched.

§16 BOX-BOUNDED: this client does NO DB writes and opens NO DB connection —
it only fetches + parses. Landing a video as a ``personal_reading`` document
is the (separate) adapter's job, and no connector output is servable
(spec §5.0 rights invariant).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

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

# The official Data API v3 search endpoint. ``part=snippet`` is fixed by the
# spec's URL shape; the key is injected at send time, never stored, never
# logged.
_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

# ``search.list`` costs 100 of the 10,000 daily units (spec §5.5 unit table).
_SEARCH_UNITS = YOUTUBE_UNIT_COSTS["search.list"]

# Data API search page bounds (vendor-documented: 1-50, default 25).
_MAX_RESULTS_MAX = 50
_MAX_RESULTS_DEFAULT = 25


class YouTubeKeyRequired(ConnectorError):
    """No key is attached to the connector. A Data API call without a key is
    refused BEFORE any request is built (fail closed — never a keyless
    send). The message never carries key material (there is none to carry)."""


class YouTubeApiError(ConnectorError):
    """A non-200 or unparseable response from the Data API.

    Carries the status code + the endpoint PATH only — NEVER the query
    string, which holds the user's key (``api_key_query`` auth). This is the
    redaction rule the FMP lane (key-in-query) also ships; it is load-bearing
    here for the same reason.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class YouTubeQuotaExhausted(YouTubeApiError):
    """The API answered 403 ``quotaExceeded`` — Google's ledger is out for
    the day even if the local meter disagreed (spec §10 risk 3). The meter
    has been hard-set to exhausted; ``reset_at`` is the PT-midnight the day
    reopens."""

    def __init__(self, reset_at: str) -> None:
        self.reset_at = reset_at
        super().__init__(
            f"YouTube Data API daily quota exceeded (vendor 403 quotaExceeded); "
            f"meter hard-set until reset {reset_at}",
            status_code=403,
        )


@dataclass(frozen=True)
class YouTubeSearchResult:
    """One parsed search hit. ``kind`` is the id-kind verbatim minus the
    ``youtube#`` prefix (``"video"`` / ``"channel"`` / ``"playlist"``), and
    ``video_id`` holds whichever id the hit carries (a channel hit carries
    the channel id — named for the workstation's primary case, the video
    search). Scalar fields default to "" when a snippet omits them."""

    video_id: str
    kind: str
    title: str
    description: str
    channel_id: str
    channel_title: str
    published_at: str
    thumbnail_url: str | None = None


def parse_search_response(payload: dict[str, Any]) -> list[YouTubeSearchResult]:
    """Map the Data API v3 search envelope to structured hits.

    Lenient per-item (a search result list, not a ledger): an item whose
    ``id`` or ``snippet`` is not a mapping is skipped rather than nuking the
    page. The envelope itself must be a mapping — anything else is a
    :class:`YouTubeApiError`. The ``id`` object carries exactly one of
    ``videoId`` / ``channelId`` / ``playlistId``, keyed off its ``kind``.
    """
    if not isinstance(payload, dict):
        raise YouTubeApiError("YouTube search returned a non-object JSON body")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return []
    out: list[YouTubeSearchResult] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        id_obj = raw.get("id")
        snippet = raw.get("snippet")
        if not isinstance(id_obj, dict) or not isinstance(snippet, dict):
            continue
        id_kind = str(id_obj.get("kind") or "")
        kind = id_kind[len("youtube#") :] if id_kind.startswith("youtube#") else id_kind
        video_id = str(
            id_obj.get("videoId")
            or id_obj.get("channelId")
            or id_obj.get("playlistId")
            or ""
        )
        thumbnails = snippet.get("thumbnails")
        thumb_url = None
        if isinstance(thumbnails, dict):
            thumb = thumbnails.get("default")
            if isinstance(thumb, dict) and thumb.get("url"):
                thumb_url = str(thumb["url"])
        out.append(
            YouTubeSearchResult(
                video_id=video_id,
                kind=kind,
                title=str(snippet.get("title") or ""),
                description=str(snippet.get("description") or ""),
                channel_id=str(snippet.get("channelId") or ""),
                channel_title=str(snippet.get("channelTitle") or ""),
                published_at=str(snippet.get("publishedAt") or ""),
                thumbnail_url=thumb_url,
            )
        )
    return out


class YouTubeConnector(PasteKeyConnector):
    """YouTube Data API v3 search — the official, quota-metered lane.

    ``descriptor`` declares ``auth="api_key_query"``: the user's GCP key is
    attached via the paste-a-key chassis (``attach_key`` → encrypted byok
    store → non-secret ``cred_id``) and revealed AT CALL TIME only into the
    ``key`` query param. ``search()`` routes every send through the
    :class:`QuotaMeter` (100 units reserved before the request is built)
    and, at the fetch boundary, through ``govern_if_arxiv`` (the sanctioned
    scanner-visible wrap — these URLs are never arXiv, so the call-through
    is zero-cost, but the pattern keeps the arXiv egress lint honest).

    Injection seams (tests): ``client`` (an ``httpx.Client`` over
    ``MockTransport`` — no network), ``meter`` (a meter pinned to a temp
    state dir + fake clock), or ``state_dir`` + ``clock`` to build one. An
    injected client is NOT closed by :meth:`close` (we close only what we
    created).
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
        """The attached quota meter (injected or self-built)."""
        return self._meter

    def quota_remaining(self) -> QuotaSnapshot:
        """Today's remaining daily quota units + the PT reset time — the
        meter surface the settings UI renders."""
        return self._meter.remaining()

    def _require_key(self) -> str:
        """The attached key, revealed HERE and only here, scoped to the
        param line the caller builds. None keyless → refuse (fail closed)."""
        secret = self._resolve_key()
        if secret is None:
            raise YouTubeKeyRequired(
                f"{self.descriptor.vendor} connector has no key attached — "
                "attach_key() before search() (or a cred_id at construction)"
            )
        return secret.reveal()

    def search(
        self,
        query: str,
        *,
        max_results: int = _MAX_RESULTS_DEFAULT,
        order: str | None = None,
        published_after: str | None = None,
        published_before: str | None = None,
        region_code: str | None = None,
        type_: str = "video",
        relevance_language: str | None = None,
    ) -> list[YouTubeSearchResult]:
        """Search YouTube via the Data API, returning structured results.

        Builds ``GET {_SEARCH_URL}?part=snippet&q=...&key=...`` (plus
        ``maxResults`` / ``type`` and, when given, ``order`` /
        ``publishedAfter`` / ``publishedBefore`` / ``regionCode`` /
        ``relevanceLanguage`` — the vendor's names verbatim), reserving
        ``search.list``'s 100 quota units in the meter BEFORE the request
        is built. An exhausted meter raises :class:`QuotaExhausted` (with
        the PT reset time) without touching the transport. On a failed send
        the 100-unit hold is released (``record_actual(-100)``); on a 403
        ``quotaExceeded`` the meter is hard-set exhausted and
        :class:`YouTubeQuotaExhausted` surfaces. ``order`` is one of the
        vendor's values (``date`` / ``rating`` / ``relevance`` / ``title`` /
        ``viewCount`` — pass verbatim; unvalidated here, the vendor rejects
        unknowns); ``published_after`` / ``published_before`` are the
        vendor's RFC-3339 strings.
        """
        if not query or not query.strip():
            raise ValueError("query must be a non-empty string")
        if not 1 <= max_results <= _MAX_RESULTS_MAX:
            raise ValueError(f"max_results must be 1-{_MAX_RESULTS_MAX}")
        if type_ and type_ not in ("video", "channel", "playlist"):
            raise ValueError("type_ must be 'video', 'channel', or 'playlist'")

        # KEY FIRST, then QUOTA — a keyless connector must refuse before
        # any accounting happens (no phantom reservations from refused
        # attempts), and the quota refusal still fires pre-dispatch with the
        # PT reset time (spec: refuse before any request exists).
        key = self._require_key()
        self._meter.check_and_reserve(_SEARCH_UNITS)
        params: dict[str, str] = {
            "part": "snippet",
            "q": query,
            "key": key,
            "maxResults": str(max_results),
        }
        if order:
            params["order"] = order
        if published_after:
            params["publishedAfter"] = published_after
        if published_before:
            params["publishedBefore"] = published_before
        if region_code:
            params["regionCode"] = region_code
        if type_:
            params["type"] = type_
        if relevance_language:
            params["relevanceLanguage"] = relevance_language

        headers = {"Accept": "application/json"}

        def _send() -> httpx.Response:
            return self._client.get(_SEARCH_URL, params=params, headers=headers)

        # HOST-GLOBAL ARXIV GOVERNANCE (compliance boundary): every raw
        # external HTTP egress in the tree routes through the arXiv governor
        # so an arXiv host can never be hit un-spaced, REGARDLESS of module.
        # youtube.googleapis.com is never arXiv, so ``govern_if_arxiv`` calls
        # ``_send`` directly with zero overhead — but the wrap is the
        # sanctioned, scanner-visible pattern
        # (tools/lint/rate_governor_check), not an allowlist exception.
        from acquisition.arxiv.rate_governor import govern_if_arxiv

        try:
            resp = govern_if_arxiv(_SEARCH_URL, _send)
        except Exception:
            # The send never reached the vendor's ledger (transport /
            # network failure): release the 100-unit hold — the call spent
            # nothing (spec §10 risk 4's settle-at-zero spirit).
            self._meter.record_actual(-_SEARCH_UNITS)
            raise

        if resp.status_code == 403 and _is_quota_exceeded(resp):
            # GOOGLE'S LEDGER WINS over the local meter (spec §10 risk 3).
            reset_at = self._meter.remaining().reset_at
            self._meter.mark_exhausted()
            raise YouTubeQuotaExhausted(reset_at)
        if resp.status_code != 200:
            # Non-quota failure: the units were not spent — release the hold.
            self._meter.record_actual(-_SEARCH_UNITS)
            raise YouTubeApiError(
                f"YouTube search failed: HTTP {resp.status_code} from "
                f"{urlsplit(_SEARCH_URL).path}",
                status_code=resp.status_code,
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            # Unparseable body = no results consumed — release the hold.
            self._meter.record_actual(-_SEARCH_UNITS)
            raise YouTubeApiError("YouTube search returned a non-JSON body") from exc
        return parse_search_response(payload)

    def close(self) -> None:
        """Close the held httpx client — only if this connector created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> YouTubeConnector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _is_quota_exceeded(resp: httpx.Response) -> bool:
    """True when the response body's error block names ``quotaExceeded``.

    Best-effort parse (the vendor's error envelope is
    ``{"error": {"code": 403, "errors": [{"reason": "quotaExceeded", ...}]}}``):
    an unparseable body on a 403 defaults to False — the caller then raises
    the generic API error, which still never echoes the query.
    """
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
    "YouTubeApiError",
    "YouTubeConnector",
    "YouTubeKeyRequired",
    "YouTubeQuotaExhausted",
    "YouTubeSearchResult",
    "parse_search_response",
]
