"""Agents layer write_log purpose registry."""

from __future__ import annotations

from substrate.analytics.agent_write_purposes import (
    is_agent_write_purpose,
    sql_agent_purpose_predicate,
)


def test_exact_agent_purposes() -> None:
    assert is_agent_write_purpose("promotion_funnel")
    assert is_agent_write_purpose("cascade_merge")
    assert is_agent_write_purpose("merge_staging")
    assert not is_agent_write_purpose("sections/create")


def test_prefix_agent_purposes() -> None:
    assert is_agent_write_purpose("monitor_create")
    assert is_agent_write_purpose("exercise:substrate")


def test_sql_predicate_contains_exact() -> None:
    sql = sql_agent_purpose_predicate()
    assert "promotion_funnel" in sql
    assert "monitor_" in sql