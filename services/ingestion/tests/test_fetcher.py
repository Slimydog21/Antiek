"""Tests for the hardened fetcher (M3) + throttle.

Coverage:

- Redis-backed throttle uses sliding window per host.
- 429 → banned_until written → subsequent fetch raises DomainBanned.
- Banned_until SURVIVES PROCESS RESTART (rigor #3): test simulates a
  fresh process by clearing the module-level Redis client + cache and
  re-checking the DuckDB ban row.
- SSL env vars are set at import.
- Metadata cache (LRU) hit returns cached body without HTTP.
- robots.txt disallow blocks fetch.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


# ---------------------------------------------------------------------------
# Fixtures — tmp DB + tmp cache + fakeredis throttle backend
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_ingest_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-spr03-fetcher-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    cache_dir = os.path.join(tmpdir, "ingest_cache")
    os.makedirs(events_dir, exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)

    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    monkeypatch.setenv("ANTIEK_INGEST_CACHE_DIR", cache_dir)

    # fakeredis for the throttle.
    import fakeredis
    fr = fakeredis.FakeRedis(decode_responses=True)
    from services.ingestion import throttle as throttle_mod
    throttle_mod.set_client_for_tests(fr)

    # Wipe any leftover cache entries.
    from services.ingestion import fetcher as fetcher_mod
    fetcher_mod.cache_clear_for_tests()
    fetcher_mod.robots_cache_clear_for_tests()

    yield {
        "db_path": db_path,
        "events_dir": events_dir,
        "cache_dir": cache_dir,
        "tmpdir": tmpdir,
        "fakeredis": fr,
    }

    throttle_mod.reset_for_tests()
    fetcher_mod.cache_clear_for_tests()
    fetcher_mod.robots_cache_clear_for_tests()


# ---------------------------------------------------------------------------
# SSL env exports
# ---------------------------------------------------------------------------


def test_ssl_env_set_at_startup():
    """The verification gate: SSL_CERT_FILE + REQUESTS_CA_BUNDLE
    explicitly resolved at module import."""
    from services.ingestion import fetcher
    env = fetcher.ssl_env_at_startup()
    # Either we set them (because they weren't set) or the operator
    # had them set already; either way they exist in os.environ now.
    assert "SSL_CERT_FILE" in os.environ
    assert "REQUESTS_CA_BUNDLE" in os.environ
    # And the certifi bundle path is non-empty.
    assert os.environ["SSL_CERT_FILE"]
    assert os.environ["REQUESTS_CA_BUNDLE"]


# ---------------------------------------------------------------------------
# Throttle — Redis sliding window
# ---------------------------------------------------------------------------


def test_throttle_first_call_no_wait(temp_ingest_env):
    """First call against a host shouldn't sleep."""
    from services.ingestion import throttle
    sleeps: list[float] = []
    res = throttle.acquire(
        "https://example.com/a", sleeper=sleeps.append, clock=lambda: 0.0,
    )
    assert res.backend == "redis"
    assert res.waited_s == 0.0
    assert sleeps == []


def test_throttle_second_call_waits(temp_ingest_env):
    """Second call within the window sleeps for the remaining time."""
    from services.ingestion import throttle

    # Simulate a clock that advances 0.5s between calls.
    t = [0.0]

    def clock():
        return t[0]

    sleeps: list[float] = []
    throttle.acquire("https://example.com/a", sleeper=sleeps.append, clock=clock)
    t[0] += 0.5  # 0.5s later
    res = throttle.acquire(
        "https://example.com/a", sleeper=sleeps.append, clock=clock,
    )
    # Default window is 1.0s; we advanced 0.5s; expected wait ~0.5s.
    assert sleeps, "second call should have slept"
    assert res.waited_s > 0
    assert 0.3 < res.waited_s < 0.7


def test_throttle_different_hosts_independent(temp_ingest_env):
    """Hosts have independent windows — no cross-domain throttle."""
    from services.ingestion import throttle
    sleeps: list[float] = []
    throttle.acquire("https://a.com/x", sleeper=sleeps.append, clock=lambda: 0.0)
    res = throttle.acquire(
        "https://b.com/x", sleeper=sleeps.append, clock=lambda: 0.0,
    )
    assert res.waited_s == 0.0


def test_throttle_arxiv_uses_3s_window(temp_ingest_env):
    """arxiv.org has a tighter 3s window per ToS."""
    from services.ingestion import throttle
    t = [0.0]

    def clock():
        return t[0]

    sleeps: list[float] = []
    throttle.acquire("https://arxiv.org/abs/x", sleeper=sleeps.append, clock=clock)
    t[0] += 1.0
    res = throttle.acquire(
        "https://arxiv.org/abs/y", sleeper=sleeps.append, clock=clock,
    )
    # We advanced 1s in a 3s window → ~2s remaining.
    assert 1.5 < res.waited_s < 2.5


# ---------------------------------------------------------------------------
# 429 → banned_until → subsequent fetch raises DomainBanned
# ---------------------------------------------------------------------------


def test_429_writes_ban_and_subsequent_fetch_raises(temp_ingest_env):
    """The core failure-mode-fix test: 429 → ban row → next call
    short-circuits without HTTP."""
    from services.ingestion import fetcher

    call_count = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        # robots.txt always 404 = allow-all.
        if "robots.txt" in str(req.url):
            return httpx.Response(404)
        return httpx.Response(
            429, headers={"retry-after": "60"}, content=b"slow down",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)

    # First call: triggers 429 → writes ban → raises.
    with pytest.raises(httpx.HTTPStatusError):
        fetcher.fetch(
            "https://test429.example.com/page",
            client=client,
            db_path=temp_ingest_env["db_path"],
        )

    first_call_count = call_count[0]
    assert first_call_count >= 1

    # Second call: banned_until honored → DomainBanned WITHOUT HTTP.
    with pytest.raises(fetcher.DomainBanned) as exc:
        fetcher.fetch(
            "https://test429.example.com/other",
            client=client,
            db_path=temp_ingest_env["db_path"],
        )
    assert exc.value.domain == "test429.example.com"
    # Call count must NOT have increased — short-circuited before HTTP.
    assert call_count[0] == first_call_count, (
        "fetcher made an HTTP call against a banned domain"
    )


# ---------------------------------------------------------------------------
# Rigor #3 — ban survives process restart (cross-process semantics)
# ---------------------------------------------------------------------------


def test_ban_survives_simulated_process_restart(temp_ingest_env):
    """Rigor #3: the 429 → banned_until test must survive a process
    boundary. Here we simulate the restart by REIMPORTING the
    fetcher + throttle modules (clearing every module-level cache:
    Redis client, robots cache, metadata cache). The DuckDB ban row
    is what should be the only state that persists. After the
    'restart' the fetcher must still honor the ban."""
    from services.ingestion import fetcher as fetcher_v1

    call_count = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        if "robots.txt" in str(req.url):
            return httpx.Response(404)
        return httpx.Response(429, headers={"retry-after": "60"})

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)
    with pytest.raises(httpx.HTTPStatusError):
        fetcher_v1.fetch(
            "https://restart-test.example.com/x",
            client=client,
            db_path=temp_ingest_env["db_path"],
        )
    initial_calls = call_count[0]
    assert initial_calls >= 1

    # --- SIMULATED RESTART -------------------------------------------------
    # Drop every module-level cache in the throttle + fetcher modules,
    # reload them so module-level state (the resolved SSL env, the
    # Redis client, the metadata cache reference) is rebuilt from
    # scratch. The DuckDB ban table is the ONLY state that persists.
    from services.ingestion import throttle as throttle_v1
    throttle_v1.reset_for_tests()

    import services.ingestion.throttle
    import services.ingestion.fetcher
    importlib.reload(services.ingestion.throttle)
    importlib.reload(services.ingestion.fetcher)

    # Re-wire fakeredis on the freshly-reloaded throttle module.
    import fakeredis
    services.ingestion.throttle.set_client_for_tests(
        fakeredis.FakeRedis(decode_responses=True),
    )
    services.ingestion.fetcher.cache_clear_for_tests()
    services.ingestion.fetcher.robots_cache_clear_for_tests()
    # -----------------------------------------------------------------------

    # New module instance; ban must still be honored.
    from services.ingestion import fetcher as fetcher_v2

    with pytest.raises(fetcher_v2.DomainBanned):
        fetcher_v2.fetch(
            "https://restart-test.example.com/y",
            client=client,
            db_path=temp_ingest_env["db_path"],
        )
    assert call_count[0] == initial_calls, (
        "after simulated restart, fetcher made an HTTP call against "
        "a banned domain — the ban did NOT survive the process boundary"
    )


# ---------------------------------------------------------------------------
# Metadata cache
# ---------------------------------------------------------------------------


def test_cache_hit_returns_without_http(temp_ingest_env):
    """Second call to the same URL with the same Accept should not
    make an HTTP request."""
    from services.ingestion import fetcher

    call_count = [0]

    def handler(req: httpx.Request) -> httpx.Response:
        call_count[0] += 1
        if "robots.txt" in str(req.url):
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"hello world",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)

    r1 = fetcher.fetch(
        "https://cache-test.example.com/x",
        client=client,
        db_path=temp_ingest_env["db_path"],
    )
    assert r1.body == b"hello world"
    assert r1.via_cache is False

    # Second call: should be served from disk LRU.
    r2 = fetcher.fetch(
        "https://cache-test.example.com/x",
        client=client,
        db_path=temp_ingest_env["db_path"],
    )
    assert r2.via_cache is True
    assert r2.body == b"hello world"


def test_cache_size_constant_matches_notes():
    """Per INGESTION_NOTES.md the cache is 10,000 entries."""
    from services.ingestion import fetcher
    assert fetcher.METADATA_CACHE_MAX_ENTRIES == 10_000, (
        "INGESTION_NOTES.md commits the cache to 10,000 entries (10× "
        "the legacy 1,000). If this constant changes, update the notes "
        "with a new rationale."
    )


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------


def test_robots_disallow_blocks_fetch(temp_ingest_env):
    from services.ingestion import fetcher

    def handler(req: httpx.Request) -> httpx.Response:
        if "robots.txt" in str(req.url):
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                content=b"User-agent: *\nDisallow: /\n",
            )
        return httpx.Response(200, content=b"shouldn't happen")

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)

    with pytest.raises(fetcher.RobotsDisallowed):
        fetcher.fetch(
            "https://no-bots.example.com/page",
            client=client,
            db_path=temp_ingest_env["db_path"],
        )


def test_robots_allow_lets_fetch_through(temp_ingest_env):
    from services.ingestion import fetcher

    def handler(req: httpx.Request) -> httpx.Response:
        if "robots.txt" in str(req.url):
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                content=b"User-agent: *\nAllow: /\n",
            )
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, content=b"ok",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)
    res = fetcher.fetch(
        "https://yes-bots.example.com/page",
        client=client,
        db_path=temp_ingest_env["db_path"],
    )
    assert res.body == b"ok"
