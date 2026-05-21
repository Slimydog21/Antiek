"""Opt-in consent gate for the Tier-1 behavior store (SPR-01 M4).

Default-off. Writes to ``behavior_events`` require an active consent
row for ``user_id``. The emit API returns success either way; consent
absence yields a silent no-op (Wave 2 surfaces must never crash
because consent is absent — surfacing that as an error would couple
the UX to the policy regime).

Policy posture (locked 2026-05-21, see ``substrate/behavior/PRIVACY.md``):
- Granting writes a row with ``granted_at`` set, ``revoked_at`` NULL.
- Revoking writes ``revoked_at`` on the latest row; future emits
  become no-ops.
- Existing ``behavior_events`` rows are NOT deleted on revoke.
  ``user_behavior_consent`` carries the immutable audit log; the
  application of "delete future events on opt-out" is a downstream
  cron concern (Sprint 22), not a SPR-01 substrate concern.
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import duckdb

try:
    from ..constants import DUCKDB_PATH
    from ...runtime.db_lock import connect_write
    from .schema import default_db_path
    from .taxonomy import BEHAVIOR_TAXONOMY_VERSION
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_write  # type: ignore[no-redef]
    from substrate.constants import DUCKDB_PATH  # type: ignore[no-redef]
    from substrate.behavior.schema import default_db_path  # type: ignore[no-redef]
    from substrate.behavior.taxonomy import BEHAVIOR_TAXONOMY_VERSION  # type: ignore[no-redef]


def _connect_for_read(db_path: str) -> "duckdb.DuckDBPyConnection":
    """Open a non-read-only connection for a quick consent check.

    DuckDB does not allow mixing read-only and read-write
    connections to the same file within a single process (it
    raises "different configuration than existing connections").
    The behavior store has an in-process write worker, so the
    consent gate uses a read-write connection but only runs
    SELECTs. The flock coordinator is BYPASSED here — we are
    not mutating anything, and the consent check is on a 1ms
    hot path that should not serialize behind the write queue."""
    return duckdb.connect(db_path)


# Current consent version — bump when the consent text changes (the
# user must re-consent). Tied to taxonomy version for now so the
# behaviour-store substrate has exactly one knob to bump.
CURRENT_CONSENT_VERSION: int = BEHAVIOR_TAXONOMY_VERSION


@dataclass(frozen=True)
class ConsentState:
    """The active-consent verdict for one user at one point in time."""

    user_id: str
    granted: bool
    consent_version: Optional[int]
    granted_at: Optional[datetime]
    revoked_at: Optional[datetime]

    @property
    def is_active(self) -> bool:
        """True iff a current grant exists and has not been revoked."""
        return self.granted and self.revoked_at is None


def _new_consent_id() -> str:
    return f"consent-{uuid.uuid4().hex[:16]}"


def grant_consent(
    user_id: str,
    *,
    db_path: Optional[str] = None,
    consent_version: int = CURRENT_CONSENT_VERSION,
) -> str:
    """Record that ``user_id`` has opted in to behavior-event collection.

    Returns the consent_id of the new row.

    Re-granting after a prior revoke is allowed (it inserts a fresh
    row); ``is_consent_active`` always inspects the most recent row.
    """
    path = db_path or default_db_path()
    consent_id = _new_consent_id()
    con = connect_write(path, purpose="behavior_grant_consent")
    try:
        con.execute(
            "INSERT INTO user_behavior_consent "
            "(consent_id, user_id, granted_at, revoked_at, consent_version) "
            "VALUES (?, ?, CURRENT_TIMESTAMP, NULL, ?)",
            [consent_id, user_id, consent_version],
        )
    finally:
        con.close()
    return consent_id


def revoke_consent(
    user_id: str,
    *,
    db_path: Optional[str] = None,
) -> int:
    """Revoke the most-recent active consent row(s) for ``user_id``.

    Returns the number of rows revoked (0 if no active consent
    existed). Re-running after revoke is a no-op.

    Privacy note: this does NOT delete any ``behavior_events`` rows
    — the locked policy (2026-05-21) is "delete future events on
    opt-out; trained models persist". See ``PRIVACY.md``.
    """
    path = db_path or default_db_path()
    con = connect_write(path, purpose="behavior_revoke_consent")
    try:
        result = con.execute(
            "UPDATE user_behavior_consent "
            "SET revoked_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ? AND revoked_at IS NULL",
            [user_id],
        )
        # DuckDB's execute returns a relation; rowcount is on the
        # underlying connection.
        try:
            count = int(con._con.rowcount or 0)  # type: ignore[attr-defined]
        except Exception:
            # Fall back to a quick re-count if rowcount isn't exposed.
            count = int(
                con.execute(
                    "SELECT COUNT(*) FROM user_behavior_consent "
                    "WHERE user_id = ? AND revoked_at IS NOT NULL "
                    "  AND revoked_at >= CURRENT_TIMESTAMP - INTERVAL 5 SECOND",
                    [user_id],
                ).fetchone()[0]
            )
        _ = result
        return count
    finally:
        con.close()


def is_consent_active(
    user_id: str,
    *,
    db_path: Optional[str] = None,
) -> bool:
    """Hot-path predicate: does ``user_id`` currently consent?

    Read-only. Called once per emit, so it's a single indexed query.
    """
    path = db_path or default_db_path()
    con = _connect_for_read(path)
    try:
        row = con.execute(
            "SELECT COUNT(*) "
            "FROM user_behavior_consent "
            "WHERE user_id = ? AND revoked_at IS NULL",
            [user_id],
        ).fetchone()
    finally:
        con.close()
    return bool(row and row[0] > 0)


def get_consent_state(
    user_id: str,
    *,
    db_path: Optional[str] = None,
) -> ConsentState:
    """Read the latest consent row (or a never-granted sentinel)."""
    path = db_path or default_db_path()
    con = _connect_for_read(path)
    try:
        row = con.execute(
            "SELECT consent_version, granted_at, revoked_at "
            "FROM user_behavior_consent "
            "WHERE user_id = ? "
            "ORDER BY granted_at DESC "
            "LIMIT 1",
            [user_id],
        ).fetchone()
    finally:
        con.close()
    if not row:
        return ConsentState(
            user_id=user_id,
            granted=False,
            consent_version=None,
            granted_at=None,
            revoked_at=None,
        )
    consent_version, granted_at, revoked_at = row
    return ConsentState(
        user_id=user_id,
        granted=True,
        consent_version=consent_version,
        granted_at=granted_at,
        revoked_at=revoked_at,
    )


def active_consent_version(
    user_id: str,
    *,
    db_path: Optional[str] = None,
) -> Optional[int]:
    """Return the ``consent_version`` to stamp on emitted events for
    ``user_id``, or ``None`` if no active consent exists. The emit
    API uses this to populate the ``consent_version`` column."""
    state = get_consent_state(user_id=user_id, db_path=db_path)
    return state.consent_version if state.is_active else None


__all__ = [
    "CURRENT_CONSENT_VERSION",
    "ConsentState",
    "active_consent_version",
    "get_consent_state",
    "grant_consent",
    "is_consent_active",
    "revoke_consent",
]
