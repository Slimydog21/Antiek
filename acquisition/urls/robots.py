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
   and every URL allowed. The warning exists so the operator SEES that
   enforcement was off, rather than assuming the site allowed the fetch.
   For a 4xx this is exactly RFC 9309 §2.3.1.3 ("unavailable": no
   restrictions). For a 5xx or a transport error it is a deliberate
   deviation: RFC 9309 §2.3.1.4 says a crawler MUST then assume complete
   disallow, but the SPR-10 contract (and the paulgraham precedent) is that
   robots handling never blocks ingest. The deviation is bounded by (3): an
   unreachable robots.txt is re-tried after :data:`UNREACHABLE_RETRY_S`
   instead of leaving enforcement off for the life of the process.
3. **One robots.txt request per origin per cache window.** The cache is an
   in-process ``dict`` keyed by ``scheme://host[:port]`` — not a service, not
   a file, not a DuckDB table — so the general fetcher adds at most one
   request per host per window, not one per page. A fetched answer (rules
   applied, or a definitive 4xx) is held for :data:`ROBOTS_CACHE_TTL_S`, the
   24 hours RFC 9309 §2.4 allows, so a publisher who adds a ``Disallow`` is
   honoured by a long-lived API process within a day rather than at its next
   restart. An unreachable one (5xx / transport error) is held only for
   :data:`UNREACHABLE_RETRY_S`. :func:`clear_robots_cache` exists for tests
   and for an operator who wants an immediate re-read.

The RSL ``License:`` directive is read from the same body and, when it points
at the same origin, the licence XML is fetched once and parsed into
:class:`acquisition.urls.rights_terms.RightsTerms` — the free machine-readable
"gate already dropped" signal this lane exists to surface. A cross-origin
``License:`` URL is recorded but NOT followed: a robots.txt must not be able
to direct the fetcher at an arbitrary third host (the SSRF shape the
acquisition layer already guards against elsewhere).

Redirects: the fetcher consults robots.txt again for every redirect hop's
origin (acquisition.urls.client), so a page that redirects to a disallowed
path on another host is refused before that host is asked for it. The licence
file is fetched only if robots.txt allows it and only while it stays on the
declaring origin.
"""

from __future__ import annotations

import logging
import threading
import time
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

# How long a cached policy is trusted. A fetched answer (rules applied, or a
# definitive 4xx) lasts the 24 hours RFC 9309 §2.4 allows; an unreachable one
# (5xx, 429, transport error) is re-tried after five minutes so a transient
# outage cannot switch enforcement off for the life of a long-lived process.
ROBOTS_CACHE_TTL_S = 24 * 60 * 60.0
UNREACHABLE_RETRY_S = 5 * 60.0

# Monotonic clock for cache expiry. A module attribute so a test can advance
# time without sleeping.
_clock: Callable[[], float] = time.monotonic

# The agent the purpose-neutral licence fetch is checked against.
# urllib.robotparser applies a group to us when the group's token is a
# substring of this one, so "*" and "Antiek" groups bind it; a
# purpose-specific group (e.g. "Antiek-Agent") does not.
LICENCE_FETCH_AGENT = "Antiek"

# Directive names seen in real robots.txt files. A non-empty body with none of
# them is not a robots file (typically an HTML error page served with 200).
_KNOWN_DIRECTIVES = frozenset({
    "user-agent", "allow", "disallow", "sitemap", "crawl-delay", "request-rate",
    "visit-time", "host", "clean-param", "noindex", "license",
})


# ``url -> (status_code, text, final_url_after_redirects)``. The fetcher
# supplies a closure that GETs through its own (possibly injected /
# arXiv-governed) client, so robots and licence fetches take exactly the
# transport the page fetch takes. It may raise on a transport error; the
# policy builder treats that as fail-open.
FetchText = Callable[[str], tuple[int, str, str]]


def _body_problem(text: str) -> str | None:
    """Why a 200 robots.txt body is not a robots file, or None when it is one.
    An empty or comment-only file IS one: it simply declares no rules."""
    if "\x00" in text:
        return "robots.txt contains NUL bytes (binary, not a robots file)"
    directive_lines = 0
    content_lines = 0
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        content_lines += 1
        key = line.partition(":")[0].strip().lower() if ":" in line else ""
        if key in _KNOWN_DIRECTIVES:
            directive_lines += 1
    if content_lines and not directive_lines:
        return "robots.txt has no robots directives (an HTML error page served with 200?)"
    return None


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


# origin -> (policy, monotonic expiry). See ROBOTS_CACHE_TTL_S / UNREACHABLE_RETRY_S.
_cache: dict[str, tuple[RobotsPolicy, float]] = {}
_cache_lock = threading.Lock()


def clear_robots_cache() -> None:
    """Drop every cached policy (tests; or a long-lived process re-reading)."""
    with _cache_lock:
        _cache.clear()


def cached_origins() -> tuple[str, ...]:
    """The origins currently held in the in-process cache, expired entries
    included (introspection)."""
    with _cache_lock:
        return tuple(_cache)


def robots_policy_for(url: str, *, fetch_text: FetchText) -> RobotsPolicy:
    """The policy for ``url``'s origin, building and caching it on first use
    and rebuilding it once the cached entry has expired.

    Concurrent builds for the same origin may both run. A concurrently stored
    entry wins only if it is at least as informative (an applied policy beats
    a fail-open one); otherwise the newer build is stored. Both paths avoid
    holding a lock across network I/O.
    """
    origin = origin_of(url)
    with _cache_lock:
        hit = _cache.get(origin)
    if hit is not None and hit[1] > _clock():
        return hit[0]
    built, ttl_s = _build_policy(origin, fetch_text)
    with _cache_lock:
        current = _cache.get(origin)
        if (
            current is not None
            and current is not hit
            and current[1] > _clock()
            and (current[0].applied or not built.applied)
        ):
            return current[0]
        _cache[origin] = (built, _clock() + ttl_s)
        return built


def _fail_open(
    origin: str,
    robots_url: str,
    parser: urllib.robotparser.RobotFileParser,
    reason: str,
    ttl_s: float,
) -> tuple[RobotsPolicy, float]:
    parser.parse([])
    logger.warning(
        "%s: %s; failing OPEN — no robots rules enforced for this origin until "
        "it is re-checked in %.0fs (fetches proceed; the site did not tell us "
        "not to)",
        origin,
        reason,
        ttl_s,
    )
    policy = RobotsPolicy(
        origin=origin,
        robots_url=robots_url,
        applied=False,
        fail_open_reason=reason,
        license_url=None,
        rights_terms=NO_TERMS,
        parser=parser,
    )
    return policy, ttl_s


def _build_policy(origin: str, fetch_text: FetchText) -> tuple[RobotsPolicy, float]:
    """Fetch and parse ``origin``'s robots.txt; return the policy and how long
    it may be cached."""
    robots_url = f"{origin}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        status, text, _final_url = fetch_text(robots_url)
    except Exception as exc:
        return _fail_open(
            origin, robots_url, parser,
            f"robots.txt unreachable ({type(exc).__name__}: {exc})",
            UNREACHABLE_RETRY_S,
        )
    if status >= 500 or status == 429:
        return _fail_open(
            origin, robots_url, parser,
            f"robots.txt unreachable (HTTP {status})", UNREACHABLE_RETRY_S,
        )
    if status >= 400:
        return _fail_open(
            origin, robots_url, parser,
            f"robots.txt returned HTTP {status}", ROBOTS_CACHE_TTL_S,
        )
    size = len(text.encode("utf-8"))
    if size > MAX_ROBOTS_BYTES:
        return _fail_open(
            origin, robots_url, parser,
            f"robots.txt is {size} bytes (> {MAX_ROBOTS_BYTES}); not parsed",
            ROBOTS_CACHE_TTL_S,
        )
    problem = _body_problem(text)
    if problem:
        return _fail_open(origin, robots_url, parser, problem, ROBOTS_CACHE_TTL_S)
    try:
        parser.parse(text.splitlines())
    except Exception as exc:
        return _fail_open(
            origin, robots_url, parser,
            f"robots.txt unparseable ({type(exc).__name__}: {exc})",
            ROBOTS_CACHE_TTL_S,
        )
    license_url = parse_license_directive(text)
    try:
        rights_terms = _load_terms(origin, license_url, fetch_text, parser)
    except Exception as exc:
        rights_terms = RightsTerms(
            source="robots_license_directive",
            license_url=license_url,
            parse_error=f"licence unreadable ({type(exc).__name__}: {exc})",
        )
    policy = RobotsPolicy(
        origin=origin,
        robots_url=robots_url,
        applied=True,
        fail_open_reason=None,
        license_url=license_url,
        rights_terms=rights_terms,
        parser=parser,
    )
    return policy, ROBOTS_CACHE_TTL_S


def _load_terms(
    origin: str,
    license_url: str | None,
    fetch_text: FetchText,
    parser: urllib.robotparser.RobotFileParser,
) -> RightsTerms:
    if license_url is None:
        return NO_TERMS
    try:
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
    except ValueError as exc:
        return RightsTerms(
            source="robots_license_directive",
            license_url=license_url,
            parse_error=f"invalid licence URL ({exc})",
        )
    if not parser.can_fetch(LICENCE_FETCH_AGENT, absolute):
        logger.warning(
            "%s: robots.txt disallows its licence URL (%s); recorded, not fetched",
            origin,
            absolute,
        )
        return RightsTerms(
            source="robots_license_directive",
            license_url=absolute,
            parse_error="licence URL is disallowed by robots.txt; not fetched",
        )
    try:
        status, text, final_url = fetch_text(absolute)
    except Exception as exc:
        return RightsTerms(
            source="robots_license_directive",
            license_url=absolute,
            parse_error=f"licence unreachable ({type(exc).__name__}: {exc})",
        )
    if origin_of(final_url) != origin:
        logger.warning(
            "%s: licence URL redirected off-origin to %s; recorded, not used",
            origin,
            final_url,
        )
        return RightsTerms(
            source="robots_license_directive",
            license_url=absolute,
            parse_error=f"licence URL redirected off-origin to {final_url}; not used",
        )
    if status >= 400:
        return RightsTerms(
            source="robots_license_directive",
            license_url=absolute,
            parse_error=f"licence returned HTTP {status}",
        )
    size = len(text.encode("utf-8"))
    if size > MAX_LICENSE_BYTES:
        return RightsTerms(
            source="robots_license_directive",
            license_url=absolute,
            parse_error=f"licence is {size} bytes (> {MAX_LICENSE_BYTES}); not parsed",
        )
    return parse_rsl_xml(text, license_url=absolute)


__all__ = [
    "MAX_LICENSE_BYTES",
    "MAX_ROBOTS_BYTES",
    "ROBOTS_CACHE_TTL_S",
    "UNREACHABLE_RETRY_S",
    "FetchText",
    "RobotsDisallowed",
    "RobotsPolicy",
    "cached_origins",
    "clear_robots_cache",
    "origin_of",
    "robots_policy_for",
    "robots_url_for",
]
