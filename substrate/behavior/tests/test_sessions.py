"""Tests for the derived last_session_at view."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import duckdb
import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


@pytest.fixture()
def db_path(tmp_path):
    p = str(tmp_path / "behavior.duckdb")
    from substrate.behavior.schema import init_behavior_schema_at_path  # noqa: WPS433
    init_behavior_schema_at_path(p)
    return p


def _insert_event(db_path: str, user_id: str, ts: datetime) -> None:
    with duckdb.connect(db_path) as con:
        con.execute(
            "INSERT INTO behavior_events "
            "(event_id, user_id, session_id, event_type, "
            " timestamp_utc, state, action, consent_version) "
            "VALUES (?, ?, ?, ?, ?, '{}', '{}', 1)",
            [
                f"evt-{ts.timestamp()}",
                user_id,
                "test-session",
                "document_opened",
                ts,
            ],
        )


def test_no_events_returns_none(db_path):
    from substrate.behavior.sessions import get_last_session_at
    assert get_last_session_at("user-1", db_path=db_path) is None


def test_returns_most_recent(db_path):
    from substrate.behavior.sessions import get_last_session_at
    now = datetime.now(timezone.utc)
    _insert_event(db_path, "user-1", now - timedelta(days=3))
    _insert_event(db_path, "user-1", now - timedelta(hours=2))
    _insert_event(db_path, "user-1", now - timedelta(days=10))
    result = get_last_session_at("user-1", db_path=db_path)
    assert result is not None
    # Within 2 hours of the most recent insert (allowing tz / coercion drift).
    assert abs((now - result).total_seconds()) < 7200


def test_returns_per_user(db_path):
    from substrate.behavior.sessions import get_last_session_at
    now = datetime.now(timezone.utc)
    _insert_event(db_path, "user-A", now - timedelta(days=1))
    _insert_event(db_path, "user-B", now - timedelta(hours=1))
    a = get_last_session_at("user-A", db_path=db_path)
    b = get_last_session_at("user-B", db_path=db_path)
    assert a is not None and b is not None
    assert b > a


def test_is_returning_user(db_path):
    from substrate.behavior.sessions import is_returning_user
    now = datetime.now(timezone.utc)
    # No events → not returning.
    assert is_returning_user("user-X", db_path=db_path) is False
    # Event 3 seconds ago → not returning (below threshold).
    _insert_event(db_path, "user-X", now - timedelta(seconds=3))
    assert is_returning_user("user-X", db_path=db_path, threshold_days=1) is False
    # Event 2 days ago → returning.
    _insert_event(db_path, "user-X", now - timedelta(days=2))
    assert is_returning_user("user-X", db_path=db_path, threshold_days=1) is True
