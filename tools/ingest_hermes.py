#!/usr/bin/env python3
"""ingest_hermes — pull Hermes research_events into the Antiek corpus (D-Hermes).

A separate agent harness (Hermes at ``~/.hermes``) writes real research traces
to ``research_events/*.jsonl``. This CLI is the operator-facing entry point for
the hardened adapter at ``substrate.research_bridge.hermes_ingest``:

1. Resolve the events directory under the allowed-root trust boundary.
2. Group events by investigation, render provenance markdown, and ingest via
   the LIVE ``ingest_file`` path (content-addressed, idempotent).
3. Report new / cache-hit / skipped / error counts honestly.

Safety posture (mirrors ``tools.license_library`` / ``tools.run_investigation``)
------------------------------------------------------------------------------
- ``--dry-run`` is the DEFAULT. It parses + groups + renders + reports the
  plan and writes NOTHING to the graph. Pass ``--apply`` to mutate.
- ``--limit N`` caps investigations (not events).
- Single-writer: every mutation rides ``connect_write(purpose=...)``.
- Hermes dir is read-only; secrets in payloads are redacted by the adapter.
- Default ``--db-path`` is the operator Mac path; on prod use
  ``/home/antiek/.antiek/antiek.duckdb`` explicitly with ``--apply``.

Usage::

    # Plan only (no writes):
    python -m tools.ingest_hermes

    # Apply against a scratch copy first:
    cp ~/.antiek/antiek.duckdb /tmp/scratch.duckdb
    python -m tools.ingest_hermes --db-path /tmp/scratch.duckdb --apply

    # Apply against the REAL store:
    python -m tools.ingest_hermes --db-path ~/.antiek/antiek.duckdb --apply

    # Prod-style (Hermes events staged under ANTIEK_HERMES_EVENTS_DIR):
    ANTIEK_HERMES_EVENTS_DIR=/home/antiek/hermes_ingest_smoke \\
      python -m tools.ingest_hermes --db-path /home/antiek/.antiek/antiek.duckdb \\
      --events-dir /home/antiek/hermes_ingest_smoke --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from runtime.db_lock import connect_write
from substrate.research_bridge.hermes_ingest import (
    DEFAULT_HERMES_EVENTS_DIR,
    HermesEventsDirError,
    default_allowed_roots,
    group_investigations,
    ingest_hermes_events,
    iter_hermes_events,
    resolve_allowed_events_dir,
)

DEFAULT_DB_PATH = os.path.expanduser("~/.antiek/antiek.duckdb")
# Mac operator default historically used research_graph.duckdb — fall back.
_ALT_DB_PATH = os.path.expanduser("~/.antiek/research_graph.duckdb")
DEFAULT_PURPOSE = "hermes_ingest_cli"
EVIDENCE_SCHEMA = "antiek.hermes_ingest_cli.evidence.v1"
DISTILL_HANDOFF_SCHEMA = "antiek.hermes_ingest_cli.distill_handoff.v1"


def _default_db_path() -> str:
    if Path(DEFAULT_DB_PATH).exists():
        return DEFAULT_DB_PATH
    if Path(_ALT_DB_PATH).exists():
        return _ALT_DB_PATH
    return DEFAULT_DB_PATH


def plan(
    events_dir: str | Path,
    *,
    limit: int | None,
) -> tuple[int, int, list[str]]:
    """Return ``(event_count, investigation_count, investigation_ids[:])``.

    Read-only. Raises ``HermesEventsDirError`` if ``events_dir`` escapes the
    allowed roots.
    """
    resolve_allowed_events_dir(events_dir)
    records = list(iter_hermes_events(events_dir))
    groups = group_investigations(records)
    ids = sorted(groups)
    if limit is not None and limit >= 0:
        ids = ids[:limit]
    return len(records), len(ids), ids


def _write_evidence(path: str | Path, receipt: dict) -> None:
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _base_receipt(
    *,
    events_dir: str | Path,
    db_path: str,
    mode: str,
    limit: int | None,
    parsed_events: int,
    investigation_ids: list[str],
) -> dict:
    return {
        "schema": EVIDENCE_SCHEMA,
        "events_dir": str(resolve_allowed_events_dir(events_dir)),
        "db_path": str(Path(db_path).expanduser()),
        "mode": mode,
        "limit": limit,
        "parsed_events": parsed_events,
        "investigations_in_plan": len(investigation_ids),
        "investigation_ids": investigation_ids,
        "payload_text_included": False,
        "provider_calls_made": False,
        "distillation_run": False,
    }


def _distill_handoff_receipt(*, db_path: str, results: list[dict]) -> dict:
    ready = [
        {
            "investigation_id": result["investigation_id"],
            "document_id": result["document_id"],
            "document_type": result["document_type"],
            "events_count": result["events_count"],
            "source_label": result["source_label"],
            "was_new": result["was_new"],
        }
        for result in results
        if result.get("document_id") and result.get("status") in {"ok", "cache_hit"}
    ]
    return {
        "schema": DISTILL_HANDOFF_SCHEMA,
        "db_path": str(Path(db_path).expanduser()),
        "documents_ready": ready,
        "documents_ready_count": len(ready),
        "distillation_run": False,
        "provider_calls_made": False,
        "payload_text_included": False,
        "runner": "substrate.research_bridge.ingest_file.distill_ingested_document",
        "operator_next_step": (
            "Run the note-taker document pass over these document_id values "
            "with an explicit distiller/provider budget."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="ingest_hermes",
        description=(
            "Ingest Hermes research_events/*.jsonl into Antiek via the live "
            "ingest_file path. Dry-run by default; pass --apply to write."
        ),
    )
    p.add_argument(
        "--events-dir",
        default=None,
        help=(
            f"Hermes events directory (default: {DEFAULT_HERMES_EVENTS_DIR} "
            "or ANTIEK_HERMES_EVENTS_DIR when set)"
        ),
    )
    p.add_argument(
        "--db-path",
        default=None,
        help=f"DuckDB path (default: {_default_db_path()})",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap number of investigations ingested (not events)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="MUTATE the named DuckDB. Without it, plan-only (no writes).",
    )
    p.add_argument(
        "--evidence-json",
        default=None,
        help=(
            "write a machine-readable smoke receipt with counts and result "
            "statuses only; Hermes payload text is never included"
        ),
    )
    p.add_argument(
        "--distill-handoff-json",
        default=None,
        help=(
            "write a provider-free handoff listing ingested document ids ready "
            "for the later note-taker document pass; valid only with --apply"
        ),
    )
    args = p.parse_args(argv)

    events_dir = args.events_dir or os.environ.get(
        "ANTIEK_HERMES_EVENTS_DIR", DEFAULT_HERMES_EVENTS_DIR
    )
    db_path = args.db_path or _default_db_path()
    if args.distill_handoff_json and not args.apply:
        print("ERROR: --distill-handoff-json requires --apply", file=sys.stderr)
        return 2

    print(f"events_dir: {events_dir}")
    print(f"allowed_roots: {', '.join(str(r) for r in default_allowed_roots())}")
    print(f"db_path: {db_path}")
    print(f"mode: {'APPLY' if args.apply else 'DRY-RUN (plan only)'}")
    if args.limit is not None:
        print(f"limit: {args.limit} investigations")

    try:
        event_count, inv_count, ids = plan(events_dir, limit=args.limit)
    except HermesEventsDirError as exc:
        print(f"ERROR: trust boundary: {exc}", file=sys.stderr)
        return 2

    print(f"parsed_events: {event_count}")
    print(f"investigations_in_plan: {inv_count}")
    if ids:
        preview = ids[:10]
        more = f" … (+{len(ids) - 10} more)" if len(ids) > 10 else ""
        print(f"ids: {', '.join(preview)}{more}")

    receipt = _base_receipt(
        events_dir=events_dir,
        db_path=db_path,
        mode="apply" if args.apply else "dry_run",
        limit=args.limit,
        parsed_events=event_count,
        investigation_ids=ids,
    )

    if not args.apply:
        receipt["writes_performed"] = False
        if args.evidence_json:
            _write_evidence(args.evidence_json, receipt)
            print(f"evidence_json: {args.evidence_json}")
        print(
            "\n(dry-run) no writes. Re-run with --apply to ingest into the graph."
        )
        return 0

    if not Path(db_path).exists():
        print(f"ERROR: db not found: {db_path}", file=sys.stderr)
        return 2

    with connect_write(db_path, purpose=DEFAULT_PURPOSE) as con:
        batch = ingest_hermes_events(
            con,
            events_dir,
            limit=args.limit,
        )

    print("\n== ingest_hermes [APPLY] ==")
    print(
        f"new={batch.new_count} cache={batch.cache_hit_count} "
        f"skip={batch.skipped_count} err={batch.error_count} "
        f"malformed={batch.malformed_lines} results={len(batch.results)}"
    )
    receipt.update(
        {
            "writes_performed": True,
            "new": batch.new_count,
            "cache": batch.cache_hit_count,
            "skip": batch.skipped_count,
            "err": batch.error_count,
            "malformed": batch.malformed_lines,
            "results": [
                {
                    "investigation_id": result.investigation_id,
                    "document_id": result.document_id,
                    "status": result.status,
                    "events_count": result.events_count,
                    "was_new": result.was_new,
                    "source_label": result.source_label,
                    "document_type": result.document_type,
                    "error": result.error_message,
                }
                for result in batch.results
            ],
        }
    )
    if args.evidence_json:
        _write_evidence(args.evidence_json, receipt)
        print(f"evidence_json: {args.evidence_json}")
    if args.distill_handoff_json:
        _write_evidence(
            args.distill_handoff_json,
            _distill_handoff_receipt(
                db_path=db_path,
                results=receipt["results"],
            ),
        )
        print(f"distill_handoff_json: {args.distill_handoff_json}")
    for result in batch.results:
        if result.status == "error":
            print(
                f"  ERR {result.investigation_id}: {result.error_message}",
                file=sys.stderr,
            )
    return 1 if batch.error_count else 0


if __name__ == "__main__":
    sys.exit(main())
