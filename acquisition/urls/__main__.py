"""CLI entry for the Paul Graham essay driver.

``python -m acquisition.urls discover [--articles-file PATH]``
``python -m acquisition.urls run --investigation-id ID [--db-path PATH] ...``

This routes to ``acquisition.urls.paulgraham._main`` so the operator can drive
discovery + personal_reading ingestion without importing the module by hand. No
new package; this is the one PG-specific driver living INSIDE acquisition/urls/.
"""
from __future__ import annotations

import sys

from acquisition.urls.paulgraham import _main

if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
