"""Resilience tests for the unified corpus-ingest orchestrator (SPR-08).

Branch fix/corpus-connector-resilience. These cover the property the SPR-08
maintenance window exposed: a transient failure in ONE source's discovery must
NOT abort the whole multi-source run. Discovery runs PD -> arXiv -> OA in one
pass, so an uncaught error in an earlier source silently blocks the later ones.

NO live HTTP and NO real state files: the arXiv throttle is redirected to a
tmp path via ANTIEK_ARXIV_THROTTLE_PATH so a test can never write a real ban
sentinel to ~/.antiek/arxiv_throttle.json (which would throttle the operator's
own ingest). Each test asserts BEHAVIOR (returns [] / a fresh throttle now
refuses), not a private JSON schema.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools import run_corpus_ingest as rci  # noqa: E402

# Pre-import the per-source CLIs at COLLECTION time (before any test patches a
# module attribute) so their module-top `from acquisition... import <name>`
# bindings freeze to the ORIGINAL functions. Otherwise a test that patches e.g.
# acquisition.books.public_domain.gutenberg_candidates while one of these CLIs
# is imported for the FIRST time (lazily, via _public_domain_candidates ->
# `from tools.ingest_public_domain import CURATED_GUTENBERG_IDS`) would
# permanently capture the patched function in the CLI's namespace and leak it
# into later tests. monkeypatch only reverts the attribute it set, not a
# downstream snapshot.
from tools import ingest_arxiv  # noqa: E402,F401
from tools import ingest_public_domain  # noqa: E402,F401


# ---------------------------------------------------------------------------
# BLOCKER 1 — public-domain / gutendex discovery isolation + body cache
# ---------------------------------------------------------------------------


def test_pd_discovery_source_error_is_isolated(monkeypatch):
    """A transient gutendex 503/timeout (SourceError) during PD discovery
    self-skips PD (returns []) instead of propagating up to main's blanket
    handler and aborting the whole run (which would also block OA)."""
    from acquisition.books import public_domain as pd

    def _boom(*_a, **_k):
        raise pd.SourceError("simulated transient gutendex 503")

    monkeypatch.setattr(pd, "gutenberg_candidates", _boom)

    out = rci._public_domain_candidates(
        subject=None, search_term=None, ids=[1], curated=False,
        limit=1, investigation_id="inv-test", min_interval_s=0.0,
    )
    assert out == []


def test_body_caching_client_dedups_get_bytes():
    """The PD body cache (Edit 2) collapses the gate-assessment fetch and the
    ingest fetch of the SAME url into a single underlying get_bytes — halving
    gutendex load in the maintenance window. get_json is never cached."""
    from tools.run_corpus_ingest import _BodyCachingClient

    class _Counting:
        def __init__(self) -> None:
            self.byte_calls: list[str] = []

        def get_bytes(self, url: str) -> bytes:
            self.byte_calls.append(url)
            return b"%PDF-" + url.encode()

        def get_json(self, url: str, *, params=None) -> dict:
            return {"u": url}

    inner = _Counting()
    client = _BodyCachingClient(inner)

    first = client.get_bytes("https://g/1.txt")
    again = client.get_bytes("https://g/1.txt")   # served from cache
    other = client.get_bytes("https://g/2.txt")

    assert first == again
    assert other != first
    # 1.txt fetched ONCE despite two logical reads; 2.txt once.
    assert inner.byte_calls == ["https://g/1.txt", "https://g/2.txt"]
    # get_json is delegated live, never cached.
    assert client.get_json("https://g/api") == {"u": "https://g/api"}


# ---------------------------------------------------------------------------
# BLOCKER 2 — arXiv discovery isolation (export.arxiv.org 429 / IP-ban)
# ---------------------------------------------------------------------------


def test_arxiv_discovery_http_429_isolated_and_persists_sentinel(monkeypatch, tmp_path):
    """A live 429 during arXiv discovery is recorded to the throttle's ban
    sentinel (so the NEXT run honors the ban instead of re-hitting and
    EXTENDING it) and degrades to zero arXiv candidates — it does not abort
    the whole multi-source run."""
    monkeypatch.setenv("ANTIEK_ARXIV_THROTTLE_PATH", str(tmp_path / "throttle.json"))

    def _raise_429(**_kwargs):
        req = httpx.Request("GET", "https://export.arxiv.org/api/query")
        resp = httpx.Response(429, request=req)
        raise httpx.HTTPStatusError("429 Too Many Requests", request=req, response=resp)

    monkeypatch.setattr("acquisition.arxiv.search", _raise_429)

    out = rci._arxiv_candidates(
        query="quantum", category=None, ids=None, limit=3,
        investigation_id="inv-test",
    )
    assert out == []

    # The sentinel was persisted: a fresh throttle (same redirected path) now
    # refuses before issuing any request.
    from acquisition.arxiv import ArxivBanned, ArxivThrottle

    with pytest.raises(ArxivBanned):
        ArxivThrottle().wait_if_needed()


def test_arxiv_discovery_active_ban_isolated(monkeypatch, tmp_path):
    """When a ban sentinel is already active, arXiv discovery degrades to []
    WITHOUT hitting the banned endpoint at all (search must never be called)."""
    monkeypatch.setenv("ANTIEK_ARXIV_THROTTLE_PATH", str(tmp_path / "throttle.json"))

    from acquisition.arxiv import ArxivThrottle

    ArxivThrottle().note_response(429)  # write a ban sentinel up front

    called = {"search": False}

    def _should_not_run(**_kwargs):
        called["search"] = True
        raise AssertionError("search must not be called while banned")

    monkeypatch.setattr("acquisition.arxiv.search", _should_not_run)

    out = rci._arxiv_candidates(
        query="quantum", category=None, ids=None, limit=3,
        investigation_id="inv-test",
    )
    assert out == []
    assert called["search"] is False
