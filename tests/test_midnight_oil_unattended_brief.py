"""Red-proof tests for Midnight Oil unattended brief pure module."""

from __future__ import annotations

import pytest

from substrate.midnight_oil.unattended_brief import (
    UnattendedBriefError,
    build_unattended_brief,
)


def test_valid_brief() -> None:
    b = build_unattended_brief(
        duration_minutes=120,
        goals=["map transformer scaling laws"],
        approved_ceiling_cents=500,
        recommended_ceiling_cents=400,
    )
    d = b.to_dict()
    assert d["duration_minutes"] == 120
    assert d["goals"] == ["map transformer scaling laws"]
    assert d["approved_ceiling_cents"] == 500
    assert d["live_execution_authorized"] is False
    assert d["authority"] == "operator_brief_only"
    assert any("exceeds recommended" in n for n in d["notes"])


def test_empty_goals_rejected() -> None:
    with pytest.raises(UnattendedBriefError, match="goals"):
        build_unattended_brief(
            duration_minutes=60,
            goals=[],
            approved_ceiling_cents=100,
        )


def test_bool_not_int_for_money() -> None:
    with pytest.raises(UnattendedBriefError, match="approved_ceiling_cents"):
        build_unattended_brief(
            duration_minutes=60,
            goals=["x"],
            approved_ceiling_cents=True,  # type: ignore[arg-type]
        )


def test_duration_bounds() -> None:
    with pytest.raises(UnattendedBriefError, match="duration_minutes"):
        build_unattended_brief(
            duration_minutes=0,
            goals=["x"],
            approved_ceiling_cents=1,
        )
    with pytest.raises(UnattendedBriefError, match="duration_minutes"):
        build_unattended_brief(
            duration_minutes=24 * 60 + 1,
            goals=["x"],
            approved_ceiling_cents=1,
        )


def test_control_chars_in_goal_rejected() -> None:
    with pytest.raises(UnattendedBriefError, match="control"):
        build_unattended_brief(
            duration_minutes=30,
            goals=["bad\ngoal"],
            approved_ceiling_cents=0,
        )


def test_zero_ceiling_note() -> None:
    b = build_unattended_brief(
        duration_minutes=30,
        goals=["read only"],
        approved_ceiling_cents=0,
    )
    assert any("zero ceiling" in n for n in b.notes)
    assert b.to_dict()["live_execution_authorized"] is False
