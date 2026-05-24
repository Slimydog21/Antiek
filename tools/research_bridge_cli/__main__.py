"""Entry shim: ``python -m tools.research_bridge_cli``."""

from __future__ import annotations

import sys

from .main import main


if __name__ == "__main__":
    sys.exit(main())
