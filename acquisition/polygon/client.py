"""Polygon.io connector — key-in-query, redaction-critical (spec §5.7 row
3b, sprint S3).

The fourth BYO-tools connector: the user's own Polygon plan on the
paste-a-key chassis, ``auth="api_key_query"`` — this client authenticates
via ``?apiKey=...`` on every URL, so the plaintext key lives in the QUERY
STRING at send time. That makes this the same redaction-critical lane as
FMP (spec §10 risk 2): the key is revealed AT CALL TIME only into the
params dict a send builds, and every error / logged surface carries status
+ PATH only — never the query string, never the key. ``redact_query`` is
the one public conversion a caller may use to render a URL safely.

AUTH NOTE (honest divergence, recorded): the spec's §5.7 row 3b lists
Polygon as ``bearer_token``; Polygon accepts BOTH an ``Authorization:
Bearer`` header and the ``apiKey`` query param, and this lane's binding
brief pins the query-param form (``GET ...?apiKey=...`` with the apiKey
REDACTED in any logged URL). The descriptor therefore declares
``api_key_query`` — the FMP posture, verbatim — so the redaction
discipline below is load-bearing, not vestigial. Free-tier keys work
(delayed data); the plan is the user's own.

GUARDS:

  * KEY. Attached via the chassis (``attach_key`` → encrypted byok store →
    non-secret ``cred_id``); ``_require_key()`` refuses a keyless send.
  * RATE. Spec §5.4 assigns Polygon "vendor-429 via governor" ("others
    governed only by vendor 429s (FMP/Polygon planwise)"): sends route
    through :class:`VendorRateGovernor` so a 429 writes the cross-process
    ``banned_until`` sentinel (the governor's real job here) — with a
    documented NO-WINDOW rate (:data:`POLYGON_RATE_NO_WINDOW`): Polygon
    gets no client-side pacing window per the spec, only the 429 pause.
    The descriptor's ``rate`` stays ``None`` (no window spec exists).

ENDPOINT SHAPES — fixture-validated, live-unverified (the honesty bar of
``acquisition/edgar/client.py:22-33``). ``GET /v3/reference/tickers/{symbol}``
returns an OBJECT envelope ``{status, request_id, results: {ticker, name,
market, locale, primary_exchange, type, active, currency_name, cik,
market_cap, ...}}``; an unknown ticker answers HTTP 404 (``status:
"NOT_FOUND"``) — the vendor's no-record signal, surfaced here as ``None``.
``GET /v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from}/{to}``
returns an OBJECT envelope ``{status, ticker, resultsCount, results: [{t,
o, h, l, c, v, vw, n}, ...]}``; an in-range-but-empty answer carries no
``results`` key, surfaced as ``[]``. Both shapes follow the public Polygon
docs, not a fresh live probe; the deterministic tests drive this client
with RECORDED fixture JSON over ``httpx.MockTransport`` (no network).

§16 BOX-BOUNDED: this client does NO DB writes and opens NO DB connection —
it only fetches + parses. Landing any fetched payload as a
``personal_reading`` document is the (separate) adapter's job; no
connector output is servable (spec §5.0 rights invariant).
"""

from __future__ import annotations

from collections.abc import Callable
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
    RateSpec,
)
from runtime.connectors.rate_governor import VendorRateGovernor

# Polygon.io API root — the reference endpoints hang off ``/v3/...`` and
# the aggregates endpoint off ``/v2/...`` (the vendor's own versioning).
_API_BASE = "https://api.polygon.io"
_TICKER_DETAILS_PATH = "/v3/reference/tickers"
_AGGREGATES_PATH = "/v2/aggs/ticker"

# The spec's §5.4 rule for Polygon: "governed only by vendor 429s" — NO
# client-side pacing window. The governor still needs a RateSpec to
# construct; a budget far beyond any single-host burst rate means the
# sliding window NEVER waits, so the governor's only effective behavior
# here is its 429 ``banned_until`` sentinel. (The descriptor's ``rate``
# stays None — there is no window spec; this is the stand-in.)
POLYGON_RATE_NO_WINDOW = RateSpec(max_calls=1_000_000, window_s=60.0)


def redact_query(url: str) -> str:
    """Render a URL WITHOUT its query string — the one safe way to log a
    key-in-query vendor URL (the ``apiKey`` param and every sibling param
    are dropped, not masked: Polygon URLs carry nothing but the key +
    request params, so path-only is both safe and sufficient)."""
    parts = urlsplit(url)
    return parts._replace(query="").geturl()


class PolygonKeyRequired(ConnectorError):
    """No key is attached to the connector. A Polygon call without a key is
    refused BEFORE any request is built (fail closed — never a keyless
    send). The message never carries key material (there is none)."""


class PolygonApiError(ConnectorError):
    """A non-200 or unparseable response from Polygon.

    Carries the status code + the endpoint PATH only — NEVER the query
    string, which holds the user's ``apiKey`` (the redaction rule, spec §10
    risk 2). ``path`` is the exact redacted form a caller may log.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class PolygonTickerDetails:
    """One parsed ticker-details record (the subset a research workstation
    uses; the vendor's payload carries more, unmapped on purpose — bounded
    mapping beats dump-everything). Scalar numbers default to None when the
    vendor omits or strings them oddly."""

    symbol: str
    name: str
    market: str
    locale: str
    primary_exchange: str
    type: str
    currency_name: str
    cik: str
    active: bool | None = None
    market_cap: int | None = None


@dataclass(frozen=True)
class PolygonAggregateBar:
    """One parsed aggregates bar (OHLCV + vwap + trade count for one
    ``multiplier``/``timespan`` bucket). ``timestamp_ms`` is the vendor's
    Unix-ms bucket start (``t``), kept verbatim — no timezone guessing.
    Fields default to None when the vendor omits them."""

    timestamp_ms: int | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    vwap: float | None = None
    transactions: int | None = None


def parse_ticker_details_response(payload: Any) -> PolygonTickerDetails | None:
    """Map the Polygon ticker-details OBJECT envelope to one record.

    ``results`` absent (or null) is the no-record shape → ``None``; the
    vendor's more common no-record signal is HTTP 404, which
    :meth:`PolygonConnector.ticker_details` maps to ``None`` before parsing.
    A non-object body or a non-mapping ``results`` is an envelope shape
    change and must surface as :class:`PolygonApiError`, never silently
    read as "no record".
    """
    if not isinstance(payload, dict):
        raise PolygonApiError("Polygon ticker details returned a non-object JSON body")
    results = payload.get("results")
    if results is None:
        return None
    if not isinstance(results, dict):
        raise PolygonApiError("Polygon ticker details returned a malformed results record")
    return _build_ticker_details(results)


def _build_ticker_details(rec: dict[str, Any]) -> PolygonTickerDetails:
    return PolygonTickerDetails(
        symbol=str(rec.get("ticker") or ""),
        name=str(rec.get("name") or ""),
        market=str(rec.get("market") or ""),
        locale=str(rec.get("locale") or ""),
        primary_exchange=str(rec.get("primary_exchange") or ""),
        type=str(rec.get("type") or ""),
        currency_name=str(rec.get("currency_name") or ""),
        cik=str(rec.get("cik") or ""),
        active=rec.get("active") if isinstance(rec.get("active"), bool) else None,
        market_cap=_to_int(rec.get("market_cap")),
    )


def parse_aggregates_response(payload: Any) -> list[PolygonAggregateBar]:
    """Map the Polygon aggregates OBJECT envelope to a list of bars.

    ``results`` absent (or null) is the vendor's in-range-but-empty answer
    → ``[]``. A non-object body, a non-list ``results``, or a non-mapping
    bar entry is an envelope shape change and must surface as
    :class:`PolygonApiError`, never silently read as "no bars".
    """
    if not isinstance(payload, dict):
        raise PolygonApiError("Polygon aggregates returned a non-object JSON body")
    results = payload.get("results")
    if results is None:
        return []
    if not isinstance(results, list):
        raise PolygonApiError("Polygon aggregates returned a malformed results array")
    bars: list[PolygonAggregateBar] = []
    for entry in results:
        if not isinstance(entry, dict):
            raise PolygonApiError("Polygon aggregates returned a malformed bar record")
        bars.append(_build_bar(entry))
    return bars


def _build_bar(rec: dict[str, Any]) -> PolygonAggregateBar:
    return PolygonAggregateBar(
        timestamp_ms=_to_int(rec.get("t")),
        open=_to_float(rec.get("o")),
        high=_to_float(rec.get("h")),
        low=_to_float(rec.get("l")),
        close=_to_float(rec.get("c")),
        volume=_to_float(rec.get("v")),
        vwap=_to_float(rec.get("vw")),
        transactions=_to_int(rec.get("n")),
    )


def _to_int(value: object) -> int | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> float | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class PolygonConnector(PasteKeyConnector):
    """Polygon.io — ticker details + aggregates bars on the paste-a-key
    chassis, ``api_key_query`` auth.

    ``descriptor`` declares ``rate=None`` (no client-side window — spec
    §5.4); every send still routes through a
    :class:`VendorRateGovernor` at :data:`POLYGON_RATE_NO_WINDOW` so a
    vendor 429 writes the cross-process ``banned_until`` sentinel. The key
    is revealed at call time only into the params dict the send builds;
    every error path carries status + PATH only (``redact_query`` is the
    one safe URL renderer).

    Injection seams (tests): ``client`` (an ``httpx.Client`` over
    ``MockTransport`` — no network), ``governor`` (a governor with a fake
    clock), or ``state_dir`` + ``clock`` + ``sleeper`` to build one. An
    injected client is NOT closed by :meth:`close`.
    """

    descriptor = ConnectorDescriptor(
        vendor="polygon",
        chassis="paste_key",
        auth="api_key_query",
        key_shape=KeyShape(min_len=10, max_len=KEY_MAX_LEN, prefix=None),
        rate=None,  # no window spec — vendor-429 via the governor's sentinel
        docs_url="https://polygon.io/docs",
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
        clock: Any = None,
        sleeper: Any = None,
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
        if governor is not None:
            self._governor = governor
        else:
            governor_kwargs: dict[str, Any] = {"state_dir": state_dir}
            if clock is not None:
                governor_kwargs["clock"] = clock
            if sleeper is not None:
                governor_kwargs["sleeper"] = sleeper
            self._governor = VendorRateGovernor(
                self.descriptor.vendor, POLYGON_RATE_NO_WINDOW, **governor_kwargs
            )

    @property
    def governor(self) -> VendorRateGovernor:
        return self._governor

    def _require_key(self) -> str:
        """The attached key, revealed HERE and only here, scoped to the
        params dict a send builds. None keyless → refuse (fail closed)."""
        secret = self._resolve_key()
        if secret is None:
            raise PolygonKeyRequired(
                f"{self.descriptor.vendor} connector has no key attached — "
                "attach_key() before a fetch (or a cred_id at construction)"
            )
        return secret.reveal()

    def ticker_details(self, symbol: str) -> PolygonTickerDetails | None:
        """Ticker details for ``symbol`` — ``GET /v3/reference/tickers/{symbol}``.

        Returns ``None`` for an unknown symbol (the vendor's 404 no-record
        signal), the structured :class:`PolygonTickerDetails` otherwise.
        ``symbol`` is the vendor's ticker verbatim (upper-cased by Polygon,
        case-insensitive; unvalidated here beyond non-empty).
        """
        if not symbol or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        return self._get(
            f"{_TICKER_DETAILS_PATH}/{symbol}",
            extra_params=None,
            parse=parse_ticker_details_response,
            not_found_is_none=True,
        )

    def aggregates(
        self,
        symbol: str,
        *,
        date_from: str,
        date_to: str,
        multiplier: int = 1,
        timespan: str = "day",
        adjusted: bool = True,
        sort: str = "asc",
        limit: int = 120,
    ) -> list[PolygonAggregateBar]:
        """Aggregates bars for ``symbol`` over ``date_from``..``date_to``.

        ``GET /v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/
        {date_from}/{date_to}``. Returns ``[]`` when the range holds no
        bars (the vendor's absent-``results`` answer). ``date_from`` /
        ``date_to`` are the vendor's date strings (``YYYY-MM-DD`` or
        Unix-ms), ``timespan`` one of the vendor's window names
        (minute/hour/day/week/...) — unvalidated here; an out-of-vocabulary
        value is the vendor's problem (it answers an error, which surfaces
        as :class:`PolygonApiError` with status + path only).
        """
        if not symbol or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        path = (
            f"{_AGGREGATES_PATH}/{symbol}/range/{multiplier}/{timespan}/{date_from}/{date_to}"
        )
        bars = self._get(
            path,
            extra_params={
                "adjusted": "true" if adjusted else "false",
                "sort": sort,
                "limit": str(limit),
            },
            parse=parse_aggregates_response,
        )
        # parse_aggregates_response never returns None; only the
        # not_found_is_none branch (unused here) yields None from _get.
        assert bars is not None
        return bars

    def _get[RecordT](
        self,
        path: str,
        *,
        extra_params: dict[str, str] | None,
        parse: Callable[[Any], RecordT],
        not_found_is_none: bool = False,
    ) -> RecordT | None:
        """The one send path for every endpoint: key → params → governed
        send → error discipline (status + path only, never the query)."""
        key = self._require_key()
        params: dict[str, str] = {"apiKey": key}
        if extra_params:
            params.update(extra_params)
        url = f"{_API_BASE}{path}"

        headers = {"Accept": "application/json"}

        def _send() -> httpx.Response:
            return self._client.get(url, params=params, headers=headers)

        # HOST-GLOBAL ARXIV GOVERNANCE (compliance boundary): every raw
        # external HTTP egress in the tree routes through the arXiv governor
        # so an arXiv host can never be hit un-spaced, REGARDLESS of module.
        # api.polygon.io is never arXiv, so ``govern_if_arxiv``
        # calls ``_send`` directly — the wrap is the sanctioned,
        # scanner-visible pattern (tools/lint/rate_governor_check).
        from acquisition.arxiv.rate_governor import govern_if_arxiv

        resp = self._governor.governed_send(lambda: govern_if_arxiv(url, _send))
        if resp.status_code == 404 and not_found_is_none:
            # The vendor's documented unknown-ticker signal — the no-record
            # answer, not an error (mirrors FMP's empty-array → None).
            return None
        if resp.status_code != 200:
            # Path-only, always: the query string holds the user's key.
            raise PolygonApiError(
                f"Polygon {path} failed: HTTP {resp.status_code} from "
                f"{urlsplit(url).path}",
                status_code=resp.status_code,
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise PolygonApiError(f"Polygon {path} returned a non-JSON body") from exc
        return parse(payload)

    def close(self) -> None:
        """Close the held httpx client — only if this connector created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> PolygonConnector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = [
    "POLYGON_RATE_NO_WINDOW",
    "PolygonAggregateBar",
    "PolygonApiError",
    "PolygonConnector",
    "PolygonKeyRequired",
    "PolygonTickerDetails",
    "parse_aggregates_response",
    "parse_ticker_details_response",
    "redact_query",
]
