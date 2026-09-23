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

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from acquisition.urls.rights_terms import NO_TERMS, RightsTerms
from acquisition.urls.robots import RobotsDisallowed, robots_policy_for

DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.urls)"
DEFAULT_TIMEOUT_S = 20.0


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
) -> FetchedHtml:
    """GET ``url``. Raises ``httpx.HTTPStatusError`` on 4xx/5xx.

    Per-host robots.txt is consulted for DEFAULT_USER_AGENT before the page is
    requested; an explicit disallow raises ``RobotsDisallowed``. A missing,
    unreachable, or unparseable robots.txt fails OPEN with a WARNING and never
    blocks ingest. The policy is cached in-process once per origin, and any
    RSL licence declared by robots.txt surfaces on ``rights_terms``.

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

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
    }

    def _run(c: httpx.Client) -> FetchedHtml:
        def _get(target: str) -> httpx.Response:
            def _send() -> httpx.Response:
                return c.get(
                    target, headers=headers, timeout=timeout_s,
                    follow_redirects=follow_redirects,
                )

            return govern_if_arxiv(target, _send, throttle=canonical_arxiv_throttle())

        def _fetch_text(target: str) -> tuple[int, str]:
            resp = _get(target)
            return resp.status_code, resp.text

        policy = None if _is_robots_txt(url) else robots_policy_for(url, fetch_text=_fetch_text)
        if policy is not None and not policy.allows(DEFAULT_USER_AGENT, url):
            raise RobotsDisallowed(url, user_agent=DEFAULT_USER_AGENT, robots_url=policy.robots_url)

        r = _get(url)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "") or ""
        return FetchedHtml(
            requested_url=url,
            final_url=str(r.url),
            status_code=r.status_code,
            content_type=content_type,
            charset=_detect_charset(content_type),
            body=r.content,
            rights_terms=policy.rights_terms if policy is not None else NO_TERMS,
            robots_fail_open_reason=policy.fail_open_reason if policy is not None else None,
        )

    if client is not None:
        install_arxiv_request_hook(client, throttle=canonical_arxiv_throttle())
        return _run(client)
    with arxiv_governed_client(
        throttle=canonical_arxiv_throttle(), follow_redirects=follow_redirects
    ) as c:
        return _run(c)
