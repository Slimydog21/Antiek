"""CLI entry point for monitoring mode — operator-invoked, box-bounded.

Mirrors ``orchestration/continuous/__main__.py``'s ``--once`` shape. This
is the operator-invoked refresh: there is deliberately NO long-lived loop,
NO daemon, NO systemd unit (§16 box-bounded — see
``docs/decisions/monitoring-mode-north-star.md`` for why the self-updating
timer is a north star, not shipped here).

Usage:

    python -m orchestration.monitoring --refresh <monitor_id> --once
    python -m orchestration.monitoring --list

The single-iteration ``--once`` refresh runs one tick (one
``refresh_monitor`` call) and exits. There is no run-forever mode by
design.
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m orchestration.monitoring",
        description=(
            "Monitoring mode (Personal-Reading Lane SPR-09). Operator-"
            "invoked, box-bounded refresh over the personal lane. No "
            "always-on daemon — refresh is a one-shot (--once)."
        ),
    )
    parser.add_argument(
        "--refresh",
        metavar="MONITOR_ID",
        help="Refresh a monitor: surface personal-lane items since its checkpoint.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all monitors and exit.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Run a single refresh tick and exit. This is the ONLY refresh "
            "mode — there is no run-forever loop (§16 box-bounded)."
        ),
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Max items to surface (default: the grazing default, 20).",
    )
    args = parser.parse_args(argv)

    # Defer heavy imports so --help is cheap.
    from runtime.db_lock import connect_read
    from orchestration.monitoring.monitor import (
        DEFAULT_TOP_K,
        list_monitors,
        refresh_monitor,
        resolve_db_path,
    )
    from substrate.graph.search import SentenceTransformerEmbedding

    db_path = resolve_db_path(None)

    if args.list:
        con = connect_read(db_path)
        try:
            for m in list_monitors(con):
                print(
                    f"{m.monitor_id}\tinvestigation={m.investigation_id}\t"
                    f"last_seen_at={m.last_seen_at}\tterms={len(m.query_terms)}"
                )
        finally:
            con.close()
        return 0

    if args.refresh:
        # The refresh ranks against the STORED centroid, so the model is only
        # needed for interface symmetry; load lazily and tolerate its absence
        # (chronological fallback still works without a live model).
        try:
            model = SentenceTransformerEmbedding()
        except Exception:  # pragma: no cover — model optional for refresh
            model = None  # type: ignore[assignment]
        top_k = args.top_k if args.top_k is not None else DEFAULT_TOP_K
        con = connect_read(db_path)
        try:
            result = refresh_monitor(
                con, args.refresh, model=model, top_k=top_k, path=db_path
            )
        finally:
            con.close()
        print(
            f"refreshed {result.monitor_id}: {len(result.new_items)} new item(s); "
            f"checkpoint -> {result.new_checkpoint}"
        )
        return 0

    parser.error("nothing to do: pass --refresh <monitor_id> --once or --list")
    return 2  # pragma: no cover — argparse error exits first


if __name__ == "__main__":
    sys.exit(main())
