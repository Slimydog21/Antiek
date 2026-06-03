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

import httpx

DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.urls)"
DEFAULT_TIMEOUT_S = 20.0


@dataclass(frozen=True)
class FetchedHtml:
    """Result of one URL fetch. ``final_url`` is what the server
    landed on after redirects (used as the stable doc id seed).
    ``charset`` is taken from the Content-Type header; falls back to
    ``utf-8`` when absent — the extractor will re-detect from
    ``<meta charset>`` if needed."""

    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    charset: str
    body: bytes


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


def fetch(
    url: str,
    *,
    client: httpx.Client | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    follow_redirects: bool = True,
) -> FetchedHtml:
    """GET ``url``. Raises ``httpx.HTTPStatusError`` on 4xx/5xx.

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
    if client is not None:
        install_arxiv_request_hook(client, throttle=canonical_arxiv_throttle())
        def _send() -> httpx.Response:
            return client.get(
                url, headers=headers, timeout=timeout_s,
                follow_redirects=follow_redirects,
            )

        r = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
    else:
        with arxiv_governed_client(
            throttle=canonical_arxiv_throttle(), follow_redirects=follow_redirects
        ) as c:
            def _send() -> httpx.Response:
                return c.get(url, headers=headers, timeout=timeout_s)

            r = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
    r.raise_for_status()
    content_type = r.headers.get("content-type", "") or ""
    return FetchedHtml(
        requested_url=url,
        final_url=str(r.url),
        status_code=r.status_code,
        content_type=content_type,
        charset=_detect_charset(content_type),
        body=r.content,
    )
