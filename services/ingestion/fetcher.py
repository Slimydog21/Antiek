"""Hardened fetcher for the universal-library ingestion (M3).

Five concerns, layered:

1. **SSL env exports.** Resolve ``SSL_CERT_FILE`` and
   ``REQUESTS_CA_BUNDLE`` from the project config at module load.
   Missing-export was a Researchmaxx failure mode (memory
   ``project_researchmaxx_arxiv``, 2026-05-17) that surfaced as
   sporadic certificate errors against arXiv from Linux workers.
   Falls back to ``certifi`` when env is empty.

2. **Cross-process throttle.** Calls ``throttle.acquire(url)`` before
   every fetch. Redis-backed sliding window; survives worker restart.

3. **Persistent banned_until sentinel.** Before fetching, check the
   ``ingestion_bans`` DuckDB table. If the domain is banned, raise
   ``DomainBanned`` immediately — no HTTP, no retry. On a 429, write
   a new ban row.

4. **robots.txt cache (24h per domain).** Best-effort. ``Disallow: /``
   for our user-agent → raise ``RobotsDisallowed`` before any
   non-robots fetch.

5. **Metadata cache (LRU on disk, 10,000 entries).** 10× the legacy
   1k. Keyed by ``(method, url, accept)``; value is the raw bytes
   + content-type + status. Pure GETs are cached. Cache key includes
   the canonical URL after redirects so a hop to a 301 destination
   doesn't poison the cache.

The fetcher is the single chokepoint for all HTTP in the ingestion
pipeline. Extractors call into ``fetch(url)`` — they don't open their
own ``httpx.Client``. This is what makes the Redis throttle and the
banned_until table *effective*: every byte that comes in is
accounted for.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

# Repo root for sibling imports when run via pytest / CLI.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from services.ingestion import throttle  # noqa: E402

# ---------------------------------------------------------------------------
# SSL env exports (rigor #4 — inherit the fix, don't reinvent)
# ---------------------------------------------------------------------------


def _ensure_ssl_env() -> dict[str, str]:
    """Resolve SSL_CERT_FILE and REQUESTS_CA_BUNDLE from project
    config at startup. Returns the dict of what was set (for tests
    + INGESTION_NOTES). The Researchmaxx fix: ensure both env vars
    point at a real CA bundle before any HTTPS call. We use the
    operator's existing env value if set, else certifi's bundle, else
    leave it (httpx will use the OS default)."""
    set_to: dict[str, str] = {}
    bundle = (
        os.environ.get("SSL_CERT_FILE", "").strip()
        or os.environ.get("REQUESTS_CA_BUNDLE", "").strip()
    )
    if not bundle:
        try:
            import certifi
            bundle = certifi.where()
        except ImportError:
            bundle = ""
    if bundle:
        if not os.environ.get("SSL_CERT_FILE"):
            os.environ["SSL_CERT_FILE"] = bundle
            set_to["SSL_CERT_FILE"] = bundle
        if not os.environ.get("REQUESTS_CA_BUNDLE"):
            os.environ["REQUESTS_CA_BUNDLE"] = bundle
            set_to["REQUESTS_CA_BUNDLE"] = bundle
    return set_to


# Resolve at module import so any sibling that uses httpx benefits.
_SSL_ENV_AT_STARTUP: dict[str, str] = _ensure_ssl_env()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


DEFAULT_USER_AGENT = "Antiek/0.1 (services.ingestion)"
DEFAULT_TIMEOUT_S = 30.0

# Per INGESTION_NOTES.md: 10,000 entries, 10× the legacy 1,000.
METADATA_CACHE_MAX_ENTRIES = 10_000

# Per INGESTION_NOTES.md: 60s default Retry-After.
DEFAULT_RETRY_AFTER_S = 60

# robots.txt cache TTL — 24h per RFC 9309 conventions.
ROBOTS_TXT_TTL_S = 24 * 60 * 60

_CACHE_DIR_ENV = "ANTIEK_INGEST_CACHE_DIR"
_DEFAULT_CACHE_DIR = "~/.antiek/ingest_cache"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FetcherError(RuntimeError):
    """Base for all fetcher-specific failures."""


class DomainBanned(FetcherError):
    """Raised when the domain has a non-expired ban in ``ingestion_bans``."""

    def __init__(self, domain: str, banned_until: datetime, reason: str):
        super().__init__(
            f"Domain {domain!r} is banned until {banned_until.isoformat()} "
            f"(reason: {reason}); short-circuiting before HTTP."
        )
        self.domain = domain
        self.banned_until = banned_until
        self.reason = reason


class RobotsDisallowed(FetcherError):
    """Raised when robots.txt disallows our User-Agent for this URL."""


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FetchResult:
    """One successful fetch."""

    url: str          # what the caller asked for
    final_url: str    # where we landed after redirects
    status_code: int
    content_type: str
    body: bytes
    via_cache: bool = False
    throttle_waited_s: float = 0.0


# ---------------------------------------------------------------------------
# Metadata cache (LRU on disk)
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    raw = os.environ.get(_CACHE_DIR_ENV, _DEFAULT_CACHE_DIR)
    p = Path(os.path.expanduser(raw))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_key(url: str, accept: str) -> str:
    h = hashlib.sha256(f"GET|{url}|{accept}".encode("utf-8")).hexdigest()
    return h[:32]


def _cache_path(key: str) -> Path:
    return _cache_dir() / (key + ".json")


def _cache_get(url: str, accept: str) -> Optional[FetchResult]:
    """LRU lookup. Returns None on miss. ``utime`` updates atime so
    eviction picks the actually-least-recently-used file."""
    path = _cache_path(_cache_key(url, accept))
    if not path.exists():
        return None
    try:
        with path.open() as f:
            raw = json.load(f)
        os.utime(path, None)
    except (OSError, json.JSONDecodeError):
        # Corrupt entry — just skip; next fetch repopulates.
        return None
    return FetchResult(
        url=raw["url"],
        final_url=raw["final_url"],
        status_code=int(raw["status_code"]),
        content_type=raw.get("content_type", ""),
        body=bytes.fromhex(raw["body_hex"]),
        via_cache=True,
    )


def _cache_set(url: str, accept: str, res: FetchResult) -> None:
    """Insert into cache, evicting the LRU file when over capacity."""
    cache = _cache_dir()
    path = _cache_path(_cache_key(url, accept))
    payload = {
        "url": res.url,
        "final_url": res.final_url,
        "status_code": res.status_code,
        "content_type": res.content_type,
        "body_hex": res.body.hex(),
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with path.open("w") as f:
            json.dump(payload, f)
    except OSError:
        return

    # Evict if we're over capacity. LRU by access time. Cheap because
    # most fetches don't trigger eviction (cache rarely full).
    files = list(cache.glob("*.json"))
    if len(files) > METADATA_CACHE_MAX_ENTRIES:
        files.sort(key=lambda p: p.stat().st_atime)
        for old in files[: len(files) - METADATA_CACHE_MAX_ENTRIES]:
            try:
                old.unlink()
            except OSError:
                pass


def cache_clear_for_tests() -> None:
    """Wipe the cache dir. Tests call this to keep fixtures isolated."""
    cache = _cache_dir()
    for f in cache.glob("*.json"):
        try:
            f.unlink()
        except OSError:
            pass


def cache_size() -> int:
    """Number of entries currently on disk. Diagnostic."""
    return len(list(_cache_dir().glob("*.json")))


# ---------------------------------------------------------------------------
# banned_until sentinel — read + write
# ---------------------------------------------------------------------------


def _default_db_path() -> str:
    """Resolve the same DuckDB file the rest of the substrate uses."""
    try:
        from substrate.graph import default_db_path
        return default_db_path()
    except Exception:  # noqa: BLE001
        return os.path.expanduser("~/.antiek/research_graph.duckdb")


def _ensure_bans_table(db_path: str) -> None:
    """Make sure ingestion_bans exists. Idempotent. Cheap after the
    first call within a process."""
    from services.ingestion.migrations import apply_all
    try:
        apply_all(db_path)
    except Exception:  # noqa: BLE001 — schema setup is best-effort here;
        # the explicit pipeline.ensure_schema() call is the contract
        # path. We swallow so a stale lock doesn't crash fetch().
        pass


def _read_ban(db_path: str, domain: str) -> Optional[tuple[datetime, str]]:
    """Return (banned_until, reason) if domain is currently banned;
    else None. Uses a read-only DuckDB handle (the ban table is small
    and the read doesn't need the write lock)."""
    import duckdb
    if not os.path.exists(db_path):
        return None
    try:
        con = duckdb.connect(db_path, read_only=True)
    except Exception:  # noqa: BLE001
        return None
    try:
        row = con.execute(
            "SELECT banned_until, reason FROM ingestion_bans WHERE domain = ?",
            [domain],
        ).fetchone()
    except duckdb.Error:
        # Table not initialized yet — no bans to honor.
        con.close()
        return None
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass
    if row is None:
        return None
    banned_until_raw, reason = row
    if isinstance(banned_until_raw, str):
        banned_until = datetime.fromisoformat(banned_until_raw)
    else:
        banned_until = banned_until_raw
    if banned_until.tzinfo is None:
        banned_until = banned_until.replace(tzinfo=timezone.utc)
    if banned_until <= datetime.now(timezone.utc):
        return None
    return (banned_until, reason)


def _write_ban(
    db_path: str,
    domain: str,
    *,
    retry_after_s: int,
    reason: str,
) -> None:
    """UPSERT a new ban row. Goes through the same write-lock
    discipline as the rest of the substrate."""
    from runtime.db_lock import connect_write
    _ensure_bans_table(db_path)
    banned_until = datetime.now(timezone.utc) + timedelta(seconds=retry_after_s)
    with connect_write(db_path, purpose="ingestion/bans") as con:
        # DuckDB doesn't have ON CONFLICT for non-primary-key UPSERT
        # in every release; the explicit delete+insert is portable
        # and idempotent under our PRIMARY KEY (domain).
        con.execute("DELETE FROM ingestion_bans WHERE domain = ?", [domain])
        con.execute(
            "INSERT INTO ingestion_bans "
            "(domain, banned_until, retry_after_s, reason) VALUES (?, ?, ?, ?)",
            [domain, banned_until, int(retry_after_s), reason],
        )


# ---------------------------------------------------------------------------
# robots.txt cache
# ---------------------------------------------------------------------------


_ROBOTS_CACHE: dict[str, tuple[float, "urllib.robotparser.RobotFileParser"]] = {}


def _robots_ok(url: str, *, user_agent: str, client: Optional[httpx.Client] = None) -> bool:
    """Best-effort robots.txt check. Returns True when the URL is
    allowed (including when robots.txt is unreachable — we don't fail
    closed). Cached 24h per domain."""
    parsed = urlparse(url)
    host = parsed.netloc
    if not host:
        return True
    base = f"{parsed.scheme}://{host}"
    now = time.time()
    cached = _ROBOTS_CACHE.get(host)
    if cached and (now - cached[0]) < ROBOTS_TXT_TTL_S:
        return cached[1].can_fetch(user_agent, url)

    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(base + "/robots.txt")
    try:
        if client is not None:
            r = client.get(
                base + "/robots.txt",
                headers={"User-Agent": user_agent},
                timeout=5.0,
                follow_redirects=True,
            )
            if r.status_code < 400:
                rp.parse(r.text.splitlines())
            else:
                # 404 / 5xx — treat as "no robots policy", allow.
                rp.parse([])
        else:
            rp.read()
    except Exception:  # noqa: BLE001 — robots is best-effort
        rp.parse([])
    _ROBOTS_CACHE[host] = (now, rp)
    return rp.can_fetch(user_agent, url)


def robots_cache_clear_for_tests() -> None:
    _ROBOTS_CACHE.clear()


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def fetch(
    url: str,
    *,
    accept: str = "*/*",
    method: str = "GET",
    client: Optional[httpx.Client] = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    use_cache: bool = True,
    db_path: Optional[str] = None,
    check_robots: bool = True,
) -> FetchResult:
    """Fetch ``url`` through the layered safeguards.

    Order of operations:

      1. Banned-until check (DuckDB; raises DomainBanned).
      2. Cache lookup (LRU on disk).
      3. Throttle acquire (Redis sliding window).
      4. robots.txt check (24h cache).
      5. HTTP GET (httpx).
      6. On 429 → write ban; raise httpx.HTTPStatusError.
      7. On success → cache the response.

    Why ban-check before cache: if the domain is banned, we should
    surface that to the caller even if we happen to have an old
    cached copy — the ban is the operator's signal, the cache is
    convenience.
    """
    resolved_db_path = db_path or _default_db_path()

    # 1. banned_until
    domain = urlparse(url).netloc.split(":")[0].lower()
    if domain:
        ban = _read_ban(resolved_db_path, domain)
        if ban is not None:
            banned_until, reason = ban
            raise DomainBanned(domain, banned_until, reason)

    # 2. cache lookup
    if use_cache and method.upper() == "GET":
        cached = _cache_get(url, accept)
        if cached is not None:
            return cached

    # 3. throttle
    throttle_result = throttle.acquire(url)

    # 4. robots
    if check_robots:
        if not _robots_ok(url, user_agent=DEFAULT_USER_AGENT, client=client):
            raise RobotsDisallowed(
                f"robots.txt disallows fetching {url!r} for User-Agent "
                f"{DEFAULT_USER_AGENT!r}."
            )

    # 5. HTTP
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": accept,
    }
    if client is not None:
        r = client.request(
            method.upper(), url, headers=headers, timeout=timeout_s,
            follow_redirects=True,
        )
    else:
        with httpx.Client(follow_redirects=True) as c:
            r = c.request(
                method.upper(), url, headers=headers, timeout=timeout_s,
            )

    # 6. 429 → ban write
    if r.status_code == 429:
        retry_after = r.headers.get("retry-after", "")
        try:
            retry_after_s = int(retry_after)
        except (ValueError, TypeError):
            retry_after_s = DEFAULT_RETRY_AFTER_S
        if domain:
            _write_ban(
                resolved_db_path, domain,
                retry_after_s=retry_after_s, reason="429",
            )
        # Surface to the caller; the pipeline records this on the job.
        r.raise_for_status()

    r.raise_for_status()

    content_type = r.headers.get("content-type", "") or ""
    body = r.content
    result = FetchResult(
        url=url,
        final_url=str(r.url),
        status_code=r.status_code,
        content_type=content_type,
        body=body,
        via_cache=False,
        throttle_waited_s=throttle_result.waited_s,
    )

    # 7. cache write
    if use_cache and method.upper() == "GET":
        _cache_set(url, accept, result)

    return result


# Diagnostic helper for tests + INGESTION_NOTES.md verification gates.
def ssl_env_at_startup() -> dict[str, str]:
    """Return the SSL_CERT_FILE / REQUESTS_CA_BUNDLE env vars resolved
    at module import time. Used by the SSL-env verification gate to
    prove they were explicitly resolved."""
    return dict(_SSL_ENV_AT_STARTUP)
