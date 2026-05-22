"""Operator CLI for `acquisition.search.exa`.

    python -m acquisition.search.exa discover --query "..." --inv inv-1 --k 10
    python -m acquisition.search.exa lookup   --claim "..."  --inv inv-1 --k 3
    python -m acquisition.search.exa budget

Accelerates the spec §15.1 operator-validation step — the operator
no longer has to spin up a REPL to run a single `discover()` call.
Output defaults to a compact table; `--json` switches to
machine-parseable output.

Authentication: `EXA_API_KEY` must be set. The legal-gate path
remains operator-acknowledgment-aware — the default factory
returns the real `RegistryBackedLegalGate`, and the CLI does not
auto-enable bypass.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, List, Optional

from .adapter import (
    DiscoveryBudgetExceeded,
    DiscoveryProposed,
    discover,
    promote_discovery,
    reject_discovery,
)
from .budget import read_state
from .client import ExaClientError
from .lookup import exa_lookup_claim


# ── Rendering ────────────────────────────────────────────────────


def _truncate(s: Optional[str], n: int) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _render_proposals_table(
    proposals: List[DiscoveryProposed], *, out=sys.stdout
) -> None:
    if not proposals:
        print("(no results)", file=out)
        return
    cols = ["#", "tier", "score", "url", "title"]
    rows = [
        [
            str(i + 1),
            str(p.suggested_tier),
            f"{p.relevance_score:.2f}" if p.relevance_score is not None else "—",
            _truncate(p.url, 60),
            _truncate(p.title, 60),
        ]
        for i, p in enumerate(proposals)
    ]
    widths = [
        max(len(r[j]) for r in [cols, *rows]) for j in range(len(cols))
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*cols), file=out)
    print(fmt.format(*("-" * w for w in widths)), file=out)
    for r in rows:
        print(fmt.format(*r), file=out)


def _render_lookup_table(results: List[Any], *, out=sys.stdout) -> None:
    if not results:
        print("(no results)", file=out)
        return
    cols = ["#", "score", "url", "title", "snippet"]
    rows = [
        [
            str(i + 1),
            f"{r.relevance_score:.2f}" if r.relevance_score is not None else "—",
            _truncate(r.url, 50),
            _truncate(r.title, 40),
            _truncate(r.text_snippet, 80),
        ]
        for i, r in enumerate(results)
    ]
    widths = [
        max(len(row[j]) for row in [cols, *rows]) for j in range(len(cols))
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*cols), file=out)
    print(fmt.format(*("-" * w for w in widths)), file=out)
    for r in rows:
        print(fmt.format(*r), file=out)


def _render_budget(state, *, out=sys.stdout) -> None:
    print(f"date:       {state.date_stamp}", file=out)
    print(f"calls:      {state.call_count}", file=out)
    print(f"spent_usd:  ${state.spent_usd:.4f}", file=out)
    print(f"cap_usd:    ${state.cap_usd:.2f}", file=out)
    pct = (state.spent_usd / state.cap_usd * 100) if state.cap_usd > 0 else 0
    print(f"used:       {pct:.1f}%", file=out)


# ── Subcommand implementations ───────────────────────────────────


def _cmd_discover(args: argparse.Namespace, *, out=sys.stdout) -> int:
    try:
        proposals = discover(
            query=args.query,
            investigation_id=args.inv,
            num_results=args.k,
            category=args.category,
            include_domains=args.include or None,
            exclude_domains=args.exclude or None,
            use_cache=not args.no_cache,
        )
    except DiscoveryBudgetExceeded as e:
        print(f"BUDGET EXCEEDED: {e}", file=sys.stderr)
        return 2
    except ExaClientError as e:
        print(f"EXA ERROR: {e}", file=sys.stderr)
        return 3

    if args.json:
        from dataclasses import asdict
        print(json.dumps([asdict(p) for p in proposals], indent=2), file=out)
    else:
        _render_proposals_table(proposals, out=out)
    return 0


def _cmd_lookup(args: argparse.Namespace, *, out=sys.stdout) -> int:
    try:
        results = exa_lookup_claim(
            claim_text=args.claim,
            investigation_id=args.inv,
            k=args.k,
        )
    except DiscoveryBudgetExceeded as e:
        print(f"BUDGET EXCEEDED: {e}", file=sys.stderr)
        return 2
    except ExaClientError as e:
        print(f"EXA ERROR: {e}", file=sys.stderr)
        return 3
    except ValueError as e:
        print(f"INPUT ERROR: {e}", file=sys.stderr)
        return 4

    if args.json:
        print(
            json.dumps([r.model_dump() for r in results], indent=2),
            file=out,
        )
    else:
        _render_lookup_table(results, out=out)
    return 0


def _cmd_budget(args: argparse.Namespace, *, out=sys.stdout) -> int:
    state = read_state()
    if args.json:
        print(
            json.dumps(
                {
                    "date_stamp": state.date_stamp,
                    "call_count": state.call_count,
                    "spent_usd": state.spent_usd,
                    "cap_usd": state.cap_usd,
                },
                indent=2,
            ),
            file=out,
        )
    else:
        _render_budget(state, out=out)
    return 0


def _cmd_retention_rollup(args: argparse.Namespace, *, out=sys.stdout) -> int:
    """Roll up expired discovery events into the discovery_summary
    table and truncate source JSONL files. Per spec §14.1.

    `--dry-run` enumerates what WOULD be rolled up without writing
    summary rows or truncating files — same read-only posture as the
    legal-gate audit CLI.
    """
    from acquisition.search.retention import (
        DEFAULT_RETENTION_DAYS,
        rollup_expired,
    )

    retention_days = args.retention_days
    if args.dry_run:
        # Read-only enumeration: walk the events dir and report what
        # would be rolled up without touching the substrate.
        from datetime import datetime, timedelta, timezone
        from pathlib import Path
        from acquisition.search import default_discovery_events_dir
        from acquisition.search.retention import _parse_event_ts

        edir = Path(default_discovery_events_dir())
        cutoff = (datetime.now(timezone.utc).replace(tzinfo=None)
                  - timedelta(days=retention_days))
        files_examined = 0
        files_would_rollup = 0
        events_would_rollup = 0
        for f in sorted(edir.rglob("*.jsonl")):
            files_examined += 1
            try:
                lines = f.read_text().splitlines()
            except OSError:
                continue
            most_recent = None
            count = 0
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                count += 1
                ts = _parse_event_ts(ev)
                if ts is None:
                    continue
                if most_recent is None or ts > most_recent:
                    most_recent = ts
            if most_recent is not None and most_recent <= cutoff:
                files_would_rollup += 1
                events_would_rollup += count
        body = {
            "dry_run": True,
            "retention_days": retention_days,
            "events_dir": str(edir),
            "files_examined": files_examined,
            "files_would_rollup": files_would_rollup,
            "events_would_rollup": events_would_rollup,
        }
        if args.json:
            print(json.dumps(body, indent=2), file=out)
        else:
            print(f"DRY RUN — retention={retention_days}d, events_dir={edir}", file=out)
            print(f"  files examined:      {files_examined}", file=out)
            print(f"  files to roll up:    {files_would_rollup}", file=out)
            print(f"  events to roll up:   {events_would_rollup}", file=out)
        return 0

    r = rollup_expired(retention_days=retention_days)
    body = {
        "dry_run": False,
        "retention_days": retention_days,
        "files_examined": r.files_examined,
        "files_rolled_up": r.files_rolled_up,
        "summary_rows_written": r.summary_rows_written,
        "raw_events_rolled_up": r.raw_events_rolled_up,
    }
    if args.json:
        print(json.dumps(body, indent=2), file=out)
    else:
        print(f"Rollup complete (retention={retention_days}d)", file=out)
        print(f"  files examined:        {r.files_examined}", file=out)
        print(f"  files rolled up:       {r.files_rolled_up}", file=out)
        print(f"  summary rows written:  {r.summary_rows_written}", file=out)
        print(f"  raw events rolled up:  {r.raw_events_rolled_up}", file=out)
    return 0


def _cmd_retention_summary(args: argparse.Namespace, *, out=sys.stdout) -> int:
    """Read the most recent `days` of discovery_summary rows.
    Operator-facing read helper."""
    from acquisition.search.retention import recent_summary

    rows = recent_summary(days=args.days)
    if args.json:
        # `day_utc` and `summarized_at` are datetime objects from
        # DuckDB; coerce to ISO strings so JSON serializes cleanly.
        def _coerce(v):
            if hasattr(v, "isoformat"):
                return v.isoformat()
            return v
        clean = [{k: _coerce(v) for k, v in r.items()} for r in rows]
        print(json.dumps(clean, indent=2), file=out)
        return 0
    if not rows:
        print("(no discovery_summary rows in the requested window)", file=out)
        return 0
    cols = ["day", "provider", "proposals", "selected", "rejected", "cost"]
    rendered = []
    for r in rows:
        rejected_total = (
            r.get("rejected_by_gate", 0)
            + r.get("rejected_by_op", 0)
            + r.get("fetch_failed", 0)
        )
        rendered.append([
            str(r.get("day_utc", "")),
            r.get("provider", ""),
            str(r.get("proposal_count", 0)),
            str(r.get("selected_count", 0)),
            str(rejected_total),
            f"${r.get('total_cost_usd', 0.0):.4f}",
        ])
    widths = [max(len(row[j]) for row in [cols, *rendered]) for j in range(len(cols))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*cols), file=out)
    print(fmt.format(*("-" * w for w in widths)), file=out)
    for row in rendered:
        print(fmt.format(*row), file=out)
    return 0


# ── argparse wiring ──────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m acquisition.search.exa",
        description=(
            "Operator CLI for the Exa & Browserbase Wedge 1 (discovery) "
            "+ Wedge 3 (verifier corroboration) surfaces."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # discover
    d = sub.add_parser("discover", help="Run an Exa neural search.")
    d.add_argument("--query", "-q", required=True, help="Search query.")
    d.add_argument(
        "--inv", "-i", required=True,
        help="Investigation id (e.g. inv-2026-05-21-claude-pricing).",
    )
    d.add_argument("--k", type=int, default=10, help="Result count (1-100).")
    d.add_argument("--category", default=None, help="Exa category filter.")
    d.add_argument(
        "--include", action="append", default=None,
        help="Whitelist domain (repeatable).",
    )
    d.add_argument(
        "--exclude", action="append", default=None,
        help="Blacklist domain (repeatable).",
    )
    d.add_argument(
        "--no-cache", action="store_true",
        help="Skip the 24h discovery cache; force a live Exa call.",
    )
    d.add_argument(
        "--json", action="store_true", help="Output JSON instead of a table.",
    )
    d.set_defaults(func=_cmd_discover)

    # lookup
    l_ = sub.add_parser(
        "lookup",
        help="Run an Exa verifier-tier corroboration lookup (Wedge 3).",
    )
    l_.add_argument(
        "--claim", "-c", required=True,
        help="The claim text to corroborate or refute.",
    )
    l_.add_argument(
        "--inv", "-i", required=True, help="Investigation id.",
    )
    l_.add_argument("--k", type=int, default=3, help="Result count (1-20).")
    l_.add_argument(
        "--json", action="store_true", help="Output JSON instead of a table.",
    )
    l_.set_defaults(func=_cmd_lookup)

    # budget
    b = sub.add_parser(
        "budget", help="Print today's Exa daily-budget state.",
    )
    b.add_argument(
        "--json", action="store_true", help="Output JSON instead of a table.",
    )
    b.set_defaults(func=_cmd_budget)

    # retention (nested: rollup, summary)
    r = sub.add_parser(
        "retention",
        help="Manage the 30-day discovery-events retention + rollup (spec §14.1).",
    )
    r_sub = r.add_subparsers(dest="retention_cmd", required=True)

    # retention rollup
    r_rollup = r_sub.add_parser(
        "rollup",
        help=(
            "Summarize and truncate JSONL files older than --retention-days. "
            "Use --dry-run to preview without writing."
        ),
    )
    r_rollup.add_argument(
        "--retention-days", type=int, default=30,
        help="Roll up events older than this many days (default: 30).",
    )
    r_rollup.add_argument(
        "--dry-run", action="store_true",
        help="Read-only: report what would be rolled up without writing.",
    )
    r_rollup.add_argument(
        "--json", action="store_true", help="Output JSON instead of a table.",
    )
    r_rollup.set_defaults(func=_cmd_retention_rollup)

    # retention summary
    r_summary = r_sub.add_parser(
        "summary",
        help="Print recent rows from the discovery_summary table.",
    )
    r_summary.add_argument(
        "--days", type=int, default=7,
        help="Look back this many days (default: 7).",
    )
    r_summary.add_argument(
        "--json", action="store_true", help="Output JSON instead of a table.",
    )
    r_summary.set_defaults(func=_cmd_retention_summary)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
