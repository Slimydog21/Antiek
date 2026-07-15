"""DuckDB store for canonical HTML projections.

The caller owns the connection. The store never opens a connection or controls
a transaction, so every operation works in autocommit or a caller-owned DuckDB
transaction. A complete projection, including its ordered anchor map, occupies
one JSON row; create and transition are each one atomic INSERT or UPDATE.
"""

from __future__ import annotations

import json
from typing import Any, Final

from substrate.contracts.html_projection import HtmlProjectionContract, ProjectionStatus


class ProjectionConflict(ValueError):
    """Stored state conflicts with the requested identity or transition."""


# Closed graph. Exact replay is separately idempotent. ``failed -> queued`` is
# the sole retry edge and additionally requires cleared derived fields.
TRANSITIONS: Final[dict[ProjectionStatus, frozenset[ProjectionStatus]]] = {
    "queued": frozenset({"extracting"}),
    "extracting": frozenset({"sanitizing", "ocr_required", "failed"}),
    "ocr_required": frozenset({"extracting", "failed"}),
    "sanitizing": frozenset({"review_required", "ready", "failed"}),
    "review_required": frozenset({"sanitizing", "ready", "failed"}),
    "ready": frozenset(),
    "failed": frozenset({"queued"}),
}


class ProjectionStore:
    def __init__(self, connection: Any) -> None:
        self._con = connection

    def ensure_tables(self) -> None:
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS html_projections (
                projection_id TEXT PRIMARY KEY,
                identity_json JSON NOT NULL UNIQUE,
                projection_json JSON NOT NULL
            )
        """)

    def claim(self, projection: HtmlProjectionContract) -> HtmlProjectionContract:
        """Create a queued projection, or idempotently replay an exact row."""
        self.ensure_tables()
        existing = self._find(projection)
        if existing is not None:
            if existing == projection:
                return existing
            raise ProjectionConflict("projection claim conflicts with stored record or identity")
        if projection.status != "queued":
            raise ProjectionConflict("a new projection must be claimed in queued status")
        self._con.execute(
            "INSERT INTO html_projections VALUES (?, ?, ?)",
            [projection.projection_id, _json(projection.identity()), _json(projection.model_dump())],
        )
        return projection

    def transition(self, projection: HtmlProjectionContract) -> HtmlProjectionContract:
        """Apply one guarded edge in :data:`TRANSITIONS`; exact replay is a no-op.

        Identity never changes. Ready records are terminal and wholly immutable.
        A failed record may retry only as a clean queued record with no reason,
        hosted HTML, hash, or anchor mappings.
        """
        self.ensure_tables()
        current = self._find(projection)
        if current is None:
            raise KeyError(projection.projection_id)
        if current == projection:
            return current
        if current.identity() != projection.identity():
            raise ProjectionConflict("canonical identity is immutable")
        if projection.status not in TRANSITIONS[current.status]:
            raise ProjectionConflict(f"invalid projection transition {current.status}->{projection.status}")
        if current.status == "failed" and (
            projection.reason_code is not None
            or projection.hosted_html_locator is not None
            or projection.hosted_html_sha256 is not None
            or projection.anchor_mappings
        ):
            raise ProjectionConflict("failed retry must clear all derived fields")
        result = self._con.execute(
            "UPDATE html_projections SET projection_json = ? "
            "WHERE projection_id = ? AND projection_json = ?",
            [_json(projection.model_dump()), projection.projection_id, _json(current.model_dump())],
        )
        if result.rowcount not in {-1, 1}:
            raise ProjectionConflict("projection changed concurrently")
        stored = self.load(projection.projection_id)
        if stored != projection:
            raise ProjectionConflict("projection changed concurrently")
        return stored

    def load(self, projection_id: str) -> HtmlProjectionContract:
        row = self._con.execute(
            "SELECT projection_json FROM html_projections WHERE projection_id = ?", [projection_id]
        ).fetchone()
        if row is None:
            raise KeyError(projection_id)
        return HtmlProjectionContract.model_validate_json(str(row[0]))

    def list(self) -> tuple[HtmlProjectionContract, ...]:
        rows = self._con.execute(
            "SELECT projection_json FROM html_projections ORDER BY projection_id"
        ).fetchall()
        return tuple(HtmlProjectionContract.model_validate_json(str(row[0])) for row in rows)

    def _find(self, projection: HtmlProjectionContract) -> HtmlProjectionContract | None:
        rows = self._con.execute(
            "SELECT projection_json FROM html_projections "
            "WHERE projection_id = ? OR identity_json = ?",
            [projection.projection_id, _json(projection.identity())],
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise ProjectionConflict("projection id and canonical identity refer to different rows")
        return HtmlProjectionContract.model_validate_json(str(rows[0][0]))


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
