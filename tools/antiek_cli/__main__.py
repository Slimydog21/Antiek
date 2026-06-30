"""Allow ``python -m tools.antiek_cli check <subcommand>``.

The original package entry point also accepted
``python -m tools.antiek_cli <subcommand>`` directly. Keep that shorthand as a
compatibility alias, but make the documented ``check`` namespace work.
"""

from __future__ import annotations

import sys

from tools.antiek_cli.check import main as check_main


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "check":
        args = args[1:]
    return check_main(args)

if __name__ == "__main__":
    sys.exit(main())
