"""Persistent Loop 3 unlock-checklist store (master-spec §13.7 + §14.2).

The operator updates the 5 criteria over time as substrate matures.
The Trust Center publishes the current state; the unlock-env gate
remains authoritative (criteria-met ≠ training-authorized — the env
flip is the operator's final action).

Storage: the substrate's existing DuckDB graph file gets a new
``loop_3_checklist`` table (CREATE IF NOT EXISTS); one row per
criterion. The store is single-writer per the canonical
``LockedConnection`` discipline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .unlock_gate import Loop3UnlockCriterion, UnlockChecklist


@dataclass(frozen=True)
class ChecklistSnapshot:
    """Read-only view of the current checklist + environment state.

    ``env_unlocked`` is the authoritative ANTIEK_LOOP3_UNLOCKED=1
    check; ``all_criteria_met`` reflects the substrate state alone.
    Both must be True for training-time work to run.
    """

    criteria: dict[str, bool]
    notes: dict[str, str]
    all_criteria_met: bool
    env_unlocked: bool
    fully_unlocked: bool


def ensure_table(con: Any) -> None:
    """Defensive CREATE-IF-NOT-EXISTS. The canonical table lives in
    ``substrate/graph/schema.py`` and is created by ``init_database``
    at boot, so this call should be a no-op on a fully-initialized
    DB. For read-only connections (``connect_read``), DuckDB will
    refuse the DDL; the loader catches the error and assumes the
    table is already present."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS loop_3_checklist (
                criterion  TEXT PRIMARY KEY,
                met        BOOLEAN NOT NULL DEFAULT FALSE,
                note       TEXT,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception:
        # Read-only connections, attached databases, etc. The canonical
        # schema bootstrap covers this on the first write path.
        pass


def set_criterion(
    con: Any,
    *,
    criterion: Loop3UnlockCriterion,
    met: bool,
    note: str = "",
) -> None:
    """Update one criterion's state. The note rides as audit context —
    Trust Center renders it verbatim.

    DuckDB's ON CONFLICT DO UPDATE syntax doesn't expand named bindings
    inside EXCLUDED.<col> the way Postgres does in our test setup, so
    we do an explicit check-and-update / insert pair under the
    LockedConnection's write lock."""
    ensure_table(con)
    exists = con.execute(
        "SELECT 1 FROM loop_3_checklist WHERE criterion = ?",
        [criterion.value],
    ).fetchone()
    if exists is None:
        con.execute(
            """
            INSERT INTO loop_3_checklist (criterion, met, note, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [criterion.value, met, note],
        )
    else:
        con.execute(
            """
            UPDATE loop_3_checklist
            SET met = ?, note = ?, updated_at = CURRENT_TIMESTAMP
            WHERE criterion = ?
            """,
            [met, note, criterion.value],
        )


def load_checklist(con: Any) -> UnlockChecklist:
    """Hydrate the current checklist state from DuckDB. Missing rows
    default to ``met=False`` — substrate refuses to assume progress."""
    ensure_table(con)
    rows = con.execute(
        "SELECT criterion, met, note FROM loop_3_checklist"
    ).fetchall()
    by_criterion: dict[str, bool] = {}
    notes: dict[str, str] = {}
    for r in rows:
        by_criterion[r[0]] = bool(r[1])
        if r[2]:
            notes[r[0]] = r[2]

    return UnlockChecklist(
        trajectory_volume=by_criterion.get(
            Loop3UnlockCriterion.TRAJECTORY_VOLUME.value, False,
        ),
        sft_readiness=by_criterion.get(
            Loop3UnlockCriterion.SFT_READINESS.value, False,
        ),
        validated_reward=by_criterion.get(
            Loop3UnlockCriterion.VALIDATED_REWARD.value, False,
        ),
        open_weight_justification=by_criterion.get(
            Loop3UnlockCriterion.OPEN_WEIGHT_JUSTIFICATION.value, False,
        ),
        eval_headroom=by_criterion.get(
            Loop3UnlockCriterion.EVAL_HEADROOM.value, False,
        ),
        notes=notes,
    )


def snapshot(con: Any) -> ChecklistSnapshot:
    """Materialize a full snapshot of the unlock state — DB checklist
    + environment-variable gate."""
    checklist = load_checklist(con)
    env_unlocked = os.environ.get("ANTIEK_LOOP3_UNLOCKED", "") == "1"
    criteria_dict = {
        Loop3UnlockCriterion.TRAJECTORY_VOLUME.value: checklist.trajectory_volume,
        Loop3UnlockCriterion.SFT_READINESS.value: checklist.sft_readiness,
        Loop3UnlockCriterion.VALIDATED_REWARD.value: checklist.validated_reward,
        Loop3UnlockCriterion.OPEN_WEIGHT_JUSTIFICATION.value: (
            checklist.open_weight_justification
        ),
        Loop3UnlockCriterion.EVAL_HEADROOM.value: checklist.eval_headroom,
    }
    all_met = checklist.all_met()
    return ChecklistSnapshot(
        criteria=criteria_dict,
        notes=dict(checklist.notes),
        all_criteria_met=all_met,
        env_unlocked=env_unlocked,
        fully_unlocked=all_met and env_unlocked,
    )


__all__ = [
    "ChecklistSnapshot",
    "ensure_table",
    "load_checklist",
    "set_criterion",
    "snapshot",
]
