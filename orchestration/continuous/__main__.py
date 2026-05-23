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
    from orchestration.continuous.daemon import (
        DaemonConfig,
        DaemonState,
        main as daemon_main,
        run_one_iteration,
    )

    if args.once:
        run_one_iteration(state=DaemonState(), config=DaemonConfig())
        return 0
    daemon_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
