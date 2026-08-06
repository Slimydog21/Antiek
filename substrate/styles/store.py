"""Per-user forked-style store — the style wheel's persistence layer (S2).

One small DuckDB table, ``user_styles``, keyed by ``(user_id, name)`` —
the style slug is the stable URL/persistence id (``styles.ProjectionStyle``
validates it before anything is stored, so the row key is URL-safe by
construction). The store itself is deliberately dumb: it persists and
recovers ``ProjectionStyle`` records. Validation, builtin-override refusal,
and wheel assembly (builtins + forks layered on top) live in the route
layer / ``StyleRegistry``.

Design points, matching the substrate's house rules:
  - The table is owned by THIS module (``CREATE TABLE IF NOT EXISTS`` on
    the write path; ``ensure_initialized`` in ``substrate/graph`` does not
    know about it). No change to ``substrate/graph/schema.py``.
  - Every write funnels through ``runtime.db_lock`` (the DuckDB
    single-writer invariant, §16). Reads use ``connect_read``.
  - ``created_at`` is stored DATA, not render input: it exists only to give
    the wheel a stable, deterministic fork order (``ORDER BY created_at,
    name`` — the name tiebreak keeps the order total even for forks written
    within the same clock tick). Rendering never reads it; a style's bytes
    are a pure function of the ``ProjectionStyle`` record.
  - Replacing an existing fork (``INSERT ... ON CONFLICT DO UPDATE``)
    preserves the original row's creation order — the wheel does not jump
    a fork around because its owner edited it.
"""

from __future__ import annotations

import logging

from runtime.db_lock import FlockWriteCoordinator, connect_read
from services.html_projection.styles import ProjectionStyle

_log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS user_styles (
  user_id         VARCHAR NOT NULL,
  name            VARCHAR NOT NULL,
  label           VARCHAR NOT NULL,
  description     VARCHAR NOT NULL DEFAULT '',
  theme_css       VARCHAR NOT NULL DEFAULT '',
  source_fidelity BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, name)
)
"""

_SELECT_COLS = "name, label, description, theme_css, source_fidelity"


class UserStyleStore:
    """Persist and recover per-user forked ``ProjectionStyle`` records.

    Instances are cheap and stateless; create one per request (or reuse a
    module-level singleton) with the resolved DB path.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # ── writes (through the db_lock single writer) ──────────────────────

    def save(self, user_id: str, style: ProjectionStyle) -> ProjectionStyle:
        """Insert (or replace) a fork for ``user_id``. Returns the style.

        ``style`` is persisted as-is; the caller (route layer) has already
        run ``validate_style`` and refused builtin-name collisions. The
        created_at of an existing row is preserved on replace, so editing
        a fork never reorders the wheel.
        """
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("styles.store") as ctx:
            ctx.execute(_DDL)
            ctx.execute(
                "INSERT INTO user_styles "
                "(user_id, name, label, description, theme_css, source_fidelity) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (user_id, name) DO UPDATE SET "
                "label = excluded.label, description = excluded.description, "
                "theme_css = excluded.theme_css, "
                "source_fidelity = excluded.source_fidelity",
                [
                    user_id,
                    style.name,
                    style.label,
                    style.description,
                    style.theme_css,
                    style.source_fidelity,
                ],
            )
        return style

    def delete(self, user_id: str, name: str) -> bool:
        """Remove a fork. Returns True if a row was removed, False if the
        (user, name) pair had nothing stored (idempotent delete).

        The existence probe happens inside the same write transaction, so
        check-then-delete is race-free under the db_lock single writer.
        """
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("styles.store") as ctx:
            ctx.execute(_DDL)
            existed = ctx.execute(
                "SELECT 1 FROM user_styles WHERE user_id = ? AND name = ?",
                [user_id, name],
            ).fetchone()
            if existed is None:
                return False
            ctx.execute(
                "DELETE FROM user_styles WHERE user_id = ? AND name = ?",
                [user_id, name],
            )
            return True

    # ── reads ───────────────────────────────────────────────────────────

    def list_for_user(self, user_id: str) -> list[ProjectionStyle]:
        """All forks for ``user_id`` in deterministic creation order.

        An absent table is treated as an empty wheel (no fork was ever
        written for this DB) rather than an error.
        """
        con = connect_read(self._db_path)
        try:
            try:
                rows = con.execute(
                    f"SELECT {_SELECT_COLS} FROM user_styles "
                    "WHERE user_id = ? ORDER BY created_at, name",
                    [user_id],
                ).fetchall()
            except Exception as exc:  # noqa: BLE001 — missing table == no forks
                if "does not exist" in str(exc):
                    return []
                raise
            return [
                ProjectionStyle(
                    name=str(r[0]),
                    label=str(r[1]),
                    description=str(r[2]),
                    theme_css=str(r[3]),
                    source_fidelity=bool(r[4]),
                    builtin=False,
                )
                for r in rows
            ]
        finally:
            con.close()


__all__ = ["UserStyleStore"]
