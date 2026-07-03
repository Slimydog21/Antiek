"""Reconcile operator dogfood log sessions with bridge substrate rows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.db_lock import connect_read

from .dogfood_log import DogfoodProjectEntry, validate_dogfood_log


@dataclass(frozen=True)
class DogfoodSessionEvidence:
    project_name: str
    session_id: str
    blocks_pasted: int
    gap_runs: int
    draft_exports: int
    prompt_signals: int

    @property
    def has_substrate_evidence(self) -> bool:
        return any((
            self.blocks_pasted,
            self.gap_runs,
            self.draft_exports,
            self.prompt_signals,
        ))


@dataclass(frozen=True)
class DogfoodSessionReconciliation:
    operator_log_path: Path
    sessions: tuple[DogfoodSessionEvidence, ...]
    missing_requirements: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_requirements


def _count_for_session(con: Any, sql: str, session_id: str) -> int:
    row = con.execute(sql, [session_id]).fetchone()
    return int(row[0]) if row else 0


def _session_evidence(con: Any, entry: DogfoodProjectEntry) -> DogfoodSessionEvidence:
    blocks = _count_for_session(
        con,
        """
        SELECT COUNT(*)
        FROM research_pastes
        WHERE session_id = ?
        """,
        entry.session_id,
    )
    gap_runs = _count_for_session(
        con,
        """
        SELECT COUNT(*)
        FROM research_gap_runs
        WHERE session_id = ?
        """,
        entry.session_id,
    )
    draft_exports = _count_for_session(
        con,
        """
        SELECT COUNT(*)
        FROM research_draft_exports
        WHERE session_id = ?
        """,
        entry.session_id,
    )
    prompt_signals = _count_for_session(
        con,
        """
        SELECT COUNT(*)
        FROM research_gap_prompt_signals s
        JOIN research_gap_prompts p ON p.prompt_id = s.prompt_id
        JOIN research_gap_runs r ON r.run_id = p.run_id
        WHERE r.session_id = ?
        """,
        entry.session_id,
    )
    return DogfoodSessionEvidence(
        project_name=entry.project_name,
        session_id=entry.session_id,
        blocks_pasted=blocks,
        gap_runs=gap_runs,
        draft_exports=draft_exports,
        prompt_signals=prompt_signals,
    )


def reconcile_dogfood_sessions(
    con: Any,
    *,
    root: str | Path | None = None,
) -> DogfoodSessionReconciliation:
    log_validation = validate_dogfood_log(root)
    missing = list(log_validation.missing_requirements)
    sessions = tuple(_session_evidence(con, entry) for entry in log_validation.project_entries)
    for row in sessions:
        if row.blocks_pasted == 0:
            missing.append(
                f"{row.project_name}: session {row.session_id} has no pasted research block"
            )
        if not row.has_substrate_evidence:
            missing.append(
                f"{row.project_name}: session {row.session_id} has no substrate evidence"
            )
    return DogfoodSessionReconciliation(
        operator_log_path=log_validation.operator_log_path,
        sessions=sessions,
        missing_requirements=tuple(missing),
    )


def reconcile_dogfood_sessions_from_db_path(
    db_path: str,
    *,
    root: str | Path | None = None,
) -> DogfoodSessionReconciliation:
    con = connect_read(db_path)
    try:
        return reconcile_dogfood_sessions(con, root=root)
    finally:
        con.close()
