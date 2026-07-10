"""Residual (adb): Midnight Oil job persists fanout_depth for ceiling formula honesty."""

from __future__ import annotations

from substrate.midnight_oil.job import InMemoryJobStore, get_job
from substrate.midnight_oil.product_path import create_with_recommended_ceiling


def test_create_persists_fanout_depth_on_job_and_payload() -> None:
    store = InMemoryJobStore()
    result = create_with_recommended_ceiling(
        ["Map residual risks"],
        30,
        store=store,
        fanout_depth=5,
        research_tier="deep",
    )
    assert result.job.fanout_depth == 5
    payload = result.to_dict()
    assert payload["fanout_depth"] == 5
    assert payload["view_format"] == "html"
    reloaded = get_job(result.job.job_id, store=store)
    assert reloaded is not None
    assert reloaded.fanout_depth == 5


def test_create_default_fanout_depth_three() -> None:
    store = InMemoryJobStore()
    result = create_with_recommended_ceiling(
        ["Default fanout"],
        10,
        store=store,
    )
    assert result.job.fanout_depth == 3
    assert result.to_dict()["fanout_depth"] == 3
