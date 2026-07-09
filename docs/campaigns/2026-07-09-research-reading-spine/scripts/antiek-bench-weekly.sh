#!/usr/bin/env zsh
# Residual (dr) — weekly Antiek-bench offline dogfood + suite proposal snapshot.
# Operator-gated LaunchAgent / cron entrypoint. Never auto-promotes suite rewrites.
set -euo pipefail

ROOT="${ANTIEK_PLATFORM_ROOT:-}"
if [[ -z "$ROOT" || ! -d "$ROOT" ]]; then
  echo "ANTIEK_PLATFORM_ROOT must point at the Antiek platform checkout" >&2
  exit 2
fi

cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

PY="${ANTIEK_PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

WEEK_ID="${ANTIEK_BENCH_WEEK_ID:-$($PY - <<'PY'
from datetime import date
d = date.today()
print(f"{d.isocalendar().year}-W{d.isocalendar().week:02d}")
PY
)}"

OUT_DIR="${ANTIEK_BENCH_WEEKLY_OUT:-$HOME/.antiek/bench-weekly}"
mkdir -p "$OUT_DIR"
STAMP="$OUT_DIR/${WEEK_ID}"
mkdir -p "$STAMP"
export ANTIEK_BENCH_WEEK_ID="$WEEK_ID"
export ANTIEK_BENCH_STAMP="$STAMP"
export ANTIEK_BENCH_USAGE_DIR="${ANTIEK_BENCH_USAGE_DIR:-$STAMP/usage}"

echo "antiek-bench-weekly · week=$WEEK_ID · root=$ROOT · out=$STAMP"

$PY - <<'PY'
"""Offline weekly dogfood + suite proposal (proposed only)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from substrate.antiek_bench.dogfood_fixtures import register_competitive_dogfood_suite
from substrate.antiek_bench.product_path import run_offline_dogfood_product
from substrate.antiek_bench.settings_surface import settings_suite_proposal_payload
from substrate.antiek_bench.store import FileBenchStore, resolve_usage_store
from substrate.antiek_bench.suite import SuiteRegistry

week = os.environ["ANTIEK_BENCH_WEEK_ID"]
stamp = Path(os.environ["ANTIEK_BENCH_STAMP"])
usage_root = Path(os.environ["ANTIEK_BENCH_USAGE_DIR"])
usage_root.mkdir(parents=True, exist_ok=True)

store = resolve_usage_store(root=usage_root) or FileBenchStore(usage_root)
registry = SuiteRegistry()

# Register dogfood suite; do not make_active unless already empty.
register_competitive_dogfood_suite(registry=registry, make_active=True)

run = run_offline_dogfood_product(
    week_id=week,
    store=store,
    include_html=True,
)
(stamp / "dogfood-run.json").write_text(
    json.dumps(run, indent=2, default=str), encoding="utf-8"
)
print(
    "dogfood_run",
    "auto_promoted=",
    run.get("auto_promoted"),
    "models=",
    len(run.get("runs") or run.get("model_runs") or []),
)

# Suite rewrite proposal from recorded usage — status proposed only.
proposal = settings_suite_proposal_payload(
    store=store, registry=registry, include_html=True
)
(stamp / "suite-proposal.json").write_text(
    json.dumps(proposal, indent=2, default=str), encoding="utf-8"
)
assert proposal.get("auto_promoted") is False, "weekly path must not auto-promote"
assert proposal.get("view_format") == "html"
print(
    "suite_proposal",
    proposal.get("status"),
    proposal.get("proposal_id"),
    "has_proposal=",
    proposal.get("has_proposal"),
    "auto_promoted=",
    proposal.get("auto_promoted"),
)
print("WEEKLY_OK", week)
PY

echo "wrote $STAMP/dogfood-run.json $STAMP/suite-proposal.json"
echo "Operator: review suite-proposal.json; promote only via Settings approve UI."
