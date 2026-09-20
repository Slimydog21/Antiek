"""SEC EDGAR acquisition — the first BYO-tools connector (keyless).

Full-text search over ``efts.sec.gov`` on the paste-a-key chassis's degenerate
keyless form (``auth="none"``): no credential, a SEC-mandated descriptive
``User-Agent`` (fail-closed without ``ANTIEK_EDGAR_CONTACT``), and every send
through the host-global ``VendorRateGovernor`` at 8 req/s — one notch under
SEC's 10 req/s host ceiling.

See ``acquisition/edgar/client.py`` for ``EdgarConnector.search`` (entry
point) and the endpoint-shape honesty note (fixture-validated,
live-unverified).
"""

from acquisition.edgar.client import (
    EDGAR_RATE,
    EdgarApiError,
    EdgarConnector,
    EdgarContactRequired,
    EdgarHit,
    parse_search_response,
)

__all__ = [
    "EDGAR_RATE",
    "EdgarApiError",
    "EdgarConnector",
    "EdgarContactRequired",
    "EdgarHit",
    "parse_search_response",
]
