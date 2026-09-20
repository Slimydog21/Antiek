"""Financial Modeling Prep acquisition — the key-in-query BYO-tools connector.

Company profiles + earnings-call transcripts on the paste-a-key chassis
(``auth="api_key_query"`` — FMP authenticates via ``?apikey=`` on every
URL), the user's own plan. Because the key lives in the query string, this
lane is redaction-critical: every error carries status + PATH only, never
the query, and ``redact_query`` is the one safe URL renderer for logging.

Sends route through the host-global ``VendorRateGovernor`` at a documented
no-window rate so a vendor 429 writes the cross-process ``banned_until``
sentinel (spec §5.4: FMP is "governed only by vendor 429s").

See ``acquisition/fmp/client.py`` for ``FmpConnector.profile`` /
``FmpConnector.transcripts`` (entry points) and the endpoint-shape honesty
note (fixture-validated, live-unverified).
"""

from acquisition.fmp.client import (
    FMP_RATE_NO_WINDOW,
    FmpApiError,
    FmpConnector,
    FmpKeyRequired,
    FmpProfile,
    FmpTranscript,
    parse_profile_response,
    parse_transcript_response,
    redact_query,
)

__all__ = [
    "FMP_RATE_NO_WINDOW",
    "FmpApiError",
    "FmpConnector",
    "FmpKeyRequired",
    "FmpProfile",
    "FmpTranscript",
    "parse_profile_response",
    "parse_transcript_response",
    "redact_query",
]
