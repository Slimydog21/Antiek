"""Discovery cache — 24h same-query dedup (spec §6.5).

Lives in the main substrate DuckDB (`discovery_cache` table) because
the spec mandates DuckDB and because future Wedge 3 work may want to
correlate a verifier's `exa_lookup_claim` against prior discovery
calls.

Cache hit semantics: short-circuit the Exa call AND skip event
re-emission. The DiscoveryProposed events are part of the audit
trail; re-emitting them on a cache hit would suggest the operator
re-considered the URLs when they actually didn't. The cached
proposals are returned AS-IS — same discovery_ids, same fields.

TTL: 24h by default; configurable per call. Older rows are expired
on read (lazy purge) and may be batch-cleared by callers via
`purge_expired(db_path)`. The cache is not a graph-write event;
DuckDB lock semantics still apply (single-writer per file) but the
cache writer doesn't block legal-gate decisions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

DEFAULT_TTL_SECONDS: int = 24 * 60 * 60


def cache_key(
    *,
    query: str,
    investigation_id: str,
    provider: str = "exa",
    num_results: int = 10,
    category: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    start_published_date: str | None = None,
    end_published_date: str | None = None,
) -> str:
    """Stable hash over every parameter that should produce identical
    Exa results. Order-invariant for the domain lists. Hex digest,
    32 chars (sha256 truncated)."""
    inc = sorted(include_domains) if include_domains else []
    exc = sorted(exclude_domains) if exclude_domains else []
    parts = [
        provider,
        query,
        investigation_id,
        str(num_results),
        category or "",
        "|".join(inc),
        "|".join(exc),
        start_published_date or "",
        end_published_date or "",
    ]
    raw = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _now_utc() -> datetime:
    """Naive UTC. DuckDB TIMESTAMP is timezone-naive; we keep app-side
    arithmetic naive too so storage round-trips identity-preserving."""
    return datetime.now(UTC).replace(tzinfo=None)


def lookup(
    key: str,
    *,
    db_path: str,
    now: datetime | None = None,
) -> list[dict] | None:
    """Return the cached proposals list (as a list of dicts ready to
    re-hydrate into DiscoveryProposed) if the key is present AND
    not expired. None otherwise.

    Uses a read-only DuckDB connection; safe to call concurrently with
    other readers."""
    import duckdb

    now = now or _now_utc()
    try:
        con = duckdb.connect(db_path, read_only=True)
    except Exception:
        # Cache miss when the DB file doesn't exist yet (first-ever
        # discover call). Caller proceeds to the live Exa call.
        return None
    try:
        rows = con.execute(
            "SELECT proposals_json, expires_at FROM discovery_cache "
            "WHERE cache_key = ?",
            [key],
        ).fetchall()
    finally:
        con.close()

    if not rows:
        return None
    proposals_json, expires_at = rows[0]
    # Both sides naive UTC — see `_now_utc()`.
    if expires_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    if expires_at <= now:
        return None
    try:
        return json.loads(proposals_json)
    except (ValueError, TypeError):
        return None


def store(
    key: str,
    *,
    proposals: list,
    query: str,
    investigation_id: str,
    provider: str = "exa",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    db_path: str,
    now: datetime | None = None,
) -> None:
    """Insert or refresh the cache entry. Idempotent via ON CONFLICT.
    `proposals` should be a list of DiscoveryProposed dataclass
    instances (or dicts) — they're JSON-serialized."""
    from runtime.db_lock import connect_write

    now = now or _now_utc()
    expires_at = now + timedelta(seconds=ttl_seconds)
    rows = []
    cost_usd = 0.0
    for p in proposals:
        if hasattr(p, "__dataclass_fields__"):
            d = asdict(p)
        elif isinstance(p, dict):
            d = p
        else:
            # Fall back to vars() for objects that aren't dataclasses
            # but expose __dict__ (rare).
            d = dict(getattr(p, "__dict__", {}))
        rows.append(d)
        cost_usd += float(d.get("cost_usd_estimate") or 0.0)
    proposals_json = json.dumps(rows)

    with connect_write(db_path, purpose="acquisition/search/exa/cache") as con:
        con.execute(
            """
            INSERT INTO discovery_cache
                (cache_key, provider, query, investigation_id,
                 proposals_json, cached_at, expires_at, result_count, cost_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (cache_key) DO UPDATE SET
                proposals_json = EXCLUDED.proposals_json,
                cached_at      = EXCLUDED.cached_at,
                expires_at     = EXCLUDED.expires_at,
                result_count   = EXCLUDED.result_count,
                cost_usd       = EXCLUDED.cost_usd
            """,
            [
                key,
                provider,
                query,
                investigation_id,
                proposals_json,
                now,
                expires_at,
                len(rows),
                cost_usd,
            ],
        )


def purge_expired(
    *,
    db_path: str,
    now: datetime | None = None,
) -> int:
    """Delete expired rows. Returns the number purged. Safe to run
    periodically (e.g. from a nightly job); the lazy-expire on read
    already handles correctness."""
    from runtime.db_lock import connect_write

    now = now or _now_utc()
    with connect_write(db_path, purpose="acquisition/search/exa/cache.purge") as con:
        before = con.execute(
            "SELECT COUNT(*) FROM discovery_cache WHERE expires_at <= ?", [now]
        ).fetchone()[0]
        con.execute("DELETE FROM discovery_cache WHERE expires_at <= ?", [now])
        return int(before)
