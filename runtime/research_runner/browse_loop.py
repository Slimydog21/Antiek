"""DRW — the real Exa→Browserbase browse loop (the actual research engine).

SPR-02 shipped the runner with ``make_demo_loop`` as a placeholder and an
*injected* ``BrowseLoop`` seam: "the real Exa→Browserbase loop drops into the
same seam." This is that loop. For one sub-question it:

  1. searches Exa (the discovery layer) for sources;
  2. fetches each top source's text, escalating to Browserbase when the plain
     HTTP fetch yields thin content (the spec's "Exa → Browserbase
     escalation");
  3. distils each source into insight + question ``StepEvent``s (per-step
     note-taking) which the SPR-06 promotion funnel turns into graph nodes.

**Single-writer-safe by construction:** the loop only *reads* (search + fetch
are read-only network calls) and *emits* note/question events — it NEVER opens
a graph write connection. Promotion is the funnel's job, serialized through
``db_lock``. Blocking network/dispatch calls run in ``asyncio.to_thread`` so a
slow fetch never blocks the event loop the other researches share.

Steerable + bounded: ``ctx.checkpoint()`` before the search and before each
source is the pause/stop/redirect point; search + fetch costs are reported on
the steps, so the runner's per-research + aggregate budget caps halt a runaway
research exactly as they do the demo loop.

The providers are injected (``SearchProvider`` / ``FetchProvider`` /
``Distiller``) so the loop's logic is tested against deterministic stubs
(``tests/test_browse_loop.py``). ``exa_search_provider`` /
``url_fetch_provider`` wire the real adapters; they are network-bound (live
Exa/Browserbase keys) and rely on those adapters' own tests, so they are
documented best-effort wrappers, not unit-tested here.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, List, Optional

try:
    from .host_local import LoopContext
    from .protocol import StepEvent
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.research_runner.host_local import LoopContext  # type: ignore[no-redef]
    from runtime.research_runner.protocol import StepEvent  # type: ignore[no-redef]


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str = ""
    snippet: str = ""
    cost_usd: float = 0.0


@dataclass(frozen=True)
class FetchedContent:
    text: str = ""
    cost_usd: float = 0.0
    escalated: bool = False
    ok: bool = True


# (query, limit) -> results;  (url) -> content. Sync (network-blocking); the
# loop runs them in a worker thread so they never block the shared event loop.
SearchProvider = Callable[[str, int], List[SearchResult]]
FetchProvider = Callable[[str], FetchedContent]

# Below this many characters of extracted text a source is "thin" — skip it
# (and, in the real fetch provider, the trigger to escalate to Browserbase).
DEFAULT_MIN_CHARS = 120
DEFAULT_TOP_K = 5


def make_browse_loop(
    *,
    search: SearchProvider,
    fetch: FetchProvider,
    distiller: Any,
    top_k: int = DEFAULT_TOP_K,
    min_chars: int = DEFAULT_MIN_CHARS,
):
    """Build a ``BrowseLoop`` (async generator) the HostLocalRunner drives.
    One search round over ``top_k`` sources; a ``redirect`` updates the
    sub-question for the loop's transparency, and a re-search is a ``deepen``
    follow-up (bounded — one search round can't run forever)."""

    async def _loop(ctx: LoopContext) -> AsyncIterator[StepEvent]:
        # Lazy import keeps runtime.research_runner free of a roles.note_taker
        # load-order dependency.
        from roles.note_taker.step_pass import RunNoteDeduper
        deduper = RunNoteDeduper()

        yield ctx.plan_event(f"research plan: {ctx.sub_question}")
        query = await ctx.checkpoint()  # pause/stop/redirect before spending

        results = await asyncio.to_thread(search, query, top_k)
        search_cost = sum(r.cost_usd for r in results)
        yield ctx.step(
            f"searched: {len(results)} sources for “{query}”",
            cost_usd=search_cost, kind_detail="exa_search",
        )

        for r in results:
            await ctx.checkpoint()  # steer point between sources
            try:
                fetched = await asyncio.to_thread(fetch, r.url)
            except Exception as exc:  # one bad source must not kill the research
                yield ctx.step(f"fetch failed: {r.title or r.url} ({type(exc).__name__})")
                continue
            if not fetched.ok or len(fetched.text.strip()) < min_chars:
                yield ctx.step(f"thin/empty, skipped: {r.title or r.url}", cost_usd=fetched.cost_usd)
                continue
            via = " via Browserbase" if fetched.escalated else ""
            yield ctx.step(f"read{via}: {r.title or r.url}", cost_usd=fetched.cost_usd)

            try:
                distillation = await asyncio.to_thread(distiller.distill, fetched.text)
            except Exception:  # distillation failure is non-fatal for the source
                continue
            for note in distillation.insights:
                if deduper.is_new(note.text):
                    yield ctx.note(note.text, confidence=note.confidence, source_url=r.url)
            for q in distillation.questions:
                if deduper.is_new(q.text):
                    yield ctx.question(q.text, source_url=r.url)

    return _loop


# ---------------------------------------------------------------------------
# Real-adapter providers (network-bound; documented best-effort wrappers)
# ---------------------------------------------------------------------------


def exa_search_provider(*, num_results_cap: int = 10) -> SearchProvider:
    """Wrap the Exa discovery client as a ``SearchProvider``. Needs the Exa
    API key in the environment (raises ``ExaClientError`` without one)."""
    def _search(query: str, limit: int) -> List[SearchResult]:
        from acquisition.search.exa import ExaClient
        resp = ExaClient().search(query=query, num_results=max(1, min(limit, num_results_cap)))
        return [
            SearchResult(url=r.url, title=r.title or "", snippet=r.text_snippet_preview or "",
                         cost_usd=float(r.cost_usd_estimate))
            for r in resp.results
        ]
    return _search


def url_fetch_provider(*, fallback_to_browserbase: bool = True, min_chars: int = 200) -> FetchProvider:
    """Wrap the URL fetch + Browserbase escalation as a ``FetchProvider``.
    Plain HTTP fetch → extract markdown; if thin and escalation is on, retry
    through Browserbase. Best-effort: any failure returns ``ok=False`` rather
    than raising, so one bad source never aborts the research."""
    def _fetch(url: str) -> FetchedContent:
        from acquisition.urls.client import fetch as http_fetch
        from acquisition.urls.extract import html_to_markdown
        try:
            fh = http_fetch(url)
            doc = html_to_markdown(fh.body, base_url=fh.final_url)
            text = doc.markdown
        except Exception:
            text = ""
        if (len(text.strip()) >= min_chars) or not fallback_to_browserbase:
            return FetchedContent(text=text, ok=bool(text.strip()))
        # Thin → escalate to a real browser session.
        try:
            from acquisition.urls.client_browserbase import (
                DEFAULT_SESSION_COST_USD, fetch_via_browserbase,
            )
            bh = fetch_via_browserbase(url)
            bdoc = html_to_markdown(bh.body, base_url=bh.final_url)
            return FetchedContent(text=bdoc.markdown, cost_usd=float(DEFAULT_SESSION_COST_USD),
                                  escalated=True, ok=bool(bdoc.markdown.strip()))
        except Exception:
            return FetchedContent(text=text, ok=bool(text.strip()))  # keep what we got
    return _fetch


def default_browse_loop(*, top_k: int = DEFAULT_TOP_K):
    """Wire the real Exa→Browserbase loop with the production distiller.
    Returns ``None`` when the dependencies/keys are unavailable so the caller
    (cascade_routes) can fall back to the demo loop without crashing."""
    try:
        from roles.note_taker.distill import DispatchDistiller
        return make_browse_loop(
            search=exa_search_provider(), fetch=url_fetch_provider(),
            distiller=DispatchDistiller(), top_k=top_k,
        )
    except Exception:  # pragma: no cover — missing deps/keys → caller falls back
        return None
