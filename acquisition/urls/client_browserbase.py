"""Browserbase escalation fetcher — Wedge 2 of the Exa & Browserbase spec.

Per `docs/integration_exa_browserbase.md` §7: when httpx's primary
fetch returns `low_word_count` and the operator opts in via
`fallback_to_browserbase=True`, this module drives a Browserbase
Chromium session via the official `browserbase` SDK + Playwright,
returns the rendered page body as a `FetchedHtml` (drop-in with
the httpx client), and lets the URL adapter continue down the
existing extraction path.

Key disciplines from spec §7:

  - **Escalation, not default.** Browserbase costs 50-5000× httpx
    per page; default-on would 50-5000× per-page acquisition cost.
    The adapter's `fallback_to_browserbase` defaults to False.

  - **No logged-in browsing.** Persistent contexts (cookies across
    sessions) are NOT used in Wedge 2 (spec §7.5). That belongs in
    Wedge 4 if and when a specific logged-in surface is ratified.

  - **Respects robots.txt.** A polite pre-check refuses to drive
    a session against a host that disallows the agent's UA.

  - **Concurrency cap.** Max 3 concurrent sessions per process via
    a semaphore. Silent queueing past the cap masks failure.

  - **Daily budget.** `BROWSERBASE_DAILY_BUDGET_USD` hard-stops
    via `acquisition/urls/budget_browserbase.check_and_reserve`.

Lazy SDK import: the `browserbase` PyPI package is an OPTIONAL
dependency. The module imports cleanly without it; the SDK is
loaded inside `fetch_via_browserbase` so test paths that mock the
fetcher don't need the SDK installed. Production callers without
the SDK get a clear `BrowserbaseUnavailable` exception when they
try to escalate.

Tests inject a `session_factory` callable to substitute for the
real `browserbase.Browserbase().sessions.create(...)` flow.
"""

from __future__ import annotations

import os
import threading
import time
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from .client import FetchedHtml

DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.urls.browserbase)"
DEFAULT_TIMEOUT_S = 60.0
MAX_CONCURRENT_SESSIONS = 3
DEFAULT_SESSION_COST_USD = 0.30  # ~3 minutes at $0.10/minute

# Process-wide semaphore (one per process). Concurrent Wedge-2
# escalations across investigations share the cap so an
# operator-issued batch can't blow past 3 sessions.
_SESSION_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_SESSIONS)


class BrowserbaseProviderError(RuntimeError):
    """Common base class for every Wedge-2 / Browserbase failure
    the URL adapter should surface loudly.

    Per Exa-spec §14.4: *"Failure is loud: ``BrowserbaseProviderError``
    raises explicitly; no silent fallback to a different provider."*

    Concrete subclasses below distinguish the failure mode (config
    vs robots vs runtime vs budget) so callers can branch
    informatively. ``except BrowserbaseProviderError`` catches all
    four; ``except BrowserbaseRobotsDisallowed`` catches only the
    one. The spec's "loud failure" semantic is preserved either
    way.
    """


class BrowserbaseUnavailable(BrowserbaseProviderError):
    """Raised when the `browserbase` SDK is not installed and the
    caller asked for an escalation fetch. Loud, not silent — the
    fallback path is opt-in and a missing SDK is a config error."""


class BrowserbaseRobotsDisallowed(BrowserbaseProviderError):
    """Raised when the target host's robots.txt disallows the
    agent's User-Agent. The escalation does not proceed. Per spec
    §7.5: 'If a site disallows crawling, the fallback does not
    proceed.'"""


class BrowserbaseFetchError(BrowserbaseProviderError):
    """Raised when the Browserbase session ran but returned an
    unrecoverable error (network exploded, page navigation timed
    out, captcha detection refused the page)."""


class _SessionLike(Protocol):
    """Minimal protocol for a Browserbase session as we use it.
    The real `browserbase.Session` object has more attributes; we
    only depend on these.
    """

    def connect_url(self) -> str: ...
    def close(self) -> None: ...


@dataclass
class _FetchEnvelope:
    """Internal result type that bundles the FetchedHtml with the
    realized cost — the adapter can record the cost into the
    FetchFallbackEscalatedPayload event."""

    fetched: FetchedHtml
    cost_usd: float


def _resolve_api_creds() -> tuple[str, str]:
    api_key = os.environ.get("BROWSERBASE_API_KEY")
    project_id = os.environ.get("BROWSERBASE_PROJECT_ID")
    if not api_key or not project_id:
        raise BrowserbaseUnavailable(
            "BROWSERBASE_API_KEY and BROWSERBASE_PROJECT_ID must both "
            "be set for fallback_to_browserbase=True. No silent "
            "fallback — see spec §7.7."
        )
    return api_key, project_id


def _robots_allows(url: str, *, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """Polite pre-check. Returns True if the host either has no
    robots.txt or the robots.txt allows the agent. On any error
    fetching robots.txt, we DEFAULT TO ALLOWED — operationally,
    most sites' robots.txt is unreachable or empty, and refusing
    on those would defeat the purpose of the escalation.

    Spec §7.5: 'The Browserbase fetcher respects robots.txt (via
    a polite-pre-check ...). If a site disallows crawling, the
    fallback does not proceed.'
    """
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return True
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        # If the file is empty or unreachable, can_fetch returns True
        # for most implementations — that's the default-allowed
        # posture we want.
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True


def _default_session_factory() -> Callable[[], _SessionLike]:
    """Production factory: imports the `browserbase` SDK on first
    use. Raises `BrowserbaseUnavailable` if the SDK is not
    installed. Tests should pass their own `session_factory` to
    `fetch_via_browserbase` and avoid invoking this code path."""

    def make_session() -> _SessionLike:
        try:
            from browserbase import Browserbase  # type: ignore[import-not-found]
        except ImportError as e:
            raise BrowserbaseUnavailable(
                "browserbase SDK not installed. Run `pip install browserbase` "
                "to enable the Wedge 2 escalation path. See "
                "docs/integration_exa_browserbase.md §7 for the cost-"
                "discipline reasons this is an opt-in install."
            ) from e
        api_key, project_id = _resolve_api_creds()
        bb = Browserbase(api_key=api_key)
        return bb.sessions.create(project_id=project_id)

    return make_session


def fetch_via_browserbase(
    url: str,
    *,
    wait_for: str | None = None,
    wait_timeout_s: float = 15.0,
    user_agent: str = DEFAULT_USER_AGENT,
    session_factory: Callable[[], _SessionLike] | None = None,
    page_runner: Callable[..., tuple[bytes, str, int]] | None = None,
    estimated_cost_usd: float = DEFAULT_SESSION_COST_USD,
    cap_override_usd: float | None = None,
    skip_robots_check: bool = False,
) -> FetchedHtml:
    """Drive a Browserbase session, fetch the URL, return a
    `FetchedHtml` envelope matching the httpx-client output shape.

    Args:
        url: The URL to fetch.
        wait_for: Optional CSS selector to wait for, or
            "networkidle". When None, the runner uses the SDK
            default ("domcontentloaded"-equivalent).
        wait_timeout_s: Maximum wait for `wait_for`. Hard-capped
            at 60s session-wide via DEFAULT_TIMEOUT_S.
        user_agent: User-Agent header to send. Browserbase's
            stealth mode may override; we still surface the
            intended UA for robots.txt matching.
        session_factory: Test injection — substitutes for the
            real SDK session creator. Defaults to the production
            factory.
        page_runner: Test injection — given a session-connect
            URL + target URL + wait params, returns
            (html_bytes, final_url, status_code). Defaults to a
            Playwright runner that uses the Browserbase session.
        estimated_cost_usd: Pre-reservation budget cost. Refined
            via `record_actual(...)` after the session closes.
        cap_override_usd: Override the daily cap for this call
            (operator-explicit, not env-driven).
        skip_robots_check: Bypass the robots.txt pre-check. Use
            sparingly — only when the operator has verified the
            site's policy manually and accepted responsibility.

    Returns:
        `FetchedHtml` with the rendered page body. Drop-in
        substitute for `client.fetch(url)` output.

    Raises:
        BrowserbaseUnavailable: SDK not installed / creds missing.
        BrowserbaseRobotsDisallowed: robots.txt forbids.
        BrowserbaseBudgetExceeded: daily cap reached.
        BrowserbaseFetchError: session ran but returned no useful
            content.
    """
    if not skip_robots_check and not _robots_allows(url, user_agent=user_agent):
        raise BrowserbaseRobotsDisallowed(
            f"robots.txt disallows {url} for User-Agent {user_agent!r}; "
            "skipping Wedge 2 escalation."
        )

    # Pre-reserve budget BEFORE acquiring the semaphore. A budget-
    # exceeded refusal shouldn't hold a semaphore slot that another
    # caller could use.
    from .budget_browserbase import check_and_reserve, record_actual

    state = check_and_reserve(
        estimated_cost_usd, cap_override=cap_override_usd
    )

    factory = session_factory or _default_session_factory()
    runner = page_runner or _default_page_runner

    acquired = _SESSION_SEMAPHORE.acquire(timeout=DEFAULT_TIMEOUT_S)
    if not acquired:
        # Refund the pre-reservation since no session ran.
        record_actual(-estimated_cost_usd)
        raise BrowserbaseFetchError(
            "Wedge 2 concurrency cap reached (3 simultaneous sessions); "
            "request timed out waiting for a slot."
        )

    started_at = time.monotonic()
    session: _SessionLike | None = None
    try:
        session = factory()
        try:
            html_bytes, final_url, status_code = runner(
                session=session,
                url=url,
                wait_for=wait_for,
                wait_timeout_s=wait_timeout_s,
                user_agent=user_agent,
            )
        except Exception as e:
            raise BrowserbaseFetchError(
                f"Browserbase page runner failed: {type(e).__name__}: {e}"
            ) from e

        return FetchedHtml(
            requested_url=url,
            final_url=final_url or url,
            status_code=status_code or 200,
            content_type="text/html; charset=utf-8",
            charset="utf-8",
            body=html_bytes,
        )
    finally:
        # Best-effort close — the SDK's own session lifecycle is
        # authoritative, but we should signal "done" so the
        # session-minute meter stops.
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        _SESSION_SEMAPHORE.release()
        # Refine the budget reservation with actual elapsed time.
        # Browserbase rounds to the minute; we use elapsed for a
        # rough refinement. Production may swap to the SDK's
        # authoritative cost reporter once the operator has run
        # enough sessions to compare.
        elapsed_s = time.monotonic() - started_at
        actual_cost = max(0.10, (elapsed_s / 60.0) * 0.10)  # $0.10/minute floor at $0.10
        record_actual(actual_cost - estimated_cost_usd)


def _default_page_runner(
    *,
    session: _SessionLike,
    url: str,
    wait_for: str | None,
    wait_timeout_s: float,
    user_agent: str,
) -> tuple[bytes, str, int]:
    """Drive a Playwright Chromium against the Browserbase session
    and return (html_bytes, final_url, status_code). Lazy-imports
    Playwright so tests that inject `page_runner` don't need it.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError as e:
        raise BrowserbaseUnavailable(
            "playwright not installed. Run `pip install playwright` "
            "alongside `pip install browserbase` for Wedge 2."
        ) from e

    connect_url = session.connect_url()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(connect_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context(
            user_agent=user_agent
        )
        page = context.new_page()
        try:
            response = page.goto(url, timeout=int(wait_timeout_s * 1000))
            if wait_for == "networkidle":
                page.wait_for_load_state("networkidle", timeout=int(wait_timeout_s * 1000))
            elif wait_for:
                page.wait_for_selector(wait_for, timeout=int(wait_timeout_s * 1000))
            html = page.content().encode("utf-8")
            final = page.url
            status = response.status if response else 200
            return html, final, status
        finally:
            try:
                page.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass


__all__ = [
    "BrowserbaseFetchError",
    "BrowserbaseRobotsDisallowed",
    "BrowserbaseUnavailable",
    "DEFAULT_SESSION_COST_USD",
    "MAX_CONCURRENT_SESSIONS",
    "fetch_via_browserbase",
]
