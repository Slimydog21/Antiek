"""
Tests for acquisition.arxiv.ban_state — the cross-process 429 sentinel.

Closes ``tests/regression/agent_failures/banned-until-sentinel-absent.yaml``
(the load-bearing arxiv fix). Verifies the persistence contract, the
fail-open-on-corrupt read, the never-shorten-an-existing-ban rule, and
atomicity of the write.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e2-harness.html (E2 GAP closure)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from acquisition.arxiv import ban_state


@pytest.fixture
def sentinel(tmp_path: Path, monkeypatch) -> Path:
    p = tmp_path / "arxiv_banned_until.json"
    monkeypatch.setenv("ANTIEK_ARXIV_BAN_SENTINEL", str(p))
    return p


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Empty / absent sentinel — fail-open (not banned)
# ---------------------------------------------------------------------------


def test_not_banned_when_sentinel_absent(sentinel: Path) -> None:
    assert ban_state.is_banned() is False
    assert ban_state.banned_until() is None
    assert ban_state.remaining() is None


def test_fail_open_on_corrupt_sentinel(sentinel: Path) -> None:
    sentinel.write_text("not json at all {{{", encoding="utf-8")
    # Corrupt sentinel must NOT wedge ingestion — treated as not-banned.
    assert ban_state.is_banned() is False
    assert ban_state.banned_until() is None


def test_fail_open_on_missing_field(sentinel: Path) -> None:
    sentinel.write_text(json.dumps({"unrelated": "value"}), encoding="utf-8")
    assert ban_state.is_banned() is False


# ---------------------------------------------------------------------------
# mark_banned / is_banned
# ---------------------------------------------------------------------------


def test_mark_banned_then_is_banned(sentinel: Path) -> None:
    expiry = ban_state.mark_banned(until=_now() + timedelta(hours=1))
    assert ban_state.is_banned() is True
    assert ban_state.banned_until() is not None
    # Persisted expiry matches what we set (to the second).
    assert abs((ban_state.banned_until() - expiry).total_seconds()) < 2


def test_default_cooldown_applied(sentinel: Path) -> None:
    before = _now()
    ban_state.mark_banned()  # uses DEFAULT_COOLDOWN
    expiry = ban_state.banned_until()
    assert expiry is not None
    delta = expiry - before
    # Within a few seconds of the 3h default.
    assert abs(delta - ban_state.DEFAULT_COOLDOWN) < timedelta(seconds=5)


def test_ban_expires(sentinel: Path) -> None:
    past = _now() - timedelta(seconds=1)
    ban_state.mark_banned(until=past)
    # An already-past expiry → not currently banned.
    assert ban_state.is_banned() is False


def test_is_banned_with_explicit_now(sentinel: Path) -> None:
    expiry = _now() + timedelta(hours=2)
    ban_state.mark_banned(until=expiry)
    # 1h from now: still banned.
    assert ban_state.is_banned(now=_now() + timedelta(hours=1)) is True
    # 3h from now: ban lifted.
    assert ban_state.is_banned(now=_now() + timedelta(hours=3)) is False


# ---------------------------------------------------------------------------
# Never-shorten rule
# ---------------------------------------------------------------------------


def test_second_ban_does_not_shorten_existing(sentinel: Path) -> None:
    long_expiry = _now() + timedelta(hours=5)
    ban_state.mark_banned(until=long_expiry)
    # A second 429 with a shorter cooldown must NOT reset the clock earlier.
    returned = ban_state.mark_banned(until=_now() + timedelta(minutes=10))
    assert abs((returned - long_expiry).total_seconds()) < 2
    assert abs((ban_state.banned_until() - long_expiry).total_seconds()) < 2


def test_second_ban_extends_when_later(sentinel: Path) -> None:
    ban_state.mark_banned(until=_now() + timedelta(hours=1))
    later = _now() + timedelta(hours=4)
    returned = ban_state.mark_banned(until=later)
    assert abs((returned - later).total_seconds()) < 2


# ---------------------------------------------------------------------------
# clear / remaining
# ---------------------------------------------------------------------------


def test_clear_removes_sentinel(sentinel: Path) -> None:
    ban_state.mark_banned(until=_now() + timedelta(hours=1))
    assert sentinel.exists()
    ban_state.clear()
    assert not sentinel.exists()
    assert ban_state.is_banned() is False


def test_clear_is_noop_when_absent(sentinel: Path) -> None:
    # Must not raise.
    ban_state.clear()


def test_remaining_reports_time_left(sentinel: Path) -> None:
    ban_state.mark_banned(until=_now() + timedelta(minutes=30))
    rem = ban_state.remaining()
    assert rem is not None
    assert timedelta(minutes=29) < rem <= timedelta(minutes=30)


def test_remaining_none_when_expired(sentinel: Path) -> None:
    ban_state.mark_banned(until=_now() - timedelta(seconds=1))
    assert ban_state.remaining() is None


# ---------------------------------------------------------------------------
# Atomic write — reason persisted, no torn file
# ---------------------------------------------------------------------------


def test_reason_is_persisted(sentinel: Path) -> None:
    ban_state.mark_banned(until=_now() + timedelta(hours=1), reason="429 from query endpoint")
    data = json.loads(sentinel.read_text(encoding="utf-8"))
    assert data["reason"] == "429 from query endpoint"
    assert "marked_at" in data
    assert "banned_until" in data


def test_no_temp_files_left_after_write(sentinel: Path) -> None:
    ban_state.mark_banned(until=_now() + timedelta(hours=1))
    leftovers = list(sentinel.parent.glob(".arxiv_ban_*.tmp"))
    assert leftovers == [], f"temp files left behind: {leftovers}"
