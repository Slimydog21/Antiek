"""Medium-horizon reward proxy backfill worker (SPR-01 M5, SPR-08 M7).

REAL IMPLEMENTATION as of SPR-08. The medium signal requires Tier-2
notebook references — see ``substrate/behavior/REWARD_PROXY.md``
§"Worker 2".

Pre-SPR-08 this module was a documented stub; SPR-08's per-document
notebook surface populates ``notebook_documents`` + ``notebook_blocks``,
which makes the canonical join real. The body below delegates to
``services.notebooks.reward_hook.run_medium_backfill`` — the
service-layer module that owns the join semantics. This keeps the
SPR-01 worker module thin (it remains the cron's entry point) while
the SPR-08 service owns the SQL and the test surface.

Backwards compatibility
-----------------------
The ``run_reward_medium_backfill`` signature + ``MediumBackfillResult``
return shape are preserved so SPR-01 callers (cron + the e2e
``test_e2e_emit.py``) keep compiling. The status strings now include
``"ran"`` in addition to ``"deferred"`` / ``"empty"``.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

try:
    from ..schema import default_db_path
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(_here))))
    from substrate.behavior.schema import default_db_path  # type: ignore[no-redef]


REQUIRED_TABLES: tuple[str, ...] = ("notebook_documents", "notebook_blocks")
"""Tables this worker joins against. If any are missing, the worker
returns ``status='deferred'`` rather than crashing — keeps cron
logs readable while SPR-08 is still rolling out."""


@dataclass(frozen=True)
class MediumBackfillResult:
    """Diagnostic returned by ``run_reward_medium_backfill``.

    ``status`` values:
      - ``"ran"`` — join executed; ``rows_updated`` may be 0+.
      - ``"empty"`` — notebooks table is empty; nothing to do.
      - ``"deferred"`` — required tables missing (substrate not
        yet migrated).
    """

    status: str
    reason: str
    rows_updated: int = 0


def run_reward_medium_backfill(
    *,
    db_path: Optional[str] = None,
) -> MediumBackfillResult:
    """Single pass over ``behavior_events``.

    Delegates to ``services.notebooks.reward_hook.run_medium_backfill``
    so the join lives next to the schema that defines its inputs.
    The shape this function returns is unchanged from the SPR-01
    stub, so existing callers (cron + e2e tests) don't break.

    Args:
        db_path: DuckDB file. Defaults to substrate constants.

    Returns:
        ``MediumBackfillResult``.
    """
    # Local import keeps the dependency one-way: services.notebooks
    # imports substrate, not the reverse. The module-level import
    # would create a cycle (notebooks.reward_hook ← substrate.behavior
    # at import time).
    try:
        from services.notebooks.reward_hook import (
            BackfillResult,
            run_medium_backfill,
        )
    except ImportError:  # pragma: no cover — services not on path
        path_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        if path_root not in sys.path:
            sys.path.insert(0, path_root)
        from services.notebooks.reward_hook import (  # type: ignore[no-redef]
            BackfillResult,
            run_medium_backfill,
        )

    path = db_path or default_db_path()
    result: BackfillResult = run_medium_backfill(db_path=path)

    status_map = {
        "ran": "ran",
        "skipped_no_notebooks": "empty",
        "skipped_tables_missing": "deferred",
    }
    return MediumBackfillResult(
        status=status_map.get(result.status, "deferred"),
        reason=result.reason,
        rows_updated=int(result.rows_updated),
    )


__all__ = ["MediumBackfillResult", "REQUIRED_TABLES", "run_reward_medium_backfill"]
