"""Canonical ``write_log.purpose`` values for the Agents layer (duckdb_plane §12).

Do not fork this list — analytics views and operator dashboards import it.
"""

from __future__ import annotations

# Exact purposes emitted by host-side agent / remote-merge writers.
AGENT_WRITE_PURPOSE_EXACT: frozenset[str] = frozenset(
    {
        "promotion_funnel",
        "cascade_merge",
        "merge_staging",
    }
)

# Prefix families (orchestration monitors, CI exercise substrate).
AGENT_WRITE_PURPOSE_PREFIXES: tuple[str, ...] = (
    "monitor_",
    "exercise:",
)


def is_agent_write_purpose(purpose: str) -> bool:
    if purpose in AGENT_WRITE_PURPOSE_EXACT:
        return True
    return any(purpose.startswith(p) for p in AGENT_WRITE_PURPOSE_PREFIXES)


def sql_agent_purpose_predicate(alias: str = "purpose") -> str:
    """SQL WHERE fragment for DuckDB analytics views."""
    exact = ", ".join(f"'{p}'" for p in sorted(AGENT_WRITE_PURPOSE_EXACT))
    prefix = " OR ".join(f"{alias} LIKE '{p}%'" for p in AGENT_WRITE_PURPOSE_PREFIXES)
    return f"({alias} IN ({exact}) OR {prefix})"