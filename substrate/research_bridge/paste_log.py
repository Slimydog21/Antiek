"""Append-only paste event log helpers."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

try:
    from ...runtime.db_lock import LockedConnection
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection  # type: ignore[no-redef]


@dataclass(frozen=True)
class PasteEvent:
    event_id: str
    document_id: str
    occurred_at: str
    paste_byte_length: int
    raw_sha256: str
    source: str
    call_site: str


def log_paste_event(
    con: LockedConnection,
    *,
    event_id: str,
    document_id: str,
    paste_byte_length: int,
    raw_sha256: str,
    source: str,
    call_site: str = "unknown",
) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            "log_paste_event requires a LockedConnection (got "
            f"{type(con).__name__}). Use runtime.db_lock.connect_write."
        )
    con.execute(
        "INSERT INTO research_paste_events "
        "(event_id, document_id, paste_byte_length, raw_sha256, source, call_site) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [event_id, document_id, int(paste_byte_length), raw_sha256, source, call_site],
    )


def list_paste_events(
    con, *, document_id: Optional[str] = None, limit: int = 100,
) -> list[PasteEvent]:
    if document_id is None:
        rows = con.execute(
            "SELECT event_id, document_id, occurred_at, paste_byte_length, "
            "       raw_sha256, source, call_site "
            "FROM research_paste_events ORDER BY occurred_at DESC LIMIT ?",
            [int(limit)],
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT event_id, document_id, occurred_at, paste_byte_length, "
            "       raw_sha256, source, call_site "
            "FROM research_paste_events WHERE document_id = ? "
            "ORDER BY occurred_at DESC LIMIT ?",
            [document_id, int(limit)],
        ).fetchall()
    return [
        PasteEvent(
            event_id=r[0], document_id=r[1], occurred_at=str(r[2]),
            paste_byte_length=int(r[3]), raw_sha256=r[4],
            source=r[5], call_site=r[6],
        )
        for r in rows
    ]
