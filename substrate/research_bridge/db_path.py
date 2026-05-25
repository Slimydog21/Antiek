"""Path resolution + ensure-initialized for the research bridge."""

from __future__ import annotations

import os
from typing import Optional


def default_db_path() -> str:
    explicit = os.environ.get("ANTIEK_DUCKDB_PATH")
    if explicit:
        return os.path.expanduser(explicit)
    from ..constants import DUCKDB_PATH
    return os.path.expanduser(DUCKDB_PATH)


def ensure_research_bridge_initialized(db_path: Optional[str] = None) -> str:
    from ..graph import ensure_initialized
    from .schema import init_research_bridge_at_path

    resolved = ensure_initialized(db_path)
    init_research_bridge_at_path(resolved)
    return resolved
