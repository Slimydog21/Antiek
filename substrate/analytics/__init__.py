"""Analytics-plane helpers — jsonl → Parquet projections (not OLTP graph).

Import submodules directly to avoid pulling coordination/contracts on lightweight imports.
"""

__all__ = [
    "agent_write_purposes",
    "corpuscrawl_snapshot",
    "dispatch_rows",
]