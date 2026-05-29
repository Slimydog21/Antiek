"""Open-access aggregator acquisition path (SPR-03).

Discovery + full-text resolution across the major OA aggregators, all gated
by the same load-bearing invariant: an item renders full text publicly ONLY
if its license actually grants redistribution. "Free to read" (bronze OA, a
DOAJ-confirmed-OA journal, a PMC full-text URL) is NEVER conflated with "free
to redistribute."

Surface:

- ``openalex.search_works(...)`` — discovery: topic/author -> candidate works
  with DOI + OA status + license + best-OA URL.
- ``unpaywall.resolve_doi(doi)`` — DOI -> best OA full-text location + license.
- ``pmc.resolve_by_doi(doi)`` — Europe PMC OA full text + per-article license.
- ``doaj.confirm_by_doi(doi)`` — journal-level OA confirmation + license.
- ``licenses.resolve_oa_license(uri)`` — the deny-by-default OA license verdict
  (CC core shared with arXiv via ``acquisition.licenses_core``).
- ``throttle.OAThrottle`` — polite-pool spacing + retry-with-backoff (NO arXiv
  ban-sentinel machinery; OA sources don't have that failure history).
"""

from .licenses import LicenseResolution, resolve_oa_license
from .throttle import POLITE_POOL_MAILTO, OAThrottle

__all__ = [
    "LicenseResolution",
    "OAThrottle",
    "POLITE_POOL_MAILTO",
    "resolve_oa_license",
]
