"""Per-host ``robots.txt`` consultation for the general URL fetcher (SPR-10
task 4). Robots.txt is parsed and evaluated here per RFC 9309; the proven
single-host fail-open logic in ``acquisition/urls/paulgraham.py`` is
generalised to every host ``acquisition.urls.client.fetch`` touches.
``urllib.robotparser`` is not used: it keeps only the first ``*`` group,
matches substrings and first rules, and cannot tell a literal ``%2A`` from a
wildcard.

Three guarantees, in priority order:

1. **An explicit rule is honoured.** When the host publishes a robots.txt,
   :func:`robots_allows` evaluates its rules per RFC 9309 (most specific
   group, longest match, wildcards). A disallowed URL makes
   :meth:`RobotsPolicy.allows` return False and the fetcher raises
   :class:`RobotsDisallowed` BEFORE any
   request for the page is sent. This is the same posture as the paulgraham
   connector's ``robots_disallowed`` bucket. Matching never backtracks (one
   substring search per literal, however many wildcards a rule has) and a
   decision's cost is capped (:data:`MAX_MATCH_COST`), because the rules are
   the host's own text; a URL whose rules would cost more is refused, not
   waved through with rules unchecked.
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
   request per host per window, not one per page. It holds at most
   :data:`MAX_CACHED_ROBOTS_BYTES` of robots.txt and licence text, counting a
   licence when it is loaded after the policy was cached; past that, the
   least recently used origin is dropped and re-read if it is fetched again
   (the entry just used is never dropped, so one origin whose files alone
   exceed the budget is still held, alone). A fetched answer (rules
   applied, or a definitive 4xx) is held for :data:`ROBOTS_CACHE_TTL_S`, the
   24 hours RFC 9309 §2.4 allows, so a publisher who adds a ``Disallow`` is
   honoured by a long-lived API process within a day rather than at its next
   restart. An unreachable one (5xx / transport error) is held only for
   :data:`UNREACHABLE_RETRY_S`. :func:`clear_robots_cache` exists for tests
   and for an operator who wants an immediate re-read.

The RSL ``License:`` directive is selected per user-agent group (a group-
scoped licence beats the global one, per RSL). When it points at the same
origin, the licence XML is fetched lazily, once per agent token, by
:meth:`RobotsPolicy.terms_for` and parsed into one
:class:`acquisition.urls.rights_terms.RightsTerms` per ``<content url>``
scope — the free machine-readable "gate already dropped" signal this lane
exists to surface. A page gets the terms of the most specific scope whose
``url`` pattern covers the URL the fetch ended on (RSL 1.0 s3.1.1, s3.3,
matched with the robots.txt path matcher below), or
``source="rsl_out_of_scope"`` when none covers it: a licence for ``/free``
says nothing about ``/paid``. A cross-origin ``License:`` URL is recorded
but NOT followed: a robots.txt must not be able to direct the fetcher at an
arbitrary third host (the SSRF shape the acquisition layer already guards
against elsewhere).

Redirects: the fetcher consults robots.txt again for every redirect hop's
origin (acquisition.urls.client), so a page that redirects to a disallowed
path on another host is refused before that host is asked for it. The
robots.txt request is itself followed one hop at a time, at most
:data:`MAX_ROBOTS_REDIRECTS` hops (RFC 9309 s2.3.1.2): a hop to a
``/robots.txt`` path or within the origin being resolved is followed; a hop
to another origin's page is followed only if that origin's own robots.txt
allows it, so ``A/robots.txt -> B/private`` never fetches a page B
disallows. A redirect that cannot be followed leaves the origin failing
open with a reason. The licence file is never fetched through a redirect;
it is fetched only if robots.txt allows the declaring agent's direct licence
URL.
"""

from __future__ import annotations

import logging
import string
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from acquisition.urls.rights_terms import (
    NO_LICENCE,
    NO_TERMS,
    RightsTerms,
    RslLicence,
    parse_rsl_licence,
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

# RFC 9309 s2.3.1.2: a crawler "SHOULD follow at least five consecutive
# redirects, even across authorities", and past five MAY treat robots.txt as
# unavailable. The robots.txt request follows exactly this many hops, one at
# a time (_build_policy), and a hop into another origin is itself checked
# against that origin's robots.txt, so nesting is bounded by the same number.
MAX_ROBOTS_REDIRECTS = 5

# The most robots.txt text the policy cache holds, summed over origins
# (_policy_weight). Measured 2026-09-23, a parsed file takes at most 14x its
# weight in memory for twelve real files and at most 21x for 512 KiB files of
# one-wildcard rules, so the cache stays under about 90 MB however many
# origins a long-lived process fetches, while still holding a few hundred
# typical ones. The least recently used origin is dropped first; if it is
# fetched again, its robots.txt is simply read again.
MAX_CACHED_ROBOTS_BYTES = 4 * 1024 * 1024

# The most character comparisons one robots_allows() decision may spend
# searching for the literals of wildcard rules (_rule_matches charges each
# search the most any substring search can cost; rules without a wildcard cost
# one prefix comparison and are not charged). The robots.txt is the host's own
# text and the URL can be the host's own redirect target, so without a bound
# the host chooses how long a decision holds the GIL: 512 KiB of "/*ab" rules
# against a 16 KiB path took 0.9 s, and the time grows with the path. Measured
# 2026-09-23: at this bound every hostile file tried (up to 40k rules, up to
# 1000 wildcards in a rule) was decided in under 70 ms, while the costliest of
# twelve real files (github.com, 199 wildcard rules) spent 1.2M comparisons
# on a 2 KiB URL and 9.7M on a 16 KiB one. Exceeding it refuses the URL.
MAX_MATCH_COST = 1 << 25

# Monotonic clock for cache expiry. A module attribute so a test can advance
# time without sleeping.
_clock: Callable[[], float] = time.monotonic

# Directive names seen in real robots.txt files. A non-empty body with none of
# them is not a robots file (typically an HTML error page served with 200).
_KNOWN_DIRECTIVES = frozenset({
    "user-agent", "allow", "disallow", "sitemap", "crawl-delay", "request-rate",
    "visit-time", "host", "clean-param", "noindex", "license",
})


# ``(url, follow_redirects) -> (status_code, text, url)``. The fetcher
# supplies a closure that GETs through its own (possibly injected /
# arXiv-governed) client, so robots and licence fetches take exactly the
# transport the page fetch takes. This module always passes
# ``follow_redirects=False`` and follows (or refuses) each hop itself; for a
# redirect response the third element is then the absolute URL its Location
# points at, otherwise the URL that answered. It may raise on a transport
# error; the policy builder treats that as fail-open.
FetchText = Callable[[str, bool], tuple[int, str, str]]


@dataclass(frozen=True)
class RobotsRule:
    """One Allow/Disallow rule, with its value exactly as written.

    ``_compiled`` is the value prepared for matching (see
    :func:`_compile_rule`). It is derived once, when the rule is parsed, so a
    decision never re-normalises a rule; it takes no part in equality."""

    allow: bool
    path: str
    _compiled: _CompiledRule = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_compiled", _compile_rule(self.path))


@dataclass(frozen=True)
class RobotsGroup:
    """A robots.txt record: agent tokens and the rules they opened together."""

    agents: tuple[str, ...]
    rules: tuple[RobotsRule, ...]
    licenses: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedRobots:
    """The records relevant to Allow/Disallow matching and RSL selection."""

    groups: tuple[RobotsGroup, ...] = ()
    global_licenses: tuple[str, ...] = ()


NO_RULES = ParsedRobots()


def parse_robots(text: str) -> ParsedRobots:
    """Parse robots.txt grouping per RFC 9309 s2.1.

    Consecutive user-agent lines open one group; allow/disallow lines add
    rules to the open group; a user-agent line that follows any other record
    starts a new group; allow/disallow before the first user-agent line are
    ignored. Other records (sitemap, crawl-delay, ...) are ignored for
    matching; ``License:`` values are collected globally or for the open
    group. Comments (#) and blank lines are skipped. Keys are
    case-insensitive. A user-agent value is reduced to its product token: the
    text before the first ``/`` or whitespace, lower-cased.
    """
    text = text.removeprefix(_BOM)
    groups: list[RobotsGroup] = []
    agents: list[str] = []
    rules: list[RobotsRule] = []
    group_licenses: list[str] = []
    global_licenses: list[str] = []
    in_agent_run = False

    def close_group() -> None:
        nonlocal agents, rules, group_licenses
        if agents:
            groups.append(
                RobotsGroup(tuple(agents), tuple(rules), tuple(group_licenses))
            )
        agents = []
        rules = []
        group_licenses = []

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if not in_agent_run and agents:
                close_group()
            agents.append(value.split()[0].split("/")[0].lower() if value else "")
            in_agent_run = True
        elif key in {"allow", "disallow"}:
            if agents:
                rules.append(RobotsRule(key == "allow", value))
            in_agent_run = False
        elif key == "license" and value:
            if agents:
                group_licenses.append(value)
            else:
                global_licenses.append(value)
        # Any other record (sitemap, crawl-delay, license, ...) neither opens
        # nor closes a group: RFC 9309 s2.2.4 says it must not interfere with
        # rule-group parsing.
    close_group()
    return ParsedRobots(tuple(groups), tuple(global_licenses))


def _body_problem(text: str) -> str | None:
    """Why a 200 robots.txt body is not a robots file, or None when it is one.
    An empty or comment-only file IS one: it simply declares no rules."""
    text = text.removeprefix(_BOM)
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


_terms_lock = threading.Lock()


@dataclass(frozen=True)
class RobotsPolicy:
    """The parsed robots posture for one origin.

    ``applied`` is True iff a robots.txt body was fetched and parsed and its
    rules govern :meth:`allows`. When False, ``fail_open_reason`` says why
    and :meth:`allows` is unconditionally True (the fail-open posture).
    """

    origin: str
    robots_url: str
    applied: bool
    fail_open_reason: str | None
    rules: ParsedRobots = field(default=NO_RULES, repr=False, compare=False)
    _licences_by_agent: dict[str, RslLicence] = field(
        default_factory=dict, repr=False, compare=False
    )

    def allows(self, user_agent: str, url: str) -> bool:
        """True iff ``user_agent`` may fetch ``url`` under this policy."""
        if not self.applied:
            return True
        return robots_allows(self.rules, user_agent, url)

    def terms_for(
        self, user_agent: str, url: str, *, fetch_text: FetchText
    ) -> RightsTerms:
        """The RSL terms ``user_agent`` gets for ``url`` on this origin: the
        licence its selected group names, else the global one (RSL), narrowed
        to the most specific ``<content>`` scope covering ``url``
        (:func:`terms_covering`). The licence is fetched at most once per
        agent token per cached policy, and the policy's cache weight is
        brought up to date when it is; never raises."""
        if not self.applied:
            return NO_TERMS
        token = user_agent.split("/", 1)[0].strip().lower()
        with _terms_lock:
            licence = self._licences_by_agent.get(token)
        if licence is None:
            try:
                loaded = _load_licence(
                    self.origin,
                    select_license(self.rules, user_agent),
                    fetch_text,
                    self.rules,
                    user_agent,
                )
            except Exception as exc:
                loaded = _unusable(
                    None, f"licence unreadable ({type(exc).__name__}: {exc})"
                )
            with _terms_lock:
                licence = self._licences_by_agent.setdefault(token, loaded)
            _reweigh(self)
        return terms_covering(licence, origin=self.origin, url=url)


def origin_of(url: str) -> str:
    """``scheme://host[:port]`` (lower-cased) — the cache key and the boundary
    a ``License:`` URL must stay inside."""
    parts = urlsplit(url)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def robots_url_for(url: str) -> str:
    return f"{origin_of(url)}/robots.txt"


def _selected_groups(
    robots: ParsedRobots,
    user_agent: str,
) -> tuple[RobotsGroup, ...]:
    """The RFC 9309 groups that govern ``user_agent``.
    Group selection (RFC 9309 s2.2.1, with the product-family fallback major
    crawlers use): take the product token (the User-Agent up to the first
    '/', lower-cased, e.g. "antiek-agent"); select the groups naming exactly
    that token; if none, the groups naming its longest '-'-delimited prefix
    ("antiek"), and so on; if none, the '*' group. All groups at the chosen
    level are merged; an empty result means no group applies."""
    token = user_agent.split("/", 1)[0].strip().lower()
    parts = token.split("-")
    candidates = ["-".join(parts[:i]) for i in range(len(parts), 0, -1)]
    for candidate in candidates:
        matched = tuple(group for group in robots.groups if candidate in group.agents)
        if matched:
            return matched
    return tuple(group for group in robots.groups if "*" in group.agents)


def robots_allows(
    robots: ParsedRobots,
    user_agent: str,
    url: str,
) -> bool:
    """RFC 9309 evaluation over :func:`parse_robots`' result.
    :func:`_selected_groups` chooses the governing groups.
    Rule matching (RFC 9309 s2.2.2/s2.2.3): the longest matching rule path
    wins, Allow wins a tie, '*' matches any sequence and a trailing '$'
    anchors the end. No matching rule means allowed.

    Matching never backtracks (:func:`_rule_matches`), and one decision
    spends at most :data:`MAX_MATCH_COST` character comparisons. A decision
    that would need more returns False with a WARNING: the rules are the
    host's explicit ones, and skipping those never checked could let through
    a URL one of them disallows."""
    selected_groups = _selected_groups(robots, user_agent)
    if not selected_groups:
        return True
    rules = tuple(rule for group in selected_groups for rule in group.rules)

    normalised = _match_target(url)
    budget = _MatchBudget(MAX_MATCH_COST)
    matching: list[tuple[int, bool]] = []
    try:
        for rule in rules:
            if rule.path and _rule_matches(rule._compiled, normalised, budget):
                matching.append((rule._compiled.specificity, rule.allow))
    except _MatchBudgetExhausted:
        logger.warning(
            "%s: robots.txt needs more than %d character comparisons to decide "
            "%.200r (%d chars); treating it as disallowed rather than skipping "
            "rules never checked",
            origin_of(url),
            MAX_MATCH_COST,
            url,
            len(url),
        )
        return False
    if not matching:
        return True
    return max(matching)[1]


def _match_target(url: str) -> str:
    """``url``'s path and query in the one form rules are matched against.

    Normalise first (which decodes %2E to "."), then resolve dot segments,
    so "/a/../x" and "/a/%2E%2E/x" are both judged as "/x": the path an HTTP
    client or a normalising server actually ends up at."""
    parsed_url = urlsplit(url)
    normalised = _remove_dot_segments(_normalise(parsed_url.path)) or "/"
    if parsed_url.query:
        normalised = f"{normalised}?{_normalise(parsed_url.query)}"
    return normalised


def _scope_pattern(content_url: str, origin: str) -> str | None:
    """The RFC 9309 path pattern an RSL ``<content url>`` covers on
    ``origin``, or None when it covers nothing there.

    RSL 1.0 s3.3 makes the value "a path conforming to the rules defined in
    [RFC 9309], including the use of wildcards"; an absolute URL is also
    accepted when it names this origin (its path and query are the
    pattern). An empty value names the scope the licence was associated
    with (RSL 1.0 s4.6.1), which for a robots.txt ``License:`` is the whole
    origin: the empty pattern, matching every path at the lowest
    specificity."""
    value = content_url.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        if origin_of(value) != origin:
            return None
        path = parts.path or "/"
        return f"{path}?{parts.query}" if parts.query else path
    return value if value.startswith(("/", "*")) else f"/{value}"


def terms_covering(licence: RslLicence, *, origin: str, url: str) -> RightsTerms:
    """The terms ``licence`` (declared on ``origin``) gives the page ``url``.

    ``licence.unscoped`` answers for every page when set. Otherwise the
    ``<content>`` scope with the most specific pattern that matches ``url``
    wins (RSL 1.0 s3.1.1; specificity and matching are RFC 9309's, as for an
    Allow/Disallow rule), the earlier one on a tie. A ``url`` on another
    origin, or one no scope covers, gets ``source="rsl_out_of_scope"``:
    nothing is known about that page. Matching is charged against
    :data:`MAX_MATCH_COST` like a robots decision; a licence too costly to
    match also answers out of scope, with a ``parse_error`` saying so."""
    if licence.unscoped is not None:
        return licence.unscoped
    out_of_scope = RightsTerms(source="rsl_out_of_scope", license_url=licence.license_url)
    if origin_of(url) != origin:
        return out_of_scope
    target = _match_target(url)
    budget = _MatchBudget(MAX_MATCH_COST)
    best: RightsTerms | None = None
    best_specificity = -1
    try:
        for scope in licence.scopes:
            if scope.content_url is None:
                continue
            pattern = _scope_pattern(scope.content_url, origin)
            if pattern is None:
                continue
            compiled = _compile_rule(pattern)
            if compiled.specificity > best_specificity and _rule_matches(
                compiled, target, budget
            ):
                best, best_specificity = scope, compiled.specificity
    except _MatchBudgetExhausted:
        logger.warning(
            "%s: licence %s needs more than %d character comparisons to scope "
            "%.200r; its terms are treated as unknown for this page",
            origin,
            licence.license_url,
            MAX_MATCH_COST,
            url,
        )
        return RightsTerms(
            source="rsl_out_of_scope",
            license_url=licence.license_url,
            parse_error="licence scopes too costly to match against this URL",
        )
    return best if best is not None else out_of_scope


def _remove_dot_segments(path: str) -> str:
    """Remove literal ``.`` and ``..`` segments exactly as HTTP clients do.

    Percent-encoded dots (``%2E``) are deliberately left alone, matching
    ``httpx.URL``. The explicit leading-slash and trailing-slash repairs keep
    absolute paths absolute and preserve the distinction between ``/a/..``
    (a directory traversal) and ``/a/../`` (the resulting directory)."""
    segments = path.split("/")
    out: list[str] = []
    for segment in segments:
        if segment == ".":
            continue
        if segment == "..":
            if len(out) > 1:
                out.pop()
            continue
        out.append(segment)
    result = "/".join(out)
    if path.endswith(("/.", "/..")) and not result.endswith("/"):
        result += "/"
    if path.startswith("/") and not result.startswith("/"):
        result = f"/{result}"
    return result


def select_license(robots: ParsedRobots, user_agent: str) -> str | None:
    """The first RSL licence that applies to ``user_agent`` (RSL group scope).

    A licence in any selected user-agent group beats every global licence;
    when no selected group declares one, the global licences apply. ``None``
    means no applicable licence was declared."""
    selected_groups = _selected_groups(robots, user_agent)
    licenses = tuple(
        license_url for group in selected_groups for license_url in group.licenses
    ) or robots.global_licenses
    return next(iter(licenses), None)


@dataclass(frozen=True, slots=True)
class _CompiledRule:
    """A rule path split at its wildcards, for matching without backtracking.

    The normalised path must start with ``head`` (the text before the first
    ``*``). A rule with no ``*`` is then decided: it matches, or for a ``$``
    rule it matches only if nothing follows. Otherwise each of ``inner`` (the
    texts between wildcards, empty ones dropped) must occur after the head,
    in order and without overlapping; and an anchored rule's ``tail`` (the
    text after its last ``*``) must end the path, after all of them."""

    head: str
    inner: tuple[str, ...]
    tail: str
    wildcard: bool
    anchored: bool
    specificity: int


def _compile_rule(pattern_text: str) -> _CompiledRule:
    anchored = pattern_text.endswith("$")
    body = pattern_text[:-1] if anchored else pattern_text
    segments = [_normalise(segment) for segment in body.split("*")]
    head, rest = segments[0], segments[1:]
    tail = rest.pop() if anchored and rest else ""
    # Precedence is by the octets of the NORMALISED rule (RFC 9309 s2.2.2), so
    # two spellings of the same path ("/caf%C3%A9" and "/café") tie and Allow
    # wins the tie.
    specificity = len("*".join(segments)) + (1 if anchored else 0)
    return _CompiledRule(
        head=head,
        inner=tuple(segment for segment in rest if segment),
        tail=tail,
        wildcard=len(segments) > 1,
        anchored=anchored,
        specificity=specificity,
    )


class _MatchBudgetExhausted(Exception):
    """A decision would exceed :data:`MAX_MATCH_COST`."""


class _MatchBudget:
    """The character comparisons one decision may still spend."""

    __slots__ = ("remaining",)

    def __init__(self, total: int) -> None:
        self.remaining = total

    def spend(self, cost: int) -> None:
        self.remaining -= cost
        if self.remaining < 0:
            raise _MatchBudgetExhausted


def _rule_matches(rule: _CompiledRule, target: str, budget: _MatchBudget) -> bool:
    """Whether ``rule`` matches the start of ``target`` (RFC 9309 s2.2.3).

    Each literal between wildcards is placed at its leftmost occurrence after
    the previous one and never revisited. That is exact: an earlier placement
    leaves at least as much of the path for everything that follows, so if
    any placement matches, the leftmost one does. The work is one substring
    search per literal, whatever the number of wildcards, where a regex with
    one ``.*`` per wildcard backtracks through every combination of positions.

    Each search is charged ``len(target) - pos`` times the literal's length,
    which bounds what any substring search can spend on it, so a
    :data:`MAX_MATCH_COST` budget bounds the whole decision."""
    if not target.startswith(rule.head):
        return False
    if not rule.wildcard:
        return not rule.anchored or len(target) == len(rule.head)
    pos = len(rule.head)
    for literal in rule.inner:
        budget.spend((len(target) - pos) * len(literal))
        found = target.find(literal, pos)
        if found < 0:
            return False
        pos = found + len(literal)
    if not rule.anchored:
        return True
    return len(target) - len(rule.tail) >= pos and target.endswith(rule.tail)


_UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
_HEX = frozenset(string.hexdigits)
_SPECIAL_ENCODED = {"*": "%2A", "$": "%24"}

# A UTF-8 byte-order mark some servers prepend. Left in place it glues onto
# the first key ("\ufeffuser-agent") and silently drops the first group.
_BOM = "\ufeff"


def _normalise(value: str) -> str:
    """Put a path in the one form RFC 9309 s2.2.2 compares.

    A percent-encoded octet is decoded only when it is an unreserved
    character (RFC 3986 s2.3); any other stays encoded, upper-cased, so
    ``%2F`` never collapses into ``/``. Non-ASCII characters are UTF-8
    percent-encoded. The two robots special characters are compared in
    encoded form (RFC 9309 s2.2.3: pattern ``/file-with-a-%2A.html`` matches
    URI ``/file-with-a-*.html``): a literal ``*`` or ``$`` becomes ``%2A`` /
    ``%24``. A rule's wildcard ``*`` and trailing ``$`` are split off before
    this runs, so they never reach it. Every other ASCII character is kept as
    written."""
    out: list[str] = []
    i = 0
    while i < len(value):
        char = value[i]
        pair = value[i + 1 : i + 3]
        if char == "%" and len(pair) == 2 and set(pair) <= _HEX:
            decoded = chr(int(pair, 16))
            out.append(decoded if decoded in _UNRESERVED else "%" + pair.upper())
            i += 3
            continue
        if ord(char) > 127:
            out.append("".join(f"%{byte:02X}" for byte in char.encode("utf-8")))
        else:
            out.append(_SPECIAL_ENCODED.get(char, char))
        i += 1
    return "".join(out)


# origin -> (policy, monotonic expiry, weight), least recently used first.
# See ROBOTS_CACHE_TTL_S / UNREACHABLE_RETRY_S and MAX_CACHED_ROBOTS_BYTES.
_cache: dict[str, tuple[RobotsPolicy, float, int]] = {}
_cache_lock = threading.Lock()

# Per-entry weight on top of the rule text, so a cache of fail-open policies
# (no rules at all) is bounded too.
_ENTRY_WEIGHT = 256


def clear_robots_cache() -> None:
    """Drop every cached policy (tests; or a long-lived process re-reading)."""
    with _cache_lock:
        _cache.clear()


def cached_origins() -> tuple[str, ...]:
    """The origins currently held in the in-process cache, least recently used
    first (introspection). An expired entry stays until the next store sweeps
    it."""
    with _cache_lock:
        return tuple(_cache)


def _terms_weight(terms: RightsTerms) -> int:
    """About the characters one parsed licence scope holds."""
    weight = _ENTRY_WEIGHT // 4
    for text in (terms.license_url, terms.content_url, terms.parse_error):
        weight += len(text or "")
    for values in (
        terms.payment_types,
        terms.permits,
        terms.prohibits,
        terms.standard_urls,
        terms.license_servers,
    ):
        weight += sum(len(value) + 8 for value in values)
    return weight


def _licence_weight(licence: RslLicence) -> int:
    scopes = licence.scopes if licence.unscoped is None else (licence.unscoped,)
    return len(licence.license_url or "") + sum(_terms_weight(scope) for scope in scopes)


def _policy_weight(policy: RobotsPolicy) -> int:
    """About the characters ``policy`` holds: each kept robots.txt record's
    value plus its directive name and newline, and every licence loaded for
    it so far (:meth:`RobotsPolicy.terms_for` re-weighs the entry when it
    loads one). Takes ``_terms_lock``; callers hold ``_cache_lock`` first."""
    parsed = policy.rules
    weight = _ENTRY_WEIGHT + sum(len(url) + 10 for url in parsed.global_licenses)
    for group in parsed.groups:
        weight += sum(len(agent) + 13 for agent in group.agents)
        weight += sum(len(rule.path) + 10 for rule in group.rules)
        weight += sum(len(url) + 10 for url in group.licenses)
    with _terms_lock:
        licences = tuple(policy._licences_by_agent.values())
    return weight + sum(_licence_weight(licence) for licence in licences)


def _evict_over_budget() -> None:
    """Drop least recently used entries until the cache is back under
    :data:`MAX_CACHED_ROBOTS_BYTES`, never the most recently used one. The
    caller holds ``_cache_lock``."""
    total = sum(entry[2] for entry in _cache.values())
    while total > MAX_CACHED_ROBOTS_BYTES and len(_cache) > 1:
        total -= _cache.pop(next(iter(_cache)))[2]


def _store(origin: str, policy: RobotsPolicy, expiry: float) -> None:
    """Cache ``policy`` as the most recently used entry, then sweep expired
    entries and drop least recently used ones until the cache is back under
    :data:`MAX_CACHED_ROBOTS_BYTES`. The caller holds ``_cache_lock``."""
    _cache.pop(origin, None)
    now = _clock()
    for stale in [key for key, entry in _cache.items() if entry[1] <= now]:
        del _cache[stale]
    _cache[origin] = (policy, expiry, _policy_weight(policy))
    _evict_over_budget()


def _reweigh(policy: RobotsPolicy) -> None:
    """Bring ``policy``'s cache weight up to date after a licence was loaded
    into it, make it the most recently used entry, and evict to budget. A
    policy no longer in the cache (evicted or replaced) is left alone."""
    with _cache_lock:
        entry = _cache.get(policy.origin)
        if entry is None or entry[0] is not policy:
            return
        del _cache[policy.origin]
        _cache[policy.origin] = (policy, entry[1], _policy_weight(policy))
        _evict_over_budget()


def robots_policy_for(
    url: str,
    *,
    fetch_text: FetchText,
    user_agent: str,
) -> RobotsPolicy:
    """The policy for ``url``'s origin, building and caching it on first use
    and rebuilding it once the cached entry has expired.

    Concurrent builds for the same origin may both run. A concurrently stored
    entry wins only if it is at least as informative (an applied policy beats
    a fail-open one); otherwise the newer build is stored. Both paths avoid
    holding a lock across network I/O.
    """
    return _policy_for(url, fetch_text, user_agent, frozenset())


def _policy_for(
    url: str,
    fetch_text: FetchText,
    user_agent: str,
    resolving: frozenset[str],
) -> RobotsPolicy:
    """:func:`robots_policy_for`, carrying the origins whose robots.txt is
    being resolved further up this call chain (a robots.txt redirect into
    another origin resolves that origin's policy first)."""
    origin = origin_of(url)
    with _cache_lock:
        hit = _cache.get(origin)
        if hit is not None and hit[1] > _clock():
            _cache[origin] = _cache.pop(origin)  # now the most recently used
            return hit[0]
    built, ttl_s = _build_policy(origin, fetch_text, user_agent, resolving | {origin})
    with _cache_lock:
        current = _cache.get(origin)
        if (
            current is not None
            and current is not hit
            and current[1] > _clock()
            and (current[0].applied or not built.applied)
        ):
            return current[0]
        _store(origin, built, _clock() + ttl_s)
        return built


def _fail_open(
    origin: str,
    robots_url: str,
    reason: str,
    ttl_s: float,
) -> tuple[RobotsPolicy, float]:
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
        rules=NO_RULES,
    )
    return policy, ttl_s


def _robots_redirect_refusal(
    origin: str,
    target: str,
    fetch_text: FetchText,
    user_agent: str,
    resolving: frozenset[str],
) -> str | None:
    """Why the robots.txt request for ``origin`` must not follow a redirect
    to ``target``, or None when it may.

    A robots.txt is never governed by robots rules (RFC 9309), so a hop to a
    ``/robots.txt`` path is followed, as is a hop within ``origin`` (its
    rules are the ones being read; the site chose where its file lives). A
    hop to any other origin's page is a request like any other: that
    origin's own robots.txt is resolved first (following the same rules) and
    must allow ``target`` for ``user_agent``. An origin already being
    resolved up the chain cannot be consulted, so a redirect back into one
    is refused, which also bounds the nesting."""
    parts = urlsplit(target)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return f"robots.txt redirected to {target!r}, not an http(s) URL; not followed"
    destination = origin_of(target)
    if destination == origin or parts.path == "/robots.txt":
        return None
    if destination in resolving or len(resolving) > MAX_ROBOTS_REDIRECTS:
        return (
            f"robots.txt redirected to {target}, whose origin's robots.txt is "
            "itself being resolved; not followed"
        )
    policy = _policy_for(target, fetch_text, user_agent, resolving)
    if not policy.allows(user_agent, target):
        return (
            f"robots.txt redirected to {target}, which {policy.robots_url} "
            f"disallows for {user_agent}; not fetched"
        )
    return None


def _build_policy(
    origin: str,
    fetch_text: FetchText,
    user_agent: str,
    resolving: frozenset[str] = frozenset(),
) -> tuple[RobotsPolicy, float]:
    """Fetch and parse ``origin``'s robots.txt; return the policy and how long
    it may be cached.

    Redirects are followed here, one hop at a time and at most
    :data:`MAX_ROBOTS_REDIRECTS` of them, each checked by
    :func:`_robots_redirect_refusal` before it is requested; one that may
    not be followed leaves the origin failing open with the reason.
    ``resolving`` holds the origins being resolved up this call chain."""
    robots_url = f"{origin}/robots.txt"
    url = robots_url
    hops = 0
    while True:
        try:
            status, text, next_url = fetch_text(url, False)
        except Exception as exc:
            return _fail_open(
                origin, robots_url,
                f"robots.txt unreachable ({type(exc).__name__}: {exc})",
                UNREACHABLE_RETRY_S,
            )
        if not 300 <= status < 400:
            break
        target = urljoin(url, next_url) if next_url else ""
        if not target or target == url:
            return _fail_open(
                origin, robots_url,
                f"robots.txt redirected (HTTP {status}) with no usable Location",
                UNREACHABLE_RETRY_S,
            )
        if hops >= MAX_ROBOTS_REDIRECTS:
            return _fail_open(
                origin, robots_url,
                f"robots.txt redirected more than {MAX_ROBOTS_REDIRECTS} times "
                "(RFC 9309 s2.3.1.2: treated as unavailable)",
                ROBOTS_CACHE_TTL_S,
            )
        refusal = _robots_redirect_refusal(
            origin, target, fetch_text, user_agent, resolving | {origin}
        )
        if refusal is not None:
            return _fail_open(origin, robots_url, refusal, UNREACHABLE_RETRY_S)
        url = target
        hops += 1
    if status >= 500 or status == 429:
        return _fail_open(
            origin, robots_url,
            f"robots.txt unreachable (HTTP {status})", UNREACHABLE_RETRY_S,
        )
    if status >= 400:
        return _fail_open(
            origin, robots_url,
            f"robots.txt returned HTTP {status}", ROBOTS_CACHE_TTL_S,
        )
    size = len(text.encode("utf-8"))
    if size > MAX_ROBOTS_BYTES:
        return _fail_open(
            origin, robots_url,
            f"robots.txt is {size} bytes (> {MAX_ROBOTS_BYTES}); not parsed",
            ROBOTS_CACHE_TTL_S,
        )
    problem = _body_problem(text)
    if problem:
        return _fail_open(origin, robots_url, problem, ROBOTS_CACHE_TTL_S)
    rules = parse_robots(text)
    policy = RobotsPolicy(
        origin=origin,
        robots_url=robots_url,
        applied=True,
        fail_open_reason=None,
        rules=rules,
    )
    return policy, ROBOTS_CACHE_TTL_S


def _unusable(license_url: str | None, reason: str) -> RslLicence:
    """A declared licence that could not be read: the same answer for every
    page, carrying why."""
    return RslLicence(
        license_url=license_url,
        unscoped=RightsTerms(
            source="robots_license_directive",
            license_url=license_url,
            parse_error=reason,
        ),
    )


def _load_licence(
    origin: str,
    license_url: str | None,
    fetch_text: FetchText,
    rules: ParsedRobots,
    user_agent: str,
) -> RslLicence:
    if license_url is None:
        return NO_LICENCE
    try:
        absolute = urljoin(origin + "/", license_url)
        if origin_of(absolute) != origin:
            logger.warning(
                "%s: robots.txt License: directive points off-origin (%s); recorded, "
                "not followed",
                origin,
                absolute,
            )
            return _unusable(absolute, "cross-origin licence URL not followed")
    except ValueError as exc:
        return _unusable(license_url, f"invalid licence URL ({exc})")
    if not robots_allows(rules, user_agent, absolute):
        logger.warning(
            "%s: robots.txt disallows its licence URL (%s); recorded, not fetched",
            origin,
            absolute,
        )
        return _unusable(absolute, "licence URL is disallowed by robots.txt; not fetched")
    try:
        status, text, final_url = fetch_text(absolute, False)
    except Exception as exc:
        return _unusable(absolute, f"licence unreachable ({type(exc).__name__}: {exc})")
    if 300 <= status < 400:
        return _unusable(absolute, f"licence URL redirected (HTTP {status}); not followed")
    if origin_of(final_url) != origin:
        logger.warning(
            "%s: licence URL redirected off-origin to %s; recorded, not used",
            origin,
            final_url,
        )
        return _unusable(absolute, f"licence URL redirected off-origin to {final_url}; not used")
    if status >= 400:
        return _unusable(absolute, f"licence returned HTTP {status}")
    size = len(text.encode("utf-8"))
    if size > MAX_LICENSE_BYTES:
        return _unusable(absolute, f"licence is {size} bytes (> {MAX_LICENSE_BYTES}); not parsed")
    return parse_rsl_licence(text, license_url=absolute)


__all__ = [
    "MAX_LICENSE_BYTES",
    "MAX_CACHED_ROBOTS_BYTES",
    "MAX_MATCH_COST",
    "MAX_ROBOTS_BYTES",
    "MAX_ROBOTS_REDIRECTS",
    "ROBOTS_CACHE_TTL_S",
    "UNREACHABLE_RETRY_S",
    "FetchText",
    "ParsedRobots",
    "RobotsDisallowed",
    "RobotsPolicy",
    "RobotsGroup",
    "RobotsRule",
    "parse_robots",
    "cached_origins",
    "clear_robots_cache",
    "origin_of",
    "robots_allows",
    "robots_policy_for",
    "robots_url_for",
    "select_license",
    "terms_covering",
]
