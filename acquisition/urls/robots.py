"""Per-host ``robots.txt`` consultation for the general URL fetcher (SPR-10
task 4) — the proven single-host logic in ``acquisition/urls/paulgraham.py``
(``urllib.robotparser`` + fail-open with a visible warning) generalised to
every host ``acquisition.urls.client.fetch`` touches.

Three guarantees, in priority order:

1. **An explicit rule is honoured.** When the host publishes a robots.txt and
   it disallows the URL for our user agent, :meth:`RobotsPolicy.allows`
   returns False and the fetcher raises :class:`RobotsDisallowed` BEFORE any
   request for the page is sent. This is the same posture as the paulgraham
   connector's ``robots_disallowed`` bucket.
2. **A missing or broken robots.txt fails OPEN, loudly.** 404, 5xx, a
   transport error, an oversized or unparseable body — all yield a policy
   with ``applied=False`` and a ``fail_open_reason``, a ``WARNING`` log line,
   and every URL allowed. Ingest is never blocked by the ABSENCE of rules
   (RFC 9309 §2.3.1.3: unavailable → no restrictions). The warning exists so
   the operator SEES that enforcement was off, rather than assuming the site
   allowed the fetch.
3. **One robots.txt request per origin per process.** The cache is an
   in-process ``dict`` keyed by ``scheme://host[:port]`` — not a service, not
   a file, not a DuckDB table — so the general fetcher adds at most one
   request per host, not one per page. :func:`clear_robots_cache` exists for
   tests and for a long-lived process that wants a re-read.

The RSL ``License:`` directive is read from the same body and, when it points
at the same origin, the licence XML is fetched once and parsed into
:class:`acquisition.urls.rights_terms.RightsTerms` — the free machine-readable
"gate already dropped" signal this lane exists to surface. A cross-origin
``License:`` URL is recorded but NOT followed: a robots.txt must not be able
to direct the fetcher at an arbitrary third host (the SSRF shape the
acquisition layer already guards against elsewhere).

Known limit (stated, not hidden): the policy is resolved for the REQUESTED
URL's origin. A cross-host redirect target is not re-consulted; the paulgraham
connector has the same limit because it pins one host.
"""

from __future__ import annotations

import logging
import threading
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from acquisition.urls.rights_terms import (
    NO_TERMS,
    RightsTerms,
    parse_license_directive,
    parse_rsl_xml,
)

logger = logging.getLogger("acquisition.urls.robots")

# Upper bounds on what we will parse. A robots.txt or licence file larger than
# this is treated as unusable (fail-open / parse_error) rather than parsed —
# the RFC 9309 minimum a crawler must accept is 500 KiB.
MAX_ROBOTS_BYTES = 512 * 1024
MAX_LICENSE_BYTES = 256 * 1024

# ``url -> (status_code, text)``. The fetcher supplies a closure that GETs
# through its own (possibly injected / arXiv-governed) client, so robots and
# licence fetches take exactly the transport the page fetch takes. It may
# raise on a transport error; the policy builder treats that as fail-open.
FetchText = Callable[[str], tuple[int, str]]


class RobotsDisallowed(Exception):
    """The host's robots.txt explicitly disallows ``url`` for ``user_agent``.

    Raised by the fetcher BEFORE the page request is sent. Distinct from an
    HTTP error on purpose: an operator counting refusals must be able to tell
    "we chose not to ask" from "we asked and were refused"."""

    def __init__(self, url: str, *, user_agent: str, robots_url: str) -> None:
        self.url = url
        self.user_agent = user_agent
        self.robots_url = robots_url
        super().__init__(
            f"{robots_url} disallows {url!r} for user agent {user_agent!r}"
        )


@dataclass(frozen=True)
class RobotsPolicy:
    """The parsed robots posture for one origin, plus the RSL terms it declared.

    ``applied`` is True iff a robots.txt body was fetched and parsed and its
    rules govern :meth:`allows`. When False, ``fail_open_reason`` says why
    and :meth:`allows` is unconditionally True (the fail-open posture).
    """

    origin: str
    robots_url: str
    applied: bool
    fail_open_reason: str | None
    license_url: str | None
    rights_terms: RightsTerms
    parser: urllib.robotparser.RobotFileParser = field(repr=False, compare=False)

    def allows(self, user_agent: str, url: str) -> bool:
        """True iff ``user_agent`` may fetch ``url`` under this policy."""
        if not self.applied:
            return True
        return self.parser.can_fetch(user_agent, url)


def origin_of(url: str) -> str:
    """``scheme://host[:port]`` (lower-cased) — the cache key and the boundary
    a ``License:`` URL must stay inside."""
    parts = urlsplit(url)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def robots_url_for(url: str) -> str:
    return f"{origin_of(url)}/robots.txt"


_cache: dict[str, RobotsPolicy] = {}
_cache_lock = threading.Lock()


def clear_robots_cache() -> None:
    """Drop every cached policy (tests; or a long-lived process re-reading)."""
    with _cache_lock:
        _cache.clear()


def cached_origins() -> tuple[str, ...]:
    """The origins currently held in the in-process cache (introspection)."""
    with _cache_lock:
        return tuple(_cache)


def robots_policy_for(url: str, *, fetch_text: FetchText) -> RobotsPolicy:
    """The policy for ``url``'s origin, building and caching it on first use.

    Concurrent first calls for the same origin may both build; the first
    writer wins and the loser's result is discarded — both are correct, and a
    duplicate robots fetch beats holding a lock across network I/O.
    """
    origin = origin_of(url)
    with _cache_lock:
        hit = _cache.get(origin)
    if hit is not None:
        return hit
    built = _build_policy(origin, fetch_text)
    with _cache_lock:
        return _cache.setdefault(origin, built)


def _fail_open(
    origin: str,
    robots_url: str,
    parser: urllib.robotparser.RobotFileParser,
    reason: str,
) -> RobotsPolicy:
    parser.parse([])
    logger.warning(
        "%s: %s; failing OPEN — no robots rules enforced for this origin in "
        "this process (fetches proceed; the site did not tell us not to)",
        origin,
        reason,
    )
    return RobotsPolicy(
        origin=origin,
        robots_url=robots_url,
        applied=False,
        fail_open_reason=reason,
        license_url=None,
        rights_terms=NO_TERMS,
        parser=parser,
    )


def _build_policy(origin: str, fetch_text: FetchText) -> RobotsPolicy:
    robots_url = f"{origin}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        status, text = fetch_text(robots_url)
    except Exception as exc:
        return _fail_open(
            origin, robots_url, parser,
            f"robots.txt unreachable ({type(exc).__name__}: {exc})",
        )
    if status >= 400:
        return _fail_open(origin, robots_url, parser, f"robots.txt returned HTTP {status}")
    if len(text) > MAX_ROBOTS_BYTES:
        return _fail_open(
            origin, robots_url, parser,
            f"robots.txt is {len(text)} bytes (> {MAX_ROBOTS_BYTES}); not parsed",
        )
    try:
        parser.parse(text.splitlines())
    except Exception as exc:
        return _fail_open(
            origin, robots_url, parser,
            f"robots.txt unparseable ({type(exc).__name__}: {exc})",
        )
    license_url = parse_license_directive(text)
    return RobotsPolicy(
        origin=origin,
        robots_url=robots_url,
        applied=True,
        fail_open_reason=None,
        license_url=license_url,
        rights_terms=_load_terms(origin, license_url, fetch_text),
        parser=parser,
    )


def _load_terms(origin: str, license_url: str | None, fetch_text: FetchText) -> RightsTerms:
    if license_url is None:
        return NO_TERMS
    absolute = urljoin(origin + "/", license_url)
    if origin_of(absolute) != origin:
        logger.warning(
            "%s: robots.txt License: directive points off-origin (%s); recorded, "
            "not followed",
            origin,
            absolute,
        )
        return RightsTerms(
            source="robots_license_directive",
            license_url=absolute,
            parse_error="cross-origin licence URL not followed",
        )
    try:
        status, text = fetch_text(absolute)
    except Exception as exc:
        return RightsTerms(
            source="robots_license_directive",
            license_url=absolute,
            parse_error=f"licence unreachable ({type(exc).__name__}: {exc})",
        )
    if status >= 400:
        return RightsTerms(
            source="robots_license_directive",
            license_url=absolute,
            parse_error=f"licence returned HTTP {status}",
        )
    if len(text) > MAX_LICENSE_BYTES:
        return RightsTerms(
            source="robots_license_directive",
            license_url=absolute,
            parse_error=f"licence is {len(text)} bytes (> {MAX_LICENSE_BYTES}); not parsed",
        )
    return parse_rsl_xml(text, license_url=absolute)


__all__ = [
    "MAX_LICENSE_BYTES",
    "MAX_ROBOTS_BYTES",
    "FetchText",
    "RobotsDisallowed",
    "RobotsPolicy",
    "cached_origins",
    "clear_robots_cache",
    "origin_of",
    "robots_policy_for",
    "robots_url_for",
]
