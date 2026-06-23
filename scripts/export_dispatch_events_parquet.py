#!/usr/bin/env python3
"""Export dispatch.call rows from investigation jsonl/parquet → dispatch_calls.parquet.

Feeds ``analytics.duckdb`` (Engine / Agents cost joins). Does not open
``antiek.duckdb``.

  ./.venv/bin/python scripts/export_dispatch_events_parquet.py \\
    --out ~/.antiek/exports/parquet/20260101/dispatch_calls.parquet

Optional: ``--events-dir`` (else ``ANTIEK_RESEARCH_EVENTS_DIR`` / default).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import duckdb  # analytics script allowlist — not OLTP funnel  # noqa: E402

_DISPATCH_DDL = """
CREATE TABLE dispatch_calls (
    event_id VARCHAR,
    investigation_id VARCHAR,
    synthesis_id VARCHAR,
    phase VARCHAR,
    role VARCHAR,
    policy_id VARCHAR,
    param_version VARCHAR,
    emitted_at VARCHAR,
    workflow VARCHAR,
    target_role VARCHAR,
    provider VARCHAR,
    model VARCHAR,
    tier VARCHAR,
    input_tokens BIGINT,
    output_tokens BIGINT,
    cost_usd DOUBLE,
    latency_ms BIGINT,
    is_remote_exec BOOLEAN,
    context_pack_event_id VARCHAR
)
"""


def _resolve_events_dir(arg: str | None) -> str:
    if arg:
        return os.path.expanduser(arg)
    return os.environ.get(
        "ANTIEK_RESEARCH_EVENTS_DIR",
        os.path.join(
            os.path.expanduser(os.environ.get("ANTIEK_HOME", "~/.antiek")),
            "research_events",
        ),
    )


def export_dispatch_parquet(events_dir: str, out_path: Path) -> dict:
    from substrate.analytics.dispatch_rows import iter_dispatch_call_rows
    from substrate.constants import ANTIEK_PARAM_VERSION

    rows = list(iter_dispatch_call_rows(events_dir=events_dir))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    staging = out_path.parent / "_dispatch_export.ndjson"
    try:
        con.execute(_DISPATCH_DDL)
        if rows:
            staging.write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            con.execute(
                "INSERT INTO dispatch_calls BY NAME "
                "SELECT * FROM read_json_auto(?)",
                [staging.as_posix()],
            )
        con.execute(
            f"COPY dispatch_calls TO '{out_path.as_posix()}' (FORMAT PARQUET)"
        )
    finally:
        staging.unlink(missing_ok=True)
        con.close()

    manifest = {
        "exported_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "antiek_param_version": ANTIEK_PARAM_VERSION,
        "source_events_dir": events_dir,
        "artifact": out_path.name,
        "layer": "engine",
        "action_type": "dispatch.call",
        "row_count": len(rows),
    }
    sidecar = out_path.with_suffix(".manifest.json")
    sidecar.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-dir", default=None)
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output Parquet path (e.g. .../parquet/DATE/dispatch_calls.parquet)",
    )
    args = parser.parse_args()
    events_dir = _resolve_events_dir(args.events_dir)
    manifest = export_dispatch_parquet(events_dir, args.out.resolve())
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()