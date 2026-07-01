"""Operator CLI for the deletion worker.

Runs one scheduler-safe deletion cycle:

    python -m substrate.deletion_worker
    python -m substrate.deletion_worker --db /path/to/antiek.duckdb

Output is JSON Lines: one object per loaded request, or one cycle-scoped
failure object if setup fails before requests can be loaded. A cycle with no
processable rows prints nothing and exits 0. Any failed request exits 1 so a
systemd timer or operator shell can alert on it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

from .db import run_db_cycle_at_path
from .worker import DeletionResult, DeletionResultKind
from substrate.telemetry_preferences import SqlitePreferenceStore


def _parse_now(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _resolve_db_path(override: str | None) -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = str(Path(override).expanduser()) if override else default_db_path()
    ensure_initialized(path)
    return path


def _resolve_preference_store(
    *,
    db_override: str | None,
    preference_override: str | None,
):
    if preference_override:
        return SqlitePreferenceStore(str(Path(preference_override).expanduser()))
    env_override = os.environ.get("ANTIEK_TELEMETRY_PREFERENCES_PATH", "").strip()
    if db_override and env_override:
        raise ValueError(
            "--db was provided while ANTIEK_TELEMETRY_PREFERENCES_PATH is set; "
            "pass --telemetry-preferences explicitly or unset the env override"
        )
    return None


def _result_payload(result: DeletionResult) -> dict:
    payload = {
        "request_id": result.request_id,
        "user_id": result.user_id,
        "kind": result.kind.value,
        "sla_remaining_days": result.sla_remaining_days,
        "rows_deleted": result.rows_deleted,
    }
    if result.reason:
        payload["reason"] = result.reason
    if result.error:
        payload["error"] = result.error
    return payload


def _write_jsonl(results: list[DeletionResult], out: TextIO) -> None:
    for result in results:
        out.write(json.dumps(_result_payload(result), sort_keys=True) + "\n")


def _write_cycle_failure(error: str, out: TextIO) -> None:
    out.write(json.dumps({
        "error": error,
        "kind": DeletionResultKind.FAILED.value,
        "request_id": None,
        "rows_deleted": {},
        "scope": "cycle",
        "sla_remaining_days": None,
        "user_id": None,
    }, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m substrate.deletion_worker",
        description="Run one Antiek deletion-worker cycle.",
    )
    parser.add_argument(
        "--db",
        help="DuckDB graph path. Defaults to substrate.graph.default_db_path().",
    )
    parser.add_argument(
        "--telemetry-preferences",
        help=(
            "SQLite telemetry-preferences path. When omitted, the shared "
            "substrate resolver uses ANTIEK_TELEMETRY_PREFERENCES_PATH, then "
            "telemetry_preferences.sqlite beside the selected graph DB."
        ),
    )
    parser.add_argument(
        "--now",
        help="ISO timestamp override for deterministic dry runs/tests.",
    )
    return parser


def main(argv: list[str] | None = None, *, out: TextIO | None = None) -> int:
    args = build_parser().parse_args(argv)
    stream = out if out is not None else sys.stdout
    try:
        now = _parse_now(args.now)
        preference_store = _resolve_preference_store(
            db_override=args.db,
            preference_override=args.telemetry_preferences,
        )
        db_path = _resolve_db_path(args.db)
        results = run_db_cycle_at_path(
            db_path,
            now=now,
            preference_store=preference_store,
        )
    except Exception as exc:
        _write_cycle_failure(str(exc), stream)
        return 1
    _write_jsonl(results, stream)
    return 1 if any(r.kind == DeletionResultKind.FAILED for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
