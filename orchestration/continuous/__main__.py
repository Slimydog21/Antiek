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
- ``ANTIEK_DAEMON_SPAWN_MODE`` — ``no_op`` (default) or ``loop_one``
  to emit Loop One start events (Sprint-14 attach).
"""

from __future__ import annotations

import argparse
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
        DaemonState,
        run_forever,
    )
    from orchestration.continuous.loop_one_spawn import resolve_daemon_spawn_fn
    from orchestration.continuous.spawn_cost import (
        daemon_config_from_env,
        run_one_iteration_settled,
    )

    # Same env-built config as daemon.main() — must not use bare DaemonConfig()
    # defaults (would ignore ANTIEK_DAEMON_SLEEP_SECONDS / EXPECTED_COST_USD).
    cfg = daemon_config_from_env()
    bdg = DaemonBudget.from_env()
    # Sprint-14: ANTIEK_DAEMON_SPAWN_MODE=loop_one emits start events;
    # default remains no_op. Settled-cost wrap applied inside resolve when
    # loop_one is selected.
    spawn_fn = resolve_daemon_spawn_fn(
        events_dir=cfg.events_dir,
        budget=bdg,
    )

    if args.once:
        # Production one-shot path always installs settled-cost hooks
        # (tripwire-safe: daemon.py untouched).
        run_one_iteration_settled(
            state=DaemonState(),
            config=cfg,
            budget=bdg,
            spawn_fn=spawn_fn,
        )
        return 0
    # Forever path: env-built config + resolved spawn (no_op or loop_one).
    run_forever(
        config=cfg,
        budget=bdg,
        spawn_fn=spawn_fn,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
