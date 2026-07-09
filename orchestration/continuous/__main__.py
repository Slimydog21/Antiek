"""CLI entry point for the continuous-research daemon.

Invoked by the systemd unit
``infrastructure/ansible/templates/antiek-continuous-research.service.j2``
as ``python -m orchestration.continuous``. Reads config from env
and runs forever; one-shot mode available via ``--once`` for
smoke-tests.

Config (env-only — systemd unit reads /etc/antiek/secrets.env):
- ``ANTIEK_DAEMON_SLEEP_SECONDS`` — scan interval (default 60).
- ``ANTIEK_DAEMON_EXPECTED_COST_USD`` — cost-per-spawn estimate
  used for budget gating (default 0.50).
- ``ANTIEK_DAEMON_BUDGET_USD_PER_DAY`` — §16 hard cap on total
  spawn spend per UTC day (default 5.0).
- ``ANTIEK_DAEMON_SPAWN_MODE`` — ``noop``/``dry_run`` by default;
  ``event_log`` writes daemon-policy start events without calling providers.
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m orchestration.continuous",
        description=(
            "Continuous-research daemon (master-spec §7.3 + §7.4). "
            "Scans the trajectory log for unresolved evidentiary "
            "gaps and spawns follow-on investigations within the "
            "§16 budget cap."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Run a single tick and exit, for smoke-testing. Default "
            "is run forever."
        ),
    )
    args = parser.parse_args()

    # Defer the daemon import so a `--help` invocation doesn't pay
    # the cost of bringing in the substrate module graph.
    from orchestration.continuous.budget import DaemonBudget
    from orchestration.continuous.daemon import (
        DaemonConfig,
        DaemonState,
        run_forever,
        run_one_iteration,
    )
    from orchestration.continuous.spawn import spawn_fn_from_env

    config = DaemonConfig(
        sleep_seconds=float(os.environ.get("ANTIEK_DAEMON_SLEEP_SECONDS", "60")),
        expected_cost_per_spawn_usd=float(
            os.environ.get("ANTIEK_DAEMON_EXPECTED_COST_USD", "0.50")
        ),
    )
    spawn_fn = spawn_fn_from_env()

    if args.once:
        run_one_iteration(
            state=DaemonState(),
            config=config,
            budget=DaemonBudget.from_env(),
            spawn_fn=spawn_fn,
        )
        return 0
    run_forever(config=config, spawn_fn=spawn_fn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
