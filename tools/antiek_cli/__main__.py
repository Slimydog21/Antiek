"""Allow ``python -m tools.antiek_cli <subcommand>``."""

from __future__ import annotations

import sys

from tools.antiek_cli.check import main

if __name__ == "__main__":
    sys.exit(main())
