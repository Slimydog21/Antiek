"""Polygon.io acquisition — the key-in-query BYO-tools connector.

Ticker details + aggregates bars on the paste-a-key chassis
(``auth="api_key_query"`` — this client authenticates via ``?apiKey=`` on
every URL), the user's own plan (free tier works for delayed data).
Because the key lives in the query string, this lane is redaction-critical:
every error carries status + PATH only, never the query, and
``redact_query`` is the one safe URL renderer for logging.

Sends route through the host-global ``VendorRateGovernor`` at a documented
no-window rate so a vendor 429 writes the cross-process ``banned_until``
sentinel (spec §5.4: Polygon is "governed only by vendor 429s").

See ``acquisition/polygon/client.py`` for ``PolygonConnector.ticker_details``
/ ``PolygonConnector.aggregates`` (entry points), the auth note (the
brief pins ``apiKey``-in-query where the spec table lists bearer), and the
endpoint-shape honesty note (fixture-validated, live-unverified).
"""

from acquisition.polygon.client import (
    POLYGON_RATE_NO_WINDOW,
    PolygonAggregateBar,
    PolygonApiError,
    PolygonConnector,
    PolygonKeyRequired,
    PolygonTickerDetails,
    parse_aggregates_response,
    parse_ticker_details_response,
    redact_query,
)

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
