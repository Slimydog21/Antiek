"""URL fetcher.

Thin httpx wrapper that returns the raw HTML + the final URL after
redirects + the declared content-type charset (so extraction can
decode bytes correctly when the server omits one).

The caller can inject an ``httpx.Client`` with a ``MockTransport``
for tests; production calls ``fetch(url)`` and gets a short-lived
client. Follow-redirects defaults to True — the polite path for
news/blog sources that 301 ``http://`` to ``https://`` or to a
canonical slug.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

import httpx

from acquisition.contact import ANTIEK_CONTACT_URL
from acquisition.urls.rights_terms import NO_TERMS, RightsTerms
from acquisition.urls.robots import RobotsDisallowed, robots_policy_for

logger = logging.getLogger("acquisition.urls.client")
DEFAULT_TIMEOUT_S = 20.0


class FetchPurpose(StrEnum):
    """Why Antiek is fetching a page.

    Each purpose sends its own User-Agent so a site, or a CDN, can allow or
    refuse each use separately. Cloudflare's 2026-09-15 post
    (https://blog.cloudflare.com/accountable-mixed-use-ai-crawlers/)
    describes per-purpose controls whose defaults, for new domains under its
    ad-supported preset, allow Search and block Agent on pages carrying ads;
    a crawler that declares no separate purposes cannot be told apart. A
    robots.txt group naming a purpose's own token binds that purpose; a
    purpose with no group of its own falls back to a group naming plain
    ``Antiek``, then to ``*`` (acquisition.urls.robots.robots_allows)."""

    SEARCH = "search"                    # discovery: finding and citing pages, not answering a user
    AGENT = "agent-retrieval"            # user-initiated: fetched because a person's research asked for it
    INGEST = "ingest-no-training"        # corpus acquisition for reading/retrieval; never used to train a model


_USER_AGENTS: Mapping[FetchPurpose, str] = {
    FetchPurpose.SEARCH: f"Antiek-Search/0.1 (+{ANTIEK_CONTACT_URL}; purpose=search)",
    FetchPurpose.AGENT: f"Antiek-Agent/0.1 (+{ANTIEK_CONTACT_URL}; purpose=agent-retrieval; user-initiated)",
    FetchPurpose.INGEST: f"Antiek-Ingest/0.1 (+{ANTIEK_CONTACT_URL}; purpose=ingest; no-ai-training)",
}


def user_agent_for(purpose: FetchPurpose) -> str:
    """The User-Agent string sent for ``purpose``."""
    return _USER_AGENTS[purpose]


DEFAULT_PURPOSE = FetchPurpose.AGENT
# Kept for importers (acquisition/urls/paulgraham.py): the agent a plain fetch() sends.
DEFAULT_USER_AGENT = user_agent_for(DEFAULT_PURPOSE)


REFUSAL_STATUSES: frozenset[int] = frozenset({401, 402, 403})
_refusals: Counter[tuple[str, int]] = Counter()
_refusals_lock = threading.Lock()


def _record_refusal(host: str, status: int, purpose: FetchPurpose) -> None:
    with _refusals_lock:
        _refusals[(host, status)] += 1
        total = sum(n for (h, _s), n in _refusals.items() if h == host)
    logger.warning(
        "%s refused %s with HTTP %d (%d refusal(s) from this host in this process); "
        "coverage from this host is being lost, not failing loudly",
        host, user_agent_for(purpose), status, total,
    )


def refusal_counts() -> dict[str, dict[int, int]]:
    """Per-host 401/402/403 refusal counts seen by fetch() in this process, as
    ``{host: {status: n}}``. In-process only: nothing is written to DuckDB, so
    the single-writer invariant is untouched. A host that starts refusing is
    coverage silently lost.

    DIAGNOSTIC ONLY, not a metric. No production code reads this: the tests
    do, and an operator can from a shell in the serving process. The signal
    an operator actually sees is the WARNING line fetch() logs for each
    refusal, carrying the running per-host total. Exporting it needs a
    metrics sink the tree does not have (runtime/monitoring/README.md lists
    Prometheus dashboards as planned), and /health is public, so per-host
    crawl targets do not belong there. It resets when the process
    restarts."""
    with _refusals_lock:
        out: dict[str, dict[int, int]] = {}
        for (host, status), n in _refusals.items():
            out.setdefault(host, {})[status] = n
        return out


def clear_refusal_counts() -> None:
    """Reset the refusal counts (tests; or an operator starting a fresh window)."""
    with _refusals_lock:
        _refusals.clear()


@dataclass(frozen=True)
class FetchedHtml:
    """Result of one URL fetch. ``final_url`` is what the server
    landed on after redirects (used as the stable doc id seed).
    ``charset`` is taken from the Content-Type header; falls back to
    ``utf-8`` when absent — the extractor will re-detect from
    ``<meta charset>`` if needed. ``rights_terms`` is the publisher's RSL
    terms read off robots.txt (``NO_TERMS`` when none declared);
    ``robots_fail_open_reason`` says why robots enforcement was OFF for this
    origin (``None`` when a robots.txt was applied)."""

    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    charset: str
    body: bytes
    rights_terms: RightsTerms = NO_TERMS
    robots_fail_open_reason: str | None = None


def _detect_charset(content_type: str) -> str:
    """Pull the charset out of ``Content-Type: text/html; charset=...``.
    Defaults to ``utf-8`` when missing or unrecognized."""
    if not content_type:
        return "utf-8"
    parts = [p.strip() for p in content_type.split(";")]
    for p in parts[1:]:
        if p.lower().startswith("charset="):
            return p.split("=", 1)[1].strip().strip('"\'') or "utf-8"
    return "utf-8"


def _is_robots_txt(url: str) -> bool:
    """The robots.txt file itself is never governed by its own rules (RFC 9309)."""
    return urlsplit(url).path == "/robots.txt"


def fetch(
    url: str,
    *,
    client: httpx.Client | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    follow_redirects: bool = True,
    purpose: FetchPurpose = DEFAULT_PURPOSE,
) -> FetchedHtml:
    """GET ``url``. Raises ``httpx.HTTPStatusError`` on 4xx/5xx.

    ``purpose`` selects the User-Agent; a 401/402/403 response is counted per
    host (``refusal_counts()``) and logged at WARNING before ``raise_for_status``
    raises; the count is in-process only and opens no database connection.

    Per-host robots.txt is consulted for the purpose's User-Agent before the
    page is requested and again for every redirect hop's URL before that hop
    is requested; an explicit disallow raises ``RobotsDisallowed``. A missing,
    unreachable, or unparseable robots.txt fails OPEN with a WARNING and never
    blocks ingest. The policy is cached in-process once per origin. The RSL
    licence robots.txt declares for the purpose's agent is narrowed to the
    ``<content>`` scope covering the URL the fetch ended on (after
    redirects) and surfaces on ``rights_terms``; a licence with no scope
    covering that URL surfaces as ``source="rsl_out_of_scope"``.

    HOST-GLOBAL arXiv GOVERNANCE (SPR-09 root fix): ``url`` is an ARBITRARY
    caller-supplied URL (any web/news/blog source), so it could resolve to an
    arXiv host (e.g. an ``arxiv.org/abs/<id>`` landing page passed as a generic
    URL). The send is routed through ``govern_if_arxiv``: an arXiv host is held
    under the host-global flock + >=3s spacing on the shared throttle state; any
    other host is fetched directly (unchanged). Host-based, not
    module-location-based.

    REDIRECT-SAFE (SPR-09 round-5): an arbitrary URL may 302-REDIRECT to an arXiv
    host (a non-arXiv shortener / DOI resolver → ``arxiv.org/abs/<id>``). The
    initial-host ``govern_if_arxiv`` check would miss that arXiv redirect hop, so
    the client carries the per-hop arXiv request/response hooks: EVERY hop whose
    host is arXiv — including a redirect target — is governed by construction."""
    from acquisition.arxiv.rate_governor import (
        arxiv_governed_client,
        canonical_arxiv_throttle,
        govern_if_arxiv,
        install_arxiv_request_hook,
    )

    user_agent = user_agent_for(purpose)
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
    }

    def _run(c: httpx.Client) -> FetchedHtml:
        def _get(target: str, *, follow: bool) -> httpx.Response:
            def _send() -> httpx.Response:
                return c.get(
                    target, headers=headers, timeout=timeout_s,
                    follow_redirects=follow,
                )

            return govern_if_arxiv(target, _send, throttle=canonical_arxiv_throttle())

        def _send_hop(request: httpx.Request) -> httpx.Response:
            def _send() -> httpx.Response:
                return c.send(request, follow_redirects=False)

            return govern_if_arxiv(str(request.url), _send, throttle=canonical_arxiv_throttle())

        def _fetch_text(target: str, follow: bool) -> tuple[int, str, str]:
            # robots.py asks with follow=False and walks each hop itself; for
            # a redirect it needs where the Location points (FetchText).
            resp = _get(target, follow=follow)
            if not follow and resp.next_request is not None:
                return resp.status_code, "", str(resp.next_request.url)
            return resp.status_code, resp.text, str(resp.url)

        policy = None if _is_robots_txt(url) else robots_policy_for(url, fetch_text=_fetch_text, user_agent=user_agent)
        if policy is not None and not policy.allows(user_agent, url):
            raise RobotsDisallowed(url, user_agent=user_agent, robots_url=policy.robots_url)

        r = _get(url, follow=False)
        hops = 0
        while follow_redirects and r.next_request is not None:
            if hops >= c.max_redirects:
                raise httpx.TooManyRedirects("Exceeded maximum allowed redirects.", request=r.request)
            nxt = r.next_request
            hop_url = str(nxt.url)
            policy = None if _is_robots_txt(hop_url) else robots_policy_for(
                hop_url, fetch_text=_fetch_text, user_agent=user_agent,
            )
            if policy is not None and not policy.allows(user_agent, hop_url):
                raise RobotsDisallowed(hop_url, user_agent=user_agent, robots_url=policy.robots_url)
            r = _send_hop(nxt)
            hops += 1
        if r.status_code in REFUSAL_STATUSES:
            _record_refusal((r.url.host or urlsplit(url).hostname or "").lower(), r.status_code, purpose)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "") or ""
        return FetchedHtml(
            requested_url=url,
            final_url=str(r.url),
            status_code=r.status_code,
            content_type=content_type,
            charset=_detect_charset(content_type),
            body=r.content,
            rights_terms=(
                policy.terms_for(user_agent, str(r.url), fetch_text=_fetch_text)
                if policy is not None
                else NO_TERMS
            ),
            robots_fail_open_reason=policy.fail_open_reason if policy is not None else None,
        )

    if client is not None:
        install_arxiv_request_hook(client, throttle=canonical_arxiv_throttle())
        return _run(client)
    with arxiv_governed_client(
        throttle=canonical_arxiv_throttle(), follow_redirects=follow_redirects
    ) as c:
        return _run(c)
