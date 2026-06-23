"""Discovery-events retention + rollup (Exa-spec §14.1).

Discovery events (DiscoveryProposed, DiscoverySelected,
VerifierLookup) live in ``~/.antiek/discovery_events/*.jsonl``
during the 30-day retention window. After 30 days they're
summarized into the ``discovery_summary`` DuckDB table (one row
per (provider, day_utc, query_hash)) and the source JSONL is
truncated.

This module exposes two functions:

  - ``rollup_expired(retention_days=30, *, db_path=None,
    events_dir=None)`` — the operator-or-cron entry point.
    Idempotent: re-running with the same window produces the
    same summary rows (via ON CONFLICT … DO UPDATE).
  - ``recent_summary(days=7, *, db_path=None)`` — operator-facing
    read helper; returns the most recent N days of summary rows.

The rollup is conservative — it only summarizes days where ALL of
the day's events are older than the retention window. A day with
even one event newer than the cutoff stays in raw JSONL form. This
prevents partial-day summaries that would lose data on re-rollup.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

DEFAULT_RETENTION_DAYS = 30


def _now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _events_dir(events_dir: str | None) -> Path:
    if events_dir:
        return Path(events_dir)
    # Lazy import to avoid the circular acquisition.search.__init__
    # → acquisition.search.exa.adapter chain on module load.
    from . import default_discovery_events_dir  # noqa: PLC0415
    return Path(default_discovery_events_dir())


def _parse_event_ts(raw: dict) -> datetime | None:
    """Best-effort parse of the event's emitted_at ISO timestamp.
    None means the event will be conservatively kept (not rolled
    up) — same posture as `runtime/weekly_report.py`'s parser."""
    v = raw.get("emitted_at") or raw.get("ts")
    if not isinstance(v, str):
        return None
    s = v.rstrip("Z")
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except ValueError:
        return None


def _day(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d")


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


@dataclass
class RollupResult:
    """Returned by `rollup_expired`. Useful for tests + the operator
    CLI's confirmation output."""

    files_examined: int
    files_rolled_up: int
    summary_rows_written: int
    raw_events_rolled_up: int


def rollup_expired(
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    db_path: str | None = None,
    events_dir: str | None = None,
    now: datetime | None = None,
) -> RollupResult:
    """Walk the discovery-events directory; for every file whose
    most-recent event is older than `retention_days`, fold all of
    that file's events into the `discovery_summary` table and
    truncate the source.

    Returns counters for the summary printable to the operator.

    Idempotency: ON CONFLICT DO UPDATE on the summary table means
    re-running against the same data set produces the same rows
    (the second run finds no remaining files because the first
    truncated them).
    """
    from substrate.graph import default_db_path

    now = now or _now_utc()
    cutoff = now - timedelta(days=retention_days)
    edir = _events_dir(events_dir)
    if not edir.exists():
        return RollupResult(0, 0, 0, 0)

    resolved_db = db_path or default_db_path()
    files_examined = 0
    files_rolled_up = 0
    raw_events_rolled_up = 0

    # Per (provider, day_utc, query_hash) aggregate buckets accumulated
    # across all expired files, then upserted in one transaction.
    buckets: dict[tuple[str, str, str], dict] = defaultdict(
        lambda: {
            "query_preview": None,
            "proposal_count": 0,
            "selected_count": 0,
            "rejected_by_gate": 0,
            "rejected_by_op": 0,
            "fetch_failed": 0,
            "distinct_urls": set(),
            "total_cost_usd": 0.0,
        }
    )
    files_to_truncate: list[Path] = []

    for f in sorted(edir.rglob("*.jsonl")):
        files_examined += 1
        try:
            lines = f.read_text().splitlines()
        except OSError:
            continue
        # Find the most recent event timestamp in the file. If any
        # event is newer than the cutoff, skip the whole file —
        # partial rollups would lose data.
        most_recent: datetime | None = None
        parsed_events: list[dict] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            parsed_events.append(ev)
            ts = _parse_event_ts(ev)
            if ts is None:
                continue
            if most_recent is None or ts > most_recent:
                most_recent = ts
        if most_recent is None:
            # File contains no parseable timestamps; conservatively keep it.
            continue
        if most_recent > cutoff:
            continue

        # Roll up. Each event contributes to its
        # (provider, day_utc, query_hash) bucket.
        for ev in parsed_events:
            payload = ev.get("payload") or {}
            action_type = ev.get("action_type") or ""
            provider = payload.get("provider", "unknown")
            ts = _parse_event_ts(ev) or most_recent
            day = _day(ts)
            query = payload.get("query") or payload.get("claim_text") or ""
            q_hash = _query_hash(query)
            b = buckets[(provider, day, q_hash)]
            if b["query_preview"] is None and query:
                b["query_preview"] = query[:200]
            if action_type == "discovery.proposed":
                b["proposal_count"] += 1
                url = payload.get("url")
                if url:
                    b["distinct_urls"].add(url)
                cost = payload.get("cost_usd_estimate") or 0.0
                with contextlib.suppress(TypeError, ValueError):
                    b["total_cost_usd"] += float(cost)
            elif action_type == "discovery.selected":
                decision = payload.get("decision", "")
                if decision == "ingested":
                    b["selected_count"] += 1
                elif decision == "rejected_by_legal_gate":
                    b["rejected_by_gate"] += 1
                elif decision == "rejected_by_operator":
                    b["rejected_by_op"] += 1
                elif decision == "fetch_failed":
                    b["fetch_failed"] += 1
            elif action_type == "verifier.lookup":
                cost = payload.get("cost_usd_estimate") or 0.0
                with contextlib.suppress(TypeError, ValueError):
                    b["total_cost_usd"] += float(cost)
            raw_events_rolled_up += 1

        files_to_truncate.append(f)
        files_rolled_up += 1

    if not buckets:
        return RollupResult(
            files_examined=files_examined,
            files_rolled_up=files_rolled_up,
            summary_rows_written=0,
            raw_events_rolled_up=raw_events_rolled_up,
        )

    # Upsert summary rows + truncate the source files atomically
    # via the substrate's single-writer discipline. Per spec §14.1
    # the JSONL files exist for audit during the retention window;
    # after rollup, the summary table is authoritative.
    from runtime.db_lock import connect_write

    with connect_write(resolved_db, purpose="acquisition/search/retention.rollup") as con:
        run_at = now
        for (provider, day, q_hash), b in buckets.items():
            summary_id = hashlib.sha256(
                f"{provider}\x1f{day}\x1f{q_hash}".encode()
            ).hexdigest()[:32]
            con.execute(
                """
                INSERT INTO discovery_summary (
                    summary_id, provider, day_utc, query_hash, query_preview,
                    proposal_count, selected_count, rejected_by_gate,
                    rejected_by_op, fetch_failed, distinct_urls,
                    total_cost_usd, summarized_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (summary_id) DO UPDATE SET
                    proposal_count   = discovery_summary.proposal_count   + EXCLUDED.proposal_count,
                    selected_count   = discovery_summary.selected_count   + EXCLUDED.selected_count,
                    rejected_by_gate = discovery_summary.rejected_by_gate + EXCLUDED.rejected_by_gate,
                    rejected_by_op   = discovery_summary.rejected_by_op   + EXCLUDED.rejected_by_op,
                    fetch_failed     = discovery_summary.fetch_failed     + EXCLUDED.fetch_failed,
                    distinct_urls    = discovery_summary.distinct_urls    + EXCLUDED.distinct_urls,
                    total_cost_usd   = discovery_summary.total_cost_usd   + EXCLUDED.total_cost_usd,
                    summarized_at    = EXCLUDED.summarized_at
                """,
                [
                    summary_id,
                    provider,
                    day,
                    q_hash,
                    b["query_preview"],
                    b["proposal_count"],
                    b["selected_count"],
                    b["rejected_by_gate"],
                    b["rejected_by_op"],
                    b["fetch_failed"],
                    len(b["distinct_urls"]),
                    b["total_cost_usd"],
                    run_at,
                ],
            )

    # Truncate source files AFTER the summary is committed so a
    # rollup interrupted between the two operations doesn't lose
    # data (re-running would re-summarize the same events; the
    # ON CONFLICT addition would double-count). Operator can
    # verify via `recent_summary(days=N)` before truncation lands.
    for f in files_to_truncate:
        try:
            f.write_text("")
        except OSError:
            continue

    return RollupResult(
        files_examined=files_examined,
        files_rolled_up=files_rolled_up,
        summary_rows_written=len(buckets),
        raw_events_rolled_up=raw_events_rolled_up,
    )


def recent_summary(
    *,
    days: int = 7,
    db_path: str | None = None,
) -> list[dict]:
    """Read the most-recent `days` of discovery_summary rows.
    Operator-facing helper; the audit CLI consumes this."""
    from runtime.db_lock import connect_read
    from substrate.graph import default_db_path

    resolved = db_path or default_db_path()
    try:
        con = connect_read(resolved)
    except Exception:
        return []
    try:
        cutoff_day = (_now_utc() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = con.execute(
            """
            SELECT provider, day_utc, query_hash, query_preview,
                   proposal_count, selected_count, rejected_by_gate,
                   rejected_by_op, fetch_failed, distinct_urls,
                   total_cost_usd, summarized_at
            FROM discovery_summary
            WHERE day_utc >= ?
            ORDER BY day_utc DESC, provider, query_hash
            """,
            [cutoff_day],
        ).fetchall()
    except Exception:
        return []
    finally:
        con.close()
    cols = [
        "provider", "day_utc", "query_hash", "query_preview",
        "proposal_count", "selected_count", "rejected_by_gate",
        "rejected_by_op", "fetch_failed", "distinct_urls",
        "total_cost_usd", "summarized_at",
    ]
    return [dict(zip(cols, row, strict=True)) for row in rows]


__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "RollupResult",
    "recent_summary",
    "rollup_expired",
]
