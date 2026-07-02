"""Mode A draft-export ledger for Deep Research Bridge dogfood evidence."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

try:
    from ...runtime.db_lock import LockedConnection
    from ..graph.ops import new_random_id
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    from substrate.graph.ops import new_random_id  # type: ignore[no-redef]


@dataclass(frozen=True)
class DraftExportRecord:
    export_id: str
    session_id: str
    deliverable_id: str
    output_path: str
    exported_at: str


def _clean_required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} must be non-empty")
    return cleaned


def record_draft_export(
    con: LockedConnection,
    *,
    session_id: str,
    deliverable_id: str,
    output_path: str,
) -> str:
    if not isinstance(con, LockedConnection):
        raise TypeError("record_draft_export requires a LockedConnection")
    session_id = _clean_required(session_id, "session_id")
    deliverable_id = _clean_required(deliverable_id, "deliverable_id")
    output_path = _clean_required(output_path, "output_path")

    exists = con.execute(
        "SELECT 1 FROM deliverables WHERE deliverable_id = ? LIMIT 1",
        [deliverable_id],
    ).fetchone()
    if exists is None:
        raise ValueError(f"deliverable_id {deliverable_id!r} does not exist")

    export_id = new_random_id("rdexp")
    con.execute(
        "INSERT INTO research_draft_exports "
        "(export_id, session_id, deliverable_id, output_path) VALUES (?, ?, ?, ?)",
        [export_id, session_id, deliverable_id, output_path],
    )
    return export_id


def list_draft_exports(
    con: Any,
    *,
    session_id: str | None = None,
    limit: int = 50,
) -> tuple[DraftExportRecord, ...]:
    if session_id is None:
        rows = con.execute(
            "SELECT export_id, session_id, deliverable_id, output_path, exported_at "
            "FROM research_draft_exports ORDER BY exported_at DESC, export_id DESC "
            "LIMIT ?",
            [int(limit)],
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT export_id, session_id, deliverable_id, output_path, exported_at "
            "FROM research_draft_exports WHERE session_id = ? "
            "ORDER BY exported_at DESC, export_id DESC LIMIT ?",
            [session_id, int(limit)],
        ).fetchall()
    return tuple(
        DraftExportRecord(
            export_id=str(r[0]),
            session_id=str(r[1]),
            deliverable_id=str(r[2]),
            output_path=str(r[3]),
            exported_at=str(r[4]),
        )
        for r in rows
    )
