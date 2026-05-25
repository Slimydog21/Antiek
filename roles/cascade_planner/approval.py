"""DRW SPR-05 M6 — the approval gate (the glass box).

No plan is launchable until explicitly approved. Approval is recorded both
on the root node's metadata (the source of truth a separate process reads)
and as a ``plan.approved`` event (the audit trail). Editing an approved plan
re-opens the gate — the tree's edit ops bump ``plan_version`` and reset the
state to ``draft`` (see ``tree_contract``), so a re-persist writes the
re-opened state and ``is_plan_launchable`` returns False until re-approval.

SPR-06's launch MUST call ``is_plan_launchable`` (or ``assert_launchable``)
before fanning out. ``plan.approved`` is emitted via ``log_event`` (an
untyped lifecycle event — no new typed payload, so no events.py change and
no codegen bump); ``validate_trajectory`` accepts it (it enforces only that
action_type is present, not a closed vocabulary).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

try:
    from ...runtime.db_lock import connect_read, connect_write
    from ...event_log import log_event
    from ...graph.insight_question import graph_db_path
    from .tree_contract import PlanTree
    from .persist import _json
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_read, connect_write  # type: ignore[no-redef]
    from substrate.event_log import log_event  # type: ignore[no-redef]
    from substrate.graph.insight_question import graph_db_path  # type: ignore[no-redef]
    from roles.cascade_planner.tree_contract import PlanTree  # type: ignore[no-redef]
    from roles.cascade_planner.persist import _json  # type: ignore[no-redef]


class PlanNotApproved(RuntimeError):
    """Raised by assert_launchable when a launch is attempted on an
    unapproved (or edited-since-approval) plan."""


def approve_plan(
    root_node_id: str,
    *,
    approver: str,
    investigation_id: str,
    db_path: Optional[str] = None,
    events_dir: Optional[str] = None,
    con: Any = None,
) -> dict:
    """Approve the plan rooted at ``root_node_id``. Writes approval state to
    the root node metadata and emits ``plan.approved``. Returns the new
    approval dict."""
    owned = con is None
    c = con if con is not None else connect_write(db_path or graph_db_path(), purpose="approve_plan")
    try:
        row = c.execute("SELECT metadata FROM nodes WHERE node_id = ?", [root_node_id]).fetchone()
        if row is None:
            raise PlanNotApproved(f"no plan root node {root_node_id!r}")
        meta = _json(row[0])
        approval = meta.get("approval", {"state": "draft", "plan_version": 1})
        approval["state"] = "approved"
        approval["approved_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        approval["approved_by"] = approver
        meta["approval"] = approval
        c.execute("UPDATE nodes SET metadata = ? WHERE node_id = ?",
                  [json.dumps(meta, default=str), root_node_id])
        log_event(investigation_id, "plan.approved",
                  payload={"root_node_id": root_node_id,
                           "plan_version": approval.get("plan_version", 1),
                           "approved_by": approver},
                  role="user_agent", events_dir=events_dir)
        return approval
    finally:
        if owned:
            c.close()


def load_approval(root_node_id: str, *, db_path: Optional[str] = None, con: Any = None) -> dict:
    owned = con is None
    c = con if con is not None else connect_read(db_path or graph_db_path())
    try:
        row = c.execute("SELECT metadata FROM nodes WHERE node_id = ?", [root_node_id]).fetchone()
        if row is None:
            return {"state": "draft"}
        return _json(row[0]).get("approval", {"state": "draft"})
    finally:
        if owned:
            c.close()


def is_plan_launchable(root_node_id: str, *, db_path: Optional[str] = None, con: Any = None) -> bool:
    """The gate SPR-06 consults. True only when the plan is in the approved
    state (and has not been edited since — edits reset it to draft)."""
    return load_approval(root_node_id, db_path=db_path, con=con).get("state") == "approved"


def assert_launchable(root_node_id: str, *, db_path: Optional[str] = None, con: Any = None) -> None:
    """SPR-06 calls this before fan-out; raises if the plan is not approved."""
    if not is_plan_launchable(root_node_id, db_path=db_path, con=con):
        raise PlanNotApproved(
            f"plan {root_node_id!r} is not approved — the glass-box gate refuses "
            f"launch. Approve the (possibly edited) plan first."
        )
